from typing import Dict, List, Optional
import numpy as np
import bomberman_engine as bme

from gui.config import BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES
from gui.state_snapshot import (
    AIDebugSnapshot,
    BombSnapshot,
    FlameSnapshot,
    GameSnapshot,
    IGameSession,
    PlayerAction,
    PlayerSnapshot,
    PowerUpSnapshot,
)


class SnapshotBuilder:
    """
    Translates raw C++ engine state into pure Python GameSnapshot objects
    with sub-tick linear interpolation for smooth 60 FPS rendering.
    """

    def __init__(self, width: int = BOARD_WIDTH_TILES, height: int = BOARD_HEIGHT_TILES):
        self.width = width
        self.height = height
        self._known_players: Dict[int, PlayerSnapshot] = {}

    def reset_player_registry(self, game: bme.Game, max_players: int = 4) -> None:
        self._known_players.clear()
        for pid in range(1, max_players + 1):
            pinfo = game.getPlayerInfo(pid)
            if pinfo.isAlive:
                self._known_players[pid] = PlayerSnapshot(
                    id=pid,
                    grid_x=pinfo.x,
                    grid_y=pinfo.y,
                    render_x=float(pinfo.x),
                    render_y=float(pinfo.y),
                    facing_dx=pinfo.facingDx,
                    facing_dy=pinfo.facingDy,
                    lives=pinfo.lives,
                    max_bombs=pinfo.maxBombs,
                    avail_bombs=pinfo.availBombs,
                    bomb_radius=pinfo.bombRadius,
                    speed_level=pinfo.speedLevel,
                    invincibility_timer=pinfo.invincibilityTimer,
                    has_hammer=pinfo.hasHammer,
                    has_ring=pinfo.hasRing,
                    is_bot=pinfo.isBot,
                    is_alive=True,
                    is_moving=False,
                )

    def _extract_board(self, game: bme.Game) -> List[List[int]]:
        if hasattr(game, "getBoardGrid"):
            return game.getBoardGrid()

        # Safe fallback if an older compiled .so is loaded
        raw_state = game.getState(1)
        state_np = np.array(raw_state, dtype=np.float32).reshape(-1, self.height, self.width)
        board = [[0 for _ in range(self.width)] for _ in range(self.height)]
        for y in range(self.height):
            for x in range(self.width):
                if state_np[0, y, x] > 0:
                    board[y][x] = 1
                elif state_np[1, y, x] > 0:
                    board[y][x] = 2
        return board

    def build_snapshot(
        self,
        game: bme.Game,
        alpha: float,
        tick_count: int = 0,
        ai_debug: Optional[AIDebugSnapshot] = None,
    ) -> GameSnapshot:
        board = self._extract_board(game)

        players: Dict[int, PlayerSnapshot] = {}
        for pid in range(1, 5):
            pinfo = game.getPlayerInfo(pid)
            if pinfo.isAlive:
                max_cd = getattr(pinfo, "moveCooldownMax", max(1, 4 - (pinfo.speedLevel * 2)))
                max_cd = max(1, int(max_cd))
                render_x, render_y = float(pinfo.x), float(pinfo.y)
                is_moving = pinfo.cooldown > 0

                if is_moving:
                    progress = (max_cd - pinfo.cooldown + alpha) / max_cd
                    progress = max(0.0, min(progress, 1.0))
                    render_x = pinfo.x - pinfo.facingDx * (1.0 - progress)
                    render_y = pinfo.y - pinfo.facingDy * (1.0 - progress)

                snap = PlayerSnapshot(
                    id=pinfo.id,
                    grid_x=pinfo.x,
                    grid_y=pinfo.y,
                    render_x=render_x,
                    render_y=render_y,
                    facing_dx=pinfo.facingDx,
                    facing_dy=pinfo.facingDy,
                    lives=pinfo.lives,
                    max_bombs=pinfo.maxBombs,
                    avail_bombs=pinfo.availBombs,
                    bomb_radius=pinfo.bombRadius,
                    speed_level=pinfo.speedLevel,
                    invincibility_timer=pinfo.invincibilityTimer,
                    has_hammer=pinfo.hasHammer,
                    has_ring=pinfo.hasRing,
                    is_bot=pinfo.isBot,
                    is_alive=True,
                    is_moving=is_moving,
                )
                self._known_players[pid] = snap
                players[pid] = snap
            elif pid in self._known_players:
                prev = self._known_players[pid]
                players[pid] = PlayerSnapshot(
                    id=pid,
                    grid_x=prev.grid_x,
                    grid_y=prev.grid_y,
                    render_x=float(prev.grid_x),
                    render_y=float(prev.grid_y),
                    facing_dx=prev.facing_dx,
                    facing_dy=prev.facing_dy,
                    lives=0,
                    max_bombs=prev.max_bombs,
                    avail_bombs=0,
                    bomb_radius=prev.bomb_radius,
                    speed_level=prev.speed_level,
                    invincibility_timer=0,
                    has_hammer=prev.has_hammer,
                    has_ring=prev.has_ring,
                    is_bot=prev.is_bot,
                    is_alive=False,
                    is_moving=False,
                )

        bombs: List[BombSnapshot] = []
        for binfo in game.getBombs():
            rx, ry = float(binfo.x), float(binfo.y)
            slide_cd = getattr(binfo, "slideCooldown", 0)
            slide_max = max(1, int(getattr(binfo, "slideCooldownMax", 2)))
            if binfo.isSliding and slide_cd > 0:
                b_prog = (slide_max - slide_cd + alpha) / slide_max
                b_prog = max(0.0, min(b_prog, 1.0))
                rx = binfo.x - binfo.slideDx * (1.0 - b_prog)
                ry = binfo.y - binfo.slideDy * (1.0 - b_prog)

            bombs.append(
                BombSnapshot(
                    grid_x=binfo.x,
                    grid_y=binfo.y,
                    render_x=rx,
                    render_y=ry,
                    timer=binfo.timer,
                    radius=binfo.radius,
                    owner_id=binfo.ownerId,
                    is_sliding=binfo.isSliding,
                )
            )

        flames = [FlameSnapshot(f.x, f.y, f.timer, f.ownerId) for f in game.getFlames()]
        powerups = [PowerUpSnapshot(pu.x, pu.y, pu.type) for pu in game.getPowerUps()]

        return GameSnapshot(
            board=board,
            players=players,
            bombs=bombs,
            flames=flames,
            powerups=powerups,
            sd_timer=game.getSuddenDeathTimer(),
            sd_active=game.isSuddenDeathActive(),
            is_game_over=game.isGameOver(),
            winner_id=game.getWinnerId(),
            tick_count=tick_count,
            ai_debug=ai_debug,
        )


class CppGameSession(IGameSession):
    """
    Concrete adapter wrapping bomberman_engine.Game.
    Isolates all Pybind11 types inside this module.
    """

    _ACTION_TO_CMD = {
        PlayerAction.NONE: bme.Command.NONE,
        PlayerAction.UP: bme.Command.UP,
        PlayerAction.DOWN: bme.Command.DOWN,
        PlayerAction.LEFT: bme.Command.LEFT,
        PlayerAction.RIGHT: bme.Command.RIGHT,
        PlayerAction.PLACE_BOMB: bme.Command.PLACE_BOMB,
    }

    def __init__(
        self,
        width: int = BOARD_WIDTH_TILES,
        height: int = BOARD_HEIGHT_TILES,
        wall_density: int = 65,
    ):
        self.width = width
        self.height = height
        self.wall_density = wall_density
        self._game = bme.Game(width, height)
        self._snapshot_builder = SnapshotBuilder(width, height)
        self._tick_count = 0
        self.reset(num_human=1, num_bots=3)

    def reset(self, num_human: int = 1, num_bots: int = 3) -> None:
        total_players = max(1, num_human + num_bots)
        level = bme.ClassicLevel(total_players, self.width, self.height, self.wall_density)
        self._game.reset(level, num_human, num_bots)
        self._tick_count = 0
        self._snapshot_builder.reset_player_registry(self._game, max_players=total_players)

    def step_tick(self, action: PlayerAction) -> None:
        if self._game.isGameOver():
            return
        cmd = self._ACTION_TO_CMD.get(action, bme.Command.NONE)
        self._game.update(cmd)
        self._tick_count += 1

    def get_snapshot(self, alpha: float, ai_debug: Optional[AIDebugSnapshot] = None) -> GameSnapshot:
        return self._snapshot_builder.build_snapshot(
            self._game,
            alpha=alpha,
            tick_count=self._tick_count,
            ai_debug=ai_debug,
        )

    def is_game_over(self) -> bool:
        return bool(self._game.isGameOver())

    def get_winner_id(self) -> int:
        return int(self._game.getWinnerId())

    def get_rl_base_observation(self, player_id: int = 1) -> np.ndarray:
        raw_state = self._game.getState(player_id)
        return np.array(raw_state, dtype=np.float32).reshape(10, self.height, self.width)

    def get_player_tactical_state(self, player_id: int = 1) -> Dict[str, int]:
        pinfo = self._game.getPlayerInfo(player_id)
        return {
            "is_alive": int(pinfo.isAlive),
            "x": int(pinfo.x),
            "y": int(pinfo.y),
            "has_ring": int(pinfo.hasRing),
            "has_hammer": int(pinfo.hasHammer),
            "bomb_radius": int(pinfo.bombRadius),
            "avail_bombs": int(pinfo.availBombs),
            "facing_dx": int(pinfo.facingDx),
            "facing_dy": int(pinfo.facingDy),
        }
