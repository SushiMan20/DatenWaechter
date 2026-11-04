"""Texterkennung (OCR) für Bilder, Screenshots und eingescannte PDFs.

Reihenfolge:
1. Windows-eigene Texterkennung (Windows 10/11, nichts zu installieren; Paket: pip install winrt-Windows.Media.Ocr …)
2. Tesseract (https://github.com/UB-Mannheim/tesseract/wiki, mit deutschem Sprachpaket; pip install pytesseract)

Liefert den Text UND die Position jedes Wortes, damit Funde im Bild geschwärzt werden können.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in Pixeln


@dataclass
class Span:
    start: int
    end: int
    box: Box


@dataclass
class OcrResult:
    text: str
    spans: list[Span]


def _builder():
    parts: list[str] = []
    spans: list[Span] = []
    pos = 0

    def add(word: str, box: Box | None, sep: str = " "):
        nonlocal pos
        if parts:
            parts.append(sep)
            pos += len(sep)
        parts.append(word)
        if box:
            spans.append(Span(pos, pos + len(word), box))
        pos += len(word)

    return add, lambda: OcrResult("".join(parts), spans)


# --------------------------------------------------------------------------- Tesseract

@lru_cache(maxsize=1)
def _tesseract():
    try:
        import pytesseract
    except ImportError:
        return None
    if sys.platform == "win32" and not shutil.which("tesseract"):
        for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                  os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")):
            if os.path.exists(p):
                pytesseract.pytesseract.tesseract_cmd = p
                break
    try:
        langs = set(pytesseract.get_languages(config=""))
    except Exception:  # noqa: BLE001 – Tesseract nicht installiert
        return None
    lang = "+".join(l for l in ("deu", "eng") if l in langs) or "eng"
    return pytesseract, lang


def _ocr_tesseract(img) -> OcrResult:
    pytesseract, lang = _tesseract()
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    add, done = _builder()
    last_line = None
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        if not word or float(data["conf"][i]) < 0:
            continue
        line = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        add(word, (x, y, x + w, y + h), "\n" if last_line is not None and line != last_line else " ")
        last_line = line
    return done()


# --------------------------------------------------------------------------- Windows OCR

@lru_cache(maxsize=1)
def _windows():
    if sys.platform != "win32":
        return None
    try:  # neue pywinrt-Pakete …
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter
    except ImportError:
        try:  # … oder das ältere Sammelpaket „winsdk“
            from winsdk.windows.globalization import Language
            from winsdk.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
            from winsdk.windows.media.ocr import OcrEngine
            from winsdk.windows.storage.streams import DataWriter
        except ImportError:
            return None
    engine = None
    try:
        de = Language("de-DE")
        if OcrEngine.is_language_supported(de):
            engine = OcrEngine.try_create_from_language(de)
    except Exception:  # noqa: BLE001
        engine = None
    engine = engine or OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        return None
    return engine, SoftwareBitmap, BitmapPixelFormat, DataWriter


def _ocr_windows(img) -> OcrResult:
    import asyncio
    engine, SoftwareBitmap, BitmapPixelFormat, DataWriter = _windows()
    rgba = img.convert("RGBA")
    writer = DataWriter()
    writer.write_bytes(rgba.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.RGBA8, *rgba.size)
    result = asyncio.run(_await(engine.recognize_async(bitmap)))
    add, done = _builder()
    for li, line in enumerate(result.lines):
        for wi, word in enumerate(line.words):
            r = word.bounding_rect
            add(word.text, (r.x, r.y, r.x + r.width, r.y + r.height), "\n" if li and wi == 0 else " ")
    return done()


async def _await(op):
    return await op


# --------------------------------------------------------------------------- Öffentliche Funktionen

def backend() -> str | None:
    forced = os.environ.get("DATENWAECHTER_OCR")
    if forced in ("windows", "tesseract"):
        return forced if (_windows() if forced == "windows" else _tesseract()) else None
    if _windows():
        return "windows"
    if _tesseract():
        return "tesseract"
    return None


def recognize(img) -> OcrResult | None:
    """Erkennt Text im Bild. Kleine Bilder (Screenshots) werden zur besseren Erkennung vergrößert."""
    b = backend()
    if b is None:
        return None
    scale = 2 if max(img.size) < 1600 else 1
    work = img.resize((img.width * scale, img.height * scale)) if scale > 1 else img
    if b == "windows":
        try:
            res = _ocr_windows(work)
        except Exception:  # noqa: BLE001 – auf Tesseract ausweichen, falls vorhanden
            if not _tesseract():
                raise
            res = _ocr_tesseract(work)
    else:
        res = _ocr_tesseract(work)
    if scale > 1:
        for s in res.spans:
            s.box = tuple(v / scale for v in s.box)
    return res
