import argparse
import json
from pathlib import Path
import shutil
import cv2
import numpy as np
from tqdm import tqdm


def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)


def resize_and_pad(img, target_wh):
    tw, th = target_wh
    h, w = img.shape[:2]
    scale = min(tw / w, th / h)
    nw, nh = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((th, tw, img.shape[2] if img.ndim == 3 else 1), dtype=img.dtype)
    y0 = (th - nh) // 2
    x0 = (tw - nw) // 2
    canvas[y0:y0+nh, x0:x0+nw] = resized
    return canvas


def uniform_fps_indices(n, src_fps, dst_fps):
    if src_fps <= 0 or dst_fps <= 0:
        return list(range(n))
    step = max(1, int(round(src_fps / dst_fps)))
    return list(range(0, n, step))


def process_sequence(img_dir: Path, depth_dir: Path, pose_file: Path, out_dir: Path,
                     target_w: int, target_h: int, dst_fps: float, src_fps: float):
    ensure_dir(out_dir / 'rgb')
    ensure_dir(out_dir / 'depth')
    poses_out = []
    images = sorted([p for p in img_dir.glob('*.png')] + [p for p in img_dir.glob('*.jpg')])
    depths = sorted([p for p in depth_dir.glob('*.png')] + [p for p in depth_dir.glob('*.npy')]) if depth_dir and depth_dir.exists() else []
    n = len(images)
    use_idx = uniform_fps_indices(n, src_fps, dst_fps)
    # Load pose json or text; if missing, synthesize indices only
    pose_data = None
    if pose_file and pose_file.exists():
        try:
            with open(pose_file, 'r', encoding='utf-8') as f:
                pose_data = json.load(f)
        except Exception:
            pose_data = None

    for i, idx in enumerate(tqdm(use_idx, desc=f"seq {img_dir.name}")):
        img_path = images[idx]
        img = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if img is None:
            continue
        img = resize_and_pad(img, (target_w, target_h))
        cv2.imwrite(str(out_dir / 'rgb' / f"{i:06d}.png"), img)

        if depths:
            di = min(idx, len(depths) - 1)
            dp = depths[di]
            if dp.suffix.lower() == '.npy':
                dep = np.load(str(dp)).astype(np.float32)
                # save depth as 16-bit PNG in decimeters to keep range
                dep_dm = np.clip(dep * 10.0, 0, 65535).astype(np.uint16)
                dep_dm = resize_and_pad(dep_dm[..., None], (target_w, target_h))
                cv2.imwrite(str(out_dir / 'depth' / f"{i:06d}.png"), dep_dm)
            else:
                dep = cv2.imread(str(dp), cv2.IMREAD_UNCHANGED)
                if dep is not None:
                    dep = resize_and_pad(dep, (target_w, target_h))
                    cv2.imwrite(str(out_dir / 'depth' / f"{i:06d}.png"), dep)

        pose = None
        if pose_data is not None:
            # Expect pose_data to be list or dict indexed by frame
            try:
                pose = pose_data[str(idx)] if isinstance(pose_data, dict) else pose_data[idx]
            except Exception:
                pose = None
        poses_out.append({"frame": i, "source_idx": int(idx), "pose": pose})

    with open(out_dir / 'poses.json', 'w', encoding='utf-8') as f:
        json.dump({"frames": poses_out, "target_size": [target_w, target_h], "dst_fps": dst_fps}, f)


def main():
    ap = argparse.ArgumentParser(description='Preprocess datasets into unified RGB+Depth+Pose format')
    ap.add_argument('--roots', type=str, nargs='+', required=True, help='One or more dataset roots under D:/datasets')
    ap.add_argument('--out', type=str, required=True, help='Output root, e.g., D:/datasets/unified')
    ap.add_argument('--width', type=int, default=640)
    ap.add_argument('--height', type=int, default=360)
    ap.add_argument('--fps', type=float, default=10.0)
    ap.add_argument('--src_fps', type=float, default=30.0)
    args = ap.parse_args()

    out_root = Path(args.out)
    ensure_dir(out_root)

    for root in args.roots:
        r = Path(root)
        if not r.exists():
            print(f"[WARN] Missing dataset root: {r}")
            continue
        # Heuristic: look for sequences containing rgb/ and depth/ and poses.json
        # Fall back to copying flat images if structure unknown
        seqs = []
        for p in sorted(r.glob('**')):
            if p.is_dir() and (p / 'rgb').exists():
                seqs.append(p)
        if not seqs:
            # Try flat structure
            seqs = [r]

        for seq in seqs:
            img_dir = seq / 'rgb' if (seq / 'rgb').exists() else seq
            depth_dir = seq / 'depth' if (seq / 'depth').exists() else None
            pose_file = seq / 'poses.json' if (seq / 'poses.json').exists() else None
            out_dir = out_root / r.name / seq.name
            process_sequence(img_dir, depth_dir, pose_file, out_dir,
                             target_w=args.width, target_h=args.height,
                             dst_fps=args.fps, src_fps=args.src_fps)


if __name__ == '__main__':
    main()
