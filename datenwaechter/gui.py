"""Das Wächter-Fenster (Windows).

- überwacht die Zwischenablage: Text, im Explorer kopierte Dateien und Bilder (Screenshots)
- warnt mit einer Liste der Funde und dem Inhalts-Check („Du lädst gerade Familienunterlagen hoch“)
- nimmt Dateien per Drag & Drop entgegen und erzeugt anonymisierte bzw. geschwärzte Kopien
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

from . import content_check, llm, ner, ocr, settings, winclip
from .analysis import analyze, anonymize as anonymize_report
from .anonymize import Anonymizer
from .detectors import HOCH, SEVERITY_LABEL, scan_text
from .faces import available as faces_available

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

POLL_MS = 200
MIN_CONTENT_CHECK = 400   # kopierte Texte erst ab dieser Länge auf Themen prüfen (sonst zu viele Hinweise)
TEMP_DIR = Path(tempfile.gettempdir()) / "datenwaechter"
COLORS = {HOCH: "#c62828", 2: "#ef6c00", 1: "#757575", 0: "#1565c0"}


class App:
    def __init__(self) -> None:
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title("Datenwächter")
        self.root.geometry("440x380")
        self.root.minsize(400, 340)

        self.anon = Anonymizer()
        self.results: queue.Queue = queue.Queue()
        self.watch = tk.BooleanVar(value=True)
        self.safe = tk.BooleanVar(value=True)
        self.use_ki = tk.BooleanVar(value=False)
        self.use_llm = tk.BooleanVar(value=False)
        self.topmost = tk.BooleanVar(value=True)
        self._last_seq = winclip.sequence_number()
        self._last_text = self._tk_clipboard_text()
        self._ignore_seq: int | None = None
        self._busy = False

        self._build()
        self.root.attributes("-topmost", True)
        self.root.after(POLL_MS, self._poll)
        threading.Thread(target=self._detect_llm, daemon=True).start()

    # ------------------------------------------------------------------ Aufbau
    def _build(self) -> None:
        pad = {"padx": 10, "pady": 4}
        ttk.Label(self.root, text="🛡  Datenwächter", font=("Segoe UI", 14, "bold")).pack(anchor="w", **pad)
        self.status = ttk.Label(self.root, text="Überwache Zwischenablage …", foreground="#2e7d32")
        self.status.pack(anchor="w", padx=10)

        drop = tk.Label(self.root, text="Datei hierher ziehen (PDF, Word, Bild, Text)\n– wird geprüft, bevor sie zur KI geht –",
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
        ki = ttk.Checkbutton(opts, text="Namen ohne Anrede finden (lokales KI-Modell)", variable=self.use_ki)
        ki.grid(row=2, column=0, sticky="w")
        if not ner.available():
            ki.state(["disabled"])
            ki.configure(text="Namen ohne Anrede finden (pip install datenwaechter[ki])")
        self.llm_box = ttk.Checkbutton(opts, text="Inhalts-Check mit KI (Server wird gesucht …)",
                                       variable=self.use_llm)
        self.llm_box.state(["disabled"])
        self.llm_box.grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(opts, text="Immer im Vordergrund", variable=self.topmost,
                        command=lambda: self.root.attributes("-topmost", self.topmost.get())).grid(
            row=4, column=0, sticky="w")
        caps = [f"Texterkennung: {ocr.backend() or 'fehlt'}", f"Gesichter: {'ja' if faces_available() else 'fehlt'}"]
        ttk.Label(opts, text=" · ".join(caps), foreground="#777").grid(row=5, column=0, sticky="w", pady=(4, 0))

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", padx=10, pady=8)
        ttk.Button(btns, text="KI-Antwort zurückübersetzen", command=self._restore_clipboard).pack(
            side="left", expand=True, fill="x")
        ttk.Button(btns, text="Zuordnung", command=self._show_mapping).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="KI-Server …", command=self._llm_settings).pack(side="left", padx=(6, 0))

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
        self.status.configure(text=f"Prüfe {len(paths)} Datei(en) …", foreground="#ef6c00")

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
            if item[0] == "llm":
                if item[1]:
                    label, extern = item[1]
                    self.llm_box.state(["!disabled"])
                    self.llm_box.configure(text=f"Inhalts-Check mit KI ({label.partition(':')[2]})"
                                                + (" – extern" if extern else ""))
                    self.use_llm.set(True)
                else:
                    self.llm_box.state(["disabled"])
                    self.use_llm.set(False)
                    self.llm_box.configure(text="Inhalts-Check mit KI (kein Server – „KI-Server …“ einrichten)")
                continue
            self._busy = False
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
        self.status.configure(text=note or "✔ Keine sensiblen Daten gefunden",
                              foreground="#ef6c00" if note else "#2e7d32")

    # ------------------------------------------------------------------ Warnungen
    def _dialog(self, title: str, rows: list[tuple[str, dict]], verdicts=(), notes=()) -> tk.Toplevel:
        self.root.bell()
        dlg = tk.Toplevel(self.root)
        dlg.title("Datenwächter – Achtung")
        dlg.attributes("-topmost", True)
        dlg.geometry("680x420" if rows else "680x220")
        worst = max([r["severity"] for _, r in rows] + [v.severity for v in verdicts] + [0])
        tk.Label(dlg, text=f"⚠  {title}", bg=COLORS[worst], fg="white", font=("Segoe UI", 12, "bold"),
                 anchor="w", padx=10, pady=8).pack(fill="x")
        for v in verdicts:
            text = f"🧠 {v.warning} Willst du das wirklich?"
            if v.description:
                text += f"\n{v.description}"
            text += "\n" + v.source_text()
            tk.Label(dlg, text=text, bg="#fff3e0", fg="#5d4037", justify="left", anchor="w", wraplength=640,
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
            ttk.Label(dlg, text=f"ℹ {n}", foreground="#777").pack(anchor="w", padx=12)
        dlg.buttons = ttk.Frame(dlg)
        dlg.buttons.pack(fill="x", side="bottom", padx=10, pady=(4, 10))
        dlg.focus_force()
        return dlg

    def _warn_text(self, text: str, findings, verdict) -> None:
        verdicts = [verdict] if verdict and verdict.warning else []
        rows = [("Text", {"label": f.label, "display": f.masked(), "severity": f.severity}) for f in findings]
        self.status.configure(text=f"⚠ {len(findings)} Fund(e) in kopiertem Text" if findings
                              else "⚠ Sensibles Thema im kopierten Text", foreground="#c62828")
        dlg = self._dialog(f"Du hast {len(findings)} sensible Angabe(n) kopiert" if findings
                           else "Bitte kurz prüfen, was du kopiert hast", rows, verdicts)
        b = dlg.buttons
        if findings and self.safe.get():
            ttk.Label(b, text="Die Zwischenablage enthält bereits die anonymisierte Fassung.").pack(anchor="w")
            ttk.Button(b, text="✔ Anonymisiert lassen", command=dlg.destroy).pack(side="left")
        elif findings:
            def anonymize():
                self._set_clipboard_text(self.anon.anonymize(text, findings))
                self.status.configure(text="✔ Anonymisierte Fassung in der Zwischenablage", foreground="#2e7d32")
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
        self.status.configure(text=f"⚠ {len(rows)} Fund(e) in {len(reports)} Datei(en)", foreground="#c62828")
        title = (f"{len(rows)} sensible Angabe(n) gefunden" if rows else
                 "Bitte kurz prüfen, was du hochlädst" if verdicts else "Nicht vollständig prüfbar")
        dlg = self._dialog(title, rows, verdicts, notes)
        b = dlg.buttons

        def anonymize():
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
            self.status.configure(text="✔ Anonymisierte Fassung bereit – jetzt einfügen (Strg+V) oder hineinziehen",
                                  foreground="#2e7d32")
            dlg.destroy()

        def original():
            self._release(paths, origin, True, original_image)
            dlg.destroy()

        def abbrechen():
            if hold:
                winclip.clear()
                self._mark_own_write()
            dlg.destroy()
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
        """Einstellungen für den KI-Server: Ollama oder eigener OpenAI-kompatibler Server mit URL + Token."""
        s = settings.load_llm()
        win = tk.Toplevel(self.root)
        win.title("KI-Server für den Inhalts-Check")
        win.attributes("-topmost", True)
        win.geometry("660x420")
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        arten = {"auto": "Automatisch (eigener Server, sonst Ollama)", "openai": "Eigener Server (OpenAI-kompatibel)",
                 "ollama": "Nur Ollama (lokal)", "aus": "Aus – nur Stichwörter"}
        art = tk.StringVar(value=arten.get(s.typ, arten["auto"]))
        url, token, modell = tk.StringVar(value=s.url), tk.StringVar(value=s.token), tk.StringVar(value=s.modell)
        bilder, anon = tk.BooleanVar(value=s.send_images), tk.BooleanVar(value=s.anonymize_first)

        ttk.Label(frm, text="Art").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Combobox(frm, textvariable=art, values=list(arten.values()), state="readonly").grid(
            row=0, column=1, columnspan=2, sticky="ew")
        ttk.Label(frm, text="Basis-URL").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(frm, textvariable=url, values=[u for _, u in settings.URL_VORLAGEN]).grid(
            row=1, column=1, columnspan=2, sticky="ew")
        ttk.Label(frm, text="z. B. http://localhost:1234/v1 (LM Studio) oder Firmen-Gateway",
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

        status = ttk.Label(frm, text="", wraplength=520, justify="left")

        def current() -> settings.LlmSettings:
            typ = next(k for k, v in arten.items() if v == art.get())
            return settings.LlmSettings(typ=typ, url=url.get().strip(), token=token.get().strip(),
                                        modell=modell.get().strip(), bilder_senden=bilder.get(),
                                        anonymisieren=anon.get())

        def in_thread(fn, done):
            threading.Thread(target=lambda: (lambda r: win.after(0, lambda: done(r)))(fn()), daemon=True).start()

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

        ttk.Checkbutton(frm, text="Bilder/Fotos zur Bewertung mitsenden", variable=bilder).grid(
            row=5, column=1, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Checkbutton(frm, text="Text vorher anonymisieren (Namen, IBAN … → Platzhalter)",
                        variable=anon).grid(row=6, column=1, columnspan=2, sticky="w")
        warn = ttk.Label(frm, text="", foreground="#c62828", wraplength=520, justify="left")
        warn.grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))
        status.grid(row=8, column=0, columnspan=3, sticky="w", pady=(6, 0))

        last_extern = [None]

        def on_url(*_):
            extern = settings.is_external(url.get())
            if extern != last_extern[0]:  # Voreinstellungen passend zur Art des Servers
                last_extern[0] = extern
                if extern:
                    bilder.set(False)
                    anon.set(True)
            host = settings.LlmSettings(url=url.get()).host
            warn.configure(text=(f"⚠ Externer Server ({host}): Inhalte verlassen deinen PC bzw. dein Netz. "
                                 "Nur nutzen, wenn du dem Anbieter vertraust (z. B. Firmenvertrag/AV-Vertrag).")
                           if extern else "")
        url.trace_add("write", on_url)
        last_extern[0] = settings.is_external(s.url)
        on_url()

        def test():
            status.configure(text="Teste Verbindung …", foreground="#555")
            in_thread(lambda: llm.test_connection(current()),
                      lambda r: status.configure(text=r[1], foreground="#2e7d32" if r[0] else "#c62828"))

        def save():
            p = settings.save_llm(current())
            llm._cache.clear()
            self.llm_box.configure(text="Inhalts-Check mit KI (Server wird gesucht …)")
            threading.Thread(target=self._detect_llm, daemon=True).start()
            status.configure(text=f"Gespeichert in {p}", foreground="#2e7d32")
            win.after(700, win.destroy)

        btns = ttk.Frame(frm)
        btns.grid(row=9, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Button(btns, text="Verbindung testen", command=test).pack(side="left")
        ttk.Button(btns, text="Speichern", command=save).pack(side="left", padx=6)
        ttk.Button(btns, text="Abbrechen", command=win.destroy).pack(side="left")
        win.widgets = {"art": art, "url": url, "token": token, "modell": modell, "bilder": bilder, "anon": anon,
                       "status": status, "test": test, "save": save, "load_models": load_models, "warn": warn}

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
