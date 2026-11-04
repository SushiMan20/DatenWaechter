"""Inhalts-Check: WAS wird da hochgeladen? („Du lädst gerade Familienunterlagen hoch – willst du das?“)

Zwei Stufen, beide lokal:
1. Stichwörter (immer verfügbar, sofort): erkennt Themen wie Familie, Gesundheit, Finanzen, Recht.
2. Lokales Sprachmodell über Ollama (optional): versteht den Inhalt wirklich und kann auch Fotos
   beschreiben („Foto eines Personalausweises“, „Familienfoto mit Kindern“).
   Einrichtung:  https://ollama.com installieren, dann  `ollama pull gemma3:4b`
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
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

OLLAMA_URL = os.environ.get("DATENWAECHTER_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("DATENWAECHTER_OLLAMA_MODELL", "gemma3:4b")
MAX_CHARS = 6000  # so viel Text bekommt das Sprachmodell zu sehen


@dataclass
class Verdict:
    categories: list[str] = field(default_factory=list)   # Anzeigenamen, z. B. "Familienunterlagen"
    hints: list[str] = field(default_factory=list)        # auslösende Wörter
    description: str | None = None                        # Was ist das? (nur Sprachmodell)
    warning: str | None = None                            # Satz an den Nutzer, None = unkritisch
    severity: int = 0                                     # 0 = unkritisch … 3 = hoch
    backend: str = "stichworte"

    def to_dict(self) -> dict:
        return {"categories": self.categories, "hints": self.hints, "description": self.description,
                "warning": self.warning, "severity": self.severity, "backend": self.backend}


# --------------------------------------------------------------------------- Stichwörter

@lru_cache(maxsize=1)
def _categories() -> dict:
    data = json.loads((Path(__file__).with_name("kategorien.json")).read_text(encoding="utf-8"))
    out = {}
    for key, cat in data.items():
        if key.startswith("_"):
            continue
        terms = []
        for raw in cat["begriffe"]:
            strong = raw.startswith("!")
            word = raw.lstrip("!")
            prefix = word.endswith("*")
            word = word.rstrip("*")
            pat = r"(?<!\w)" + re.escape(word).replace(r"\ ", r"\s+") + (r"\w*" if prefix else r"(?!\w)")
            terms.append((word, strong, re.compile(pat, re.IGNORECASE)))
        out[key] = (cat["name"], cat["stufe"], terms)
    return out


def write_extension_categories() -> None:
    """Überträgt kategorien.json in die Browser-Erweiterung (extension/kategorien.js)."""
    src = Path(__file__).with_name("kategorien.json")
    data = json.loads(src.read_text(encoding="utf-8"))
    target = Path(__file__).resolve().parent.parent / "extension" / "kategorien.js"
    target.write_text("// Automatisch aus datenwaechter/kategorien.json erzeugt – dort ändern, dann:\n"
                      "//   python -c \"import datenwaechter.content_check as c; c.write_extension_categories()\"\n"
                      "globalThis.DWKategorien = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
                      encoding="utf-8")


def keyword_check(text: str) -> Verdict:
    cats, hints, sev = [], [], 0
    for _key, (name, stufe, terms) in _categories().items():
        hit_words, strong_hit = [], False
        for word, strong, pat in terms:
            m = pat.search(text)
            if m:
                hit_words.append(m.group(0))
                strong_hit |= strong
        if strong_hit or len(hit_words) >= 2:
            cats.append(name)
            hints.extend(hit_words[:3])
            sev = max(sev, stufe)
    v = Verdict(categories=cats, hints=hints, severity=sev)
    if cats:
        v.warning = f"Du lädst gerade {_join(cats)} hoch (Hinweise: {', '.join(f'„{h}“' for h in hints[:5])})."
    return v


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " und " + items[-1]


# --------------------------------------------------------------------------- Sprachmodell (Ollama)

LLM_KATEGORIEN = {
    "familie": "Familienunterlagen", "kinder": "Daten über Kinder", "gesundheit": "Gesundheitsdaten",
    "finanzen": "Finanzunterlagen", "recht": "rechtliche Unterlagen", "arbeit": "Personal- und Arbeitsunterlagen",
    "ausweis": "Ausweisdokumente", "vertraulich": "vertrauliche Firmeninterna", "zugangsdaten": "Zugangsdaten",
    "intim": "intime oder private Inhalte", "besonders": "besonders geschützte Daten (Religion, Politik, Sexualität)",
    "personenfoto": "Fotos von Personen",
}

PROMPT = """Du bist ein lokaler Datenschutz-Assistent. Ein Nutzer will gleich den folgenden Inhalt in einen
Cloud-KI-Chat (z. B. ChatGPT oder Claude) hochladen. Prüfe, ob der Inhalt private oder sensible Informationen enthält.

Mögliche Kategorien: {kats}, unkritisch.

Antworte NUR mit JSON in genau diesem Format:
{{"kategorien": ["..."], "beschreibung": "ein kurzer Satz, was das ist",
  "warnung": "ein Satz an den Nutzer in Du-Form, z. B. 'Du lädst gerade die Scheidungsunterlagen deiner Familie hoch.' – leer lassen, wenn unkritisch",
  "stufe": 0}}
stufe: 0 = unkritisch, 1 = etwas privat, 2 = sensibel, 3 = hoch sensibel (Gesundheit, Ausweis, Kinder, Intimes).

Dateiname: {name}
Inhalt:
<<<
{text}
>>>"""

_status_cache: tuple[float, bool] | None = None


def ollama_available() -> bool:
    """Läuft Ollama lokal und ist das Modell geladen? (Ergebnis 60 s zwischengespeichert)"""
    global _status_cache
    if _status_cache and time.time() - _status_cache[0] < 60:
        return _status_cache[1]
    ok = False
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=0.7) as r:
            models = [m.get("name", "") for m in json.load(r).get("models", [])]
            ok = any(m == OLLAMA_MODEL or m.split(":")[0] == OLLAMA_MODEL for m in models)
    except (OSError, ValueError):
        ok = False
    _status_cache = (time.time(), ok)
    return ok


def llm_check(text: str, image=None, name: str = "") -> Verdict | None:
    body = {
        "model": OLLAMA_MODEL,
        "prompt": PROMPT.format(kats=", ".join(LLM_KATEGORIEN), name=name or "(eingefügter Text)",
                                text=(text or "(kein Text – siehe Bild)")[:MAX_CHARS]),
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},
    }
    if image is not None:
        buf = io.BytesIO()
        img = image.convert("RGB")
        img.thumbnail((1024, 1024))
        img.save(buf, "JPEG", quality=85)
        body["images"] = [base64.b64encode(buf.getvalue()).decode()]
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            answer = json.loads(json.load(r)["response"])
    except (OSError, ValueError, KeyError):
        return None
    keys = [k for k in answer.get("kategorien") or [] if k != "unkritisch"]
    stufe = int(answer.get("stufe") or 0)
    warnung = (answer.get("warnung") or "").strip() or None
    if stufe == 0 or not keys:
        warnung = None
    return Verdict(categories=[LLM_KATEGORIEN.get(k, k) for k in keys], description=answer.get("beschreibung"),
                   warning=warnung, severity=min(max(stufe, 0), 3), backend=f"ollama:{OLLAMA_MODEL}")


# --------------------------------------------------------------------------- Kombiniert

def check(text: str, image=None, name: str = "", use_llm: bool | str = "auto") -> Verdict:
    """use_llm: True = Sprachmodell nutzen, False = nur Stichwörter, "auto" = nutzen, falls Ollama läuft."""
    kw = keyword_check(text or "")
    if use_llm == "auto":
        use_llm = ollama_available()
    if not use_llm:
        return kw
    llm = llm_check(text, image, name)
    if llm is None:
        return kw
    # Sprachmodell führt, Stichwort-Kategorien ergänzen (falls das Modell etwas übersieht)
    for c in kw.categories:
        if c not in llm.categories:
            llm.categories.append(c)
    llm.hints = kw.hints
    if not llm.warning and kw.warning:
        llm.warning = kw.warning
    llm.severity = max(llm.severity, kw.severity)
    return llm
