"""Erzeugt app/js/gesichter-daten.js aus den Gesichts-Kaskaden von OpenCV.

Die Handy-App nutzt damit genau dieselben Erkennungsdaten wie das Windows-Programm (datenwaechter/faces.py).
Nur nötig, wenn OpenCV neue Kaskaden mitbringt:

    pip install "opencv-python-headless>=4.8,<5" numpy
    python mobile/gesichter_daten.py
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ZIEL = Path(__file__).resolve().parent / "app" / "js" / "gesichter-daten.js"
KASKADEN = {"frontal": "haarcascade_frontalface_default.xml", "profil": "haarcascade_profileface.xml"}


def _zahl(v: str) -> float | int:
    import numpy as np
    f = np.float32(float(v))
    return int(f) if f == int(f) else float(str(f))   # kürzeste Schreibweise, die genau diesen float32-Wert ergibt


def kaskade(pfad: Path) -> dict:
    wurzel = ET.parse(pfad).getroot()[0]
    if wurzel.findtext("featureType").strip() != "HAAR":
        raise ValueError(f"{pfad.name}: keine Haar-Kaskade")
    stufen, anzahl, stuempfe = [], [], []
    for stufe in wurzel.find("stages"):
        schwache = list(stufe.find("weakClassifiers"))
        stufen.append(_zahl(stufe.findtext("stageThreshold")))
        anzahl.append(len(schwache))
        for w in schwache:
            links, rechts, merkmal, schwelle = w.findtext("internalNodes").split()
            if (links, rechts) != ("0", "-1"):
                raise ValueError(f"{pfad.name}: nur Kaskaden aus Einzelentscheidungen (Stümpfen) werden unterstützt")
            blatt = [_zahl(x) for x in w.findtext("leafValues").split()]
            stuempfe += [int(merkmal), _zahl(schwelle), *blatt]
    merkmale = []
    for m in wurzel.find("features"):
        if (m.findtext("tilted") or "0").strip() != "0":
            raise ValueError(f"{pfad.name}: gedrehte Merkmale werden nicht unterstützt")
        rechtecke = [r.text.split() for r in m.find("rects")]
        if not 1 <= len(rechtecke) <= 3:
            raise ValueError(f"{pfad.name}: unerwartete Merkmalsform")
        for r in rechtecke + [["0"] * 5] * (3 - len(rechtecke)):
            merkmale += [int(r[0]), int(r[1]), int(r[2]), int(r[3]), _zahl(r[4])]
    return {"breite": int(wurzel.findtext("width")), "hoehe": int(wurzel.findtext("height")),
            "stufen": stufen, "anzahl": anzahl, "stuempfe": stuempfe, "merkmale": merkmale}


def lizenz(pfad: Path) -> str:
    """Der Lizenztext aus dem Kopf der XML-Datei (muss bei Weitergabe erhalten bleiben)."""
    kopf = re.search(r"<!--(.*?)-->", pfad.read_text(encoding="utf-8"), re.S).group(1)
    return "\n".join(("// " + z.rstrip()).rstrip() for z in kopf.strip("\n").splitlines())


def erzeugen() -> str:
    import cv2
    basis = Path(cv2.data.haarcascades)
    daten = {name: kaskade(basis / datei) for name, datei in KASKADEN.items()}
    teile = ["// Erzeugt von mobile/gesichter_daten.py aus den Gesichts-Kaskaden von OpenCV – nicht von Hand ändern.",
             "// Dieselben Daten nutzt das Windows-Programm (datenwaechter/faces.py).", "//"]
    for datei in KASKADEN.values():
        teile += [f"// {datei}:", lizenz(basis / datei), "//"]
    teile.append("export default " + json.dumps(daten, separators=(",", ":")) + ";")
    return "\n".join(teile) + "\n"


if __name__ == "__main__":
    ZIEL.write_text(erzeugen(), encoding="utf-8")
    print(f"{ZIEL} geschrieben ({ZIEL.stat().st_size // 1024} KB)")
