"""Kompakte Benachrichtigung unten rechts über dem Infobereich (statt eines großen Warnfensters).

Wie eine Windows-Benachrichtigung: kurze Zusammenfassung, ein bis drei Knöpfe, „Details“ für die volle Liste.
Nimmt dem aktiven Programm nicht den Fokus weg (man will ja gleich einfügen). Verschwindet auf Wunsch nach
einigen Sekunden von selbst; solange die Maus darüber ist, bleibt sie stehen.
"""

from __future__ import annotations

import base64
import io
import sys
import tkinter as tk

from .icons import shield
from .palette import FARBEN, _windows_polish

_IMAGES: dict = {}   # Tk-Bilder einmal anlegen und behalten (nie in fremden Threads aufräumen lassen)


def _image(master, state: str, size: int) -> tk.PhotoImage:
    # je Tk-Interpreter zwischenspeichern (ein neues Fenster-Programm im selben Prozess hat einen neuen)
    cache = _IMAGES.setdefault(id(master.tk), {})
    key = (state, size)
    if key not in cache:
        buf = io.BytesIO()
        shield(state, size).save(buf, "PNG")
        cache[key] = tk.PhotoImage(master=master, data=base64.b64encode(buf.getvalue()).decode())
    return cache[key]

WIDTH = 368
MARGIN = 14
LEVEL = {"warnung": ("warnung", "#c62828", "#ff8a80"), "thema": ("pause", "#b45309", "#ffb74d"),
         "ok": ("aktiv", "#2e7d32", "#81c784")}


def work_area(win: tk.Misc) -> tuple[int, int, int, int]:
    """Bildschirmbereich ohne Taskleiste (links, oben, rechts, unten)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            r = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):  # SPI_GETWORKAREA
                return r.left, r.top, r.right, r.bottom
        except Exception:  # noqa: BLE001
            pass
    return 0, 0, win.winfo_screenwidth(), win.winfo_screenheight() - 48


def _no_activate(win: tk.Toplevel) -> None:
    """Windows: Fenster bei Klick nicht aktivieren – der Fokus bleibt im Programm, in das man einfügen will."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        GWL_EXSTYLE, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = -20, 0x08000000, 0x00000080
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception:  # noqa: BLE001
        pass


class TrayPopup(tk.Toplevel):
    current: "TrayPopup | None" = None   # immer nur eine Benachrichtigung gleichzeitig

    def __init__(self, master, *, dark: bool, font: str, level: str, title: str, summary: str = "",
                 topic: str = "", status: str = "", actions=(), on_details=None, timeout_ms: int | None = None,
                 on_timeout=None, on_close=None):
        alt = TrayPopup.current
        if alt is not None:
            try:
                if alt.winfo_exists():
                    alt.close(silent=True)
            except tk.TclError:   # gehört zu einem schon beendeten Fenster-Programm
                pass
            TrayPopup.current = None
        super().__init__(master)
        TrayPopup.current = self
        c = FARBEN["dunkel" if dark else "hell"]
        icon_state, color_light, color_dark = LEVEL[level]
        color = color_dark if dark else color_light
        self.c, self.font = c, font
        self.on_timeout, self.on_close = on_timeout, on_close
        self._closed = False
        self._remaining = timeout_ms
        self._hover = False

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=c["border"])
        body = tk.Frame(self, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=1, pady=1)

        # Kopfzeile: Schild, Titel, Schließen
        head = tk.Frame(body, bg=c["bg"])
        head.pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(head, image=_image(master, icon_state, 22), bg=c["bg"]).pack(side="left")
        tk.Label(head, text=title, bg=c["bg"], fg=c["text"], font=(font, 10, "bold"), anchor="w").pack(
            side="left", padx=(8, 0), fill="x", expand=True)
        x = tk.Label(head, text="✕", bg=c["bg"], fg=c["muted"], font=(font, 10), cursor="hand2")
        x.pack(side="right")
        x.bind("<Button-1>", lambda e: self.close())

        text = tk.Frame(body, bg=c["bg"])
        text.pack(fill="x", padx=(44, 14))
        if summary:
            tk.Label(text, text=summary, bg=c["bg"], fg=c["text"], font=(font, 9), anchor="w", justify="left",
                     wraplength=WIDTH - 64).pack(fill="x")
        if topic:
            tk.Label(text, text=topic, bg=c["bg"], fg=color, font=(font, 9), anchor="w", justify="left",
                     wraplength=WIDTH - 64).pack(fill="x", pady=(2, 0))
        if status:
            tk.Label(text, text=status, bg=c["bg"], fg=c["muted"], font=(font, 8), anchor="w", justify="left",
                     wraplength=WIDTH - 64).pack(fill="x", pady=(4, 0))

        # Knöpfe
        row = tk.Frame(body, bg=c["bg"])
        row.pack(fill="x", padx=(44, 14), pady=(10, 12))
        self.buttons = {}
        for label, fn, primary in actions:
            b = tk.Label(row, text=label, cursor="hand2", font=(font, 9, "bold" if primary else "normal"),
                         bg=c["accent"] if primary else c["hover"], fg="white" if primary else c["text"],
                         padx=10, pady=4)
            b.pack(side="left", padx=(0, 6))
            b.bind("<Button-1>", lambda e, fn=fn: self._act(fn))
            self.buttons[label] = b
        if on_details:
            d = tk.Label(row, text="Details", cursor="hand2", font=(font, 9, "underline"), bg=c["bg"], fg=c["accent"])
            d.pack(side="right")
            d.bind("<Button-1>", lambda e: self._act(on_details))
            self.buttons["Details"] = d

        # Laufzeit-Leiste (zeigt, wann die Benachrichtigung von selbst verschwindet)
        self.bar = tk.Frame(body, bg=color, height=3)
        if timeout_ms:
            self.bar.pack(fill="x", side="bottom")
            self._total = timeout_ms

        for w in (self, body):
            w.bind("<Enter>", lambda e: setattr(self, "_hover", True))
            w.bind("<Leave>", lambda e: setattr(self, "_hover", False))

        self._place()
        _windows_polish(self)
        _no_activate(self)
        if timeout_ms:
            self.after(100, self._tick)

    def _place(self) -> None:
        self.update_idletasks()
        h = self.winfo_reqheight()
        left, top, right, bottom = work_area(self)
        self._x, self._y = right - WIDTH - MARGIN, bottom - h - MARGIN
        self.geometry(f"{WIDTH}x{h}+{self._x}+{self._y + 24}")
        self._slide(24)

    def _slide(self, offset: int) -> None:  # kurz von unten hereingleiten
        if self._closed:
            return
        self.geometry(f"+{self._x}+{self._y + offset}")
        if offset > 0:
            self.after(12, self._slide, max(0, offset - 6))

    def _tick(self) -> None:
        if self._closed:
            return
        if not self._hover:
            self._remaining -= 100
            frac = max(0.0, self._remaining / self._total)
            self.bar.configure(width=int(WIDTH * frac))
            self.bar.pack_configure(fill="none", anchor="w")
        if self._remaining <= 0:
            self.close(timeout=True)
            return
        self.after(100, self._tick)

    def _act(self, fn) -> None:
        self.close(silent=True)
        if fn:
            fn()

    def close(self, timeout: bool = False, silent: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        if TrayPopup.current is self:
            TrayPopup.current = None
        self.destroy()
        if silent:
            return
        cb = self.on_timeout if timeout and self.on_timeout else self.on_close
        if cb:
            cb()
