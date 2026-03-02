import argparse
import time
import numpy as np


def time_it(fn, warmup=10, runs=100):
    for _ in range(warmup):
        fn()
    t0 = time.perf_counter()
    for _ in range(runs):
        fn()
    dt = time.perf_counter() - t0
    ms = (dt / runs) * 1000.0
    fps = 1000.0 / ms if ms > 0 else float("inf")
    return ms, fps


def make_image(w=640, h=360):
    import numpy as _np
    return _np.random.randint(0, 255, (h, w, 3), dtype=_np.uint8)


def torch_seg(weights, img_size=(256, 256)):
    from ai_modules.segmentation_inference_torch import TorchSegmenter
    seg = TorchSegmenter(weights, img_size=img_size, classes=1)
    img = make_image()
    return lambda: seg.predict_mask(img)


def ultralytics_yolo(model_path):
    from ultralytics import YOLO  # pip install ultralytics
    yolo = YOLO(model_path)
    img = make_image()
    return lambda: yolo(img, verbose=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["seg", "yolo"], required=True)
    ap.add_argument("--weights", type=str, required=True)
    ap.add_argument("--speed_mps", type=float, default=5.0)
    args = ap.parse_args()

    if args.task == "seg":
        fn = torch_seg(args.weights)
    else:
        fn = ultralytics_yolo(args.weights)

    ms, fps = time_it(fn)
    blind_m = args.speed_mps * (ms / 1000.0)
    print(f"Latency: {ms:.2f} ms | FPS: {fps:.1f} | Blind travel @ {args.speed_mps} m/s: {blind_m:.2f} m")


if __name__ == "__main__":
    main()