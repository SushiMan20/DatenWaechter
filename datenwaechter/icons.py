"""Schild-Symbole für Tray, Fenster und Browser-Erweiterung – zur Laufzeit gezeichnet, keine Bilddateien nötig."""

from __future__ import annotations

from functools import lru_cache

FARBEN = {
    "aktiv": "#2e7d32",     # grün: Schutz läuft
    "pause": "#ef6c00",     # orange: pausiert
    "warnung": "#c62828",   # rot: gerade etwas gefunden
    "pruefe": "#1565c0",    # blau: prüft gerade
}

_SCHILD = [(0.50, 0.04), (0.90, 0.17), (0.89, 0.46), (0.84, 0.63), (0.74, 0.78), (0.62, 0.89), (0.50, 0.96),
           (0.38, 0.89), (0.26, 0.78), (0.16, 0.63), (0.11, 0.46), (0.10, 0.17)]


@lru_cache(maxsize=32)
def shield(state: str = "aktiv", size: int = 64):
    """Schild in der Farbe des Zustands, mit Haken / Pause / Ausrufezeichen / Lupe."""
    from PIL import Image, ImageDraw
    big = size * 4  # groß zeichnen, dann verkleinern = glatte Kanten
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pts = [(x * big, y * big) for x, y in _SCHILD]
    d.polygon(pts, fill=FARBEN.get(state, FARBEN["aktiv"]))
    w = max(4, big // 11)
    white = (255, 255, 255, 255)
    if state == "aktiv":
        d.line([(0.31 * big, 0.50 * big), (0.45 * big, 0.64 * big), (0.70 * big, 0.36 * big)], fill=white, width=w,
               joint="curve")
    elif state == "pause":
        for x in (0.38, 0.56):
            d.rounded_rectangle((x * big, 0.33 * big, (x + 0.07) * big, 0.68 * big), radius=w // 3, fill=white)
    elif state == "warnung":
        d.rounded_rectangle((0.455 * big, 0.25 * big, 0.545 * big, 0.60 * big), radius=w // 3, fill=white)
        d.ellipse((0.45 * big, 0.66 * big, 0.55 * big, 0.76 * big), fill=white)
    else:  # prüft
        d.ellipse((0.30 * big, 0.28 * big, 0.62 * big, 0.60 * big), outline=white, width=w)
        d.line([(0.58 * big, 0.56 * big), (0.72 * big, 0.72 * big)], fill=white, width=w)
    return img.resize((size, size), Image.LANCZOS)


def write_extension_icons(target_dir) -> None:
    """Erzeugt die PNG-Symbole der Browser-Erweiterung (extension/icons)."""
    from pathlib import Path
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    for state in ("aktiv", "pause"):
        for size in (16, 32, 48, 128):
            shield(state, size).save(target / f"{state}-{size}.png")
