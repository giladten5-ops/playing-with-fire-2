import os
from collections import deque
from typing import Any, Dict, List, Optional, Tuple
import gymnasium as gym
import numpy as np
import torch as th
import torch.nn as nn
from gymnasium import spaces
from stable_baselines3 import PPO
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
import bomberman_engine as bme
from rl.rl_utils import (
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
        max_steps=1500,
        max_match_ticks=3600,
        frame_skip=6,
        num_bots=3,
        wall_density=65,
        tactical_shield=True,
        use_10_channels=False,
        use_bfs_channels=False,
        mask_mode="clean",
        randomize_curriculum=False,
        sudden_death_ticks=1200,
        num_ai_opponents=0,
        self_play_model_path=None,
        gamma=0.995,
        curriculum_slot=None,
        worker_target_steps=0,
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
        self.max_match_ticks = int(max_match_ticks)
        self.frame_skip = frame_skip
        self.tactical_shield = tactical_shield
        self.use_10_channels = use_10_channels
        self.use_bfs_channels = use_bfs_channels
        self.mask_mode = mask_mode
        self.randomize_curriculum = randomize_curriculum
        self.sudden_death_ticks = sudden_death_ticks
        self.gamma = float(gamma)
        self.curriculum_slot = curriculum_slot
        self.worker_target_steps = int(worker_target_steps)
        self._worker_steps_completed = 0

        self.game = bme.Game(self.width, self.height)
        self.action_space = spaces.Discrete(6)
        if self.use_10_channels:
            self.n_channels = 10
        elif self.use_bfs_channels:
            self.n_channels = 19
        else:
            self.n_channels = 17
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
        self._stagnation_window: deque = deque()
        self._active_ai_opponent_ids: List[int] = []
        self._opp_idle_cooldowns: Dict[int, int] = {}
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
        return compute_action_mask(self._cached_analysis, mode=self.mask_mode)

    def _get_ai_opponent_commands_for_tick(self) -> List[bme.PlayerCommand]:
        """Computes frozen Self-Play PPO + Shield commands on the exact tick each opponent's cooldown <= 1."""
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
            if opp_info.cooldown > 1:
                continue
            idle_cd = self._opp_idle_cooldowns.get(opp_id, 0)
            if idle_cd > 0:
                self._opp_idle_cooldowns[opp_id] = idle_cd - 1
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
                opp_mode = "clean" if opp_channels == 17 else "legacy"
                with th.no_grad():
                    opp_mask = compute_action_mask(opp_analysis, mode=opp_mode)
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
                    int(raw_act), opp_analysis, rng=self.np_random, mode=opp_mode
                )
            else:
                exec_act = choose_bfs_fallback_action(opp_analysis, rng=self.np_random)
            if exec_act == 0:
                self._opp_idle_cooldowns[opp_id] = max(0, self.frame_skip - 1)
            else:
                self._opp_idle_cooldowns[opp_id] = 0
                cmds.append(bme.PlayerCommand(opp_id, self.action_mapping[exec_act]))
        return cmds

    def step(self, action):
        self.current_step += 1
        self._worker_steps_completed += 1
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
                raw_action, analysis, rng=self.np_random, mode=self.mask_mode
            )
            if shield_intervened:
                self.ep_stats["shield_interventions"] += 1

        cpp_command = self.action_mapping[exec_action]
        total_reward, moved_any, bomb_placed_any, bomb_pushed_any, won, died = 0.0, False, False, False, False, False
        rew_tact = 0.0
        if shield_intervened:
            pen = -0.20 if (analysis["in_danger"] or raw_action == 5) else -0.08
            total_reward += pen
            rew_tact += pen

        ticks_executed = 0
        step_walls = 0
        step_hits = 0
        step_kills = 0
        step_powerups = 0
        step_lives_lost = 0
        res_done = False

        for tick_idx in range(self.frame_skip):
            if self.ep_stats["ticks"] + ticks_executed >= self.max_match_ticks:
                break
            cmd = cpp_command if tick_idx == 0 else bme.Command.NONE
            tick_extra = self._get_ai_opponent_commands_for_tick() if self._active_ai_opponent_ids else []
            res = self.game.step(self.player_id, cmd, tick_extra)
            ticks_executed += 1
            total_reward += float(res.reward)
            moved_any |= res.moved
            bomb_placed_any |= res.bombPlaced
            bomb_pushed_any |= res.bombPushed
            won |= res.won
            died |= res.died
            res_done |= res.isDone
            step_walls += res.wallsDestroyed
            step_hits += res.enemiesHit
            step_kills += res.enemiesKilled
            step_powerups += res.powerUpsCollected
            step_lives_lost += res.livesLost
            if res.isDone:
                break
            if self.ep_stats["ticks"] + ticks_executed >= self.max_match_ticks:
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
        self.ep_stats["walls_destroyed"] += step_walls
        self.ep_stats["enemies_hit"] += step_hits
        self.ep_stats["kills"] += step_kills
        self.ep_stats["powerups"] += step_powerups
        self.ep_stats["lives_lost"] += step_lives_lost

        rew_time = -0.003 * float(ticks_executed)
        rew_prog = 0.20 * float(step_walls) + 0.80 * float(step_powerups)
        rew_combat = 6.0 * float(step_hits) + 12.0 * float(step_kills) - 6.0 * float(step_lives_lost)
        rew_term = (100.0 if won else 0.0) + (-72.0 if died else 0.0)

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
                if bool(analysis.get("trap_bomb_here", False)):
                    self.ep_stats["traps_created"] += 1
        if bomb_pushed_any:
            self.ep_stats["bombs_pushed"] += 1
            prev_en_safe = int(analysis.get("total_enemy_safe_tiles", 0))
            post_en_safe = int(post_analysis.get("total_enemy_safe_tiles", 0))
            push_compressed = max(0, prev_en_safe - post_en_safe)
            trapped_emergency = bool(analysis["in_danger"] and int(analysis.get("escape_action", 0)) == exec_action)
            if not (
                exec_action in analysis.get("tactical_push_actions", [])
                or trapped_emergency
                or push_compressed > 0
            ):
                total_reward -= 0.10
                rew_tact -= 0.10
        if analysis["in_danger"] and not post_analysis["in_danger"] and not died:
            self.ep_stats["successful_dodges"] += 1

        engine_done = bool(won or died or res_done)
        match_timeout = bool((not engine_done) and (self.ep_stats["ticks"] >= self.max_match_ticks))
        terminated = bool(engine_done or match_timeout)
        truncated = bool((not terminated) and (self.current_step >= self.max_steps))

        if won:
            win_speed_bonus = 20.0 * max(
                0.0, 1.0 - float(self.ep_stats["ticks"]) / float(max(1, self.max_match_ticks))
            )
            total_reward += win_speed_bonus
            rew_term += win_speed_bonus
        elif match_timeout:
            timeout_pen = -max(0.0, 90.0 - 6.0 * float(self.ep_stats["lives_lost"]))
            total_reward += timeout_pen
            rew_term += timeout_pen

        # Exact Standard Potential-Based Reward Shaping (Ng et al., 1999):
        # F(s_t, s_{t+1}) = gamma * Phi(s_{t+1}) - Phi(s_t), applied uniformly on EVERY transition
        # with Phi(s_terminal) = 0.0 and preserved Phi(s_T) on external truncation.
        phi_next = 0.0 if terminated else float(new_potential)
        rew_pbrs = float(self.gamma * phi_next - prev_potential)
        total_reward += rew_pbrs

        # Tick-proportional spatial stagnation heuristic (-0.005 * ticks_executed):
        # Evaluated only when safe, open (safe_reachable_count > 4), with no local bombs and no bomb placed.
        rew_stagnation = 0.0
        if not terminated and not truncated:
            if not self.tactical_shield and raw_action in (1, 2, 3, 4) and raw_action not in analysis["valid_moves"]:
                total_reward -= 0.15
                rew_tact -= 0.15

            local_bombs = int(post_analysis.get("local_active_bombs", post_analysis.get("active_bombs_count", 0)))
            safe_reach = int(post_analysis.get("safe_reachable_count", 0))
            pos = post_analysis.get("pos")
            if (
                not post_analysis["in_danger"]
                and local_bombs == 0
                and safe_reach > 4
                and not bomb_placed_any
                and pos is not None
            ):
                cur_tick = int(self.ep_stats["ticks"])
                self._stagnation_window.append((cur_tick, int(pos[0]), int(pos[1])))
                while len(self._stagnation_window) > 1 and (cur_tick - self._stagnation_window[1][0]) >= 60:
                    self._stagnation_window.popleft()
                if (cur_tick - self._stagnation_window[0][0]) >= 60:
                    xs = [p[1] for p in self._stagnation_window]
                    ys = [p[2] for p in self._stagnation_window]
                    span = (max(xs) - min(xs)) + (max(ys) - min(ys))
                    if span <= 2:
                        rew_stagnation = -0.005 * float(ticks_executed)
                        total_reward += rew_stagnation
            else:
                self._stagnation_window.clear()
        else:
            self._stagnation_window.clear()

        self.ep_stats["rew_term"] += rew_term
        self.ep_stats["rew_combat"] += rew_combat
        self.ep_stats["rew_prog"] += rew_prog
        self.ep_stats["rew_tact"] += rew_tact
        self.ep_stats["rew_pbrs"] += rew_pbrs
        self.ep_stats["rew_time"] += rew_time
        self.ep_stats["rew_stagnation"] += rew_stagnation
        self.ep_stats["last_pbrs_reward"] = rew_pbrs
        self.ep_stats["last_phi_prev"] = float(prev_potential)
        self.ep_stats["last_phi_next"] = float(phi_next)

        info: Dict[str, Any] = {
            "pbrs_reward": rew_pbrs,
            "phi_prev": float(prev_potential),
            "phi_next": float(phi_next),
            "ticks_executed": ticks_executed,
            "match_timeout": match_timeout,
            "rew_stagnation": rew_stagnation,
        }
        if terminated or truncated:
            self.ep_stats["unique_tiles"] = len(self.visited_tiles)
            self.ep_stats["won"] = 1.0 if won else 0.0
            self.ep_stats["lost"] = 1.0 if died else 0.0
            self.ep_stats["draw"] = 1.0 if (not won and not died) else 0.0
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
        self._stagnation_window.clear()
        self._opp_idle_cooldowns.clear()
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
            "lost": 0.0,
            "draw": 0.0,
            "survived": 1.0,
            "rew_term": 0.0,
            "rew_combat": 0.0,
            "rew_prog": 0.0,
            "rew_tact": 0.0,
            "rew_pbrs": 0.0,
            "rew_time": 0.0,
            "rew_stagnation": 0.0,
            "last_pbrs_reward": 0.0,
            "last_phi_prev": 0.0,
            "last_phi_next": 0.0,
        }
        active_bots = self.num_bots
        active_ai_opps = self.num_ai_opponents
        active_density = self.wall_density
        active_sd_ticks = self.sudden_death_ticks
        starting_powerup_chance = 0.0
        starting_powerup_pool: List[str] = ["H", "R", "S", "B", "L"]

        if self.curriculum_slot is not None and self.worker_target_steps > 0:
            progress = min(1.0, float(self._worker_steps_completed) / float(max(1, self.worker_target_steps)))
            slot = int(self.curriculum_slot) % 4
            has_sp = bool(self.self_play_model_path and os.path.exists(self.self_play_model_path))
            if progress < 0.25:
                # Phase 1: Foundation, fuse escape, crate breaching & 1v1 approach
                if slot == 0:
                    active_bots, active_density, active_sd_ticks, active_ai_opps = 1, 30, 1500, 0
                elif slot == 1:
                    active_bots, active_density, active_sd_ticks, active_ai_opps = 1, 40, 1200, 0
                elif slot == 2:
                    active_bots, active_density, active_sd_ticks, active_ai_opps = 2, 50, 1200, 0
                else:
                    active_bots, active_density, active_sd_ticks, active_ai_opps = 3, 65, 1200, 0
            elif progress < 0.60:
                # Phase 2: Offensive pressure, controlled special abilities & multi-bot combat
                if slot == 0:
                    active_bots, active_density, active_sd_ticks = 1, 35, 1000
                    active_ai_opps = 1 if has_sp else 0
                elif slot == 1:
                    active_bots, active_density, active_sd_ticks, active_ai_opps = 2, 45, 1200, 0
                    starting_powerup_chance = 0.20
                    starting_powerup_pool = ["H", "R"]
                elif slot == 2:
                    active_bots, active_density, active_sd_ticks, active_ai_opps = 2, 55, 1200, 0
                else:
                    active_bots, active_density, active_sd_ticks, active_ai_opps = 3, 65, 1200, 0
            else:
                # Phase 3: Full match competence & generalization with retained duel exposure
                if slot == 0:
                    active_bots, active_density, active_sd_ticks = 1, 40, 1000
                    active_ai_opps = 1 if has_sp else 0
                elif slot == 1:
                    active_bots, active_density, active_sd_ticks, active_ai_opps = 2, 50, 1200, 0
                elif slot == 2:
                    active_bots, active_density, active_sd_ticks, active_ai_opps = 3, 65, 1200, 0
                else:
                    active_bots = int(self.np_random.choice([2, 3], p=[0.40, 0.60]))
                    active_density = int(self.np_random.choice([35, 50, 65, 75], p=[0.20, 0.30, 0.35, 0.15]))
                    active_sd_ticks = int(self.np_random.choice([900, 1200, 1500]))
                    active_ai_opps = int(self.np_random.integers(0, min(2, active_bots) + 1)) if has_sp else 0
                    starting_powerup_chance = 0.15
        elif self.randomize_curriculum:
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

        if active_sd_ticks is not None:
            self.game.setSuddenDeathTimer(int(active_sd_ticks))

        if starting_powerup_chance > 0.0 and float(self.np_random.random()) < starting_powerup_chance:
            pu_choice = str(self.np_random.choice(starting_powerup_pool))
            self.game.givePlayerPowerUp(self.player_id, pu_choice)

        base_obs = np.asarray(self.game.getState(self.player_id), dtype=np.float32).reshape(
            -1, self.height, self.width
        )
        reach_map, bomb_map, potential, analysis = self._compute_bfs_features(base_obs)
        if analysis.get("pos"):
            self.visited_tiles.add(analysis["pos"])
            if (
                not analysis["in_danger"]
                and int(analysis.get("local_active_bombs", 0)) == 0
                and int(analysis.get("safe_reachable_count", 0)) > 4
            ):
                self._stagnation_window.append((0, int(analysis["pos"][0]), int(analysis["pos"][1])))
        obs = self._format_obs(base_obs, reach_map, bomb_map)
        self._cached_obs = obs
        self._cached_potential = potential
        self._cached_analysis = analysis
        return obs, {}
