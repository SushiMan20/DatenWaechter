"""Eigener OpenAI-kompatibler KI-Server (URL + Token) für den Inhalts-Check."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from datenwaechter import content_check, llm, settings
from datenwaechter.settings import LlmSettings

TOKEN = "geheimes-token-123"
ANTWORT = {"kategorien": ["familie"], "beschreibung": "Brief ans Jugendamt.",
           "warnung": "Du lädst gerade einen Brief über das Sorgerecht deiner Tochter hoch.", "stufe": 2}


@pytest.fixture
def server():
    """Simulierter OpenAI-kompatibler Server (wie LM Studio, vLLM, Firmen-Gateway …)."""
    state = {"requests": [], "reject_json_mode": False, "models": ["lokal-7b", "lokal-vision"], "fence": False}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                self._send(401, {"error": {"message": "invalid api key"}})
                return False
            return True

        def do_GET(self):
            if self.path == "/v1/models" and self._authorized():
                self._send(200, {"data": [{"id": m} for m in state["models"]]})
            elif self.path != "/v1/models":
                self._send(404, {})

        def do_POST(self):
            if self.path != "/v1/chat/completions" or not self._authorized():
                return self._send(404, {}) if self.path != "/v1/chat/completions" else None
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append(body)
            if state["reject_json_mode"] and "response_format" in body:
                return self._send(400, {"error": {"message": "response_format not supported"}})
            content = json.dumps(ANTWORT, ensure_ascii=False)
            if state["fence"]:
                content = "Hier ist das Ergebnis:\n```json\n" + content + "\n```"
            self._send(200, {"choices": [{"message": {"role": "assistant", "content": content}}]})

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{srv.server_port}/v1"
    yield state
    srv.shutdown()


def _save(**kw):
    settings.save_llm(LlmSettings(**kw))
    llm._cache.clear()


TEXT = "Bitte an Frau Müller, IBAN DE89 3704 0044 0532 0130 00 – es geht um das Sorgerecht für unsere Tochter."


def test_eigener_server_mit_token(server):
    _save(typ="openai", url=server["url"], token=TOKEN, modell="lokal-7b")
    v = content_check.check(TEXT)
    assert v.backend == "openai:lokal-7b@127.0.0.1"
    assert v.warning == ANTWORT["warnung"] and v.description == "Brief ans Jugendamt."
    req = server["requests"][0]
    assert req["model"] == "lokal-7b" and req["response_format"] == {"type": "json_object"}
    assert "DE89" in json.dumps(req, ensure_ascii=False), "lokaler Server: Text geht unverändert"
    assert v.sent_to is None and "KI-Server" in v.source_text()


def test_vor_dem_senden_anonymisieren(server):
    _save(typ="openai", url=server["url"], token=TOKEN, modell="lokal-7b", anonymisieren=True)
    content_check.check(TEXT)
    sent = json.dumps(server["requests"][0], ensure_ascii=False)
    assert "DE89" not in sent and "Müller" not in sent
    assert "[IBAN_1]" in sent and "Sorgerecht" in sent, "Thema bleibt erkennbar, Personendaten nicht"


def test_bilder_nur_wenn_erlaubt(server):
    from PIL import Image
    img = Image.new("RGB", (32, 32), "white")
    _save(typ="openai", url=server["url"], token=TOKEN, modell="lokal-vision", bilder_senden=True)
    content_check.check("", image=img)
    parts = server["requests"][-1]["messages"][1]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    _save(typ="openai", url=server["url"], token=TOKEN, modell="lokal-vision", bilder_senden=False)
    content_check.check("", image=img)
    assert isinstance(server["requests"][-1]["messages"][1]["content"], str)


def test_server_ohne_json_modus_und_mit_codeblock(server):
    server["reject_json_mode"] = True
    server["fence"] = True
    _save(typ="openai", url=server["url"], token=TOKEN, modell="lokal-7b")
    v = content_check.check(TEXT)
    assert v.warning == ANTWORT["warnung"]
    assert "response_format" not in server["requests"][-1]


def test_modell_automatisch_vom_server(server):
    _save(typ="openai", url=server["url"] + "/chat/completions", token=TOKEN)  # volle URL wird gekürzt
    assert content_check.llm_status() == "openai:lokal-7b@127.0.0.1"


def test_falsches_token(server):
    ok, msg = llm.test_connection(LlmSettings(typ="openai", url=server["url"], token="falsch", modell="lokal-7b"))
    assert not ok and "Token" in msg
    _save(typ="openai", url=server["url"], token="falsch", modell="lokal-7b")
    assert content_check.check(TEXT).backend == "stichworte", "ohne Zugang: zurück auf Stichwörter"


def test_verbindung_testen(server):
    ok, msg = llm.test_connection(LlmSettings(typ="openai", url=server["url"], token=TOKEN, modell="lokal-7b"))
    assert ok and "lokal-7b" in msg
    ok, msg = llm.test_connection(LlmSettings(typ="openai", url=server["url"], token=TOKEN, modell="gibtsnicht"))
    assert not ok and "lokal-vision" in msg


def test_umgebungsvariablen(server, monkeypatch):
    monkeypatch.setenv("DATENWAECHTER_LLM_URL", server["url"])
    monkeypatch.setenv("DATENWAECHTER_LLM_TOKEN", TOKEN)
    monkeypatch.setenv("DATENWAECHTER_LLM_MODELL", "lokal-7b")
    assert content_check.llm_status() == "openai:lokal-7b@127.0.0.1"


def test_browser_bruecke_meldet_server(server):
    from datenwaechter.native_host import handle
    _save(typ="openai", url=server["url"], token=TOKEN, modell="lokal-7b")
    assert handle({"action": "ping"})["llm"] == "openai:lokal-7b@127.0.0.1"
    reply = handle({"action": "check_text", "text": TEXT})
    assert reply["content"]["warning"] == ANTWORT["warnung"]


@pytest.mark.parametrize("url,extern", [
    ("http://localhost:1234/v1", False), ("http://127.0.0.1:8000/v1", False), ("http://192.168.1.20:8000/v1", False),
    ("http://ki-server/v1", False), ("https://llm.firma.internal/v1", False),
    ("https://api.openai.com/v1", True), ("https://openrouter.ai/api/v1", True),
])
def test_extern_erkennung(url, extern):
    s = LlmSettings(url=url)
    assert s.extern is extern
    assert s.anonymize_first is extern and s.send_images is (not extern)


def test_einstellungen_speichern_und_laden():
    p = settings.save_llm(LlmSettings(typ="openai", url="https://gw.firma.de/v1", token="t0k3n-abcdef", modell="m"))
    loaded = settings.load_llm()
    assert loaded.url == "https://gw.firma.de/v1" and loaded.token == "t0k3n-abcdef" and loaded.modell == "m"
    assert json.loads(p.read_text())["llm"]["typ"] == "openai"
    assert settings.masked_token("t0k3n-abcdef") == "t0k…cdef"
