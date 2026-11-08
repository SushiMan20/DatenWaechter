"""Schwärzen in Bildern: Funde werden mit einem Kasten samt Platzhalter überdeckt, Gesichter verpixelt."""

from __future__ import annotations

from functools import lru_cache

from .ocr import Box, Span


def boxes_for(spans: list[Span], start: int, end: int) -> list[Box]:
    """Alle Wort-/Zeichenkästen im Bereich [start, end), pro Textzeile zu einem Kasten zusammengefasst."""
    lines: list[list[float]] = []
    for s in spans:
        if s.end <= start or s.start >= end:
            continue
        x0, y0, x1, y1 = s.box
        if x1 - x0 <= 0 or y1 - y0 <= 0:
            continue
        cur = lines[-1] if lines else None
        # gleiche Zeile, wenn sich die Höhen deutlich überlappen
        if cur and min(cur[3], y1) - max(cur[1], y0) > 0.4 * min(cur[3] - cur[1], y1 - y0) and x0 >= cur[0] - 2:
            cur[0], cur[1], cur[2], cur[3] = min(cur[0], x0), min(cur[1], y0), max(cur[2], x1), max(cur[3], y1)
        else:
            lines.append([x0, y0, x1, y1])
    return [tuple(b) for b in lines]


@lru_cache(maxsize=8)
def _font(size: int):
    from PIL import ImageFont
    for name in ("arialbd.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_label(img, box: Box, label: str) -> None:
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = (int(v) for v in box)
    pad = max(1, (y1 - y0) // 8)
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    d.rectangle((x0, y0, x1, y1), fill=(30, 30, 30))
    size = max(8, int((y1 - y0) * 0.7))
    font = _font(size)
    while size > 6 and d.textlength(label, font=font) > (x1 - x0) - 2 * pad:
        size -= 1
        font = _font(size)
    if d.textlength(label, font=font) <= (x1 - x0):
        d.text(((x0 + x1) / 2, (y0 + y1) / 2), label, fill=(255, 255, 255), font=font, anchor="mm")


def pixelate(img, box: Box, blocks: int = 10) -> None:
    from PIL import Image
    x0, y0, x1, y1 = (int(v) for v in box)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img.width, x1), min(img.height, y1)
    if x1 <= x0 or y1 <= y0:
        return
    region = img.crop((x0, y0, x1, y1))
    small = region.resize((max(1, (x1 - x0) // blocks), max(1, (y1 - y0) // blocks)), Image.BILINEAR)
    img.paste(small.resize(region.size, Image.NEAREST), (x0, y0))


def redact(img, spans: list[Span], findings, anonymizer, faces: list[Box] = ()):
    """Gibt eine geschwärzte Kopie des Bildes zurück."""
    out = img.convert("RGB")
    for f in findings:
        label = anonymizer.placeholder(f)
        for box in boxes_for(spans, f.start, f.end):
            draw_label(out, box, label)
    for box in faces:
        pixelate_face(out, box)
    return out


def pixelate_face(img, box: Box) -> None:
    """Verpixelt ein Gesicht samt Rand (15 % der Breite) – grob: etwa 5 Blöcke über die Gesichtsbreite,
    sonst bleibt das Gesicht erkennbar. Die Handy-App macht es genauso (mobile/app/js/dokumente.js)."""
    x0, y0, x1, y1 = box
    m = 0.15 * (x1 - x0)
    pixelate(img, (x0 - m, y0 - m, x1 + m, y1 + m), blocks=max(8, int((x1 - x0) / 5)))
