"""✨-Knopf beim Markieren (Windows): Text markieren → kleiner Knopf daneben → KI-Aktionen.

Fremde Rechtsklick-Menüs lassen sich unter Windows nicht erweitern. Deshalb melden zwei Hooks, wenn Text markiert wurde:
- Maus (WH_MOUSE_LL): Ziehen über Text oder Doppel-/Dreifachklick (Mauszeiger ist der Text-Cursor „I“).
- Tastatur (WH_KEYBOARD_LL): Strg+A („alles markieren“) und Umschalt + Pfeil/Pos1/Ende/Bild – sobald Umschalt
  losgelassen wird. Nicht im Explorer, auf dem Desktop, in Excel und in Konsolen (dort markiert man Dateien/Zellen).
Der Knopf nimmt keinen Fokus – die Markierung im Programm bleibt erhalten, ein Klick startet dieselben KI-Aktionen
wie Strg+Alt+Leertaste. Abschaltbar in „KI-Aktionen bearbeiten“.
"""

from __future__ import annotations

import json
import math
import os
import sys
import threading

from .settings import path as settings_path

WH_MOUSE_LL, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_QUIT = 14, 0x0201, 0x0202, 0x0012
WH_KEYBOARD_LL, WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 13, 0x0100, 0x0101, 0x0104, 0x0105
VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN, VK_A = 0x10, 0x11, 0x12, 0x5B, 0x5C, 0x41
SHIFT_TASTEN = {0x10, 0xA0, 0xA1}
MODIFIKATOREN = SHIFT_TASTEN | {0x11, 0xA2, 0xA3, 0x12, 0xA4, 0xA5, 0x5B, 0x5C, 0x14}
NAVIGATION = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28}   # Bild↑↓, Ende, Pos1, Pfeile
IDC_IBEAM = 32513
MIN_ZIEHEN = 10        # Pixel, ab denen ein Ziehen als Markieren zählt
TEXTFENSTER = ("edit", "richedit", "notepadtextbox", "scintilla", "_wwg")   # Fensterklassen mit Text
# Hier markiert Strg+A bzw. Umschalt+Pfeil Dateien, Zellen oder Konsolentext – kein Knopf
KEIN_TEXT_FENSTER = {"cabinetwclass", "explorewclass", "progman", "workerw", "shell_traywnd", "xlmain",
                     "consolewindowclass", "cascadia_hosting_window_class", "mintty", "putty", "virtualconsoleclass"}
KEIN_TEXT_FOKUS = {"syslistview32", "systreeview32", "directuihwnd", "excel7", "sysheader32", "systabcontrol32"}


def tastatur_ausgeschlossen(fenster_klasse: str, fokus_klasse: str = "") -> bool:
    """True, wenn Strg+A/Umschalt-Markieren dort keinen Text markiert (Explorer, Desktop, Excel, Konsolen, Listen)."""
    return fenster_klasse.lower() in KEIN_TEXT_FENSTER or fokus_klasse.lower() in KEIN_TEXT_FOKUS


def aktiv() -> bool:
    """Einstellung „✨-Knopf beim Markieren zeigen“ (Standard: an)."""
    try:
        return bool(json.loads(settings_path().read_text(encoding="utf-8")).get("auswahl_knopf", True))
    except (OSError, ValueError):
        return True


def speichern(an: bool) -> None:
    p = settings_path()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data["auswahl_knopf"] = bool(an)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class Waechter:
    """Meldet Markieren per Maus: callback("auswahl", x, y, hwnd) bzw. callback("klick", x, y, 0) bei jedem Klick.

    Der Rückruf läuft im Hook-Thread und muss sofort zurückkehren (nur in eine Queue legen).
    """

    def __init__(self, callback):
        self.callback = callback
        self.error: str | None = None
        self._thread_id = None
        self._down = None           # (x, y, Zeit, Text-Cursor?)
        self._last_down = None      # für Doppelklick
        self._klicks = 0
        self._alles = False         # Strg+A gedrückt – gemeldet beim Loslassen von A
        self._shift_markiert = False   # Umschalt + Pfeil/Pos1/Ende – gemeldet beim Loslassen von Umschalt
        self.knopf_offen = False       # setzt das Fenster: nur dann „weitergetippt“ melden (nicht jeden Tastendruck)
        if sys.platform != "win32":
            self.error = "nur unter Windows"
            return
        ready = threading.Event()
        threading.Thread(target=self._loop, args=(ready,), daemon=True, name="auswahl-hook").start()
        ready.wait(2)

    @property
    def active(self) -> bool:
        return self.error is None and self._thread_id is not None

    def _loop(self, ready: threading.Event) -> None:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32

        class MSLL(ctypes.Structure):
            _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        class KBDLL(ctypes.Structure):
            _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("active", wintypes.HWND),
                        ("focus", wintypes.HWND), ("capture", wintypes.HWND), ("menuOwner", wintypes.HWND),
                        ("moveSize", wintypes.HWND), ("caret", wintypes.HWND), ("rcCaret", wintypes.RECT)]

        class CURSORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hCursor", wintypes.HANDLE),
                        ("pt", wintypes.POINT)]

        LRESULT = ctypes.c_ssize_t
        Proc = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, Proc, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.LoadCursorW.restype = wintypes.HANDLE
        user32.GetForegroundWindow.restype = wintypes.HWND
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        ibeam = user32.LoadCursorW(None, IDC_IBEAM)
        doppel_ms = user32.GetDoubleClickTime()
        own_pid = os.getpid()

        user32.WindowFromPoint.argtypes = [wintypes.POINT]
        user32.WindowFromPoint.restype = wintypes.HWND
        name = ctypes.create_unicode_buffer(64)

        def text_cursor(x: int, y: int) -> bool:
            ci = CURSORINFO()
            ci.cbSize = ctypes.sizeof(CURSORINFO)
            if user32.GetCursorInfo(ctypes.byref(ci)) and ci.hCursor and ci.flags & 1:   # CURSOR_SHOWING
                if ci.hCursor == ibeam:
                    return True
            # Mauszeiger unbekannt/eigener Text-Cursor: an der Fensterklasse erkennen (Editor, Word, Notepad …)
            hwnd = user32.WindowFromPoint(wintypes.POINT(x, y))
            return bool(hwnd and user32.GetClassNameW(hwnd, name, 64) and name.value.lower().startswith(TEXTFENSTER))

        def fremdes_fenster():
            hwnd = user32.GetForegroundWindow()
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return hwnd if hwnd and pid.value != own_pid else None

        def klasse(hwnd) -> str:
            return name.value if hwnd and user32.GetClassNameW(hwnd, name, 64) else ""

        def gedrueckt(vk: int) -> bool:
            return bool(user32.GetAsyncKeyState(vk) & 0x8000)

        def tastatur_auswahl() -> None:
            """Per Tastatur markiert: Knopf an der Maus (liegt sie über dem Fenster), sonst am Text-Cursor."""
            hwnd = fremdes_fenster()
            if not hwnd:
                return
            info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
            tid = user32.GetWindowThreadProcessId(hwnd, None)
            hat_info = bool(user32.GetGUIThreadInfo(tid, ctypes.byref(info)))
            if tastatur_ausgeschlossen(klasse(hwnd), klasse(info.focus) if hat_info else ""):
                return
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            p = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(p))
            if not (r.left <= p.x < r.right and r.top <= p.y < r.bottom):
                if hat_info and info.caret:   # Maus woanders: an den Text-Cursor
                    p = wintypes.POINT(info.rcCaret.right, info.rcCaret.bottom)
                    user32.ClientToScreen(info.caret, ctypes.byref(p))
                if not (r.left <= p.x < r.right and r.top <= p.y < r.bottom):
                    p = wintypes.POINT((r.left + r.right) // 2, (r.top + r.bottom) // 2)
            self.callback("auswahl", p.x, p.y, hwnd)

        def tasten(n_code, w_param, l_param):
            try:
                if n_code >= 0:
                    vk = ctypes.cast(l_param, ctypes.POINTER(KBDLL)).contents.vk
                    if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        win_alt = gedrueckt(VK_MENU) or gedrueckt(VK_LWIN) or gedrueckt(VK_RWIN)
                        if vk == VK_A and gedrueckt(VK_CONTROL) and not gedrueckt(VK_SHIFT) and not win_alt:
                            self._alles = True
                        elif vk in NAVIGATION and gedrueckt(VK_SHIFT) and not win_alt:
                            self._shift_markiert = True
                        elif vk not in MODIFIKATOREN and vk not in NAVIGATION:
                            if self._alles or self._shift_markiert:
                                self._alles = self._shift_markiert = False
                            if self.knopf_offen and not gedrueckt(VK_CONTROL):
                                self.knopf_offen = False
                                self.callback("tippen", 0, 0, 0)   # getippt: Markierung ist weg, Knopf ausblenden
                    elif w_param in (WM_KEYUP, WM_SYSKEYUP):
                        if vk == VK_A and self._alles:
                            self._alles = False
                            tastatur_auswahl()
                        elif vk in SHIFT_TASTEN and self._shift_markiert:
                            self._shift_markiert = False
                            tastatur_auswahl()
            except Exception:  # noqa: BLE001 – ein Fehler hier darf nie die Tastatur blockieren
                pass
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        def proc(n_code, w_param, l_param):
            try:
                if n_code >= 0 and w_param in (WM_LBUTTONDOWN, WM_LBUTTONUP):
                    info = ctypes.cast(l_param, ctypes.POINTER(MSLL)).contents
                    # GetCursorPos liefert logische Koordinaten (passen zu Tk, auch bei 125/150 % Skalierung);
                    # info.pt wäre in physischen Pixeln
                    p = wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(p))
                    x, y, t = p.x, p.y, info.time
                    if w_param == WM_LBUTTONDOWN:
                        last = self._last_down
                        nah = last and t - last[2] <= doppel_ms and math.hypot(x - last[0], y - last[1]) <= 4
                        self._klicks = self._klicks + 1 if nah else 1
                        self._down = self._last_down = (x, y, t, text_cursor(x, y))
                        self.callback("klick", x, y, 0)
                    elif self._down:
                        dx, dy, _, war_text = self._down
                        self._down = None
                        if war_text and (math.hypot(x - dx, y - dy) >= MIN_ZIEHEN or self._klicks >= 2):
                            hwnd = fremdes_fenster()
                            if hwnd:
                                self.callback("auswahl", x, y, hwnd)
            except Exception:  # noqa: BLE001 – ein Fehler hier darf nie die Maus blockieren
                pass
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        self._proc = Proc(proc)      # Referenz halten, sonst räumt Python den Rückruf weg
        self._tasten = Proc(tasten)
        self._thread_id = kernel32.GetCurrentThreadId()
        modul = kernel32.GetModuleHandleW(None)
        hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, modul, 0)
        if not hook:
            self.error = "Maus-Hook nicht verfügbar"
            self._thread_id = None
            ready.set()
            return
        tasten_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._tasten, modul, 0)   # ohne: nur Maus
        ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnhookWindowsHookEx(hook)
            if tasten_hook:
                user32.UnhookWindowsHookEx(tasten_hook)

    def stop(self) -> None:
        if self._thread_id:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread_id = None
