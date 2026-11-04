from collections import deque
import gymnasium as gym
import numpy as np
import torch as th
import torch.nn as nn
from gymnasium import spaces
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
import bomberman_engine as bme


class BombermanCNN(BaseFeaturesExtractor):
    def __init__(self, observation_space: spaces.Box, features_dim: int = 256):
        super().__init__(observation_space, features_dim)
        n_input_channels = observation_space.shape[0]
        self.cnn = nn.Sequential(
            nn.Conv2d(n_input_channels, 32, kernel_size=3, stride=1, padding=1), nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1), nn.ReLU(),
            nn.Conv2d(64, 64, kernel_size=3, stride=1, padding=0), nn.ReLU(),
            nn.Flatten(),
        )
        with th.no_grad():
            sample_tensor = th.as_tensor(observation_space.sample()[None]).float()
            n_flatten = self.cnn(sample_tensor).shape[1]
        self.linear = nn.Sequential(nn.Linear(n_flatten, features_dim), nn.ReLU())

    def forward(self, observations: th.Tensor) -> th.Tensor:
        return self.linear(self.cnn(observations))


class BombermanEnv(gym.Env):
    DIRS = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0)}

    def __init__(
        self,
        board_width=13,
        board_height=13,
        max_steps=900,
        frame_skip=4,
        num_bots=3,
        wall_density=65,
        tactical_shield=True,
        use_10_channels=False,
    ):
        super().__init__()
        self.width = board_width
        self.height = board_height
        self.num_bots = num_bots
        self.wall_density = wall_density
        self.player_id = 1
        self.max_steps = max_steps
        self.frame_skip = frame_skip
        self.tactical_shield = tactical_shield
        self.use_10_channels = use_10_channels

        self.game = bme.Game(self.width, self.height)
        self.action_space = spaces.Discrete(6)
        self.n_channels = 10 if self.use_10_channels else 12
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(self.n_channels, self.height, self.width), dtype=np.float32
        )
        self.action_mapping = {
            0: bme.Command.NONE,
            1: bme.Command.UP,
            2: bme.Command.DOWN,
            3: bme.Command.LEFT,
            4: bme.Command.RIGHT,
            5: bme.Command.PLACE_BOMB,
        }
        self.ep_stats = {}
        self.current_step = 0
        self.idle_streak = 0
        self.visited_tiles = set()

    def _compute_bfs_features(self, base_obs):
        h, w = self.height, self.width
        reach_map = np.zeros((h, w), dtype=np.float32)
        bomb_map = np.zeros((h, w), dtype=np.float32)

        pinfo = self.game.getPlayerInfo(self.player_id)
        if not pinfo.isAlive:
            return reach_map, bomb_map, 0.0, {
                "safe_escape_from_here": False,
                "bomb_targets_here": 0,
                "in_danger": False,
                "escape_action": 0,
                "valid_moves": [0],
                "can_place_bomb": False,
                "can_push_bomb_now": False,
            }

        px, py = int(pinfo.x), int(pinfo.y)
        solid = base_obs[0] > 0.0
        breakable = base_obs[1] > 0.0
        bombs = base_obs[2] > 0.0
        danger = base_obs[3]
        flames = base_obs[4] > 0.0
        powerups = base_obs[5] > 0.0
        enemies = base_obs[7] > 0.0

        has_ring = bool(pinfo.hasRing)
        has_hammer = bool(pinfo.hasHammer)
        bomb_radius = int(pinfo.bombRadius)
        avail_bombs = int(pinfo.availBombs)
        facing_dx, facing_dy = int(pinfo.facingDx), int(pinfo.facingDy)

        in_danger = bool(danger[py, px] > 0.0)

        # RING MECHANIC: Only Ring allows walking through bombs!
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
            d = dist[cy, cx]
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
                    fa = act_id if d == 0 else first_action[cy, cx]
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

        # HAMMER MECHANIC: Check if an adjacent bomb can be pushed into a free tile
        def can_push_bomb_in_dir(dx, dy):
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

        def compute_blast_zone(bx, by, radius):
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

        def has_escape_if_bomb_at(bx, by, radius):
            blast_tiles = compute_blast_zone(bx, by, radius)
            max_search_steps = max(6, radius + 3)
            b_dist = np.full((h, w), -1, dtype=np.int32)
            bq = deque([(bx, by)])
            b_dist[by, bx] = 0
            while bq:
                cx, cy = bq.popleft()
                cd = b_dist[cy, cx]
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

        def count_targets_at(bx, by, radius):
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

        for act_id, (dx, dy) in self.DIRS.items():
            nx, ny = px + dx, py + dy
            if 0 <= nx < w and 0 <= ny < h and passable[ny, nx] and danger[ny, nx] == 0.0:
                if has_escape_if_bomb_at(nx, ny, bomb_radius):
                    t = count_targets_at(nx, ny, bomb_radius)
                    if t > 0:
                        bomb_map[ny, nx] = min(1.0, t / 4.0)

        safe_reachable_count = int(np.sum((dist >= 0) & (danger == 0.0)))
        phi_space = min(safe_reachable_count, 35) * 0.12
        phi_safety = -4.0 * float(danger[py, px]) if in_danger else 0.0
        phi_hunt = 0.0
        if not in_danger:
            pu_ys, pu_xs = np.where((powerups) & (dist >= 0))
            if len(pu_xs) > 0:
                phi_hunt += (15.0 - min(int(np.min(dist[pu_ys, pu_xs])), 15)) * 0.15
            en_ys, en_xs = np.where(enemies)
            if len(en_xs) > 0:
                phi_hunt += (24.0 - min(int(np.min(np.abs(en_xs - px) + np.abs(en_ys - py))), 24)) * 0.06

        analysis = {
            "pos": (px, py),
            "safe_escape_from_here": safe_escape_here,
            "bomb_targets_here": targets_here,
            "in_danger": in_danger,
            "escape_action": escape_action,
            "valid_moves": valid_moves,
            "can_place_bomb": can_place_bomb,
            "can_push_bomb_now": can_push_bomb_now,
        }
        return reach_map, bomb_map, phi_space + phi_safety + phi_hunt, analysis

    def _format_obs(self, base_obs, reach_map, bomb_map):
        if self.use_10_channels:
            return np.concatenate([base_obs[:8], reach_map[None, ...], bomb_map[None, ...]], axis=0)
        return np.concatenate([base_obs, reach_map[None, ...], bomb_map[None, ...]], axis=0)

    def step(self, action):
        self.current_step += 1
        raw_action = int(action)

        state = self.game.getState(self.player_id)
        base_obs = np.array(state, dtype=np.float32).reshape(10, self.height, self.width)
        _, _, prev_potential, analysis = self._compute_bfs_features(base_obs)

        exec_action = raw_action
        if self.tactical_shield:
            if analysis["in_danger"] and analysis["escape_action"] != 0 and (
                exec_action == 0 or (exec_action == 5 and not analysis["can_push_bomb_now"]) or exec_action not in analysis["valid_moves"]
            ):
                exec_action = int(analysis["escape_action"])
            elif exec_action == 5 and not analysis["can_push_bomb_now"] and (
                not analysis["can_place_bomb"] or not analysis["safe_escape_from_here"] or analysis["bomb_targets_here"] == 0
            ):
                nz = [m for m in analysis["valid_moves"] if m != 0]
                exec_action = int(np.random.choice(nz)) if nz else 0
            elif exec_action in (1, 2, 3, 4) and exec_action not in analysis["valid_moves"]:
                nz = [m for m in analysis["valid_moves"] if m != 0]
                exec_action = int(np.random.choice(nz)) if nz else 0

        cpp_command = self.action_mapping[exec_action]
        total_reward, moved_any, bomb_placed_any, bomb_pushed_any, won, died = 0.0, False, False, False, False, False

        for tick_idx in range(self.frame_skip):
            cmd = cpp_command if tick_idx == 0 else bme.Command.NONE
            res = self.game.step(self.player_id, cmd)
            total_reward += float(res.reward)
            moved_any |= res.moved
            bomb_placed_any |= res.bombPlaced
            bomb_pushed_any |= res.bombPushed
            won |= res.won
            died |= res.died
            self.ep_stats["walls_destroyed"] += res.wallsDestroyed
            self.ep_stats["kills"] += res.enemiesKilled
            self.ep_stats["powerups"] += res.powerUpsCollected
            self.ep_stats["lives_lost"] += res.livesLost
            if res.isDone:
                break

        new_state = self.game.getState(self.player_id)
        new_base_obs = np.array(new_state, dtype=np.float32).reshape(10, self.height, self.width)
        reach_map, bomb_map, new_potential, post_analysis = self._compute_bfs_features(new_base_obs)
        obs = self._format_obs(new_base_obs, reach_map, bomb_map)

        self.ep_stats["steps"] += 1
        if raw_action == 0:
            self.ep_stats["idle_actions"] += 1
        if raw_action in (1, 2, 3, 4) and not moved_any:
            self.ep_stats["wall_bumps"] += 1
        if moved_any:
            self.ep_stats["moves"] += 1
            if post_analysis.get("pos"):
                self.visited_tiles.add(post_analysis["pos"])
        if bomb_placed_any:
            self.ep_stats["bombs_placed"] += 1
            if analysis["safe_escape_from_here"] and analysis["bomb_targets_here"] > 0:
                self.ep_stats["tactical_bombs"] += 1
                total_reward += 1.5
            else:
                total_reward -= 0.5
        if bomb_pushed_any:
            self.ep_stats["bombs_pushed"] += 1
            total_reward += 1.5
        if analysis["in_danger"] and not post_analysis["in_danger"] and not died:
            self.ep_stats["successful_dodges"] += 1

        terminated = won or died or res.isDone
        if not terminated:
            total_reward += float(np.clip(0.99 * new_potential - prev_potential, -3.0, 3.0))
            if raw_action in (1, 2, 3, 4) and raw_action not in analysis["valid_moves"]:
                total_reward -= 0.25
            if not moved_any and not bomb_placed_any and not bomb_pushed_any and not analysis["in_danger"]:
                self.idle_streak += 1
                if self.idle_streak > 2:
                    total_reward -= 0.2
            else:
                self.idle_streak = 0

        truncated = bool(self.current_step >= self.max_steps and not terminated)
        info = {}
        if terminated or truncated:
            self.ep_stats["unique_tiles"] = len(self.visited_tiles)
            self.ep_stats["won"] = 1.0 if won else 0.0
            self.ep_stats["survived"] = 0.0 if died else 1.0
            info["is_success"] = bool(won)
            info["win"] = 1.0 if won else 0.0
            info["episode_metrics"] = dict(self.ep_stats)
        return obs, float(total_reward), terminated, truncated, info

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            bme.seed_rng(int(seed) & 0xFFFFFFFF)
        self.current_step = 0
        self.idle_streak = 0
        self.visited_tiles = set()
        self.ep_stats = {
            "steps": 0,
            "moves": 0,
            "idle_actions": 0,
            "wall_bumps": 0,
            "bombs_placed": 0,
            "bombs_pushed": 0,
            "tactical_bombs": 0,
            "walls_destroyed": 0,
            "kills": 0,
            "powerups": 0,
            "lives_lost": 0,
            "successful_dodges": 0,
            "unique_tiles": 1,
            "won": 0.0,
            "survived": 1.0,
        }
        self.game.reset(bme.ClassicLevel(1 + self.num_bots, self.width, self.height, self.wall_density), 1, self.num_bots)

        state = self.game.getState(self.player_id)
        base_obs = np.array(state, dtype=np.float32).reshape(10, self.height, self.width)
        reach_map, bomb_map, _, analysis = self._compute_bfs_features(base_obs)
        if analysis.get("pos"):
            self.visited_tiles.add(analysis["pos"])
        return self._format_obs(base_obs, reach_map, bomb_map), {}
