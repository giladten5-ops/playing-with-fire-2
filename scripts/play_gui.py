#!/usr/bin/env python3
"""Playing with Fire 2 — Pygame GUI Entry Point.

Supports normal interactive play (Main Menu wizard) and direct 1v1 AI Duel mode:
  ./venv/bin/python play_gui.py          # Normal interactive game
  ./venv/bin/python play_gui.py --duel   # Spectate v8 (Masked PPO) vs v7 (Grandmaster)
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gui.app import BombermanGUIApp


def main():
    parser = argparse.ArgumentParser(description="Playing with Fire 2 — Pygame GUI")
    parser.add_argument(
        "--duel",
        action="store_true",
        help="Launch directly in 1v1 AI Duel mode: v8 (Masked PPO) vs v7 (Grandmaster).",
    )
    parser.add_argument("--p1-model", type=str, default=None, help="Custom model path for Player 1 (Blue).")
    parser.add_argument("--p2-model", type=str, default=None, help="Custom model path for Player 2 (Red).")
    args = parser.parse_args()

    app = BombermanGUIApp(
        duel_mode=args.duel,
        p1_model_path=args.p1_model,
        p2_model_path=args.p2_model,
    )
    app.run()


if __name__ == "__main__":
    main()