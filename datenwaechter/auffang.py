"""Auffangfläche für den Drop-Schutz: legt sich beim Ziehen einer Datei über das Fenster einer KI-App.

Die Datei landet hier statt in der App; der Datenwächter prüft sie und übergibt erst danach (Original oder
geschwärzt). Halbdurchsichtig, damit man sieht, wohin man zieht.
"""

from __future__ import annotations

import sys
import tkinter as tk

try:
    from tkinterdnd2 import DND_FILES, DND_TEXT
except ImportError:  # ohne tkinterdnd2 gibt es keinen Drop-Schutz
    DND_FILES = DND_TEXT = None


class Auffangflaeche(tk.Toplevel):
    def __init__(self, master, *, font: str, on_drop):
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        try:
            self.attributes("-alpha", 0.86)
        except tk.TclError:
            pass
        self.on_drop = on_drop
        self.configure(bg="#14532d")
        rahmen = tk.Frame(self, bg="#14532d", highlightthickness=3, highlightbackground="#86efac")
        rahmen.pack(fill="both", expand=True, padx=10, pady=10)
        mitte = tk.Frame(rahmen, bg="#14532d")
        mitte.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(mitte, text="🛡", bg="#14532d", fg="white", font=(font, 40)).pack()
        tk.Label(mitte, text="Hier ablegen", bg="#14532d", fg="white", font=(font, 22, "bold")).pack(pady=(4, 2))
        self.unter = tk.Label(mitte, text="", bg="#14532d", fg="#dcfce7", font=(font, 12), justify="center")
        self.unter.pack()
        self._widgets = [self, rahmen, mitte, *mitte.winfo_children()]
        self.aktiv = False
        if DND_FILES:
            for w in self._widgets:
                w.drop_target_register(DND_FILES, DND_TEXT)
                w.dnd_bind("<<Drop>>", self._drop)

    def zeigen(self, rect: tuple[int, int, int, int], app: str, app_hwnd=None) -> None:
        """Über das Fenster der KI-App legen – direkt darüber, nicht über Fenster, die vor der App liegen."""
        left, top, right, bottom = rect
        self.unter.configure(text=f"Der Datenwächter prüft die Datei,\nbevor {app} sie bekommt.")
        self.geometry(f"{max(200, right - left)}x{max(150, bottom - top)}+{left}+{top}")
        self.deiconify()
        self.update_idletasks()
        if sys.platform == "win32" and app_hwnd:
            from . import schutz
            try:
                schutz.direkt_ueber(schutz.wurzel(self.winfo_id()), app_hwnd)
            except Exception:  # noqa: BLE001 – im Zweifel normal anzeigen
                self.lift()
        else:
            self.lift()
        self.aktiv = True

    def verstecken(self) -> None:
        self.aktiv = False
        if self.winfo_exists():
            self.withdraw()

    def _drop(self, event):
        daten, art = event.data, str(getattr(event, "type", "") or "")
        self.verstecken()
        self.on_drop(daten, "text" if "text" in art.lower() else "dateien")
        return getattr(event, "action", "copy")
