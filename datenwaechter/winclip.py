"""Windows-Zwischenablage: Änderungen erkennen und kopierte Dateien (Strg+C im Explorer) lesen/setzen.

Benötigt pywin32. Auf anderen Systemen liefern die Funktionen neutrale Werte,
damit der Rest des Programms trotzdem läuft.
"""

from __future__ import annotations

import struct
import sys
import time

try:
    import win32clipboard as wc
    import win32con
    AVAILABLE = sys.platform == "win32"
except ImportError:  # kein Windows oder pywin32 fehlt
    wc = win32con = None
    AVAILABLE = False


def sequence_number() -> int | None:
    """Zählt bei jeder Änderung der Zwischenablage hoch – billig, daher gut zum häufigen Abfragen."""
    return wc.GetClipboardSequenceNumber() if AVAILABLE else None


def _open(retries: int = 10) -> bool:
    for _ in range(retries):
        try:
            wc.OpenClipboard()
            return True
        except Exception:  # gerade von einem anderen Programm geöffnet
            time.sleep(0.03)
    return False


def get_files() -> list[str]:
    if not AVAILABLE or not _open():
        return []
    try:
        if wc.IsClipboardFormatAvailable(win32con.CF_HDROP):
            return list(wc.GetClipboardData(win32con.CF_HDROP))
        return []
    finally:
        wc.CloseClipboard()


def get_text() -> str | None:
    if not AVAILABLE or not _open():
        return None
    try:
        if wc.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return wc.GetClipboardData(win32con.CF_UNICODETEXT)
        return None
    finally:
        wc.CloseClipboard()


def get_image():
    """Bild in der Zwischenablage (z. B. Screenshot mit Win+Umschalt+S) als PIL-Bild, sonst None."""
    if not AVAILABLE:
        return None
    try:
        from PIL import Image, ImageGrab
        data = ImageGrab.grabclipboard()
    except Exception:  # noqa: BLE001 – Zwischenablage gerade gesperrt o. Ä.
        return None
    return data if isinstance(data, Image.Image) else None


def set_image(img) -> None:
    """Legt ein Bild als Bitmap in die Zwischenablage (Strg+V fügt es überall ein)."""
    if not AVAILABLE or not _open():
        return
    import io
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "BMP")
    try:
        wc.EmptyClipboard()
        wc.SetClipboardData(win32con.CF_DIB, buf.getvalue()[14:])  # ohne BMP-Dateikopf = DIB
    finally:
        wc.CloseClipboard()


def set_text(text: str) -> None:
    if not AVAILABLE or not _open():
        return
    try:
        wc.EmptyClipboard()
        wc.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        wc.CloseClipboard()


def set_files(paths: list[str]) -> None:
    """Legt Dateien so in die Zwischenablage, als hätte man sie im Explorer kopiert."""
    if not AVAILABLE or not _open():
        return
    # DROPFILES-Struktur: Offset der Dateiliste, Punkt (x, y), fNC, fWide=1 (Unicode)
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    body = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    try:
        wc.EmptyClipboard()
        wc.SetClipboardData(win32con.CF_HDROP, header + body)
    finally:
        wc.CloseClipboard()


def clear() -> None:
    if AVAILABLE and _open():
        try:
            wc.EmptyClipboard()
        finally:
            wc.CloseClipboard()
