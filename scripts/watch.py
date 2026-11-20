import os, sys, time
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from stable_baselines3 import PPO
from rl.bomberman_env import BombermanEnv, BombermanCNN

def render_board(obs):
    channels, height, width = obs.shape
    print("=" * (width * 3 + 2))
    for y in range(height):
        row_str = "|"
        for x in range(width):
            if obs[4,y,x]>0: ch = "*"
            elif obs[6,y,x]>0: ch = "P"
            elif obs[7,y,x]>0: ch = "E"
            elif obs[2,y,x]>0: ch = "@"
            elif obs[1,y,x]>0: ch = "B"
            elif obs[5,y,x]>0: ch = "?"
            elif obs[0,y,x]>0: ch = "#"
            elif obs[3,y,x]>0: ch = "."
            else: ch = " "
            row_str += f" {ch} "
        row_str += "|"
        print(row_str)
    print("=" * (width * 3 + 2))

if __name__ == "__main__":
    env = BombermanEnv()
    model = None
    for path in ["models/v3_best/best_model", "models/ppo_grandmaster_v3"]:
        try:
            from sb3_contrib import MaskablePPO
            model = MaskablePPO.load(path, custom_objects={"BombermanCNN": BombermanCNN})
            break
        except Exception:
            try:
                model = PPO.load(path, custom_objects={"BombermanCNN": BombermanCNN})
                break
            except Exception:
                continue
    obs, _ = env.reset()
    done = False
    while not done:
        print("\033[H\033[J", end="")
        if model is not None:
            try:
                action, _ = model.predict(obs, action_masks=env.action_masks(), deterministic=True)
            except TypeError:
                action, _ = model.predict(obs, deterministic=True)
        else:
            action = 0
        obs, rew, term, trunc, _ = env.step(action)
        done = term or trunc
        render_board(obs)
        st = env.ep_stats
        print(f"Grandmaster | Rew: {rew:+.2f} | Kills: {st['kills']} | Bombs: {st['bombs_placed']} | Walls: {st['walls_destroyed']}")
        time.sleep(0.12)
