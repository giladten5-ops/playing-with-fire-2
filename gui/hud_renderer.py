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
    - Real-time engine countdown timer & Sudden Death alert.
    - Player status cards (showing ALIVE & DEAD players, lives, bombs, radius, speed, Hammer/Ring).
    - AI Telemetry & Control hints.
    """

    def __init__(self, assets: AssetManager) -> None:
        self.assets = assets
        self.font_title = pygame.font.SysFont(None, 50, bold=True)
        self.font_header = pygame.font.SysFont(None, 26, bold=True)
        self.font_text = pygame.font.SysFont(None, 22)
        self.font_small = pygame.font.SysFont(None, 19)

    def render(
        self,
        surface: pygame.Surface,
        snapshot: GameSnapshot,
        ai_enabled: bool = False,
        debug_mode: bool = False,
    ) -> None:
        # 1. Background and separator border
        pygame.draw.rect(surface, COLOR_HUD_BG, (0, 0, HUD_WIDTH, WINDOW_HEIGHT))
        pygame.draw.line(surface, COLOR_HUD_BORDER, (HUD_WIDTH - 2, 0), (HUD_WIDTH - 2, WINDOW_HEIGHT), 4)

        # 2. Real-time Sudden Death Countdown Timer
        seconds_left = max(0, snapshot.sd_timer // ENGINE_TICK_RATE)
        minutes = seconds_left // 60
        seconds = seconds_left % 60
        time_str = f"{minutes}:{seconds:02d}"

        timer_color = COLOR_TIMER_DANGER if (snapshot.sd_active or seconds_left <= 15) else COLOR_TIMER_NORMAL
        time_surf = self.font_title.render(time_str, True, timer_color)
        surface.blit(time_surf, (HUD_WIDTH // 2 - time_surf.get_width() // 2, 14))

        if snapshot.sd_active:
            sd_surf = self.font_header.render("!! SUDDEN DEATH !!", True, COLOR_TIMER_DANGER)
            surface.blit(sd_surf, (HUD_WIDTH // 2 - sd_surf.get_width() // 2, 54))
        else:
            mode_label = "MODE: PPO AI AGENT" if ai_enabled else "MODE: HUMAN PLAYER"
            mode_color = (90, 220, 130) if ai_enabled else (160, 185, 255)
            m_surf = self.font_small.render(mode_label, True, mode_color)
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

            icon = self.assets.get(f"player_{pid}")
            if icon:
                if player.is_alive:
                    surface.blit(icon, (18, y_offset + 18))
                else:
                    dim_icon = icon.copy()
                    dim_icon.fill((90, 90, 90, 160), special_flags=pygame.BLEND_RGBA_MULT)
                    surface.blit(dim_icon, (18, y_offset + 18))

            role = "BOT" if player.is_bot else ("AI" if ai_enabled and pid == 1 else "YOU")
            status_str = f"HP: {player.lives}" if player.is_alive else "DEAD"
            title_color = COLOR_TEXT_MAIN if player.is_alive else COLOR_TEXT_DIM
            status_color = (95, 230, 115) if player.is_alive else (220, 75, 75)

            name_surf = self.font_header.render(f"P{pid} ({role})", True, title_color)
            stat_surf = self.font_header.render(status_str, True, status_color)
            surface.blit(name_surf, (22 + TILE_SIZE, y_offset + 10))
            surface.blit(stat_surf, (HUD_WIDTH - 24 - stat_surf.get_width(), y_offset + 10))

            info_line = f"Bombs: {player.avail_bombs}/{player.max_bombs}  |  Rad: {player.bomb_radius}  |  Spd: {player.speed_level}"
            info_surf = self.font_text.render(info_line, True, title_color)
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
            b_surf = self.font_small.render(badge_str, True, badge_color)
            surface.blit(b_surf, (22 + TILE_SIZE, y_offset + 66))

            y_offset += card_h + 10

        # 4. AI Telemetry Panel (when AI or Debug is active)
        if snapshot.ai_debug is not None and (ai_enabled or debug_mode):
            dbg = snapshot.ai_debug
            panel_y = y_offset + 4
            val_text = f"AI Value: {dbg.value:+.2f} | Danger: {'YES' if dbg.in_danger else 'NO'}"
            if dbg.shield_intervened:
                val_text += " [SHIELD!]"
            v_surf = self.font_small.render(val_text, True, (120, 230, 255))
            surface.blit(v_surf, (16, panel_y))

        # 5. Footer Controls Help
        footer_y = WINDOW_HEIGHT - 64
        pygame.draw.line(surface, COLOR_HUD_BORDER, (12, footer_y - 6), (HUD_WIDTH - 12, footer_y - 6), 1)
        help_lines = [
            "Arrows: Move | Space: Bomb",
            "P: Pause | N: Step | R: Restart",
            "A: Toggle AI | D: Debug Heatmap",
        ]
        for idx, line in enumerate(help_lines):
            h_surf = self.font_small.render(line, True, COLOR_TEXT_DIM)
            surface.blit(h_surf, (16, footer_y + idx * 19))
