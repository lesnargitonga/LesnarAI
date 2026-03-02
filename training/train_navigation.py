import argparse
from pathlib import Path
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import cv2
import numpy as np
from tqdm import tqdm
from training.models.vision_nav import VisionNavCNNLSTM


class NavDataset(Dataset):
    def __init__(self, root: Path, seq_len=4):
        self.rgb = sorted(list((root / 'rgb').glob('*.png')))
        self.act = sorted(list((root / 'actions').glob('*.npy')))
        self.seq_len = seq_len
        assert len(self.rgb) >= seq_len and len(self.rgb) == len(self.act)

    def __len__(self):
        return len(self.rgb) - self.seq_len + 1

    def __getitem__(self, idx):
        frames = []
        for k in range(self.seq_len):
            img = cv2.imread(str(self.rgb[idx + k]), cv2.IMREAD_COLOR)
            frames.append((img[:, :, ::-1].astype(np.float32) / 255.0).transpose(2, 0, 1))
        x = np.stack(frames, axis=0)
        y = np.load(str(self.act[idx + self.seq_len - 1])).astype(np.float32)  # last frame action
        return torch.from_numpy(x), torch.from_numpy(y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', type=str, required=True)
    ap.add_argument('--epochs', type=int, default=5)
    ap.add_argument('--bs', type=int, default=4)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--seq_len', type=int, default=4)
    ap.add_argument('--out', type=str, default='models/vision_nav.pt')
    args = ap.parse_args()

    ds = NavDataset(Path(args.data), seq_len=args.seq_len)
    dl = DataLoader(ds, batch_size=args.bs, shuffle=True, num_workers=2)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = VisionNavCNNLSTM(in_ch=3, hidden=128, lstm_hidden=128, out_dim=3).to(device)
    criterion = nn.MSELoss()
    opt = optim.Adam(model.parameters(), lr=args.lr)

    model.train()
    for ep in range(args.epochs):
        pbar = tqdm(dl, desc=f"epoch {ep+1}/{args.epochs}")
        total = 0.0
        for x, y in pbar:
            x = x.to(device)
            y = y.to(device)
            opt.zero_grad()
            out = model(x)
            loss = criterion(out, y)
            loss.backward()
            opt.step()
            total += float(loss.item())
            pbar.set_postfix(loss=f"{total/ (pbar.n+1):.4f}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), args.out)


if __name__ == '__main__':
    main()
