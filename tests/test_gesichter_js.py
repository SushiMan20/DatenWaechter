"""Windows-Programm (OpenCV) und Handy-App (JavaScript) finden genau dieselben Gesichter.

Die Handy-App rechnet die Gesichtssuche von OpenCV in JavaScript nach (mobile/app/js/gesichter.js) – mit denselben
Daten (mobile/app/js/gesichter-daten.js, erzeugt von mobile/gesichter_daten.py). Hier wird beides verglichen.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from datenwaechter import faces

ROOT = Path(__file__).resolve().parent.parent
GESICHT = ROOT / "tests" / "fixtures" / "gesicht.jpg"

pytestmark = pytest.mark.skipif(not faces.available(), reason="OpenCV 4 nicht installiert")

JS = """
const { readFileSync } = await import("node:fs");
const { pathToFileURL } = await import("node:url");
const m = await import(pathToFileURL(process.argv[1]).href);
const bilder = JSON.parse(readFileSync(process.argv[2], "utf8"));
process.stdout.write(JSON.stringify(bilder.map(({ datei, b, h }) => m.finde(new Uint8Array(readFileSync(datei)), b, h))));
"""


def _bilder():
    """Fotos und Dokumentseiten in verschiedenen Größen – mit und ohne Gesicht."""
    from PIL import Image, ImageDraw, ImageFont
    foto = Image.open(GESICHT).convert("RGB")
    try:
        schrift = ImageFont.truetype("DejaVuSans.ttf", 15)
    except OSError:
        schrift = ImageFont.load_default()

    def seite(breite, foto_breite):
        s = Image.new("RGB", (breite, int(breite * 1.414)), "white")
        d = ImageDraw.Draw(s)
        for i in range(30):
            d.text((50, 260 + i * 22), f"Berufserfahrung {2000 + i}: Projektleitung bei der Muster GmbH", fill="black",
                   font=schrift)
        s.paste(foto.resize((foto_breite, foto_breite)), (breite - foto_breite - 40, 40))
        return s

    gruppe = Image.new("RGB", (1000, 750), (120, 130, 140))
    for i, (x, y, s) in enumerate([(40, 60, 300), (420, 200, 260), (720, 380, 240)]):
        f = foto.resize((s, s))
        gruppe.paste(f.transpose(Image.FLIP_LEFT_RIGHT) if i % 2 else f, (x, y))
    leer = Image.new("RGB", (900, 1273), "white")
    ImageDraw.Draw(leer).text((60, 60), "Sehr geehrte Damen und Herren, anbei die Unterlagen.", fill="black", font=schrift)
    return {"Foto": foto, "Foto gespiegelt, doppelt so groß": foto.transpose(Image.FLIP_LEFT_RIGHT).resize((640, 640)),
            "Lebenslauf-Seite": seite(1100, 333), "kleine Seite": seite(700, 260), "Gruppe": gruppe,
            "Textseite ohne Foto": leer}


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js fehlt")
def test_python_und_javascript_finden_dieselben_gesichter(tmp_path):
    bilder = _bilder()
    auftrag = []
    for i, img in enumerate(bilder.values()):
        grau = img.convert("L")
        (tmp_path / f"{i}.raw").write_bytes(grau.tobytes())
        auftrag.append({"datei": str(tmp_path / f"{i}.raw"), "b": grau.width, "h": grau.height})
    (tmp_path / "auftrag.json").write_text(json.dumps(auftrag), encoding="utf-8")
    lauf = subprocess.run(["node", "--input-type=module", "-e", JS, str(ROOT / "mobile" / "app" / "js" / "gesichter.js"),
                           str(tmp_path / "auftrag.json")], capture_output=True, text=True, check=True, timeout=300)
    js = json.loads(lauf.stdout)
    ergebnis = {name: ([[int(v) for v in b] for b in faces.detect(img)], j) for (name, img), j in zip(bilder.items(), js)}
    assert all(py == j for py, j in ergebnis.values()), json.dumps(ergebnis, ensure_ascii=False, indent=1)
    gefunden = {name: len(py) for name, (py, _) in ergebnis.items()}
    assert gefunden["Foto"] == gefunden["Lebenslauf-Seite"] == gefunden["kleine Seite"] == 1, gefunden
    assert gefunden["Gruppe"] >= 3 and gefunden["Textseite ohne Foto"] == 0, gefunden


def test_daten_der_handy_app_passen_zu_opencv():
    sys.path.insert(0, str(ROOT / "mobile"))
    try:
        from gesichter_daten import ZIEL, erzeugen
    finally:
        sys.path.pop(0)
    assert ZIEL.read_text(encoding="utf-8") == erzeugen(), \
        "OpenCV bringt andere Gesichts-Kaskaden mit – bitte „python mobile/gesichter_daten.py“ ausführen"


def test_foto_auf_weisser_seite_wird_gefunden():
    """Früher (mit Histogramm-Ausgleich über das ganze Bild) blieb ein Passfoto auf einer Dokumentseite unsichtbar."""
    seite = _bilder()["Lebenslauf-Seite"]
    assert len(faces.detect(seite)) == 1
