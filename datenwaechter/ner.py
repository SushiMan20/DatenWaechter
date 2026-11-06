"""KI-Erkennung von Namen, Adressen & Co. – auch ohne „Herr/Frau“ davor.

Regeln finden Strukturiertes (IBAN, Schlüssel …). Namen wie „Mia Schneider“ ohne Anrede erkennt nur ein
Sprachmodell. Zwei Wege, beide lokal:
1. GLiNER: kleines Spezialmodell (~600 MB) in Python –  pip install "datenwaechter[ki]"
2. Der eingestellte KI-Server (lokales Modell über Ollama oder eigener Server im eigenen Netz).
   Funktioniert auch im fertigen Windows-Programm. Externe Server werden dafür NICHT benutzt –
   sonst müssten genau die Daten verschickt werden, die geschützt werden sollen.
"""

from __future__ import annotations

import os
from functools import lru_cache

from .detectors import HOCH, MITTEL, Finding

MODEL_NAME = os.environ.get("DATENWAECHTER_MODELL", "urchade/gliner_multi_pii-v1")
THRESHOLD = float(os.environ.get("DATENWAECHTER_SCHWELLE", "0.5"))
CHUNK = 1500  # Zeichen pro Abschnitt; das Modell sieht nur ~384 Tokens auf einmal

# GLiNER-Label  ->  (Typ, Anzeige, Stufe)
LABELS = {
    "person": ("PERSON", "Name einer Person", MITTEL),
    "address": ("ADRESSE", "Adresse", MITTEL),
    "date of birth": ("GEBURTSDATUM", "Geburtsdatum", MITTEL),
    "passport number": ("AUSWEIS", "Ausweis-/Passnummer", HOCH),
    "health insurance number": ("KRANKENVERSICHERUNG", "Krankenversicherungsnummer", HOCH),
    "medical condition": ("GESUNDHEIT", "Gesundheitsdaten", HOCH),
}


def gliner_available() -> bool:
    try:
        import gliner  # noqa: F401
        return True
    except ImportError:
        return False


def _local_llm():
    from . import llm
    b = llm.backend()
    return b if b is not None and not b.extern else None


def available() -> bool:
    return gliner_available() or _local_llm() is not None


def source() -> str | None:
    """Wer sucht die Namen? Für die Anzeige im Fenster."""
    if gliner_available():
        return "GLiNER"
    b = _local_llm()
    return b.label.partition(":")[2] if b else None


@lru_cache(maxsize=1)
def _model():
    from gliner import GLiNER
    return GLiNER.from_pretrained(MODEL_NAME)


def _chunks(text: str):
    pos = 0
    while pos < len(text):
        end = min(len(text), pos + CHUNK)
        if end < len(text):
            cut = text.rfind(" ", pos + CHUNK // 2, end)
            end = cut if cut > pos else end
        yield pos, text[pos:end]
        pos = end


def detect(text: str) -> list[Finding]:
    if not gliner_available():
        return _detect_llm(text)
    model = _model()
    out: list[Finding] = []
    for offset, chunk in _chunks(text):
        for ent in model.predict_entities(chunk, list(LABELS), threshold=THRESHOLD):
            kind, label, sev = LABELS[ent["label"]]
            start, end = offset + ent["start"], offset + ent["end"]
            out.append(Finding(kind, label, text[start:end], start, end, sev, "ki", float(ent["score"])))
    return out


_LLM_ARTEN = {"namen": ("PERSON", "Name einer Person", MITTEL), "adressen": ("ADRESSE", "Adresse", MITTEL),
              "geburtsdaten": ("GEBURTSDATUM", "Geburtsdatum", MITTEL)}


def _detect_llm(text: str) -> list[Finding]:
    """Fragt den lokalen KI-Server und sucht die genannten Angaben im Text (die KI liefert keine Positionen)."""
    import re as _re
    from . import llm
    b = _local_llm()
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
            for m in _re.finditer(_re.escape(value), text):   # nur, was wirklich im Text steht
                out.append(Finding(kind, label, m.group(0), m.start(), m.end(), sev, "ki", 0.8))
    return out
