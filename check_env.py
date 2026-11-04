from bomberman_env import BombermanEnv


def main():
    print("1. Creating environment...")
    env = BombermanEnv(board_width=13, board_height=13)

    print("2. Resetting environment...")
    obs, info = env.reset(seed=42)

    print(f"   Observation shape: {obs.shape}")
    assert obs.shape == (8, 13, 13), f"Error: Expected (8, 13, 13), got {obs.shape}!"

    print("3. Running 10 random steps...")
    for i in range(10):
        action = env.action_space.sample()
        obs, reward, terminated, truncated, info = env.step(action)
        print(f"   Step {i+1}: Action={action}, Reward={reward:.2f}, Terminated={terminated}, Truncated={truncated}")

        if terminated or truncated:
            print("   Episode ended! Resetting...")
            env.reset()

    print("4. Environment test passed successfully!")


if __name__ == "__main__":
    main()
