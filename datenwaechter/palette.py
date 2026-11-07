"""Moderne Aktionsleiste für KI-Aktionen (statt des grauen Standard-Menüs).

Schwebendes Fenster direkt neben dem Mauszeiger (auf dem Bildschirm, auf dem die Maus ist): Kopfzeile, Vorschau
des markierten Texts, Suchfeld, Aktionen mit Symbol und Hinweis, was mit dem Ergebnis passiert. Bedienung mit Maus
oder ↑ ↓ Enter Esc; Eingabe filtert – oder wird als eigene Anweisung ausgeführt. Nach der Wahl bleibt die Leiste an
ihrem Platz und zeigt einen drehenden Kreis, bis die KI fertig ist (Abbrechen jederzeit). Unter Windows 11 mit runden
Ecken und Schatten.
"""

from __future__ import annotations

import sys
import time
import tkinter as tk

from .actions import Aktion

SYMBOLE = [  # (Stichwort im Namen, Symbol) – nur Zeichen, die Tk überall darstellen kann
    ("umformulier", "✎"), ("kürz", "✂"), ("kuerz", "✂"), ("freundlich", "☺"), ("professionell", "◆"),
    ("rechtschreib", "✓"), ("korrigier", "✓"), ("übersetz", "⇄"), ("englisch", "⇄"), ("zusammenfass", "≡"),
    ("antwort", "↩"), ("tweet", "#"), ("mail", "✉"),
]
MODUS = {  # Hinweis rechts: Text, Farbe hell, Farbe dunkel
    "ersetzen": ("ersetzt", ("#e8f5e9", "#1b5e20"), ("#1f3322", "#81c784")),
    "einfuegen": ("fügt ein", ("#e3f2fd", "#0d47a1"), ("#172a3a", "#90caf9")),
    "anzeigen": ("zeigt an", ("#f3f4f6", "#4b5563"), ("#303036", "#c4c4cc")),
}
FARBEN = {
    "hell": {"bg": "#ffffff", "border": "#d4d4d8", "text": "#18181b", "muted": "#71717a", "hover": "#f4f4f5",
             "active": "#ecfdf3", "accent": "#2e7d32", "icon_bg": "#f4f4f5", "field": "#f4f4f5", "sep": "#e4e4e7"},
    "dunkel": {"bg": "#232326", "border": "#3f3f46", "text": "#f4f4f5", "muted": "#a1a1aa", "hover": "#2e2e33",
               "active": "#1f3322", "accent": "#66bb6a", "icon_bg": "#2e2e33", "field": "#2e2e33", "sep": "#34343a"},
}


def symbol(name: str) -> str:
    n = name.lower()
    return next((s for key, s in SYMBOLE if key in n), "✦")


def _windows_polish(win: tk.Toplevel) -> None:
    """Windows 11: runde Ecken + Schatten für das randlose Fenster (ältere Windows: einfach ohne)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        GCL_STYLE, CS_DROPSHADOW = -26, 0x00020000
        get = getattr(ctypes.windll.user32, "GetClassLongPtrW", ctypes.windll.user32.GetClassLongW)
        put = getattr(ctypes.windll.user32, "SetClassLongPtrW", ctypes.windll.user32.SetClassLongW)
        put(hwnd, GCL_STYLE, get(hwnd, GCL_STYLE) | CS_DROPSHADOW)
    except Exception:  # noqa: BLE001 – rein optisch
        pass


class ActionPalette(tk.Toplevel):
    WIDTH = 360

    def __init__(self, master, aktionen: list[Aktion], preview: str, *, dark: bool, font: str,
                 server: str | None, on_choose, on_cancel, on_edit=None, xy: tuple[int, int] | None = None):
        super().__init__(master)
        self.c = FARBEN["dunkel" if dark else "hell"]
        self.dark, self.font = dark, font
        self.aktionen, self.on_choose, self.on_cancel, self.on_edit = aktionen, on_choose, on_cancel, on_edit
        self.server = server
        self.rows: list[tuple[tk.Frame, Aktion]] = []
        self.visible: list[Aktion] = []
        self.index = 0
        self._closed = False
        self._had_focus = False
        self.modus = "auswahl"           # auswahl → arbeitet → fertig
        self._on_abbrechen = None
        self._ueber_zeiger = False       # am unteren Rand oberhalb der Maus platziert

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        c = self.c
        self.configure(bg=c["border"])
        body = self.body = tk.Frame(self, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=1, pady=1)

        # Kopfzeile
        head = tk.Frame(body, bg=c["bg"])
        head.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(head, text="✦", bg=c["bg"], fg=c["accent"], font=(font, 12, "bold")).pack(side="left")
        tk.Label(head, text="Mit KI bearbeiten", bg=c["bg"], fg=c["text"], font=(font, 11, "bold")).pack(
            side="left", padx=(6, 0))
        anzeige = server or "kein KI-Server"
        anzeige = anzeige if len(anzeige) <= 24 else anzeige[:23] + "…"
        tk.Label(head, text=anzeige, bg=c["bg"], fg=c["muted"] if server else "#c62828",
                 font=(font, 8)).pack(side="right")

        # Vorschau der Markierung
        snippet = " ".join(preview.split())
        snippet = snippet if len(snippet) <= 90 else snippet[:87] + "…"
        tk.Label(body, text=f"„{snippet}“", bg=c["bg"], fg=c["muted"], font=(font, 9, "italic"), anchor="w",
                 justify="left", wraplength=self.WIDTH - 30).pack(fill="x", padx=14, pady=(0, 8))

        # Suchfeld
        field = self.field = tk.Frame(body, bg=c["field"])
        field.pack(fill="x", padx=12)
        tk.Label(field, text="⌕", bg=c["field"], fg=c["muted"], font=(font, 11)).pack(side="left", padx=(10, 2))
        self.query = tk.StringVar()
        self.entry = tk.Entry(field, textvariable=self.query, bg=c["field"], fg=c["text"], relief="flat",
                              insertbackground=c["text"], font=(font, 10), highlightthickness=0, bd=0)
        self.entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(2, 10))
        self._placeholder(True)

        self.list = tk.Frame(body, bg=c["bg"])
        self.list.pack(fill="x", padx=6, pady=(8, 4))

        self.sep = tk.Frame(body, bg=c["sep"], height=1)
        self.sep.pack(fill="x")
        foot = self.foot = tk.Frame(body, bg=c["bg"])
        foot.pack(fill="x", padx=14, pady=7)
        tk.Label(foot, text="↑↓ wählen   ↵ ausführen   Esc schließen", bg=c["bg"], fg=c["muted"],
                 font=(font, 8)).pack(side="left")
        if on_edit:
            edit = tk.Label(foot, text="Bearbeiten", bg=c["bg"], fg=c["accent"], font=(font, 8, "underline"),
                            cursor="hand2")
            edit.pack(side="right")
            edit.bind("<Button-1>", lambda e: self._finish(self.on_edit))

        self.query.trace_add("write", lambda *_: self._render())
        for key, fn in (("<Down>", lambda e: self._move(1)), ("<Up>", lambda e: self._move(-1)),
                        ("<Tab>", lambda e: self._move(1)), ("<Return>", lambda e: self.choose()),
                        ("<Escape>", lambda e: self.cancel())):
            self.entry.bind(key, lambda e, fn=fn: (fn(e), "break")[1])
        self.bind("<FocusIn>", lambda e: setattr(self, "_had_focus", True))
        self.bind("<FocusOut>", self._focus_out)
        self._render()
        self._place(xy)
        _windows_polish(self)
        self.after(10, self._grab_focus)

    # ------------------------------------------------------------------ Darstellung
    def _placeholder(self, on: bool) -> None:
        self._ph = on
        if on:
            self.entry.insert(0, "Suchen oder eigene Anweisung …")
            self.entry.configure(fg=self.c["muted"])
            self.entry.bind("<Key>", self._clear_placeholder, add="+")

    def _clear_placeholder(self, e=None):
        if self._ph and (e is None or e.keysym not in ("Up", "Down", "Return", "Escape", "Tab")):
            self._ph = False
            self.entry.delete(0, "end")
            self.entry.configure(fg=self.c["text"])

    def _text(self) -> str:
        return "" if self._ph else self.query.get().strip()

    def _render(self) -> None:
        for w in self.list.winfo_children():
            w.destroy()
        self.rows.clear()
        q = self._text().lower()
        if q != getattr(self, "_last_q", None):   # neue Eingabe: Auswahl auf den besten Treffer
            self._last_q = q
            self.index = 0
        self.visible = [a for a in self.aktionen if not q or q in a.name.lower()]
        items = list(self.visible)
        if q and not any(a.name.lower() == q for a in self.visible):
            items.append(Aktion(f"„{self._text()}“ als Anweisung", self._text(), "ersetzen"))
        for a in items:
            self._row(a, custom=a not in self.visible)
        self.index = min(self.index, max(0, len(self.rows) - 1))
        self._highlight()

    def _row(self, a: Aktion, custom: bool) -> None:
        c = self.c
        row = tk.Frame(self.list, bg=c["bg"], cursor="hand2")
        row.pack(fill="x", pady=1)
        icon = tk.Label(row, text="✦" if custom else symbol(a.name), width=2, bg=c["icon_bg"], fg=c["accent"],
                        font=(self.font, 11))
        icon.pack(side="left", padx=(8, 10), pady=3, ipadx=3)
        name = tk.Label(row, text=a.name, bg=c["bg"], fg=c["text"], font=(self.font, 10), anchor="w")
        name.pack(side="left", fill="x", expand=True)
        widgets = [row, name, icon]
        if a.modus != "ersetzen" or custom:   # Standard (ersetzen) braucht keinen Hinweis
            label, light, dark = MODUS[a.modus]
            pbg, pfg = dark if self.dark else light
            pill = tk.Label(row, text="eigene Anweisung" if custom else label, bg=pbg, fg=pfg, font=(self.font, 8),
                            padx=7, pady=1)
            pill.pack(side="right", padx=8)
            widgets.append(pill)
        i = len(self.rows)
        for w in widgets:
            w.bind("<Enter>", lambda e, i=i: self._set(i))
            w.bind("<Button-1>", lambda e, i=i: (self._set(i), self.choose()))
        row.marks = (row, name)  # Teile, die beim Hervorheben die Farbe wechseln
        self.rows.append((row, a))

    def _highlight(self) -> None:
        for i, (row, _) in enumerate(self.rows):
            bg = self.c["active"] if i == self.index else self.c["bg"]
            for w in row.marks:
                w.configure(bg=bg)

    def _set(self, i: int) -> None:
        self.index = i
        self._highlight()

    def _move(self, d: int) -> None:
        if self.rows:
            self._set((self.index + d) % len(self.rows))

    def _place(self, xy) -> None:
        """Direkt neben den Mauszeiger – auf dem Monitor, auf dem die Maus ist; am Rand links bzw. oberhalb."""
        from .toast import neben_zeiger, zeiger
        self.update_idletasks()
        w, h = self.WIDTH, self.winfo_reqheight()
        mx, my = xy or zeiger(self)
        x, y = neben_zeiger(self, w, h, mx, my)
        self._ueber_zeiger = y < my
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _groesse_anpassen(self) -> None:
        """Nach dem Umschalten: gleiche Stelle, neue Höhe (oberhalb der Maus: untere Kante bleibt)."""
        x, y, alt = self.winfo_x(), self.winfo_y(), self.winfo_height()
        self.update_idletasks()
        h = self.winfo_reqheight()
        if self._ueber_zeiger:
            y += alt - h
        self.geometry(f"{self.WIDTH}x{h}+{x}+{y}")

    def _grab_focus(self) -> None:
        if self._closed:
            return
        self.lift()
        self.focus_force()
        self.entry.focus_set()
        self.entry.icursor("end")

    # ------------------------------------------------------------------ Auswahl
    def choose(self, i: int | None = None) -> None:
        """Aktion gewählt: Die Leiste bleibt offen – der Aufrufer schaltet auf „arbeitet“ (oder schließt sie)."""
        if self.modus != "auswahl":
            return
        if i is not None:
            self._set(i)
        if not self.rows:
            return
        aktion = self.rows[self.index][1]
        if aktion not in self.aktionen:  # eigene Anweisung
            aktion = Aktion("Eigene Anweisung", aktion.anweisung, "ersetzen")
        self.modus = "gewaehlt"
        self.on_choose(aktion)

    # ------------------------------------------------------------------ Während die KI arbeitet
    def arbeiten(self, name: str, on_abbrechen) -> None:
        """Gleiche Stelle, statt der Liste: drehender Kreis, Name der Aktion, Sekunden, „Abbrechen“."""
        if self._closed:
            return
        c = self.c
        self.modus = "arbeitet"
        self._on_abbrechen = on_abbrechen
        for w in (self.field, self.list, self.sep, self.foot):
            w.pack_forget()
        self.arbeit = tk.Frame(self.body, bg=c["bg"])
        self.arbeit.pack(fill="x", padx=14, pady=(2, 14))
        self.kreis = tk.Canvas(self.arbeit, width=28, height=28, bg=c["bg"], highlightthickness=0)
        self.kreis.pack(side="left")
        self.kreis.create_oval(4, 4, 24, 24, outline=c["sep"], width=3)
        self._bogen = self.kreis.create_arc(4, 4, 24, 24, start=90, extent=-110, style="arc", outline=c["accent"],
                                            width=3)
        self._winkel = 90
        self.knopf = tk.Label(self.arbeit, text="Abbrechen", bg=c["bg"], fg=c["accent"], cursor="hand2",
                              font=(self.font, 9, "underline"))
        self.knopf.pack(side="right", anchor="n")   # zuerst: behält seinen Platz, auch bei langem Text
        self.knopf.bind("<Button-1>", lambda e: self._abbrechen())
        texte = tk.Frame(self.arbeit, bg=c["bg"])
        texte.pack(side="left", fill="x", expand=True, padx=(10, 8))
        self.arbeit_titel = tk.Label(texte, text=f"{name} …", bg=c["bg"], fg=c["text"], font=(self.font, 10, "bold"),
                                     anchor="w")
        self.arbeit_titel.pack(fill="x")
        self.arbeit_info = tk.Label(texte, text="KI arbeitet", bg=c["bg"], fg=c["muted"], font=(self.font, 8),
                                    anchor="w", justify="left", wraplength=self.WIDTH - 140)
        self.arbeit_info.pack(fill="x")
        self.bind("<Escape>", lambda e: self._abbrechen())
        self._start = time.monotonic()
        self._groesse_anpassen()
        self._drehen()
        self._sekunden()

    def _drehen(self) -> None:
        if self._closed or self.modus != "arbeitet":
            return
        self._winkel = (self._winkel - 14) % 360
        self.kreis.itemconfigure(self._bogen, start=self._winkel)
        self.after(40, self._drehen)

    def _sekunden(self) -> None:
        if self._closed or self.modus != "arbeitet":
            return
        s = int(time.monotonic() - self._start)
        self.arbeit_info.configure(text="KI arbeitet" + (f" · {s} s" if s else ""))
        self.after(1000, self._sekunden)

    def _abbrechen(self) -> None:
        if self.modus == "arbeitet" and self._on_abbrechen:
            self._on_abbrechen()
        self.schliessen()

    def fertig(self, text: str, ms: int = 900) -> None:
        """Häkchen statt Kreis, kurz stehen lassen, dann schließen."""
        if self._closed or not hasattr(self, "kreis"):
            return self.schliessen()
        self.modus = "fertig"
        self.kreis.delete("all")
        self.kreis.create_oval(4, 4, 24, 24, outline=self.c["accent"], width=3)
        self.kreis.create_text(14, 14, text="✓", fill=self.c["accent"], font=(self.font, 11, "bold"))
        self.arbeit_titel.configure(text=text)
        self.arbeit_info.configure(text="")
        self.knopf.pack_forget()
        self.after(ms, self.schliessen)

    def fehler(self, text: str, ms: int = 12000) -> None:
        """Fehler an derselben Stelle zeigen (schließt sich nach einiger Zeit oder mit „Schließen“)."""
        if self._closed or not hasattr(self, "kreis"):
            return
        self.modus = "fertig"
        warn = "#c62828" if not self.dark else "#ef9a9a"
        self.kreis.delete("all")
        self.kreis.create_oval(4, 4, 24, 24, outline=warn, width=3)
        self.kreis.create_text(14, 14, text="!", fill=warn, font=(self.font, 11, "bold"))
        self.arbeit_titel.configure(text="Hat nicht geklappt", fg=warn)
        self.arbeit_info.configure(text=text)
        self.knopf.configure(text="Schließen")
        self.knopf.bind("<Button-1>", lambda e: self.schliessen())
        self._groesse_anpassen()
        self.after(ms, self.schliessen)

    def schliessen(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.modus = "fertig"
        if self.winfo_exists():
            self.destroy()

    def cancel(self) -> None:
        self._finish(self.on_cancel)

    def _finish(self, fn) -> None:
        if self._closed:
            return
        self._closed = True
        self.destroy()
        if fn:
            fn()

    def _focus_out(self, e) -> None:
        # Klick in ein anderes Programm = abbrechen (kurz warten: Fokus springt auch innerhalb des Fensters).
        # Nach der Wahl nicht: die KI arbeitet, das Ergebnis wird ins Programm eingefügt.
        if self._had_focus and self.modus == "auswahl":
            self.after(150, lambda: (not self._closed and self.focus_get() is None) and self.cancel())

    def type(self, text: str) -> None:
        """Für Tests: Eingabe ins Suchfeld."""
        self._clear_placeholder()
        self.query.set(text)
