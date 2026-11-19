#!/usr/bin/env python3
"""End-to-end PPO training pipeline for Playing with Fire 2 (Bomberman C++ Engine).

Features:
- WSL-safe & Low-RAM Architecture:
  * Enforces single-threaded OpenMP/BLAS/PyTorch pools (`OMP_NUM_THREADS=1`, `th.set_num_threads(1)`)
    before importing heavy libraries to prevent CPU thread-pool oversubscription (150+ threads on 12-core WSL).
  * Defaults to `DummyVecEnv` (single-process in-memory vectorized envs) so all training and evaluation
    environments run inside 1 Python process (~280 MB total RSS instead of 13 processes × 300 MB = 3.9 GB OOM).
  * Supports optional `--vec-env subproc` with capped worker count if desired on high-RAM machines.
- Reproducible seeding across Python, NumPy, PyTorch, Gymnasium, and C++ `bme.seed_rng`
- Multi-scenario curriculum diversity (1-3 bots, 35-75% walls, Hammer/Ring/Speed/Sudden Death exposure)
- Periodic CheckpointCallback + deterministic EvalCallback + live EpisodeMetricsCallback
- Supports both Pilot Training (--pilot, 150,000 steps) and Full Training (1,500,000 steps)
- Supports resuming/fine-tuning from an existing checkpoint (--resume <path>)
"""

from __future__ import annotations

import os

# Must be set BEFORE importing numpy / torch to prevent OpenMP / MKL / OpenBLAS thread explosion in WSL
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
os.environ.setdefault("TORCH_NUM_THREADS", "1")

import argparse
import gc
import json
import multiprocessing
import random
import shutil
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import torch as th
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback, CallbackList, CheckpointCallback, EvalCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv

from sb3_contrib import MaskablePPO
from sb3_contrib.common.maskable.buffers import MaskableRolloutBuffer
from sb3_contrib.common.maskable.callbacks import MaskableEvalCallback
from sb3_contrib.common.maskable.policies import MaskableActorCriticPolicy

import bomberman_engine as bme
from bomberman_env import BombermanCNN, BombermanEnv, _get_shared_opponent_model

# Cap PyTorch CPU threads so training never starves the WSL host or VS Code / Antigravity IDE server
th.set_num_threads(2)
try:
    th.set_num_interop_threads(1)
except RuntimeError:
    pass


def seed_everything(seed: int) -> None:
    """Seed Python, NumPy, PyTorch, and C++ engine RNG."""
    random.seed(seed)
    np.random.seed(seed)
    th.manual_seed(seed)
    if th.cuda.is_available():
        th.cuda.manual_seed_all(seed)
    bme.seed_rng(int(seed) & 0xFFFFFFFF)


def linear_schedule(initial_value: float, final_value: float = 5e-5) -> Callable[[float], float]:
    """Linear learning rate schedule from initial_value down to final_value."""
    def func(progress_remaining: float) -> float:
        return final_value + progress_remaining * (initial_value - final_value)
    return func


class EpisodeMetricsCallback(BaseCallback):
    """Logs detailed Bomberman gameplay metrics with a live progress bar, ETA, FPS, and game stats."""

    def __init__(
        self,
        total_timesteps: int,
        log_freq_steps: int = 4096,
        history_path: Optional[str] = None,
        verbose: int = 1,
    ):
        super().__init__(verbose)
        self.total_timesteps = total_timesteps
        self.log_freq_steps = log_freq_steps
        self.history_path = history_path
        self._last_logged_step = 0
        self.ep_buffer: deque = deque(maxlen=80)
        self.reward_buffer: deque = deque(maxlen=80)
        self.history: List[Dict[str, Any]] = []
        self.start_time = time.perf_counter()
        self.start_timesteps = 0

    def _on_training_start(self) -> None:
        self.start_time = time.perf_counter()
        self.start_timesteps = int(self.model.num_timesteps)
        self._last_logged_step = self.start_timesteps

    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        for info in infos:
            ep_m = info.get("episode_metrics")
            if ep_m is not None:
                self.ep_buffer.append(ep_m)
            if "episode" in info:
                self.reward_buffer.append(float(info["episode"]["r"]))

        current_step = self.num_timesteps
        if current_step - self._last_logged_step >= self.log_freq_steps and len(self.ep_buffer) > 0:
            self._last_logged_step = current_step
            run_steps = max(1, current_step - self.start_timesteps)
            elapsed = max(1e-6, time.perf_counter() - self.start_time)
            fps = int(run_steps / elapsed)
            progress = min(1.0, run_steps / max(1, self.total_timesteps))
            eta_seconds = int(max(0, self.total_timesteps - run_steps) / max(fps, 1))
            eta_str = time.strftime("%H:%M:%S", time.gmtime(max(0, eta_seconds)))
            elapsed_str = time.strftime("%H:%M:%S", time.gmtime(int(elapsed)))

            def mean_key(k: str) -> float:
                return float(np.mean([m.get(k, 0.0) for m in self.ep_buffer]))

            mean_rew = float(np.mean(self.reward_buffer)) if self.reward_buffer else 0.0
            win_pct = mean_key("won") * 100.0
            surv_pct = mean_key("survived") * 100.0
            kills = mean_key("kills")
            hits = mean_key("enemies_hit")
            walls = mean_key("walls_destroyed")
            bombs = mean_key("bombs_placed")
            tact_bombs = mean_key("tactical_bombs")
            pushes = mean_key("bombs_pushed")
            dodges = mean_key("successful_dodges")
            shields = mean_key("shield_interventions")
            traps = mean_key("traps_created")

            bar_len = 16
            filled = int(progress * bar_len)
            bar = "█" * filled + "░" * (bar_len - filled)

            entry = {
                "timesteps": int(run_steps),
                "total_model_timesteps": int(current_step),
                "fps": fps,
                "elapsed_sec": round(elapsed, 1),
                "episodes_in_window": len(self.ep_buffer),
                "mean_reward": round(mean_rew, 2),
                "win_rate": round(win_pct, 2),
                "survival_rate": round(surv_pct, 2),
                "avg_kills": round(kills, 3),
                "avg_enemies_hit": round(hits, 3),
                "avg_walls_destroyed": round(walls, 2),
                "avg_bombs_placed": round(bombs, 2),
                "avg_tactical_bombs": round(tact_bombs, 2),
                "avg_bombs_pushed": round(pushes, 3),
                "avg_dodges": round(dodges, 2),
                "avg_shield_interventions": round(shields, 2),
                "avg_traps_created": round(traps, 2),
            }
            self.history.append(entry)

            if self.history_path:
                os.makedirs(os.path.dirname(self.history_path) or ".", exist_ok=True)
                with open(self.history_path, "w", encoding="utf-8") as f:
                    json.dump(self.history, f, indent=2)

            if self.verbose >= 1:
                print(
                    f"[{bar}] {progress * 100:5.1f}% | "
                    f"Step {run_steps:>7,}/{self.total_timesteps:,} | "
                    f"FPS: {fps:>4d} | "
                    f"Time: {elapsed_str} (ETA: {eta_str}) | "
                    f"Rew: {mean_rew:>6.1f} | "
                    f"Win: {win_pct:4.1f}% | Surv: {surv_pct:4.1f}% | "
                    f"Kills: {kills:4.2f} | Hits: {hits:4.2f} | "
                    f"Traps: {traps:4.2f} | "
                    f"Walls: {walls:4.1f} | Bombs: {bombs:4.1f} | "
                    f"Push: {pushes:4.2f} | Dodges: {dodges:4.1f} | "
                    f"Shld: {shields:4.1f}",
                    flush=True,
                )
        return True


def make_train_env(
    rank: int,
    base_seed: int,
    total_envs: int = 4,
    self_play_model_path: Optional[str] = None,
) -> Callable[[], Monitor]:
    """Create a seeded worker environment with structured + League Self-Play curriculum diversity."""
    def _init() -> Monitor:
        th.set_num_threads(1)
        worker_seed = base_seed + rank * 1009
        seed_everything(worker_seed)
        slot = rank % 4
        has_sp = bool(self_play_model_path and os.path.exists(self_play_model_path))
        # Slot 0: 1v1 Self-Play Duel (or 1v1 DumbBot if no self-play model yet) (45% walls)
        # Slot 1: 1v2 Mixed League combat (1 Self-Play AI + 1 DumbBot, 55% walls)
        # Slot 2: 1v3 Full standard DumbBot match (65% walls — prevents catastrophic forgetting)
        # Slot 3: Randomized League curriculum (varying AI/DumbBot mix, wall densities, powerups, Sudden Death)
        if slot == 0:
            env = BombermanEnv(
                num_bots=1,
                num_ai_opponents=1 if has_sp else 0,
                self_play_model_path=self_play_model_path if has_sp else None,
                wall_density=45,
                randomize_curriculum=False,
            )
        elif slot == 1:
            env = BombermanEnv(
                num_bots=2,
                num_ai_opponents=1 if has_sp else 0,
                self_play_model_path=self_play_model_path if has_sp else None,
                wall_density=55,
                randomize_curriculum=False,
            )
        elif slot == 2:
            env = BombermanEnv(
                num_bots=3,
                num_ai_opponents=0,
                wall_density=65,
                randomize_curriculum=False,
            )
        else:
            env = BombermanEnv(
                num_bots=3,
                num_ai_opponents=1 if has_sp else 0,
                self_play_model_path=self_play_model_path if has_sp else None,
                wall_density=60,
                randomize_curriculum=True,
            )
        env.reset(seed=worker_seed)
        return Monitor(env, info_keywords=("is_success", "win"))
    return _init


def make_eval_env(base_seed: int, self_play_model_path: Optional[str] = None) -> Callable[[], Monitor]:
    """Create a lightweight in-process evaluation environment with curriculum coverage."""
    def _init() -> Monitor:
        eval_seed = base_seed + 50000
        seed_everything(eval_seed)
        has_sp = bool(self_play_model_path and os.path.exists(self_play_model_path))
        env = BombermanEnv(
            num_bots=2,
            num_ai_opponents=1 if has_sp else 0,
            self_play_model_path=self_play_model_path if has_sp else None,
            wall_density=55,
            randomize_curriculum=True,
        )
        env.reset(seed=eval_seed)
        return Monitor(env, info_keywords=("is_success", "win"))
    return _init


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Bomberman PPO Agent (Pilot & Full Training)")
    parser.add_argument("--timesteps", type=int, default=1500000, help="Total training timesteps.")
    parser.add_argument("--pilot", action="store_true", help="Run Stage 4 Pilot training preset (150,000 steps).")
    parser.add_argument("--n-envs", type=int, default=4, help="Number of vectorized environments (default: 4).")
    parser.add_argument(
        "--vec-env",
        type=str,
        choices=["dummy", "subproc"],
        default="dummy",
        help="Vectorized env backend: 'dummy' (in-process, ~280MB RAM, WSL-safe) or 'subproc' (multiprocess).",
    )
    parser.add_argument("--seed", type=int, default=42, help="Master RNG seed.")
    parser.add_argument("--resume", type=str, default=None, help="Optional checkpoint .zip to resume from.")
    parser.add_argument(
        "--self-play-model",
        type=str,
        default=None,
        help="Optional frozen checkpoint .zip for Self-Play opponents (defaults to --resume checkpoint if omitted).",
    )
    parser.add_argument(
        "--no-self-play",
        action="store_true",
        help="Disable Self-Play AI opponents even when --resume is provided.",
    )
    parser.add_argument(
        "--mask-actions",
        dest="mask_actions",
        action="store_true",
        default=True,
        help="Enable Invalid Action Masking via sb3_contrib.MaskablePPO (default: True).",
    )
    parser.add_argument(
        "--no-mask-actions",
        dest="mask_actions",
        action="store_false",
        help="Disable action masking and train with standard PPO.",
    )
    parser.add_argument("--run-name", type=str, default=None, help="Run directory name under models/.")
    parser.add_argument("--export-gui", action="store_true", default=True, help="Export best/final model to GUI default paths.")
    args = parser.parse_args()

    timesteps = 150000 if (args.pilot and args.timesteps == 1500000) else args.timesteps
    algo_tag = "v8_masked" if args.mask_actions else "v8_unmasked"
    run_name = args.run_name or (f"{algo_tag}_pilot" if args.pilot else f"{algo_tag}_{timesteps // 1000}k")
    run_dir = os.path.join("models", run_name)
    ckpt_dir = os.path.join(run_dir, "checkpoints")
    best_dir = os.path.join(run_dir, "best")
    os.makedirs(ckpt_dir, exist_ok=True)
    os.makedirs(best_dir, exist_ok=True)
    os.makedirs("models/v3_best", exist_ok=True)

    sp_model_path: Optional[str] = None
    if not args.no_self_play:
        candidate_sp = args.self_play_model or args.resume
        if candidate_sp is None:
            # Generation-2: Default to Grandmaster model if available
            default_gm = "models/v7_grandmaster_full/best/best_model.zip"
            if os.path.exists(default_gm):
                candidate_sp = default_gm
        if candidate_sp and os.path.exists(candidate_sp):
            loaded_sp, _ = _get_shared_opponent_model(candidate_sp, 13, 15)
            if loaded_sp is not None:
                # Copy frozen snapshot into run_dir so Self-Play opponent stays stable even if source is overwritten
                frozen_sp_path = os.path.join(run_dir, "frozen_opponent.zip")
                shutil.copy2(candidate_sp, frozen_sp_path)
                sp_model_path = frozen_sp_path
                print(f"🤖 League Self-Play Enabled — Opponent Snapshot: {candidate_sp}", flush=True)
            else:
                print(
                    f"ℹ️ Skipping incompatible Self-Play checkpoint ({candidate_sp} is not 15x13); using BFS/DumbBot opponents for this run.",
                    flush=True,
                )

    seed_everything(args.seed)
    gc.collect()

    env_fns = [
        make_train_env(i, args.seed, args.n_envs, self_play_model_path=sp_model_path)
        for i in range(args.n_envs)
    ]
    if args.vec_env == "subproc" and args.n_envs > 1:
        multiprocessing.set_start_method("spawn", force=True)
        env = SubprocVecEnv(env_fns)
    else:
        env = DummyVecEnv(env_fns)

    # Always keep eval_env in-process via DummyVecEnv (1 env) to save ~1.2 GB of idle worker RAM
    eval_env = DummyVecEnv([make_eval_env(args.seed, self_play_model_path=sp_model_path)])

    policy_kwargs = dict(
        features_extractor_class=BombermanCNN,
        features_extractor_kwargs=dict(features_dim=256),
        net_arch=dict(pi=[128, 64], vf=[128, 64]),
        normalize_images=False,
    )

    if args.mask_actions:
        if args.resume and os.path.exists(args.resume):
            print(f"🔄 Resuming MaskablePPO training from checkpoint: {args.resume}", flush=True)
            model = MaskablePPO.load(
                args.resume,
                env=env,
                device="cpu",
                custom_objects={
                    "BombermanCNN": BombermanCNN,
                    "policy_class": MaskableActorCriticPolicy,
                    "rollout_buffer_class": MaskableRolloutBuffer,
                    "learning_rate": linear_schedule(2.0e-4, 4.0e-5),
                },
                seed=args.seed,
                verbose=0,
            )
        else:
            model = MaskablePPO(
                MaskableActorCriticPolicy,
                env,
                policy_kwargs=policy_kwargs,
                learning_rate=linear_schedule(3.0e-4, 4.0e-5),
                n_steps=512,
                batch_size=256,
                n_epochs=4,
                ent_coef=0.02,
                gamma=0.99,
                gae_lambda=0.95,
                clip_range=0.2,
                max_grad_norm=0.5,
                device="cpu",
                seed=args.seed,
                verbose=0,
            )
        eval_cb_cls = MaskableEvalCallback
    else:
        if args.resume and os.path.exists(args.resume):
            print(f"🔄 Resuming PPO training from checkpoint: {args.resume}", flush=True)
            model = PPO.load(
                args.resume,
                env=env,
                device="cpu",
                custom_objects={
                    "BombermanCNN": BombermanCNN,
                    "learning_rate": linear_schedule(2.0e-4, 4.0e-5),
                },
                seed=args.seed,
                verbose=0,
            )
        else:
            model = PPO(
                "CnnPolicy",
                env,
                policy_kwargs=policy_kwargs,
                learning_rate=linear_schedule(3.0e-4, 4.0e-5),
                n_steps=512,
                batch_size=256,
                n_epochs=4,
                ent_coef=0.02,
                gamma=0.99,
                gae_lambda=0.95,
                clip_range=0.2,
                max_grad_norm=0.5,
                device="cpu",
                seed=args.seed,
                verbose=0,
            )
        eval_cb_cls = EvalCallback

    save_freq_per_env = max(1, (25000 if args.pilot else 100000) // args.n_envs)
    eval_freq_per_env = max(1, (25000 if args.pilot else 75000) // args.n_envs)

    ckpt_cb = CheckpointCallback(
        save_freq=save_freq_per_env,
        save_path=ckpt_dir,
        name_prefix=f"{'maskable_ppo' if args.mask_actions else 'ppo'}_{run_name}",
        save_replay_buffer=False,
    )
    eval_cb = eval_cb_cls(
        eval_env,
        best_model_save_path=best_dir,
        log_path=run_dir,
        eval_freq=eval_freq_per_env,
        n_eval_episodes=8,
        deterministic=True,
        render=False,
        verbose=1,
    )
    metrics_cb = EpisodeMetricsCallback(
        total_timesteps=timesteps,
        log_freq_steps=2048 if args.pilot else 4096,
        history_path=os.path.join(run_dir, "training_metrics.json"),
        verbose=1,
    )

    callbacks = CallbackList([ckpt_cb, eval_cb, metrics_cb])

    algo_name = "MaskablePPO" if args.mask_actions else "PPO"
    print(
        f"🚀 STARTING {algo_name.upper()} TRAINING [{run_name}] — {timesteps:,} timesteps | "
        f"{args.n_envs} envs ({args.vec_env.upper()}) | Seed={args.seed} | ActionMasking={'ON' if args.mask_actions else 'OFF'} | WSL Low-RAM Safe Mode",
        flush=True,
    )
    t0 = time.perf_counter()
    model.learn(
        total_timesteps=timesteps,
        callback=callbacks,
        reset_num_timesteps=not bool(args.resume),
    )
    elapsed = time.perf_counter() - t0

    final_path = os.path.join(run_dir, "final_model.zip")
    model.save(final_path)
    best_model_zip = os.path.join(best_dir, "best_model.zip")

    if args.export_gui:
        source_for_gui = best_model_zip if os.path.exists(best_model_zip) else final_path
        shutil.copy2(source_for_gui, "models/v3_best/best_model.zip")
        shutil.copy2(final_path, "models/ppo_grandmaster_v3.zip")

    env.close()
    eval_env.close()
    print(
        f"✅ Training Complete in {elapsed:.1f}s ({int(timesteps / max(1e-6, elapsed))} fps)! "
        f"Saved final model to {final_path} and best model to {best_model_zip}.",
        flush=True,
    )


if __name__ == "__main__":
    main()
