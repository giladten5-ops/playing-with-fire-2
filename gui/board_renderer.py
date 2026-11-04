import pygame
from gui.config import TILE_SIZE, HUD_WIDTH, BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES

class BoardRenderer:
    def __init__(self, assets):
        self.assets = assets
        # Shift the entire board to the right to make room for the HUD on the left
        self.offset_x = HUD_WIDTH
        self.offset_y = 0

    def render(self, surface, snapshot, debug_mode=False):
        self._draw_background_and_walls(surface, snapshot.board)
        self._draw_powerups(surface, snapshot.powerups)
        # Next steps will add: bombs, flames, players, and debug overlays

    def _draw_background_and_walls(self, surface, board):
        floor_img = self.assets.get('floor')
        solid_img = self.assets.get('solid')
        break_img = self.assets.get('breakable')

        for y in range(BOARD_HEIGHT_TILES):
            for x in range(BOARD_WIDTH_TILES):
                px = self.offset_x + x * TILE_SIZE
                py = self.offset_y + y * TILE_SIZE
                
                # Floor is always at the bottom
                surface.blit(floor_img, (px, py))
                
                # Draw walls on top if they exist
                cell = board[y][x]
                if cell == 1:
                    surface.blit(solid_img, (px, py))
                elif cell == 2:
                    surface.blit(break_img, (px, py))

    def _draw_powerups(self, surface, powerups):
        for pu in powerups:
            px = self.offset_x + pu.grid_x * TILE_SIZE
            py = self.offset_y + pu.grid_y * TILE_SIZE
            img = self.assets.get(f'powerup_{pu.type_char}')
            if img:
                surface.blit(img, (px, py))