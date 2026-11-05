from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Protocol
import numpy as np


class PlayerAction(IntEnum):
    """Pure Python action enum decoupling input/controllers from C++ bindings."""
    NONE = 0
    UP = 1
    DOWN = 2
    LEFT = 3
    RIGHT = 4
    PLACE_BOMB = 5


@dataclass
class PlayerSnapshot:
    id: int
    grid_x: int
    grid_y: int
    render_x: float
    render_y: float
    facing_dx: int
    facing_dy: int
    lives: int
    max_bombs: int
    avail_bombs: int
    bomb_radius: int
    speed_level: int
    invincibility_timer: int
    has_hammer: bool
    has_ring: bool
    is_bot: bool
    is_alive: bool
    is_moving: bool = False


@dataclass
class BombSnapshot:
    grid_x: int
    grid_y: int
    render_x: float
    render_y: float
    timer: int
    radius: int
    owner_id: int
    is_sliding: bool


@dataclass
class FlameSnapshot:
    grid_x: int
    grid_y: int
    timer: int
    owner_id: int


@dataclass
class PowerUpSnapshot:
    grid_x: int
    grid_y: int
    type_char: str  # 'H', 'R', 'S', 'L', '+'


@dataclass
class AIDebugSnapshot:
    action_probs: Optional[List[float]] = None
    chosen_action: int = 0
    value: float = 0.0
    reach_map: Optional[np.ndarray] = None
    bomb_map: Optional[np.ndarray] = None
    in_danger: bool = False
    shield_intervened: bool = False


@dataclass
class GameSnapshot:
    board: List[List[int]]  # 0 = Empty, 1 = Solid, 2 = Breakable
    players: Dict[int, PlayerSnapshot]
    bombs: List[BombSnapshot]
    flames: List[FlameSnapshot]
    powerups: List[PowerUpSnapshot]
    sd_timer: int
    sd_active: bool
    is_game_over: bool = False
    winner_id: int = -1
    tick_count: int = 0
    ai_debug: Optional[AIDebugSnapshot] = None


class IGameSession(Protocol):
    """Abstract boundary interface between the GUI presentation layer and the game engine."""

    def reset(self, num_human: int = 1, num_bots: int = 3) -> None:
        ...

    def step_tick(self, action: PlayerAction) -> None:
        ...

    def get_snapshot(self, alpha: float, ai_debug: Optional[AIDebugSnapshot] = None) -> GameSnapshot:
        ...

    def is_game_over(self) -> bool:
        ...

    def get_winner_id(self) -> int:
        ...

    def get_rl_base_observation(self, player_id: int = 1) -> np.ndarray:
        ...

    def get_player_tactical_state(self, player_id: int = 1) -> Dict[str, int]:
        ...
