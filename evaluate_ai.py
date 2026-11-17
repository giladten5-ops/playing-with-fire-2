#!/usr/bin/env python3
"""Independent evaluation and benchmarking suite for Bomberman PPO AI models.

Supports evaluating:
- Trained PPO models (.zip checkpoints) with Tactical Shield (default) or Raw Policy (--no-shield)
- Pure BFS + Tactical Shield heuristic baseline (when --baseline-bfs is passed)
- Multi-scenario benchmark suites (1v1, 1v2, 1v3 Classic, Dense Walls, Hammer & Ring Arena, Fast Sudden Death)
- Live multi-agent CppGameSession / GUI controller integration (Trained AI vs DumbBots & Mixed opponents)
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("TORCH_NUM_THREADS", "1")

import argparse
import json
import random
import time
from typing import Any, Dict, List, Optional

import numpy as np
import torch as th
from stable_baselines3 import PPO

import bomberman_engine as bme
from bomberman_env import BombermanCNN, BombermanEnv
from rl_utils import choose_bfs_fallback_action

th.set_num_threads(1)


def seed_everything(seed: int) -> None:
    """Seed Python, NumPy, PyTorch, and the C++ engine RNG deterministically."""
    random.seed(seed)
    np.random.seed(seed)
    th.manual_seed(seed)
    if th.cuda.is_available():
        th.cuda.manual_seed_all(seed)
    bme.seed_rng(int(seed) & 0xFFFFFFFF)


SCENARIO_SUITES: List[Dict[str, Any]] = [
    {
        "name": "1v1_classic",
        "label": "1v1 vs DumbBot (45% Walls)",
        "num_bots": 1,
        "wall_density": 45,
        "sudden_death_ticks": None,
        "grant_powerups": [],
    },
    {
        "name": "1v2_classic",
        "label": "1v2 vs DumbBots (55% Walls)",
        "num_bots": 2,
        "wall_density": 55,
        "sudden_death_ticks": None,
        "grant_powerups": [],
    },
    {
        "name": "1v3_classic",
        "label": "1v3 vs DumbBots (65% Walls)",
        "num_bots": 3,
        "wall_density": 65,
        "sudden_death_ticks": None,
        "grant_powerups": [],
    },
    {
        "name": "1v3_dense",
        "label": "1v3 Dense Maze (75% Walls)",
        "num_bots": 3,
        "wall_density": 75,
        "sudden_death_ticks": None,
        "grant_powerups": [],
    },
    {
        "name": "1v3_hammer_ring",
        "label": "1v3 Hammer & Ring Combat (50% Walls)",
        "num_bots": 3,
        "wall_density": 50,
        "sudden_death_ticks": None,
        "grant_powerups": ["H", "R", "B"],
    },
    {
        "name": "1v3_sudden_death",
        "label": "1v3 Early Sudden Death (450 Ticks)",
        "num_bots": 3,
        "wall_density": 55,
        "sudden_death_ticks": 450,
        "grant_powerups": ["S"],
    },
]


def evaluate_scenario(
    model: Optional[PPO],
    scenario: Dict[str, Any],
    n_episodes: int = 20,
    base_seed: int = 10000,
    tactical_shield: bool = True,
    deterministic: bool = True,
) -> Dict[str, float]:
    """Run n_episodes on a specific scenario and aggregate gameplay metrics."""
    env = BombermanEnv(
        num_bots=scenario["num_bots"],
        wall_density=scenario["wall_density"],
        tactical_shield=tactical_shield,
        randomize_curriculum=False,
        sudden_death_ticks=scenario.get("sudden_death_ticks"),
    )

    metrics_list: List[Dict[str, float]] = []
    episode_rewards: List[float] = []
    outcomes = {"wins": 0, "deaths": 0, "timeouts": 0}

    for ep in range(n_episodes):
        ep_seed = base_seed + ep * 97
        seed_everything(ep_seed)
        obs, _ = env.reset(seed=ep_seed)
        for pu in scenario.get("grant_powerups", []):
            env.game.givePlayerPowerUp(env.player_id, pu)
        if scenario.get("grant_powerups"):
            env._cached_analysis = None
            base_obs = np.asarray(env.game.getState(env.player_id), dtype=np.float32).reshape(
                10, env.height, env.width
            )
            reach_map, bomb_map, potential, analysis = env._compute_bfs_features(base_obs)
            obs = env._format_obs(base_obs, reach_map, bomb_map)
            env._cached_obs = obs
            env._cached_potential = potential
            env._cached_analysis = analysis

        done = False
        ep_reward = 0.0
        while not done:
            if model is not None:
                try:
                    action, _ = model.predict(
                        obs, action_masks=env.action_masks(), deterministic=deterministic
                    )
                except TypeError:
                    action, _ = model.predict(obs, deterministic=deterministic)
                raw_action = int(action)
            else:
                raw_action = choose_bfs_fallback_action(env._cached_analysis)
            obs, reward, terminated, truncated, info = env.step(raw_action)
            ep_reward += float(reward)
            done = terminated or truncated

        episode_rewards.append(ep_reward)
        ep_m = info.get("episode_metrics", env.ep_stats)
        metrics_list.append(ep_m)
        if ep_m.get("won", 0.0) > 0.5:
            outcomes["wins"] += 1
        elif ep_m.get("survived", 1.0) < 0.5:
            outcomes["deaths"] += 1
        else:
            outcomes["timeouts"] += 1

    def avg(key: str) -> float:
        return float(np.mean([m.get(key, 0.0) for m in metrics_list]))

    return {
        "scenario": scenario["name"],
        "label": scenario["label"],
        "episodes": float(n_episodes),
        "win_rate": outcomes["wins"] / n_episodes * 100.0,
        "death_rate": outcomes["deaths"] / n_episodes * 100.0,
        "timeout_draw_rate": outcomes["timeouts"] / n_episodes * 100.0,
        "survival_rate": (outcomes["wins"] + outcomes["timeouts"]) / n_episodes * 100.0,
        "avg_reward": float(np.mean(episode_rewards)),
        "avg_steps": avg("steps"),
        "avg_ticks": avg("ticks"),
        "avg_kills": avg("kills"),
        "avg_enemies_hit": avg("enemies_hit"),
        "avg_walls_destroyed": avg("walls_destroyed"),
        "avg_powerups": avg("powerups"),
        "avg_bombs_placed": avg("bombs_placed"),
        "avg_tactical_bombs": avg("tactical_bombs"),
        "avg_bombs_pushed": avg("bombs_pushed"),
        "avg_dodges": avg("successful_dodges"),
        "avg_unique_tiles": avg("unique_tiles"),
    }


def evaluate_model_suite(
    model_path: Optional[str],
    n_episodes: int = 20,
    base_seed: int = 10000,
    tactical_shield: bool = True,
    output_json: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate a model checkpoint (or BFS baseline if model_path is None) across all scenarios."""
    model = None
    if model_path is not None:
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model checkpoint not found: {model_path}")
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

    algo_name = type(model).__name__ if model is not None else "Pure BFS"
    title = (
        f"{algo_name} Model ({model_path}) [Shield={'ON' if tactical_shield else 'OFF'}]"
        if model_path
        else f"Pure BFS Heuristic Baseline [Shield={'ON' if tactical_shield else 'OFF'}]"
    )
    print(f"\n{'=' * 92}")
    print(f"EVALUATING: {title} | Episodes/Scenario: {n_episodes} | Base Seed: {base_seed}")
    print(f"{'=' * 92}")
    header = (
        f"{'Scenario':<38} | {'Win%':>5} | {'Surv%':>5} | {'Kills':>5} | "
        f"{'Hits':>5} | {'Walls':>5} | {'Bombs':>5} | {'Push':>4} | {'Steps':>5} | {'Reward':>7}"
    )
    print(header)
    print("-" * len(header))

    t0 = time.perf_counter()
    results = []
    for idx, sc in enumerate(SCENARIO_SUITES):
        res = evaluate_scenario(
            model=model,
            scenario=sc,
            n_episodes=n_episodes,
            base_seed=base_seed + idx * 5000,
            tactical_shield=tactical_shield,
        )
        results.append(res)
        print(
            f"{res['label']:<38} | {res['win_rate']:5.1f} | {res['survival_rate']:5.1f} | "
            f"{res['avg_kills']:5.2f} | {res['avg_enemies_hit']:5.2f} | "
            f"{res['avg_walls_destroyed']:5.1f} | {res['avg_bombs_placed']:5.1f} | "
            f"{res['avg_bombs_pushed']:4.2f} | {res['avg_steps']:5.1f} | {res['avg_reward']:7.1f}"
        )

    overall = {
        "win_rate": float(np.mean([r["win_rate"] for r in results])),
        "death_rate": float(np.mean([r["death_rate"] for r in results])),
        "timeout_draw_rate": float(np.mean([r["timeout_draw_rate"] for r in results])),
        "survival_rate": float(np.mean([r["survival_rate"] for r in results])),
        "avg_reward": float(np.mean([r["avg_reward"] for r in results])),
        "avg_steps": float(np.mean([r["avg_steps"] for r in results])),
        "avg_kills": float(np.mean([r["avg_kills"] for r in results])),
        "avg_enemies_hit": float(np.mean([r["avg_enemies_hit"] for r in results])),
        "avg_walls_destroyed": float(np.mean([r["avg_walls_destroyed"] for r in results])),
        "avg_powerups": float(np.mean([r["avg_powerups"] for r in results])),
        "avg_bombs_placed": float(np.mean([r["avg_bombs_placed"] for r in results])),
        "avg_tactical_bombs": float(np.mean([r["avg_tactical_bombs"] for r in results])),
        "avg_bombs_pushed": float(np.mean([r["avg_bombs_pushed"] for r in results])),
        "avg_dodges": float(np.mean([r["avg_dodges"] for r in results])),
        "elapsed_sec": time.perf_counter() - t0,
    }
    print("-" * len(header))
    print(
        f"{'OVERALL MEAN ACROSS ALL 6 SUITES':<38} | {overall['win_rate']:5.1f} | "
        f"{overall['survival_rate']:5.1f} | {overall['avg_kills']:5.2f} | "
        f"{overall['avg_enemies_hit']:5.2f} | {overall['avg_walls_destroyed']:5.1f} | "
        f"{overall['avg_bombs_placed']:5.1f} | {overall['avg_bombs_pushed']:4.2f} | "
        f"{overall['avg_steps']:5.1f} | {overall['avg_reward']:7.1f}"
    )
    print(f"{'=' * 92}\n")

    summary = {
        "model_path": model_path,
        "tactical_shield": tactical_shield,
        "n_episodes_per_scenario": n_episodes,
        "base_seed": base_seed,
        "scenarios": results,
        "overall": overall,
    }
    if output_json:
        os.makedirs(os.path.dirname(output_json) or ".", exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Bomberman PPO AI models across scenario suites.")
    parser.add_argument("--model", type=str, default=None, help="Path to PPO .zip model checkpoint.")
    parser.add_argument("--baseline-bfs", action="store_true", help="Evaluate pure BFS heuristic baseline.")
    parser.add_argument("--episodes", type=int, default=20, help="Number of episodes per scenario.")
    parser.add_argument("--seed", type=int, default=10000, help="Base deterministic seed.")
    parser.add_argument("--no-shield", action="store_true", help="Disable Tactical Shield during evaluation.")
    parser.add_argument("--output-json", type=str, default=None, help="Optional JSON path to save results.")
    args = parser.parse_args()

    model_path = None if args.baseline_bfs else (args.model or "models/v3_best/best_model.zip")
    evaluate_model_suite(
        model_path=model_path,
        n_episodes=args.episodes,
        base_seed=args.seed,
        tactical_shield=not args.no_shield,
        output_json=args.output_json,
    )


if __name__ == "__main__":
    main()
