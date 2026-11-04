import sys
import pygame
import bomberman_engine as bme
from gui.config import *
from gui.state_snapshot import SnapshotBuilder
from gui.assets import AssetManager
from gui.board_renderer import BoardRenderer
from gui.controllers import KeyboardController


class BombermanGUIApp:
    def __init__(self):
        pygame.init()
        # Initialize the main window using dimensions from config
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Bomberman Grandmaster GUI")
        self.clock = pygame.time.Clock()
        
        # Initialize C++ engine and snapshot builder
        self.game = bme.Game(BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES)
        self.snapshot_builder = SnapshotBuilder(BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES)

        self.game = bme.Game(BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES)
        self.snapshot_builder = SnapshotBuilder(BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES)
        
        self.assets = AssetManager()
        self.board_renderer = BoardRenderer(self.assets)

        self.assets = AssetManager()
        self.board_renderer = BoardRenderer(self.assets)
        
        # Initialize input controller
        self.controller = KeyboardController()
        
        # Timing variables for the Accumulator pattern
        self.accumulator = 0.0
        self.sim_speed = 1.0
        self.paused = False
        
        # Temporary setup to have something in the world
        # Generate a classic level (4 players total, 13x13 board, 65% breakable wall density)
        level = bme.ClassicLevel(4, BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES, 65)
        # Reset the game with 1 human and 3 bots
        self.game.reset(level, 1, 3)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                # Toggle pause with SPACE
                if event.key == pygame.K_p:
                    self.paused = not self.paused
                # Single step debugging with 'N' when paused
                elif event.key == pygame.K_n and self.paused:
                    self.game.update(bme.Command.NONE)
        return True

    def render(self, snapshot):
        # Fill the entire window (HUD area will stay dark grey for now)
        self.screen.fill(COLOR_BG)
        
        # Render the board (shifted to the right)
        self.board_renderer.render(self.screen, snapshot)
        
        pygame.display.flip()
    def run(self):
        running = True
        while running:
            # dt is the time passed since last frame in seconds
            dt = self.clock.tick(TARGET_FPS) / 1000.0  
            running = self.handle_events()

            if not self.paused:
                self.accumulator += dt * self.sim_speed

           # Advance engine in fixed timesteps
            while self.accumulator >= TICK_DURATION:
                # Get input from keyboard and step the engine
                cmd = self.controller.get_command()
                self.game.update(cmd)
                self.accumulator -= TICK_DURATION

            # Calculate interpolation factor (alpha)
            alpha = self.accumulator / TICK_DURATION if not self.paused else 0.0
            
            # Extract state and render
            snapshot = self.snapshot_builder.build_snapshot(self.game, alpha)
            self.render(snapshot)
            
            # Display real-time FPS in window title
            pygame.display.set_caption(f"Bomberman GUI | FPS: {self.clock.get_fps():.1f}")

        pygame.quit()
        sys.exit()