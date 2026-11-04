"""Regelbasierte Erkennung sensibler Daten (läuft komplett lokal, ohne Internet).

Jede Regel liefert Kandidaten; Prüfsummen (IBAN, Kreditkarte, Steuer-ID) filtern
Fehlalarme heraus. Überlappende Treffer werden zugunsten des wichtigsten aufgelöst.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

HOCH, MITTEL, NIEDRIG = 3, 2, 1
SEVERITY_LABEL = {HOCH: "hoch", MITTEL: "mittel", NIEDRIG: "niedrig"}


@dataclass(frozen=True)
class Finding:
    kind: str          # technischer Typ, z. B. "IBAN" – wird auch als Platzhalter genutzt
    label: str         # deutsche Bezeichnung für die Anzeige
    text: str          # gefundener Wert
    start: int
    end: int
    severity: int
    source: str = "regel"   # "regel" oder "ki"
    score: float = 1.0

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABEL[self.severity]

    def masked(self) -> str:
        """Für die Anzeige: Geheimnisse nur teilweise zeigen, alles andere vollständig."""
        if self.kind in SECRET_KINDS:
            t = self.text.replace("\n", " ")
            if len(t) <= 8:
                return "****"
            return f"{t[:4]}…{t[-3:]} ({len(self.text)} Zeichen)"
        return self.text if len(self.text) <= 80 else self.text[:77] + "…"


@dataclass
class Rule:
    kind: str
    label: str
    pattern: re.Pattern
    severity: int
    group: int | str = 0
    validate: Callable[[str], bool] | None = None
    min_digits: int = 0
    max_digits: int = 0
    tags: tuple = field(default_factory=tuple)


# --------------------------------------------------------------------------- Prüfsummen

def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def iban_valid(s: str) -> bool:
    iban = re.sub(r"\s", "", s).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):
        return False
    if iban.startswith("DE") and len(iban) != 22:
        return False
    rearranged = iban[4:] + iban[:4]
    num = "".join(str(int(c, 36)) for c in rearranged)
    return int(num) % 97 == 1


def luhn_valid(s: str) -> bool:
    d = _digits(s)
    if not 13 <= len(d) <= 19 or len(set(d)) == 1:
        return False
    total = 0
    for i, ch in enumerate(reversed(d)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def steuer_id_valid(s: str) -> bool:
    """Deutsche Steuer-Identifikationsnummer (11 Ziffern, ISO 7064 MOD 11,10)."""
    d = _digits(s)
    if len(d) != 11 or d[0] == "0":
        return False
    product = 10
    for ch in d[:10]:
        total = (int(ch) + product) % 10 or 10
        product = (total * 2) % 11
    check = (11 - product) % 10
    return check == int(d[10])


# --------------------------------------------------------------------------- Regeln

_UC = "A-ZÄÖÜ"
_LC = "a-zäöüß"

SECRET_KINDS = {
    "PRIVATER_SCHLUESSEL", "API_SCHLUESSEL", "PASSWORT", "ZUGANGSDATEN_URL", "TOKEN",
}

RULES: list[Rule] = [
    # ---- Geheimnisse (immer "hoch")
    Rule("PRIVATER_SCHLUESSEL", "Privater Schlüssel",
         re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----"), HOCH),
    Rule("API_SCHLUESSEL", "API-Schlüssel (Anthropic)", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), HOCH),
    Rule("API_SCHLUESSEL", "API-Schlüssel (OpenAI)", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}"), HOCH),
    Rule("API_SCHLUESSEL", "AWS-Zugangsschlüssel", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), HOCH),
    Rule("API_SCHLUESSEL", "GitHub-Token",
         re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b"), HOCH),
    Rule("API_SCHLUESSEL", "Slack-Token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), HOCH),
    Rule("API_SCHLUESSEL", "Google-API-Schlüssel", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), HOCH),
    Rule("API_SCHLUESSEL", "Stripe-Schlüssel", re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}\b"), HOCH),
    Rule("TOKEN", "JWT / Sitzungs-Token",
         re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), HOCH),
    Rule("ZUGANGSDATEN_URL", "Datenbank-Zugang mit Passwort",
         re.compile(r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqp|mssql|ftp|sftp)://"
                    r"[^\s:@/]+:[^\s@/]+@[^\s\"'<>]+"), HOCH),
    Rule("PASSWORT", "Passwort / Geheimnis",
         re.compile(r"(?i)\b(?:passwor[dt]|kennwort|passwd|pwd|secret|client[_-]?secret|api[_-]?key|access[_-]?token)"
                    r"\b[\"']?\s*[:=]\s*[\"']?(?P<v>[^\s\"',;]{4,})"), HOCH, group="v"),

    # ---- Finanz- und Identitätsdaten
    Rule("IBAN", "IBAN / Bankverbindung",
         re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b"), HOCH, validate=iban_valid),
    Rule("KREDITKARTE", "Kreditkartennummer",
         re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])"), HOCH, validate=luhn_valid),
    Rule("STEUER_ID", "Steuer-ID",
         re.compile(r"(?<!\d)\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}(?!\d)"), HOCH, validate=steuer_id_valid),
    Rule("SOZIALVERSICHERUNG", "Sozialversicherungsnummer",
         re.compile(r"\b\d{2}[ ]?(?:0[1-9]|[12]\d|3[01])(?:0[1-9]|1[0-2])\d{2}[ ]?[A-Z][ ]?\d{3}\b"), HOCH),
    Rule("GEBURTSDATUM", "Geburtsdatum",
         re.compile(r"(?i)\b(?:geb(?:oren|\.)?(?:\s+am)?|geburtsdatum|geburtstag|date of birth|dob)\s*:?\s*"
                    r"(?P<v>\d{1,2}\.\s?\d{1,2}\.\s?\d{2,4}|\d{4}-\d{2}-\d{2})"), MITTEL, group="v"),

    # ---- Kontakt & Adresse
    Rule("EMAIL", "E-Mail-Adresse",
         re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), MITTEL),
    Rule("TELEFON", "Telefonnummer",
         re.compile(r"(?<![\w+/.])(?:\+\d{1,3}|00\d{1,3}|0)[ /.-]?\(?\d{2,5}\)?(?:[ /.-]?\d{2,}){1,4}(?!\w|\.\d)"),
         MITTEL, min_digits=7, max_digits=15),
    Rule("ADRESSE", "Straße und Hausnummer",
         re.compile(rf"\b[{_UC}][{_LC}]+(?:[- ][{_UC}]?[{_LC}]+)*"
                    rf"(?:straße|strasse|str\.|weg|gasse|platz|allee|ring|damm|ufer|chaussee|pfad|steig)"
                    rf"\s+\d{{1,4}}(?:\s?[a-zA-Z])?\b"), MITTEL),
    Rule("ADRESSE", "PLZ und Ort",
         re.compile(rf"(?<![\d.,])\b\d{{5}}\s+(?!(?:Euro|EUR|Stück|Mal|Jahre|Tage|Mitarbeiter|Kunden|Nutzer)\b)"
                    rf"[{_UC}][{_LC}]+(?:[ -](?:am|an der|im|ob der)?\s?[{_UC}][{_LC}]+)?\b"), MITTEL),
    Rule("PERSON", "Name (Anrede)",
         re.compile(rf"\b(?:Herr|Herrn|Frau|Mr\.?|Mrs\.?|Ms\.?)\s+(?:(?:Dr|Prof)\.\s+)*"
                    rf"(?P<v>[{_UC}][{_LC}]+(?:[- ][{_UC}][{_LC}]+)?)"), MITTEL, group="v"),
    Rule("IP_ADRESSE", "IP-Adresse",
         re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])"),
         NIEDRIG),
]


def _rule_findings(text: str) -> Iterable[Finding]:
    for rule in RULES:
        for m in rule.pattern.finditer(text):
            start, end = m.span(rule.group)
            value = text[start:end]
            if rule.validate and not rule.validate(value):
                continue
            if rule.min_digits or rule.max_digits:
                n = len(_digits(value))
                if n < rule.min_digits or (rule.max_digits and n > rule.max_digits):
                    continue
            yield Finding(rule.kind, rule.label, value, start, end, rule.severity)


def resolve_overlaps(findings: Iterable[Finding]) -> list[Finding]:
    """Bei Überlappung gewinnt: höhere Stufe, dann längerer Treffer, dann früherer."""
    ordered = sorted(findings, key=lambda f: (-f.severity, -(f.end - f.start), f.start))
    kept: list[Finding] = []
    for f in ordered:
        if all(f.end <= k.start or f.start >= k.end for k in kept):
            kept.append(f)
    return sorted(kept, key=lambda f: f.start)


def scan_text(text: str, use_ki: bool = False) -> list[Finding]:
    """Durchsucht Text nach sensiblen Daten. `use_ki=True` ergänzt das lokale KI-Modell (falls installiert)."""
    found = list(_rule_findings(text))
    if use_ki:
        from . import ner
        if ner.available():
            found.extend(ner.detect(text))
    return resolve_overlaps(found)


def summarize(findings: list[Finding]) -> dict[str, int]:
    out: dict[str, int] = {}
    for f in findings:
        out[f.label] = out.get(f.label, 0) + 1
    return out
