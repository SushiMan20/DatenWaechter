"""KI-Aktionen auf markiertem Text: „Umformulieren“, „Kürzen“, „Übersetzen“ … und eigene Aktionen.

Aufruf per Rechtsklick (Browser-Erweiterung), Tastenkürzel (Windows-Fenster) oder Kommandozeile.
Läuft über den eingestellten KI-Server (Ollama oder eigener OpenAI-kompatibler Server).

Datenschutz: Ist der Server extern, werden Namen, IBAN usw. vor dem Senden durch Platzhalter ersetzt
und in der Antwort wieder eingesetzt – der Anbieter sieht die echten Daten nie.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from . import llm
from .anonymize import Anonymizer
from .settings import path as settings_path

MODI = {"ersetzen": "Markierung ersetzen", "einfuegen": "darunter einfügen", "anzeigen": "nur anzeigen"}
MAX_CHARS = 12_000

SYSTEM = ("Du bist ein Schreibassistent. Wende die Anweisung auf den Text an und gib NUR das Ergebnis zurück – "
          "ohne Einleitung, ohne Erklärung, ohne Anführungszeichen drumherum. Behalte die Sprache des Textes bei, "
          "außer die Anweisung verlangt etwas anderes. Platzhalter in eckigen Klammern wie [PERSON_1] oder [IBAN_1] "
          "sind ersetzte echte Daten: übernimm sie unverändert.")


@dataclass
class Aktion:
    name: str
    anweisung: str
    modus: str = "ersetzen"   # ersetzen | einfuegen | anzeigen
    denken: str = ""          # "" = wie beim KI-Server eingestellt | aus | an

    @property
    def id(self) -> str:
        return slug(self.name)


STANDARD = [
    Aktion("Umformulieren", "Formuliere den Text um: gleiche Aussage, flüssiger und klarer."),
    Aktion("Kürzen", "Kürze den Text auf etwa die Hälfte, ohne wichtige Informationen zu verlieren."),
    Aktion("Freundlicher formulieren", "Formuliere den Text freundlicher und höflicher, aber nicht unterwürfig."),
    Aktion("Professioneller formulieren", "Formuliere den Text sachlich und professionell für eine geschäftliche E-Mail."),
    Aktion("Rechtschreibung korrigieren", "Korrigiere nur Rechtschreibung, Grammatik und Zeichensetzung. Ändere sonst nichts."),
    Aktion("Ins Englische übersetzen", "Übersetze den Text ins Englische."),
    Aktion("Zusammenfassen", "Fasse den Text in 3 bis 5 Stichpunkten zusammen.", "anzeigen"),
    Aktion("Antwort entwerfen", "Schreibe eine kurze, freundliche Antwort auf diese Nachricht.", "einfuegen"),
]


def slug(name: str) -> str:
    s = name.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "aktion"


def _read() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load() -> list[Aktion]:
    raw = _read().get("aktionen")
    if not isinstance(raw, list):
        return list(STANDARD)
    out = []
    for a in raw:
        if isinstance(a, dict) and a.get("name") and a.get("anweisung"):
            out.append(Aktion(a["name"], a["anweisung"], a.get("modus") if a.get("modus") in MODI else "ersetzen",
                              a.get("denken") if a.get("denken") in ("aus", "an") else ""))
    return out


def save(aktionen: list[Aktion]) -> None:
    p = settings_path()
    data = _read()
    data["aktionen"] = [asdict(a) for a in aktionen]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_hotkey() -> str:
    from .hotkey import STANDARD as HK
    return _read().get("tastenkuerzel") or HK


def save_hotkey(combo: str) -> None:
    p = settings_path()
    data = _read()
    data["tastenkuerzel"] = combo
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def find(key: str, aktionen: list[Aktion] | None = None) -> Aktion | None:
    aktionen = aktionen if aktionen is not None else load()
    return next((a for a in aktionen if a.id == key or a.name.lower() == key.lower()), None)


@dataclass
class Ergebnis:
    text: str
    aktion: Aktion
    backend: str
    sent_to: str | None
    anonymized: bool

    def to_dict(self) -> dict:
        return {"ok": True, "result": self.text, "mode": self.aktion.modus, "name": self.aktion.name,
                "backend": self.backend, "sent_to": self.sent_to, "anonymized": self.anonymized}


def _clean(text: str) -> str:
    t = (text or "").strip()
    m = re.fullmatch(r"```[a-zA-Z]*\n(.*)\n```", t, re.S)
    if m:
        t = m.group(1).strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'„“":
        t = t[1:-1].strip()
    if t.startswith("„") and t.endswith("“"):
        t = t[1:-1].strip()
    return t


def run(aktion: Aktion | str, text: str, fortschritt=None) -> Ergebnis:
    """Führt die Aktion mit dem eingestellten KI-Server aus. Wirft llm.LlmError mit verständlicher Meldung.

    fortschritt(text_bisher, denkt): während die Antwort hereinkommt (gestreamt)."""
    a = find(aktion) if isinstance(aktion, str) else aktion
    if a is None:
        raise llm.LlmError(f"Aktion „{aktion}“ nicht gefunden")
    if not text.strip():
        raise llm.LlmError("Kein Text markiert")
    if len(text) > MAX_CHARS:
        raise llm.LlmError(f"Text zu lang ({len(text)} Zeichen, höchstens {MAX_CHARS})")
    b = llm.backend()
    if b is None:
        raise llm.LlmError("Kein KI-Server eingerichtet oder erreichbar – im Datenwächter unter Einstellungen → KI-Server")
    anon = Anonymizer()
    send = anon.anonymize(text) if b.anonymize_first else text
    reply = b.complete([{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": f"Anweisung: {a.anweisung}\n\nText:\n<<<\n{send}\n>>>"}],
                       denken=a.denken or None, fortschritt=fortschritt)
    result = anon.restore(_clean(reply))
    return Ergebnis(result, a, b.label, b.host if b.extern else None, send != text)
