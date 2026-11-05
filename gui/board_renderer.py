import pygame

from gui.assets import AssetManager
from gui.config import BOARD_HEIGHT_TILES, BOARD_WIDTH_TILES, HUD_WIDTH, TILE_SIZE
from gui.state_snapshot import AIDebugSnapshot, GameSnapshot


class BoardRenderer:
    """
    Renders the 13x13 game board, entities, animations, AI debug heatmaps,
    and Game Over / Pause overlays purely from a GameSnapshot.
    """

    def __init__(self, assets: AssetManager) -> None:
        self.assets = assets
        self.offset_x = HUD_WIDTH
        self.offset_y = 0
        self.font_banner = pygame.font.SysFont(None, 54, bold=True)
        self.font_sub = pygame.font.SysFont(None, 30, bold=True)

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

        for y in range(BOARD_HEIGHT_TILES):
            for x in range(BOARD_WIDTH_TILES):
                px = self.offset_x + x * TILE_SIZE
                py = self.offset_y + y * TILE_SIZE

                if floor_img:
                    surface.blit(floor_img, (px, py))

                cell = board[y][x]
                if cell == 1 and solid_img:
                    surface.blit(solid_img, (px, py))
                elif cell == 2 and break_img:
                    surface.blit(break_img, (px, py))

    def _draw_ai_debug_overlay(self, surface: pygame.Surface, ai_debug: AIDebugSnapshot) -> None:
        tile_overlay = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)

        if ai_debug.reach_map is not None:
            for y in range(BOARD_HEIGHT_TILES):
                for x in range(BOARD_WIDTH_TILES):
                    val = float(ai_debug.reach_map[y, x])
                    if val > 0.05:
                        alpha = int(min(130, val * 115))
                        tile_overlay.fill((40, 220, 90, alpha))
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
        overlay = pygame.Surface((board_w, 140), pygame.SRCALPHA)
        overlay.fill((15, 18, 24, 215))

        cy = board_h // 2 - 70
        surface.blit(overlay, (self.offset_x, cy))
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

        t_surf = self.font_banner.render(title_text, True, title_color)
        s_surf = self.font_sub.render("Press [R] to Play Again  |  [A] Toggle AI", True, (220, 225, 235))

        surface.blit(t_surf, (self.offset_x + board_w // 2 - t_surf.get_width() // 2, cy + 28))
        surface.blit(s_surf, (self.offset_x + board_w // 2 - s_surf.get_width() // 2, cy + 88))

    def _draw_pause_overlay(self, surface: pygame.Surface) -> None:
        board_w = BOARD_WIDTH_TILES * TILE_SIZE
        board_h = BOARD_HEIGHT_TILES * TILE_SIZE
        overlay = pygame.Surface((board_w, 100), pygame.SRCALPHA)
        overlay.fill((15, 18, 24, 195))

        cy = board_h // 2 - 50
        surface.blit(overlay, (self.offset_x, cy))
        t_surf = self.font_banner.render("PAUSED", True, (255, 210, 60))
        s_surf = self.font_sub.render("Press [P] to Resume  |  [N] Step Frame", True, (220, 225, 235))
        surface.blit(t_surf, (self.offset_x + board_w // 2 - t_surf.get_width() // 2, cy + 16))
        surface.blit(s_surf, (self.offset_x + board_w // 2 - s_surf.get_width() // 2, cy + 62))
