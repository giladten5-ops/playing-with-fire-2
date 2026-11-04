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
        self._draw_bombs(surface, snapshot.bombs)
        self._draw_flames(surface, snapshot.flames)
        self._draw_players(surface, snapshot.players)

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

    def _draw_bombs(self, surface, bombs):
        for bomb in bombs:
            # Use smooth render coordinates
            px = self.offset_x + bomb.render_x * TILE_SIZE
            py = self.offset_y + bomb.render_y * TILE_SIZE
            
            img = self.assets.get(f'bomb_{bomb.owner_id}')
            if not img:
                img = self.assets.get('bomb_1')  # Fallback
            surface.blit(img, (px, py))

    def _draw_flames(self, surface, flames):
        for flame in flames:
            px = self.offset_x + flame.grid_x * TILE_SIZE
            py = self.offset_y + flame.grid_y * TILE_SIZE
            
            img = self.assets.get(f'flame_{flame.owner_id}')
            if not img:
                img = self.assets.get('flame_1')  # Fallback
            surface.blit(img, (px, py))

    def _draw_players(self, surface, players):
        for pid, player in players.items():
            # Use smooth render coordinates for players
            px = self.offset_x + player.render_x * TILE_SIZE
            py = self.offset_y + player.render_y * TILE_SIZE
            
            img = self.assets.get(f'player_{pid}')
            if not img:
                img = self.assets.get('player_1')  # Fallback
            surface.blit(img, (px, py))