"""Fehlerprotokoll für unerwartete Fehler im Hintergrund – ohne Inhalte (keine markierten Texte, keine Dateien).

Liegt neben den Einstellungen als fehler.log (Windows: %APPDATA%\\Datenwaechter\\fehler.log), höchstens ~200 KB.
"""

from __future__ import annotations

import datetime as dt
import traceback
from pathlib import Path

MAX_BYTES = 200_000


def datei() -> Path:
    from .settings import path
    return path().with_name("fehler.log")


def fehler(wo: str, e: BaseException) -> Path | None:
    try:
        p = datei()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > MAX_BYTES:
            p.replace(p.with_suffix(".log.alt"))
        from . import __version__
        spur = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"--- {dt.datetime.now():%Y-%m-%d %H:%M:%S} · Datenwächter {__version__} · {wo}\n{spur}\n")
        return p
    except Exception:  # noqa: BLE001 – das Protokoll darf selbst nie stören
        return None
