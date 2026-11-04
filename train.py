import os
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import SubprocVecEnv
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.callbacks import EvalCallback
from bomberman_env import BombermanEnv, BombermanCNN

def make_env(rank: int):
    def _init():
        num_bots = 1 if rank < 2 else 2 if rank < 4 else 3
        density = 45 if rank < 2 else 55 if rank < 4 else 65
        return Monitor(BombermanEnv(num_bots=num_bots, wall_density=density), info_keywords=("is_success", "win"))
    return _init

def linear_schedule(initial_value: float, final_value: float = 5e-5):
    return lambda progress_remaining: final_value + progress_remaining * (initial_value - final_value)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)
    os.makedirs("models/v3_best", exist_ok=True)
    env = SubprocVecEnv([make_env(i) for i in range(8)])
    eval_env = SubprocVecEnv([lambda: Monitor(BombermanEnv(num_bots=3, wall_density=65), info_keywords=("is_success", "win"))])
    
    policy_kwargs = dict(features_extractor_class=BombermanCNN, features_extractor_kwargs=dict(features_dim=256), net_arch=dict(pi=[128, 64], vf=[128, 64]), normalize_images=False)
    
    model = PPO("CnnPolicy", env, policy_kwargs=policy_kwargs, learning_rate=linear_schedule(3e-4, 5e-5), n_steps=512, batch_size=256, n_epochs=4, ent_coef=0.02, gamma=0.99, verbose=1)
    
    eval_cb = EvalCallback(eval_env, best_model_save_path="./models/v3_best/", eval_freq=2500, n_eval_episodes=5, deterministic=True, render=False)
    
    print("🚀 STARTING GRANDMASTER V3 FULL TRAINING (600,000 steps)...")
    model.learn(total_timesteps=600000, callback=eval_cb)
    model.save("models/ppo_grandmaster_v3")
    print("✅ Training Complete!")
