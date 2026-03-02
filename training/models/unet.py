import torch
import torch.nn as nn


class DoubleConv(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.net(x)


class UNet(nn.Module):
    def __init__(self, in_ch=3, num_classes=2, base_ch=32):
        super().__init__()
        self.d1 = DoubleConv(in_ch, base_ch)
        self.p1 = nn.MaxPool2d(2)
        self.d2 = DoubleConv(base_ch, base_ch * 2)
        self.p2 = nn.MaxPool2d(2)
        self.d3 = DoubleConv(base_ch * 2, base_ch * 4)
        self.p3 = nn.MaxPool2d(2)
        self.bottleneck = DoubleConv(base_ch * 4, base_ch * 8)
        self.u3 = nn.ConvTranspose2d(base_ch * 8, base_ch * 4, 2, stride=2)
        self.c3 = DoubleConv(base_ch * 8, base_ch * 4)
        self.u2 = nn.ConvTranspose2d(base_ch * 4, base_ch * 2, 2, stride=2)
        self.c2 = DoubleConv(base_ch * 4, base_ch * 2)
        self.u1 = nn.ConvTranspose2d(base_ch * 2, base_ch, 2, stride=2)
        self.c1 = DoubleConv(base_ch * 2, base_ch)
        self.out = nn.Conv2d(base_ch, num_classes, 1)

    def forward(self, x):
        x1 = self.d1(x)
        x2 = self.d2(self.p1(x1))
        x3 = self.d3(self.p2(x2))
        xb = self.bottleneck(self.p3(x3))
        x = self.u3(xb)
        x = self.c3(torch.cat([x, x3], dim=1))
        x = self.u2(x)
        x = self.c2(torch.cat([x, x2], dim=1))
        x = self.u1(x)
        x = self.c1(torch.cat([x, x1], dim=1))
        return self.out(x)
