from pathlib import Path
from typing import Dict, Optional, Tuple
import pygame

from gui.config import ASSETS_DIR, PLAYER_COLORS, TILE_SIZE


class AssetManager:
    """
    Manages game surfaces and sprites.
    Loads external PNG assets from ASSETS_DIR if present, and generates
    classic Playing with Fire 2 styled procedural sprites as a fallback.
    """

    def __init__(self, assets_dir: Optional[Path] = None) -> None:
        self.assets_dir = Path(assets_dir) if assets_dir else ASSETS_DIR
        self.surfaces: Dict[str, pygame.Surface] = {}
        self.player_colors: Dict[int, Tuple[int, int, int]] = dict(PLAYER_COLORS)
        pygame.font.init()
        self._generate_procedural_assets()
        self._load_external_overrides()
        self._generate_dimmed_player_icons()

    @staticmethod
    def _optimize_surface(surf: pygame.Surface, has_alpha: bool = True) -> pygame.Surface:
        """Converts surface to the active display format for fast hardware/software blitting."""
        if pygame.display.get_surface() is not None:
            return surf.convert_alpha() if has_alpha else surf.convert()
        return surf

    def _generate_dimmed_player_icons(self) -> None:
        for pid in self.player_colors:
            icon = self.surfaces.get(f"player_{pid}")
            if icon is not None:
                dim_icon = pygame.Surface(icon.get_size(), pygame.SRCALPHA)
                dim_icon.blit(icon, (0, 0))
                dim_icon.fill((90, 90, 90, 160), special_flags=pygame.BLEND_RGBA_MULT)
                self.surfaces[f"player_{pid}_dim"] = self._optimize_surface(dim_icon, has_alpha=True)

    def _load_external_overrides(self) -> None:
        if not self.assets_dir.exists() or not self.assets_dir.is_dir():
            return
        for png_file in self.assets_dir.glob("*.png"):
            key = png_file.stem
            try:
                loaded = pygame.image.load(str(png_file))
                scaled = pygame.transform.scale(loaded, (TILE_SIZE, TILE_SIZE))
                has_alpha = key not in ("floor", "solid")
                self.surfaces[key] = self._optimize_surface(scaled, has_alpha=has_alpha)
                print(f"Loaded external asset: {key}")
            except Exception:
                continue

    def _generate_procedural_assets(self) -> None:
        # 1. Floor (Dark asphalt tile with subtle grid bevel)
        floor = pygame.Surface((TILE_SIZE, TILE_SIZE))
        floor.fill((45, 42, 42))
        pygame.draw.rect(floor, (52, 49, 49), (1, 1, TILE_SIZE - 2, TILE_SIZE - 2), 1)
        pygame.draw.rect(floor, (33, 30, 30), (0, 0, TILE_SIZE, TILE_SIZE), 1)
        self.surfaces["floor"] = self._optimize_surface(floor, has_alpha=False)

        # 2. Solid Wall (Khaki/Sandstone beveled pillar matching original game)
        solid = pygame.Surface((TILE_SIZE, TILE_SIZE))
        solid.fill((185, 165, 110))
        pygame.draw.polygon(
            solid,
            (215, 198, 145),
            [(0, 0), (TILE_SIZE, 0), (TILE_SIZE - 6, 6), (6, 6), (6, TILE_SIZE - 6), (0, TILE_SIZE)],
        )
        pygame.draw.polygon(
            solid,
            (130, 112, 72),
            [(TILE_SIZE, 0), (TILE_SIZE, TILE_SIZE), (0, TILE_SIZE), (6, TILE_SIZE - 6), (TILE_SIZE - 6, TILE_SIZE - 6), (TILE_SIZE - 6, 6)],
        )
        pygame.draw.rect(solid, (105, 90, 58), (0, 0, TILE_SIZE, TILE_SIZE), 2)
        self.surfaces["solid"] = self._optimize_surface(solid, has_alpha=False)

        # 3. Breakable Wall (Classic wooden/reddish barrel with metal bands)
        breakable = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        barrel_rect = pygame.Rect(4, 2, TILE_SIZE - 8, TILE_SIZE - 4)
        pygame.draw.rect(breakable, (164, 96, 86), barrel_rect, border_radius=8)
        for plank_x in range(12, TILE_SIZE - 10, 10):
            pygame.draw.line(breakable, (135, 75, 68), (plank_x, 4), (plank_x, TILE_SIZE - 5), 2)
        pygame.draw.rect(breakable, (85, 85, 95), (4, TILE_SIZE // 3 - 2, TILE_SIZE - 8, 5))
        pygame.draw.rect(breakable, (85, 85, 95), (4, (2 * TILE_SIZE) // 3 - 2, TILE_SIZE - 8, 5))
        pygame.draw.rect(breakable, (95, 48, 42), barrel_rect, 2, border_radius=8)
        self.surfaces["breakable"] = self._optimize_surface(breakable, has_alpha=True)

        # 4. Power-up Badges
        font = pygame.font.SysFont(None, 32, bold=True)
        pu_colors = {
            "S": ((255, 165, 0), "S"),   # Speed
            "L": ((60, 140, 255), "L"),  # Lightning / Radius
            "+": ((235, 65, 65), "+"),   # Extra Bomb
            "H": ((195, 195, 205), "H"), # Hammer
            "R": ((255, 215, 40), "R"),  # Ring
        }
        for key, (color, text) in pu_colors.items():
            surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
            box = pygame.Rect(TILE_SIZE // 6, TILE_SIZE // 6, (2 * TILE_SIZE) // 3, (2 * TILE_SIZE) // 3)
            pygame.draw.rect(surf, (30, 34, 42), box, border_radius=6)
            pygame.draw.rect(surf, color, box, 3, border_radius=6)
            text_surf = font.render(text, True, color)
            text_rect = text_surf.get_rect(center=(TILE_SIZE // 2, TILE_SIZE // 2))
            surf.blit(text_surf, text_rect)
            self.surfaces[f"powerup_{key}"] = self._optimize_surface(surf, has_alpha=True)

        # 5. Players (Directional + Walking frames), Bombs (Pulsing), and Plasma Flames
        directions = {
            "down": (0, 1),
            "up": (0, -1),
            "left": (-1, 0),
            "right": (1, 0),
        }

        for pid, color in self.player_colors.items():
            for dir_name, (dx, dy) in directions.items():
                for frame in (0, 1):
                    psurf = self._optimize_surface(
                        self._create_player_sprite(color, dx, dy, frame), has_alpha=True
                    )
                    self.surfaces[f"player_{pid}_{dir_name}_{frame}"] = psurf
                self.surfaces[f"player_{pid}_{dir_name}"] = self.surfaces[f"player_{pid}_{dir_name}_0"]

            self.surfaces[f"player_{pid}"] = self.surfaces[f"player_{pid}_down_0"]

            for phase in range(3):
                bsurf = self._optimize_surface(
                    self._create_bomb_sprite(color, phase), has_alpha=True
                )
                self.surfaces[f"bomb_{pid}_{phase}"] = bsurf
            self.surfaces[f"bomb_{pid}"] = self.surfaces[f"bomb_{pid}_0"]

            fsurf = self._optimize_surface(self._create_flame_sprite(color), has_alpha=True)
            self.surfaces[f"flame_{pid}"] = fsurf

    def _create_player_sprite(
        self, color: Tuple[int, int, int], dx: int, dy: int, frame: int
    ) -> pygame.Surface:
        surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        cx, cy = TILE_SIZE // 2, TILE_SIZE // 2

        # Ground shadow
        pygame.draw.ellipse(surf, (0, 0, 0, 95), (10, TILE_SIZE - 12, TILE_SIZE - 20, 8))

        # Feet (animated shift based on frame)
        foot_offset = 3 if frame == 1 else -2
        pygame.draw.circle(surf, (40, 40, 45), (cx - 8, TILE_SIZE - 9 + foot_offset), 5)
        pygame.draw.circle(surf, (40, 40, 45), (cx + 8, TILE_SIZE - 9 - foot_offset), 5)

        # Body & Helmet
        pygame.draw.circle(surf, color, (cx, cy - 1), TILE_SIZE // 2 - 7)
        highlight = (min(255, color[0] + 70), min(255, color[1] + 70), min(255, color[2] + 70))
        pygame.draw.circle(surf, highlight, (cx - 6, cy - 8), 5)
        pygame.draw.circle(surf, (20, 20, 25), (cx, cy - 1), TILE_SIZE // 2 - 7, 2)

        # Visor & Eyes (omitted when facing up)
        if dy >= 0:
            visor_x = cx + dx * 5
            visor_y = cy - 3 + dy * 2
            visor_rect = pygame.Rect(visor_x - 11, visor_y - 6, 22, 12)
            pygame.draw.rect(surf, (240, 235, 220), visor_rect, border_radius=5)
            pygame.draw.rect(surf, (30, 30, 35), visor_rect, 1, border_radius=5)
            pygame.draw.circle(surf, (20, 20, 25), (visor_x - 5 + dx * 2, visor_y), 2)
            pygame.draw.circle(surf, (20, 20, 25), (visor_x + 5 + dx * 2, visor_y), 2)

        return surf

    def _create_bomb_sprite(self, owner_color: Tuple[int, int, int], phase: int) -> pygame.Surface:
        surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        cx, cy = TILE_SIZE // 2, TILE_SIZE // 2 + 2
        radius = (TILE_SIZE // 2 - 10) + phase * 2

        pygame.draw.circle(surf, (28, 30, 35), (cx, cy), radius)
        pygame.draw.circle(surf, (80, 85, 95), (cx - 5, cy - 5), max(2, radius // 3))
        pygame.draw.circle(surf, owner_color, (cx, cy), radius, 3)

        # Fuse and spark
        pygame.draw.line(surf, (180, 160, 120), (cx, cy - radius), (cx + 6, 6), 3)
        spark_color = (255, 240, 80) if phase < 2 else (255, 80, 40)
        pygame.draw.circle(surf, spark_color, (cx + 6, 6), 4 + phase)
        return surf

    def _create_flame_sprite(self, color: Tuple[int, int, int]) -> pygame.Surface:
        flame_surf = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        pygame.draw.rect(flame_surf, color, (TILE_SIZE // 4, 0, TILE_SIZE // 2, TILE_SIZE), border_radius=8)
        pygame.draw.rect(flame_surf, color, (0, TILE_SIZE // 4, TILE_SIZE, TILE_SIZE // 2), border_radius=8)

        bright_color = (min(255, color[0] + 100), min(255, color[1] + 100), min(255, color[2] + 100))
        pygame.draw.rect(
            flame_surf,
            bright_color,
            (TILE_SIZE // 3, TILE_SIZE // 6, TILE_SIZE // 3, (2 * TILE_SIZE) // 3),
            border_radius=4,
        )
        pygame.draw.rect(
            flame_surf,
            bright_color,
            (TILE_SIZE // 6, TILE_SIZE // 3, (2 * TILE_SIZE) // 3, TILE_SIZE // 3),
            border_radius=4,
        )
        return flame_surf

    def get(self, name: str) -> Optional[pygame.Surface]:
        return self.surfaces.get(name)
