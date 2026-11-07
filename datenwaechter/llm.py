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

from .settings import LlmSettings, load_llm

OLLAMA_URL = os.environ.get("DATENWAECHTER_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("DATENWAECHTER_OLLAMA_MODELL", "gemma3:4b")
MAX_CHARS = 6000
TIMEOUT = 120

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


# Gateways wie LiteLLM listen auch Sprach-, Vorlese-, Embedding- und OCR-Modelle – die können keinen Chat
_KEIN_CHAT = re.compile(r"(?i)(?:^|[/_.:-])(?:stt|tts|whisper|embed\w*|embedding\w*|ocr|rerank\w*|moderation|dall-e"
                        r"|image|transcri\w*|speech|audio)(?:$|[/_.:-])|\*")


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
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise LlmError(f"HTTP {e.code}: {detail}") from e
    except (OSError, ValueError) as e:
        raise LlmError(str(e)) from e


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

    def complete(self, messages: list[dict], temperature: float = 0.3) -> str:
        """Freier Text (für KI-Aktionen wie „Umformulieren“)."""
        body = {"model": self.model, "messages": messages, "stream": False, "options": {"temperature": temperature}}
        return (_request(f"{self.url}/api/chat", body).get("message") or {}).get("content", "")

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
        self.model = s.modell
        self.label = f"openai:{s.modell or '?'}@{s.host}"

    def models(self) -> list[str]:
        data = _request(f"{self.s.base_url}/models", token=self.s.token, timeout=3)
        return chat_zuerst([m.get("id", "") for m in data.get("data", []) if m.get("id")])

    def available(self) -> bool:
        if not self.s.base_url:
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

    def complete(self, messages: list[dict], temperature: float = 0.3) -> str:
        """Freier Text (für KI-Aktionen wie „Umformulieren“)."""
        body = {"model": self.model, "temperature": temperature, "messages": messages}
        data = _request(f"{self.s.base_url}/chat/completions", body, self.s.token)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LlmError("Unerwartetes Antwortformat") from e

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
        url = f"{self.s.base_url}/chat/completions"
        try:
            data = _request(url, body, self.s.token)
        except LlmError as e:
            if not str(e).startswith("HTTP 400"):
                raise
            body.pop("response_format")       # nicht jeder Server kennt den JSON-Modus …
            try:
                data = _request(url, body, self.s.token)
            except LlmError as e2:
                if not (str(e2).startswith("HTTP 400") and isinstance(content, list)):
                    raise
                body["messages"][1]["content"] = content[0]["text"]   # … oder Bilder
                data = _request(url, body, self.s.token)
        try:
            reply = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LlmError("Unerwartetes Antwortformat") from e
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


def test_connection(s: LlmSettings) -> tuple[bool, str]:
    """Für den Knopf „Verbindung testen“: echte Mini-Anfrage, verständliche Meldung."""
    if s.typ == "aus":
        return False, "Inhalts-Check mit KI ist ausgeschaltet."
    b = OpenAICompatible(s) if s.typ in ("openai", "auto") and s.base_url else Ollama()
    try:
        if isinstance(b, OpenAICompatible):
            try:
                listed = b.models()
                if not b.model and listed:
                    b.model = listed[0]
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
