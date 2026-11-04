"""KI-Aktionen in jedem Windows-Programm: Text markieren -> Tastenkürzel (Standard: Strg+Alt+Leertaste)
-> Menü am Mauszeiger -> Ergebnis wird an Stelle der Markierung eingefügt.

Ein eigener Eintrag im Rechtsklick-Menü fremder Programme ist unter Windows nicht möglich; das Tastenkürzel
ist der übliche Weg (so arbeiten auch PowerToys & Co.). Umsetzung ohne Zusatzpakete über die Windows-API:
- RegisterHotKey in einem eigenen Thread (meldet sich mit WM_HOTKEY)
- markierten Text holen: Strg+C senden und Zwischenablage lesen
- Ergebnis einsetzen: Zwischenablage setzen, vorheriges Fenster aktivieren, Strg+V senden,
  danach den alten Inhalt der Zwischenablage wiederherstellen
"""

from __future__ import annotations

import sys
import threading
import time

from . import winclip

STANDARD = "Strg+Alt+Leertaste"

_MODS = {"strg": 0x2, "ctrl": 0x2, "alt": 0x1, "umschalt": 0x4, "shift": 0x4, "win": 0x8}
_KEYS = {"leertaste": 0x20, "space": 0x20, "eingabe": 0x0D, "enter": 0x0D, "einfg": 0x2D, "insert": 0x2D}
MOD_NOREPEAT = 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN = 0x11, 0x12, 0x10, 0x5B, 0x5C
KEYUP = 0x0002


def parse(combo: str) -> tuple[int, int]:
    """'Strg+Alt+Leertaste' -> (Modifikatoren, virtueller Tastencode). Wirft ValueError bei Unsinn."""
    parts = [p.strip().lower() for p in combo.replace("-", "+").split("+") if p.strip()]
    if len(parts) < 2:
        raise ValueError("Mindestens eine Zusatztaste (Strg, Alt, Umschalt, Win) und eine Taste angeben")
    mods = 0
    for p in parts[:-1]:
        if p not in _MODS:
            raise ValueError(f"Unbekannte Zusatztaste „{p}“")
        mods |= _MODS[p]
    key = parts[-1]
    if key in _KEYS:
        vk = _KEYS[key]
    elif len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    else:
        raise ValueError(f"Unbekannte Taste „{parts[-1]}“")
    return mods, vk


class Hotkey:
    """Globales Tastenkürzel (nur Windows). callback(hwnd) läuft im Hotkey-Thread."""

    def __init__(self, combo: str, callback):
        self.combo, self.callback = combo, callback
        self.error: str | None = None
        self._thread_id = None
        if sys.platform != "win32":
            self.error = "Tastenkürzel gibt es nur unter Windows"
            return
        try:
            self.mods, self.vk = parse(combo)
        except ValueError as e:
            self.error = str(e)
            return
        ready = threading.Event()
        threading.Thread(target=self._loop, args=(ready,), daemon=True).start()
        ready.wait(2)

    @property
    def active(self) -> bool:
        return self.error is None and self._thread_id is not None

    def _loop(self, ready: threading.Event) -> None:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, self.mods | MOD_NOREPEAT, self.vk):
            self.error = f"{self.combo} ist schon von einem anderen Programm belegt"
            self._thread_id = None
            ready.set()
            return
        ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    self.callback(user32.GetForegroundWindow())
        finally:
            user32.UnregisterHotKey(None, 1)

    def stop(self) -> None:
        if self._thread_id:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread_id = None


class WindowsBridge:
    """Markierten Text aus dem aktiven Programm holen und Ergebnis dort einsetzen."""

    def __init__(self):
        import ctypes
        self.user32 = ctypes.windll.user32

    def _key(self, vk: int, up: bool = False) -> None:
        self.user32.keybd_event(vk, 0, KEYUP if up else 0, 0)

    def _ctrl(self, letter: str) -> None:
        self._key(VK_CONTROL)
        self._key(ord(letter))
        self._key(ord(letter), True)
        self._key(VK_CONTROL, True)

    def _wait_modifiers_released(self, timeout: float = 1.5) -> None:
        end = time.time() + timeout
        while time.time() < end:
            if not any(self.user32.GetAsyncKeyState(vk) & 0x8000
                       for vk in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN)):
                return
            time.sleep(0.02)

    def capture(self, hwnd) -> tuple[str, str | None]:
        """Gibt (markierter Text, alter Zwischenablage-Text) zurück. Läuft im Hintergrund-Thread."""
        self._wait_modifiers_released()
        old = winclip.get_text()
        before = winclip.sequence_number()
        self._ctrl("C")
        end = time.time() + 0.8
        while time.time() < end and winclip.sequence_number() == before:
            time.sleep(0.02)
        text = winclip.get_text() if winclip.sequence_number() != before else ""
        return text or "", old

    def deliver(self, hwnd, text: str, old: str | None) -> None:
        winclip.set_text(text)
        if hwnd:
            self.user32.SetForegroundWindow(hwnd)
            time.sleep(0.15)
        self._ctrl("V")
        time.sleep(0.4)  # Zielprogramm liest die Zwischenablage, danach alten Inhalt zurück
        if old is not None:
            winclip.set_text(old)

    def restore(self, old: str | None) -> None:
        if old is not None:
            winclip.set_text(old)


def bridge():
    return WindowsBridge() if sys.platform == "win32" else None
