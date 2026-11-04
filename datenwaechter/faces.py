"""Gesichter auf Fotos finden (OpenCV, läuft lokal, ~30 MB). Installation: pip install "opencv-python-headless<5"."""

from __future__ import annotations

from functools import lru_cache

from .ocr import Box


@lru_cache(maxsize=1)
def _detectors():
    try:
        import cv2
        base = cv2.data.haarcascades
        cascades = [cv2.CascadeClassifier(base + n) for n in
                    ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]
    except (ImportError, AttributeError):  # OpenCV fehlt oder Version 5 ohne mitgelieferte Modelle
        return None
    cascades = [c for c in cascades if not c.empty()]
    return (cv2, cascades) if cascades else None


def available() -> bool:
    return _detectors() is not None


def detect(img) -> list[Box]:
    det = _detectors()
    if det is None:
        return []
    import numpy as np
    cv2, cascades = det
    gray = cv2.equalizeHist(np.asarray(img.convert("L")))
    min_side = max(24, min(img.size) // 25)
    found: list[Box] = []
    for c in cascades:
        for (x, y, w, h) in c.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(min_side, min_side)):
            box = (float(x), float(y), float(x + w), float(y + h))
            if not any(_overlap(box, b) > 0.3 for b in found):
                found.append(box)
    return found


def _overlap(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0
