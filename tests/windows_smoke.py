"""Praxistest auf echtem Windows (läuft in GitHub Actions auf windows-latest, geht auch auf jedem Windows-PC).

    python tests/windows_smoke.py                      # Windows-Funktionen über die Python-Installation
    python tests/windows_smoke.py --exe dist/Datenwaechter   # zusätzlich das fertige Programm

Prüft, was sich unter Linux nicht testen lässt: Zwischenablage (Text, Dateien, Bilder), Windows-Texterkennung,
globales Tastenkürzel, ✨-Knopf beim Markieren, Benachrichtigung unten rechts (Platz, kein Fokus-Klau), Einsetzen in ein
echtes Programm (Notepad), Browser-Brücke in der Registry und das gebaute Programm selbst.
„✘“ = Pflicht-Test fehlgeschlagen (Exit-Code 1), „⚠“ = optional (z. B. hängt von der Desktop-Sitzung ab).
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SECRET = "Hallo Frau Becker, hier meine IBAN DE89 3704 0044 0532 0130 00 und Tel. 0171 2345678."
RESULTS: list[tuple[str, str, str]] = []
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
TMP = Path(tempfile.mkdtemp(prefix="dw-smoke-"))
os.environ.setdefault("DATENWAECHTER_EINSTELLUNGEN", str(TMP / "einstellungen.json"))
os.environ.setdefault("DATENWAECHTER_KEIN_SCHLUESSELBUND", "1")


def run(name: str, fn, hard: bool = True) -> None:
    t = time.time()
    try:
        detail = fn() or "ok"
        RESULTS.append(("✔", name, f"{detail} ({time.time() - t:.1f} s)"))
    except Exception as e:  # noqa: BLE001
        RESULTS.append(("✘" if hard else "⚠", name, f"{type(e).__name__}: {e}"))
    print(f"{RESULTS[-1][0]} {name}: {RESULTS[-1][2]}", flush=True)


def text_image(path: Path, lines: list[str]) -> Path:
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("arial.ttf", 28)
    img = Image.new("RGB", (1100, 70 + 60 * len(lines)), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((40, 35 + 60 * i), line, font=font, fill="black")
    img.save(path)
    return path


# --------------------------------------------------------------------------- Windows-Funktionen (Python)

def t_clipboard_text():
    from datenwaechter import winclip
    assert winclip.AVAILABLE, "pywin32 fehlt"
    before = winclip.sequence_number()
    winclip.set_text("Grüße ÄÖÜ ß – Test")
    assert winclip.get_text() == "Grüße ÄÖÜ ß – Test"
    assert winclip.sequence_number() != before
    return "Umlaute bleiben erhalten, Änderungszähler läuft"


def t_clipboard_files():
    from datenwaechter import winclip
    f = TMP / "Vertrag äöü.txt"
    f.write_text("IBAN DE89 3704 0044 0532 0130 00", encoding="utf-8")
    winclip.set_files([str(f)])
    got = winclip.get_files()
    assert [os.path.normcase(x) for x in got] == [os.path.normcase(str(f))], got
    return "Datei wie im Explorer kopiert und gelesen"


def t_clipboard_image():
    from PIL import Image
    from datenwaechter import winclip
    winclip.set_image(Image.new("RGB", (120, 80), "red"))
    img = winclip.get_image()
    assert img is not None and img.size == (120, 80), img
    return "Bild (wie Screenshot) gesetzt und gelesen"


def t_ocr_windows():
    from PIL import Image
    from datenwaechter import ocr
    from datenwaechter.detectors import scan_text
    backend = ocr.backend()
    assert backend == "windows", f"Texterkennung: {backend}"
    img = Image.open(text_image(TMP / "ocr.png", ["Invoice for Frau Anna Becker", "IBAN DE89 3704 0044 0532 0130 00",
                                                   "Phone 0171 2345678"]))
    res = ocr.recognize(img)
    kinds = {f.kind for f in scan_text(res.text)}
    assert "IBAN" in kinds, res.text
    return f"Windows-OCR liest: {res.text.splitlines()[1] if len(res.text.splitlines()) > 1 else res.text!r}; Funde: {sorted(kinds)}"


def t_hotkey():
    import ctypes
    from datenwaechter import hotkey
    hits = []
    hk = hotkey.Hotkey("Strg+Alt+Leertaste", lambda hwnd: hits.append(hwnd))
    assert hk.active, hk.error
    u = ctypes.windll.user32
    for vk in (0x11, 0x12, 0x20):
        u.keybd_event(vk, 0, 0, 0)
    for vk in (0x20, 0x12, 0x11):
        u.keybd_event(vk, 0, 2, 0)
    end = time.time() + 3
    while not hits and time.time() < end:
        time.sleep(0.05)
    hk.stop()
    return "registriert und ausgelöst" if hits else "registriert (Tastendruck in dieser Sitzung nicht zustellbar)"


def t_gui_popup():
    import ctypes
    from ctypes import wintypes
    from datenwaechter import winclip
    from datenwaechter.gui import App
    from datenwaechter.toast import TrayPopup, work_area
    app = App(start_hidden=True)
    out = {}

    def copy():
        out["fg_before"] = ctypes.windll.user32.GetForegroundWindow()
        winclip.set_text(SECRET)

    def check():
        p = TrayPopup.current
        out["popup"] = p is not None
        if p:
            p.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(p.winfo_id()) or p.winfo_id()
            out["noactivate"] = bool(ctypes.windll.user32.GetWindowLongW(hwnd, -20) & 0x08000000)
            r = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
            left, top, right, bottom = work_area(p)
            out["rechts"], out["unten"] = right - r.right, bottom - r.bottom
            out["fg_after"] = ctypes.windll.user32.GetForegroundWindow()
            out["popup_hwnd"] = hwnd
        out["clip"] = winclip.get_text()
        out["tray"] = app.tray.available
        app._quit()

    app.root.after(1500, copy)
    app.root.after(4000, check)
    app.run()
    assert out.get("popup"), "keine Benachrichtigung"
    assert "[IBAN_1]" in out["clip"] and "DE89" not in out["clip"], out["clip"]
    assert out["noactivate"], "Benachrichtigung würde den Fokus nehmen"
    assert 0 <= out["rechts"] <= 40 and 0 <= out["unten"] <= 40, out
    assert out["fg_after"] != out["popup_hwnd"], "Benachrichtigung wurde Vordergrundfenster"
    return (f"unten rechts ({out['rechts']}/{out['unten']} px Abstand), nimmt keinen Fokus, Zwischenablage anonymisiert, "
            f"Tray-Symbol: {'ja' if out['tray'] else 'nein'}")


def t_notepad_bridge():
    import ctypes
    from datenwaechter import hotkey, winclip
    u = ctypes.windll.user32
    proc = subprocess.Popen(["notepad.exe"])
    try:
        hwnd = 0
        for _ in range(50):
            time.sleep(0.2)
            hwnd = u.FindWindowW("Notepad", None)
            if hwnd:
                break
        assert hwnd, "Notepad-Fenster nicht gefunden"
        u.ShowWindow(hwnd, 5)
        u.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        b = hotkey.WindowsBridge()
        winclip.set_text("hallo herr becker anbei die unterlagen")
        b._ctrl("V")
        time.sleep(0.4)
        b._ctrl("A")
        time.sleep(0.2)
        text, old = b.capture(hwnd)
        assert "becker" in text, f"markierter Text: {text!r}"
        b.deliver(hwnd, "Sehr geehrter Herr Becker, anbei die Unterlagen.", old)
        time.sleep(0.3)
        b._ctrl("A")
        b._ctrl("C")
        time.sleep(0.4)
        now = winclip.get_text()
        assert now == "Sehr geehrter Herr Becker, anbei die Unterlagen.", now
        return "Text in Notepad markiert, geholt und ersetzt"
    finally:
        proc.kill()


def _notepad_mit_text(text: str):
    """Startet Notepad mit Text; gibt (Prozess, Fenster, Punkt mitten im ersten Wort) zurück."""
    import ctypes
    from ctypes import wintypes
    from datenwaechter import hotkey, winclip
    u = ctypes.windll.user32
    proc = subprocess.Popen(["notepad.exe"])
    hwnd = 0
    for _ in range(50):
        time.sleep(0.2)
        hwnd = u.FindWindowW("Notepad", None)
        if hwnd:
            break
    assert hwnd, "Notepad-Fenster nicht gefunden"
    u.ShowWindow(hwnd, 5)
    u.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    b = hotkey.WindowsBridge()
    winclip.set_text(text)
    b._ctrl("V")
    time.sleep(0.4)
    edit = 0
    for cls in ("Edit", "RichEditD2DPT", "NotepadTextBox"):
        edit = u.FindWindowExW(hwnd, 0, cls, None) or edit
    r = wintypes.RECT()
    u.GetWindowRect(edit or hwnd, ctypes.byref(r))
    oben = r.top + (8 if edit else 80)
    return proc, hwnd, (r.left + 30, oben + 6)


def _doppelklick(x: int, y: int) -> None:
    import ctypes
    u = ctypes.windll.user32
    u.SetCursorPos(x, y)
    u.mouse_event(0x0001, 1, 0, 0, 0)    # kleine Bewegung, damit der Text-Cursor gesetzt wird
    time.sleep(0.2)
    for _ in range(2):
        u.mouse_event(0x0002, 0, 0, 0, 0)
        u.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.05)


def t_auswahl_hook():
    from datenwaechter import auswahl
    events = []
    w = auswahl.Waechter(lambda *e: events.append(e))
    assert w.active, w.error
    proc, hwnd, (x, y) = _notepad_mit_text("hallo herr becker anbei die unterlagen")
    try:
        _doppelklick(x, y)
        end = time.time() + 3
        while not any(e[0] == "auswahl" for e in events) and time.time() < end:
            time.sleep(0.05)
        treffer = [e for e in events if e[0] == "auswahl"]
        assert treffer, f"kein Markieren erkannt (Ereignisse: {[e[0] for e in events]})"
        assert treffer[0][3] == hwnd, "gemeldetes Fenster ist nicht Notepad"
        return "Doppelklick auf Text in Notepad erkannt"
    finally:
        w.stop()
        proc.kill()


def t_auswahl_knopf():
    """Ganzer Ablauf: Wort in Notepad markieren → ✨-Knopf erscheint → Klick → KI-Leiste mit dem markierten Wort."""
    import ctypes
    from datenwaechter.gui import App
    app = App(start_hidden=True)
    out = {}
    orig = app._ki_captured

    def spy(hwnd, text, old):
        out["text"] = text
        out["fg"] = ctypes.windll.user32.GetForegroundWindow()
        orig(hwnd, text, old)
    app._ki_captured = spy

    def start():
        out["proc"], out["hwnd"], (x, y) = _notepad_mit_text("hallo herr becker anbei die unterlagen")
        _doppelklick(x, y)
        app.root.after(1200, klick)

    def klick():
        k = app.knopf
        out["knopf"] = bool(k is not None and k.sichtbar())
        if out["knopf"]:
            u = ctypes.windll.user32
            u.SetCursorPos(k.winfo_rootx() + 12, k.winfo_rooty() + 8)
            time.sleep(0.15)
            u.mouse_event(0x0002, 0, 0, 0, 0)
            u.mouse_event(0x0004, 0, 0, 0, 0)
        app.root.after(2500, ende)

    def ende():
        out["palette"] = app._ki_palette is not None and app._ki_palette.winfo_exists()
        if out["palette"]:
            app._ki_palette.destroy()
        out["proc"].kill()
        app._quit()

    app.root.after(1500, start)
    app.run()
    assert out.get("knopf"), "✨-Knopf ist nach dem Markieren nicht erschienen"
    assert out.get("text", "").strip(), "Klick auf den Knopf hat keinen markierten Text geholt"
    assert out["fg"] == out["hwnd"], "Knopf hat Notepad den Fokus genommen"
    assert out.get("palette"), "KI-Leiste ist nicht aufgegangen"
    return f"Knopf erschienen, markierter Text „{out['text'].strip()}“ geholt, KI-Leiste offen, Fokus blieb in Notepad"


DIALOG_KIND = r"""
import sys, tkinter as tk
from tkinter import filedialog
r = tk.Tk(); r.withdraw()
p = filedialog.askopenfilename(parent=r, initialdir=sys.argv[1], title="Datei für die KI")
print("ERGEBNIS:" + (p or ""), flush=True)
"""

DRAG_KIND = r"""
import sys, tkinter as tk
import pythoncom, winerror, win32con
from win32com.server.util import wrap
sys.path.insert(0, sys.argv[2])
from datenwaechter import winclip
pythoncom.OleInitialize()
winclip.set_files([sys.argv[1]])
daten = pythoncom.OleGetClipboard()

class Quelle:
    _com_interfaces_ = [pythoncom.IID_IDropSource]
    _public_methods_ = ["QueryContinueDrag", "GiveFeedback"]
    def QueryContinueDrag(self, esc, tasten):
        if esc:
            return winerror.DRAGDROP_S_CANCEL
        return winerror.S_OK if tasten & win32con.MK_LBUTTON else winerror.DRAGDROP_S_DROP
    def GiveFeedback(self, wirkung):
        return winerror.DRAGDROP_S_USEDEFAULTCURSORS

r = tk.Tk(); r.geometry("240x140+40+40"); r.title("Quelle"); r.attributes("-topmost", True)
lbl = tk.Label(r, text="Ziehen!", bg="yellow"); lbl.pack(fill="both", expand=True)
def los(_e):
    print("DRAG:", pythoncom.DoDragDrop(daten, wrap(Quelle(), pythoncom.IID_IDropSource), 1), flush=True)
lbl.bind("<ButtonPress-1>", los)
r.after(25000, r.destroy)
r.mainloop()
"""


def _fenster_von(pid: int, klasse: str | None = None):
    import ctypes
    from ctypes import wintypes
    from datenwaechter import schutz
    gefunden = []
    Proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _l):
        if (schutz.fenster_pid(h) == pid and ctypes.windll.user32.IsWindowVisible(h)
                and (klasse is None or schutz.klasse(h) == klasse)):
            gefunden.append(h)
        return True
    ctypes.windll.user32.EnumWindows(Proc(cb), 0)
    return gefunden[0] if gefunden else None


def _klick(x: int, y: int, doppel: bool = False) -> None:
    import ctypes
    u = ctypes.windll.user32
    u.SetCursorPos(x, y)
    u.mouse_event(0x0001, 1, 0, 0, 0)
    time.sleep(0.15)
    for _ in range(2 if doppel else 1):
        u.mouse_event(0x0002, 0, 0, 0, 0)
        u.mouse_event(0x0004, 0, 0, 0, 0)
        time.sleep(0.05)


def t_dialog_schutz():
    """„Datei öffnen“ in einer KI-App (hier: Python-Testprogramm) – Öffnen, Enter und Doppelklick werden geprüft."""
    import ctypes
    from datenwaechter import schutz
    from datenwaechter.gui import App
    from datenwaechter.toast import TrayPopup
    ordner = TMP / "dialog"
    ordner.mkdir(exist_ok=True)
    (ordner / "Vertrag.txt").write_text(SECRET + " Geboren am 12.03.1985, Mia Schneider.", encoding="utf-8")
    (ordner / "Einkauf.txt").write_text("Milch, Brot, Äpfel", encoding="utf-8")
    os.environ["DATENWAECHTER_SCHUTZ_APPS"] = "python.exe"
    app = App(start_hidden=True)
    app.watch.set(False)
    out = {"schritte": []}
    u = ctypes.windll.user32

    def kind():
        p = subprocess.Popen([sys.executable, "-c", DIALOG_KIND, str(ordner)], stdout=subprocess.PIPE, text=True,
                             encoding="utf-8")
        h = None
        for _ in range(60):
            time.sleep(0.2)
            h = _fenster_von(p.pid, "#32770")
            if h:
                break
        assert h, "Dateidialog des Testprogramms nicht gefunden"
        time.sleep(0.6)
        d = schutz.dateidialog(h, frozenset({"python.exe"}))
        assert d, "Dateidialog nicht erkannt (Steuerelemente)"
        return p, d

    def ergebnis(p):
        try:
            text, _ = p.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()
            return "(kein Ergebnis – Dialog noch offen)"
        return next((z.split(":", 1)[1] for z in text.splitlines() if z.startswith("ERGEBNIS:")), "")

    def popup_knopf(name):
        pop = TrayPopup.current
        if pop is None or name not in pop.buttons:
            return f"keine Rückfrage mit „{name}“ (Popup: {pop.buttons.keys() if pop else None})"
        out["schritte"].append(f"Rückfrage: {pop.title() if hasattr(pop, 'title') else ''}")
        pop.buttons[name].event_generate("<Button-1>")
        return None

    def schritt1():   # Datei mit IBAN, Klick auf „Öffnen“ -> Rückfrage -> geschwärzt
        try:
            p, d = kind()
            schutz.setze_text(d.feld, "Vertrag.txt")
            l, t, r, b = schutz.rechteck(d.ok)
            _klick((l + r) // 2, (t + b) // 2)
            out["p"] = p
            app.root.after(3500, schritt1b)
        except Exception as e:  # noqa: BLE001
            out["fehler"] = f"Schritt 1: {e}"
            app._quit()

    def schritt1b():
        fehler = popup_knopf("Geschwärzt übergeben")
        pfad = ergebnis(out["p"])
        out["geschwaerzt"] = (fehler, pfad)
        app.root.after(500, schritt2)

    def schritt2():   # harmlose Datei per Enter -> geht ohne Rückfrage durch
        try:
            p, d = kind()
            schutz.setze_text(d.feld, "Einkauf.txt")
            schutz.nach_vorne(d.hwnd)
            time.sleep(0.3)
            u.keybd_event(0x0D, 0, 0, 0)
            u.keybd_event(0x0D, 0, 2, 0)
            out["p"] = p
            app.root.after(3500, schritt2b)
        except Exception as e:  # noqa: BLE001
            out["fehler"] = f"Schritt 2: {e}"
            app._quit()

    def schritt2b():
        out["harmlos"] = ergebnis(out["p"])
        app.root.after(500, schritt3)

    def schritt3():   # Doppelklick auf „Vertrag“ in der Liste -> Rückfrage -> Original
        try:
            import comtypes.client
            p, d = kind()
            uia = comtypes.client.GetModule("UIAutomationCore.dll")
            auto = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=uia.IUIAutomation)
            liste = auto.ElementFromHandle(d.liste)
            el = None
            for name in ("Vertrag.txt", "Vertrag"):
                el = liste.FindFirst(4, auto.CreatePropertyCondition(30005, name))
                if el:
                    break
            assert el, "Eintrag „Vertrag“ in der Dateiliste nicht gefunden"
            r = el.CurrentBoundingRectangle
            _klick((r.left + r.right) // 2, (r.top + r.bottom) // 2, doppel=True)
            out["p"] = p
            app.root.after(3500, schritt3b)
        except Exception as e:  # noqa: BLE001
            out["doppel"] = (f"Schritt 3: {e}", "")
            app.root.after(100, app._quit)

    def schritt3b():
        fehler = popup_knopf("Original")
        out["doppel"] = (fehler, ergebnis(out["p"]))
        app._quit()

    app.root.after(1500, schritt1)
    try:
        app.run()
    finally:
        os.environ.pop("DATENWAECHTER_SCHUTZ_APPS", None)
    assert "fehler" not in out, out.get("fehler")
    fehler, pfad = out["geschwaerzt"]
    assert not fehler, fehler
    assert pfad.endswith("_anonymisiert.txt"), f"App bekam: {pfad!r}"
    inhalt = Path(pfad).read_text(encoding="utf-8")
    assert "DE89" not in inhalt and "[IBAN_1]" in inhalt, inhalt
    assert Path(out["harmlos"]).name == "Einkauf.txt", f"harmlose Datei: {out['harmlos']!r}"
    meldung = "„Öffnen“ → geschwärzte Kopie übergeben; Enter auf harmloser Datei → ohne Rückfrage"
    fehler3, pfad3 = out.get("doppel", ("nicht gelaufen", ""))
    if fehler3 or Path(pfad3).name != "Vertrag.txt":
        raise AssertionError(f"{meldung}; Doppelklick: {fehler3 or pfad3!r}")
    return meldung + "; Doppelklick → Rückfrage → Original"


def t_drop_schutz():
    """Echtes Ziehen (OLE Drag & Drop) einer Datei über eine KI-App (hier: Notepad) -> Auffangfläche -> geschwärzt."""
    import ctypes
    from datenwaechter import schutz, winclip
    from datenwaechter.gui import App
    from datenwaechter.toast import TrayPopup
    datei = TMP / "Brief.txt"
    datei.write_text(SECRET, encoding="utf-8")
    os.environ["DATENWAECHTER_SCHUTZ_APPS"] = "notepad.exe"
    os.environ["DATENWAECHTER_DRAG_QUELLEN"] = "python.exe"
    app = App(start_hidden=True)
    app.watch.set(False)
    out = {"ereignisse": []}
    orig = app._schutz_ereignis
    app._schutz_ereignis = lambda art, h, x=None: (out["ereignisse"].append(art), orig(art, h, x))
    u = ctypes.windll.user32
    sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)

    def bewege(x, y):
        u.mouse_event(0x8001, int(x * 65535 / sw), int(y * 65535 / sh), 0, 0)   # MOVE | ABSOLUTE

    def ziehen():
        try:
            note = subprocess.Popen(["notepad.exe"])
            quelle = subprocess.Popen([sys.executable, "-c", DRAG_KIND, str(datei), str(ROOT)],
                                      stdout=subprocess.PIPE, text=True)
            out["prozesse"] = (note, quelle)
            hn = hq = None
            for _ in range(50):
                time.sleep(0.2)
                hn = hn or u.FindWindowW("Notepad", None)
                hq = hq or _fenster_von(quelle.pid)
                if hn and hq:
                    break
            assert hn and hq, "Notepad oder Ziehquelle nicht gefunden"
            u.MoveWindow(hn, 400, 200, 700, 500, True)
            time.sleep(0.8)
            ql, qt, qr, qb = schutz.rechteck(hq)
            sx, sy = (ql + qr) // 2, (qt + qb) // 2 + 10
            tx, ty = 750, 450
            u.SetCursorPos(sx, sy)
            bewege(sx, sy)
            time.sleep(0.3)
            u.mouse_event(0x0002, 0, 0, 0, 0)          # Maustaste runter in der Quelle -> DoDragDrop startet
            time.sleep(0.4)
            for i in range(1, 31):
                bewege(sx + (tx - sx) * i // 30, sy + (ty - sy) * i // 30)
                time.sleep(0.03)
            for _ in range(15):                         # über dem Ziel etwas bewegen, bis die Auffangfläche da ist
                bewege(tx + _ % 3, ty)
                time.sleep(0.08)
            u.mouse_event(0x0004, 0, 0, 0, 0)          # loslassen = ablegen
        except Exception as e:  # noqa: BLE001
            out["fehler"] = str(e)

    def pruefen():
        pop = TrayPopup.current
        out["popup"] = bool(pop and "Geschwärzt übergeben" in pop.buttons)
        if out["popup"]:
            pop.buttons["Geschwärzt übergeben"].event_generate("<Button-1>")
        app.root.after(2000, ende)

    def ende():
        out["zwischenablage"] = winclip.get_files()
        for p in out.get("prozesse", ()):
            p.kill()
        app._quit()

    app.root.after(1500, lambda: threading.Thread(target=ziehen, daemon=True).start())
    app.root.after(12000, pruefen)
    try:
        app.run()
    finally:
        os.environ.pop("DATENWAECHTER_SCHUTZ_APPS", None)
        os.environ.pop("DATENWAECHTER_DRAG_QUELLEN", None)
    assert "fehler" not in out, out["fehler"]
    assert "drop-zeigen" in out["ereignisse"], f"Auffangfläche nicht gezeigt (Ereignisse: {out['ereignisse']})"
    assert out.get("popup"), f"keine Rückfrage nach dem Ablegen (Ereignisse: {out['ereignisse']})"
    dateien = out.get("zwischenablage") or []
    assert dateien and dateien[0].endswith("_anonymisiert.txt"), f"übergeben: {dateien}"
    assert "DE89" not in Path(dateien[0]).read_text(encoding="utf-8")
    return "Ziehen über Notepad → Auffangfläche → Rückfrage → geschwärzte Fassung übergeben"


def t_browser_bridge():
    import winreg
    from datenwaechter import browser_bridge
    manifest = browser_bridge.install()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{browser_bridge.REG_KEYS[0]}\{browser_bridge.HOST}") as k:
        assert winreg.QueryValueEx(k, "")[0] == str(manifest)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["allowed_origins"] == [f"chrome-extension://{browser_bridge.EXTENSION_ID}/"]
    assert browser_bridge.is_installed()
    browser_bridge.uninstall()
    assert not browser_bridge.is_installed()
    return "Registry-Einträge für Chrome/Edge/Brave gesetzt und wieder entfernt"


# --------------------------------------------------------------------------- Fertiges Programm (.exe)

def exe_tests(dist: Path) -> None:
    cli, gui = dist / "datenwaechter-cli.exe", dist / "Datenwaechter.exe"
    env = dict(os.environ)

    def c(*args, **kw):
        return subprocess.run([str(cli), *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=180, env=env, **kw)   # Ausgabe umgeleitet: muss als UTF-8 kommen, ohne Absturz

    def t_help():
        r = c("--help")
        assert r.returncode == 0 and "browser-bruecke" in r.stdout, r.stderr[-500:]
        return "Kommandozeile startet"

    def t_scan_files():
        txt = TMP / "brief.txt"
        txt.write_text(SECRET, encoding="utf-8")
        from reportlab.pdfgen import canvas
        pdf = TMP / "vertrag.pdf"
        cv = canvas.Canvas(str(pdf))
        cv.drawString(72, 750, "Arbeitsvertrag mit Herrn Klaus Becker, IBAN DE89 3704 0044 0532 0130 00")
        cv.drawString(72, 730, "Probezeit: 6 Monate, Gehalt laut Anlage")
        cv.save()
        img = text_image(TMP / "screenshot.png", ["Transfer to IBAN DE89 3704 0044 0532 0130 00"])
        r = c("--kein-sprachmodell", "scan", str(txt), str(pdf), str(img), str(ROOT / "tests" / "fixtures" / "gesicht.jpg"))
        out = r.stdout
        assert r.returncode == 2, (r.returncode, out[-800:], r.stderr[-800:])
        assert out.count("IBAN") >= 3, out
        assert "Gesicht" in out and "Personal- und Arbeitsunterlagen" in out, out
        r = c("anonymisieren", str(pdf), str(img), "--ziel", str(TMP / "aus"))
        assert r.returncode == 0 and (TMP / "aus" / "vertrag_anonymisiert.pdf").exists(), r.stderr[-800:]
        return "Text, PDF, Screenshot (Windows-OCR) und Foto geprüft, PDF + Bild geschwärzt"

    def t_native_host():
        msg = json.dumps({"action": "ping"}).encode()
        r = subprocess.run([str(cli), "chrome-extension://cfehnnbcppbopfbeiledoobmkgdffomd/", "--parent-window=0"],
                           input=struct.pack("=I", len(msg)) + msg, capture_output=True, timeout=120, env=env)
        n = struct.unpack("=I", r.stdout[:4])[0]
        reply = json.loads(json.loads(r.stdout[4:4 + n])["data"])
        assert reply["ok"] and reply["ocr"] == "windows" and reply["faces"], reply
        return f"Browser-Brücke antwortet: Version {reply['version']}, OCR {reply['ocr']}, Gesichter {reply['faces']}"

    def t_gui_start():
        marker = TMP / "gestartet.txt"
        e = dict(env, DATENWAECHTER_STARTMARKER=str(marker), DATENWAECHTER_SMOKE_MS="4000")
        p = subprocess.Popen([str(gui), "--minimiert"], env=e)
        try:
            p.wait(timeout=60)
        except subprocess.TimeoutExpired:
            p.kill()
            raise AssertionError("Programm hat sich nicht selbst beendet (Absturz-Dialog?)")
        assert marker.exists(), "Startmarke fehlt – Fenster ist nicht hochgekommen"
        info = marker.read_text(encoding="utf-8")
        assert "tray=True" in info and "hotkey=True" in info, info
        return f"Datenwaechter.exe startet im Infobereich ({info})"

    run("Programm: Kommandozeile", t_help)
    run("Programm: Dateien prüfen und schwärzen", t_scan_files)
    run("Programm: Browser-Brücke (Native Messaging)", t_native_host)
    run("Programm: Datenwaechter.exe startet mit Tray + Tastenkürzel", t_gui_start)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", help="Ordner mit Datenwaechter.exe und datenwaechter-cli.exe")
    ap.add_argument("--nur-exe", action="store_true")
    args = ap.parse_args()
    if not args.nur_exe:
        run("Zwischenablage: Text", t_clipboard_text)
        run("Zwischenablage: Dateien", t_clipboard_files)
        run("Zwischenablage: Bild", t_clipboard_image)
        run("Windows-Texterkennung", t_ocr_windows)
        run("Tastenkürzel Strg+Alt+Leertaste", t_hotkey)
        run("Benachrichtigung beim Kopieren", t_gui_popup)
        run("KI-Aktion: Text in Notepad holen und ersetzen", t_notepad_bridge, hard=False)
        run("✨-Knopf: Markieren in Notepad erkennen", t_auswahl_hook, hard=False)
        run("✨-Knopf: Klick öffnet KI-Leiste mit markiertem Text", t_auswahl_knopf, hard=False)
        run("KI-App-Schutz: „Datei öffnen“ (Öffnen, Enter, Doppelklick)", t_dialog_schutz, hard=False)
        run("KI-App-Schutz: Drag & Drop über das App-Fenster", t_drop_schutz, hard=False)
        run("Browser-Brücke einrichten/entfernen", t_browser_bridge)
    if args.exe:
        exe_tests(Path(args.exe))
    lines = ["| | Prüfung | Ergebnis |", "|---|---|---|"] + [f"| {s} | {n} | {d} |" for s, n, d in RESULTS]
    summary = "\n".join(lines)
    print("\n" + summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("### Windows-Praxistest\n\n" + summary + "\n")
    return 1 if any(s == "✘" for s, _, _ in RESULTS) else 0


if __name__ == "__main__":
    sys.exit(main())
