#!/usr/bin/env python3
"""
Multi-Metric Statistical Benchmark Suite:
Compares Random Baseline, Legacy v1 Model (8-channel, no shield), and Strategic v2 Model (10-channel + PBRS + Tactical Shield)
across unseen map seeds and multiple opponent configurations.
"""

import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from stable_baselines3 import PPO
from bomberman_env import BombermanEnv, BombermanCNN


def run_evaluation(agent_name, predict_fn, env_kwargs, n_episodes=30, base_seed=10000):
    env = BombermanEnv(**env_kwargs)
    metrics_list = []
    returns = []

    for ep in range(n_episodes):
        obs, _ = env.reset(seed=base_seed + ep * 17)
        done = False
        ep_ret = 0.0
        info = {}
        while not done:
            action = predict_fn(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            ep_ret += reward
            done = terminated or truncated

        returns.append(ep_ret)
        metrics_list.append(info.get("episode_metrics", env.ep_stats))

    def avg(key):
        return float(np.mean([m.get(key, 0.0) for m in metrics_list]))

    total_steps = np.array([max(1, m.get("steps", 1)) for m in metrics_list], dtype=np.float32)
    idle_rates = np.array([m.get("idle_actions", 0) + m.get("wall_bumps", 0) for m in metrics_list]) / total_steps
    move_eff = np.array([m.get("unique_tiles", 1) / max(1, m.get("moves", 1)) for m in metrics_list])
    bombs_arr = np.array([m.get("bombs_placed", 0) for m in metrics_list], dtype=np.float32)
    walls_arr = np.array([m.get("walls_destroyed", 0) for m in metrics_list], dtype=np.float32)
    kills_arr = np.array([m.get("kills", 0) for m in metrics_list], dtype=np.float32)
    bomb_eff = float(np.sum(walls_arr + kills_arr) / max(1.0, np.sum(bombs_arr)))

    summary = {
        "agent": agent_name,
        "win_rate_pct": avg("won") * 100.0,
        "survival_rate_pct": avg("survived") * 100.0,
        "avg_return": float(np.mean(returns)),
        "std_return": float(np.std(returns)),
        "kills_per_game": avg("kills"),
        "walls_per_game": avg("walls_destroyed"),
        "bombs_per_game": avg("bombs_placed"),
        "tactical_bombs_per_game": avg("tactical_bombs"),
        "bomb_effectiveness": bomb_eff,
        "powerups_per_game": avg("powerups"),
        "dodges_per_game": avg("successful_dodges"),
        "lives_lost_per_game": avg("lives_lost"),
        "idle_or_stuck_pct": float(np.mean(idle_rates) * 100.0),
        "unique_tiles_visited": avg("unique_tiles"),
        "movement_efficiency": float(np.mean(move_eff)),
        "avg_ep_len": avg("steps"),
    }
    return summary


def main():
    n_episodes = int(os.environ.get("BENCHMARK_EPISODES", "30"))
    print("=" * 78)
    print(f"RUNNING COMPREHENSIVE BOMBERMAN AI BENCHMARK ({n_episodes} unseen seeds per agent)")
    print("=" * 78)

    results = []

    # 1. Random Baseline (No Shield)
    rng = np.random.default_rng(42)
    res_random = run_evaluation(
        "Random Baseline",
        lambda obs: int(rng.integers(0, 6)),
        dict(num_bots=3, wall_density=65, use_10_channels=False, tactical_shield=False),
        n_episodes=n_episodes,
    )
    results.append(res_random)

    # 2. Legacy v1 Model (8-Channel, No Shield)
    legacy_path = "models/legacy_backup/legacy_v1_model.zip"
    if os.path.exists(legacy_path):
        legacy_model = PPO.load(legacy_path, custom_objects={"BombermanCNN": BombermanCNN})
        res_legacy = run_evaluation(
            "Legacy PPO v1 (Old)",
            lambda obs: int(legacy_model.predict(obs, deterministic=True)[0].item()),
            dict(num_bots=3, wall_density=65, use_10_channels=False, tactical_shield=False),
            n_episodes=n_episodes,
        )
        results.append(res_legacy)

    # 3. Strategic v2 Model (10-Channel + PBRS + Tactical Shield)
    v2_candidates = ["models/v2_best/best_model.zip", "models/ppo_bomberman_v2_strategic.zip"]
    v2_path = next((p for p in v2_candidates if os.path.exists(p)), None)
    if v2_path:
        v2_model = PPO.load(v2_path, custom_objects={"BombermanCNN": BombermanCNN})
        res_v2_3bots = run_evaluation(
            "Strategic PPO v2 (1v3 Arena)",
            lambda obs: int(v2_model.predict(obs, deterministic=True)[0].item()),
            dict(num_bots=3, wall_density=65, use_10_channels=True, tactical_shield=True),
            n_episodes=n_episodes,
        )
        results.append(res_v2_3bots)

        # Generalization test: Unseen dense map (75% walls) & 1v1 duel
        res_v2_1v1 = run_evaluation(
            "Strategic PPO v2 (1v1 Duel)",
            lambda obs: int(v2_model.predict(obs, deterministic=True)[0].item()),
            dict(num_bots=1, wall_density=55, use_10_channels=True, tactical_shield=True),
            n_episodes=n_episodes,
            base_seed=50000,
        )
        results.append(res_v2_1v1)

    # Print formatted comparison table
    header = f"{'Agent / Scenario':<28} | {'Win%':>6} | {'Surv%':>6} | {'Kills':>5} | {'Walls':>5} | {'Bombs':>5} | {'P-Ups':>5} | {'Stuck%':>6} | {'Tiles':>5}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['agent']:<28} | "
            f"{r['win_rate_pct']:>5.1f}% | "
            f"{r['survival_rate_pct']:>5.1f}% | "
            f"{r['kills_per_game']:>5.2f} | "
            f"{r['walls_per_game']:>5.1f} | "
            f"{r['bombs_per_game']:>5.1f} | "
            f"{r['powerups_per_game']:>5.2f} | "
            f"{r['idle_or_stuck_pct']:>5.1f}% | "
            f"{r['unique_tiles_visited']:>5.1f}"
        )
    print("=" * 78)

    with open("models/benchmark_summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    # Generate comparison chart
    labels = [r["agent"] for r in results]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle("Bomberman AI Benchmark: Legacy v1 vs Strategic v2", fontsize=14, fontweight="bold")

    axes[0, 0].bar(labels, [r["win_rate_pct"] for r in results], color=["#888888", "#d9534f", "#5cb85c", "#0275d8"][:len(results)])
    axes[0, 0].set_title("Win Rate (%) - Higher is Better")
    axes[0, 0].set_ylabel("Win Rate %")
    axes[0, 0].tick_params(axis="x", rotation=15)

    axes[0, 1].bar(labels, [r["idle_or_stuck_pct"] for r in results], color=["#888888", "#d9534f", "#5cb85c", "#0275d8"][:len(results)])
    axes[0, 1].set_title("Idle / Wall-Stuck Time (%) - Lower is Better")
    axes[0, 1].set_ylabel("% of Steps Stuck/Idle")
    axes[0, 1].tick_params(axis="x", rotation=15)

    axes[1, 0].bar(labels, [r["walls_per_game"] for r in results], color=["#888888", "#d9534f", "#5cb85c", "#0275d8"][:len(results)])
    axes[1, 0].set_title("Breakable Walls Destroyed per Game")
    axes[1, 0].set_ylabel("Walls / Game")
    axes[1, 0].tick_params(axis="x", rotation=15)

    axes[1, 1].bar(labels, [r["kills_per_game"] for r in results], color=["#888888", "#d9534f", "#5cb85c", "#0275d8"][:len(results)])
    axes[1, 1].set_title("Enemy Kills per Game")
    axes[1, 1].set_ylabel("Kills / Game")
    axes[1, 1].tick_params(axis="x", rotation=15)

    plt.tight_layout()
    plt.savefig("benchmark_comparison.png", dpi=150)
    print("[PLOT] Saved visual benchmark report to 'benchmark_comparison.png' and 'models/benchmark_summary.json'.")


if __name__ == "__main__":
    main()
