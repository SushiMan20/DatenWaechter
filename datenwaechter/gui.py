"""Das Datenwächter-Fenster (Windows) mit Symbol im Infobereich (Tray).

- überwacht die Zwischenablage: Text, im Explorer kopierte Dateien und Bilder (Screenshots)
- warnt mit einer Liste der Funde und dem Inhalts-Check („Du lädst gerade Familienunterlagen hoch“)
- nimmt Dateien per Drag & Drop entgegen und erzeugt anonymisierte bzw. geschwärzte Kopien
- übersetzt KI-Antworten mit Platzhaltern wieder zurück
- Tray-Symbol: grün = aktiv, orange = pausiert, blau = prüft, rot = Warnung; Schließen = weiter im Hintergrund
"""

from __future__ import annotations

import datetime as dt
import os
from collections import deque
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import actions, autostart, browser_bridge, content_check, hotkey, llm, ocr, settings, winclip
from .analysis import analyze, anonymize as anonymize_report
from .anonymize import Anonymizer
from .detectors import HOCH, SEVERITY_LABEL, scan_text
from .faces import available as faces_available
from .icons import FARBEN, shield
from .palette import ActionPalette
from .toast import TrayPopup
from .stats import Stats
from .tray import Tray

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

POLL_MS = 200
MIN_CONTENT_CHECK = 400   # kopierte Texte erst ab dieser Länge auf Themen prüfen (sonst zu viele Hinweise)
TEMP_DIR = Path(tempfile.gettempdir()) / "datenwaechter"
COLORS = {HOCH: "#c62828", 2: "#ef6c00", 1: "#757575", 0: "#1565c0"}
FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"

THEMES = {
    "hell": {"bg": "#f3f4f6", "card": "#ffffff", "text": "#1f2937", "muted": "#6b7280", "border": "#d1d5db",
             "drop": "#f9fafb", "drop_hover": "#e8f5e9", "button": "#e5e7eb", "button_hover": "#d1d5db"},
    "dunkel": {"bg": "#18181b", "card": "#27272a", "text": "#f4f4f5", "muted": "#a1a1aa", "border": "#3f3f46",
               "drop": "#202023", "drop_hover": "#1b2e1d", "button": "#3f3f46", "button_hover": "#52525b"},
}
STATUS_TEXT = {
    "aktiv": ("Schutz aktiv", "Zwischenablage und Dateien werden geprüft"),
    "pause": ("Schutz pausiert", "Klicke auf den Schalter, um ihn wieder einzuschalten"),
    "pruefe": ("Prüfe …", "Einen Moment – Inhalt wird lokal untersucht"),
    "warnung": ("Achtung", "Sensible Daten gefunden – bitte entscheiden"),
}


def _windows_dark() -> bool:
    if os.environ.get("DATENWAECHTER_THEME") in ("dunkel", "hell"):
        return os.environ["DATENWAECHTER_THEME"] == "dunkel"
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


class Switch(tk.Canvas):
    """Ein/Aus-Schalter im Stil von Windows 11."""

    def __init__(self, master, variable: tk.BooleanVar, command, bg: str, off: str):
        super().__init__(master, width=56, height=30, bg=bg, highlightthickness=0, cursor="hand2")
        self.var, self.command, self.off = variable, command, off
        self.bind("<Button-1>", lambda e: (self.var.set(not self.var.get()), self.command()))
        self.var.trace_add("write", lambda *_: self.draw())
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        on = self.var.get()
        color = FARBEN["aktiv"] if on else self.off
        self.create_oval(2, 2, 30, 28, fill=color, outline=color)
        self.create_oval(26, 2, 54, 28, fill=color, outline=color)
        self.create_rectangle(16, 2, 40, 28, fill=color, outline=color)
        x = 40 if on else 16
        self.create_oval(x - 11, 4, x + 11, 26, fill="white", outline="white")


class App:
    def __init__(self, start_hidden: bool = False) -> None:
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title("Datenwächter")
        self.root.geometry("420x520")
        self.root.minsize(380, 480)
        self.t = THEMES["dunkel" if _windows_dark() else "hell"]
        self.root.configure(bg=self.t["bg"])

        self.anon = Anonymizer()
        self.stats = Stats()
        self.results: queue.Queue = queue.Queue()
        self.watch = tk.BooleanVar(value=True)
        self.safe = tk.BooleanVar(value=True)
        self.use_ki = tk.BooleanVar(value=settings.load_llm().ki_namen)
        self.use_llm = tk.BooleanVar(value=False)
        self.topmost = tk.BooleanVar(value=False)
        self.llm_text = tk.StringVar(value="Inhalts-Check mit KI (Server wird gesucht …)")
        self.llm_ok = False
        self.llm_box = None
        self._last_seq = winclip.sequence_number()
        self._last_text = self._tk_clipboard_text()
        self._ignore_seq: int | None = None
        self._busy = False
        self._alerts = 0
        self._pause_job = None
        self._icons = {}
        self._hint_shown = False
        self._log: deque = deque(maxlen=4)
        self._suspend = False      # während einer KI-Aktion die Zwischenablage nicht prüfen
        self._ki_busy = False
        self._ki_popup = None
        self._ki_palette = None
        self._llm_info = None
        self._last_popup = None
        self.bridge = hotkey.bridge()
        self.hotkey = None

        self._build()
        self.tray = Tray(lambda name: self.results.put(("ui", name)), self.watch.get, self.stats.summary)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._start_hotkey()
        self._refresh()
        self.root.after(POLL_MS, self._poll)
        threading.Thread(target=self._detect_llm, daemon=True).start()
        if start_hidden and self.tray.available:
            self.root.withdraw()

    # ------------------------------------------------------------------ Aufbau
    def _img(self, state: str, size: int):
        """Schild als Tk-Bild (PNG direkt an Tk – braucht kein PIL.ImageTk)."""
        import base64
        import io
        key = (state, size)
        if key not in self._icons:
            buf = io.BytesIO()
            shield(state, size).save(buf, "PNG")
            self._icons[key] = tk.PhotoImage(data=base64.b64encode(buf.getvalue()).decode())
        return self._icons[key]

    def _button(self, master, text: str, command):
        t = self.t
        b = tk.Label(master, text=text, bg=t["button"], fg=t["text"], font=(FONT, 9), padx=10, pady=7, cursor="hand2")
        b.bind("<Button-1>", lambda e: command())
        b.bind("<Enter>", lambda e: b.configure(bg=t["button_hover"]))
        b.bind("<Leave>", lambda e: b.configure(bg=t["button"]))
        return b

    def _build(self) -> None:
        t = self.t
        self.root.iconphoto(True, self._img("aktiv", 64))
        outer = tk.Frame(self.root, bg=t["bg"])
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        # Statuskarte: großes Schild, Zustand, Schalter
        card = tk.Frame(outer, bg=t["card"], highlightthickness=1, highlightbackground=t["border"])
        card.pack(fill="x")
        self.status_icon = tk.Label(card, bg=t["card"])
        self.status_icon.pack(side="left", padx=(14, 10), pady=14)
        texts = tk.Frame(card, bg=t["card"])
        texts.pack(side="left", fill="x", expand=True)
        self.status_title = tk.Label(texts, bg=t["card"], fg=t["text"], font=(FONT, 15, "bold"), anchor="w")
        self.status_title.pack(fill="x")
        self.status_sub = tk.Label(texts, bg=t["card"], fg=t["muted"], font=(FONT, 9), anchor="w", justify="left",
                                   wraplength=220)
        self.status_sub.pack(fill="x")
        Switch(card, self.watch, self._toggle, t["card"], t["border"]).pack(side="right", padx=14)

        # Ablagefläche
        self.drop = tk.Frame(outer, bg=t["drop"], highlightthickness=2, highlightbackground=t["border"], cursor="hand2")
        self.drop.pack(fill="x", pady=12)
        l1 = tk.Label(self.drop, text="⬇", bg=t["drop"], fg=t["muted"], font=(FONT, 20))
        l2 = tk.Label(self.drop, text="Datei hierher ziehen", bg=t["drop"], fg=t["text"], font=(FONT, 11, "bold"))
        l3 = tk.Label(self.drop, text="PDF, Word, Bild, Text – oder klicken zum Auswählen", bg=t["drop"],
                      fg=t["muted"], font=(FONT, 9))
        for w in (l1, l2, l3):
            w.pack(pady=(0, 0))
        l1.pack_configure(pady=(10, 0))
        l3.pack_configure(pady=(0, 12))
        drop_widgets = (self.drop, l1, l2, l3)
        for w in drop_widgets:
            w.bind("<Button-1>", lambda e: self._pick_files())
            w.bind("<Enter>", lambda e: [x.configure(bg=t["drop_hover"]) for x in drop_widgets])
            w.bind("<Leave>", lambda e: [x.configure(bg=t["drop"]) for x in drop_widgets])
        if TkinterDnD:
            for w in drop_widgets:
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", lambda e: self._check_files(list(self.root.tk.splitlist(e.data)), "drop"))

        # Tageszähler
        tiles = tk.Frame(outer, bg=t["bg"])
        tiles.pack(fill="x")
        self.counters = {}
        for i, (key, label, color) in enumerate((("geprueft", "geprüft", t["text"]), ("gewarnt", "gewarnt", FARBEN["warnung"]),
                                                 ("anonymisiert", "anonymisiert", FARBEN["aktiv"]))):
            tile = tk.Frame(tiles, bg=t["card"], highlightthickness=1, highlightbackground=t["border"])
            tile.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            tiles.columnconfigure(i, weight=1)
            num = tk.Label(tile, text="0", bg=t["card"], fg=color, font=(FONT, 18, "bold"))
            num.pack(pady=(8, 0))
            tk.Label(tile, text=label, bg=t["card"], fg=t["muted"], font=(FONT, 9)).pack(pady=(0, 8))
            self.counters[key] = num
        tk.Label(outer, text="heute", bg=t["bg"], fg=t["muted"], font=(FONT, 8)).pack(anchor="e")

        # Letzte Aktivität
        tk.Label(outer, text="ZULETZT", bg=t["bg"], fg=t["muted"], font=(FONT, 8, "bold"), anchor="w").pack(
            fill="x", pady=(6, 2))
        self.log_labels = []
        for i in range(self._log.maxlen):
            lbl = tk.Label(outer, text="Noch nichts geprüft" if i == 0 else "", bg=t["bg"], fg=t["muted"],
                           font=(FONT, 9), anchor="w", justify="left", wraplength=380)
            lbl.pack(fill="x")
            self.log_labels.append(lbl)

        # Knöpfe
        btns = tk.Frame(outer, bg=t["bg"])
        btns.pack(side="bottom", fill="x", pady=(12, 0))
        for i, (text, cmd) in enumerate((("↩ Zurückübersetzen", self._restore_clipboard),
                                         ("Zuordnung", self._show_mapping), ("⚙ Einstellungen", self._settings_window))):
            self._button(btns, text, cmd).grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            btns.columnconfigure(i, weight=1)

    def _settings_window(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Datenwächter – Einstellungen")
        win.transient(self.root)
        frm = ttk.Frame(win, padding=14)
        frm.pack(fill="both", expand=True)
        ttk.Checkbutton(frm, text="Sicherer Modus (Zwischenablage sofort anonymisieren)", variable=self.safe).pack(
            anchor="w", pady=2)
        self.llm_box = ttk.Checkbutton(frm, textvariable=self.llm_text, variable=self.use_llm)
        self.llm_box.pack(anchor="w", pady=2)
        if not self.llm_ok:
            self.llm_box.state(["disabled"])
        ttk.Button(frm, text="KI-Server einrichten (API-Adresse + Token) …", command=self._llm_settings).pack(
            anchor="w", padx=22, pady=(0, 6))
        hk = (f"Tastenkürzel {self.hotkey.combo}: markierten Text in jedem Programm bearbeiten"
              if self.hotkey and self.hotkey.active else
              f"Tastenkürzel: {self.hotkey.error if self.hotkey else 'nur unter Windows'}")
        ttk.Button(frm, text="KI-Aktionen (Umformulieren …) bearbeiten …", command=self._actions_editor).pack(
            anchor="w", padx=22)
        ttk.Label(frm, text=hk, foreground="#777").pack(anchor="w", padx=22, pady=(0, 6))
        ttk.Checkbutton(frm, text="Fenster immer im Vordergrund", variable=self.topmost,
                        command=lambda: self.root.attributes("-topmost", self.topmost.get())).pack(anchor="w", pady=2)
        auto = tk.BooleanVar(value=autostart.is_enabled())
        ttk.Checkbutton(frm, text="Mit Windows starten (im Infobereich)", variable=auto,
                        command=lambda: autostart.set_enabled(auto.get())).pack(anchor="w", pady=2)
        bridge = ttk.Frame(frm)
        bridge.pack(anchor="w", pady=(8, 2), fill="x")
        bridge_text = tk.StringVar()

        def bridge_refresh():
            bridge_text.set("Browser-Erweiterung: Verbindung zum Scanner eingerichtet ✔" if browser_bridge.is_installed()
                            else "Browser-Erweiterung: Verbindung zum Scanner fehlt")

        def bridge_setup():
            try:
                browser_bridge.install()
            except OSError as e:
                bridge_text.set(f"Einrichten fehlgeschlagen: {e}")
                return
            bridge_refresh()
            self._status("Browser-Brücke eingerichtet – Browser einmal neu starten")
        ttk.Label(bridge, textvariable=bridge_text).pack(side="left")
        ttk.Button(bridge, text="Einrichten", command=bridge_setup).pack(side="left", padx=8)
        bridge_refresh()
        caps = [f"Texterkennung: {ocr.backend() or 'nicht installiert'}",
                f"Gesichter: {'ja' if faces_available() else 'nicht installiert'}",
                f"Tray-Symbol: {'ja' if self.tray.available else 'nicht verfügbar'}"]
        ttk.Label(frm, text="\n".join(caps), foreground="#777").pack(anchor="w", pady=(10, 0))
        ttk.Button(frm, text="Schließen", command=win.destroy).pack(anchor="e", pady=(10, 0))
        win.bind("<Destroy>", lambda e: setattr(self, "llm_box", None) if e.widget is win else None)

    # ------------------------------------------------------------------ Zustand, Tray, Zähler
    def _state(self) -> str:
        if self._alerts:
            return "warnung"
        if self._busy or self._ki_busy:
            return "pruefe"
        return "aktiv" if self.watch.get() else "pause"

    def _refresh(self) -> None:
        state = self._state()
        title, sub = STATUS_TEXT[state]
        if state == "pause" and self._pause_job:
            sub = "Pausiert für 15 Minuten – danach automatisch wieder aktiv"
        self.status_icon.configure(image=self._img(state, 56))
        self.status_title.configure(text=title, fg=FARBEN[state] if state != "aktiv" else self.t["text"])
        self.status_sub.configure(text=sub)
        for key, lbl in self.counters.items():
            lbl.configure(text=str(self.stats.get(key)))
        self.tray.set_state(state, f"Datenwächter – {title}\n{self.stats.summary()}")

    def _status(self, text: str, color: str | None = None) -> None:
        """Neuer Eintrag in „Zuletzt“ (neueste oben)."""
        self._log.appendleft((f"{dt.datetime.now():%H:%M}  {text}", color or self.t["text"]))
        for i, lbl in enumerate(self.log_labels):
            if i < len(self._log):
                txt, col = self._log[i]
                lbl.configure(text=txt, fg=col if i == 0 else self.t["muted"])
        self._refresh()

    def _count(self, key: str, n: int = 1) -> None:
        self.stats.inc(key, n)
        self._refresh()

    def _toggle(self) -> None:
        if self._pause_job:
            self.root.after_cancel(self._pause_job)
            self._pause_job = None
        if self.watch.get():  # nach der Pause nicht auf alte Zwischenablage reagieren
            self._last_seq = winclip.sequence_number()
            self._last_text = self._tk_clipboard_text()
        self._status("Schutz eingeschaltet" if self.watch.get() else "Schutz ausgeschaltet")

    def _pause(self, minutes: int = 15) -> None:
        if self._pause_job:
            self.root.after_cancel(self._pause_job)
        self.watch.set(False)
        self._pause_job = self.root.after(minutes * 60_000, self._resume)
        self._status(f"Für {minutes} Minuten pausiert")

    def _resume(self) -> None:
        self._pause_job = None
        self.watch.set(True)
        self._toggle()
        self.tray.notify("Datenwächter", "Schutz ist wieder aktiv.")

    def _show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _close(self) -> None:
        if self.tray.available:
            self.root.withdraw()
            if not self._hint_shown:
                self._hint_shown = True
                self.tray.notify("Datenwächter läuft weiter", "Der Schutz bleibt im Hintergrund aktiv. "
                                                              "Das Symbol findest du im Infobereich.")
        else:
            self._quit()

    def _quit(self) -> None:
        if self.hotkey:
            self.hotkey.stop()
        self.tray.stop()
        self.root.destroy()

    def _ui(self, name: str) -> None:
        """Befehle aus dem Tray-Menü (laufen hier im Fenster-Thread)."""
        actions = {
            "show": self._show, "pick": self._pick_files, "restore": self._restore_clipboard,
            "settings": lambda: (self._show(), self._settings_window()), "pause15": self._pause, "quit": self._quit,
            "toggle": lambda: (self.watch.set(not self.watch.get()), self._toggle()),
            "autostart": lambda: (autostart.set_enabled(not autostart.is_enabled()), self._refresh()),
        }
        if name in actions:
            actions[name]()

    # ------------------------------------------------------------------ KI-Aktionen per Tastenkürzel
    def _start_hotkey(self) -> None:
        if self.hotkey:
            self.hotkey.stop()
            self.hotkey = None
        if self.bridge is not None:
            self.hotkey = hotkey.Hotkey(actions.load_hotkey(), lambda hwnd: self.results.put(("ki-hotkey", hwnd)))

    def _pointer_note(self, text: str, ms: int = 3500):
        """Kleiner Hinweis am Mauszeiger (gibt das Fenster zurück, damit es vorzeitig geschlossen werden kann)."""
        x, y = self.root.winfo_pointerxy()
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        tk.Label(w, text=text, bg="#263238", fg="white", font=(FONT, 10), padx=12, pady=8).pack()
        w.geometry(f"+{x + 16}+{y + 16}")
        if ms:
            w.after(ms, lambda: w.winfo_exists() and w.destroy())
        return w

    def _ki_start(self, hwnd) -> None:
        """Tastenkürzel gedrückt: markierten Text aus dem aktiven Programm holen (im Hintergrund)."""
        if self._suspend or self.bridge is None:
            return
        self._suspend = True
        b = self.bridge
        threading.Thread(target=lambda: self.results.put(("ki-captured", hwnd, *b.capture(hwnd))), daemon=True).start()

    def _ki_end(self) -> None:
        self._suspend = False
        self._ki_busy = False
        self._last_seq = winclip.sequence_number()   # eigene Zwischenablage-Änderungen nicht prüfen
        self._last_text = self._tk_clipboard_text()
        self._refresh()

    def _ki_captured(self, hwnd, text: str, old) -> None:
        if not text.strip():
            self.bridge.restore(old)
            self._ki_end()
            self._pointer_note(f"Erst Text markieren, dann {actions.load_hotkey()} drücken")
            return

        def cancel():
            self.bridge.restore(old)
            self._ki_end()

        def edit():
            cancel()
            self._show()
            self._actions_editor()
        label, extern = self._llm_info or (None, False)
        server = None
        if label and self.llm_ok:
            anon = " anonymisiert" if extern and settings.load_llm().anonymize_first else ""
            server = label.partition(":")[2].split("@")[0] + (f" · extern{anon}" if extern else " · lokal")
        self._ki_palette = ActionPalette(
            self.root, actions.load(), text, dark=self.t is THEMES["dunkel"], font=FONT, server=server,
            on_choose=lambda a: self._ki_run(a, hwnd, text, old) if self.llm_ok else (cancel(), self._show(),
                                                                                       self._llm_settings()),
            on_cancel=cancel, on_edit=edit)

    def _ki_run(self, aktion, hwnd, text: str, old) -> None:
        self._ki_busy = True
        self._refresh()
        self._ki_popup = self._pointer_note(f"🛡 {aktion.name} … KI arbeitet", ms=0)

        def work():
            try:
                self.results.put(("ki-result", hwnd, actions.run(aktion, text), None, old, text))
            except llm.LlmError as e:
                self.results.put(("ki-result", hwnd, None, str(e), old, text))
        threading.Thread(target=work, daemon=True).start()

    def _ki_result(self, hwnd, erg, error, old, text: str) -> None:
        if self._ki_popup is not None and self._ki_popup.winfo_exists():
            self._ki_popup.destroy()
        if erg is None:
            self.bridge.restore(old)
            self._ki_end()
            self._status(f"KI-Aktion fehlgeschlagen: {error}", FARBEN["warnung"])
            self._pointer_note(f"KI-Aktion fehlgeschlagen:\n{error}", ms=6000)
            return
        note = f" – an {erg.sent_to} gesendet{', vorher anonymisiert' if erg.anonymized else ''}" if erg.sent_to else ""
        if erg.aktion.modus == "anzeigen":
            self._ki_busy = False
            self._refresh()
            self._ki_show(hwnd, erg, old, note)
            return
        out = erg.text if erg.aktion.modus == "ersetzen" else f"{text}\n\n{erg.text}"
        b = self.bridge
        threading.Thread(target=lambda: (b.deliver(hwnd, out, old),
                                         self.results.put(("ki-done", f"✔ {erg.aktion.name}{note}"))), daemon=True).start()

    def _ki_done(self, message: str) -> None:
        self._ki_end()
        self._status(message, FARBEN["aktiv"])

    def _ki_show(self, hwnd, erg, old, note: str) -> None:
        """Ergebnis anzeigen (Modus „nur anzeigen“) – im Stil der Aktionsleiste, mit Kopieren und Einsetzen."""
        from .palette import FARBEN as PF, _windows_polish
        c = PF["dunkel" if self.t is THEMES["dunkel"] else "hell"]
        win = tk.Toplevel(self.root, bg=c["border"])
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        body = tk.Frame(win, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=1, pady=1)
        head = tk.Frame(body, bg=c["bg"])
        head.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(head, text="✦", bg=c["bg"], fg=c["accent"], font=(FONT, 12, "bold")).pack(side="left")
        tk.Label(head, text=erg.aktion.name, bg=c["bg"], fg=c["text"], font=(FONT, 11, "bold")).pack(side="left", padx=6)
        close = tk.Label(head, text="✕", bg=c["bg"], fg=c["muted"], font=(FONT, 11), cursor="hand2")
        close.pack(side="right")
        box = tk.Text(body, wrap="word", bg=c["field"], fg=c["text"], relief="flat", font=(FONT, 10), padx=12,
                      pady=10, height=9, highlightthickness=0, insertbackground=c["text"])
        box.insert("1.0", erg.text)
        box.pack(fill="both", expand=True, padx=12)
        if note:
            tk.Label(body, text=note.strip(" –"), bg=c["bg"], fg=c["muted"], font=(FONT, 8)).pack(anchor="w", padx=14,
                                                                                               pady=(6, 0))
        btns = tk.Frame(body, bg=c["bg"])
        btns.pack(fill="x", padx=12, pady=12)
        state = {"kept": False}

        def button(text, cmd, main=False):
            b = tk.Label(btns, text=text, bg=c["accent"] if main else c["hover"], fg="white" if main else c["text"],
                         font=(FONT, 9, "bold" if main else "normal"), padx=12, pady=6, cursor="hand2")
            b.bind("<Button-1>", lambda e: cmd())
            return b

        def copy():
            state["kept"] = True
            self._set_clipboard_text(box.get("1.0", "end-1c"))
            win.destroy()

        def insert():
            state["kept"] = True
            txt = box.get("1.0", "end-1c")   # inkl. eigener Änderungen im Ergebnisfenster
            win.destroy()
            b = self.bridge
            threading.Thread(target=lambda: (b.deliver(hwnd, txt, old),
                                             self.results.put(("ki-done", f"✔ {erg.aktion.name} eingesetzt"))),
                             daemon=True).start()

        def closed(e):
            if e.widget is win and not state["kept"]:
                self.bridge.restore(old)
                self._ki_end()
        win.bind("<Destroy>", closed)
        win.bind("<Escape>", lambda e: win.destroy())
        close.bind("<Button-1>", lambda e: win.destroy())
        button("Kopieren", copy, main=True).pack(side="left")
        button("Markierung ersetzen", insert).pack(side="left", padx=6)
        win.update_idletasks()
        x, y = self.root.winfo_pointerxy()
        w, h = 460, win.winfo_reqheight()
        x = max(8, min(x - w // 2, self.root.winfo_screenwidth() - w - 8))
        y = max(8, min(y + 12, self.root.winfo_screenheight() - h - 8))
        win.geometry(f"{w}x{h}+{x}+{y}")
        _windows_polish(win)
        win.focus_force()
        self._ki_result_window = win

    def _actions_editor(self) -> None:
        """Eigene KI-Aktionen anlegen: Name, Anweisung an die KI, was mit dem Ergebnis passiert."""
        liste = actions.load()
        win = tk.Toplevel(self.root)
        win.title("Datenwächter – KI-Aktionen")
        win.geometry("700x430")
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(0, weight=1)

        lb = tk.Listbox(frm, width=26, exportselection=False, font=(FONT, 10))
        lb.grid(row=0, column=0, rowspan=2, sticky="ns")
        right = ttk.Frame(frm, padding=(12, 0, 0, 0))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        name = tk.StringVar()
        modus = tk.StringVar()
        ttk.Label(right, text="Name im Menü").grid(row=0, column=0, sticky="w")
        ttk.Entry(right, textvariable=name).grid(row=1, column=0, sticky="ew")
        ttk.Label(right, text="Anweisung an die KI").grid(row=2, column=0, sticky="w", pady=(8, 0))
        anweisung = tk.Text(right, height=6, wrap="word", font=(FONT, 10))
        anweisung.grid(row=3, column=0, sticky="nsew")
        right.rowconfigure(3, weight=1)
        ttk.Label(right, text="Ergebnis").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(right, textvariable=modus, values=list(actions.MODI.values()), state="readonly").grid(
            row=5, column=0, sticky="w")
        sel = {"i": None}

        def refresh_list():
            lb.delete(0, "end")
            for a in liste:
                lb.insert("end", a.name)

        def commit():
            i = sel["i"]
            if i is None or i >= len(liste):
                return
            m = next((k for k, v in actions.MODI.items() if v == modus.get()), "ersetzen")
            liste[i] = actions.Aktion(name.get().strip() or liste[i].name, anweisung.get("1.0", "end-1c").strip()
                                      or liste[i].anweisung, m)
            lb.delete(i)
            lb.insert(i, liste[i].name)

        def select(i):
            commit()
            sel["i"] = i
            lb.selection_clear(0, "end")
            if i is None:
                return
            lb.selection_set(i)
            a = liste[i]
            name.set(a.name)
            anweisung.delete("1.0", "end")
            anweisung.insert("1.0", a.anweisung)
            modus.set(actions.MODI[a.modus])

        lb.bind("<<ListboxSelect>>", lambda e: lb.curselection() and select(lb.curselection()[0]))

        def live_name(*_):
            i = sel["i"]
            if i is not None and i < lb.size() and name.get().strip():
                lb.delete(i)
                lb.insert(i, name.get().strip())
                lb.selection_set(i)
        name.trace_add("write", live_name)

        def neu():
            commit()
            liste.append(actions.Aktion("Neue Aktion", "Beschreibe hier, was die KI mit dem markierten Text tun soll."))
            refresh_list()
            sel["i"] = None
            select(len(liste) - 1)

        def loeschen():
            i = sel["i"]
            if i is not None and liste:
                sel["i"] = None
                del liste[i]
                refresh_list()
                select(min(i, len(liste) - 1) if liste else None)

        def move(d):
            commit()
            i = sel["i"]
            if i is None or not 0 <= i + d < len(liste):
                return
            liste[i], liste[i + d] = liste[i + d], liste[i]
            refresh_list()
            sel["i"] = None
            select(i + d)

        def standard():
            liste[:] = list(actions.STANDARD)
            sel["i"] = None
            refresh_list()
            select(0)

        side = ttk.Frame(frm)
        side.grid(row=2, column=0, sticky="w", pady=(6, 0))
        for text, cmd in (("Neu", neu), ("Löschen", loeschen), ("↑", lambda: move(-1)), ("↓", lambda: move(1))):
            ttk.Button(side, text=text, width=7 if len(text) > 1 else 3, command=cmd).pack(side="left", padx=(0, 4))

        bottom = ttk.Frame(frm)
        bottom.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(bottom, text="Tastenkürzel (Windows):").pack(side="left")
        combo = tk.StringVar(value=actions.load_hotkey())
        ttk.Entry(bottom, textvariable=combo, width=22).pack(side="left", padx=6)
        status = ttk.Label(frm, text="Im Browser: Text markieren → Rechtsklick → „Mit KI bearbeiten …“.", foreground="#777")
        status.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        def speichern():
            commit()
            try:
                hotkey.parse(combo.get())
            except ValueError as e:
                status.configure(text=f"Tastenkürzel: {e}", foreground="#c62828")
                return
            actions.save(liste)
            actions.save_hotkey(combo.get().strip())
            self._start_hotkey()
            err = self.hotkey.error if self.hotkey else None
            status.configure(text=f"Gespeichert. {err or ''}".strip(), foreground="#c62828" if err else "#2e7d32")

        ttk.Button(bottom, text="Standard wiederherstellen", command=standard).pack(side="right")
        ttk.Button(bottom, text="Speichern", command=speichern).pack(side="right", padx=6)
        refresh_list()
        select(0 if liste else None)
        win.widgets = {"list": lb, "name": name, "anweisung": anweisung, "modus": modus, "neu": neu,
                       "loeschen": loeschen, "speichern": speichern, "combo": combo, "status": status, "liste": liste}
        self._actions_win = win

    def _detect_llm(self) -> None:
        llm._cache.clear()
        b = llm.backend()
        self.results.put(("llm", (b.label, b.s.extern) if b and isinstance(b, llm.OpenAICompatible) else
                                 ((b.label, False) if b else None)))

    # ------------------------------------------------------------------ Zwischenablage
    def _tk_clipboard_text(self) -> str | None:
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return None

    def _mark_own_write(self) -> None:
        self._ignore_seq = winclip.sequence_number()

    def _set_clipboard_text(self, text: str) -> None:
        if winclip.AVAILABLE:
            winclip.set_text(text)
            self._mark_own_write()
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        self._last_text = text

    def _set_clipboard_files(self, paths: list[str]) -> None:
        winclip.set_files(paths)
        self._mark_own_write()

    def _set_clipboard_image(self, img) -> None:
        winclip.set_image(img)
        self._mark_own_write()

    def _poll(self) -> None:
        try:
            self._drain_results()
            if self.watch.get() and not self._busy and not self._suspend:
                self._check_clipboard()
        finally:
            self.root.after(POLL_MS, self._poll)

    def _check_clipboard(self) -> None:
        if winclip.AVAILABLE:
            seq = winclip.sequence_number()
            if seq == self._last_seq:
                return
            self._last_seq = seq
            if seq == self._ignore_seq:
                return
            files = winclip.get_files()
            if files:
                self._check_files(files, "clipboard")
                return
            text = winclip.get_text()
            if text is None:
                img = winclip.get_image()
                if img is not None:
                    self._check_clipboard_image(img)
                return
        else:
            text = self._tk_clipboard_text()
            if text == self._last_text:
                return
        self._last_text = text
        if text and text.strip():
            self._check_text(text)

    # ------------------------------------------------------------------ Prüfen
    def _check_text(self, text: str) -> None:
        self._count("geprueft")
        findings = scan_text(text)  # Regeln sind schnell -> sofort reagieren
        if findings and self.safe.get():
            self._set_clipboard_text(self.anon.anonymize(text, findings))
        long_text = len(text) >= MIN_CONTENT_CHECK
        if self.use_ki.get() or (long_text and self.use_llm.get()):
            use_ki, use_llm = self.use_ki.get(), long_text and self.use_llm.get()
            self._run(lambda: ("text", text, scan_text(text, use_ki=use_ki),
                               content_check.check(text, use_llm=use_llm) if long_text else None))
        else:
            verdict = content_check.keyword_check(text) if long_text else None
            if findings or (verdict and verdict.warning):
                self._warn_text(text, findings, verdict)

    def _check_clipboard_image(self, img) -> None:
        TEMP_DIR.mkdir(exist_ok=True)
        path = TEMP_DIR / "Zwischenablage.png"
        img.save(path)
        self._check_files([str(path)], "clipboard-image", original_image=img)

    def _check_files(self, paths: list[str], origin: str, original_image=None) -> None:
        use_ki, use_llm = self.use_ki.get(), self.use_llm.get()
        hold = origin.startswith("clipboard") and self.safe.get() and winclip.AVAILABLE
        if hold:  # während der Prüfung nichts Einfügbares in der Zwischenablage lassen
            winclip.clear()
            self._mark_own_write()
        self._busy = True
        self._count("geprueft", len(paths))
        self._status(f"Prüfe {len(paths)} Datei(en) …")

        def job():
            reports, errors = [], []
            for p in paths:
                try:
                    reports.append(analyze(p, use_ki=use_ki, use_llm=use_llm))
                except Exception as e:  # noqa: BLE001 – Fehler pro Datei anzeigen, nicht abstürzen
                    errors.append(f"{Path(p).name}: {e}")
            return ("files", paths, reports, errors, origin, hold, original_image)

        self._run(job)

    def _run(self, fn) -> None:
        self._busy = True

        def worker():
            try:
                self.results.put(fn())
            except Exception as e:  # noqa: BLE001
                self.results.put(("error", str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def _drain_results(self) -> None:
        while not self.results.empty():
            item = self.results.get()
            if item[0] == "ui":
                self._ui(item[1])
                continue
            if item[0].startswith("ki-"):
                {"ki-hotkey": self._ki_start, "ki-captured": self._ki_captured, "ki-result": self._ki_result,
                 "ki-done": self._ki_done}[item[0]](*item[1:])
                continue
            if item[0] == "llm":
                self.llm_ok = bool(item[1])
                self._llm_info = item[1]
                if item[1]:
                    label, extern = item[1]
                    self.llm_text.set(f"Inhalts-Check mit KI ({label.partition(':')[2]})" + (" – extern" if extern else ""))
                    self.use_llm.set(True)
                else:
                    self.use_llm.set(False)
                    self.llm_text.set("Inhalts-Check mit KI (kein KI-Server eingerichtet)")
                if self.llm_box is not None:
                    self.llm_box.state(["!disabled"] if self.llm_ok else ["disabled"])
                continue
            self._busy = False
            self._refresh()
            if item[0] == "error":
                self._ok(f"Fehler: {item[1]}")
            elif item[0] == "text":
                _, text, findings, verdict = item
                if findings and self.safe.get():
                    self._set_clipboard_text(self.anon.anonymize(text, findings))
                if findings or (verdict and verdict.warning):
                    self._warn_text(text, findings, verdict)
                else:
                    self._ok()
            else:
                _, paths, reports, errors, origin, hold, original_image = item
                if errors or any(r.needs_attention for r in reports):
                    self._warn_files(paths, reports, errors, origin, hold, original_image)
                else:
                    self._release(paths, origin, hold, original_image)
                    self._ok()

    def _release(self, paths, origin, hold, original_image) -> None:
        """Original wieder in die Zwischenablage legen (nach bestandener Prüfung oder auf Wunsch)."""
        if origin == "clipboard-image" and original_image is not None and hold:
            self._set_clipboard_image(original_image)
        elif hold or (origin == "drop" and winclip.AVAILABLE):
            self._set_clipboard_files(paths)

    def _ok(self, note: str | None = None) -> None:
        self._status(note or "✔ Keine sensiblen Daten gefunden", FARBEN["pause"] if note else FARBEN["aktiv"])

    # ------------------------------------------------------------------ Warnungen
    def _dialog(self, title: str, rows: list[tuple[str, dict]], verdicts=(), notes=(), count: bool = True) -> tk.Toplevel:
        if count:
            self.root.bell()
            self._count("gewarnt")
        self._alerts += 1
        self._refresh()
        dlg = tk.Toplevel(self.root)

        def closed(e):
            if e.widget is dlg:
                self._alerts = max(0, self._alerts - 1)
                self._refresh()
        dlg.bind("<Destroy>", closed)
        dlg.title("Datenwächter – Achtung")
        dlg.configure(bg=self.t["bg"])
        dlg.attributes("-topmost", True)
        dlg.geometry("680x420" if rows else "680x220")
        worst = max([r["severity"] for _, r in rows] + [v.severity for v in verdicts] + [0])
        tk.Label(dlg, text=f"⚠  {title}", bg=COLORS[worst], fg="white", font=(FONT, 12, "bold"),
                 anchor="w", padx=10, pady=8).pack(fill="x")
        for v in verdicts:
            text = f"🧠 {v.warning} Willst du das wirklich?"
            if v.description:
                text += f"\n{v.description}"
            text += "\n" + v.source_text()
            dark = self.t is THEMES["dunkel"]
            tk.Label(dlg, text=text, bg="#3e2723" if dark else "#fff3e0", fg="#ffe0b2" if dark else "#5d4037",
                     font=(FONT, 10), justify="left", anchor="w", wraplength=640,
                     padx=10, pady=6).pack(fill="x", padx=10, pady=(8, 0))
        if rows:
            tree = ttk.Treeview(dlg, columns=("stufe", "art", "wert", "quelle"), show="headings", height=8)
            for col, w, txt in (("stufe", 70, "Stufe"), ("art", 200, "Art"), ("wert", 260, "Wert"), ("quelle", 120, "Fundort")):
                tree.heading(col, text=txt)
                tree.column(col, width=w, anchor="w")
            for sev in (3, 2, 1):
                tree.tag_configure(str(sev), foreground=COLORS[sev])
            for src, r in rows:
                tree.insert("", "end", values=(SEVERITY_LABEL[r["severity"]], r["label"], r["display"], src),
                            tags=(str(r["severity"]),))
            tree.pack(fill="both", expand=True, padx=10, pady=8)
        for n in notes:
            tk.Label(dlg, text=f"ℹ {n}", bg=self.t["bg"], fg=self.t["muted"], font=(FONT, 9)).pack(anchor="w", padx=12)
        dlg.buttons = ttk.Frame(dlg)
        dlg.buttons.pack(fill="x", side="bottom", padx=10, pady=(4, 10))
        dlg.focus_force()
        return dlg

    # Kurzbezeichnungen für die Benachrichtigung
    KURZ = {"PERSON": "Name", "IBAN": "IBAN", "KREDITKARTE": "Kreditkarte", "STEUER_ID": "Steuer-ID",
            "SOZIALVERSICHERUNG": "SV-Nummer", "AUSWEIS": "Ausweisnummer", "GEBURTSDATUM": "Geburtsdatum",
            "EMAIL": "E-Mail", "TELEFON": "Telefon", "ADRESSE": "Adresse", "IP_ADRESSE": "IP-Adresse",
            "API_SCHLUESSEL": "API-Schlüssel", "PASSWORT": "Passwort", "PRIVATER_SCHLUESSEL": "privater Schlüssel",
            "TOKEN": "Token", "ZUGANGSDATEN_URL": "Datenbank-Zugang", "GESICHT": "Gesicht"}

    def _summary(self, kinds: list[str]) -> str:
        names = list(dict.fromkeys(self.KURZ.get(k, k.title()) for k in kinds))
        return " · ".join(names[:4]) + (f"  +{len(names) - 4}" if len(names) > 4 else "")

    def _popup(self, **kw) -> TrayPopup:
        """Benachrichtigung unten rechts; zählt als Warnung und färbt das Tray-Symbol, solange sie sichtbar ist."""
        self.root.bell()
        self._count("gewarnt")
        self._alerts += 1
        self._refresh()
        pop = TrayPopup(self.root, dark=self.t is THEMES["dunkel"], font=FONT, **kw)

        def gone(e):
            if e.widget is pop:
                self._alerts = max(0, self._alerts - 1)
                self._refresh()
        pop.bind("<Destroy>", gone)
        self._last_popup = pop
        return pop

    def _warn_text(self, text: str, findings, verdict) -> None:
        """Kopierter Text mit sensiblen Daten -> Benachrichtigung unten rechts."""
        verdicts = [verdict] if verdict and verdict.warning else []
        safe = bool(findings) and self.safe.get()
        self._status(f"⚠ {len(findings)} Fund(e) in kopiertem Text" if findings
                     else "⚠ Sensibles Thema im kopierten Text", "#c62828")
        if safe:
            self._count("anonymisiert")

        def original():
            self._set_clipboard_text(text)
            self._status("Original in die Zwischenablage gelegt", FARBEN["pause"])

        def anonymize():
            self._count("anonymisiert")
            self._set_clipboard_text(self.anon.anonymize(text, findings))
            self._status("✔ Anonymisierte Fassung in der Zwischenablage", FARBEN["aktiv"])

        def leeren():
            self._set_clipboard_text("")
            self._status("Zwischenablage geleert")

        topic = f"Thema: {', '.join(verdicts[0].categories)}" if verdicts and verdicts[0].categories else ""
        if findings:
            actions = [("Original verwenden", original, False)] if safe else [("Anonymisieren", anonymize, True)]
            status = ("✔ In der Zwischenablage liegt jetzt die anonymisierte Fassung." if safe
                      else "Das Original liegt noch in der Zwischenablage.")
            self._popup(level="warnung", title=f"{len(findings)} sensible Angabe(n) kopiert",
                        summary=self._summary([f.kind for f in findings]), topic=topic, status=status,
                        actions=actions, timeout_ms=9000 if safe else 20000,
                        on_details=lambda: self._warn_text_dialog(text, findings, verdict, safe))
        else:
            v = verdicts[0] if verdicts else None
            hints = ", ".join(f"„{h}“" for h in (v.hints if v else [])[:3])
            summary = (f"{', '.join(v.categories)}" + (f" – erkannt an {hints}" if hints else "")) if v else ""
            self._popup(level="thema", title="Sensibles Thema kopiert", summary=summary,
                        status="Willst du das wirklich teilen?",
                        actions=[("Zwischenablage leeren", leeren, False)], timeout_ms=12000,
                        on_details=lambda: self._warn_text_dialog(text, findings, verdict, False))

    def _warn_text_dialog(self, text: str, findings, verdict, already_anonymized: bool) -> None:
        """Ausführliche Ansicht („Details“) mit allen Funden."""
        verdicts = [verdict] if verdict and verdict.warning else []
        rows = [("Text", {"label": f.label, "display": f.masked(), "severity": f.severity}) for f in findings]
        dlg = self._dialog(f"Du hast {len(findings)} sensible Angabe(n) kopiert" if findings
                           else "Bitte kurz prüfen, was du kopiert hast", rows, verdicts, count=False)
        b = dlg.buttons
        if findings and already_anonymized:
            ttk.Label(b, text="Die Zwischenablage enthält bereits die anonymisierte Fassung.").pack(anchor="w")
            ttk.Button(b, text="✔ Anonymisiert lassen", command=dlg.destroy).pack(side="left")
        elif findings:
            def anonymize():
                self._count("anonymisiert")
                self._set_clipboard_text(self.anon.anonymize(text, findings))
                self._status("✔ Anonymisierte Fassung in der Zwischenablage", "#2e7d32")
                dlg.destroy()
            ttk.Button(b, text="✔ Anonymisieren", command=anonymize).pack(side="left")
        else:
            ttk.Button(b, text="OK, ist in Ordnung", command=dlg.destroy).pack(side="left")

        def original():
            self._set_clipboard_text(text)
            dlg.destroy()

        def leeren():
            self._set_clipboard_text("")
            dlg.destroy()
        if findings:
            ttk.Button(b, text="Original verwenden", command=original).pack(side="left", padx=6)
        ttk.Button(b, text="Zwischenablage leeren", command=leeren).pack(side="left", padx=6)

    def _warn_files(self, paths, reports, errors, origin: str, hold: bool, original_image) -> None:
        shown = lambda r: "Bild aus Zwischenablage" if origin == "clipboard-image" else r.name  # noqa: E731
        rows = [(shown(r), row) for r in reports for row in r.rows()]
        verdicts = [r.verdict for r in reports if r.verdict.warning]
        notes = errors + [f"{shown(r)}: {n}" for r in reports for n in r.doc.notes + r.info]
        can_anon = any(r.can_anonymize for r in reports)
        self._status(f"⚠ {len(rows)} Fund(e) in {len(reports)} Datei(en)", "#c62828")
        title = (f"{len(rows)} sensible Angabe(n) gefunden" if rows else
                 "Bitte kurz prüfen, was du hochlädst" if verdicts else "Nicht vollständig prüfbar")
        ui = {"close": lambda: None}

        def anonymize():
            self._count("anonymisiert", sum(1 for r in reports if r.can_anonymize))
            TEMP_DIR.mkdir(exist_ok=True)
            out_dir = TEMP_DIR if origin.startswith("clipboard") else None
            outs = []
            for r in reports:
                if r.can_anonymize:
                    outs.append(str(anonymize_report(r, self.anon, out_dir)))
                elif not r.rows():
                    outs.append(str(r.doc.path))  # unbedenkliche Dateien unverändert weiterreichen
            if origin == "clipboard-image" and outs:
                from PIL import Image
                self._set_clipboard_image(Image.open(outs[0]))
            elif winclip.AVAILABLE:
                self._set_clipboard_files(outs)
            if origin == "drop" and outs and sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", outs[0]])
            self._status("✔ Anonymisierte Fassung bereit – jetzt einfügen (Strg+V) oder hineinziehen", "#2e7d32")
            ui["close"]()

        def original():
            self._release(paths, origin, True, original_image)
            ui["close"]()

        def abbrechen():
            if hold:
                winclip.clear()
                self._mark_own_write()
            ui["close"]()

        if origin.startswith("clipboard"):   # beim Kopieren: Benachrichtigung unten rechts
            what = "Screenshot" if origin == "clipboard-image" else (
                reports[0].name if len(reports) == 1 else f"{len(reports)} Dateien")
            kinds = [row["kind"] for r in reports for row in r.rows()]
            topic = "; ".join(f"Thema: {', '.join(v.categories)}" for v in verdicts if v.categories)
            if can_anon:
                actions = [("Geschwärzt einfügen", anonymize, True), ("Original", original, False)]
                status = "Bis du entscheidest, ist die Zwischenablage leer." if hold else ""
            else:
                actions = [("Trotzdem verwenden", original, True), ("Verwerfen", abbrechen, False)]
                status = "; ".join(notes[:2])
            self._popup(level="warnung" if rows else "thema",
                        title=f"{what}: {len(rows)} sensible Angabe(n)" if rows else f"{what}: bitte prüfen",
                        summary=self._summary(kinds), topic=topic, status=status, actions=actions,
                        on_details=lambda: self._files_dialog(title, rows, verdicts, notes, can_anon, anonymize,
                                                              original, abbrechen, ui),
                        on_close=abbrechen)
            return
        self._files_dialog(title, rows, verdicts, notes, can_anon, anonymize, original, abbrechen, ui, count=True)

    def _files_dialog(self, title, rows, verdicts, notes, can_anon, anonymize, original, abbrechen, ui,
                      count: bool = False) -> None:
        dlg = self._dialog(title, rows, verdicts, notes, count=count)
        ui["close"] = dlg.destroy
        b = dlg.buttons
        if can_anon:
            ttk.Button(b, text="✔ Anonymisierte Fassung erstellen", command=anonymize).pack(side="left")
            ttk.Button(b, text="Original trotzdem verwenden", command=original).pack(side="left", padx=6)
            ttk.Button(b, text="Abbrechen", command=abbrechen).pack(side="left")
        else:
            ttk.Button(b, text="Abbrechen", command=abbrechen).pack(side="left")
            ttk.Button(b, text="Trotzdem verwenden", command=original).pack(side="left", padx=6)
        dlg.protocol("WM_DELETE_WINDOW", abbrechen)

    # ------------------------------------------------------------------ Sonstiges
    def _pick_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Datei prüfen")
        if paths:
            self._check_files(list(paths), "drop")

    def _restore_clipboard(self) -> None:
        text = winclip.get_text() if winclip.AVAILABLE else self._tk_clipboard_text()
        if not text:
            messagebox.showinfo("Datenwächter", "Kopiere zuerst die Antwort der KI (Strg+C).")
            return
        restored = self.anon.restore(text)
        self._set_clipboard_text(restored)
        n = sum(text.count(ph) for ph in self.anon.mapping)
        messagebox.showinfo("Datenwächter", f"{n} Platzhalter ersetzt. Die Originalfassung liegt jetzt in der "
                                            "Zwischenablage.")

    def _llm_settings(self) -> None:
        """KI-Server einrichten: OpenAI-kompatible API mit Adresse + Token (OpenAI, Azure, Firmen-Gateway, LM Studio …)."""
        s = settings.load_llm()
        win = tk.Toplevel(self.root)
        win.title("Datenwächter – KI-Server")
        win.attributes("-topmost", True)
        win.minsize(600, 0)
        frm = ttk.Frame(win, padding=14)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        aktiv = tk.BooleanVar(value=s.typ != "aus" and bool(s.url))
        url, token, modell = tk.StringVar(value=s.url), tk.StringVar(value=s.token), tk.StringVar(value=s.modell)
        bilder, anon = tk.BooleanVar(value=s.send_images), tk.BooleanVar(value=s.anonymize_first)
        namen = tk.BooleanVar(value=s.ki_namen)

        ttk.Checkbutton(frm, text="KI-Server benutzen (OpenAI-kompatible API)", variable=aktiv).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Label(frm, text="API-Adresse").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(frm, textvariable=url, values=[u for _, u in settings.URL_VORLAGEN]).grid(
            row=1, column=1, columnspan=2, sticky="ew")
        ttk.Label(frm, text="Basis-Adresse mit /v1, z. B. von OpenAI oder deinem Firmen-Gateway",
                  foreground="#777").grid(row=2, column=1, columnspan=2, sticky="w")
        ttk.Label(frm, text="Token / API-Schlüssel").grid(row=3, column=0, sticky="w", pady=3)
        tok_entry = ttk.Entry(frm, textvariable=token, show="•")
        tok_entry.grid(row=3, column=1, sticky="ew")
        show = tk.BooleanVar(value=False)
        ttk.Checkbutton(frm, text="zeigen", variable=show,
                        command=lambda: tok_entry.configure(show="" if show.get() else "•")).grid(row=3, column=2)
        ttk.Label(frm, text="Modell").grid(row=4, column=0, sticky="w", pady=3)
        model_box = ttk.Combobox(frm, textvariable=modell)
        model_box.grid(row=4, column=1, sticky="ew")

        pruef = ttk.LabelFrame(frm, text="Was die KI prüfen soll", padding=10)
        pruef.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Label(pruef, text="✔ Inhalt bewerten („Du lädst gerade Familienunterlagen hoch“) – immer aktiv").pack(
            anchor="w")
        ttk.Checkbutton(pruef, text="Namen ohne „Herr/Frau“ finden (z. B. den Kindernamen „Mia Schneider“)",
                        variable=namen).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(pruef, text="Fotos und Screenshots bewerten („Foto eines Ausweises“)",
                        variable=bilder).pack(anchor="w")
        ttk.Checkbutton(pruef, text="Vor dem Senden anonymisieren (IBAN, Telefon, bekannte Namen → Platzhalter)",
                        variable=anon).pack(anchor="w")

        warn = ttk.Label(frm, text="", foreground="#b45309", wraplength=580, justify="left")
        warn.grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        status = ttk.Label(frm, text="", wraplength=580, justify="left")
        status.grid(row=7, column=0, columnspan=3, sticky="w", pady=(6, 0))

        def current() -> settings.LlmSettings:
            return settings.LlmSettings(typ="openai" if aktiv.get() else "aus", url=url.get().strip(),
                                        token=token.get().strip(), modell=modell.get().strip(),
                                        bilder_senden=bilder.get(), anonymisieren=anon.get(), ki_namen=namen.get())

        def in_thread(fn, done):
            threading.Thread(target=lambda: (lambda r: win.after(0, lambda: win.winfo_exists() and done(r)))(fn()),
                             daemon=True).start()

        def load_models():
            status.configure(text="Lade Modelle …", foreground="#555")

            def fetch():
                try:
                    return llm.OpenAICompatible(current()).models()
                except llm.LlmError as e:
                    return e

            def done(r):
                if isinstance(r, Exception):
                    status.configure(text=f"Modelle nicht abrufbar: {r}", foreground="#c62828")
                else:
                    model_box.configure(values=r)
                    if r and not modell.get():
                        modell.set(r[0])
                    status.configure(text=f"{len(r)} Modell(e) gefunden.", foreground="#2e7d32")
            in_thread(fetch, done)
        ttk.Button(frm, text="Modelle laden", command=load_models).grid(row=4, column=2, padx=(6, 0))

        last_extern = [settings.is_external(s.url)]

        def update_warn(*_):
            extern = settings.is_external(url.get())
            if extern != last_extern[0]:  # Voreinstellungen passend zur Art des Servers
                last_extern[0] = extern
                if extern:
                    bilder.set(False)
                    anon.set(True)
            if not extern or not url.get().strip():
                warn.configure(text="")
                return
            host = settings.LlmSettings(url=url.get()).host
            parts = [f"⚠ Externer Server ({host}): Inhalte verlassen deinen PC bzw. dein Netz – nur mit einem Anbieter, "
                     "dem du vertraust (z. B. Firmenvertrag/AV-Vertrag)."]
            if namen.get():
                parts.append("Für die Namenssuche gehen Namen, die der Datenwächter noch nicht kennt, an den Server.")
            if bilder.get():
                parts.append("Fotos und Screenshots gehen unverändert an den Server.")
            if not anon.get():
                parts.append("Texte werden ohne Anonymisierung gesendet.")
            warn.configure(text=" ".join(parts))
        for var in (url, namen, bilder, anon):
            var.trace_add("write", update_warn)
        update_warn()

        def test():
            status.configure(text="Teste Verbindung …", foreground="#555")
            in_thread(lambda: llm.test_connection(current()),
                      lambda r: status.configure(text=r[1], foreground="#2e7d32" if r[0] else "#c62828"))

        def save():
            new = current()
            p = settings.save_llm(new)
            llm._cache.clear()
            self.use_ki.set(new.ki_namen)
            self.llm_text.set("Inhalts-Check mit KI (Server wird gesucht …)")
            threading.Thread(target=self._detect_llm, daemon=True).start()
            status.configure(text=f"Gespeichert in {p}", foreground="#2e7d32")
            win.after(700, win.destroy)

        btns = ttk.Frame(frm)
        btns.grid(row=8, column=0, columnspan=3, sticky="w", pady=(14, 0))
        ttk.Button(btns, text="Verbindung testen", command=test).pack(side="left")
        ttk.Button(btns, text="Speichern", command=save).pack(side="left", padx=6)
        ttk.Button(btns, text="Abbrechen", command=win.destroy).pack(side="left")
        win.widgets = {"aktiv": aktiv, "url": url, "token": token, "modell": modell, "bilder": bilder, "anon": anon,
                       "namen": namen, "status": status, "test": test, "save": save, "load_models": load_models,
                       "warn": warn}

    def _show_mapping(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("Platzhalter-Zuordnung (nur lokal)")
        win.attributes("-topmost", True)
        tree = ttk.Treeview(win, columns=("ph", "orig"), show="headings", height=14)
        tree.heading("ph", text="Platzhalter")
        tree.heading("orig", text="Original")
        tree.column("ph", width=160)
        tree.column("orig", width=320)
        for ph, orig in self.anon.mapping.items():
            tree.insert("", "end", values=(ph, orig))
        tree.pack(fill="both", expand=True, padx=8, pady=8)

        def clear():
            self.anon.clear()
            for i in tree.get_children():
                tree.delete(i)
        ttk.Button(win, text="Zuordnung löschen", command=clear).pack(pady=(0, 8))

    def run(self) -> None:
        self.root.mainloop()


def main(start_hidden: bool | None = None) -> None:
    if os.environ.get("DATENWAECHTER_NO_GUI"):
        return
    if start_hidden is None:
        start_hidden = "--minimiert" in sys.argv
    app = App(start_hidden=start_hidden)
    # Für den automatischen Praxistest des fertigen Programms: Start bestätigen und nach kurzer Zeit beenden
    marker = os.environ.get("DATENWAECHTER_STARTMARKER")
    if marker:
        Path(marker).write_text(f"gestartet tray={app.tray.available} hotkey={bool(app.hotkey and app.hotkey.active)}",
                                encoding="utf-8")
        app.root.after(int(os.environ.get("DATENWAECHTER_SMOKE_MS", "4000")), app._quit)
    app.run()


if __name__ == "__main__":
    main()
