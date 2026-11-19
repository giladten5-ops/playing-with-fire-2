import os
from typing import Any, Dict, List, Optional, Tuple
import gymnasium as gym
import numpy as np
import torch as th
import torch.nn as nn
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
import bomberman_engine as bme
from rl_utils import (
    DIRS,
    apply_tactical_shield,
    choose_bfs_fallback_action,
    compute_action_mask,
    compute_bfs_features,
    format_obs,
)

# Process-global singleton cache for frozen Self-Play PPO opponent models (saves RAM across DummyVecEnv)
_SHARED_OPPONENT_MODELS: Dict[str, Tuple[float, Any, int]] = {}


def _get_shared_opponent_model(
    model_path: Optional[str],
    expected_height: int = 13,
    expected_width: int = 15,
) -> Tuple[Optional[Any], int]:
    """Loads and caches a frozen PPO or MaskablePPO checkpoint once per process, reloading only if file mtime changes."""
    if not model_path or not os.path.exists(model_path):
        return None, 19
    try:
        mtime = os.path.getmtime(model_path)
        cache_key = f"{model_path}:{expected_height}x{expected_width}"
        cached = _SHARED_OPPONENT_MODELS.get(cache_key)
        if cached is not None and cached[0] == mtime:
            return cached[1], cached[2]
        try:
            from sb3_contrib import MaskablePPO
            model = MaskablePPO.load(
                model_path,
                device="cpu",
                custom_objects={"BombermanCNN": BombermanCNN},
            )
        except Exception:
            model = PPO.load(
                model_path,
                device="cpu",
                custom_objects={"BombermanCNN": BombermanCNN},
            )
        model.policy.set_training_mode(False)
        obs_shape = getattr(model.observation_space, "shape", (19, 13, 15))
        if obs_shape and len(obs_shape) == 3:
            if int(obs_shape[1]) != int(expected_height) or int(obs_shape[2]) != int(expected_width):
                _SHARED_OPPONENT_MODELS[cache_key] = (mtime, None, 19)
                return None, 19
        expected_channels = int(obs_shape[0]) if obs_shape else 19
        _SHARED_OPPONENT_MODELS[cache_key] = (mtime, model, expected_channels)
        return model, expected_channels
    except Exception:
        return None, 19


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
        board_width=15,
        board_height=13,
        max_steps=900,
        frame_skip=6,
        num_bots=3,
        wall_density=65,
        tactical_shield=True,
        use_10_channels=False,
        randomize_curriculum=False,
        sudden_death_ticks=None,
        num_ai_opponents=0,
        self_play_model_path=None,
    ):
        super().__init__()
        self.width = board_width
        self.height = board_height
        self.num_bots = num_bots
        self.num_ai_opponents = num_ai_opponents
        self.self_play_model_path = self_play_model_path
        self.wall_density = wall_density
        self.player_id = 1
        self.max_steps = max_steps
        self.frame_skip = frame_skip
        self.tactical_shield = tactical_shield
        self.use_10_channels = use_10_channels
        self.randomize_curriculum = randomize_curriculum
        self.sudden_death_ticks = sudden_death_ticks

        self.game = bme.Game(self.width, self.height)
        self.action_space = spaces.Discrete(6)
        self.n_channels = 10 if self.use_10_channels else 19
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
        self._active_ai_opponent_ids: List[int] = []
        self._cached_obs = None
        self._cached_potential = 0.0
        self._cached_analysis = None

    def _compute_bfs_features(self, base_obs):
        pinfo = self.game.getPlayerInfo(self.player_id)
        return compute_bfs_features(base_obs, pinfo, self.width, self.height)

    def _format_obs(self, base_obs, reach_map, bomb_map):
        return format_obs(base_obs, reach_map, bomb_map, expected_channels=self.n_channels)

    def action_masks(self) -> np.ndarray:
        """Returns boolean action mask [idle, up, down, left, right, bomb] for MaskablePPO."""
        return compute_action_mask(self._cached_analysis)

    def _get_ai_opponent_commands(self) -> List[bme.PlayerCommand]:
        """Computes frozen Self-Play PPO + Tactical Shield commands for active AI opponent slots."""
        if not self._active_ai_opponent_ids:
            return []
        opp_model, opp_channels = _get_shared_opponent_model(
            self.self_play_model_path, self.height, self.width
        )
        cmds: List[bme.PlayerCommand] = []
        for opp_id in self._active_ai_opponent_ids:
            opp_info = self.game.getPlayerInfo(opp_id)
            if not opp_info.isAlive:
                continue
            opp_base = np.asarray(self.game.getState(opp_id), dtype=np.float32).reshape(
                -1, self.height, self.width
            )
            opp_reach, opp_bomb, _, opp_analysis = compute_bfs_features(
                opp_base, opp_info, self.width, self.height
            )
            if opp_model is not None:
                opp_obs = format_obs(
                    opp_base, opp_reach, opp_bomb, expected_channels=opp_channels
                )
                with th.no_grad():
                    opp_mask = compute_action_mask(opp_analysis)
                    obs_t = th.as_tensor(opp_obs[None], dtype=th.float32)
                    try:
                        dist = opp_model.policy.get_distribution(obs_t, action_masks=opp_mask[None])
                        raw_act = int(dist.get_actions(deterministic=False).item())
                    except Exception:
                        try:
                            raw_act, _ = opp_model.predict(
                                opp_obs, action_masks=opp_mask, deterministic=False
                            )
                        except (TypeError, ValueError):
                            raw_act, _ = opp_model.predict(opp_obs, deterministic=False)
                exec_act, _ = apply_tactical_shield(
                    int(raw_act), opp_analysis, rng=self.np_random
                )
            else:
                exec_act = choose_bfs_fallback_action(opp_analysis, rng=self.np_random)
            if exec_act != 0:
                cmds.append(bme.PlayerCommand(opp_id, self.action_mapping[exec_act]))
        return cmds

    def step(self, action):
        self.current_step += 1
        raw_action = int(action)

        if self._cached_analysis is None:
            base_obs = np.asarray(self.game.getState(self.player_id), dtype=np.float32).reshape(
                -1, self.height, self.width
            )
            _, _, prev_potential, analysis = self._compute_bfs_features(base_obs)
        else:
            prev_potential = self._cached_potential
            analysis = self._cached_analysis

        exec_action = raw_action
        shield_intervened = False
        if self.tactical_shield:
            exec_action, shield_intervened = apply_tactical_shield(
                raw_action, analysis, rng=self.np_random
            )
            if shield_intervened:
                self.ep_stats["shield_interventions"] += 1

        cpp_command = self.action_mapping[exec_action]
        total_reward, moved_any, bomb_placed_any, bomb_pushed_any, won, died = 0.0, False, False, False, False, False
        if shield_intervened:
            if analysis["in_danger"] or raw_action == 5:
                total_reward -= 0.20
            else:
                total_reward -= 0.08
        ticks_executed = 0

        extra_cmds = self._get_ai_opponent_commands() if self._active_ai_opponent_ids else []

        for tick_idx in range(self.frame_skip):
            cmd = cpp_command if tick_idx == 0 else bme.Command.NONE
            tick_extra = extra_cmds if tick_idx == 0 else []
            res = self.game.step(self.player_id, cmd, tick_extra)
            ticks_executed += 1
            total_reward += float(res.reward)
            moved_any |= res.moved
            bomb_placed_any |= res.bombPlaced
            bomb_pushed_any |= res.bombPushed
            won |= res.won
            died |= res.died
            self.ep_stats["walls_destroyed"] += res.wallsDestroyed
            self.ep_stats["enemies_hit"] += res.enemiesHit
            self.ep_stats["kills"] += res.enemiesKilled
            self.ep_stats["powerups"] += res.powerUpsCollected
            self.ep_stats["lives_lost"] += res.livesLost
            if res.isDone:
                break

            pinfo = self.game.getPlayerInfo(self.player_id)
            if not pinfo.isAlive:
                break

            if tick_idx == 0 and (res.bombPlaced or res.bombPushed):
                if pinfo.cooldown <= 1:
                    break
            elif moved_any:
                if pinfo.cooldown <= 1:
                    break
            else:
                if ticks_executed >= min(self.frame_skip, 4):
                    break

        self.ep_stats["ticks"] += ticks_executed

        new_base_obs = np.asarray(self.game.getState(self.player_id), dtype=np.float32).reshape(
            -1, self.height, self.width
        )
        reach_map, bomb_map, new_potential, post_analysis = self._compute_bfs_features(new_base_obs)
        obs = self._format_obs(new_base_obs, reach_map, bomb_map)
        self._cached_obs = obs
        self._cached_potential = new_potential
        self._cached_analysis = post_analysis

        self.ep_stats["steps"] += 1
        if raw_action == 0:
            self.ep_stats["idle_actions"] += 1
        if raw_action in (1, 2, 3, 4) and not moved_any and not bomb_pushed_any:
            self.ep_stats["wall_bumps"] += 1
        if moved_any:
            self.ep_stats["moves"] += 1
            if post_analysis.get("pos"):
                self.visited_tiles.add(post_analysis["pos"])
        if bomb_placed_any:
            self.ep_stats["bombs_placed"] += 1
            if analysis["safe_escape_from_here"] and analysis["bomb_targets_here"] > 0:
                self.ep_stats["tactical_bombs"] += 1
                enemy_t = int(analysis.get("enemy_targets_here", 0))
                compressed_t = int(analysis.get("enemy_space_compressed_here", 0))
                trap_here = bool(analysis.get("trap_bomb_here", False))
                total_reward += 0.35 + (1.6 * enemy_t) + (0.40 * min(compressed_t, 6))
                if trap_here:
                    self.ep_stats["traps_created"] += 1
                    total_reward += 3.50
            else:
                total_reward -= 0.45
        if bomb_pushed_any:
            self.ep_stats["bombs_pushed"] += 1
            prev_en_safe = int(analysis.get("total_enemy_safe_tiles", 0))
            post_en_safe = int(post_analysis.get("total_enemy_safe_tiles", 0))
            push_compressed = max(0, prev_en_safe - post_en_safe)
            newly_trapped = (
                int(post_analysis.get("trapped_enemies_count", 0))
                > int(analysis.get("trapped_enemies_count", 0))
            )
            if (
                exec_action in analysis.get("tactical_push_actions", [])
                or analysis["in_danger"]
                or push_compressed > 0
                or newly_trapped
            ):
                total_reward += 1.2 + (0.40 * min(push_compressed, 6))
                if newly_trapped:
                    self.ep_stats["traps_created"] += 1
                    total_reward += 3.50
            else:
                total_reward -= 0.1
        if analysis["in_danger"] and not post_analysis["in_danger"] and not died:
            self.ep_stats["successful_dodges"] += 1

        terminated = won or died or res.isDone
        if not terminated:
            total_reward += float(np.clip(0.3 * (0.99 * new_potential - prev_potential), -1.0, 1.0))
            if not self.tactical_shield and raw_action in (1, 2, 3, 4) and raw_action not in analysis["valid_moves"]:
                total_reward -= 0.15
            if not moved_any and not bomb_placed_any and not bomb_pushed_any and not analysis["in_danger"]:
                self.idle_streak += 1
                if self.idle_streak > 2:
                    total_reward -= 0.2
            else:
                self.idle_streak = 0

        truncated = bool(self.current_step >= self.max_steps and not terminated)
        if truncated and not won:
            total_reward -= 15.0
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
            "ticks": 0,
            "moves": 0,
            "idle_actions": 0,
            "wall_bumps": 0,
            "bombs_placed": 0,
            "bombs_pushed": 0,
            "tactical_bombs": 0,
            "walls_destroyed": 0,
            "enemies_hit": 0,
            "kills": 0,
            "powerups": 0,
            "lives_lost": 0,
            "successful_dodges": 0,
            "shield_interventions": 0,
            "traps_created": 0,
            "unique_tiles": 1,
            "won": 0.0,
            "survived": 1.0,
        }
        active_bots = self.num_bots
        active_ai_opps = self.num_ai_opponents
        active_density = self.wall_density
        if self.randomize_curriculum:
            active_bots = int(self.np_random.choice([1, 2, 3], p=[0.25, 0.35, 0.40]))
            active_density = int(self.np_random.choice([35, 50, 65, 75], p=[0.20, 0.30, 0.35, 0.15]))
            if self.self_play_model_path or self.num_ai_opponents > 0:
                max_ai = min(2, active_bots)
                active_ai_opps = int(self.np_random.integers(0, max_ai + 1))

        active_ai_opps = max(0, min(active_ai_opps, active_bots))
        active_dumb_bots = max(0, active_bots - active_ai_opps)
        self._active_ai_opponent_ids = list(range(2, 2 + active_ai_opps))

        self.game.reset(
            bme.ClassicLevel(1 + active_bots, self.width, self.height, active_density),
            1 + active_ai_opps,
            active_dumb_bots,
        )

        if self.sudden_death_ticks is not None:
            self.game.setSuddenDeathTimer(int(self.sudden_death_ticks))
        elif self.randomize_curriculum:
            roll = float(self.np_random.random())
            if roll < 0.20:
                self.game.setSuddenDeathTimer(int(self.np_random.integers(240, 900)))
            if float(self.np_random.random()) < 0.25:
                pu_choice = str(self.np_random.choice(["H", "R", "S", "B", "L"]))
                self.game.givePlayerPowerUp(self.player_id, pu_choice)
                if float(self.np_random.random()) < 0.35:
                    self.game.givePlayerPowerUp(self.player_id, "H")

        base_obs = np.asarray(self.game.getState(self.player_id), dtype=np.float32).reshape(
            -1, self.height, self.width
        )
        reach_map, bomb_map, potential, analysis = self._compute_bfs_features(base_obs)
        if analysis.get("pos"):
            self.visited_tiles.add(analysis["pos"])
        obs = self._format_obs(base_obs, reach_map, bomb_map)
        self._cached_obs = obs
        self._cached_potential = potential
        self._cached_analysis = analysis
        return obs, {}
