import argparse
from collections import deque
import time
from pathlib import Path
import numpy as np
import cv2
import torch
import airsim
from training.models.vision_nav import VisionNavCNNLSTM


def preprocess(rgb, w=160, h=120):
    rgb = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_AREA)
    x = (rgb[:, :, ::-1].astype(np.float32) / 255.0).transpose(2, 0, 1)
    return x


def main():
    ap = argparse.ArgumentParser(description='Run trained CNN+LSTM navigation model in AirSim')
    ap.add_argument('--ip', type=str, default='127.0.0.1')
    ap.add_argument('--port', type=int, default=41451)
    ap.add_argument('--vehicle', type=str, default='')
    ap.add_argument('--model', type=str, required=True)
    ap.add_argument('--seq_len', type=int, default=4)
    ap.add_argument('--hz', type=float, default=5.0)
    ap.add_argument('--z_hold', action='store_true')
    ap.add_argument('--alt', type=float, default=-4.0)
    args = ap.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = VisionNavCNNLSTM(in_ch=3, hidden=128, lstm_hidden=128, out_dim=3)
    sd = torch.load(args.model, map_location=device)
    model.load_state_dict(sd)
    model.to(device).eval()

    client = airsim.MultirotorClient(ip=args.ip, port=args.port)
    client.confirmConnection()
    client.enableApiControl(True, vehicle_name=args.vehicle)
    client.armDisarm(True, vehicle_name=args.vehicle)
    try:
        client.takeoffAsync(timeout_sec=10, vehicle_name=args.vehicle).join()
        client.moveToZAsync(float(args.alt), 2.0, vehicle_name=args.vehicle).join()
    except Exception:
        pass

    buf = deque(maxlen=args.seq_len)
    dt = 1.0 / max(1e-3, args.hz)
    try:
        while True:
            t0 = time.time()
            scene = client.simGetImage('0', airsim.ImageType.Scene, vehicle_name=args.vehicle)
            if not scene:
                time.sleep(dt)
                continue
            img1d = np.frombuffer(bytearray(scene), dtype=np.uint8)
            rgb = cv2.imdecode(img1d, cv2.IMREAD_COLOR)
            if rgb is None:
                time.sleep(dt)
                continue
            x = preprocess(rgb)
            buf.append(x)
            if len(buf) < buf.maxlen:
                time.sleep(dt)
                continue
            inp = torch.from_numpy(np.stack(list(buf), axis=0)[None, ...]).to(device)
            with torch.no_grad():
                act = model(inp).cpu().numpy()[0]
            vx, vy, yaw_rate = float(act[0]), float(act[1]), float(act[2])
            cmd_dur = dt
            try:
                if args.z_hold:
                    client.moveByVelocityZAsync(vx, vy, float(args.alt), cmd_dur,
                                                drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                                                yaw_mode=airsim.YawMode(is_rate=True, yaw_or_rate=yaw_rate),
                                                vehicle_name=args.vehicle).join()
                else:
                    client.moveByVelocityAsync(vx, vy, 0.0, cmd_dur,
                                               drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
                                               yaw_mode=airsim.YawMode(is_rate=True, yaw_or_rate=yaw_rate),
                                               vehicle_name=args.vehicle).join()
            except Exception:
                pass
            rem = dt - (time.time() - t0)
            if rem > 0:
                time.sleep(rem)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            client.hoverAsync().join()
            client.landAsync(vehicle_name=args.vehicle).join()
        except Exception:
            pass
        try:
            client.armDisarm(False)
            client.enableApiControl(False)
        except Exception:
            pass


if __name__ == '__main__':
    main()
