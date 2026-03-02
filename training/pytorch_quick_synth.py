from pathlib import Path
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

from pytorch_unet import UNet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="models/unet_torch_synth")
    ap.add_argument("--size", type=int, nargs=2, default=[128, 128])
    ap.add_argument("--samples", type=int, default=128)
    ap.add_argument("--epochs", type=int, default=2)
    args = ap.parse_args()

    H, W = args.size
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = UNet(in_ch=3, num_classes=1, base=16).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCEWithLogitsLoss()

    # Synthetic blobs
    rng = np.random.default_rng(0)
    X = np.zeros((args.samples, 3, H, W), dtype=np.float32)
    Y = np.zeros((args.samples, 1, H, W), dtype=np.float32)
    yy, xx = np.ogrid[:H, :W]
    for i in range(args.samples):
        img = np.zeros((3, H, W), dtype=np.float32)
        msk = np.zeros((1, H, W), dtype=np.float32)
        for _ in range(rng.integers(1, 4)):
            r = int(rng.integers(8, 20))
            cy = int(rng.integers(r, H - r))
            cx = int(rng.integers(r, W - r))
            mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= r ** 2
            color = rng.random(3)
            # Assign color per channel using the boolean mask
            img[0, mask] = color[0]
            img[1, mask] = color[1]
            img[2, mask] = color[2]
            msk[0, mask] = 1.0
        X[i] = img
        Y[i] = msk

    X = torch.from_numpy(X).to(device)
    Y = torch.from_numpy(Y).to(device)

    model.train()
    for ep in range(args.epochs):
        logits = model(X)
        loss = loss_fn(logits, Y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
        print(f"epoch {ep+1}/{args.epochs} loss={loss.item():.4f}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), (out / "model.pt").as_posix())
    example = torch.randn(1, 3, H, W).to(device)
    traced = torch.jit.trace(model.eval(), example)
    traced.save((out / "model_ts.pt").as_posix())
    print("Saved to", out)


if __name__ == "__main__":
    main()
