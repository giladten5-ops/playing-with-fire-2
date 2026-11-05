import pygame
from gui.config import HUD_WIDTH, WINDOW_HEIGHT, TILE_SIZE

class HUDRenderer:
    def __init__(self, assets):
        self.assets = assets
        self.font_title = pygame.font.SysFont(None, 48, bold=True)
        self.font_text = pygame.font.SysFont(None, 28)
        self.bg_color = (25, 25, 30)
        self.border_color = (80, 80, 80)
        self.text_color = (240, 240, 240)

    def render(self, surface, snapshot):
        # 1. Background and border
        pygame.draw.rect(surface, self.bg_color, (0, 0, HUD_WIDTH, WINDOW_HEIGHT))
        pygame.draw.line(surface, self.border_color, (HUD_WIDTH - 2, 0), (HUD_WIDTH - 2, WINDOW_HEIGHT), 4)

        # 2. Timer (Mock for now)
        time_surf = self.font_title.render("3:00", True, (255, 200, 50))
        surface.blit(time_surf, (HUD_WIDTH // 2 - time_surf.get_width() // 2, 20))

        # 3. Player Stats
        y_offset = 100
        for pid, player in snapshot.players.items():
            # Draw player icon
            icon = self.assets.get(f'player_{pid}')
            if icon:
                surface.blit(icon, (20, y_offset))
            
            # Draw player name/status
            status_text = "ALIVE" if player.is_alive else "DEAD"
            color = self.text_color if player.is_alive else (100, 100, 100)
            
            name_surf = self.font_text.render(f"Player {pid}", True, color)
            status_surf = self.font_text.render(status_text, True, color)
            
            surface.blit(name_surf, (20 + TILE_SIZE + 10, y_offset + 5))
            surface.blit(status_surf, (20 + TILE_SIZE + 10, y_offset + 30))
            
            y_offset += TILE_SIZE + 30