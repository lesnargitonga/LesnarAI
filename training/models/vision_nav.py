import torch
import torch.nn as nn


class VisionNavCNNLSTM(nn.Module):
    def __init__(self, in_ch=3, hidden=128, lstm_hidden=128, out_dim=3):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(in_ch, 32, 5, stride=2, padding=2), nn.ReLU(),
            nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.ReLU(),
            nn.Conv2d(64, 128, 3, stride=2, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.proj = nn.Linear(128, hidden)
        self.lstm = nn.LSTM(hidden, lstm_hidden, batch_first=True)
        self.head = nn.Linear(lstm_hidden, out_dim)  # vx, vy, yaw_rate

    def forward(self, x_seq):
        # x_seq: (B, T, C, H, W)
        B, T, C, H, W = x_seq.shape
        x = x_seq.view(B * T, C, H, W)
        f = self.cnn(x).view(B * T, -1)
        f = self.proj(f)
        f = f.view(B, T, -1)
        y, _ = self.lstm(f)
        out = self.head(y[:, -1, :])
        return out
