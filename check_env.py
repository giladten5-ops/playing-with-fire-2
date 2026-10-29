from bomberman_env import BombermanEnv

def main():
    print("1. Creating environment...")
    env = BombermanEnv(board_width=13, board_height=13)

    print("2. Resetting environment...")
    obs, info = env.reset()
    
    # Verify the shape of the observation
    print(f"   Observation shape: {obs.shape}")
    assert obs.shape == (7, 13, 13), "Error: Observation shape is incorrect!"

    print("3. Running 10 random steps...")
    for i in range(10):
        # sample() picks a random valid action (0 to 5)
        action = env.action_space.sample()
        
        # Take a step in the environment
        obs, reward, terminated, truncated, info = env.step(action)
        
        print(f"   Step {i+1}: Action={action}, Reward={reward:.2f}, Terminated={terminated}")

        if terminated:
            print("   Game over! Resetting...")
            env.reset()

    print("4. Environment test passed successfully!")

if __name__ == "__main__":
    main()
