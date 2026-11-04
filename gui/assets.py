import pygame
from gui.config import TILE_SIZE

class AssetManager:
    def __init__(self):
        self.surfaces = {}
        # We must call init for fonts
        pygame.font.init() 
        self._generate_assets()

    def _generate_assets(self):
        # 1. Floor (Beige/Tan color)
        floor = pygame.Surface((TILE_SIZE, TILE_SIZE))
        floor.fill((193, 175, 126))
        pygame.draw.rect(floor, (170, 150, 100), (0, 0, TILE_SIZE, TILE_SIZE), 1)
        self.surfaces['floor'] = floor

        # 2. Solid Wall (Khaki/Sand square with inner border)
        solid = pygame.Surface((TILE_SIZE, TILE_SIZE))
        solid.fill((185, 165, 110))
        pygame.draw.rect(solid, (140, 120, 80), (0, 0, TILE_SIZE, TILE_SIZE), 4)
        self.surfaces['solid'] = solid

        # 3. Breakable Wall (Brown reddish barrel style)
        breakable = pygame.Surface((TILE_SIZE, TILE_SIZE))
        breakable.fill((164, 98, 98))
        pygame.draw.line(breakable, (120, 60, 60), (0, TILE_SIZE // 3), (TILE_SIZE, TILE_SIZE // 3), 3)
        pygame.draw.line(breakable, (120, 60, 60), (0, 2 * TILE_SIZE // 3), (TILE_SIZE, 2 * TILE_SIZE // 3), 3)
        pygame.draw.rect(breakable, (100, 50, 50), (0, 0, TILE_SIZE, TILE_SIZE), 2)
        self.surfaces['breakable'] = breakable

        # 4. Power-ups (Dark square with colored letter for now)
        font = pygame.font.SysFont(None, 36, bold=True)
        pu_colors = {
            'S': ((255, 165, 0), "S"),   # Orange (Speed)
            'L': ((50, 100, 255), "L"),  # Blue (Lightning/Radius)
            '+': ((200, 50, 50), "+"),   # Red (Bomb amount)
            'H': ((180, 180, 180), "H"), # Grey (Hammer)
            'R': ((255, 215, 0), "R")    # Gold (Ring)
        }

        for key, (color, text) in pu_colors.items():
            surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
            # Dark background box
            pygame.draw.rect(surf, (40, 45, 50), (TILE_SIZE//6, TILE_SIZE//6, 2*TILE_SIZE//3, 2*TILE_SIZE//3))
            pygame.draw.rect(surf, color, (TILE_SIZE//6, TILE_SIZE//6, 2*TILE_SIZE//3, 2*TILE_SIZE//3), 2)
            # Letter
            text_surf = font.render(text, True, color)
            text_rect = text_surf.get_rect(center=(TILE_SIZE//2, TILE_SIZE//2))
            surf.blit(text_surf, text_rect)
            self.surfaces[f'powerup_{key}'] = surf

    def get(self, name: str) -> pygame.Surface:
        return self.surfaces.get(name)