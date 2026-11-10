from collections import OrderedDict
import inspect
import sys
from typing import Dict, List, Optional, Tuple
import pygame

from gui.assets import AssetManager
from gui.board_renderer import BoardRenderer
from gui.config import (
    BOARD_HEIGHT_TILES,
    BOARD_WIDTH_TILES,
    COLOR_BG,
    LEVEL_PRESETS,
    TARGET_FPS,
    TICK_DURATION,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from gui.controllers import (
    IPlayerController,
    KeyboardController,
    PPOAgentController,
    Player2KeyboardController,
)
from gui.engine_adapter import CppGameSession
from gui.hud_renderer import HUDRenderer
from gui.state_snapshot import AIDebugSnapshot, GameSnapshot, IGameSession, PlayerAction


class BombermanGUIApp:
    """
    Main GUI application coordinator.
    Features a multi-step pre-game wizard menu styled after the classic
    'Playing with Fire 2' retro aesthetic with independent control over
    Human Players, DumbBots, and Trained AI opponents.
    """

    WINDOW_CAPTION: str = "Playing with Fire 2 — Bomberman GUI"
    MAX_FRAME_DELTA: float = 0.1
    MAX_TICKS_PER_FRAME: int = 3
    MAX_TOTAL_PLAYERS: int = 4
    MAX_HUMAN_PLAYERS: int = 2
    MAX_TEXT_CACHE_SIZE: int = 256
    MAX_BUTTON_CACHE_SIZE: int = 64

    # Multi-stage wizard states
    MENU_HUMANS: str = "MENU_HUMANS"
    MENU_DUMB_BOTS: str = "MENU_DUMB_BOTS"
    MENU_TRAINED_AI: str = "MENU_TRAINED_AI"
    MENU_LEVEL: str = "MENU_LEVEL"
    PLAYING: str = "PLAYING"

    # Aliases for backwards compatibility
    MENU_OPPONENTS: str = MENU_DUMB_BOTS
    MENU_AI_TYPE: str = MENU_TRAINED_AI

    STORY_LINES: Tuple[str, ...] = (
        "YOU HAVE LOST YOUR MATES, YOU'RE ON YOUR OWN.",
        "THE LOCAL NEIGHBORHOOD GANG ARE HUNTING YOU DOWN.",
        "BLAST YOUR WAY TO THEM BEFORE THEY KILL YOU!!",
    )

    def __init__(
        self,
        session: Optional[IGameSession] = None,
        start_in_menu: bool = True,
    ) -> None:
        pygame.display.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self._current_caption: str = ""
        self._set_window_caption(self.WINDOW_CAPTION)
        pygame.event.pump()
        self.clock = pygame.time.Clock()

        # Wizard selections dictionary with explicit dumb_bots and trained_ai counts
        self.menu_selections: Dict[str, object] = {
            "humans": 1,
            "dumb_bots": 3,
            "trained_ai": 0,
            "opponents": 3,
            "level": "CLASSIC LEVEL",
        }
        self.num_human: int = 1
        self.num_dumb_bots: int = 3
        self.num_trained_ai: int = 0
        self.num_bots: int = 3
        self.level_id: int = 1

        self.menu_state: str = self.MENU_HUMANS if start_in_menu else self.PLAYING
        self.menu_selected_index: int = 0
        self._menu_hitboxes: Dict[int, pygame.Rect] = {}
        self._text_cache: "OrderedDict[Tuple[int, str, Tuple[int, int, int]], pygame.Surface]" = OrderedDict()
        self._button_cache: "OrderedDict[Tuple[str, bool, int, int], pygame.Surface]" = OrderedDict()

        self.session: IGameSession = session if session is not None else CppGameSession(
            BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES
        )
        self._cached_step_callable: Optional[object] = None
        self._step_accepts_p2: bool = False
        self._step_accepts_extra: bool = False
        self._cached_reset_callable: Optional[object] = None
        self._reset_accepts_level: bool = False
        self._reset_accepts_trained_ai: bool = False
        self._refresh_session_signatures()

        self.assets = AssetManager()
        self.board_renderer = BoardRenderer(self.assets)
        self.hud_renderer = HUDRenderer(self.assets)
        pygame.event.pump()

        # Resolve retro font once instead of repeating system font scans
        retro_fonts = ["PressStart2P", "Courier New", "Consolas", "DejaVu Sans Mono", "monospace"]
        matched_retro = pygame.font.match_font(retro_fonts, bold=True)
        if matched_retro:
            self.font_story = pygame.font.Font(matched_retro, 16)
            self.font_step_title = pygame.font.Font(matched_retro, 18)
            self.font_button = pygame.font.Font(matched_retro, 18)
            self.font_hint = pygame.font.Font(matched_retro, 14)
        else:
            self.font_story = pygame.font.SysFont(retro_fonts, 16, bold=True)
            self.font_step_title = pygame.font.SysFont(retro_fonts, 18, bold=True)
            self.font_button = pygame.font.SysFont(retro_fonts, 18, bold=True)
            self.font_hint = pygame.font.SysFont(retro_fonts, 14, bold=True)

        self._menu_bg_surface = self._build_retro_menu_bg()
        self._logo_surface = self._build_pwf2_logo()
        pygame.event.pump()

        self.controller = KeyboardController()
        self.human_controller = self.controller
        self.p2_controller = Player2KeyboardController()
        self.ai_controller = PPOAgentController(player_id=1, lazy=True)
        self.opponent_ai_controllers: Dict[int, PPOAgentController] = {}
        self.ai_mode = False
        self.debug_mode = False

        self.accumulator = 0.0
        self.sim_speed = 1.0
        self.paused = False

    def _set_window_caption(self, caption: str) -> None:
        if caption != self._current_caption:
            pygame.display.set_caption(caption)
            self._current_caption = caption

    def _refresh_session_signatures(self) -> None:
        step_fn = getattr(self.session, "step_tick", None)
        if step_fn is not None and step_fn != self._cached_step_callable:
            sig = inspect.signature(step_fn)
            self._step_accepts_p2 = "p2_action" in sig.parameters
            self._step_accepts_extra = "extra_actions" in sig.parameters
            self._cached_step_callable = step_fn

        reset_fn = getattr(self.session, "reset", None)
        if reset_fn is not None and reset_fn != self._cached_reset_callable:
            rsig = inspect.signature(reset_fn)
            self._reset_accepts_level = "level_id" in rsig.parameters
            self._reset_accepts_trained_ai = "trained_ai_bots" in rsig.parameters
            self._cached_reset_callable = reset_fn

    def _render_text_cached(
        self,
        font: pygame.font.Font,
        text: str,
        color: Tuple[int, int, int],
    ) -> pygame.Surface:
        key = (id(font), text, (int(color[0]), int(color[1]), int(color[2])))
        cached = self._text_cache.get(key)
        if cached is not None:
            self._text_cache.move_to_end(key)
            return cached

        surf = font.render(text, True, color)
        if pygame.display.get_surface() is not None:
            surf = surf.convert_alpha()
        if len(self._text_cache) >= self.MAX_TEXT_CACHE_SIZE:
            self._text_cache.popitem(last=False)
        self._text_cache[key] = surf
        return surf

    @property
    def state(self) -> str:
        return self.menu_state

    @state.setter
    def state(self, value: str) -> None:
        self.menu_state = value

    @property
    def in_menu(self) -> bool:
        return self.menu_state != self.PLAYING

    @in_menu.setter
    def in_menu(self, value: bool) -> None:
        if value:
            if self.menu_state == self.PLAYING:
                self.menu_state = self.MENU_HUMANS
                self.menu_selected_index = 0
        else:
            self.menu_state = self.PLAYING

    @property
    def ai_enabled(self) -> bool:
        return self.ai_mode

    @ai_enabled.setter
    def ai_enabled(self, value: bool) -> None:
        self.ai_mode = bool(value)

    @property
    def active_controller(self) -> IPlayerController:
        return self.ai_controller if self.ai_mode else self.controller

    def _reset_input_controllers(self) -> None:
        self.controller.reset_state()
        self.p2_controller.reset_state()

    # ------------------------------------------------------------------
    # Retro 'Playing with Fire 2' Surface Builders
    # ------------------------------------------------------------------

    def _build_retro_menu_bg(self) -> pygame.Surface:
        """Pre-renders the dark textured stone/asphalt background from Playing with Fire 2."""
        surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        base_r, base_g, base_b = 48, 43, 37
        surf.fill((base_r, base_g, base_b))

        tile_size = 64
        grain_tile = pygame.Surface((tile_size, tile_size))
        grain_tile.fill((base_r, base_g, base_b))
        seed = 1337
        for y in range(0, tile_size, 2):
            for x in range(0, tile_size, 2):
                seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
                delta = ((seed >> 16) % 13) - 6
                col = (
                    max(24, min(72, base_r + delta)),
                    max(20, min(66, base_g + delta)),
                    max(16, min(58, base_b + delta)),
                )
                grain_tile.fill(col, (x, y, 2, 2))

        if pygame.display.get_surface() is not None:
            grain_tile = grain_tile.convert()
        for y in range(0, WINDOW_HEIGHT, tile_size):
            for x in range(0, WINDOW_WIDTH, tile_size):
                surf.blit(grain_tile, (x, y))

        # Top and bottom dark cinema bars
        bar_h = 26
        pygame.draw.rect(surf, (28, 25, 21), (0, 0, WINDOW_WIDTH, bar_h))
        pygame.draw.rect(surf, (28, 25, 21), (0, WINDOW_HEIGHT - bar_h, WINDOW_WIDTH, bar_h))
        pygame.draw.line(surf, (65, 58, 50), (0, bar_h), (WINDOW_WIDTH, bar_h), 1)
        pygame.draw.line(
            surf, (65, 58, 50), (0, WINDOW_HEIGHT - bar_h - 1), (WINDOW_WIDTH, WINDOW_HEIGHT - bar_h - 1), 1
        )

        # Top-right retro grey speaker button
        spk_rect = pygame.Rect(WINDOW_WIDTH - 96, 46, 56, 26)
        pygame.draw.rect(surf, (138, 138, 138), spk_rect, border_radius=3)
        pygame.draw.line(surf, (180, 180, 180), (spk_rect.left + 2, spk_rect.top + 2), (spk_rect.right - 3, spk_rect.top + 2), 2)
        pygame.draw.line(surf, (90, 90, 90), (spk_rect.left + 2, spk_rect.bottom - 2), (spk_rect.right - 3, spk_rect.bottom - 2), 2)
        pygame.draw.rect(surf, (24, 20, 16), spk_rect, 2, border_radius=3)

        cx, cy = spk_rect.centerx - 6, spk_rect.centery
        pygame.draw.rect(surf, (20, 20, 20), (cx - 6, cy - 3, 4, 6))
        pygame.draw.polygon(surf, (20, 20, 20), [(cx - 2, cy - 3), (cx + 4, cy - 7), (cx + 4, cy + 7), (cx - 2, cy + 3)])
        for r_off in (7, 11):
            pygame.draw.arc(
                surf, (35, 35, 35), (cx + 1, cy - r_off + 2, r_off, (r_off - 2) * 2), -0.7, 0.7, 2
            )

        if pygame.display.get_surface() is not None:
            surf = surf.convert()
        return surf

    @staticmethod
    def _render_fire_text(text: str, font: pygame.font.Font) -> pygame.Surface:
        """Renders bold text with a dark outline and yellow->orange->red vertical fire gradient."""
        base_mask = font.render(text, True, (255, 255, 255))
        w, h = base_mask.get_size()
        pad = 6
        out = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)

        outline_surf = font.render(text, True, (22, 14, 8))
        for dy in range(-4, 6):
            for dx in range(-4, 6):
                if dx * dx + dy * dy <= 20:
                    out.blit(outline_surf, (pad + dx, pad + dy))

        grad = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            t = y / max(1, h - 1)
            if t < 0.45:
                u = t / 0.45
                r = 255
                g = int(248 - u * 55)
                b = int(45 - u * 35)
            else:
                u = (t - 0.45) / 0.55
                r = int(255 - u * 35)
                g = int(193 - u * 155)
                b = 10
            pygame.draw.line(grad, (r, g, b, 255), (0, y), (w - 1, y))

        grad.blit(base_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        out.blit(grad, (pad, pad))
        return out

    def _build_pwf2_logo(self) -> pygame.Surface:
        """Builds the 'Playing with Fire 2' logo banner with the character mascot."""
        logo_w, logo_h = 460, 210
        surf = pygame.Surface((logo_w, logo_h), pygame.SRCALPHA)

        serif_fonts = ["Georgia", "Times New Roman", "DejaVu Serif", "serif"]
        matched_serif = pygame.font.match_font(serif_fonts, bold=True)
        if matched_serif:
            font_big = pygame.font.Font(matched_serif, 64)
            font_mid = pygame.font.Font(matched_serif, 42)
            font_sup = pygame.font.Font(matched_serif, 46)
        else:
            font_big = pygame.font.SysFont(serif_fonts, 64, bold=True)
            font_mid = pygame.font.SysFont(serif_fonts, 42, bold=True)
            font_sup = pygame.font.SysFont(serif_fonts, 46, bold=True)

        playing_surf = self._render_fire_text("Playing", font_big)
        with_surf = self._render_fire_text("with", font_mid)
        fire_surf = self._render_fire_text("Fire", font_big)

        sup_outline = font_sup.render("2", True, (18, 24, 38))
        sup_fill = font_sup.render("2", True, (75, 165, 245))
        sup_hi = font_sup.render("2", True, (165, 220, 255))

        surf.blit(playing_surf, (logo_w // 2 - playing_surf.get_width() // 2 + 10, 4))
        surf.blit(with_surf, (logo_w // 2 - with_surf.get_width() // 2 - 5, 72))
        fire_x = logo_w // 2 - fire_surf.get_width() // 2 + 28
        fire_y = 112
        surf.blit(fire_surf, (fire_x, fire_y))

        s2_x = fire_x + fire_surf.get_width() - 4
        s2_y = fire_y - 8
        for dy in range(-3, 5):
            for dx in range(-3, 5):
                if dx * dx + dy * dy <= 12:
                    surf.blit(sup_outline, (s2_x + dx, s2_y + dy))
        surf.blit(sup_fill, (s2_x, s2_y))
        surf.blit(sup_hi, (s2_x - 1, s2_y - 1), area=pygame.Rect(0, 0, sup_hi.get_width(), sup_hi.get_height() // 2))

        mx, my = 112, 132
        pygame.draw.ellipse(surf, (18, 16, 14, 210), (mx - 26, my + 42, 52, 18))
        pygame.draw.ellipse(surf, (20, 24, 34), (mx - 18, my + 38, 16, 11))
        pygame.draw.ellipse(surf, (20, 24, 34), (mx + 2, my + 38, 16, 11))
        pygame.draw.rect(surf, (20, 30, 55), (mx - 14, my + 12, 28, 30), border_radius=5)
        pygame.draw.rect(surf, (45, 105, 215), (mx - 12, my + 14, 24, 26), border_radius=4)
        pygame.draw.line(surf, (25, 55, 125), (mx, my + 28), (mx, my + 39), 2)
        pygame.draw.rect(surf, (30, 25, 20), (mx - 13, my + 25, 26, 5))
        pygame.draw.rect(surf, (215, 180, 45), (mx - 3, my + 25, 6, 5))
        pygame.draw.circle(surf, (22, 18, 15), (mx, my - 2), 18)
        pygame.draw.circle(surf, (232, 182, 142), (mx, my - 2), 15)
        pygame.draw.rect(surf, (30, 24, 20), (mx - 11, my - 5, 9, 6), 1)
        pygame.draw.rect(surf, (30, 24, 20), (mx + 2, my - 5, 9, 6), 1)
        pygame.draw.rect(surf, (245, 245, 245), (mx - 9, my - 4, 5, 4))
        pygame.draw.rect(surf, (245, 245, 245), (mx + 4, my - 4, 5, 4))
        pygame.draw.rect(surf, (20, 20, 25), (mx - 7, my - 3, 2, 2))
        pygame.draw.rect(surf, (20, 20, 25), (mx + 6, my - 3, 2, 2))
        pygame.draw.line(surf, (95, 55, 40), (mx - 4, my + 6), (mx + 4, my + 6), 2)
        pygame.draw.ellipse(surf, (20, 30, 55), (mx - 19, my - 24, 38, 22))
        pygame.draw.ellipse(surf, (55, 130, 235), (mx - 17, my - 22, 34, 18))
        pygame.draw.rect(surf, (35, 95, 195), (mx - 17, my - 11, 34, 6), border_radius=2)
        for rx in range(mx - 12, mx + 14, 6):
            pygame.draw.line(surf, (25, 65, 145), (rx, my - 11), (rx, my - 6), 1)

        pygame.draw.circle(surf, (232, 182, 142), (mx - 22, my + 18), 5)
        pygame.draw.line(surf, (165, 115, 65), (mx - 22, my + 18), (mx - 22, my + 4), 3)
        pygame.draw.polygon(surf, (235, 65, 15), [(mx - 27, my + 4), (mx - 22, my - 10), (mx - 17, my + 4)])
        pygame.draw.polygon(surf, (255, 215, 35), [(mx - 25, my + 4), (mx - 22, my - 5), (mx - 19, my + 4)])

        pygame.draw.circle(surf, (232, 182, 142), (mx + 19, my + 19), 5)
        pygame.draw.rect(surf, (25, 15, 15), (mx + 15, my + 13, 10, 20), border_radius=2)
        pygame.draw.rect(surf, (220, 40, 30), (mx + 16, my + 14, 8, 18), border_radius=1)
        pygame.draw.line(surf, (220, 200, 150), (mx + 20, my + 13), (mx + 24, my + 8), 2)

        if pygame.display.get_surface() is not None:
            surf = surf.convert_alpha()
        return surf

    # ------------------------------------------------------------------
    # Multi-Stage Wizard Logic (Explicit DumbBots & Trained AI Control)
    # ------------------------------------------------------------------

    def _get_trained_ai_range(self) -> Tuple[int, int]:
        humans = int(self.menu_selections.get("humans", 1))
        dumb_bots = int(self.menu_selections.get("dumb_bots", 0))
        max_ai = max(0, self.MAX_TOTAL_PLAYERS - humans - dumb_bots)
        min_ai = max(0, 2 - humans - dumb_bots)
        if min_ai > max_ai:
            min_ai = max_ai
        return min_ai, max_ai

    def _get_current_menu_options(self) -> List[str]:
        if self.menu_state == self.MENU_HUMANS:
            return ["1 PLAYER", "2 PLAYERS"]
        if self.menu_state == self.MENU_DUMB_BOTS:
            humans = int(self.menu_selections.get("humans", 1))
            max_dumb = max(0, self.MAX_TOTAL_PLAYERS - humans)
            return [f"{n} DUMB BOT" if n == 1 else f"{n} DUMB BOTS" for n in range(max_dumb + 1)]
        if self.menu_state == self.MENU_TRAINED_AI:
            min_ai, max_ai = self._get_trained_ai_range()
            return [f"{n} TRAINED AI" for n in range(min_ai, max_ai + 1)]
        if self.menu_state == self.MENU_LEVEL:
            return ["CLASSIC LEVEL"]
        return []

    def _get_step_heading(self) -> str:
        if self.menu_state == self.MENU_HUMANS:
            return "SELECT HUMAN PLAYERS"
        if self.menu_state == self.MENU_DUMB_BOTS:
            humans = int(self.menu_selections.get("humans", 1))
            return f"SELECT DUMB BOTS (0 - {self.MAX_TOTAL_PLAYERS - humans})"
        if self.menu_state == self.MENU_TRAINED_AI:
            min_ai, max_ai = self._get_trained_ai_range()
            return f"SELECT TRAINED AI OPPONENTS ({min_ai} - {max_ai})"
        if self.menu_state == self.MENU_LEVEL:
            return "SELECT LEVEL"
        return ""

    def _advance_menu_selection(self) -> None:
        options = self._get_current_menu_options()
        if not options:
            return
        idx = max(0, min(len(options) - 1, self.menu_selected_index))
        choice = options[idx]

        if self.menu_state == self.MENU_HUMANS:
            humans = 2 if choice.startswith("2") else 1
            self.menu_selections["humans"] = humans
            self.num_human = humans
            max_dumb = max(0, self.MAX_TOTAL_PLAYERS - humans)
            prev_dumb = int(self.menu_selections.get("dumb_bots", max_dumb))
            self.menu_selections["dumb_bots"] = max(0, min(max_dumb, prev_dumb))
            self.num_dumb_bots = int(self.menu_selections["dumb_bots"])
            self.menu_state = self.MENU_DUMB_BOTS
            self.menu_selected_index = 0

        elif self.menu_state == self.MENU_DUMB_BOTS:
            dumb_bots = idx
            self.menu_selections["dumb_bots"] = dumb_bots
            self.num_dumb_bots = dumb_bots
            min_ai, max_ai = self._get_trained_ai_range()
            prev_ai = int(self.menu_selections.get("trained_ai", min_ai))
            self.menu_selections["trained_ai"] = max(min_ai, min(max_ai, prev_ai))
            self.num_trained_ai = int(self.menu_selections["trained_ai"])
            self.num_bots = self.num_dumb_bots + self.num_trained_ai
            self.menu_selections["opponents"] = self.num_bots
            self.menu_state = self.MENU_TRAINED_AI
            self.menu_selected_index = 0

        elif self.menu_state == self.MENU_TRAINED_AI:
            min_ai, _ = self._get_trained_ai_range()
            trained_ai = min_ai + idx
            self.menu_selections["trained_ai"] = trained_ai
            self.num_trained_ai = trained_ai
            self.num_bots = self.num_dumb_bots + self.num_trained_ai
            self.menu_selections["opponents"] = self.num_bots
            self.menu_state = self.MENU_LEVEL
            self.menu_selected_index = 0

        elif self.menu_state == self.MENU_LEVEL:
            self.menu_selections["level"] = choice
            self.level_id = 1
            self.start_game()

    def _go_back_menu(self, allow_quit_on_root: bool = False) -> bool:
        """
        Moves one step back in the menu wizard.
        At the root menu (MENU_HUMANS), remains on MENU_HUMANS without quitting
        so pressing or holding ESC never accidentally closes the application.
        """
        if self.menu_state == self.MENU_LEVEL:
            self.menu_state = self.MENU_TRAINED_AI
            min_ai, _ = self._get_trained_ai_range()
            cur_ai = int(self.menu_selections.get("trained_ai", min_ai))
            self.menu_selected_index = max(0, cur_ai - min_ai)
            return True

        if self.menu_state == self.MENU_TRAINED_AI:
            self.menu_state = self.MENU_DUMB_BOTS
            self.menu_selected_index = int(self.menu_selections.get("dumb_bots", 0))
            return True

        if self.menu_state == self.MENU_DUMB_BOTS:
            self.menu_state = self.MENU_HUMANS
            self.menu_selected_index = 1 if int(self.menu_selections.get("humans", 1)) == 2 else 0
            return True

        return True

    def _reset_session(self) -> None:
        self._reset_input_controllers()
        self.num_human = max(0, min(self.MAX_HUMAN_PLAYERS, int(self.num_human)))
        max_opponents = max(0, self.MAX_TOTAL_PLAYERS - self.num_human)
        self.num_dumb_bots = max(0, min(max_opponents, int(self.num_dumb_bots)))
        self.num_trained_ai = max(0, min(max_opponents - self.num_dumb_bots, int(self.num_trained_ai)))
        self.num_bots = self.num_dumb_bots + self.num_trained_ai

        if self.num_trained_ai > 0 or self.ai_mode:
            self.ai_controller.ensure_model_loaded()

        self.opponent_ai_controllers.clear()
        for pid in range(self.num_human + 1, self.num_human + self.num_trained_ai + 1):
            self.opponent_ai_controllers[pid] = PPOAgentController(
                player_id=pid,
                shared_model=self.ai_controller.model,
                expected_channels=self.ai_controller.expected_channels,
                lazy=True,
            )

        self._refresh_session_signatures()
        kwargs: Dict[str, object] = {
            "num_human": self.num_human,
            "num_bots": self.num_bots,
        }
        if self._reset_accepts_level:
            kwargs["level_id"] = self.level_id
        if self._reset_accepts_trained_ai:
            kwargs["trained_ai_bots"] = self.num_trained_ai
        self.session.reset(**kwargs)  # type: ignore[arg-type]
        self.board_renderer.invalidate_board_cache()

    def start_game(self) -> None:
        self.num_human = int(self.menu_selections.get("humans", self.num_human))
        self.num_dumb_bots = int(self.menu_selections.get("dumb_bots", self.num_dumb_bots))
        self.num_trained_ai = int(self.menu_selections.get("trained_ai", self.num_trained_ai))
        self.num_bots = self.num_dumb_bots + self.num_trained_ai
        self.menu_selections["opponents"] = self.num_bots

        self._reset_session()
        self.ai_controller.reset()
        for ctrl in self.opponent_ai_controllers.values():
            ctrl.reset()
        if self.num_human == 0:
            self.ai_mode = False
        self.accumulator = 0.0
        self.paused = False
        self.menu_state = self.PLAYING
        self.clock.tick()
        lvl_name = str(
            self.menu_selections.get("level", LEVEL_PRESETS.get(self.level_id, ("CLASSIC LEVEL", 65, ""))[0])
        )
        print(
            f"[GUI] Starting match — Humans: {self.num_human}, DumbBots: {self.num_dumb_bots}, "
            f"Trained AI: {self.num_trained_ai}, Level: {lvl_name}"
        )

    @staticmethod
    def _is_hotkey(
        event: pygame.event.Event,
        key_codes: tuple,
        scan_code: int,
        chars: str,
    ) -> bool:
        if getattr(event, "key", None) in key_codes:
            return True
        ev_scan = getattr(event, "scancode", None)
        if ev_scan is not None and scan_code != 0 and ev_scan == scan_code:
            return True
        uni = getattr(event, "unicode", "")
        if uni and uni in chars:
            return True
        return False

    def handle_events(self) -> bool:
        # System hotkeys (completely disjoint from P1 Arrows+Space and P2 WASD+E+LShift):
        # P (scancode 19): Pause
        # N (scancode 17): Single-step when paused
        # R (scancode 21) / F5: Restart match (strictly physical R, not E)
        # T (scancode 23) / F1: Toggle AI control for Player 1 (removed from A)
        # H (scancode 11) / F2: Toggle AI Debug Heatmap (removed from D)
        # M (scancode 16) / ESC: Return to Main Menu
        kscan_p = getattr(pygame, "KSCAN_P", 19)
        kscan_n = getattr(pygame, "KSCAN_N", 17)
        kscan_r = getattr(pygame, "KSCAN_R", 21)
        kscan_t = getattr(pygame, "KSCAN_T", 23)
        kscan_h = getattr(pygame, "KSCAN_H", 11)
        kscan_m = getattr(pygame, "KSCAN_M", 16)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if self.in_menu:
                options = self._get_current_menu_options()
                num_opts = max(1, len(options))

                if event.type == pygame.MOUSEMOTION:
                    for idx, rect in self._menu_hitboxes.items():
                        if rect.collidepoint(event.pos):
                            self.menu_selected_index = idx
                            break
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for idx, rect in self._menu_hitboxes.items():
                        if rect.collidepoint(event.pos):
                            self.menu_selected_index = idx
                            self._advance_menu_selection()
                            break
                    continue

                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        self._go_back_menu()
                        continue
                    if event.key == pygame.K_UP:
                        self.menu_selected_index = (self.menu_selected_index - 1) % num_opts
                        continue
                    if event.key == pygame.K_DOWN:
                        self.menu_selected_index = (self.menu_selected_index + 1) % num_opts
                        continue
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                        self._advance_menu_selection()
                        continue
                    continue

            if event.type == pygame.KEYUP:
                self.controller.handle_event(event)
                if self.num_human >= 2:
                    self.p2_controller.handle_event(event)
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.menu_state = self.MENU_HUMANS
                    self.menu_selected_index = 0
                    self.paused = False
                    self.accumulator = 0.0
                    self._reset_input_controllers()
                    self.clock.tick()
                    continue

                if self._is_hotkey(event, (pygame.K_m, ord("M"), ord("\u05e6")), kscan_m, "mM\u05e6"):
                    self.menu_state = self.MENU_HUMANS
                    self.menu_selected_index = 0
                    self.paused = False
                    self.accumulator = 0.0
                    self._reset_input_controllers()
                    self.clock.tick()
                elif self._is_hotkey(event, (pygame.K_p, ord("P"), ord("\u05e4")), kscan_p, "pP\u05e4"):
                    self.paused = not self.paused
                    self.accumulator = 0.0
                    self._reset_input_controllers()
                    self.clock.tick()
                elif self._is_hotkey(event, (pygame.K_n, ord("N"), ord("\u05de")), kscan_n, "nN\u05de") and self.paused:
                    self._step_single_tick()
                elif (
                    self._is_hotkey(event, (pygame.K_r, ord("R"), ord("\u05e8")), kscan_r, "rR\u05e8")
                    or event.key == pygame.K_F5
                ):
                    self._reset_session()
                    self.ai_controller.reset()
                    for ctrl in self.opponent_ai_controllers.values():
                        ctrl.reset()
                    self.accumulator = 0.0
                    self.paused = False
                    self.clock.tick()
                    print("[GUI] Game restarted.")
                elif (
                    self._is_hotkey(event, (pygame.K_t, ord("T"), ord("\u05d0")), kscan_t, "tT\u05d0")
                    or event.key == pygame.K_F1
                ):
                    self.ai_mode = not self.ai_mode
                    if self.ai_mode:
                        self.ai_controller.ensure_model_loaded()
                    self.ai_controller.reset()
                    self._reset_input_controllers()
                    self.accumulator = 0.0
                    self.clock.tick()
                    status = "AI (PPO Agent)" if self.ai_mode else "HUMAN (Keyboard)"
                    print(f"[GUI] AI Mode toggled: {self.ai_mode} — Control: {status}")
                elif (
                    self._is_hotkey(event, (pygame.K_h, ord("H"), ord("\u05d9")), kscan_h, "hH\u05d9")
                    or event.key == pygame.K_F2
                ):
                    self.debug_mode = not self.debug_mode
                    self.clock.tick()
                    print(f"[GUI] Debug overlay: {'ON' if self.debug_mode else 'OFF'}")
                else:
                    self.controller.handle_event(event)
                    if self.num_human >= 2:
                        self.p2_controller.handle_event(event)
        return True

    def _step_single_tick(self) -> None:
        if self.num_human == 0:
            action = PlayerAction.NONE
            p2_action = None
        elif self.ai_mode:
            action = self.ai_controller.get_command(self.session)
            p2_action = self.p2_controller.get_command(self.session) if self.num_human >= 2 else None
        else:
            action = self.controller.get_command()
            p2_action = self.p2_controller.get_command(self.session) if self.num_human >= 2 else None

        extra_actions: Optional[Dict[int, PlayerAction]] = None
        if self.opponent_ai_controllers:
            extra_actions = {
                pid: ctrl.get_command(self.session)
                for pid, ctrl in self.opponent_ai_controllers.items()
            }

        self._refresh_session_signatures()
        kwargs: Dict[str, object] = {}
        if p2_action is not None and self._step_accepts_p2:
            kwargs["p2_action"] = p2_action
        if extra_actions and self._step_accepts_extra:
            kwargs["extra_actions"] = extra_actions
        self.session.step_tick(action, **kwargs)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Retro Menu Rendering
    # ------------------------------------------------------------------

    def _draw_retro_button(
        self,
        rect: pygame.Rect,
        label: str,
        is_selected: bool,
    ) -> None:
        """Draws a wide 'Playing with Fire 2' rectangular button with a left '->' compartment."""
        cache_key = (label, is_selected, rect.width, rect.height)
        btn_surf = self._button_cache.get(cache_key)
        if btn_surf is not None:
            self._button_cache.move_to_end(cache_key)
            self.screen.blit(btn_surf, rect.topleft)
            return

        btn_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        local_rect = pygame.Rect(0, 0, rect.width, rect.height)

        if is_selected:
            fill_col = (244, 206, 22)
            hi_col = (255, 240, 120)
            sh_col = (182, 142, 10)
            div_dark = (145, 112, 8)
            div_light = (255, 235, 110)
            txt_hi_col = (255, 242, 155)
        else:
            fill_col = (138, 138, 138)
            hi_col = (182, 182, 182)
            sh_col = (90, 90, 90)
            div_dark = (88, 88, 88)
            div_light = (172, 172, 172)
            txt_hi_col = (176, 176, 176)

        border_col = (22, 18, 14)

        pygame.draw.rect(btn_surf, fill_col, local_rect, border_radius=6)
        pygame.draw.line(
            btn_surf, hi_col, (4, 2), (local_rect.right - 5, 2), 2
        )
        pygame.draw.line(
            btn_surf, hi_col, (2, 4), (2, local_rect.bottom - 5), 2
        )
        pygame.draw.line(
            btn_surf, sh_col, (4, local_rect.bottom - 3), (local_rect.right - 5, local_rect.bottom - 3), 2
        )
        pygame.draw.line(
            btn_surf, sh_col, (local_rect.right - 3, 4), (local_rect.right - 3, local_rect.bottom - 5), 2
        )
        pygame.draw.rect(btn_surf, border_col, local_rect, 2, border_radius=6)

        arrow_box_w = 46
        div_x = arrow_box_w
        pygame.draw.line(btn_surf, div_dark, (div_x, 3), (div_x, local_rect.bottom - 4), 2)
        pygame.draw.line(btn_surf, div_light, (div_x + 2, 3), (div_x + 2, local_rect.bottom - 4), 1)

        acx = arrow_box_w // 2
        acy = local_rect.centery
        arrow_col = (24, 22, 20)
        pygame.draw.line(btn_surf, arrow_col, (acx - 7, acy), (acx + 5, acy), 2)
        pygame.draw.polygon(
            btn_surf,
            arrow_col,
            [(acx + 1, acy - 5), (acx + 7, acy), (acx + 1, acy + 5)],
        )

        text_center_x = div_x + (local_rect.width - arrow_box_w) // 2
        text_center_y = local_rect.centery

        hi_surf = self._render_text_cached(self.font_button, label, txt_hi_col)
        txt_surf = self._render_text_cached(self.font_button, label, (22, 22, 32))
        tx = text_center_x - txt_surf.get_width() // 2
        ty = text_center_y - txt_surf.get_height() // 2
        btn_surf.blit(hi_surf, (tx + 1, ty + 1))
        btn_surf.blit(txt_surf, (tx, ty))

        if pygame.display.get_surface() is not None:
            btn_surf = btn_surf.convert_alpha()
        if len(self._button_cache) >= self.MAX_BUTTON_CACHE_SIZE:
            self._button_cache.popitem(last=False)
        self._button_cache[cache_key] = btn_surf
        self.screen.blit(btn_surf, rect.topleft)

    def render_menu(self) -> None:
        self._menu_hitboxes.clear()
        self.screen.blit(self._menu_bg_surface, (0, 0))

        # 1. 'Playing with Fire 2' Retro Logo Banner
        logo_x = WINDOW_WIDTH // 2 - self._logo_surface.get_width() // 2
        logo_y = 66
        self.screen.blit(self._logo_surface, (logo_x, logo_y))

        # 2. Classic 3-line intro story text in white uppercase
        story_y = 304
        for line in self.STORY_LINES:
            shadow = self._render_text_cached(self.font_story, line, (18, 15, 12))
            fg = self._render_text_cached(self.font_story, line, (242, 242, 242))
            lx = WINDOW_WIDTH // 2 - fg.get_width() // 2
            self.screen.blit(shadow, (lx + 2, story_y + 2))
            self.screen.blit(fg, (lx, story_y))
            story_y += 24

        # 3. Current wizard step title
        step_heading = self._get_step_heading()
        step_shadow = self._render_text_cached(self.font_step_title, step_heading, (18, 15, 12))
        step_fg = self._render_text_cached(self.font_step_title, step_heading, (255, 218, 55))
        sx = WINDOW_WIDTH // 2 - step_fg.get_width() // 2
        sy = story_y + 18
        self.screen.blit(step_shadow, (sx + 2, sy + 2))
        self.screen.blit(step_fg, (sx, sy))

        # 4. Wide rectangular option buttons (yellow for selected, grey for unselected)
        options = self._get_current_menu_options()
        btn_w, btn_h = 330, 42
        btn_x = WINDOW_WIDTH // 2 - btn_w // 2
        btn_y = sy + 38
        btn_gap = 14

        for idx, opt_label in enumerate(options):
            rect = pygame.Rect(btn_x, btn_y + idx * (btn_h + btn_gap), btn_w, btn_h)
            self._menu_hitboxes[idx] = rect
            self._draw_retro_button(rect, opt_label, is_selected=(idx == self.menu_selected_index))

        # 5. Summary breadcrumb & keyboard controls footer
        if self.menu_state != self.MENU_HUMANS:
            h_cnt = int(self.menu_selections.get("humans", 1))
            crumbs = [f"HUMANS: {h_cnt}"]
            if self.menu_state in (self.MENU_TRAINED_AI, self.MENU_LEVEL):
                d_cnt = int(self.menu_selections.get("dumb_bots", 0))
                crumbs.append(f"DUMB BOTS: {d_cnt}")
            if self.menu_state == self.MENU_LEVEL:
                t_cnt = int(self.menu_selections.get("trained_ai", 0))
                d_cnt = int(self.menu_selections.get("dumb_bots", 0))
                crumbs.append(f"TRAINED AI: {t_cnt}")
                crumbs.append(f"TOTAL: {h_cnt + d_cnt + t_cnt}/{self.MAX_TOTAL_PLAYERS}")
            crumb_str = "   |   ".join(crumbs)
            crumb_surf = self._render_text_cached(self.font_hint, crumb_str, (205, 200, 190))
            self.screen.blit(
                crumb_surf,
                (WINDOW_WIDTH // 2 - crumb_surf.get_width() // 2, WINDOW_HEIGHT - 82),
            )

        footer_text = (
            "UP / DOWN: SELECT     ENTER: CONFIRM     ESC / BACKSPACE: BACK"
            if self.menu_state != self.MENU_HUMANS
            else "UP / DOWN: SELECT     ENTER: CONFIRM"
        )
        foot_surf = self._render_text_cached(self.font_hint, footer_text, (170, 165, 155))
        self.screen.blit(
            foot_surf,
            (WINDOW_WIDTH // 2 - foot_surf.get_width() // 2, WINDOW_HEIGHT - 54),
        )

        pygame.display.flip()

    def render(self, snapshot: GameSnapshot) -> None:
        self.board_renderer.render(
            self.screen,
            snapshot,
            debug_mode=self.debug_mode,
            paused=self.paused,
        )
        self.hud_renderer.render(
            self.screen,
            snapshot,
            ai_enabled=self.ai_mode,
            debug_mode=self.debug_mode,
            fps=self.clock.get_fps(),
        )
        pygame.display.flip()

    def _advance_simulation(self, dt: float) -> None:
        clamped_dt = min(max(0.0, dt), self.MAX_FRAME_DELTA)
        if self.in_menu or self.paused or self.session.is_game_over():
            self.accumulator = 0.0
            return

        self.accumulator += clamped_dt * self.sim_speed
        steps_this_frame = 0

        while self.accumulator >= TICK_DURATION and steps_this_frame < self.MAX_TICKS_PER_FRAME:
            if not self.session.is_game_over():
                self._step_single_tick()
            self.accumulator -= TICK_DURATION
            steps_this_frame += 1

        if steps_this_frame >= self.MAX_TICKS_PER_FRAME:
            # Drop excess accumulated time to prevent a fixed-timestep spiral of death
            self.accumulator = 0.0

    def run(self) -> None:
        running = True
        self.clock.tick()
        while running:
            raw_dt = self.clock.tick(TARGET_FPS) / 1000.0
            running = self.handle_events()
            if not running:
                break

            if self.in_menu:
                self.render_menu()
                continue

            self._advance_simulation(raw_dt)

            alpha = (
                self.accumulator / TICK_DURATION
                if (not self.paused and not self.session.is_game_over())
                else 0.0
            )

            ai_debug: Optional[AIDebugSnapshot] = None
            if self.debug_mode:
                ai_debug = self.ai_controller.compute_debug_only(self.session)
            elif self.ai_mode:
                ai_debug = self.ai_controller.get_debug_snapshot()
                if ai_debug is None:
                    ai_debug = self.ai_controller.compute_debug_only(self.session)

            snapshot = self.session.get_snapshot(alpha, ai_debug=ai_debug)
            self.render(snapshot)

        pygame.quit()
        sys.exit()
