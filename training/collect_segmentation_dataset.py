import argparse
from pathlib import Path
import time
from typing import Tuple
import numpy as np
import cv2
import airsim


def ensure_dirs(root: Path, split: str):
    img_dir = root / split / "images"
    msk_dir = root / split / "masks"
    img_dir.mkdir(parents=True, exist_ok=True)
    msk_dir.mkdir(parents=True, exist_ok=True)
    return img_dir, msk_dir


def color_to_id_mask(colored_mask: np.ndarray) -> np.ndarray:
    if colored_mask.ndim == 2:
        return colored_mask
    r, g, b = colored_mask[..., 0], colored_mask[..., 1], colored_mask[..., 2]
    ids = (r.astype(np.int32) << 16) + (g.astype(np.int32) << 8) + b.astype(np.int32)
    return ids


def capture_pair(client: airsim.MultirotorClient, camera_name: str = "0") -> Tuple[np.ndarray, np.ndarray]:
    reqs = [
        airsim.ImageRequest(camera_name, airsim.ImageType.Scene, pixels_as_float=False, compress=False),
        airsim.ImageRequest(camera_name, airsim.ImageType.Segmentation, pixels_as_float=False, compress=False),
    ]
    resp = client.simGetImages(reqs)
    if len(resp) != 2:
        raise RuntimeError("Did not receive both scene and segmentation images")
    img1d = np.frombuffer(resp[0].image_data_uint8, dtype=np.uint8)
    rgb = img1d.reshape(resp[0].height, resp[0].width, 3)
    seg1d = np.frombuffer(resp[1].image_data_uint8, dtype=np.uint8)
    seg_rgb = seg1d.reshape(resp[1].height, resp[1].width, 3)
    return rgb, seg_rgb


def main():
    parser = argparse.ArgumentParser(description="Collect RGB+Seg dataset from AirSim")
    parser.add_argument("--out", type=str, default="dataset")
    parser.add_argument("--split", type=str, default="train", choices=["train", "val", "test"])
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--move", action="store_true")
    parser.add_argument("--altitude", type=float, default=-5.0)
    parser.add_argument("--sleep", type=float, default=0.05)
    args = parser.parse_args()

    root = Path(args.out)
    img_dir, msk_dir = ensure_dirs(root, args.split)

    client = airsim.MultirotorClient()
    client.confirmConnection()
    client.enableApiControl(True)
    client.armDisarm(True)
    client.takeoffAsync(timeout_sec=10).join()
    client.moveToZAsync(args.altitude, 2).join()

    try:
        for i in range(args.count):
            if args.move and i % 10 == 0:
                vx = 2.0 if (i // 10) % 2 == 0 else -2.0
                client.moveByVelocityAsync(vx, 0, 0, 1.0)
            rgb, seg_rgb = capture_pair(client)
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            seg_ids = color_to_id_mask(seg_rgb)
            cv2.imwrite(str(img_dir / f"frame_{i:06d}.png"), bgr)
            if seg_ids.max() < 65535:
                cv2.imwrite(str(msk_dir / f"frame_{i:06d}.png"), seg_ids.astype(np.uint16))
            else:
                cv2.imwrite(str(msk_dir / f"frame_{i:06d}.png"), cv2.cvtColor(seg_rgb, cv2.COLOR_RGB2BGR))
            if (i + 1) % 50 == 0:
                print(f"Captured {i + 1}/{args.count}")
            time.sleep(args.sleep)
    finally:
        client.hoverAsync().join()
        client.landAsync().join()
        client.armDisarm(False)
        client.enableApiControl(False)


if __name__ == "__main__":
    main()
