"""Das Repository bleibt sauber: keine echten Schlüssel, keine echten E-Mail-Adressen, keine internen Server.

Läuft bei jedem Push (pytest in der Windows-CI) und lokal mit pytest. Geprüft werden alle Dateien im Repository
und die Nachricht des letzten Commits.

Interne Begriffe (Server-Adressen, Modellnamen, IP-Adressen …) stehen nur als SHA-256-Fingerabdruck in
tests/fixtures/verboten.sha256 – die Liste selbst verrät also nichts. Neuen Begriff sperren:

    python tests/test_repo_sauber.py --sperren "intern.example-firma.de"
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VERBOTEN = ROOT / "tests" / "fixtures" / "verboten.sha256"
BINAER = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".docx", ".onnx", ".zip", ".gz", ".woff", ".woff2", ".ttf"}

SCHLUESSEL = {
    "OpenAI/Anthropic-Schlüssel": r"\bsk-(?:ant-[a-z0-9]+-|proj-|svcacct-)?[A-Za-z0-9_\-]{20,}",
    "GitHub-Token": r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})",
    "AWS-Schlüssel": r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    "Google-API-Schlüssel": r"\bAIza[0-9A-Za-z_\-]{35}\b",
    "Slack-Token": r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    "Stripe-Schlüssel": r"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}",
    "JWT": r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
}
PRIVATER_SCHLUESSEL = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s*\n\s*[A-Za-z0-9+/]{40,}")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
ERLAUBTE_DOMAINS = re.compile(r"(?i)(?:^|\.)(?:example(?:\.(?:de|com|org|net|at|ch))?|test|invalid|localhost|local|"
                              r"intern|users\.noreply\.github\.com)$")
CLAUDE_SPUREN = re.compile(r"(?i)co-authored-by:[^\n]*(?:claude|anthropic)|claude-session:|generated with \[?claude")


def _dateien() -> list[Path]:
    try:
        namen = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("kein git-Repository")
    return [ROOT / n for n in namen if Path(n).suffix.lower() not in BINAER and (ROOT / n).is_file()]


def _texte():
    for p in _dateien():
        try:
            yield p.relative_to(ROOT).as_posix(), p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def _offensichtlich_ausgedacht(wert: str) -> bool:
    """Testwerte wie „sk-proj-AbCdEfGh…0123456789“: lange Folgen (abcdefgh, 01234567) oder Wiederholungen."""
    w = wert.lower()
    folgen = ("abcdefgh", "bcdefghi", "ijklmnop", "qrstuvwx", "01234567", "12345678", "xxxxxxxx", "beispiel", "example")
    return any(f in w for f in folgen) or re.search(r"(.)\1{7,}", w) is not None


def _fingerabdruck(begriff: str) -> str:
    return hashlib.sha256(begriff.strip().lower().encode("utf-8")).hexdigest()


def _gesperrt() -> set[str]:
    if not VERBOTEN.exists():
        return set()
    return {z.split()[0] for z in VERBOTEN.read_text(encoding="utf-8").splitlines() if z.strip() and not z.startswith("#")}


def _kandidaten(text: str):
    """Wörter, Rechnernamen und IP-Adressen – bei Rechnernamen auch jede übergeordnete Domain."""
    for m in re.finditer(r"[a-z0-9][a-z0-9._-]{2,}[a-z0-9]", text.lower()):
        t = m.group(0)
        yield t
        teile = t.split(".")
        for i in range(1, len(teile) - 1):
            yield ".".join(teile[i:])


def test_keine_echten_schluessel():
    funde = []
    for name, text in _texte():
        for art, rx in SCHLUESSEL.items():
            for m in re.finditer(rx, text):
                if not _offensichtlich_ausgedacht(m.group(0)):
                    funde.append(f"{name}: {art} „{m.group(0)[:12]}…“")
        if PRIVATER_SCHLUESSEL.search(text):
            funde.append(f"{name}: privater Schlüssel")
    assert not funde, "Echt aussehende Schlüssel im Repository (Testwerte bitte wie „sk-…abcdefgh…“):\n" + "\n".join(funde)


def test_nur_beispiel_adressen():
    funde = [f"{name}: {m.group(0)}" for name, text in _texte() for m in EMAIL.finditer(text)
             if not ERLAUBTE_DOMAINS.search(m.group(1)) and text[max(0, m.start() - 1):m.start()] != ":"]
    # „openai:modell@server“ (Anzeige) und „nutzer:passwort@rechner“ (URLs) sind keine E-Mail-Adressen
    assert not funde, ("Echte E-Mail-Adressen im Repository – bitte example.de / *.example verwenden:\n"
                       + "\n".join(funde))


def test_keine_gesperrten_begriffe():
    gesperrt = _gesperrt()
    funde = []
    for name, text in _texte():
        if name == "tests/fixtures/verboten.sha256":
            continue
        for t in set(_kandidaten(text)):
            if _fingerabdruck(t) in gesperrt:
                funde.append(f"{name}: gesperrter Begriff ({t[:3]}…)")
    assert not funde, "Interne Begriffe (Server, Modelle, IPs) im Repository:\n" + "\n".join(sorted(set(funde)))


def test_letzter_commit_ohne_interna_und_ohne_claude_spuren():
    try:
        nachricht = subprocess.run(["git", "log", "-1", "--format=%B%n%an <%ae>"], cwd=ROOT, capture_output=True,
                                   text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("kein git-Repository")
    assert not CLAUDE_SPUREN.search(nachricht), "Commit-Nachricht enthält Co-Autor-/Werkzeug-Zeilen"
    gesperrt = _gesperrt()
    assert not any(_fingerabdruck(t) in gesperrt for t in _kandidaten(nachricht)), "Commit-Nachricht nennt Interna"
    for m in EMAIL.finditer(nachricht):
        assert ERLAUBTE_DOMAINS.search(m.group(1)), f"Commit mit echter E-Mail-Adresse: {m.group(0)}"


def test_pruefung_selbst():
    """Die Prüfung erkennt, was sie erkennen soll – und lässt Testwerte durch."""
    assert _offensichtlich_ausgedacht("sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789")
    assert not _offensichtlich_ausgedacht("sk-proj-" + hashlib.sha256(b"x").hexdigest()[:40])
    assert "ki.firma.example" in set(_kandidaten("https://ki.firma.example/v1")) and "firma.example" in set(
        _kandidaten("https://ki.firma.example/v1"))
    assert ERLAUBTE_DOMAINS.search("example.de") and not ERLAUBTE_DOMAINS.search("gmail.com")
    assert CLAUDE_SPUREN.search("Co-Authored-By: Claude <noreply@anthropic.example>")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--sperren":
        VERBOTEN.parent.mkdir(parents=True, exist_ok=True)
        neu = _fingerabdruck(sys.argv[2])
        if neu in _gesperrt():
            print("schon gesperrt")
        else:
            with open(VERBOTEN, "a", encoding="utf-8") as f:
                f.write(neu + "\n")
            print("gesperrt (nur der Fingerabdruck steht in tests/fixtures/verboten.sha256)")
    else:
        print(__doc__)
