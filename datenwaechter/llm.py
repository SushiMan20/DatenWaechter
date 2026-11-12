"""KI-Server für den Inhalts-Check: Ollama (lokal) oder ein beliebiger OpenAI-kompatibler Server mit URL + Token
(LM Studio, vLLM, LocalAI, Firmen-Gateway, OpenRouter, OpenAI …).

Liegt der Server außerhalb des eigenen Netzes, wird der Text vorher anonymisiert und standardmäßig kein Bild
mitgeschickt – für die Frage „Was ist das für ein Inhalt?“ braucht die KI keine echten Namen oder Kontonummern.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .netz import oeffnen
from .settings import LlmSettings, load_llm

OLLAMA_URL = os.environ.get("DATENWAECHTER_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("DATENWAECHTER_OLLAMA_MODELL", "gemma3:4b")
MAX_CHARS = 6000
TIMEOUT = 120          # Sekunden ohne jedes Lebenszeichen vom Server (beim Streaming: Pause zwischen zwei Stücken)

KATEGORIEN = {
    "familie": "Familienunterlagen", "kinder": "Daten über Kinder", "gesundheit": "Gesundheitsdaten",
    "finanzen": "Finanzunterlagen", "recht": "rechtliche Unterlagen", "arbeit": "Personal- und Arbeitsunterlagen",
    "ausweis": "Ausweisdokumente", "vertraulich": "vertrauliche Firmeninterna", "zugangsdaten": "Zugangsdaten",
    "intim": "intime oder private Inhalte", "besonders": "besonders geschützte Daten (Religion, Politik, Sexualität)",
    "personenfoto": "Fotos von Personen", "personen": "Fotos von Personen",
}
STUFE = {"kinder": 3, "ausweis": 3, "gesundheit": 3, "intim": 3, "zugangsdaten": 3, "besonders": 3}  # sonst 2

# Ja/Nein-Fragen statt „wähle Kategorien“: Das beantworten auch kleine lokale Modelle zuverlässig.
# Den Warnsatz baut der Datenwächter danach selbst (content_check.llm_check).
FRAGEN = {
    "personen": "Sind auf einem Bild Menschen zu sehen (Foto, Selfie, Gruppenbild)?",
    "kinder": "Sind Kinder zu sehen oder geht es um ein bestimmtes Kind?",
    "ausweis": "Ist es ein Ausweis, Pass, Führerschein, eine Bank-, Kredit- oder Versichertenkarte?",
    "gesundheit": "Geht es um Krankheit, Diagnose, Therapie, Medikamente, Arztbrief oder ein medizinisches Bild?",
    "finanzen": "Geht es um Kontoauszug, Gehalt, Steuer, Rechnung mit Bankdaten oder Schulden?",
    "familie": "Geht es um Familienangelegenheiten wie Scheidung, Sorgerecht, Unterhalt oder Erbschaft?",
    "recht": "Geht es um Gericht, Anwalt, Polizei, Strafsache oder einen Rechtsstreit?",
    "arbeit": "Geht es um Personalakte, Kündigung, Abmahnung, Arbeitszeugnis oder Bewerbung?",
    "vertraulich": "Ist es als vertraulich/intern markiert oder enthält es Firmengeheimnisse?",
    "intim": "Enthält es Nacktheit, Sexualität oder sehr intime private Momente?",
    "zugangsdaten": "Enthält es Passwörter, PINs, API-Schlüssel oder andere Zugangsdaten?",
    "besonders": "Geht es um Religion, politische Meinung, Gewerkschaft oder sexuelle Orientierung einer Person?",
}

PROMPT = """Du bist ein Datenschutz-Assistent. Ein Nutzer will den folgenden Inhalt gleich in einen Cloud-KI-Chat
hochladen. Platzhalter wie [PERSON_1] oder [IBAN_1] stehen für bereits entfernte echte Daten.

Beschreibe zuerst in einem kurzen deutschen Satz, was zu sehen bzw. zu lesen ist. Beantworte dann jede Frage
nur mit true oder false. Antworte im Zweifel mit false.
{fragen}

Antworte NUR mit JSON in genau diesem Format:
{{"beschreibung": "…", {felder}}}

Dateiname: {name}
Inhalt:
<<<
{text}
>>>"""


class LlmError(Exception):
    pass


# --------------------------------------------------------------------------- Nachdenken (Reasoning)

DENKEN = {"auto": "wie der Server es macht", "aus": "aus – schneller", "an": "an – gründlicher"}

# Jeder Anbieter schaltet das Nachdenken anders: (Name, Angaben für „aus“, Angaben für „an“)
DENK_VARIANTEN = [
    ("reasoning_effort", {"reasoning_effort": "none"}, {"reasoning_effort": "medium"}),        # OpenAI, LiteLLM
    ("reasoning_effort_minimal", {"reasoning_effort": "minimal"}, None),                     # ältere OpenAI-Modelle
    ("chat_template_kwargs", {"chat_template_kwargs": {"enable_thinking": False}},           # Qwen, DeepSeek … (vLLM)
     {"chat_template_kwargs": {"enable_thinking": True}}),
    ("enable_thinking", {"enable_thinking": False}, {"enable_thinking": True}),               # Alibaba DashScope
    ("thinking", {"thinking": {"type": "disabled"}}, {"thinking": {"type": "enabled", "budget_tokens": 2048}}),
]


def denk_angaben(variante: str, modus: str) -> dict:
    """Zusatzangaben für eine Anfrage – {} bei „auto“, unbekannter oder nicht nötiger Variante."""
    for name, aus, an in DENK_VARIANTEN:
        if name == variante:
            return dict((aus if modus == "aus" else an) or {})
    return {}


def _denkt(data: dict) -> bool:
    """Hat das Modell nachgedacht? (eigenes Feld, Token-Zählung oder <think> im Text)"""
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return False
    if msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking_blocks") or msg.get("thinking"):
        return True
    det = (data.get("usage") or {}).get("completion_tokens_details") or {}
    return (det.get("reasoning_tokens") or 0) > 0 or "<think>" in (msg.get("content") or "")


# Gateways wie LiteLLM listen auch Sprach-, Vorlese-, Embedding- und OCR-Modelle – die können keinen Chat
_KEIN_CHAT = re.compile(r"(?i)(?:^|[/_.:-])(?:stt|tts|whisper|embed\w*|embedding\w*|ocr|rerank\w*|moderation|dall-e"
                        r"|image|transcri\w*|speech|audio|realtime|instruct|davinci|babbage)(?:$|[/_.:-])|\*")


def chat_zuerst(models: list[str]) -> list[str]:
    """Modellliste mit Chat-Modellen vorn – das erste ist der sinnvolle Standard, wenn keins eingestellt ist."""
    return [m for m in models if not _KEIN_CHAT.search(m)] + [m for m in models if _KEIN_CHAT.search(m)]


@dataclass
class Answer:
    data: dict
    backend: str          # Anzeige, z. B. "ollama:gemma3:4b" oder "openai:gpt-4o-mini@api.openai.com"
    sent_to: str | None   # Hostname, falls die Daten den eigenen Rechner/das Netz verlassen haben
    anonymized: bool


# --------------------------------------------------------------------------- HTTP-Helfer

def _request(url: str, body: dict | None = None, token: str = "", timeout: float = TIMEOUT) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data else "GET")
    try:
        with oeffnen(req, timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise LlmError(f"HTTP {e.code}: {detail}") from e
    except (OSError, ValueError) as e:
        raise LlmError(str(e)) from e


def _inhalt(data: dict) -> str:
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise LlmError("Unerwartetes Antwortformat") from e
    return text if isinstance(text, str) else ""


def _stream(url: str, body: dict, token: str = "", timeout: float | None = None, fortschritt=None) -> str:
    """Chat-Antwort als Datenstrom: Der Server schickt laufend Stücke, statt erst am Ende alles auf einmal.

    So bleibt die Verbindung aktiv – Proxys wie Cloudflare brechen nach etwa 100 Sekunden ohne Antwort ab, und
    Nachdenken oder lange Texte dauern oft länger. timeout gilt für die Pause zwischen zwei Stücken, nicht für
    die ganze Antwort. Versteht der Server OpenAI-Streaming (Server-Sent Events) oder Ollama-Streaming (eine
    JSON-Zeile je Stück); schickt er trotzdem eine normale Antwort, wird die genommen.
    fortschritt(text_bisher, denkt): bei jedem Stück; denkt=True, solange nur „Nachdenken“ kommt.
    Gibt den Antworttext zurück (noch mit <think>…</think>, falls das Modell so nachdenkt).
    """
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream, application/x-ndjson, application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps({**body, "stream": True}).encode(), headers=headers, method="POST")
    text = ""
    try:
        with oeffnen(req, timeout or TIMEOUT) as r:
            art = (r.headers.get("Content-Type") or "").lower()
            if "event-stream" not in art and "ndjson" not in art:
                data = json.load(r)                    # Server streamt nicht: normale Antwort
                if "message" in data:                  # Ollama
                    return (data.get("message") or {}).get("content") or ""
                return _inhalt(data)
            for zeile in r:
                zeile = zeile.decode("utf-8", "replace").strip()
                if "event-stream" in art:
                    if not zeile.startswith("data:"):
                        continue                       # Kommentare („: ping“), event:, id:
                    zeile = zeile[5:].strip()
                    if zeile == "[DONE]":
                        break
                if not zeile:
                    continue
                try:
                    stueck = json.loads(zeile)
                except ValueError:
                    continue
                if stueck.get("error"):
                    fehler = stueck["error"]
                    raise LlmError(fehler.get("message", str(fehler)) if isinstance(fehler, dict) else str(fehler))
                denkt = False
                for c in stueck.get("choices") or []:  # OpenAI-kompatibel
                    delta = c.get("delta") or c.get("message") or {}
                    if isinstance(delta.get("content"), str):
                        text += delta["content"]
                    denkt = denkt or bool(delta.get("reasoning_content") or delta.get("reasoning"))
                msg = stueck.get("message")            # Ollama
                if isinstance(msg, dict):
                    text += msg.get("content") or ""
                    denkt = denkt or bool(msg.get("thinking"))
                if fortschritt:
                    fortschritt(text, denkt and not text.strip())
                if stueck.get("done") is True:
                    break
        return text
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise LlmError(f"HTTP {e.code}: {detail}") from e
    except (OSError, ValueError) as e:
        raise LlmError(str(e)) from e


def _antwort(text: str | None) -> str:
    """Antworttext ohne „Nachdenken“ (<think>…</think>) und Leerzeilen davor/danach."""
    return re.sub(r"(?s)<think>.*?</think>", "", text or "").strip()


def _parse_json(text: str) -> dict:
    """Modelle packen JSON gern in ```-Blöcke oder schreiben einen Satz davor."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise LlmError("Antwort enthält kein JSON")
    try:
        return json.loads(m.group(0))
    except ValueError as e:
        raise LlmError(f"Antwort ist kein gültiges JSON: {e}") from e


def _jpeg_b64(image) -> str:
    buf = io.BytesIO()
    img = image.convert("RGB")
    img.thumbnail((1024, 1024))
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _prompt(text: str, name: str) -> str:
    return PROMPT.format(fragen="\n".join(f"- {k}: {q}" for k, q in FRAGEN.items()),
                         felder=", ".join(f'"{k}": false' for k in FRAGEN), name=name or "(eingefügter Text)",
                         text=(text or "(kein Text – siehe Bild)")[:MAX_CHARS])


# --------------------------------------------------------------------------- Ollama

class Ollama:
    def __init__(self, url: str | None = None, model: str | None = None):
        self.url, self.model = (url or OLLAMA_URL).rstrip("/"), model or OLLAMA_MODEL
        self.label = f"ollama:{self.model}"

    def available(self) -> bool:
        try:
            models = [m.get("name", "") for m in _request(f"{self.url}/api/tags", timeout=0.7).get("models", [])]
        except LlmError:
            return False
        return any(m == self.model or m.split(":")[0] == self.model for m in models)

    extern = False           # läuft auf diesem Rechner
    anonymize_first = False
    host = "localhost"

    def complete(self, messages: list[dict], temperature: float = 0.3, denken: str | None = None,
                 fortschritt=None) -> str:
        """Freier Text (für KI-Aktionen wie „Umformulieren“), gestreamt."""
        body = {"model": self.model, "messages": messages, "options": {"temperature": temperature}}
        if denken in ("aus", "an"):
            body["think"] = denken == "an"   # Ollama: eigener Schalter
        return _antwort(_stream(f"{self.url}/api/chat", body, fortschritt=fortschritt))

    def ask(self, text: str, image=None, name: str = "") -> Answer:
        body = {"model": self.model, "prompt": _prompt(text, name), "format": "json", "stream": False,
                "options": {"temperature": 0}}
        if image is not None:
            body["images"] = [_jpeg_b64(image)]
        return Answer(_parse_json(_request(f"{self.url}/api/generate", body).get("response", "")),
                      self.label, None, False)


# --------------------------------------------------------------------------- OpenAI-kompatibel

class OpenAICompatible:
    def __init__(self, s: LlmSettings):
        self.s = s
        self.model = s.modell or s.vorlage.get("modell", "")
        self.label = f"openai:{self.model or '?'}@{s.host}"

    def _body(self, body: dict, denken: str | None = None) -> dict:
        """Zusatzangaben: Vorlage (nur für deren Modell) und Nachdenken (geprüfte Variante dieses Servers)."""
        v = self.s.vorlage
        if v.get("extra") and self.model == v.get("modell"):
            body.update(v["extra"])
        modus = denken or self.s.denken
        if modus in ("aus", "an") and self.s.denken_geprueft == f"{self.s.base_url}|{self.model}":
            extra = denk_angaben(self.s.denken_an if modus == "an" else self.s.denken_aus, modus)
            body.update(extra)
            if "thinking" in extra and modus == "an":
                body["temperature"] = 1   # Claude: Nachdenken nur mit Temperatur 1
        return body

    def models(self) -> list[str]:
        if not self.s.host:
            raise LlmError("Die Adresse ist ungültig. Beispiel: https://ki.firma.de/v1")
        data = _request(f"{self.s.base_url}/models", token=self.s.token, timeout=3)
        return chat_zuerst([m.get("id", "") for m in data.get("data", []) if m.get("id")])

    def available(self) -> bool:
        if not self.s.base_url or (self.s.vorlage.get("schluessel") and not self.s.token):
            return False
        try:
            listed = self.models()
        except LlmError as e:
            # Manche Gateways haben kein /models – dann zählt die Konfiguration, solange ein Modell gesetzt ist
            return bool(self.model) and str(e).startswith(("HTTP 404", "HTTP 405"))
        if not self.model and listed:
            self.model = listed[0]
            self.label = f"openai:{self.model}@{self.s.host}"
        return bool(self.model)

    @property
    def extern(self) -> bool:
        return self.s.extern

    @property
    def anonymize_first(self) -> bool:
        return self.s.anonymize_first

    @property
    def host(self) -> str:
        return self.s.host

    def _chat(self, body: dict, fortschritt=None) -> str:
        """Eine Chat-Anfrage, gestreamt. Lehnt der Server Streaming ab, einmal ohne."""
        url = f"{self.s.base_url}/chat/completions"
        try:
            return _stream(url, body, self.s.token, fortschritt=fortschritt)
        except LlmError as e:
            if not (str(e).startswith(("HTTP 400", "HTTP 422")) and "stream" in str(e).lower()):
                raise
            return _inhalt(_request(url, body, self.s.token))

    def complete(self, messages: list[dict], temperature: float = 0.3, denken: str | None = None,
                 fortschritt=None) -> str:
        """Freier Text (für KI-Aktionen wie „Umformulieren“). denken: aus | an | None = Einstellung."""
        body = self._body({"model": self.model, "temperature": temperature, "messages": messages}, denken)
        return _antwort(self._chat(body, fortschritt))

    def ask(self, text: str, image=None, name: str = "") -> Answer:
        anonymized = False
        if self.s.anonymize_first and text:
            from .anonymize import Anonymizer
            text, anonymized = Anonymizer().anonymize(text), True
        content: list | str = _prompt(text, name)
        if image is not None and self.s.send_images:
            content = [{"type": "text", "text": content},
                       {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_jpeg_b64(image)}"}}]
        body = {"model": self.model, "temperature": 0,
                "messages": [{"role": "system", "content": "Du antwortest ausschließlich mit gültigem JSON."},
                             {"role": "user", "content": content}],
                "response_format": {"type": "json_object"}}
        self._body(body)
        try:
            reply = self._chat(body)
        except LlmError as e:
            if not str(e).startswith("HTTP 400"):
                raise
            body.pop("response_format")       # nicht jeder Server kennt den JSON-Modus …
            try:
                reply = self._chat(body)
            except LlmError as e2:
                if not (str(e2).startswith("HTTP 400") and isinstance(content, list)):
                    raise
                body["messages"][1]["content"] = content[0]["text"]   # … oder Bilder
                reply = self._chat(body)
        reply = _antwort(reply)
        return Answer(_parse_json(reply), self.label, self.s.host if self.s.extern else None, anonymized)


# --------------------------------------------------------------------------- Auswahl

_cache: dict = {}


def backend(settings: LlmSettings | None = None, fresh: bool = False):
    """Liefert den zu nutzenden KI-Server oder None. Ergebnis wird 60 s zwischengespeichert."""
    s = settings or load_llm()
    key = (s.typ, s.base_url, s.token, s.modell, s.ollama_modell)
    hit = _cache.get(key)
    if hit and not fresh and time.time() - hit[0] < 60:
        return hit[1]
    chosen = None
    if s.typ in ("openai", "auto") and s.base_url:
        b = OpenAICompatible(s)
        chosen = b if b.available() else None
    if chosen is None and s.typ == "ollama":   # nur auf ausdrücklichen Wunsch (ki-server --art ollama)
        b = Ollama(model=s.ollama_modell or None)
        chosen = b if b.available() else None
    _cache[key] = (time.time(), chosen)
    return chosen


# --------------------------------------------------------------------------- Personendaten per KI

NAMEN_PROMPT = """Finde in dem Text alle personenbezogenen Angaben, die eine bestimmte Person identifizieren:
Namen von Personen (auch ohne „Herr“/„Frau“, auch Kindernamen), Wohnadressen und Geburtsdaten.
Firmen, Behörden, Städte allein und Funktionen („Rechtsanwalt“, „Jugendamt“) gehören NICHT dazu.
Gib jede Angabe genau so zurück, wie sie im Text steht.

Antworte NUR mit JSON: {{"namen": ["…"], "adressen": ["…"], "geburtsdaten": ["…"]}}

Text:
<<<
{text}
>>>"""


def find_personal_data(text: str, backend_=None) -> dict:
    """Fragt den KI-Server nach Namen/Adressen/Geburtsdaten, die die Regeln nicht finden.

    Ist „vor dem Senden anonymisieren“ aktiv, werden bereits erkannte Angaben (IBAN, Telefon, Namen mit Anrede …)
    vorher durch Platzhalter ersetzt – der Server sieht dann nur noch, was er finden soll.
    """
    b = backend_ or backend()
    if b is None:
        raise LlmError("Kein KI-Server eingerichtet")
    if b.anonymize_first:
        from .anonymize import Anonymizer
        text = Anonymizer().anonymize(text)
    reply = b.complete([{"role": "system", "content": "Du antwortest ausschließlich mit gültigem JSON."},
                        {"role": "user", "content": NAMEN_PROMPT.format(text=text[:MAX_CHARS])}], temperature=0)
    return _parse_json(reply)


def denken_pruefen(s: LlmSettings) -> dict:
    """Findet heraus, wie dieser Server das Nachdenken an- und ausschaltet – und ob es überhaupt wirkt.

    Ein Schalter zählt nur, wenn er die Antwort wirklich ändert: Manche Server nehmen Angaben an und ignorieren sie.
    Ergebnis: {"standard": denkt ohne Angaben?, "aus": Variante, "an": Variante, "geprueft": "adresse|modell"};
    Variante "" = ohne Zusatz, "-" = nicht möglich. Kostet ein paar sehr kurze Anfragen.
    """
    b = OpenAICompatible(s)
    if not b.model:
        listed = b.models()
        b.model = listed[0] if listed else ""
    if not b.model:
        raise LlmError("Bitte ein Modell angeben.")
    frage = [{"role": "user", "content": "Wie viel ist 17 + 25? Antworte nur mit der Zahl."}]

    def probe(extra: dict) -> dict | None:
        body = {"model": b.model, "messages": frage, **extra}
        if "thinking" in extra and extra["thinking"].get("type") == "enabled":
            body["temperature"] = 1
        try:
            return _request(f"{s.base_url}/chat/completions", body, s.token, timeout=60)
        except LlmError as e:
            if str(e).startswith(("HTTP 400", "HTTP 422")):   # Angabe unbekannt: nächste Variante
                return None
            raise

    basis = probe({})
    if basis is None:
        raise LlmError("Der Server beantwortet keine einfache Anfrage.")
    ergebnis = {"standard": _denkt(basis), "geprueft": f"{s.base_url}|{b.model}"}
    for modus in ("aus", "an"):
        if ergebnis["standard"] == (modus == "an"):
            ergebnis[modus] = ""            # tut es ohnehin
            continue
        ergebnis[modus] = "-"
        for name, aus, an in DENK_VARIANTEN:
            extra = aus if modus == "aus" else an
            if extra is None:
                continue
            antwort = probe(extra)
            if antwort is not None and _denkt(antwort) == (modus == "an"):
                ergebnis[modus] = name
                break
    return ergebnis


def denken_beschreiben(e: dict) -> str:
    """Für die Anzeige: „Modell denkt von sich aus nach · Aus: über chat_template_kwargs · An: ohne Zusatz“."""
    teile = ["Das Modell denkt von sich aus nach." if e.get("standard") else "Das Modell denkt von sich aus nicht nach."]
    for modus in ("aus", "an"):
        v = e.get(modus, "-")
        teile.append(f"{'Ausschalten' if modus == 'aus' else 'Einschalten'}: "
                     + ("nicht möglich" if v == "-" else "ohne Zusatz" if v == "" else f"über „{v}“"))
    return " · ".join(teile)


def test_connection(s: LlmSettings) -> tuple[bool, str]:
    """Für den Knopf „Verbindung testen“: echte Mini-Anfrage, verständliche Meldung."""
    if s.typ == "aus":
        return False, "Inhalts-Check mit KI ist ausgeschaltet."
    if s.vorlage.get("schluessel") and not s.token:
        return False, f"Für {s.vorlage.get('name', s.host)} brauchst du einen Schlüssel (Token)."
    b = OpenAICompatible(s) if s.typ in ("openai", "auto") and s.base_url else Ollama()
    try:
        if isinstance(b, OpenAICompatible):
            try:
                listed = b.models()
                if not b.model and listed:
                    b.model = listed[0]
                    b.label = f"openai:{b.model}@{s.host}"
                if b.model and listed and b.model not in listed:
                    return False, f"Modell „{b.model}“ nicht gefunden. Verfügbar: {', '.join(listed[:8])}"
            except LlmError as e:
                if str(e).startswith(("HTTP 401", "HTTP 403")):
                    return False, "Zugriff verweigert – Token prüfen."
                if not str(e).startswith(("HTTP 404", "HTTP 405")):
                    return False, f"Server nicht erreichbar: {e}"
            if not b.model:
                return False, "Bitte ein Modell angeben."
        elif not b.available():
            return False, f"Ollama nicht erreichbar oder Modell {OLLAMA_MODEL} nicht geladen."
        a = b.ask("Einkaufsliste: Milch, Brot, Äpfel.", name="test.txt")
        ziel = f" (Daten gehen an {a.sent_to}{', vorher anonymisiert' if a.anonymized else ''})" if a.sent_to else ""
        return True, f"✔ Verbindung klappt: {b.label}{ziel}. Testantwort: {a.data.get('beschreibung') or a.data}"
    except LlmError as e:
        return False, f"Fehler: {e}"
