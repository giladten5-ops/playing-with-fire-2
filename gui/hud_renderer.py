from collections import OrderedDict
from typing import Tuple
import pygame

from gui.assets import AssetManager
from gui.config import (
    COLOR_HUD_BG,
    COLOR_HUD_BORDER,
    COLOR_HUD_CARD_ALIVE,
    COLOR_HUD_CARD_DEAD,
    COLOR_TEXT_DIM,
    COLOR_TEXT_MAIN,
    COLOR_TIMER_DANGER,
    COLOR_TIMER_NORMAL,
    ENGINE_TICK_RATE,
    HUD_WIDTH,
    TILE_SIZE,
    WINDOW_HEIGHT,
)
from gui.state_snapshot import GameSnapshot


class HUDRenderer:
    """
    Renders the left sidebar HUD:
    - Real-time engine countdown timer, live FPS badge, & Sudden Death alert.
    - Player status cards (showing ALIVE & DEAD players, lives, bombs, radius, speed, Hammer/Ring).
    - AI Telemetry & Control hints.
    Uses a bounded LRU text cache so unchanged labels are never re-rendered.
    """

    MAX_TEXT_CACHE_SIZE: int = 256

    def __init__(self, assets: AssetManager) -> None:
        self.assets = assets
        self.font_title = pygame.font.SysFont(None, 50, bold=True)
        self.font_header = pygame.font.SysFont(None, 26, bold=True)
        self.font_text = pygame.font.SysFont(None, 22)
        self.font_small = pygame.font.SysFont(None, 19)
        self._text_cache: "OrderedDict[Tuple[int, str, Tuple[int, int, int]], pygame.Surface]" = OrderedDict()

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

    def render(
        self,
        surface: pygame.Surface,
        snapshot: GameSnapshot,
        ai_enabled: bool = False,
        debug_mode: bool = False,
        fps: float = 0.0,
    ) -> None:
        # 1. Background and separator border
        pygame.draw.rect(surface, COLOR_HUD_BG, (0, 0, HUD_WIDTH, WINDOW_HEIGHT))
        pygame.draw.line(surface, COLOR_HUD_BORDER, (HUD_WIDTH - 2, 0), (HUD_WIDTH - 2, WINDOW_HEIGHT), 4)

        # 2. Real-time Sudden Death Countdown Timer & FPS indicator
        seconds_left = max(0, snapshot.sd_timer // ENGINE_TICK_RATE)
        minutes = seconds_left // 60
        seconds = seconds_left % 60
        time_str = f"{minutes}:{seconds:02d}"

        timer_color = COLOR_TIMER_DANGER if (snapshot.sd_active or seconds_left <= 15) else COLOR_TIMER_NORMAL
        time_surf = self._render_text_cached(self.font_title, time_str, timer_color)
        surface.blit(time_surf, (HUD_WIDTH // 2 - time_surf.get_width() // 2, 14))

        if fps > 0.0:
            fps_surf = self._render_text_cached(self.font_small, f"FPS: {int(round(fps))}", COLOR_TEXT_DIM)
            surface.blit(fps_surf, (HUD_WIDTH - 14 - fps_surf.get_width(), 16))

        if snapshot.sd_active:
            sd_surf = self._render_text_cached(self.font_header, "!! SUDDEN DEATH !!", COLOR_TIMER_DANGER)
            surface.blit(sd_surf, (HUD_WIDTH // 2 - sd_surf.get_width() // 2, 54))
        else:
            mode_label = "MODE: PPO AI AGENT" if ai_enabled else "MODE: HUMAN PLAYER"
            if debug_mode:
                mode_label += " [DEBUG]"
            mode_color = (90, 220, 130) if ai_enabled else (160, 185, 255)
            m_surf = self._render_text_cached(self.font_small, mode_label, mode_color)
            surface.blit(m_surf, (HUD_WIDTH // 2 - m_surf.get_width() // 2, 58))

        # 3. Player Status Cards
        y_offset = 84
        card_h = 98
        for pid in sorted(snapshot.players.keys()):
            player = snapshot.players[pid]
            card_bg = COLOR_HUD_CARD_ALIVE if player.is_alive else COLOR_HUD_CARD_DEAD
            card_rect = pygame.Rect(12, y_offset, HUD_WIDTH - 24, card_h)
            pygame.draw.rect(surface, card_bg, card_rect, border_radius=8)
            pygame.draw.rect(surface, COLOR_HUD_BORDER, card_rect, 1, border_radius=8)

            if player.is_alive:
                icon = self.assets.get(f"player_{pid}")
                if icon:
                    surface.blit(icon, (18, y_offset + 18))
            else:
                dim_icon = self.assets.get(f"player_{pid}_dim") or self.assets.get(f"player_{pid}")
                if dim_icon:
                    surface.blit(dim_icon, (18, y_offset + 18))

            if getattr(player, "is_trained_ai", False):
                role = "AI"
            elif player.is_bot:
                role = "BOT"
            elif ai_enabled and pid == 1:
                role = "AI"
            else:
                role = "YOU"
            status_str = f"HP: {player.lives}" if player.is_alive else "DEAD"
            title_color = COLOR_TEXT_MAIN if player.is_alive else COLOR_TEXT_DIM
            status_color = (95, 230, 115) if player.is_alive else (220, 75, 75)

            name_surf = self._render_text_cached(self.font_header, f"P{pid} ({role})", title_color)
            stat_surf = self._render_text_cached(self.font_header, status_str, status_color)
            surface.blit(name_surf, (22 + TILE_SIZE, y_offset + 10))
            surface.blit(stat_surf, (HUD_WIDTH - 24 - stat_surf.get_width(), y_offset + 10))

            info_line = f"Bombs: {player.avail_bombs}/{player.max_bombs}  |  Rad: {player.bomb_radius}  |  Spd: {player.speed_level}"
            info_surf = self._render_text_cached(self.font_text, info_line, title_color)
            surface.blit(info_surf, (22 + TILE_SIZE, y_offset + 40))

            badges = []
            if player.has_hammer:
                badges.append("[H: Hammer]")
            if player.has_ring:
                badges.append("[R: Ring]")
            if player.invincibility_timer > 0:
                badges.append("[SHIELD]")
            badge_str = " ".join(badges) if badges else "No special gear"
            badge_color = (255, 215, 70) if badges else COLOR_TEXT_DIM
            b_surf = self._render_text_cached(self.font_small, badge_str, badge_color)
            surface.blit(b_surf, (22 + TILE_SIZE, y_offset + 66))

            y_offset += card_h + 10

        # 4. AI Telemetry Panel (when AI or Debug is active)
        if snapshot.ai_debug is not None and (ai_enabled or debug_mode):
            dbg = snapshot.ai_debug
            panel_y = y_offset + 4
            val_text = f"AI Value: {dbg.value:+.2f} | Danger: {'YES' if dbg.in_danger else 'NO'}"
            if dbg.shield_intervened:
                val_text += " [SHIELD!]"
            v_surf = self._render_text_cached(self.font_small, val_text, (120, 230, 255))
            surface.blit(v_surf, (16, panel_y))
            if debug_mode:
                d_surf = self._render_text_cached(
                    self.font_small, "Heatmap: Green=Reach | Orange=Bomb", (90, 220, 130)
                )
                surface.blit(d_surf, (16, panel_y + 18))

        # 5. Footer Controls Help
        footer_y = WINDOW_HEIGHT - 64
        pygame.draw.line(surface, COLOR_HUD_BORDER, (12, footer_y - 6), (HUD_WIDTH - 12, footer_y - 6), 1)
        help_lines = [
            "Arrows+Space: P1 | WASD+E: P2",
            "P: Pause | R: Restart | M: Menu",
            "T: Toggle AI | H: Debug Heatmap",
        ]
        for idx, line in enumerate(help_lines):
            h_surf = self._render_text_cached(self.font_small, line, COLOR_TEXT_DIM)
            surface.blit(h_surf, (16, footer_y + idx * 19))
