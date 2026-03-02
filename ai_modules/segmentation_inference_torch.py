from pathlib import Path
import numpy as np
import torch
import cv2

from training.pytorch_unet import UNet


class TorchSegmenter:
    def __init__(self, weights_path: str, img_size=(256, 256), classes=1, base=32, jit: bool=False, device: str|None=None, invert_mask: bool=False):
        self.device = torch.device(device) if device else torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.img_size = img_size
        self.classes = classes
        self.jit = jit
        self.invert_mask = invert_mask
        p = Path(weights_path)

        # Try to auto-detect TorchScript vs state_dict formats.
        self.model = None
        if p.suffix == ".pt":
            try:
                # First attempt: treat as TorchScript
                self.model = torch.jit.load(p.as_posix(), map_location=self.device)
                self.jit = True
            except Exception:
                self.model = None

        if self.model is None:
            # Fallback: load as state_dict and try common base widths.
            sd = torch.load(p.as_posix(), map_location=self.device)
            tried = []
            last_err = None
            for b in [base, 16, 32, 64]:
                if b in tried:
                    continue
                tried.append(b)
                candidate = UNet(in_ch=3, num_classes=classes, base=b).to(self.device)
                try:
                    candidate.load_state_dict(sd, strict=True)
                    self.model = candidate
                    break
                except RuntimeError as e:
                    last_err = e
            # Last resort: attempt non-strict load with the requested base
            if self.model is None:
                candidate = UNet(in_ch=3, num_classes=classes, base=base).to(self.device)
                try:
                    candidate.load_state_dict(sd, strict=False)
                    self.model = candidate
                except Exception:
                    # Re-raise the most informative error
                    raise last_err if last_err else RuntimeError(
                        "Failed to load UNet weights: incompatible shapes and non-strict load failed"
                    )

        self.model.eval()

    def predict_mask(self, image_bgr: np.ndarray) -> np.ndarray:
        img = cv2.resize(image_bgr, self.img_size[::-1])
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        x = torch.from_numpy(img.transpose(2, 0, 1)).float().div(255.0)[None, ...].to(self.device)
        with torch.inference_mode():
            logits = self.model(x)
            if self.classes == 1:
                prob = torch.sigmoid(logits)[0, 0].cpu().numpy()
                # Adaptive thresholding: try Otsu on the probability map first
                prob_u8 = (np.clip(prob, 0.0, 1.0) * 255.0).astype(np.uint8)
                _thr, mask_bin = cv2.threshold(prob_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                # Fallback if Otsu collapses to all-0 or all-255
                if mask_bin.mean() in (0.0, 255.0):
                    mask_bin = (prob > 0.5).astype(np.uint8) * 255
                if self.invert_mask:
                    mask_bin = 255 - mask_bin
                return mask_bin
            else:
                cls = torch.argmax(logits, dim=1)[0].cpu().numpy().astype(np.uint8)
                return cls


__all__ = ["TorchSegmenter"]
