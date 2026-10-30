import os
from stable_baselines3 import PPO
from bomberman_env import BombermanEnv

def main():
    print("1. Initializing the Bomberman Environment...")
    env = BombermanEnv(board_width=13, board_height=13)

    print("2. Initializing the PPO model...")

    model = PPO(
        policy="MlpPolicy",
        env=env,
        verbose=1,
        learning_rate=3e-4,
        n_steps=2048,
        ent_coef=0.01,
    )

    total_timesteps = 1000000
    print(f"3. Starting training for {total_timesteps} timesteps...")
    model.learn(total_timesteps=total_timesteps)

    print("4. Training completed. Saving the model...")
    model.save("ppo_bomberman_v1")
    print("5. Model saved as 'ppo_bomberman_v1.zip'.")
if __name__ == "__main__":
    main()