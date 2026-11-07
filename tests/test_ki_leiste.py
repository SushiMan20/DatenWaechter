"""KI-Aktionsleiste (Windows-Fenster, hier mit Tk): bleibt beim Arbeiten an ihrer Stelle, hängt nie fest."""

from __future__ import annotations

import os
import time

import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture
def app(monkeypatch):
    if not os.environ.get("DISPLAY") and os.name != "nt":
        pytest.skip("kein Bildschirm (xvfb-run)")
    from datenwaechter import actions, toast
    from datenwaechter import gui
    from datenwaechter.gui import App

    class Bruecke:
        def __init__(self):
            self.eingesetzt, self.kaputt = [], False

        def capture(self, hwnd):
            return "Ihre Unterlagen fehlen immer noch.", "alt"

        def deliver(self, hwnd, text, old):
            if self.kaputt:
                raise OSError("Zwischenablage belegt")
            self.eingesetzt.append(text)

        def restore(self, old):
            pass

    zustand = {"dauer": 0.6, "fehler": None}

    def run(aktion, text):
        time.sleep(zustand["dauer"])
        if zustand["fehler"]:
            raise zustand["fehler"]
        return actions.Ergebnis("Bitte nachreichen.", aktion, "openai:m@x", None, False)

    monkeypatch.setattr(actions, "run", run)
    monkeypatch.setattr(toast, "zeiger", lambda win: (300, 200))
    monkeypatch.setattr(gui, "zeiger", lambda win: (300, 200))
    a = App(start_hidden=True)
    pumpen(a, 0.8)
    a.bridge, a.llm_ok = Bruecke(), True
    a.zustand = zustand
    yield a
    a._quit()   # Hooks, Tastenkürzel und Tray-Symbol sauber beenden (unter Windows echt)


def pumpen(app, sek):
    ende = time.time() + sek
    while time.time() < ende:
        app.root.update()
        time.sleep(0.02)


def waehlen(app):
    app._ki_start(1)
    pumpen(app, 0.4)
    p = app._ki_palette
    p.choose(0)
    pumpen(app, 0.2)
    return p


def test_leiste_am_zeiger_bleibt_beim_arbeiten_und_schliesst_danach(app):
    app._ki_start(1)
    pumpen(app, 0.4)
    p = app._ki_palette
    assert (p.winfo_x(), p.winfo_y()) == (312, 212), "direkt rechts unter dem Mauszeiger"
    p.choose(0)
    pumpen(app, 0.2)
    assert p.winfo_exists() and p.modus == "arbeitet" and app._ki_busy
    assert (p.winfo_x(), p.winfo_y()) == (312, 212), "bleibt beim Arbeiten an derselben Stelle"
    pumpen(app, 1.0)
    assert app.bridge.eingesetzt == ["Bitte nachreichen."] and not app._ki_busy
    assert p.modus == "fertig"
    pumpen(app, 1.2)
    assert not p.winfo_exists()


def test_unerwarteter_fehler_haengt_nicht(app):
    from datenwaechter import protokoll
    app.zustand["fehler"] = KeyError("choices")
    p = waehlen(app)
    pumpen(app, 1.0)
    assert not app._ki_busy, "kein ewiges „prüft …“"
    assert p.winfo_exists() and p.arbeit_titel.cget("text") == "Hat nicht geklappt"
    assert "KeyError" in protokoll.datei().read_text(encoding="utf-8")


def test_einfuegen_scheitert_ergebnis_in_zwischenablage(app):
    app.bridge.kaputt = True
    p = waehlen(app)
    pumpen(app, 1.2)
    assert not app._ki_busy and "Zwischenablage" in p.arbeit_info.cget("text")


def test_abbrechen_verwirft_spaete_antwort(app):
    p = waehlen(app)
    p._abbrechen()
    pumpen(app, 1.2)
    assert not app._ki_busy and app.bridge.eingesetzt == []


def test_wachhund_beendet_nach_zeitueberschreitung(app):
    app.zustand["dauer"] = 3
    p = waehlen(app)
    app._ki_wachhund(app._ki_lauf, "alt")
    pumpen(app, 0.2)
    assert not app._ki_busy and p.arbeit_titel.cget("text") == "Hat nicht geklappt"
