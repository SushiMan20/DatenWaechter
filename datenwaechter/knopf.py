"""Der kleine schwebende „✨ KI“-Knopf, der beim Markieren erscheint (siehe auswahl.py)."""

from __future__ import annotations

import tkinter as tk


class Knopf(tk.Toplevel):
    """Kleiner schwebender „✨ KI“-Knopf am Mauszeiger. Nimmt keinen Fokus, verschwindet nach ein paar Sekunden."""

    ZEIT_MS = 4000

    def __init__(self, master, *, dark: bool, font: str, hotkey: str = ""):
        from .palette import FARBEN, _windows_polish
        from .toast import _no_activate
        super().__init__(master)
        c = FARBEN["dunkel" if dark else "hell"]
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=c["border"])
        self._on_click = None
        self._job = None
        self._hover = False
        inner = tk.Frame(self, bg=c["bg"], padx=10, pady=5, cursor="hand2")
        inner.pack(padx=1, pady=1)
        self.label = tk.Label(inner, text="✨ KI", bg=c["bg"], fg=c["accent"], font=(font, 10, "bold"), cursor="hand2")
        self.label.pack(side="left")
        self.hint = tk.Label(inner, text="Umschreiben …", bg=c["bg"], fg=c["muted"], font=(font, 9), cursor="hand2")
        self.hint.pack(side="left", padx=(6, 0))
        self.tooltip = f"KI-Aktionen für den markierten Text{f' (auch: {hotkey})' if hotkey else ''}"
        for w in (self, inner, self.label, self.hint):
            w.bind("<ButtonRelease-1>", self._klick)
            w.bind("<Enter>", lambda _e: self._set_hover(True))
            w.bind("<Leave>", lambda _e: self._set_hover(False))
        self.update_idletasks()
        _no_activate(self)
        _windows_polish(self)

    def zeigen(self, x: int, y: int, on_click) -> None:
        from .toast import work_area
        self._on_click = on_click
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        left, top, right, bottom = work_area(self, (x, y))   # Monitor unter der Maus, nicht der Hauptbildschirm
        px = min(max(left, x + 12), right - w - 4)
        py = y + 18 if y + 18 + h < bottom else y - h - 12
        self.geometry(f"+{px}+{max(top, py)}")
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self._zeitgeber()

    def sichtbar(self) -> bool:
        return bool(self.winfo_exists() and self.winfo_viewable())

    def enthaelt(self, x: int, y: int) -> bool:
        if not self.sichtbar():
            return False
        rx, ry = self.winfo_rootx(), self.winfo_rooty()
        return rx <= x <= rx + self.winfo_width() and ry <= y <= ry + self.winfo_height()

    def verstecken(self) -> None:
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        if self.winfo_exists():
            self.withdraw()

    def _zeitgeber(self) -> None:
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(self.ZEIT_MS, lambda: self._zeitgeber() if self._hover else self.verstecken())

    def _set_hover(self, an: bool) -> None:
        self._hover = an

    def _klick(self, _e=None) -> None:
        cb = self._on_click
        self.verstecken()
        if cb:
            cb()
