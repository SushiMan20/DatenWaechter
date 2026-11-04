"""Tageszähler für die Anzeige: geprüft / gewarnt / anonymisiert (nur Zahlen, keine Inhalte)."""

from __future__ import annotations

import datetime as dt
import json

from .settings import path as settings_path

KEYS = ("geprueft", "gewarnt", "anonymisiert")


class Stats:
    def __init__(self) -> None:
        self.file = settings_path().with_name("statistik.json")
        self.data = {"datum": "", **{k: 0 for k in KEYS}}
        try:
            self.data.update(json.loads(self.file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        self._roll()

    def _roll(self) -> None:
        today = dt.date.today().isoformat()
        if self.data.get("datum") != today:
            self.data = {"datum": today, **{k: 0 for k in KEYS}}

    def inc(self, key: str, n: int = 1) -> None:
        self._roll()
        self.data[key] = self.data.get(key, 0) + n
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text(json.dumps(self.data), encoding="utf-8")
        except OSError:
            pass

    def get(self, key: str) -> int:
        self._roll()
        return int(self.data.get(key, 0))

    def summary(self) -> str:
        return f"Heute: {self.get('geprueft')} geprüft · {self.get('gewarnt')} gewarnt · {self.get('anonymisiert')} anonymisiert"
