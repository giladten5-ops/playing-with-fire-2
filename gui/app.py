import sys
from typing import Optional
import pygame

from gui.assets import AssetManager
from gui.board_renderer import BoardRenderer
from gui.config import (
    BOARD_HEIGHT_TILES,
    BOARD_WIDTH_TILES,
    COLOR_BG,
    TARGET_FPS,
    TICK_DURATION,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from gui.controllers import IPlayerController, KeyboardController, PPOAgentController
from gui.engine_adapter import CppGameSession
from gui.hud_renderer import HUDRenderer
from gui.state_snapshot import AIDebugSnapshot, GameSnapshot, IGameSession, PlayerAction


class BombermanGUIApp:
    """
    Main GUI application coordinator.
    Depends strictly on the abstract IGameSession and GameSnapshot domain models,
    keeping presentation and input completely decoupled from the C++ engine.
    """

    def __init__(self, session: Optional[IGameSession] = None) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Bomberman Grandmaster GUI")
        self.clock = pygame.time.Clock()

        self.session: IGameSession = session if session is not None else CppGameSession(
            BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES
        )

        self.assets = AssetManager()
        self.board_renderer = BoardRenderer(self.assets)
        self.hud_renderer = HUDRenderer(self.assets)

        self.human_controller = KeyboardController()
        self.ai_controller = PPOAgentController(player_id=1)
        self.ai_enabled = False
        self.debug_mode = False

        self.accumulator = 0.0
        self.sim_speed = 1.0
        self.paused = False

    @property
    def active_controller(self) -> IPlayerController:
        return self.ai_controller if self.ai_enabled else self.human_controller

    def handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_p:
                    self.paused = not self.paused
                elif event.key == pygame.K_n and self.paused:
                    action = self.active_controller.get_action(self.session)
                    self.session.step_tick(action)
                elif event.key == pygame.K_r:
                    self.session.reset(num_human=1, num_bots=3)
                    self.accumulator = 0.0
                    self.paused = False
                elif event.key == pygame.K_a:
                    self.ai_enabled = not self.ai_enabled
                elif event.key == pygame.K_d:
                    self.debug_mode = not self.debug_mode
        return True

    def render(self, snapshot: GameSnapshot) -> None:
        self.screen.fill(COLOR_BG)
        self.board_renderer.render(
            self.screen,
            snapshot,
            debug_mode=self.debug_mode,
            paused=self.paused,
        )
        self.hud_renderer.render(
            self.screen,
            snapshot,
            ai_enabled=self.ai_enabled,
            debug_mode=self.debug_mode,
        )
        pygame.display.flip()

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            running = self.handle_events()

            if not self.paused and not self.session.is_game_over():
                self.accumulator += dt * self.sim_speed

            while self.accumulator >= TICK_DURATION:
                if not self.session.is_game_over():
                    action = self.active_controller.get_action(self.session)
                    self.session.step_tick(action)
                self.accumulator -= TICK_DURATION

            alpha = (
                self.accumulator / TICK_DURATION
                if (not self.paused and not self.session.is_game_over())
                else 0.0
            )

            ai_debug: Optional[AIDebugSnapshot] = None
            if self.ai_enabled:
                ai_debug = self.ai_controller.get_debug_snapshot()
            elif self.debug_mode:
                ai_debug = self.ai_controller.compute_debug_only(self.session)

            snapshot = self.session.get_snapshot(alpha, ai_debug=ai_debug)
            self.render(snapshot)

            pygame.display.set_caption(f"Bomberman GUI | FPS: {self.clock.get_fps():.1f}")

        pygame.quit()
        sys.exit()
