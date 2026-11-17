from typing import Dict, List, Optional, Tuple
import numpy as np
import bomberman_engine as bme

from gui.config import BOARD_WIDTH_TILES, BOARD_HEIGHT_TILES, LEVEL_PRESETS
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
        self._human_count: int = 1
        self._trained_ai_count: int = 0
        self._known_players: Dict[int, PlayerSnapshot] = {}
        self._last_grid_pos: Dict[int, Tuple[int, int]] = {}
        self._move_origin: Dict[int, Tuple[int, int]] = {}
        self._cached_tick: Optional[int] = None
        self._cached_board: List[List[int]] = []
        self._cached_pinfo: Dict[int, bme.PlayerInfo] = {}
        self._cached_binfo: List[bme.BombInfo] = []
        self._cached_flames: List[FlameSnapshot] = []
        self._cached_powerups: List[PowerUpSnapshot] = []
        self._cached_sd_timer: int = 0
        self._cached_sd_active: bool = False
        self._cached_is_game_over: bool = False
        self._cached_winner_id: int = -1

    def invalidate_cache(self) -> None:
        self._cached_tick = None

    def reset_player_registry(
        self,
        game: bme.Game,
        max_players: int = 4,
        human_count: int = 1,
        trained_ai_count: int = 0,
    ) -> None:
        self.invalidate_cache()
        self._human_count = human_count
        self._trained_ai_count = trained_ai_count
        self._known_players.clear()
        self._last_grid_pos.clear()
        self._move_origin.clear()
        for pid in range(1, max_players + 1):
            pinfo = game.getPlayerInfo(pid)
            if pinfo.isAlive:
                self._last_grid_pos[pid] = (pinfo.x, pinfo.y)
                self._move_origin[pid] = (pinfo.x, pinfo.y)
                is_trained = bool(
                    self._human_count < pid <= self._human_count + self._trained_ai_count
                )
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
                    is_bot=bool(pinfo.isBot or pid > self._human_count),
                    is_alive=True,
                    is_moving=False,
                    is_trained_ai=is_trained,
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

    def _refresh_tick_cache(self, game: bme.Game, tick_count: int) -> None:
        self._cached_board = self._extract_board(game)
        self._cached_pinfo = {pid: game.getPlayerInfo(pid) for pid in range(1, 5)}
        for pid, pinfo in self._cached_pinfo.items():
            if not pinfo.isAlive:
                continue
            cur_pos = (pinfo.x, pinfo.y)
            prev_pos = self._last_grid_pos.get(pid, cur_pos)
            if cur_pos != prev_pos:
                self._move_origin[pid] = prev_pos
                self._last_grid_pos[pid] = cur_pos
            elif pinfo.cooldown == 0:
                self._move_origin[pid] = cur_pos
        self._cached_binfo = list(game.getBombs())
        self._cached_flames = [FlameSnapshot(f.x, f.y, f.timer, f.ownerId) for f in game.getFlames()]
        self._cached_powerups = [PowerUpSnapshot(pu.x, pu.y, pu.type) for pu in game.getPowerUps()]
        self._cached_sd_timer = game.getSuddenDeathTimer()
        self._cached_sd_active = game.isSuddenDeathActive()
        self._cached_is_game_over = game.isGameOver()
        self._cached_winner_id = game.getWinnerId()
        self._cached_tick = tick_count

    def build_snapshot(
        self,
        game: bme.Game,
        alpha: float,
        tick_count: int = 0,
        ai_debug: Optional[AIDebugSnapshot] = None,
    ) -> GameSnapshot:
        if self._cached_tick != tick_count:
            self._refresh_tick_cache(game, tick_count)

        players: Dict[int, PlayerSnapshot] = {}
        for pid in range(1, 5):
            pinfo = self._cached_pinfo[pid]
            if pinfo.isAlive:
                max_cd = getattr(pinfo, "moveCooldownMax", max(4, 6 - pinfo.speedLevel))
                max_cd = max(1, int(max_cd))
                render_x, render_y = float(pinfo.x), float(pinfo.y)
                ox, oy = self._move_origin.get(pid, (pinfo.x, pinfo.y))
                is_moving = pinfo.cooldown > 0 and (ox != pinfo.x or oy != pinfo.y)

                if is_moving:
                    progress = (max_cd - pinfo.cooldown + alpha) / max_cd
                    progress = max(0.0, min(progress, 1.0))
                    render_x = ox + (pinfo.x - ox) * progress
                    render_y = oy + (pinfo.y - oy) * progress

                is_trained = bool(
                    self._human_count < pid <= self._human_count + self._trained_ai_count
                )
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
                    is_bot=bool(pinfo.isBot or pid > self._human_count),
                    is_alive=True,
                    is_moving=is_moving,
                    is_trained_ai=is_trained,
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
                    is_trained_ai=prev.is_trained_ai,
                )

        bombs: List[BombSnapshot] = []
        for binfo in self._cached_binfo:
            rx, ry = float(binfo.x), float(binfo.y)
            slide_cd = getattr(binfo, "slideCooldown", 0)
            slide_max = max(1, int(getattr(binfo, "slideCooldownMax", 3)))
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

        return GameSnapshot(
            board=self._cached_board,
            players=players,
            bombs=bombs,
            flames=self._cached_flames,
            powerups=self._cached_powerups,
            sd_timer=self._cached_sd_timer,
            sd_active=self._cached_sd_active,
            is_game_over=self._cached_is_game_over,
            winner_id=self._cached_winner_id,
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
        self._obs_cache: Dict[int, np.ndarray] = {}
        self._tstate_cache: Dict[int, Dict[str, int]] = {}
        self.reset(num_human=1, num_bots=3)

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def _clear_step_caches(self) -> None:
        self._obs_cache.clear()
        self._tstate_cache.clear()
        self._snapshot_builder.invalidate_cache()

    def reset(
        self,
        num_human: int = 1,
        num_bots: int = 3,
        level_id: int = 1,
        trained_ai_bots: int = 0,
    ) -> None:
        if level_id in LEVEL_PRESETS:
            _, self.wall_density, _ = LEVEL_PRESETS[level_id]
        trained_count = max(0, min(num_bots, trained_ai_bots))
        c_human_slots = num_human + trained_count
        c_dumb_bots = max(0, num_bots - trained_count)
        total_players = max(1, c_human_slots + c_dumb_bots)
        level = bme.ClassicLevel(total_players, self.width, self.height, self.wall_density)
        self._game.reset(level, c_human_slots, c_dumb_bots)
        self._tick_count = 0
        self._clear_step_caches()
        self._snapshot_builder.reset_player_registry(
            self._game,
            max_players=total_players,
            human_count=num_human,
            trained_ai_count=trained_count,
        )

    def step_tick(
        self,
        action: PlayerAction,
        p2_action: Optional[PlayerAction] = None,
        extra_actions: Optional[Dict[int, PlayerAction]] = None,
    ) -> None:
        if self._game.isGameOver():
            return
        cmd1 = self._ACTION_TO_CMD.get(action, bme.Command.NONE)
        if (p2_action is not None or extra_actions) and hasattr(self._game, "updateCommands"):
            cmds = []
            if cmd1 != bme.Command.NONE:
                cmds.append(bme.PlayerCommand(1, cmd1))
            if p2_action is not None:
                cmd2 = self._ACTION_TO_CMD.get(p2_action, bme.Command.NONE)
                if cmd2 != bme.Command.NONE:
                    cmds.append(bme.PlayerCommand(2, cmd2))
            if extra_actions:
                for pid, act in extra_actions.items():
                    c = self._ACTION_TO_CMD.get(act, bme.Command.NONE)
                    if c != bme.Command.NONE:
                        cmds.append(bme.PlayerCommand(int(pid), c))
            self._game.updateCommands(cmds)
        else:
            self._game.update(cmd1)
        self._tick_count += 1
        self._clear_step_caches()

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
        if player_id not in self._obs_cache:
            raw_state = self._game.getState(player_id)
            self._obs_cache[player_id] = np.asarray(raw_state, dtype=np.float32).reshape(
                10, self.height, self.width
            )
        return self._obs_cache[player_id]

    def get_player_tactical_state(self, player_id: int = 1) -> Dict[str, int]:
        if player_id not in self._tstate_cache:
            pinfo = self._game.getPlayerInfo(player_id)
            self._tstate_cache[player_id] = {
                "is_alive": int(pinfo.isAlive),
                "x": int(pinfo.x),
                "y": int(pinfo.y),
                "cooldown": int(pinfo.cooldown),
                "move_cooldown_max": int(getattr(pinfo, "moveCooldownMax", 6)),
                "has_ring": int(pinfo.hasRing),
                "has_hammer": int(pinfo.hasHammer),
                "bomb_radius": int(pinfo.bombRadius),
                "avail_bombs": int(pinfo.availBombs),
                "facing_dx": int(pinfo.facingDx),
                "facing_dy": int(pinfo.facingDy),
            }
        return self._tstate_cache[player_id]
