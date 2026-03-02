import numpy as np
import gymnasium as gym
from gymnasium import spaces
from sb3_contrib import RecurrentPPO


class Dummy(gym.Env):
    def __init__(self):
        super().__init__()
        self.observation_space = spaces.Dict(
            {
                "visual": spaces.Box(0.0, 1.0, shape=(1, 64, 64), dtype=np.float32),
                "kinematics": spaces.Box(-np.inf, np.inf, shape=(19,), dtype=np.float32),
            }
        )
        self.action_space = spaces.Box(-1.0, 1.0, shape=(4,), dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        obs = {
            "visual": np.zeros((1, 64, 64), dtype=np.float32),
            "kinematics": np.zeros((19,), dtype=np.float32),
        }
        return obs, {}

    def step(self, action):
        obs, info = self.reset()
        return obs, 0.0, True, False, info


env = Dummy()
model = RecurrentPPO("MultiInputLstmPolicy", env, verbose=0)
policy = model.policy
s = policy.initial_state(3)
print("initial_state type:", type(s))
print("has pi/vf:", hasattr(s, "pi"), hasattr(s, "vf"))
print("pi type:", type(s.pi))
print("vf type:", type(s.vf))
print("pi[0] shape:", getattr(s.pi[0], "shape", None))
print("pi[1] shape:", getattr(s.pi[1], "shape", None))
print("vf[0] shape:", getattr(s.vf[0], "shape", None))
print("vf[1] shape:", getattr(s.vf[1], "shape", None))
