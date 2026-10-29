import sys
import bomberman_engine as bme

def main():
    print("1. Successfully imported the C++ engine!")

    # Create the game engine (13x13 board)
    game = bme.Game(13, 13)
    print("2. Game engine instance created.")

    # Create the classic level with 1 human player and 3 bots
    level = bme.ClassicLevel(4, 13, 13)
    
    # Reset the game with the level
    game.reset(level, 1, 3)
    print("3. Game reset successfully.")

    # Get the state for Player 1 (the human)
    state = game.getState(1)
    
    # State should be 7 channels * 13 * 13 = 1183 floats
    print(f"4. State vector received! Length: {len(state)}")
    
    # Step the game forward by doing nothing
    result = game.step(1, bme.Command.NONE)
    print(f"5. Step executed. isDone: {result.isDone}, reward: {result.reward}")

if __name__ == "__main__":
    main()
