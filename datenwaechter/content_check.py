"""Inhalts-Check: WAS wird da hochgeladen? („Du lädst gerade Familienunterlagen hoch – willst du das?“)

Zwei Stufen, beide lokal:
1. Stichwörter (immer verfügbar, sofort): erkennt Themen wie Familie, Gesundheit, Finanzen, Recht.
2. KI-Server (optional): versteht den Inhalt wirklich und kann auch Fotos beschreiben
   („Foto eines Personalausweises“, „Familienfoto mit Kindern“). Entweder Ollama lokal
   (https://ollama.com, dann `ollama pull gemma3:4b`) oder ein eigener OpenAI-kompatibler Server
   mit URL + Token (siehe settings.py / llm.py).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

from . import llm


@dataclass
class Verdict:
    categories: list[str] = field(default_factory=list)   # Anzeigenamen, z. B. "Familienunterlagen"
    hints: list[str] = field(default_factory=list)        # auslösende Wörter
    description: str | None = None                        # Was ist das? (nur Sprachmodell)
    warning: str | None = None                            # Satz an den Nutzer, None = unkritisch
    severity: int = 0                                     # 0 = unkritisch … 3 = hoch
    backend: str = "stichworte"                           # oder z. B. "ollama:gemma3:4b", "openai:modell@host"
    sent_to: str | None = None                            # Host, falls Inhalt an einen externen Server ging
    sent_anonymized: bool = False

    @property
    def by_ai(self) -> bool:
        return self.backend != "stichworte"

    def source_text(self) -> str:
        if not self.by_ai:
            return "Erkannt an Stichwörtern"
        kind, _, name = self.backend.partition(":")
        where = "lokaler KI" if kind == "ollama" else "KI-Server"
        out = f"Bewertet von {where} ({name})"
        if self.sent_to:
            out += f" – Inhalt wurde{' anonymisiert' if self.sent_anonymized else ''} an {self.sent_to} gesendet"
        return out

    def to_dict(self) -> dict:
        return {"categories": self.categories, "hints": self.hints, "description": self.description,
                "warning": self.warning, "severity": self.severity, "backend": self.backend,
                "sent_to": self.sent_to, "source": self.source_text()}


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
        hit_words = list(dict.fromkeys(hit_words))   # gleiches Wort nur einmal (z. B. „Familie*“ und „Familiengericht*“)
        if strong_hit or len(set(w.lower() for w in hit_words)) >= 2:
            cats.append(name)
            hints.extend(w for w in hit_words[:3] if w not in hints)
            sev = max(sev, stufe)
    v = Verdict(categories=cats, hints=hints, severity=sev)
    if cats:
        v.warning = f"Du lädst gerade {_join(cats)} hoch (Hinweise: {', '.join(f'„{h}“' for h in hints[:5])})."
    return v


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " und " + items[-1]


# --------------------------------------------------------------------------- KI-Server

def llm_status() -> str | None:
    """Anzeigename des aktiven KI-Servers (z. B. "ollama:gemma3:4b") oder None."""
    b = llm.backend()
    return b.label if b else None


def llm_check(text: str, image=None, name: str = "") -> Verdict | None:
    b = llm.backend()
    if b is None:
        return None
    try:
        a = b.ask(text, image, name)
    except llm.LlmError:
        return None
    keys = _llm_keys(a.data, has_image=image is not None)
    names = list(dict.fromkeys(llm.KATEGORIEN[k] for k in keys))
    desc = a.data.get("beschreibung") or None
    if isinstance(desc, str):
        desc = desc.strip().rstrip(".") + "." if desc.strip() else None
    return Verdict(categories=names, description=desc,
                   warning=f"Du lädst gerade {_join(names)} hoch." if names else None,
                   severity=max((llm.STUFE.get(k, 2) for k in keys), default=0), backend=a.backend,
                   sent_to=a.sent_to, sent_anonymized=a.anonymized)


def _truthy(v) -> bool:
    return v is True or (isinstance(v, str) and v.strip().lower() in ("true", "ja", "yes", "1"))


def _llm_keys(data: dict, has_image: bool) -> list[str]:
    """Liest die Ja/Nein-Antworten (und zur Sicherheit das ältere Format mit Kategorienliste)."""
    keys = [k for k in llm.FRAGEN if _truthy(data.get(k))]
    for raw in data.get("kategorien") or []:            # älteres Format / Modelle, die eine Liste liefern
        k = str(raw).strip().lower()
        k = next((key for key in llm.KATEGORIEN if k.startswith(key[:5])), None)  # „intimes“ -> „intim“
        if k and k not in keys:
            keys.append(k)
    if not has_image:  # „Menschen zu sehen“ ergibt nur bei Bildern Sinn
        keys = [k for k in keys if k not in ("personen", "personenfoto")]
    return keys


# --------------------------------------------------------------------------- Kombiniert

def check(text: str, image=None, name: str = "", use_llm: bool | str = "auto") -> Verdict:
    """use_llm: True/"auto" = KI-Server nutzen, falls eingerichtet und erreichbar; False = nur Stichwörter."""
    kw = keyword_check(text or "")
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


# --------------------------------------------------------------------------- Themen nur mit Personenbezug

# Diese Themen sind nur heikel, wenn eine Person erkennbar ist („CRP 200 – was heißt das?“ ist anonym und unkritisch).
# Firmeninterna, Zugangsdaten, Ausweise, Fotos von Personen und intime Inhalte bleiben immer eine Warnung.
PERSONENBEZOGEN = {"familie", "gesundheit", "finanzen", "recht", "arbeit", "besonders", "kinder"}


def _themen_namen() -> dict[str, str]:
    """Anzeigename → Schlüssel (Stichwort-Kategorien und KI-Kategorien)."""
    out = {name: key for key, (name, _st, _t) in _categories().items()}
    out.update({name: key for key, name in llm.KATEGORIEN.items()})
    return out


def nur_mit_personenbezug(v: Verdict, findings, faces: int = 0, aktiv: bool | None = None) -> Verdict:
    """Entfernt personenbezogene Themen, wenn im Inhalt keine Person erkennbar ist (Einstellung, Standard an)."""
    from .inhalte import IDENTITAET
    from .settings import schwaerzen
    if aktiv is None:
        aktiv = schwaerzen()["themen_nur_mit_person"]
    if not aktiv or not v.categories or faces or any(f.kind in IDENTITAET for f in findings):
        return v
    schluessel = _themen_namen()
    rest = [c for c in v.categories if schluessel.get(c) not in PERSONENBEZOGEN]
    if rest == v.categories:
        return v
    stufen = {name: st for _k, (name, st, _t) in _categories().items()}
    stufen.update({name: llm.STUFE.get(k, 2) for k, name in llm.KATEGORIEN.items()})
    # Kopie: keyword_check ist zwischengespeichert, das Original darf sich nicht ändern
    return replace(v, categories=rest, severity=max((stufen.get(c, 2) for c in rest), default=0),
                   warning=f"Du lädst gerade {_join(rest)} hoch." if rest else None)
