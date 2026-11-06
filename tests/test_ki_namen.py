"""Namen ohne „Herr/Frau“ über den eigenen KI-Server (OpenAI-kompatible API mit Adresse + Token)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from datenwaechter import llm, ner, settings
from datenwaechter.detectors import scan_text
from datenwaechter.settings import LlmSettings

TOKEN = "firmen-token"
BRIEF = ("In der Familiensache betreffend das Sorgerecht für das Kind Wenzeslaus Brummer, geb. 02.05.2019. "
         "Rückfragen an 0171 2345678, IBAN DE89 3704 0044 0532 0130 00. Das Jugendamt ist informiert.")


@pytest.fixture
def api():
    """OpenAI-kompatibler Server, der wie ein Sprachmodell Namen aus dem gesendeten Text liefert."""
    state = {"chats": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            self._json({"data": [{"id": "pruef-modell"}]})

        def do_POST(self):
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                return self._json({"error": "token"}, 401)
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            prompt = body["messages"][-1]["content"]
            if "namen" in prompt:
                state["chats"].append(prompt)
                antwort = {"namen": ["Wenzeslaus Brummer", "Erika Nichtimtext", "[PERSON_1]"], "adressen": [],
                           "geburtsdaten": ["02.05.2019"]}
            else:
                antwort = {"beschreibung": "Brief", "familie": True}
            self._json({"choices": [{"message": {"content": json.dumps(antwort)}}]})

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{srv.server_port}/v1"
    yield state
    srv.shutdown()


def _api(url, **kw):
    settings.save_llm(LlmSettings(typ="openai", url=url, token=TOKEN, modell="pruef-modell", **kw))
    llm._cache.clear()


def test_seltener_name_nur_mit_ki():
    """Häufige Namen findet die Vornamenliste; seltene („Wenzeslaus“) nur die KI."""
    assert not any(f.text == "Wenzeslaus Brummer" for f in scan_text(BRIEF))
    assert any(f.text == "Mia Schneider" for f in scan_text(BRIEF.replace("Wenzeslaus Brummer", "Mia Schneider")))


def test_namen_ueber_eigene_api(api):
    _api(api["url"])
    assert ner.available() and ner.source() == "pruef-modell@127.0.0.1"
    found = {(f.kind, f.text) for f in scan_text(BRIEF, use_ki=True)}
    assert ("PERSON", "Wenzeslaus Brummer") in found
    assert ("GEBURTSDATUM", "02.05.2019") in found
    assert not any("Nichtimtext" in t or t.startswith("[") for _, t in found), "nur was wirklich im Text steht"


def test_vor_dem_senden_anonymisiert(api):
    _api(api["url"], anonymisieren=True)
    scan_text(BRIEF, use_ki=True)
    gesendet = api["chats"][0]
    assert "DE89" not in gesendet and "0171" not in gesendet, "bekannte Angaben gehen nur als Platzhalter raus"
    assert "[IBAN_1]" in gesendet and "Wenzeslaus Brummer" in gesendet


def test_auch_externe_api_wenn_eingeschaltet(monkeypatch):
    """Die Namenssuche läuft auch über externe Server – der Nutzer schaltet sie im KI-Dialog bewusst ein."""
    monkeypatch.setattr(llm.OpenAICompatible, "available", lambda self: True)
    calls = []
    monkeypatch.setattr(llm.OpenAICompatible, "complete",
                        lambda self, messages, temperature=0.3: calls.append(messages) or '{"namen": ["Wenzeslaus Brummer"]}')
    _api("https://api.openai.com/v1")
    assert llm.backend().extern
    assert ("PERSON", "Wenzeslaus Brummer") in {(f.kind, f.text) for f in scan_text(BRIEF, use_ki=True)}
    assert "DE89" not in calls[0][-1]["content"], "externer Server: vorher anonymisiert (Standard)"


def test_kein_ollama_mehr_im_automatik_modus(monkeypatch):
    """„Automatisch“ sucht nicht heimlich nach Ollama – es zählt nur die eingetragene API."""
    settings.save_llm(LlmSettings(typ="auto"))
    monkeypatch.setattr(llm.Ollama, "available", lambda self: True)
    llm._cache.clear()
    assert llm.backend() is None
