"""Symbol im Infobereich (Tray): zeigt auf einen Blick, ob der Schutz läuft, und bietet die wichtigsten Befehle.

Grün = aktiv, orange = pausiert, blau = prüft gerade, rot = Warnung. Rechtsklick öffnet das Menü,
Doppelklick (bzw. Linksklick unter Windows) das Fenster. Benötigt `pystray` (im Paket [windows] enthalten).
Menübefehle laufen in einem eigenen Thread; sie werden über `send` an das Fenster weitergereicht.

Wichtig: Das Fenster (Tk) darf nie auf den Tray-Thread warten. Je nach System blockiert das Setzen des Symbols,
bis der Tray-Thread es übernimmt – räumt dieser gleichzeitig ein Tk-Objekt auf, warten beide aufeinander.
Deshalb gehen Zustandswechsel über einen eigenen kleinen Arbeits-Thread (nur der neueste Stand zählt).
"""

from __future__ import annotations

import sys
import threading
from typing import Callable

from . import autostart
from .icons import shield


def _safe(text: str) -> str:
    """Manche Tray-Systeme (X11) können nur Latin-1 – Gedankenstriche usw. ersetzen."""
    text = text.replace("–", "-").replace("…", "...")
    if sys.platform != "win32":
        text = text.encode("latin-1", "replace").decode("latin-1")
    return text


class Tray:
    def __init__(self, send: Callable[[str], None], is_active: Callable[[], bool], summary: Callable[[], str]):
        self.icon = None
        self.state = "aktiv"
        self.error: str | None = None
        self._pending = None
        self._cv = threading.Condition()
        try:
            import pystray
            from pystray import Menu, MenuItem as Item
        except Exception as e:  # noqa: BLE001 – pystray fehlt oder kein Infobereich vorhanden
            self.error = f"pystray nicht verfügbar ({e.__class__.__name__}: {e})"
            return
        cmd = lambda name: (lambda icon, item: send(name))  # noqa: E731
        menu = Menu(
            Item(lambda item: _safe(summary()), None, enabled=False),
            Menu.SEPARATOR,
            Item("Datenwächter öffnen", cmd("show"), default=True),
            Item("Schutz aktiv", cmd("toggle"), checked=lambda item: is_active()),
            Item("15 Minuten pausieren", cmd("pause15"), visible=lambda item: is_active()),
            Item("Datei prüfen …", cmd("pick")),
            Item("KI-Antwort zurückübersetzen", cmd("restore")),
            Item("Einstellungen …", cmd("settings")),
            Item("Mit Windows starten", cmd("autostart"), checked=lambda item: autostart.is_enabled()),
            Menu.SEPARATOR,
            Item("Beenden", cmd("quit")),
        )
        try:
            self.icon = pystray.Icon("datenwaechter", shield("aktiv", 64), _safe("Datenwächter – Schutz aktiv"), menu)
            threading.Thread(target=self.icon.run, daemon=True).start()
            threading.Thread(target=self._worker, daemon=True).start()
        except Exception as e:  # noqa: BLE001
            self.icon = None
            self.error = f"{e.__class__.__name__}: {e}"

    @property
    def available(self) -> bool:
        return self.icon is not None

    def set_state(self, state: str, tooltip: str) -> None:
        """Kehrt sofort zurück; das Symbol wird im Hintergrund aktualisiert."""
        if not self.icon:
            return
        self.state = state
        with self._cv:
            self._pending = (state, tooltip)
            self._cv.notify()

    def _worker(self) -> None:
        shown = None
        while True:
            with self._cv:
                while self._pending is None:
                    self._cv.wait()
                state, tooltip = self._pending
                self._pending = None
            try:
                if state != shown:
                    self.icon.icon = shield(state, 64)
                    shown = state
                self.icon.title = _safe(tooltip)[:120]  # Windows begrenzt die Länge des Tooltips
                self.icon.update_menu()
            except Exception:  # noqa: BLE001 – nicht jedes Backend kann alles
                pass

    def notify(self, title: str, message: str) -> None:
        if self.icon and getattr(self.icon, "HAS_NOTIFICATION", False):
            try:
                self.icon.notify(_safe(message), _safe(title))
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        if self.icon:
            try:
                self.icon.stop()
            except Exception:  # noqa: BLE001
                pass
