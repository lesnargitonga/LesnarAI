"""
Segmentation inference helper supporting:
- TFHub DeepLabV3 SavedModel export (training/export_tfhub_deeplab.py)
- Small UNet SavedModel (training/quick_train_synth_unet.py or train_unet.py)
"""

from pathlib import Path
from typing import Optional

import numpy as np
import tensorflow as tf


class Segmenter:
    def __init__(self, model_dir: str, binary: bool = True):
        self.model_dir = Path(model_dir)
        self.binary = binary
        self.model = tf.keras.models.load_model(self.model_dir.as_posix())

        # Try to detect if this is a hub-wrapped model with dict outputs
        self.hub_dict_output = False
        try:
            test = self.model(tf.zeros([1, 128, 128, 3], dtype=tf.float32))
            if isinstance(test, dict):
                self.hub_dict_output = True
        except Exception:
            pass

    def predict_mask(self, image_bgr: np.ndarray) -> np.ndarray:
        """
        Accepts BGR uint8 image (OpenCV). Returns mask as uint8 (0/255 for binary).
        """
        img_rgb = image_bgr[..., ::-1].astype(np.float32) / 255.0
        inp = tf.convert_to_tensor(img_rgb[None, ...], dtype=tf.float32)
        out = self.model(inp)

        if isinstance(out, dict):
            # TFHub DeepLabV3 usually returns {"semantic": logits}
            logits = out.get("semantic", None)
            if logits is None:
                raise RuntimeError("Unexpected hub output structure")
            probs = tf.nn.softmax(logits, axis=-1)
            mask = tf.argmax(probs, axis=-1)[0].numpy().astype(np.uint8)
            return mask

        # UNet or generic keras model: shape [1,H,W,1] or [1,H,W,C]
        pred = out[0].numpy()
        if pred.ndim == 3 and pred.shape[-1] == 1:
            mask = (pred[..., 0] > 0.5).astype(np.uint8) * 255
            return mask
        else:
            cls = np.argmax(pred, axis=-1).astype(np.uint8)
            return cls


__all__ = ["Segmenter"]
