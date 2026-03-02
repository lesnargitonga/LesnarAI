import argparse
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from training.airsim_env import AirSimNavEnv


def make_env(ip, port, vehicle):
    def _f():
        return AirSimNavEnv(ip=ip, port=port, vehicle=vehicle)
    return _f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ip', type=str, default='127.0.0.1')
    ap.add_argument('--port', type=int, default=41451)
    ap.add_argument('--vehicle', type=str, default='')
    ap.add_argument('--steps', type=int, default=10000)
    ap.add_argument('--out', type=str, default='models/ppo_airsim')
    args = ap.parse_args()

    env = DummyVecEnv([make_env(args.ip, args.port, args.vehicle)])
    model = PPO('MlpPolicy', env, verbose=1)
    model.learn(total_timesteps=args.steps)
    model.save(args.out)


if __name__ == '__main__':
    main()
