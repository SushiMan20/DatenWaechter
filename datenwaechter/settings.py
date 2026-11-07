"""Einstellungen (vor allem: welcher KI-Server den Inhalts-Check macht).

Gespeichert in  %APPDATA%\\Datenwaechter\\einstellungen.json  (Windows)
bzw.            ~/.config/datenwaechter/einstellungen.json   (sonst).
Das Token liegt – wenn `keyring` installiert ist – in der Windows-Anmeldeinformationsverwaltung,
sonst in der Datei. Fenster, Kommandozeile und Browser-Erweiterung lesen dieselbe Datei.

Umgebungsvariablen haben Vorrang (praktisch für Firmen-Rollouts):
  DATENWAECHTER_LLM_URL, DATENWAECHTER_LLM_TOKEN, DATENWAECHTER_LLM_MODELL
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from urllib.parse import urlparse

KEYRING_SERVICE = "datenwaechter"
KEYRING_USER = "llm-token"

# Vorschläge für das Eingabefeld (Anzeige, Basis-URL)
URL_VORLAGEN = [
    ("OpenAI", "https://api.openai.com/v1"),
    ("OpenRouter", "https://openrouter.ai/api/v1"),
    ("Mistral", "https://api.mistral.ai/v1"),
    ("LM Studio (lokal)", "http://localhost:1234/v1"),
    ("Ollama, OpenAI-Modus (lokal)", "http://localhost:11434/v1"),
    ("vLLM / LocalAI (lokal)", "http://localhost:8000/v1"),
]

# Feste Angaben für einen eigenen Dienst (Basis-URL → Angaben), z. B.:
#   "https://ki.example.org/v1": {"name": "Mein Dienst", "modell": "qwen3-…",
#                                 "extra": {"chat_template_kwargs": {"enable_thinking": False}}, "schluessel": True}
# modell = Standardmodell, extra = Zusatzangaben je Anfrage (nur für dieses Modell), schluessel = Token ist Pflicht
VORLAGE_DETAILS: dict[str, dict] = {}


@dataclass
class LlmSettings:
    typ: str = "auto"              # auto | ollama | openai | aus
    url: str = ""                  # Basis-URL eines OpenAI-kompatiblen Servers, z. B. http://localhost:1234/v1
    token: str = ""                # API-Schlüssel / Bearer-Token (leer = ohne Anmeldung)
    modell: str = ""               # leer = erstes Modell, das der Server anbietet
    bilder_senden: bool | None = None   # None = automatisch: nur an Server im eigenen Netz
    anonymisieren: bool | None = None   # None = automatisch: vor dem Senden an externe Server
    ollama_modell: str = ""        # lokales Modell in Ollama; leer = Standard (gemma3:4b)
    ki_namen: bool = False         # KI sucht zusätzlich Namen/Adressen ohne „Herr/Frau“ (nur lokale Server)

    @property
    def base_url(self) -> str:
        return normalize_url(self.url)

    @property
    def host(self) -> str:
        return urlparse(self.base_url).hostname or ""

    @property
    def vorlage(self) -> dict:
        return VORLAGE_DETAILS.get(self.base_url, {})

    @property
    def extern(self) -> bool:
        return is_external(self.base_url)

    @property
    def send_images(self) -> bool:
        return (not self.extern) if self.bilder_senden is None else self.bilder_senden

    @property
    def anonymize_first(self) -> bool:
        return self.extern if self.anonymisieren is None else self.anonymisieren


_LOKAL = re.compile(r"(?i)^(?:localhost|127\.|10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.|\[?::1\]?$|[^./]+\.(?:local|lan)$|[^.]+$)")   # ohne Punkt = Rechner im eigenen Netz


def normalize_url(url: str) -> str:
    """Adresse so, wie sie eingetippt wurde → saubere Basis-URL.

    „https:\\ki.firma.de\\v1“ (Backslashes wie im Explorer), „ki.firma.de/v1“ (ohne https://) und
    „…/v1/chat/completions“ (ganze Endpunkt-Adresse) werden zu „https://ki.firma.de/v1“.
    """
    u = (url or "").strip().replace("\\", "/")
    if not u:
        return ""
    m = re.match(r"(?i)^(https?):/*", u)
    if m:
        u = f"{m.group(1).lower()}://{u[m.end():]}"
    else:
        rechner = re.split(r"[/:]", u, maxsplit=1)[0]
        u = ("http://" if _LOKAL.match(rechner) else "https://") + u
    u = u.rstrip("/")
    for suffix in ("/chat/completions", "/completions", "/models"):
        if u.endswith(suffix):
            u = u[: -len(suffix)]
    return u


def is_external(url: str) -> bool:
    """True, wenn der Server (vermutlich) außerhalb des eigenen Rechners/Netzes liegt."""
    host = (urlparse(normalize_url(url)).hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or host.endswith((".local", ".lan", ".internal", ".intranet", ".home.arpa", ".localhost")):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        return "." in host  # einfacher Rechnername ohne Punkt = Firmennetz


def path() -> Path:
    if os.environ.get("DATENWAECHTER_EINSTELLUNGEN"):
        return Path(os.environ["DATENWAECHTER_EINSTELLUNGEN"])
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "Datenwaechter" / "einstellungen.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "datenwaechter" / "einstellungen.json"


def _keyring():
    if os.environ.get("DATENWAECHTER_KEIN_SCHLUESSELBUND"):
        return None
    try:
        import keyring
        from keyring.backends import fail
    except ImportError:
        return None
    try:
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
    except Exception:  # noqa: BLE001
        return None
    return keyring


def load_llm() -> LlmSettings:
    s = LlmSettings()
    p = path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8")).get("llm", {})
        except (OSError, ValueError):
            data = {}
        known = {f.name for f in fields(LlmSettings)}
        for k, v in data.items():
            if k in known:
                setattr(s, k, v)
        if "\\" in s.url:   # früher mit Backslashes gespeichert: Server galt als „lokal“ – Vorgaben neu bestimmen
            s.url, s.anonymisieren, s.bilder_senden = normalize_url(s.url), None, None
        if data.get("token_im_schluesselbund") and (kr := _keyring()):
            try:
                s.token = kr.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
            except Exception:  # noqa: BLE001
                s.token = ""
    # Umgebungsvariablen haben Vorrang
    if os.environ.get("DATENWAECHTER_LLM_URL"):
        s.url = os.environ["DATENWAECHTER_LLM_URL"]
        if s.typ in ("auto", "ollama"):
            s.typ = "openai"
    s.token = os.environ.get("DATENWAECHTER_LLM_TOKEN", s.token)
    s.modell = os.environ.get("DATENWAECHTER_LLM_MODELL", s.modell)
    return s


def save_llm(s: LlmSettings) -> Path:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        data = {}
    llm = asdict(s)
    kr = _keyring()
    if kr and s.token:
        kr.set_password(KEYRING_SERVICE, KEYRING_USER, s.token)
        llm["token"] = ""
        llm["token_im_schluesselbund"] = True
    else:
        llm["token_im_schluesselbund"] = False
    data["llm"] = llm
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if sys.platform != "win32":
        try:
            p.chmod(0o600)  # Token nur für den eigenen Benutzer lesbar
        except OSError:
            pass
    return p


def masked_token(token: str) -> str:
    if not token:
        return "(keins)"
    return "****" if len(token) <= 8 else f"{token[:3]}…{token[-4:]}"


# --------------------------------------------------------------------------- Was soll geschwärzt werden?

SCHWAERZEN_STANDARD = {
    "firmen": True,                  # Firmennamen, Kunden-/Vertrags-/Angebotsnummern, Aktenzeichen
    "betraege": False,               # Preise und Beträge (die KI braucht sie oft)
    "medizin": False,                # Diagnosen, ICD-Codes, Medikamente, Laborwerte
    "themen_nur_mit_person": True,   # Gesundheit/Familie/Recht … nur melden, wenn eine Person erkennbar ist
}
_schwaerzen_cache: dict = {}


def schwaerzen() -> dict:
    """Einstellungen „Was soll geschwärzt werden?“ (mit Standardwerten; kurz zwischengespeichert)."""
    p = path()
    try:
        stand = p.stat().st_mtime_ns
    except OSError:
        stand = None
    if _schwaerzen_cache.get("p") == str(p) and _schwaerzen_cache.get("stand") == stand:
        return dict(_schwaerzen_cache["wert"])
    wert = dict(SCHWAERZEN_STANDARD)
    try:
        eigene = json.loads(p.read_text(encoding="utf-8")).get("schwaerzen", {})
        wert.update({k: bool(v) for k, v in eigene.items() if k in SCHWAERZEN_STANDARD})
    except (OSError, ValueError, AttributeError):
        pass
    _schwaerzen_cache.update(p=str(p), stand=stand, wert=wert)
    return dict(wert)


def schwaerzen_speichern(werte: dict) -> None:
    p = path()
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        data = {}
    data["schwaerzen"] = {k: bool(werte.get(k, v)) for k, v in SCHWAERZEN_STANDARD.items()}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- Lokales KI-Modell

def modell_nutzen() -> bool:
    """Lokales KI-Modell verwenden, sobald es geladen ist (Standard: ja)."""
    try:
        return bool(json.loads(path().read_text(encoding="utf-8")).get("lokales_modell", True))
    except (OSError, ValueError, AttributeError):
        return True


def modell_nutzen_speichern(an: bool) -> None:
    p = path()
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        data = {}
    data["lokales_modell"] = bool(an)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- Kleine Schalter

def _schalter(name: str, standard: bool) -> bool:
    try:
        return bool(json.loads(path().read_text(encoding="utf-8")).get(name, standard))
    except (OSError, ValueError, AttributeError):
        return standard


def _schalter_speichern(name: str, an: bool) -> None:
    p = path()
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        data = {}
    data[name] = bool(an)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def inhalts_check_ki() -> bool:
    """Inhalts-Check („Du lädst gerade …“) mit dem KI-Server, sobald einer eingerichtet ist (Standard: ja)."""
    return _schalter("inhalts_check_ki", True)


def inhalts_check_ki_speichern(an: bool) -> None:
    _schalter_speichern("inhalts_check_ki", an)


def ki_server_schalten(an: bool) -> LlmSettings:
    """KI-Server an/aus (z. B. aus dem Tray-Menü) – Adresse, Token und Modell bleiben gespeichert."""
    s = load_llm()
    s.typ = "openai" if an else "aus"
    save_llm(s)
    return s
