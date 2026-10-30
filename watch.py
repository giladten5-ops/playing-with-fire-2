import time
from stable_baselines3 import PPO
from bomberman_env import BombermanEnv

def render_board(obs):
    """
    Renders the game board directly from the neural network's observation tensor.
    obs shape: (7, height 13, width 13) -> indexed as [channel, y, x]
    Exact channel layout from Game::getState in C++:
    0: Solid Walls (#)
    1: Breakable Walls (B)
    2: Bombs (@)
    3: Flames (*)
    4: PowerUps (?)
    5: Self / Player (P)
    6: Other Players / Enemies (E)
    """
    channels, height, width = obs.shape
    
    print("=" * (width * 3 + 2))
    
    for y in range(height):
        row_str = "|"
        for x in range(width):
            # Render priority: Flames > Players/Bots > Bombs > Walls > PowerUps
            if obs[3, y, x] > 0:
                ch = "*"  # Flame
            elif obs[5, y, x] > 0:
                ch = "P"  # Self (Player 1)
            elif obs[6, y, x] > 0:
                ch = "E"  # Enemy Bot
            elif obs[2, y, x] > 0:
                ch = "@"  # Bomb
            elif obs[1, y, x] > 0:
                ch = "B"  # Breakable Wall
            elif obs[4, y, x] > 0:
                ch = "?"  # PowerUp
            elif obs[0, y, x] > 0:
                ch = "#"  # Solid Wall
            else:
                ch = " "  # Empty space
            row_str += f" {ch} "
        row_str += "|"
        print(row_str)
        
    print("=" * (width * 3 + 2))

def main():
    print("1. Loading Environment...")
    env = BombermanEnv(board_width=13, board_height=13)

    print("2. Loading Trained Model...")
    model = PPO.load("ppo_bomberman_v1")

    print("3. Starting the game...")
    obs, info = env.reset()
    
    terminated = False
    step_count = 0
    
    while not terminated:
        print("\033[H\033[J", end="")
        
        # Predict the best action deterministically
        action, _states = model.predict(obs, deterministic=True)
        action = int(action.item())
        
        # Step the environment
        obs, reward, terminated, truncated, info = env.step(action)
        step_count += 1
        
        # Render the board
        render_board(obs)
        print(f"Step: {step_count} | Action chosen: {action} | Reward: {reward:.2f}")
        
        time.sleep(0.15)

    print("Game Over!")

if __name__ == "__main__":
    main()
