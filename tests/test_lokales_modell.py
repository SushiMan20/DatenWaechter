"""Lokales KI-Modell (Ollama) einrichten und Namen per KI finden."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from datenwaechter import llm, ner, settings
from datenwaechter.detectors import scan_text
from datenwaechter.settings import LlmSettings

BRIEF = ("In der Familiensache betreffend das Sorgerecht für das Kind Mia Schneider, geb. 02.05.2019. "
         "Die Mutter wohnt Lindenweg 7 in München. Das Jugendamt Musterstadt ist informiert.")


@pytest.fixture
def ollama(monkeypatch):
    state = {"models": ["gemma3:4b"], "pulled": [], "chat": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj):
            b = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            self._json({"models": [{"name": m} for m in state["models"]]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/api/pull":
                self.send_response(200)
                self.end_headers()
                for done in (0, 500, 1000):
                    self.wfile.write((json.dumps({"status": "pulling", "total": 1000, "completed": done}) + "\n").encode())
                self.wfile.write(b'{"status": "success"}\n')
                state["pulled"].append(body["model"])
                state["models"].append(body["model"])
                return
            if self.path == "/api/chat":
                state["chat"].append(body)
                antwort = {"namen": ["Mia Schneider", "Erika Nichtimtext"], "adressen": ["Lindenweg 7 in München"],
                           "geburtsdaten": ["02.05.2019"]}
                return self._json({"message": {"role": "assistant", "content": json.dumps(antwort)}})
            self._json({"response": json.dumps({"beschreibung": "Brief", "familie": True})})

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(llm, "OLLAMA_URL", f"http://127.0.0.1:{srv.server_port}")
    llm._cache.clear()
    yield state
    srv.shutdown()


def test_status_und_download_mit_fortschritt(ollama):
    st = llm.ollama_status()
    assert st["laeuft"] and st["modelle"] == ["gemma3:4b"]
    schritte = []
    llm.ollama_pull("gemma3:1b", lambda text, frac: schritte.append(frac))
    assert ollama["pulled"] == ["gemma3:1b"]
    assert [f for f in schritte if f is not None] == [0.0, 0.5, 1.0]
    assert "gemma3:1b" in llm.ollama_status()["modelle"]


def test_ohne_ollama():
    assert llm.ollama_status() == {"laeuft": False, "modelle": []}


def test_gewaehltes_modell_wird_benutzt(ollama):
    settings.save_llm(LlmSettings(typ="ollama", ollama_modell="gemma3:1b"))
    ollama["models"].append("gemma3:1b")
    llm._cache.clear()
    assert llm.backend().label == "ollama:gemma3:1b"


def test_namen_ohne_anrede_per_ki(ollama):
    assert scan_text(BRIEF) and not any(f.text == "Mia Schneider" for f in scan_text(BRIEF)), \
        "ohne KI wird der Kindername nicht gefunden"
    assert ner.available() and ner.source() == "gemma3:4b"
    found = {(f.kind, f.text) for f in scan_text(BRIEF, use_ki=True)}
    assert ("PERSON", "Mia Schneider") in found
    assert ("GEBURTSDATUM", "02.05.2019") in found
    assert not any("Nichtimtext" in t for _, t in found), "nur was wirklich im Text steht"
    assert "Mia Schneider" in ollama["chat"][0]["messages"][-1]["content"]


def test_externer_server_bekommt_keine_personendaten(monkeypatch):
    settings.save_llm(LlmSettings(typ="openai", url="https://api.openai.com/v1", modell="gpt-x"))
    monkeypatch.setattr(llm.OpenAICompatible, "available", lambda self: True)
    llm._cache.clear()
    assert llm.backend().extern
    assert not ner.available(), "externe Server werden für die Namenssuche nicht benutzt"
    with pytest.raises(llm.LlmError, match="Externer Server"):
        llm.find_personal_data(BRIEF)
