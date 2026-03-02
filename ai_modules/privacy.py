import cv2
import numpy as np
from typing import Tuple


class PrivacyMasker:
    def __init__(self, cascade: str | None = None, blur_kernel: Tuple[int, int] = (15, 15)):
        self.cascade_path = cascade or (cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        self.detector = cv2.CascadeClassifier(self.cascade_path)
        self.blur_kernel = blur_kernel

    def blur_faces(self, bgr: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        faces = self.detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(32, 32))
        out = bgr.copy()
        for (x, y, w, h) in faces:
            roi = out[y:y + h, x:x + w]
            roi_blur = cv2.GaussianBlur(roi, self.blur_kernel, 0)
            out[y:y + h, x:x + w] = roi_blur
        return out


if __name__ == "__main__":
    import time
    cap = cv2.VideoCapture(0)
    pm = PrivacyMasker()
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        masked = pm.blur_faces(frame)
        cv2.imshow("privacy", masked)
        if cv2.waitKey(1) & 0xFF == 27:
            break
    cap.release()
    cv2.destroyAllWindows()