import numpy as np
import gymnasium as gym
from gymnasium import spaces
import airsim
import cv2


class AirSimNavEnv(gym.Env):
    metadata = {"render_modes": []}
    def __init__(self, ip='127.0.0.1', port=41451, vehicle='', frame_stack=4, img_w=160, img_h=120):
        super().__init__()
        self.client = airsim.MultirotorClient(ip=ip, port=port)
        self.client.confirmConnection()
        self.vehicle = vehicle
        self.stack_n = frame_stack
        self.w, self.h = img_w, img_h
        self.obs_stack = None
        self.action_space = spaces.Box(low=np.array([-2.0, -2.0, -60.0], dtype=np.float32),
                                       high=np.array([ 2.0,  2.0,  60.0], dtype=np.float32), dtype=np.float32)
        self.observation_space = spaces.Box(low=0, high=255, shape=(self.stack_n, self.h, self.w, 3), dtype=np.uint8)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        try:
            self.client.enableApiControl(True, vehicle_name=self.vehicle)
            self.client.armDisarm(True, vehicle_name=self.vehicle)
            self.client.takeoffAsync(timeout_sec=10, vehicle_name=self.vehicle).join()
        except Exception:
            pass
        obs = self._get_obs()
        self.obs_stack = np.repeat(obs[None, ...], self.stack_n, axis=0)
        return self.obs_stack, {}

    def step(self, action):
        vx, vy, yaw_rate = float(action[0]), float(action[1]), float(action[2])
        try:
            self.client.moveByVelocityAsync(vx, vy, 0.0, 0.2,
                                            drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                                            yaw_mode=airsim.YawMode(is_rate=True, yaw_or_rate=yaw_rate),
                                            vehicle_name=self.vehicle).join()
        except Exception:
            pass
        obs = self._get_obs()
        self.obs_stack = np.concatenate([self.obs_stack[1:], obs[None, ...]], axis=0)
        reward = 0.01  # step reward
        terminated = False
        truncated = False
        try:
            ci = self.client.simGetCollisionInfo(vehicle_name=self.vehicle)
            if getattr(ci, 'has_collided', False):
                reward -= 1.0
                terminated = True
        except Exception:
            pass
        return self.obs_stack, reward, terminated, truncated, {}

    def _get_obs(self):
        try:
            scene = self.client.simGetImage('0', airsim.ImageType.Scene, vehicle_name=self.vehicle)
            if scene:
                img1d = np.frombuffer(bytearray(scene), dtype=np.uint8)
                rgb = cv2.imdecode(img1d, cv2.IMREAD_COLOR)
                rgb = cv2.resize(rgb, (self.w, self.h), interpolation=cv2.INTER_AREA)
                return rgb
        except Exception:
            pass
        return np.zeros((self.h, self.w, 3), dtype=np.uint8)
