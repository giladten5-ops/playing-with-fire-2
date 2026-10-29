import gymnasium as gym
import numpy as np
from gymnasium import spaces
import bomberman_engine as bme

class BombermanEnv(gym.Env):
    """
    Custom Environment that follows the standard Gymnasium interface.
    This acts as a bridge between the RL algorithm (PPO) and our C++ game engine.
    """
    
    def __init__(self, board_width=13, board_height=13):
        super().__init__()
        
        self.width = board_width
        self.height = board_height
        
        # Initialize the C++ game engine
        self.game = bme.Game(self.width, self.height)
        
        # Action Space: 6 discrete actions (0 to 5)
        # 0=NONE, 1=UP, 2=DOWN, 3=LEFT, 4=RIGHT, 5=PLACE_BOMB
        self.action_space = spaces.Discrete(6)
        
        # Observation Space: A 3D tensor of shape (Channels, Width, Height)
        # We use 7 channels with boolean-like values (0.0 or 1.0)
        self.observation_space = spaces.Box(
            low=0.0, 
            high=1.0, 
            shape=(7, self.width, self.height), 
            dtype=np.float32
        )
        
        # Dictionary mapping python integers to C++ Command Enums
        self.action_mapping = {
            0: bme.Command.NONE,
            1: bme.Command.UP,
            2: bme.Command.DOWN,
            3: bme.Command.LEFT,
            4: bme.Command.RIGHT,
            5: bme.Command.PLACE_BOMB
        }

    def _get_obs(self):
        """
        Helper method to retrieve the state from C++ and shape it correctly.
        """
        # Call the C++ getState function for Player 1
        # It returns a flat std::vector<float> of size 1183 (7 * 13 * 13)
        flat_state = self.game.getState(1)
        
        # Convert the flat list to a numpy array and reshape it to 3D
        obs = np.array(flat_state, dtype=np.float32).reshape((7, self.width, self.height))
        return obs

    def step(self, action):
        """
        Executes one time step within the environment.
        """
        # Convert the chosen action (int) to the C++ Command
        cpp_command = self.action_mapping[action]
        
        # Call step on the C++ engine
        result = self.game.step(1, cpp_command)
        
        # Retrieve the new state
        obs = self._get_obs()
        
        # Determine if the episode ended
        terminated = result.isDone
        truncated = False # We don't use artificial time limits for truncation yet
        
        # Gymnasium requires an info dictionary, we can leave it empty
        info = {}
        
        return obs, result.reward, terminated, truncated, info

    def reset(self, seed=None, options=None):
        """
        Resets the environment to start a new episode.
        """
        # We must call super().reset to seed the internal RNG if a seed is provided
        super().reset(seed=seed)
        
        # Create a new classic level: 1 Human (Model), 3 Bots
        level = bme.ClassicLevel(4, self.width, self.height)
        
        # Reset the C++ game with the new level
        self.game.reset(level, 1, 3)
        
        # Get the initial observation for the new game
        obs = self._get_obs()
        info = {}
        
        return obs, info
