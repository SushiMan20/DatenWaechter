"""Eigener OpenAI-kompatibler KI-Server (URL + Token) für den Inhalts-Check."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from datenwaechter import content_check, llm, settings
from datenwaechter.settings import LlmSettings

TOKEN = "geheimes-token-123"
ANTWORT = {"beschreibung": "Brief ans Jugendamt", "familie": True, "kinder": False, "personen": True}
WARNUNG = "Du lädst gerade Familienunterlagen hoch."


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
    assert v.warning == WARNUNG and v.description == "Brief ans Jugendamt."
    assert "Fotos von Personen" not in v.categories, "„Menschen zu sehen“ zählt nur bei Bildern"
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
    assert v.warning == WARNUNG
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
    assert reply["content"]["warning"] == WARNUNG


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


def test_aelteres_antwortformat_und_kleine_modelle(server, monkeypatch):
    """Kleine Modelle liefern mal eine Kategorienliste, mal „intimes“ statt „intim“, mal "true" als Text."""
    from datenwaechter.content_check import _llm_keys
    assert _llm_keys({"kategorien": ["intimes", "Ausweis", "unkritisch"]}, has_image=True) == ["intim", "ausweis"]
    assert _llm_keys({"ausweis": "true", "gesundheit": "false", "personen": True}, has_image=False) == ["ausweis"]
    assert _llm_keys({"beschreibung": "eine Katze", "personen": False}, has_image=True) == []


def test_gateway_liste_chat_modell_zuerst(monkeypatch):
    """LiteLLM & Co. listen auch Sprach-, Embedding- und OCR-Modelle; ohne Einstellung wird ein Chat-Modell gewählt."""
    liste = ["stt", "tts", "tts-eu", "anthropic/*", "embed-modell", "ocr-modell", "text-embedding-3-small",
             "whisper-1", "chat-modell", "qwen3-chat"]
    monkeypatch.setattr(llm, "_request", lambda url, *a, **kw: {"data": [{"id": m} for m in liste]})
    b = llm.OpenAICompatible(LlmSettings(typ="openai", url="https://ai.example.org/v1", token="t"))
    assert b.available() and b.model == "chat-modell"
    assert b.models()[:2] == ["chat-modell", "qwen3-chat"] and set(b.models()) == set(liste)


def test_vorlagen_ohne_eigenen_dienst():
    from datenwaechter.settings import URL_VORLAGEN, VORLAGE_DETAILS
    assert URL_VORLAGEN[0] == ("OpenAI", "https://api.openai.com/v1")
    assert not VORLAGE_DETAILS, "keine fest eingebauten Dienste – Adresse und Token trägt jeder selbst ein"


DIENST = "https://ki.example.org/v1"


def test_eigener_dienst_braucht_schluessel_und_denkt_nicht(monkeypatch):
    monkeypatch.setitem(settings.VORLAGE_DETAILS, DIENST, {
        "name": "Mein Dienst", "modell": "qwen3-chat",
        "extra": {"chat_template_kwargs": {"enable_thinking": False}}, "schluessel": True})
    gesendet = []

    def antwort(url, body=None, token="", timeout=0):
        if url.endswith("/models"):
            return {"data": [{"id": m} for m in ("stt", "chat-modell", "qwen3-chat", "anthropic/claude-x")]}
        gesendet.append((body, token))
        return {"choices": [{"message": {"content": '<think>hmm</think>\n\n{"beschreibung": "Einkaufsliste"}'}}]}
    monkeypatch.setattr(llm, "_request", antwort)

    ohne = LlmSettings(typ="openai", url=DIENST + "/")
    assert not llm.OpenAICompatible(ohne).available()
    ok, meldung = llm.test_connection(ohne)
    assert not ok and "Schlüssel" in meldung and not gesendet, "ohne Schlüssel geht nichts raus"

    mit = LlmSettings(typ="openai", url=DIENST, token="sk-kunde")
    b = llm.OpenAICompatible(mit)
    assert b.available() and b.model == "qwen3-chat", "Standardmodell der Vorlage"
    ok, meldung = llm.test_connection(mit)
    assert ok, meldung
    body, token = gesendet[-1]
    assert token == "sk-kunde" and body["chat_template_kwargs"] == {"enable_thinking": False}
    assert b.complete([{"role": "user", "content": "x"}]) == '{"beschreibung": "Einkaufsliste"}', "Nachdenken entfernt"

    anderes = llm.OpenAICompatible(LlmSettings(typ="openai", url=DIENST, token="t",
                                               modell="anthropic/claude-x"))
    anderes.complete([{"role": "user", "content": "x"}])
    assert "chat_template_kwargs" not in gesendet[-1][0], "Zusatzangaben nur für das Modell der Vorlage"


def test_inhalts_check_schalter_bleibt_gespeichert():
    assert settings.inhalts_check_ki(), "Standard: an"
    settings.inhalts_check_ki_speichern(False)
    assert not settings.inhalts_check_ki()


def test_ki_server_aus_und_wieder_an_behaelt_adresse():
    settings.save_llm(LlmSettings(typ="openai", url="https://api.openai.com/v1", token="sk-test", modell="gpt-x"))
    settings.ki_server_schalten(False)
    s = settings.load_llm()
    assert s.typ == "aus" and s.url == "https://api.openai.com/v1" and s.modell == "gpt-x"
    assert llm.backend(fresh=True) is None, "ausgeschaltet: keine Anfrage an den Server"
    settings.ki_server_schalten(True)
    s = settings.load_llm()
    assert s.typ == "openai" and s.token == "sk-test"


@pytest.mark.parametrize("eingabe, sauber, extern", [
    (r"https:\\ki.example.org\v1", "https://ki.example.org/v1", True),     # Backslashes wie im Explorer
    ("ki.example.org/v1/", "https://ki.example.org/v1", True),             # ohne https://
    ("HTTPS:/ki.example.org/v1/chat/completions", "https://ki.example.org/v1", True),
    ("localhost:1234/v1", "http://localhost:1234/v1", False),
    ("192.168.1.20:8000/v1", "http://192.168.1.20:8000/v1", False),
    ("ki-server:8000/v1", "http://ki-server:8000/v1", False),               # Rechnername ohne Punkt = eigenes Netz
])
def test_adresse_wird_aufgeraeumt(eingabe, sauber, extern):
    s = LlmSettings(typ="openai", url=eingabe)
    assert s.base_url == sauber and s.extern is extern
    assert s.anonymize_first is extern and s.send_images is not extern, "externe Server: anonymisieren, keine Fotos"


def test_alte_adresse_mit_backslashes_bekommt_sichere_vorgaben():
    """Mit „https:\\server\\v1“ galt der Server früher als lokal: Fotos an, Anonymisieren aus – das wird zurückgesetzt."""
    p = settings.path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"llm": {"typ": "openai", "url": "https:\\\\ki.example.org\\v1",
                                     "anonymisieren": False, "bilder_senden": True}}), encoding="utf-8")
    s = settings.load_llm()
    assert s.url == "https://ki.example.org/v1" and s.anonymize_first and not s.send_images


def test_ungueltige_adresse_klare_meldung():
    ok, meldung = llm.test_connection(LlmSettings(typ="openai", url="https://", token="t"))
    assert not ok and "ungültig" in meldung


def test_https_zertifikate_wie_im_browser():
    import ssl
    from datenwaechter import netz
    assert isinstance(netz.ssl_kontext(), ssl.SSLContext)


@pytest.mark.skipif(not os.environ.get("DATENWAECHTER_NETZTEST"), reason="nur mit Internet (DATENWAECHTER_NETZTEST=1)")
def test_https_echt():
    from datenwaechter import netz
    with netz.oeffnen("https://huggingface.co/api/models/Xenova/bert-base-multilingual-cased-ner-hrl", 30) as r:
        assert r.status == 200


# --------------------------------------------------------------------------- Nachdenken (Reasoning)

def _denk_server(monkeypatch):
    """Drei nachgebaute Modelle: „denker“ (denkt immer, Schalter nur über chat_template_kwargs; reasoning_effort wird
    angenommen, aber ignoriert), „still“ (denkt nur mit reasoning_effort), „gpt“ (denkt nie, kennt reasoning_effort nicht)."""
    gesendet = []

    def antwort(url, body=None, token="", timeout=0):
        if url.endswith("/models"):
            return {"data": [{"id": "denker"}, {"id": "still"}, {"id": "gpt"}]}
        gesendet.append(body)
        m = body["model"]
        if m == "gpt" and "reasoning_effort" in body:
            raise llm.LlmError("HTTP 400: Unsupported parameter: reasoning_effort")
        if "thinking" in body and m != "still":
            raise llm.LlmError("HTTP 400: unknown field thinking")
        if m == "denker":
            denkt = (body.get("chat_template_kwargs") or {}).get("enable_thinking", True)
        elif m == "still":
            denkt = body.get("reasoning_effort") in ("low", "medium", "high")
        else:
            denkt = False
        msg = {"content": "42"}
        if denkt:
            msg["reasoning_content"] = "17 + 25 …"
        return {"choices": [{"message": msg}], "usage": {"completion_tokens_details": {"reasoning_tokens": 9 if denkt else 0}}}
    monkeypatch.setattr(llm, "_request", antwort)
    return gesendet


@pytest.mark.parametrize("modell, standard, aus, an", [
    ("denker", True, "chat_template_kwargs", ""),    # angenommen-aber-ignoriert (reasoning_effort) zählt nicht
    ("still", False, "", "reasoning_effort"),
    ("gpt", False, "", "-"),                          # denkt nie: Einschalten nicht möglich
])
def test_nachdenken_pruefen_findet_wirksamen_schalter(monkeypatch, modell, standard, aus, an):
    _denk_server(monkeypatch)
    e = llm.denken_pruefen(LlmSettings(typ="openai", url="http://ki.firma.example/v1", token="t", modell=modell))
    assert (e["standard"], e["aus"], e["an"]) == (standard, aus, an)
    assert e["geprueft"] == f"http://ki.firma.example/v1|{modell}"
    assert llm.denken_beschreiben(e)


def test_nachdenken_wird_bei_anfragen_angewendet(monkeypatch):
    from datenwaechter import actions
    gesendet = _denk_server(monkeypatch)
    s = LlmSettings(typ="openai", url="http://ki.firma.example/v1", token="t", modell="denker", denken="aus",
                    denken_aus="chat_template_kwargs", denken_an="", denken_geprueft="http://ki.firma.example/v1|denker")
    b = llm.OpenAICompatible(s)
    b.complete([{"role": "user", "content": "x"}])
    assert gesendet[-1]["chat_template_kwargs"] == {"enable_thinking": False}, "Einstellung „aus“"
    b.complete([{"role": "user", "content": "x"}], denken="an")
    assert "chat_template_kwargs" not in gesendet[-1], "„an“ braucht hier keinen Zusatz"
    anderes = llm.OpenAICompatible(LlmSettings(**{**s.__dict__, "modell": "gpt"}))
    anderes.complete([{"role": "user", "content": "x"}])
    assert "chat_template_kwargs" not in gesendet[-1], "nur für das geprüfte Modell"

    # Aktion mit eigener Einstellung („Zusammenfassen“ gründlich, Rest schnell)
    monkeypatch.setattr(llm, "backend", lambda *a, **k: b)
    actions.run(actions.Aktion("Zusammenfassen", "Fasse zusammen", "anzeigen", "an"), "Ein Text.")
    assert "chat_template_kwargs" not in gesendet[-1]
    actions.run(actions.Aktion("Umformulieren", "Formuliere um"), "Ein Text.")
    assert gesendet[-1]["chat_template_kwargs"] == {"enable_thinking": False}


def test_aktion_merkt_sich_nachdenken():
    from datenwaechter import actions
    actions.save([actions.Aktion("Zusammenfassen", "Fasse zusammen", "anzeigen", "an"), actions.Aktion("Kürzen", "Kürze")])
    geladen = actions.load()
    assert [a.denken for a in geladen] == ["an", ""]
