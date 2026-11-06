"""Bausteine der Oberfläche: Symbole, Tageszähler, Autostart, Tray-Texte."""

import datetime as dt
import json

from datenwaechter import autostart, stats as stats_mod
from datenwaechter.icons import FARBEN, shield
from datenwaechter.tray import _safe


def test_symbole_je_zustand():
    imgs = {s: shield(s, 32) for s in FARBEN}
    assert all(i.size == (32, 32) and i.mode == "RGBA" for i in imgs.values())
    mitte = {s: i.getpixel((10, 8))[:3] for s, i in imgs.items()}  # Schildfläche, kein Symbol
    assert len(set(mitte.values())) == 4, "jeder Zustand hat eine eigene Farbe"
    assert imgs["aktiv"].getpixel((0, 31))[3] == 0, "Ecken sind durchsichtig"


def test_erweiterungs_symbole_vorhanden():
    from pathlib import Path
    icons = Path(__file__).resolve().parent.parent / "extension" / "icons"
    for state in ("aktiv", "pause"):
        for size in (16, 32, 48, 128):
            assert (icons / f"{state}-{size}.png").exists()


def test_tageszaehler_und_tageswechsel(tmp_path):
    s = stats_mod.Stats()
    s.inc("geprueft", 3)
    s.inc("gewarnt")
    assert stats_mod.Stats().get("geprueft") == 3, "Zähler bleiben nach Neustart erhalten"
    assert "3 geprüft · 1 gewarnt · 0 anonymisiert" in s.summary()
    gestern = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    s.file.write_text(json.dumps({"datum": gestern, "geprueft": 9, "gewarnt": 9, "anonymisiert": 9}))
    assert stats_mod.Stats().get("geprueft") == 0, "neuer Tag = neue Zählung"


def test_autostart_ein_aus(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert not autostart.is_enabled()
    autostart.set_enabled(True)
    assert autostart.is_enabled()
    assert "-m datenwaechter gui --minimiert" in (tmp_path / "autostart" / "datenwaechter.desktop").read_text()
    autostart.set_enabled(False)
    assert not autostart.is_enabled()


def test_tray_texte_ueberall_darstellbar(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    t = _safe("Datenwächter – Schutz aktiv … · ok")
    t.encode("latin-1")  # darf nicht scheitern
    assert t.startswith("Datenwächter - Schutz aktiv")


def test_auswahl_knopf_einstellung():
    from datenwaechter import auswahl
    assert auswahl.aktiv(), "standardmäßig an"
    auswahl.speichern(False)
    assert not auswahl.aktiv()
    auswahl.speichern(True)
    assert auswahl.aktiv()


def test_auswahl_knopf_zeigen_und_klicken():
    import pytest
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("keine Anzeige")
    from datenwaechter.knopf import Knopf
    try:
        root.withdraw()
        klicks = []
        k = Knopf(root, dark=False, font="Segoe UI", hotkey="Strg+Alt+Leertaste")
        k.zeigen(200, 150, lambda: klicks.append(1))
        root.update()
        assert k.sichtbar() and k.enthaelt(k.winfo_rootx() + 5, k.winfo_rooty() + 5)
        assert not k.enthaelt(5, 5)
        assert "Strg+Alt+Leertaste" in k.tooltip
        k._klick()
        root.update()
        assert klicks == [1] and not k.sichtbar(), "Klick startet KI-Aktionen und blendet den Knopf aus"
    finally:
        root.destroy()
