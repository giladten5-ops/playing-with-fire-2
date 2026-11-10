from pathlib import Path
from typing import Dict, Tuple

# --- Paths ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
MODELS_DIR = PROJECT_ROOT / "models"

DEFAULT_MODEL_PATHS = [
    MODELS_DIR / "v3_best" / "best_model.zip",
    MODELS_DIR / "ppo_grandmaster_v3.zip",
    MODELS_DIR / "v2_best" / "best_model.zip",
    MODELS_DIR / "ppo_bomberman_v2_strategic.zip",
]

# --- Display Settings ---
TILE_SIZE = 56
BOARD_WIDTH_TILES = 13
BOARD_HEIGHT_TILES = 13
HUD_WIDTH = 320

WINDOW_WIDTH = (BOARD_WIDTH_TILES * TILE_SIZE) + HUD_WIDTH
WINDOW_HEIGHT = BOARD_HEIGHT_TILES * TILE_SIZE

# --- Timing ---
TARGET_FPS = 60
ENGINE_TICK_RATE = 30
TICK_DURATION = 1.0 / ENGINE_TICK_RATE

# --- Colors ---
COLOR_BG = (30, 30, 30)
COLOR_GRID = (50, 50, 50)
COLOR_HUD_BG = (22, 24, 30)
COLOR_HUD_CARD_ALIVE = (36, 40, 50)
COLOR_HUD_CARD_DEAD = (28, 28, 34)
COLOR_HUD_BORDER = (75, 80, 95)
COLOR_TEXT_MAIN = (240, 240, 245)
COLOR_TEXT_DIM = (130, 135, 145)
COLOR_TIMER_NORMAL = (255, 210, 60)
COLOR_TIMER_DANGER = (255, 65, 65)

PLAYER_COLORS: Dict[int, Tuple[int, int, int]] = {
    1: (50, 120, 255),   # Blue
    2: (230, 55, 55),    # Red
    3: (170, 65, 220),   # Purple
    4: (55, 205, 65),    # Green
}

PLAYER_NAMES: Dict[int, str] = {
    1: "Player 1",
    2: "Player 2",
    3: "Player 3",
    4: "Player 4",
}

LEVEL_PRESETS: Dict[int, Tuple[str, int, str]] = {
    1: ("Classic Arena", 65, "Balanced destructible barrels & classic pillars"),
    2: ("Open Battleground", 35, "Open sightlines ideal for kicking bombs"),
    3: ("Dense Labyrinth", 80, "Tight maze packed with hidden power-ups"),
}
