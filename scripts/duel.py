#!/usr/bin/env python3
"""Head-to-head AI Duel Suite: v8 (Masked PPO) vs v7 (Grandmaster PPO).

Supports three modes:
1. Pygame GUI Spectator Mode:
   ./venv/bin/python duel.py --gui
   (or: make duel)
   Launches the full 60 FPS retro graphical window in 1v1 spectator duel mode.
   Hotkeys:
     P / Space : Pause / Resume
     N         : Step single tick forward (frame-by-frame analysis)
     H / F2    : Live BFS debug heatmap & action probabilities overlay
     R / F5    : Restart match with a fresh random seed
     Esc       : Return / Exit

2. Terminal ASCII Live Spectator Mode:
   ./venv/bin/python duel.py
   (or: ./venv/bin/python duel.py --cli --speed 0.05)
   Streams live tick-by-tick animated matches directly in your terminal.

3. Statistical Head-to-Head Tournament:
   ./venv/bin/python duel.py --tournament 20
   Simulates N full games head-to-head and prints comprehensive win/kill/push statistics.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Dict, Optional, Tuple

import numpy as np

# Low-RAM / WSL thread caps
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("TORCH_NUM_THREADS", "1")

from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import bomberman_engine as bme
from rl.bomberman_env import BombermanCNN
from gui.controllers import PPOAgentController
from gui.engine_adapter import CppGameSession


DEFAULT_V8_PATH = "models/v11_clean_cnn_1500k/best/best_model.zip"
DEFAULT_V7_PATH = "models/v10_15x13_selfplay/best/best_model.zip"


def load_model(path: str):
    """Loads either a MaskablePPO or standard PPO model checkpoint."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model checkpoint not found: {path}")
    try:
        from sb3_contrib import MaskablePPO
        return MaskablePPO.load(path, device="cpu", custom_objects={"BombermanCNN": BombermanCNN})
    except Exception:
        from stable_baselines3 import PPO
        return PPO.load(path, device="cpu", custom_objects={"BombermanCNN": BombermanCNN})


def render_ascii_board(
    session: CppGameSession,
    p1_info: Dict[str, int],
    p2_info: Dict[str, int],
    tick: int,
    p1_name: str = "v8 (Masked)",
    p2_name: str = "v7 (Grandmaster)",
) -> str:
    """Renders a colorized ASCII board representing the live C++ engine state."""
    base_obs = session.get_rl_base_observation(1)
    channels, height, width = base_obs.shape

    lines = []
    lines.append("╔" + "═" * (width * 3 + 2) + "╗")
    header_title = f" AI DUEL: \033[94mP1 {p1_name}\033[0m VS \033[91mP2 {p2_name}\033[0m "
    lines.append(f"║ {header_title:<{width * 3 + 18}}║")
    sd_active = session._game.isSuddenDeathActive()
    sd_timer = session._game.getSuddenDeathTimer()
    timer_str = f"Tick: {tick:04d} | SD: {'ACTIVE!' if sd_active else f'{sd_timer // 30}s'}"
    lines.append(f"║ {timer_str:<{width * 3}} ║")
    lines.append("╠" + "═" * (width * 3 + 2) + "╣")

    for y in range(height):
        row = "║ "
        for x in range(width):
            # 2: P1, 7: P2, 4: Flames, 1: Bombs, 0: Solid Wall, 3: Soft Wall, 6: Powerup
            if base_obs[2, y, x] > 0 and base_obs[7, y, x] > 0:
                cell = "\033[95m!X\033[0m" # Both players on same tile
            elif base_obs[2, y, x] > 0:
                cell = "\033[94;1m8 \033[0m" # P1 (Blue)
            elif base_obs[7, y, x] > 0:
                cell = "\033[91;1m7 \033[0m" # P2 (Red)
            elif base_obs[4, y, x] > 0:
                cell = "\033[93;1m**\033[0m" # Flame
            elif base_obs[1, y, x] > 0:
                cell = "\033[91m@@\033[0m" # Bomb
            elif base_obs[6, y, x] > 0:
                cell = "\033[92m? \033[0m" # PowerUp
            elif base_obs[0, y, x] > 0:
                cell = "\033[90m██\033[0m" # Solid Wall
            elif base_obs[3, y, x] > 0:
                cell = "\033[33m▒▒\033[0m" # Breakable Wall
            else:
                cell = "  "
            row += cell + " "
        row += "║"
        lines.append(row)

    lines.append("╠" + "═" * (width * 3 + 2) + "╣")
    p1_status = "\033[92mALIVE\033[0m" if p1_info["is_alive"] else "\033[91mDEAD\033[0m"
    p2_status = "\033[92mALIVE\033[0m" if p2_info["is_alive"] else "\033[91mDEAD\033[0m"
    lines.append(f"║ \033[94mP1 (v8)\033[0m: {p1_status} (pos: {p1_info['x']},{p1_info['y']} | Bombs: {p1_info['avail_bombs']})")
    lines.append(f"║ \033[91mP2 (v7)\033[0m: {p2_status} (pos: {p2_info['x']},{p2_info['y']} | Bombs: {p2_info['avail_bombs']})")
    lines.append("╚" + "═" * (width * 3 + 2) + "╝")
    return "\n".join(lines)


def run_cli_spectator(
    p1_path: str,
    p2_path: str,
    wall_density: int = 55,
    sudden_death_ticks: int = 450,
    speed: float = 0.05,
    temperature: float = 0.2,
) -> None:
    """Runs a single live animated duel in the terminal."""
    print("Loading models for terminal duel...")
    m1 = load_model(p1_path)
    m2 = load_model(p2_path)

    session = CppGameSession(wall_density=wall_density)
    session.reset(num_human=1, num_bots=1, trained_ai_bots=1)
    if sudden_death_ticks:
        session._game.setSuddenDeathTimer(sudden_death_ticks)

    ctrl1 = PPOAgentController(player_id=1, shared_model=m1, lazy=True, temperature=temperature)
    ctrl2 = PPOAgentController(player_id=2, shared_model=m2, lazy=True, temperature=temperature)

    print("\033[H\033[J", end="")
    tick = 0
    max_ticks = 1800
    while tick < max_ticks and not session.is_game_over():
        cmd1 = ctrl1.get_command(session)
        cmd2 = ctrl2.get_command(session)
        session.step_tick(cmd1, extra_actions={2: cmd2})
        tick += 1

        p1_state = session.get_player_tactical_state(1)
        p2_state = session.get_player_tactical_state(2)

        output = render_ascii_board(session, p1_state, p2_state, tick)
        print("\033[H" + output, flush=True)
        time.sleep(speed)

    p1_final = session.get_player_tactical_state(1)
    p2_final = session.get_player_tactical_state(2)
    print("\n" + "=" * 45)
    if p1_final["is_alive"] and not p2_final["is_alive"]:
        print("🏆 MATCH RESULT: \033[94mPLAYER 1 (v8 MASKED PPO) VICTORIOUS!\033[0m")
    elif p2_final["is_alive"] and not p1_final["is_alive"]:
        print("🏆 MATCH RESULT: \033[91mPLAYER 2 (v7 GRANDMASTER) VICTORIOUS!\033[0m")
    else:
        print("🤝 MATCH RESULT: DRAW (STALEMATE / TIMEOUT)")
    print(f"Total Ticks: {tick} ({tick / 30:.1f}s)")
    print("=" * 45)


def run_tournament(
    p1_path: str,
    p2_path: str,
    num_games: int = 20,
    wall_density: int = 55,
    sudden_death_ticks: int = 450,
    temperature: float = 0.2,
) -> None:
    """Runs a batch head-to-head tournament and aggregates win/loss statistics."""
    print(f"\n{'=' * 75}")
    print(f"RUNNING AI DUEL TOURNAMENT: {num_games} GAMES")
    print(f"Player 1 (Blue): {p1_path} [Gen-2 MaskablePPO]")
    print(f"Player 2 (Red):  {p2_path} [Gen-1 Grandmaster PPO]")
    print(f"Wall Density: {wall_density}% | Sudden Death Ticks: {sudden_death_ticks}")
    print(f"{'=' * 75}\n")

    m1 = load_model(p1_path)
    m2 = load_model(p2_path)

    stats = {
        "p1_wins": 0,
        "p2_wins": 0,
        "draws": 0,
        "total_ticks": 0,
    }

    t0 = time.perf_counter()
    header = f"{'Game':<6} | {'Winner':<22} | {'Ticks':>6} | {'Time (s)':>8} | {'P1 Status':>10} | {'P2 Status':>10}"
    print(header)
    print("-" * len(header))

    for g in range(1, num_games + 1):
        session = CppGameSession(wall_density=wall_density)
        bme.seed_rng(int(20000 + g * 101) & 0xFFFFFFFF)
        session.reset(num_human=1, num_bots=1, trained_ai_bots=1)
        if sudden_death_ticks:
            session._game.setSuddenDeathTimer(sudden_death_ticks)

        ctrl1 = PPOAgentController(player_id=1, shared_model=m1, lazy=True, temperature=temperature)
        ctrl2 = PPOAgentController(player_id=2, shared_model=m2, lazy=True, temperature=temperature)

        tick = 0
        max_ticks = 1800
        while tick < max_ticks and not session.is_game_over():
            cmd1 = ctrl1.get_command(session)
            cmd2 = ctrl2.get_command(session)
            session.step_tick(cmd1, extra_actions={2: cmd2})
            tick += 1

        stats["total_ticks"] += tick
        p1 = session.get_player_tactical_state(1)
        p2 = session.get_player_tactical_state(2)

        if p1["is_alive"] and not p2["is_alive"]:
            stats["p1_wins"] += 1
            winner_str = "P1 (v8 Masked)"
        elif p2["is_alive"] and not p1["is_alive"]:
            stats["p2_wins"] += 1
            winner_str = "P2 (v7 Grandmaster)"
        else:
            stats["draws"] += 1
            winner_str = "Draw / Timeout"

        p1_st = "Alive" if p1["is_alive"] else "Dead"
        p2_st = "Alive" if p2["is_alive"] else "Dead"
        print(f"#{g:<5} | {winner_str:<22} | {tick:6d} | {tick / 30:8.1f} | {p1_st:>10} | {p2_st:>10}")

    elapsed = time.perf_counter() - t0
    print("-" * len(header))
    p1_pct = (stats["p1_wins"] / num_games) * 100.0
    p2_pct = (stats["p2_wins"] / num_games) * 100.0
    draw_pct = (stats["draws"] / num_games) * 100.0
    print(f"\nFINAL TOURNAMENT SCORE ACROSS {num_games} MATCHES ({elapsed:.1f}s):")
    print(f"  * P1 (v8 MaskablePPO)  Wins : {stats['p1_wins']:>3d} / {num_games} ({p1_pct:5.1f}%)")
    print(f"  * P2 (v7 Grandmaster)  Wins : {stats['p2_wins']:>3d} / {num_games} ({p2_pct:5.1f}%)")
    print(f"  * Draws / Timeouts          : {stats['draws']:>3d} / {num_games} ({draw_pct:5.1f}%)")
    print(f"  * Avg Match Length          : {stats['total_ticks'] / num_games:.1f} ticks ({(stats['total_ticks'] / num_games) / 30:.1f}s)")
    print(f"{'=' * 75}\n")


def main():
    parser = argparse.ArgumentParser(description="Head-to-head AI Duel Suite: v8 (Masked PPO) vs v7 (Grandmaster)")
    parser.add_argument("--gui", action="store_true", help="Launch interactive 60 FPS Pygame GUI spectator window.")
    parser.add_argument("--cli", action="store_true", help="Run live animated ASCII terminal spectator match.")
    parser.add_argument("--tournament", type=int, default=None, help="Run an automated N-game tournament and print statistics.")
    parser.add_argument("--speed", type=float, default=0.04, help="Playback speed for terminal ASCII mode (seconds per tick).")
    parser.add_argument("--temperature", type=float, default=0.2, help="Softmax sampling temperature for AI actions (default: 0.2, 0.0 = greedy argmax).")
    parser.add_argument("--walls", type=int, default=55, help="Wall density percentage (default: 55).")
    parser.add_argument("--sudden-death", type=int, default=450, help="Ticks before Sudden Death starts (default: 450 = 15s).")
    parser.add_argument("--p1", type=str, default=DEFAULT_V8_PATH, help="Checkpoint for Player 1 (v8 MaskablePPO).")
    parser.add_argument("--p2", type=str, default=DEFAULT_V7_PATH, help="Checkpoint for Player 2 (v7 Grandmaster).")
    args = parser.parse_args()

    if args.gui:
        from gui.app import BombermanGUIApp
        app = BombermanGUIApp(
            duel_mode=True,
            p1_model_path=args.p1,
            p2_model_path=args.p2,
        )
        app.run()
    elif args.tournament is not None and args.tournament > 0:
        run_tournament(
            p1_path=args.p1,
            p2_path=args.p2,
            num_games=args.tournament,
            wall_density=args.walls,
            sudden_death_ticks=args.sudden_death,
            temperature=args.temperature,
        )
    else:
        # Default: Terminal ASCII live match
        run_cli_spectator(
            p1_path=args.p1,
            p2_path=args.p2,
            wall_density=args.walls,
            sudden_death_ticks=args.sudden_death,
            speed=args.speed,
            temperature=args.temperature,
        )


if __name__ == "__main__":
    main()

