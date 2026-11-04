"""KI-Aktionen (Rechtsklick / Tastenkürzel): Umformulieren & Co. über den eigenen KI-Server."""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from datenwaechter import actions, llm, settings
from datenwaechter.settings import LlmSettings

TOKEN = "t-123"


@pytest.fixture
def ki():
    """OpenAI-kompatibler Server, der den Text zwischen <<< >>> „umformuliert“ (Großbuchstaben + Präfix)."""
    state = {"requests": [], "reply": None}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            self._send({"data": [{"id": "schreib-modell"}]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert self.headers["Authorization"] == f"Bearer {TOKEN}"
            state["requests"].append(body)
            user = body["messages"][-1]["content"]
            inner = re.search(r"<<<\n(.*)\n>>>", user, re.S).group(1)
            text = state["reply"] or f'"Neu: {inner}"'   # Anführungszeichen drumherum werden entfernt
            self._send({"choices": [{"message": {"content": text}}]})

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{srv.server_port}/v1"
    yield state
    srv.shutdown()


def _server(url, **kw):
    settings.save_llm(LlmSettings(typ="openai", url=url, token=TOKEN, modell="schreib-modell", **kw))
    llm._cache.clear()


TEXT = "Hallo Herr Becker, die IBAN DE89 3704 0044 0532 0130 00 stimmt so."


def test_standardaktionen_und_eigene():
    assert [a.id for a in actions.load()][:2] == ["umformulieren", "kuerzen"]
    liste = actions.load() + [actions.Aktion("Als Tweet", "Mach einen Tweet daraus", "anzeigen")]
    actions.save(liste)
    a = actions.find("als-tweet")
    assert a and a.modus == "anzeigen" and actions.find("Als Tweet") == a


def test_umformulieren_ueber_eigenen_server(ki):
    _server(ki["url"])
    r = actions.run("umformulieren", TEXT)
    assert r.text == f"Neu: {TEXT}"
    req = ki["requests"][0]
    assert "Formuliere den Text um" in req["messages"][-1]["content"]
    assert "Platzhalter" in req["messages"][0]["content"]
    assert r.sent_to is None and not r.anonymized, "lokaler Server: keine Anonymisierung nötig"


def test_externer_server_sieht_keine_echten_daten(ki):
    _server(ki["url"], anonymisieren=True)
    r = actions.run("umformulieren", TEXT)
    gesendet = ki["requests"][0]["messages"][-1]["content"]
    assert "Becker" not in gesendet and "DE89" not in gesendet
    assert "[PERSON_1]" in gesendet and "[IBAN_1]" in gesendet
    assert r.text == f"Neu: {TEXT}", "Platzhalter in der Antwort werden wieder durch die echten Werte ersetzt"
    assert r.anonymized


def test_antwort_wird_bereinigt(ki):
    ki["reply"] = "```\nKurzer Text.\n```"
    _server(ki["url"])
    assert actions.run("kuerzen", "Ein sehr langer Text.").text == "Kurzer Text."


def test_fehlermeldungen(ki):
    with pytest.raises(llm.LlmError, match="Kein KI-Server"):
        actions.run("umformulieren", TEXT)
    _server(ki["url"])
    with pytest.raises(llm.LlmError, match="Kein Text"):
        actions.run("umformulieren", "   ")
    with pytest.raises(llm.LlmError, match="nicht gefunden"):
        actions.run("gibt-es-nicht", TEXT)


def test_browser_bruecke(ki):
    from datenwaechter.native_host import handle
    _server(ki["url"])
    liste = handle({"action": "list_actions"})
    assert liste["ok"] and liste["llm"] and {"id": "zusammenfassen", "name": "Zusammenfassen", "mode": "anzeigen"} in liste["actions"]
    r = handle({"action": "run_action", "id": "antwort-entwerfen", "text": "Kommst du morgen?"})
    assert r["ok"] and r["mode"] == "einfuegen" and r["result"] == "Neu: Kommst du morgen?"
    assert handle({"action": "run_action", "id": "umformulieren", "text": ""})["ok"] is False


@pytest.mark.parametrize("combo,expected", [
    ("Strg+Alt+Leertaste", (0x2 | 0x1, 0x20)),
    ("Ctrl+Shift+K", (0x2 | 0x4, ord("K"))),
    ("Win+Alt+F9", (0x8 | 0x1, 0x78)),
])
def test_tastenkuerzel_lesen(combo, expected):
    from datenwaechter.hotkey import parse
    assert parse(combo) == expected


@pytest.mark.parametrize("falsch", ["Leertaste", "Strg+Hupe", "Foo+K"])
def test_tastenkuerzel_fehler(falsch):
    from datenwaechter.hotkey import parse
    with pytest.raises(ValueError):
        parse(falsch)


def test_tastenkuerzel_speichern():
    assert actions.load_hotkey() == "Strg+Alt+Leertaste"
    actions.save_hotkey("Strg+Umschalt+K")
    assert actions.load_hotkey() == "Strg+Umschalt+K"
    assert actions.load()[0].name == "Umformulieren", "Aktionen bleiben beim Speichern des Kürzels erhalten"
