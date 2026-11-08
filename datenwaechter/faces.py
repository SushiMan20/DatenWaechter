"""Gesichter auf Fotos finden (OpenCV, läuft lokal, ~30 MB). Installation: pip install "opencv-python-headless<5".

Gesucht wird von vorn und im Profil (in beide Blickrichtungen). Die Handy-App macht mit denselben Daten genau
dasselbe in JavaScript (mobile/app/js/gesichter.js) – tests/test_gesichter_js.py prüft, dass beide gleich finden.
"""

from __future__ import annotations

from functools import lru_cache

from .ocr import Box


@lru_cache(maxsize=1)
def _detectors():
    try:
        import cv2
        base = cv2.data.haarcascades
        frontal, profil = (cv2.CascadeClassifier(base + n) for n in
                           ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"))
    except (ImportError, AttributeError):  # OpenCV fehlt oder Version 5 ohne mitgelieferte Modelle
        return None
    # (Kaskade, gespiegelt?) – die Profil-Kaskade kennt nur eine Blickrichtung, gespiegelt findet sie die andere
    laeufe = [(c, gespiegelt) for c, gespiegelt in ((frontal, False), (profil, False), (profil, True)) if not c.empty()]
    return (cv2, laeufe) if laeufe else None


def available() -> bool:
    return _detectors() is not None


def detect(img) -> list[Box]:
    det = _detectors()
    if det is None:
        return []
    import numpy as np
    cv2, laeufe = det
    # Bewusst ohne Histogramm-Ausgleich: die Kaskade gleicht Helligkeit und Kontrast je Suchfenster selbst aus.
    # Ein Ausgleich über das ganze Bild drückt ein Foto auf einer fast weißen Seite (Lebenslauf, Ausweis-Kopie)
    # in wenige dunkle Grautöne – das Gesicht wird dann nicht mehr gefunden.
    gray = np.asarray(img.convert("L"))
    flipped = cv2.flip(gray, 1)
    width = gray.shape[1]
    min_side = max(24, min(img.size) // 25)
    found: list[Box] = []
    for c, gespiegelt in laeufe:
        boxes = []
        for (x, y, w, h) in c.detectMultiScale(flipped if gespiegelt else gray, scaleFactor=1.1, minNeighbors=6,
                                               minSize=(min_side, min_side)):
            if gespiegelt:
                x = width - x - w
            boxes.append((float(x), float(y), float(x + w), float(y + h)))
        # OpenCV rechnet auf mehreren Kernen – die Reihenfolge der Treffer schwankt. Fest sortiert (von oben nach
        # unten, dann links nach rechts), damit das Ergebnis immer gleich ist (und gleich wie in der Handy-App).
        for box in sorted(boxes, key=lambda b: (b[1], b[0], b[2], b[3])):
            if not any(_overlap(box, b) > 0.3 for b in found):
                found.append(box)
    return found


def _overlap(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0
