"""Optionales lokales KI-Modell (GLiNER) für Namen, Adressen & Co.

Regeln finden Strukturiertes (IBAN, Schlüssel …). Namen wie „Anna Schmidt“ ohne Anrede
erkennt nur ein Sprachmodell. GLiNER ist ein kleines NER-Modell (~600 MB), läuft auf
der CPU, spricht Deutsch und lädt nach dem ersten Download nichts mehr aus dem Netz.

Installation:  pip install "datenwaechter[ki]"
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


def available() -> bool:
    try:
        import gliner  # noqa: F401
        return True
    except ImportError:
        return False


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
    model = _model()
    out: list[Finding] = []
    for offset, chunk in _chunks(text):
        for ent in model.predict_entities(chunk, list(LABELS), threshold=THRESHOLD):
            kind, label, sev = LABELS[ent["label"]]
            start, end = offset + ent["start"], offset + ent["end"]
            out.append(Finding(kind, label, text[start:end], start, end, sev, "ki", float(ent["score"])))
    return out
