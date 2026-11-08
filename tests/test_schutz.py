"""KI-Apps schützen: Drop-Schutz und „Datei öffnen“-Schutz – die Teile, die sich ohne Windows prüfen lassen.
Der echte Ablauf (Hook, Dialog, Ziehen) läuft in tests/windows_smoke.py auf Windows."""

from pathlib import Path

import pytest

from datenwaechter import schutz


def test_adresse_des_dialogs(tmp_path):
    assert schutz.ordner_aus_adresse("Adresse: C:\\Users\\mia\\Downloads") == Path("C:\\Users\\mia\\Downloads")
    assert schutz.ordner_aus_adresse("Address: \\\\server\\freigabe") == Path("\\\\server\\freigabe")
    assert schutz.ordner_aus_adresse("C:\\Daten") == Path("C:\\Daten")
    assert schutz.ordner_aus_adresse("") is None
    assert schutz.ordner_aus_adresse("Adresse: Bibliotheken\\Unbekannt") is None


def test_dateiname_feld():
    assert schutz.namen_aus_feld("Vertrag.pdf") == ["Vertrag.pdf"]
    assert schutz.namen_aus_feld('"a.pdf" "b c.pdf"') == ["a.pdf", "b c.pdf"]
    assert schutz.namen_aus_feld('"C:\\x\\a.pdf"') == ["C:\\x\\a.pdf"]
    assert schutz.namen_aus_feld("  ") == []


def test_anzeigename_ohne_endung(tmp_path):
    (tmp_path / "Vertrag.pdf").write_text("x")
    (tmp_path / "Ordner").mkdir()
    assert schutz.aufloesen(tmp_path, "Vertrag.pdf") == tmp_path / "Vertrag.pdf"
    assert schutz.aufloesen(tmp_path, "Vertrag") == tmp_path / "Vertrag.pdf", "Windows blendet Endungen aus"
    assert schutz.aufloesen(tmp_path, "Ordner").is_dir()
    assert schutz.aufloesen(tmp_path, "Fehlt") is None
    assert schutz.aufloesen(None, "Vertrag") is None
    assert schutz.aufloesen(None, str(tmp_path / "Vertrag.pdf")) == tmp_path / "Vertrag.pdf"


def test_apps_und_schalter(monkeypatch):
    assert "chatgpt.exe" in schutz.apps() and "claude.exe" in schutz.apps()
    assert schutz.app_name("claude.exe") == "Claude" and schutz.app_name("Copilot.exe") == "Copilot"
    monkeypatch.setenv("DATENWAECHTER_SCHUTZ_APPS", "python.exe, Notepad.exe")
    assert schutz.apps() == {"python.exe", "notepad.exe"}
    assert schutz.aktiv()
    schutz.speichern(False)
    assert not schutz.aktiv()
    schutz.speichern(True)


def test_waechter_nur_unter_windows():
    import sys
    if sys.platform == "win32":
        pytest.skip("läuft unter Windows im Praxistest")
    assert not schutz.Waechter(lambda *e: None).active


def test_auffangflaeche():
    tk = pytest.importorskip("tkinter")
    pytest.importorskip("tkinterdnd2")
    from tkinterdnd2 import TkinterDnD
    try:
        root = TkinterDnD.Tk()
    except (tk.TclError, RuntimeError):
        pytest.skip("keine Anzeige oder tkdnd")
    from datenwaechter.auffang import Auffangflaeche
    try:
        root.withdraw()
        drops = []
        a = Auffangflaeche(root, font="DejaVu Sans", on_drop=lambda d, art: drops.append((d, art)))
        a.zeigen((100, 80, 700, 480), "ChatGPT")
        root.update()
        assert a.aktiv and a.winfo_viewable() and a.winfo_width() == 600
        assert "bevor ChatGPT sie bekommt" in a.unter.cget("text")

        class E:
            data, type, action = "{C:/Daten/Vertrag.pdf}", "DND_Files", "copy"
        assert a._drop(E()) == "copy"
        assert drops == [("{C:/Daten/Vertrag.pdf}", "dateien")] and not a.aktiv
    finally:
        root.destroy()


def test_tastatur_markieren_nicht_in_explorer_excel_konsole():
    from datenwaechter.auswahl import tastatur_ausgeschlossen
    for fenster in ("CabinetWClass", "Progman", "WorkerW", "XLMAIN", "ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"):
        assert tastatur_ausgeschlossen(fenster), fenster
    assert tastatur_ausgeschlossen("#32770", "SysListView32"), "Dateiliste im Öffnen-Dialog"
    for fenster, fokus in (("Notepad", "RichEditD2DPT"), ("Chrome_WidgetWin_1", "Chrome_RenderWidgetHostHWND"),
                           ("OpusApp", "_WwG"), ("#32770", "Edit")):
        assert not tastatur_ausgeschlossen(fenster, fokus), (fenster, fokus)
