from collections import OrderedDict
from typing import Dict, Optional, Tuple
import pygame

from gui.assets import AssetManager
from gui.config import BOARD_HEIGHT_TILES, BOARD_WIDTH_TILES, HUD_WIDTH, TILE_SIZE
from gui.state_snapshot import AIDebugSnapshot, GameSnapshot


class BoardRenderer:
    """
    Renders the 13x13 game board, entities, animations, AI debug heatmaps,
    and Game Over / Pause overlays purely from a GameSnapshot.
    Caches the static floor layer and the composite board (floor + walls) layer,
    rebuilding automatically whenever a breakable wall is destroyed or a
    Sudden Death block falls.
    """

    MAX_TEXT_CACHE_SIZE: int = 128

    def __init__(self, assets: AssetManager) -> None:
        self.assets = assets
        self.offset_x = HUD_WIDTH
        self.offset_y = 0
        self.board_w = BOARD_WIDTH_TILES * TILE_SIZE
        self.board_h = BOARD_HEIGHT_TILES * TILE_SIZE
        self.font_banner = pygame.font.SysFont(None, 54, bold=True)
        self.font_sub = pygame.font.SysFont(None, 30, bold=True)

        self._text_cache: "OrderedDict[Tuple[int, str, Tuple[int, int, int]], pygame.Surface]" = OrderedDict()
        self._debug_tile_cache: Dict[int, pygame.Surface] = {}
        self._debug_tile_overlay = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)

        self._game_over_overlay = pygame.Surface((self.board_w, 140), pygame.SRCALPHA)
        self._game_over_overlay.fill((15, 18, 24, 215))
        self._pause_overlay = pygame.Surface((self.board_w, 100), pygame.SRCALPHA)
        self._pause_overlay.fill((15, 18, 24, 195))
        if pygame.display.get_surface() is not None:
            self._game_over_overlay = self._game_over_overlay.convert_alpha()
            self._pause_overlay = self._pause_overlay.convert_alpha()

        self._floor_layer_surface: Optional[pygame.Surface] = None
        self._cached_floor_asset: Optional[pygame.Surface] = None
        self._cached_board_surface: Optional[pygame.Surface] = None
        self._cached_board_state: Optional[Tuple[Tuple[int, ...], ...]] = None
        self._cached_board_assets: Optional[
            Tuple[Optional[pygame.Surface], Optional[pygame.Surface], Optional[pygame.Surface]]
        ] = None
        self._ensure_floor_layer(self.assets.get("floor"))
        board_surf = pygame.Surface((self.board_w, self.board_h))
        if pygame.display.get_surface() is not None:
            board_surf = board_surf.convert()
        self._cached_board_surface = board_surf

    def invalidate_board_cache(self) -> None:
        """Explicitly invalidates the cached static/wall board state while retaining the surface buffer."""
        self._cached_board_state = None

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

    def _ensure_floor_layer(self, floor_img: Optional[pygame.Surface]) -> pygame.Surface:
        if self._floor_layer_surface is None or self._cached_floor_asset is not floor_img:
            floor_layer = pygame.Surface((self.board_w, self.board_h))
            floor_layer.fill((45, 42, 42))
            if floor_img is not None:
                for y in range(BOARD_HEIGHT_TILES):
                    py = y * TILE_SIZE
                    for x in range(BOARD_WIDTH_TILES):
                        floor_layer.blit(floor_img, (x * TILE_SIZE, py))
            if pygame.display.get_surface() is not None:
                floor_layer = floor_layer.convert()
            self._floor_layer_surface = floor_layer
            self._cached_floor_asset = floor_img
        return self._floor_layer_surface

    def render(
        self,
        surface: pygame.Surface,
        snapshot: GameSnapshot,
        debug_mode: bool = False,
        paused: bool = False,
    ) -> None:
        self._draw_background_and_walls(surface, snapshot.board)
        if debug_mode and snapshot.ai_debug is not None:
            self._draw_ai_debug_overlay(surface, snapshot.ai_debug)
        self._draw_powerups(surface, snapshot.powerups)
        self._draw_bombs(surface, snapshot.bombs)
        self._draw_flames(surface, snapshot.flames)
        self._draw_players(surface, snapshot.players, snapshot.tick_count)

        if snapshot.is_game_over:
            self._draw_game_over_overlay(surface, snapshot)
        elif paused:
            self._draw_pause_overlay(surface)

    def _draw_background_and_walls(self, surface: pygame.Surface, board) -> None:
        floor_img = self.assets.get("floor")
        solid_img = self.assets.get("solid")
        break_img = self.assets.get("breakable")

        board_key = tuple(tuple(row) for row in board)
        asset_key = (floor_img, solid_img, break_img)

        if (
            self._cached_board_surface is None
            or self._cached_board_state != board_key
            or self._cached_board_assets != asset_key
        ):
            floor_layer = self._ensure_floor_layer(floor_img)
            if self._cached_board_surface is None:
                board_surf = pygame.Surface((self.board_w, self.board_h))
                if pygame.display.get_surface() is not None:
                    board_surf = board_surf.convert()
                self._cached_board_surface = board_surf

            self._cached_board_surface.blit(floor_layer, (0, 0))
            for y in range(BOARD_HEIGHT_TILES):
                py = y * TILE_SIZE
                row = board_key[y]
                for x in range(BOARD_WIDTH_TILES):
                    cell = row[x]
                    if cell == 1 and solid_img is not None:
                        self._cached_board_surface.blit(solid_img, (x * TILE_SIZE, py))
                    elif cell == 2 and break_img is not None:
                        self._cached_board_surface.blit(break_img, (x * TILE_SIZE, py))

            self._cached_board_state = board_key
            self._cached_board_assets = asset_key

        surface.blit(self._cached_board_surface, (self.offset_x, self.offset_y))

    def _get_debug_tile_overlay(self, alpha: int) -> pygame.Surface:
        quantized_alpha = max(8, min(130, (alpha // 8) * 8))
        tile = self._debug_tile_cache.get(quantized_alpha)
        if tile is None:
            tile = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
            tile.fill((40, 220, 90, quantized_alpha))
            if pygame.display.get_surface() is not None:
                tile = tile.convert_alpha()
            self._debug_tile_cache[quantized_alpha] = tile
        return tile

    def _draw_ai_debug_overlay(self, surface: pygame.Surface, ai_debug: AIDebugSnapshot) -> None:
        if ai_debug.reach_map is not None:
            for y in range(BOARD_HEIGHT_TILES):
                for x in range(BOARD_WIDTH_TILES):
                    val = float(ai_debug.reach_map[y, x])
                    if val > 0.05:
                        alpha = int(min(130, val * 115))
                        tile_overlay = self._get_debug_tile_overlay(alpha)
                        px = self.offset_x + x * TILE_SIZE
                        py = self.offset_y + y * TILE_SIZE
                        surface.blit(tile_overlay, (px, py))

        if ai_debug.bomb_map is not None:
            for y in range(BOARD_HEIGHT_TILES):
                for x in range(BOARD_WIDTH_TILES):
                    bval = float(ai_debug.bomb_map[y, x])
                    if bval > 0.05:
                        px = self.offset_x + x * TILE_SIZE
                        py = self.offset_y + y * TILE_SIZE
                        pygame.draw.rect(
                            surface,
                            (255, 120, 30),
                            (px + 4, py + 4, TILE_SIZE - 8, TILE_SIZE - 8),
                            3,
                            border_radius=6,
                        )

    def _draw_powerups(self, surface: pygame.Surface, powerups) -> None:
        for pu in powerups:
            px = self.offset_x + pu.grid_x * TILE_SIZE
            py = self.offset_y + pu.grid_y * TILE_SIZE
            img = self.assets.get(f"powerup_{pu.type_char}")
            if img:
                surface.blit(img, (px, py))

    def _draw_bombs(self, surface: pygame.Surface, bombs) -> None:
        for bomb in bombs:
            px = self.offset_x + bomb.render_x * TILE_SIZE
            py = self.offset_y + bomb.render_y * TILE_SIZE

            if bomb.timer < 25:
                phase = 2
            elif bomb.timer < 55:
                phase = 1
            else:
                phase = 0

            img = (
                self.assets.get(f"bomb_{bomb.owner_id}_{phase}")
                or self.assets.get(f"bomb_{bomb.owner_id}")
                or self.assets.get("bomb_1")
            )
            if img:
                surface.blit(img, (px, py))

    def _draw_flames(self, surface: pygame.Surface, flames) -> None:
        for flame in flames:
            px = self.offset_x + flame.grid_x * TILE_SIZE
            py = self.offset_y + flame.grid_y * TILE_SIZE

            img = self.assets.get(f"flame_{flame.owner_id}") or self.assets.get("flame_1")
            if img:
                surface.blit(img, (px, py))

    def _draw_players(self, surface: pygame.Surface, players, tick_count: int) -> None:
        for pid, player in players.items():
            if not player.is_alive:
                continue

            # Blink effect during invincibility frames
            if player.invincibility_timer > 0 and (player.invincibility_timer % 4 < 2):
                continue

            px = self.offset_x + player.render_x * TILE_SIZE
            py = self.offset_y + player.render_y * TILE_SIZE

            if player.facing_dy < 0:
                dir_name = "up"
            elif player.facing_dy > 0:
                dir_name = "down"
            elif player.facing_dx < 0:
                dir_name = "left"
            else:
                dir_name = "right"

            frame = (tick_count // 4) % 2 if player.is_moving else 0
            img = (
                self.assets.get(f"player_{pid}_{dir_name}_{frame}")
                or self.assets.get(f"player_{pid}_{dir_name}")
                or self.assets.get(f"player_{pid}")
                or self.assets.get("player_1")
            )
            if img:
                surface.blit(img, (px, py))

            if player.has_ring:
                pygame.draw.circle(
                    surface,
                    (255, 215, 40),
                    (int(px + TILE_SIZE // 2), int(py + TILE_SIZE // 2)),
                    TILE_SIZE // 2 - 3,
                    2,
                )

    def _draw_game_over_overlay(self, surface: pygame.Surface, snapshot: GameSnapshot) -> None:
        board_w = BOARD_WIDTH_TILES * TILE_SIZE
        board_h = BOARD_HEIGHT_TILES * TILE_SIZE

        cy = board_h // 2 - 70
        surface.blit(self._game_over_overlay, (self.offset_x, cy))
        pygame.draw.rect(surface, (255, 210, 60), (self.offset_x, cy, board_w, 140), 3)

        winner_id = snapshot.winner_id
        if winner_id == -1:
            title_text = "IT'S A DRAW!"
            title_color = (230, 230, 230)
        else:
            winner = snapshot.players.get(winner_id)
            label = f"BOT {winner_id}" if (winner and winner.is_bot) else f"PLAYER {winner_id}"
            title_text = f"{label} WINS!"
            title_color = (255, 215, 60)

        t_surf = self._render_text_cached(self.font_banner, title_text, title_color)
        s_surf = self._render_text_cached(
            self.font_sub,
            "Press [R] Play Again  |  [M] Main Menu  |  [T] Toggle AI",
            (220, 225, 235),
        )

        surface.blit(t_surf, (self.offset_x + board_w // 2 - t_surf.get_width() // 2, cy + 28))
        surface.blit(s_surf, (self.offset_x + board_w // 2 - s_surf.get_width() // 2, cy + 88))

    def _draw_pause_overlay(self, surface: pygame.Surface) -> None:
        board_w = BOARD_WIDTH_TILES * TILE_SIZE
        board_h = BOARD_HEIGHT_TILES * TILE_SIZE

        cy = board_h // 2 - 50
        surface.blit(self._pause_overlay, (self.offset_x, cy))
        t_surf = self._render_text_cached(self.font_banner, "PAUSED", (255, 210, 60))
        s_surf = self._render_text_cached(
            self.font_sub,
            "Press [P] Resume  |  [N] Step  |  [M] Main Menu",
            (220, 225, 235),
        )
        surface.blit(t_surf, (self.offset_x + board_w // 2 - t_surf.get_width() // 2, cy + 16))
        surface.blit(s_surf, (self.offset_x + board_w // 2 - s_surf.get_width() // 2, cy + 62))
