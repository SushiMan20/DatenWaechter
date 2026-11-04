"""Das Wächter-Fenster.

- überwacht die Zwischenablage (Text UND im Explorer kopierte Dateien)
- warnt mit einer Liste der Funde und bietet „Anonymisieren“ an
- nimmt Dateien per Drag & Drop entgegen und erzeugt anonymisierte Kopien
- übersetzt KI-Antworten mit Platzhaltern wieder zurück
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import winclip
from .anonymize import Anonymizer
from .detectors import HOCH, Finding, scan_text
from .files import scan_file, write_anonymized

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

POLL_MS = 200
TEMP_DIR = Path(tempfile.gettempdir()) / "datenwaechter"
COLORS = {HOCH: "#c62828", 2: "#ef6c00", 1: "#757575"}


class App:
    def __init__(self) -> None:
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title("Datenwächter")
        self.root.geometry("420x330")
        self.root.minsize(380, 300)

        self.anon = Anonymizer()
        self.results: queue.Queue = queue.Queue()
        self.watch = tk.BooleanVar(value=True)
        self.safe = tk.BooleanVar(value=True)
        self.use_ki = tk.BooleanVar(value=False)
        self.topmost = tk.BooleanVar(value=True)
        self._last_seq = winclip.sequence_number()
        self._last_text = self._tk_clipboard_text()
        self._ignore_seq: int | None = None
        self._busy = False

        self._build()
        self.root.attributes("-topmost", True)
        self.root.after(POLL_MS, self._poll)

    # ------------------------------------------------------------------ Aufbau
    def _build(self) -> None:
        pad = {"padx": 10, "pady": 4}
        head = ttk.Label(self.root, text="🛡  Datenwächter", font=("Segoe UI", 14, "bold"))
        head.pack(anchor="w", **pad)

        self.status = ttk.Label(self.root, text="Überwache Zwischenablage …", foreground="#2e7d32")
        self.status.pack(anchor="w", padx=10)

        drop = tk.Label(self.root, text="Datei hierher ziehen\n(wird geprüft, bevor sie zur KI geht)",
                        relief="groove", bd=2, height=4, bg="#f5f5f5", fg="#555")
        drop.pack(fill="x", padx=10, pady=8)
        if TkinterDnD:
            drop.drop_target_register(DND_FILES)
            drop.dnd_bind("<<Drop>>", lambda e: self._check_files(list(self.root.tk.splitlist(e.data)), "drop"))
        else:
            drop.configure(text="Datei prüfen … (klicken)\nDrag & Drop: pip install tkinterdnd2")
        drop.bind("<Button-1>", lambda e: self._pick_files())

        opts = ttk.Frame(self.root)
        opts.pack(fill="x", padx=10)
        ttk.Checkbutton(opts, text="Zwischenablage überwachen", variable=self.watch).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(opts, text="Sicherer Modus (sofort anonymisieren)", variable=self.safe).grid(
            row=1, column=0, sticky="w")
        from . import ner
        ki = ttk.Checkbutton(opts, text="Lokales KI-Modell für Namen/Adressen", variable=self.use_ki)
        ki.grid(row=2, column=0, sticky="w")
        if not ner.available():
            ki.state(["disabled"])
            ki.configure(text="Lokales KI-Modell (pip install datenwaechter[ki])")
        ttk.Checkbutton(opts, text="Immer im Vordergrund", variable=self.topmost,
                        command=lambda: self.root.attributes("-topmost", self.topmost.get())).grid(
            row=3, column=0, sticky="w")

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", padx=10, pady=8)
        ttk.Button(btns, text="KI-Antwort zurückübersetzen", command=self._restore_clipboard).pack(
            side="left", expand=True, fill="x")
        ttk.Button(btns, text="Zuordnung", command=self._show_mapping).pack(side="left", padx=(6, 0))

    # ------------------------------------------------------------------ Zwischenablage
    def _tk_clipboard_text(self) -> str | None:
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return None

    def _set_clipboard_text(self, text: str) -> None:
        if winclip.AVAILABLE:
            winclip.set_text(text)
            self._ignore_seq = winclip.sequence_number()
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        self._last_text = text

    def _set_clipboard_files(self, paths: list[str]) -> None:
        winclip.set_files(paths)
        self._ignore_seq = winclip.sequence_number()

    def _poll(self) -> None:
        try:
            self._drain_results()
            if self.watch.get() and not self._busy:
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
        else:
            text = self._tk_clipboard_text()
            if text == self._last_text:
                return
        self._last_text = text
        if text and text.strip():
            self._check_text(text)

    # ------------------------------------------------------------------ Prüfen (im Hintergrund)
    def _check_text(self, text: str) -> None:
        use_ki = self.use_ki.get()
        findings = scan_text(text)  # Regeln sind schnell -> sofort reagieren
        if findings and self.safe.get():
            self._set_clipboard_text(self.anon.anonymize(text, findings))
        if use_ki:
            self._run(lambda: ("text", text, scan_text(text, use_ki=True)))
        elif findings:
            self._warn_text(text, findings)

    def _check_files(self, paths: list[str], origin: str) -> None:
        use_ki = self.use_ki.get()
        hold = origin == "clipboard" and self.safe.get() and winclip.AVAILABLE
        if hold:
            # Während des Scans nichts Einfügbares in der Zwischenablage lassen
            winclip.clear()
            self._ignore_seq = winclip.sequence_number()
        self.status.configure(text=f"Prüfe {len(paths)} Datei(en) …", foreground="#ef6c00")

        def job():
            report = []
            for p in paths:
                try:
                    _, f = scan_file(p, use_ki=use_ki)
                    report.append((p, f, None))
                except Exception as e:  # noqa: BLE001 – Fehler pro Datei anzeigen, nicht abstürzen
                    report.append((p, [], str(e)))
            return ("files", paths, report, origin, hold)

        self._run(job)

    def _run(self, fn) -> None:
        self._busy = True
        threading.Thread(target=lambda: self.results.put(fn()), daemon=True).start()

    def _drain_results(self) -> None:
        while not self.results.empty():
            self._busy = False
            item = self.results.get()
            if item[0] == "text":
                _, text, findings = item
                if findings and self.safe.get():
                    self._set_clipboard_text(self.anon.anonymize(text, findings))
                if findings:
                    self._warn_text(text, findings)
                else:
                    self._ok()
            else:
                _, paths, report, origin, hold = item
                if any(f for _, f, _ in report):
                    self._warn_files(paths, report, origin, hold)
                else:
                    if hold:
                        self._set_clipboard_files(paths)
                    errors = [f"{Path(p).name}: {e}" for p, _, e in report if e]
                    self._ok("Nicht prüfbar: " + "; ".join(errors) if errors else None)

    def _ok(self, note: str | None = None) -> None:
        self.status.configure(text=note or "✔ Keine sensiblen Daten gefunden",
                              foreground="#ef6c00" if note else "#2e7d32")

    # ------------------------------------------------------------------ Warnungen
    def _dialog(self, title: str, rows: list[tuple[str, Finding]]) -> tk.Toplevel:
        self.root.bell()
        dlg = tk.Toplevel(self.root)
        dlg.title("Datenwächter – Achtung")
        dlg.attributes("-topmost", True)
        dlg.geometry("640x380")
        worst = max(f.severity for _, f in rows)
        bar = tk.Label(dlg, text=f"⚠  {title}", bg=COLORS[worst], fg="white",
                       font=("Segoe UI", 12, "bold"), anchor="w", padx=10, pady=8)
        bar.pack(fill="x")

        tree = ttk.Treeview(dlg, columns=("stufe", "art", "wert", "quelle"), show="headings", height=10)
        for col, w, txt in (("stufe", 70, "Stufe"), ("art", 190, "Art"), ("wert", 260, "Wert"), ("quelle", 110, "Fundort")):
            tree.heading(col, text=txt)
            tree.column(col, width=w, anchor="w")
        for sev in (3, 2, 1):
            tree.tag_configure(str(sev), foreground=COLORS[sev])
        for src, f in rows:
            label = f.label + (" (KI)" if f.source == "ki" else "")
            tree.insert("", "end", values=(f.severity_label, label, f.masked(), src), tags=(str(f.severity),))
        tree.pack(fill="both", expand=True, padx=10, pady=8)
        dlg.buttons = ttk.Frame(dlg)
        dlg.buttons.pack(fill="x", padx=10, pady=(0, 10))
        dlg.focus_force()
        return dlg

    def _warn_text(self, text: str, findings: list[Finding]) -> None:
        self.status.configure(text=f"⚠ {len(findings)} Fund(e) in kopiertem Text", foreground="#c62828")
        dlg = self._dialog(f"Du hast {len(findings)} sensible Angabe(n) kopiert", [("Text", f) for f in findings])
        b = dlg.buttons
        if self.safe.get():
            ttk.Label(b, text="Die Zwischenablage enthält bereits die anonymisierte Fassung.").pack(anchor="w")
            ttk.Button(b, text="✔ Anonymisiert lassen", command=dlg.destroy).pack(side="left")
        else:
            def anonymize():
                self._set_clipboard_text(self.anon.anonymize(text, findings))
                self.status.configure(text="✔ Anonymisierte Fassung in der Zwischenablage", foreground="#2e7d32")
                dlg.destroy()
            ttk.Button(b, text="✔ Anonymisieren", command=anonymize).pack(side="left")

        def original():
            self._set_clipboard_text(text)
            dlg.destroy()

        def leeren():
            self._set_clipboard_text("")
            dlg.destroy()
        ttk.Button(b, text="Original verwenden", command=original).pack(side="left", padx=6)
        ttk.Button(b, text="Zwischenablage leeren", command=leeren).pack(side="left")

    def _warn_files(self, paths, report, origin: str, hold: bool) -> None:
        rows = [(Path(p).name, f) for p, fs, _ in report for f in fs]
        self.status.configure(text=f"⚠ {len(rows)} Fund(e) in {len(paths)} Datei(en)", foreground="#c62828")
        dlg = self._dialog(f"Diese Datei(en) enthalten {len(rows)} sensible Angabe(n)", rows)
        b = dlg.buttons

        def anonymize():
            outs = []
            out_dir = TEMP_DIR if origin == "clipboard" else None
            TEMP_DIR.mkdir(exist_ok=True)
            for p, fs, err in report:
                if fs:
                    outs.append(str(write_anonymized(p, self.anon, out_dir=out_dir, use_ki=self.use_ki.get())))
                elif not err:
                    outs.append(p)  # unbedenkliche Dateien unverändert weiterreichen
            if winclip.AVAILABLE:
                self._set_clipboard_files(outs)
            if origin == "drop" and outs and sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", outs[0]])
            self.status.configure(text="✔ Anonymisierte Kopie bereit – jetzt einfügen (Strg+V) oder hineinziehen",
                                  foreground="#2e7d32")
            dlg.destroy()

        def original():
            if hold or origin == "drop":
                self._set_clipboard_files(paths)
            dlg.destroy()

        def abbrechen():
            if hold:
                winclip.clear()
            dlg.destroy()
        ttk.Button(b, text="✔ Anonymisierte Kopie erstellen", command=anonymize).pack(side="left")
        ttk.Button(b, text="Original trotzdem verwenden", command=original).pack(side="left", padx=6)
        ttk.Button(b, text="Abbrechen", command=abbrechen).pack(side="left")
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


def main() -> None:
    if os.environ.get("DATENWAECHTER_NO_GUI"):
        return
    App().run()


if __name__ == "__main__":
    main()
