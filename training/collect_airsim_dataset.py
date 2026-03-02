import argparse
from pathlib import Path
import time
import json
import cv2
import numpy as np
import airsim


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def main():
    ap = argparse.ArgumentParser(description='Collect synthetic dataset from AirSim: RGB + Depth + Pose')
    ap.add_argument('--ip', type=str, default='127.0.0.1')
    ap.add_argument('--port', type=int, default=41451)
    ap.add_argument('--vehicle', type=str, default='')
    ap.add_argument('--cams', type=str, nargs='+', default=['0'])
    ap.add_argument('--duration', type=float, default=60.0)
    ap.add_argument('--hz', type=float, default=5.0)
    ap.add_argument('--out', type=str, required=True)
    args = ap.parse_args()

    out_root = Path(args.out)
    ensure_dir(out_root / 'rgb')
    ensure_dir(out_root / 'depth')

    client = airsim.MultirotorClient(ip=args.ip, port=args.port)
    client.confirmConnection()
    client.enableApiControl(True, vehicle_name=args.vehicle)
    client.armDisarm(True, vehicle_name=args.vehicle)
    try:
        client.takeoffAsync(timeout_sec=10, vehicle_name=args.vehicle).join()
    except Exception:
        pass

    start = time.time()
    dt = 1.0 / max(1e-3, args.hz)
    i = 0
    poses = []
    while (time.time() - start) < float(args.duration):
        t0 = time.time()
        # Collect from first cam only for simplicity
        cam = str(args.cams[0])
        reqs = [
            airsim.ImageRequest(cam, airsim.ImageType.Scene, pixels_as_float=False, compress=False),
            airsim.ImageRequest(cam, airsim.ImageType.DepthPerspective, pixels_as_float=True, compress=False),
        ]
        try:
            resp = client.simGetImages(reqs, vehicle_name=args.vehicle)
            if not resp or len(resp) < 2:
                time.sleep(dt)
                continue
            scene = resp[0]
            depth = resp[1]
            if scene.width <= 0 or depth.width <= 0:
                time.sleep(dt)
                continue
            rgb = np.frombuffer(scene.image_data_uint8, dtype=np.uint8).reshape(scene.height, scene.width, 3)
            d = np.array(depth.image_data_float, dtype=np.float32).reshape(depth.height, depth.width)
            # Save
            cv2.imwrite(str(out_root / 'rgb' / f"{i:06d}.png"), rgb[:, :, ::-1])
            dep_dm = np.clip(d * 10.0, 0, 65535).astype(np.uint16)
            cv2.imwrite(str(out_root / 'depth' / f"{i:06d}.png"), dep_dm)
            # Pose
            try:
                st = client.getMultirotorState(vehicle_name=args.vehicle)
                pos = st.kinematics_estimated.position
                ori = st.kinematics_estimated.orientation
                poses.append({
                    "frame": i,
                    "t": time.time(),
                    "position": {"x": pos.x_val, "y": pos.y_val, "z": pos.z_val},
                    "orientation": {"w": ori.w_val, "x": ori.x_val, "y": ori.y_val, "z": ori.z_val}
                })
            except Exception:
                pass
            i += 1
        except Exception:
            pass
        # pace
        rem = dt - (time.time() - t0)
        if rem > 0:
            time.sleep(rem)

    with open(out_root / 'poses.json', 'w', encoding='utf-8') as f:
        json.dump({"frames": poses}, f)

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
