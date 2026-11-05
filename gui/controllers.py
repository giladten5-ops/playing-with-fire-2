from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Tuple
import numpy as np
import pygame

from gui.config import BOARD_HEIGHT_TILES, BOARD_WIDTH_TILES, DEFAULT_MODEL_PATHS
from gui.state_snapshot import AIDebugSnapshot, IGameSession, PlayerAction


class IPlayerController(Protocol):
    """Interface for any player input source (Human Keyboard, PPO Agent, Heuristic Bot)."""

    def get_action(self, session: Optional[IGameSession] = None) -> PlayerAction:
        ...

    def get_debug_snapshot(self) -> Optional[AIDebugSnapshot]:
        ...


class KeyboardController:
    """Reads human keyboard state and maps it to pure Python PlayerAction values."""

    def __init__(self) -> None:
        pass

    def get_action(self, session: Optional[IGameSession] = None) -> PlayerAction:
        keys = pygame.key.get_pressed()

        if keys[pygame.K_SPACE]:
            return PlayerAction.PLACE_BOMB

        if keys[pygame.K_UP] or keys[pygame.K_w]:
            return PlayerAction.UP
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            return PlayerAction.DOWN
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            return PlayerAction.LEFT
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            return PlayerAction.RIGHT

        return PlayerAction.NONE

    def get_debug_snapshot(self) -> Optional[AIDebugSnapshot]:
        return None


class PPOAgentController:
    """
    AI Controller that wraps the trained PPO Grandmaster model (or BFS tactical fallback)
    and produces real-time AIDebugSnapshot heatmaps for GUI visualization.
    """

    DIRS: Dict[int, Tuple[int, int]] = {
        1: (0, -1),
        2: (0, 1),
        3: (-1, 0),
        4: (1, 0),
    }

    def __init__(
        self,
        player_id: int = 1,
        width: int = BOARD_WIDTH_TILES,
        height: int = BOARD_HEIGHT_TILES,
        tactical_shield: bool = True,
    ) -> None:
        self.player_id = player_id
        self.width = width
        self.height = height
        self.tactical_shield = tactical_shield
        self.model = None
        self.expected_channels = 12
        self._last_debug: Optional[AIDebugSnapshot] = None
        self._load_model_if_available()

    def _load_model_if_available(self) -> None:
        try:
            from stable_baselines3 import PPO
            from bomberman_env import BombermanCNN

            for path in DEFAULT_MODEL_PATHS:
                if Path(path).exists():
                    self.model = PPO.load(str(path), custom_objects={"BombermanCNN": BombermanCNN})
                    obs_shape = getattr(self.model.observation_space, "shape", None)
                    if obs_shape and len(obs_shape) == 3:
                        self.expected_channels = int(obs_shape[0])
                    break
        except Exception:
            self.model = None

    def _compute_bfs_features(
        self, base_obs: np.ndarray, tstate: Dict[str, int]
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, object]]:
        h, w = self.height, self.width
        reach_map = np.zeros((h, w), dtype=np.float32)
        bomb_map = np.zeros((h, w), dtype=np.float32)

        if not tstate.get("is_alive", 0):
            return reach_map, bomb_map, {
                "safe_escape_from_here": False,
                "bomb_targets_here": 0,
                "in_danger": False,
                "escape_action": 0,
                "valid_moves": [0],
                "can_place_bomb": False,
                "can_push_bomb_now": False,
            }

        px, py = int(tstate["x"]), int(tstate["y"])
        solid = base_obs[0] > 0.0
        breakable = base_obs[1] > 0.0
        bombs = base_obs[2] > 0.0
        danger = base_obs[3]
        flames = base_obs[4] > 0.0
        enemies = base_obs[7] > 0.0

        has_ring = bool(tstate["has_ring"])
        has_hammer = bool(tstate["has_hammer"])
        bomb_radius = int(tstate["bomb_radius"])
        avail_bombs = int(tstate["avail_bombs"])
        facing_dx, facing_dy = int(tstate["facing_dx"]), int(tstate["facing_dy"])

        in_danger = bool(danger[py, px] > 0.0)
        passable = ~(solid | breakable | flames) if has_ring else ~(solid | breakable | bombs | flames)

        dist = np.full((h, w), -1, dtype=np.int32)
        first_action = np.zeros((h, w), dtype=np.int32)
        q = deque([(px, py)])
        dist[py, px] = 0
        reach_map[py, px] = 1.0 if danger[py, px] == 0.0 else 0.2

        valid_moves = [0]
        escape_action = 0
        min_safe_dist = 999

        while q:
            cx, cy = q.popleft()
            d = int(dist[cy, cx])
            if d >= 14:
                continue
            for act_id, (dx, dy) in self.DIRS.items():
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and dist[ny, nx] == -1 and passable[ny, nx]:
                    if not in_danger and danger[ny, nx] > 0.0:
                        continue
                    if in_danger and danger[ny, nx] >= 0.88:
                        continue
                    dist[ny, nx] = d + 1
                    fa = act_id if d == 0 else int(first_action[cy, cx])
                    first_action[ny, nx] = fa
                    if d == 0:
                        valid_moves.append(act_id)
                    if danger[ny, nx] == 0.0:
                        reach_map[ny, nx] = max(0.1, 1.0 - (d + 1) / 15.0)
                        if d + 1 < min_safe_dist:
                            min_safe_dist = d + 1
                            escape_action = fa
                    else:
                        reach_map[ny, nx] = 0.15
                    q.append((nx, ny))

        def can_push_bomb_in_dir(dx: int, dy: int) -> bool:
            if not has_hammer or (dx == 0 and dy == 0) or bombs[py, px]:
                return False
            bx, by = px + dx, py + dy
            dest_x, dest_y = bx + dx, by + dy
            if not (0 <= bx < w and 0 <= by < h and 0 <= dest_x < w and 0 <= dest_y < h):
                return False
            if not bombs[by, bx]:
                return False
            if solid[dest_y, dest_x] or breakable[dest_y, dest_x] or bombs[dest_y, dest_x] or flames[dest_y, dest_x] or enemies[dest_y, dest_x]:
                return False
            return True

        can_push_bomb_now = can_push_bomb_in_dir(facing_dx, facing_dy)

        if has_hammer and not bombs[py, px]:
            for act_id, (dx, dy) in self.DIRS.items():
                if can_push_bomb_in_dir(dx, dy) and (dx != facing_dx or dy != facing_dy):
                    if act_id not in valid_moves:
                        valid_moves.append(act_id)

        def compute_blast_zone(bx: int, by: int, radius: int):
            blast = {(bx, by)}
            for _, (dx, dy) in self.DIRS.items():
                for r in range(1, radius + 1):
                    nx, ny = bx + dx * r, by + dy * r
                    if not (0 <= nx < w and 0 <= ny < h) or solid[ny, nx]:
                        break
                    blast.add((nx, ny))
                    if breakable[ny, nx] or bombs[ny, nx]:
                        break
            return blast

        def has_escape_if_bomb_at(bx: int, by: int, radius: int) -> bool:
            blast_tiles = compute_blast_zone(bx, by, radius)
            max_search_steps = max(6, radius + 3)
            b_dist = np.full((h, w), -1, dtype=np.int32)
            bq = deque([(bx, by)])
            b_dist[by, bx] = 0
            while bq:
                cx, cy = bq.popleft()
                cd = int(b_dist[cy, cx])
                if cd >= max_search_steps:
                    continue
                for _, (dx, dy) in self.DIRS.items():
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < w and 0 <= ny < h and b_dist[ny, nx] == -1 and passable[ny, nx] and danger[ny, nx] < 0.7:
                        b_dist[ny, nx] = cd + 1
                        if (nx, ny) not in blast_tiles and danger[ny, nx] == 0.0:
                            return True
                        bq.append((nx, ny))
            return False

        def count_targets_at(bx: int, by: int, radius: int) -> int:
            t = 0
            for _, (dx, dy) in self.DIRS.items():
                for r in range(1, radius + 1):
                    nx, ny = bx + dx * r, by + dy * r
                    if not (0 <= nx < w and 0 <= ny < h) or solid[ny, nx]:
                        break
                    if enemies[ny, nx]:
                        t += 3
                    if breakable[ny, nx]:
                        t += 1
                        break
            return t

        can_place_bomb = (avail_bombs > 0) and (not bombs[py, px])
        safe_escape_here = can_place_bomb and has_escape_if_bomb_at(px, py, bomb_radius)
        targets_here = count_targets_at(px, py, bomb_radius) if safe_escape_here else 0
        if safe_escape_here and targets_here > 0:
            bomb_map[py, px] = min(1.0, targets_here / 4.0)
        elif can_push_bomb_now:
            bomb_map[py, px] = 1.0

        for _, (dx, dy) in self.DIRS.items():
            nx, ny = px + dx, py + dy
            if 0 <= nx < w and 0 <= ny < h and passable[ny, nx] and danger[ny, nx] == 0.0:
                if has_escape_if_bomb_at(nx, ny, bomb_radius):
                    t = count_targets_at(nx, ny, bomb_radius)
                    if t > 0:
                        bomb_map[ny, nx] = min(1.0, t / 4.0)

        return reach_map, bomb_map, {
            "safe_escape_from_here": safe_escape_here,
            "bomb_targets_here": targets_here,
            "in_danger": in_danger,
            "escape_action": escape_action,
            "valid_moves": valid_moves,
            "can_place_bomb": can_place_bomb,
            "can_push_bomb_now": can_push_bomb_now,
        }

    def _format_obs(self, base_obs: np.ndarray, reach_map: np.ndarray, bomb_map: np.ndarray) -> np.ndarray:
        if self.expected_channels == 10:
            return np.concatenate([base_obs[:8], reach_map[None, ...], bomb_map[None, ...]], axis=0)
        if self.expected_channels == 8:
            return base_obs[:8]
        return np.concatenate([base_obs, reach_map[None, ...], bomb_map[None, ...]], axis=0)

    def compute_debug_only(self, session: IGameSession) -> Optional[AIDebugSnapshot]:
        tstate = session.get_player_tactical_state(self.player_id)
        base_obs = session.get_rl_base_observation(self.player_id)
        reach_map, bomb_map, analysis = self._compute_bfs_features(base_obs, tstate)
        self._last_debug = AIDebugSnapshot(
            action_probs=self._last_debug.action_probs if self._last_debug else None,
            chosen_action=self._last_debug.chosen_action if self._last_debug else 0,
            value=self._last_debug.value if self._last_debug else 0.0,
            reach_map=reach_map,
            bomb_map=bomb_map,
            in_danger=bool(analysis["in_danger"]),
            shield_intervened=False,
        )
        return self._last_debug

    def get_action(self, session: Optional[IGameSession] = None) -> PlayerAction:
        if session is None:
            return PlayerAction.NONE

        tstate = session.get_player_tactical_state(self.player_id)
        if not tstate.get("is_alive", 0):
            return PlayerAction.NONE

        base_obs = session.get_rl_base_observation(self.player_id)
        reach_map, bomb_map, analysis = self._compute_bfs_features(base_obs, tstate)
        obs = self._format_obs(base_obs, reach_map, bomb_map)

        raw_action = 0
        action_probs: Optional[List[float]] = None
        value_est = 0.0

        if self.model is not None:
            try:
                import torch as th
                obs_tensor, _ = self.model.policy.obs_to_tensor(obs)
                with th.no_grad():
                    dist = self.model.policy.get_distribution(obs_tensor)
                    probs = dist.distribution.probs.cpu().numpy()[0]
                    action_probs = [float(p) for p in probs]
                    val = self.model.policy.predict_values(obs_tensor).cpu().numpy()[0]
                    value_est = float(val.item() if hasattr(val, "item") else val[0])
                raw_action = int(np.argmax(probs))
            except Exception:
                pred, _ = self.model.predict(obs, deterministic=True)
                raw_action = int(pred.item() if hasattr(pred, "item") else pred)
        else:
            # Tactical BFS heuristic fallback when no PPO model file is present
            if analysis["in_danger"] and int(analysis["escape_action"]) != 0:
                raw_action = int(analysis["escape_action"])
            elif analysis["safe_escape_from_here"] and int(analysis["bomb_targets_here"]) > 0:
                raw_action = int(PlayerAction.PLACE_BOMB)
            else:
                valid_moves: List[int] = list(analysis["valid_moves"])  # type: ignore
                non_zero = [m for m in valid_moves if m != 0]
                raw_action = int(np.random.choice(non_zero)) if non_zero else 0

        exec_action = raw_action
        shield_intervened = False
        valid_moves_list: List[int] = list(analysis["valid_moves"])  # type: ignore

        if self.tactical_shield:
            if analysis["in_danger"] and int(analysis["escape_action"]) != 0 and (
                exec_action == 0
                or (exec_action == 5 and not analysis["can_push_bomb_now"])
                or exec_action not in valid_moves_list
            ):
                exec_action = int(analysis["escape_action"])
                shield_intervened = True
            elif exec_action == 5 and not analysis["can_push_bomb_now"] and (
                not analysis["can_place_bomb"]
                or not analysis["safe_escape_from_here"]
                or int(analysis["bomb_targets_here"]) == 0
            ):
                nz = [m for m in valid_moves_list if m != 0]
                exec_action = int(np.random.choice(nz)) if nz else 0
                shield_intervened = True
            elif exec_action in (1, 2, 3, 4) and exec_action not in valid_moves_list:
                nz = [m for m in valid_moves_list if m != 0]
                exec_action = int(np.random.choice(nz)) if nz else 0
                shield_intervened = True

        self._last_debug = AIDebugSnapshot(
            action_probs=action_probs,
            chosen_action=exec_action,
            value=value_est,
            reach_map=reach_map,
            bomb_map=bomb_map,
            in_danger=bool(analysis["in_danger"]),
            shield_intervened=shield_intervened,
        )
        return PlayerAction(exec_action)

    def get_debug_snapshot(self) -> Optional[AIDebugSnapshot]:
        return self._last_debug
