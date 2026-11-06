"""Namen, Adressen und Geburtsdaten über den eingestellten KI-Server – auch ohne „Herr/Frau“ davor.

Der KI-Server (OpenAI-kompatible API mit Adresse + Token) wird gefragt, wenn unter „KI-Server“ → „Namen ohne
Herr/Frau finden“ eingeschaltet ist. Bereits erkannte Angaben (IBAN, Telefon …) werden vorher durch Platzhalter
ersetzt, wenn „vor dem Senden anonymisieren“ aktiv ist.

Ohne Server und offline sucht das lokale KI-Modell (lokales_modell.py) Namen und Orte.
"""

from __future__ import annotations

from .detectors import MITTEL, Finding


def _llm():
    from . import llm
    return llm.backend()


def available() -> bool:
    return _llm() is not None


def source() -> str | None:
    """Wer sucht die Namen? Für die Anzeige im Fenster."""
    b = _llm()
    return b.label.partition(":")[2] if b else None


def detect(text: str) -> list[Finding]:
    return _detect_llm(text)


_LLM_ARTEN = {"namen": ("PERSON", "Name einer Person", MITTEL), "adressen": ("ADRESSE", "Adresse", MITTEL),
              "geburtsdaten": ("GEBURTSDATUM", "Geburtsdatum", MITTEL)}


def _detect_llm(text: str) -> list[Finding]:
    """Fragt den KI-Server und sucht die genannten Angaben im Text (die KI liefert keine Positionen)."""
    import re as _re
    from . import llm
    b = _llm()
    if b is None or not text.strip():
        return []
    try:
        data = llm.find_personal_data(text, b)
    except llm.LlmError:
        return []
    out: list[Finding] = []
    for key, (kind, label, sev) in _LLM_ARTEN.items():
        for value in data.get(key) or []:
            value = str(value).strip()
            if len(value) < 3 or len(value) > 120:
                continue
            if _re.fullmatch(r"\[[A-Z_]+_\d+\]", value):   # Platzhalter = schon gefunden
                continue
            for m in _re.finditer(_re.escape(value), text):   # nur, was wirklich im Text steht
                out.append(Finding(kind, label, m.group(0), m.start(), m.end(), sev, "ki", 0.8))
    return out
