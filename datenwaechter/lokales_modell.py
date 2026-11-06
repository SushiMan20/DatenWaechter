"""Lokales KI-Modell: findet Namen und Orte, die keine Regel und keine Vornamenliste kennt – auf dem eigenen Rechner.

Einmal laden (Einstellungen → „Lokales KI-Modell“, rund 180 MB), danach läuft es ohne Internet und ohne Server
auf dem Prozessor: ca. 1 Sekunde zum Starten, dann wenige Millisekunden pro Text, rund 300 MB Arbeitsspeicher.

Modell: bert-base-multilingual-cased-ner-hrl von David Adelani (Lizenz AFL-3.0), als ONNX mit 8-Bit-Gewichten
(Xenova). Es erkennt Personen und Orte in Deutsch und neun weiteren Sprachen. Ausgeführt wird es mit onnxruntime und
tokenizers – ohne PyTorch und ohne Python-Pickles: Die Dateien enthalten nur Daten und werden per SHA-256 geprüft.

Gemessen an 63 Arztbriefen (python tests/benchmark_grascco.py --modell): Orte 59 % → 85 %, Namen 97,5 % → 98 %.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Callable

from .detectors import MITTEL, Finding

MODELL = "Xenova/bert-base-multilingual-cased-ner-hrl"
REVISION = "263e82c06569c8c2ac46238a7ae5107598934234"   # fester Stand – die Prüfsummen gehören dazu
DATEIEN = {   # Name auf der Platte: (Pfad im Modell-Repository, Bytes, SHA-256)
    "config.json": ("config.json", 1207, "7aa891abae067f95a40f5e2005b3de44824a083f256802934a993d301ec25076"),
    "tokenizer.json": ("tokenizer.json", 2919362, "bf1b59b7b11c95f194f51708d918eea378e09d05f84c0e1656dc5180e8117088"),
    "model.onnx": ("onnx/model_quantized.onnx", 178495423,
                   "5b65139844be260b624a2a13782b01d122e613d64ce16ed0ba4d82e0b816f1a9"),
}
GROESSE = sum(b for _, b, _ in DATEIEN.values())
QUELLE = os.environ.get("DATENWAECHTER_MODELL_QUELLE", "https://huggingface.co")   # z. B. Firmen-Spiegel
SCHWELLE = float(os.environ.get("DATENWAECHTER_MODELL_SCHWELLE", "0.85"))
HINWEIS = "Modell: bert-base-multilingual-cased-ner-hrl (D. Adelani, AFL-3.0), ONNX-Fassung von Xenova"

_ARTEN = {"PER": ("PERSON", "Name"), "LOC": ("ADRESSE", "Ort")}   # Anzeige ergänzt „(KI)“
_MARKE = "geprueft.json"


class LadeFehler(Exception):
    pass


class Abgebrochen(Exception):
    pass


# --------------------------------------------------------------------------- Ort, Zustand

def ordner() -> Path:
    if os.environ.get("DATENWAECHTER_MODELL_ORDNER"):
        return Path(os.environ["DATENWAECHTER_MODELL_ORDNER"])
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Datenwaechter" / "Modell"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "datenwaechter" / "modell"


def laufzeit() -> bool:
    """Sind onnxruntime und tokenizers installiert (im Windows-Programm immer)?"""
    try:
        import numpy  # noqa: F401
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
        return True
    except ImportError:
        return False


def installiert() -> bool:
    o = ordner()
    try:
        marke = json.loads((o / _MARKE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return marke.get("revision") == REVISION and all(
        (o / n).is_file() and (o / n).stat().st_size == b for n, (_, b, _) in DATEIEN.items())


def bereit() -> bool:
    return installiert() and laufzeit()


def aktiv() -> bool:
    """Geladen und in den Einstellungen eingeschaltet."""
    from .settings import modell_nutzen
    return modell_nutzen() and bereit()


# --------------------------------------------------------------------------- Laden / Entfernen

def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def laden(fortschritt: Callable[[int, int], None] | None = None, abbrechen: threading.Event | None = None) -> Path:
    """Lädt das Modell (setzt abgebrochene Downloads fort) und prüft jede Datei. fortschritt(bytes, gesamt)."""
    ziel = ordner()
    ziel.mkdir(parents=True, exist_ok=True)
    (ziel / _MARKE).unlink(missing_ok=True)
    fertig = 0
    for name, (pfad, groesse, sha) in DATEIEN.items():
        datei = ziel / name
        if datei.is_file() and datei.stat().st_size == groesse and _sha256(datei) == sha:
            fertig += groesse
            continue
        teil = ziel / (name + ".teil")
        vorhanden = teil.stat().st_size if teil.is_file() else 0
        if vorhanden >= groesse:
            teil.unlink()
            vorhanden = 0
        req = urllib.request.Request(f"{QUELLE}/{MODELL}/resolve/{REVISION}/{pfad}",
                                     headers={"User-Agent": "Datenwaechter"})
        if vorhanden:
            req.add_header("Range", f"bytes={vorhanden}-")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if vorhanden and r.status != 206:   # Server kann nicht fortsetzen: von vorn
                    vorhanden = 0
                with open(teil, "ab" if vorhanden else "wb") as f:
                    geladen = vorhanden
                    while True:
                        if abbrechen is not None and abbrechen.is_set():
                            raise Abgebrochen()
                        block = r.read(1 << 18)
                        if not block:
                            break
                        f.write(block)
                        geladen += len(block)
                        if fortschritt:
                            fortschritt(fertig + geladen, GROESSE)
        except OSError as e:
            raise LadeFehler(f"Download fehlgeschlagen: {e}") from e
        if teil.stat().st_size != groesse or _sha256(teil) != sha:
            teil.unlink(missing_ok=True)
            raise LadeFehler(f"{name}: Prüfsumme stimmt nicht – Datei verworfen, bitte noch einmal laden.")
        os.replace(teil, datei)
        fertig += groesse
    (ziel / _MARKE).write_text(json.dumps({"modell": MODELL, "revision": REVISION}), encoding="utf-8")
    _sitzung.cache_clear()
    return ziel


def entfernen() -> None:
    _sitzung.cache_clear()
    shutil.rmtree(ordner(), ignore_errors=True)


# --------------------------------------------------------------------------- Erkennen

_SPERRE = threading.Lock()


@lru_cache(maxsize=1)
def _sitzung():
    import onnxruntime as ort
    from tokenizers import Tokenizer
    o = ordner()
    id2label = {int(k): v for k, v in json.loads((o / "config.json").read_text(encoding="utf-8"))["id2label"].items()}
    tok = Tokenizer.from_file(str(o / "tokenizer.json"))
    tok.no_padding()
    tok.no_truncation()
    opt = ort.SessionOptions()
    opt.intra_op_num_threads = max(1, min(4, os.cpu_count() or 1))
    s = ort.InferenceSession(str(o / "model.onnx"), opt, providers=["CPUExecutionProvider"])
    return s, tok, id2label, {i.name for i in s.get_inputs()}


fehler: str | None = None   # letzter Fehler beim Starten/Ausführen (für die Anzeige)


def vorladen() -> None:
    """Im Hintergrund starten, damit die erste Prüfung nicht wartet."""
    def start():
        global fehler
        try:
            _sitzung()
        except Exception as e:  # noqa: BLE001 – kaputte Datei, fehlende Laufzeit: Regeln laufen trotzdem
            fehler = str(e)
    if aktiv():
        threading.Thread(target=start, daemon=True).start()


def _teile(text: str, n: int = 900):
    pos = 0
    while pos < len(text):
        end = min(len(text), pos + n)
        if end < len(text):
            cut = max(text.rfind("\n", pos + n // 2, end), text.rfind(". ", pos + n // 2, end))
            end = cut + 1 if cut > pos else end
        yield pos, text[pos:end]
        pos = end


def _spannen(text: str) -> list[tuple[str, int, int, float]]:
    """Rohe Treffer des Modells: (PER|LOC|ORG|DATE, Start, Ende, mittlere Sicherheit)."""
    import numpy as np
    sitzung, tok, id2label, eingaben = _sitzung()
    out = []
    stapel = list(_teile(text))
    while stapel:
        off, teil = stapel.pop(0)
        enc = tok.encode(teil)
        if len(enc.ids) > 512:   # zu viele Tokens für das Modell: halbieren
            mitte = teil.rfind(" ", 0, len(teil) // 2) + 1 or len(teil) // 2
            stapel[0:0] = [(off, teil[:mitte]), (off + mitte, teil[mitte:])]
            continue
        feed = {"input_ids": np.array([enc.ids], dtype=np.int64),
                "attention_mask": np.array([enc.attention_mask], dtype=np.int64)}
        if "token_type_ids" in eingaben:
            feed["token_type_ids"] = np.zeros_like(feed["input_ids"])
        logits = sitzung.run(None, feed)[0][0]
        p = np.exp(logits - logits.max(-1, keepdims=True))
        p /= p.sum(-1, keepdims=True)
        cur = None
        for i, ((a, b), wid) in enumerate(zip(enc.offsets, enc.word_ids)):
            if wid is None or a == b:
                continue
            k = int(p[i].argmax())
            lab, sc = id2label[k], float(p[i][k])
            neues_wort = i == 0 or enc.word_ids[i - 1] != wid
            if lab == "O":
                if neues_wort and cur:
                    out.append(cur)
                    cur = None
                continue
            typ = lab[2:] if lab[:2] in ("B-", "I-") else lab
            if cur and cur[0] == typ and not neues_wort:
                cur[2] = b
                cur[3].append(sc)
            elif cur and cur[0] == typ and lab.startswith("I-") and teil[cur[2]:a].strip() in ("", "-"):
                cur[2] = b
                cur[3].append(sc)
            else:
                if cur:
                    out.append(cur)
                cur = [typ, a, b, [sc], off]
        if cur:
            out.append(cur)
    return [(c[0], c[4] + c[1], c[4] + c[2], sum(c[3]) / len(c[3])) for c in out]


_PARTIKEL = {"von", "van", "de", "der", "den", "zu", "am", "an", "im", "bei", "la", "le", "da", "di", "del"}
_EPONYME = {"Babinski", "Babinsky", "Valsalva", "Vasalva", "Lasègue", "Lasegue"}   # „Babinski negativ“
_RAND = " \t\n.,;:()[]\"'„“”‚‘’"


def _plausibel(art: str, wort: str) -> bool:
    """Filtert, was in Arztbriefen und Formularen oft fälschlich als Name/Ort gilt (gemessen an GraSCCo)."""
    from .inhalte import MEDIKAMENTE
    from .namen import ABKUERZUNGEN, KOERPER, STOPP, _NOMEN_ENDUNG
    teile = wort.split()
    if len(wort) < 3 or not teile:
        return False
    medikamente = {m.lower() for m in MEDIKAMENTE}
    for t in teile:
        if t.lower() in _PARTIKEL:
            continue
        if not t[:1].isupper() or "." in t.rstrip(".") or any(c.isdigit() for c in t):
            return False
        if t in STOPP or t in ABKUERZUNGEN or t.lower() in medikamente or t in KOERPER or t in _EPONYME:
            return False
    if art == "PER" and any(t.isupper() and len(t) <= 3 for t in teile):
        return False
    if art == "LOC" and len(teile) == 1 and wort.isupper():   # Überschriften wie „AMBULANZ“
        return False
    if len(teile[-1]) > 6 and _NOMEN_ENDUNG.search(teile[-1]):
        return False
    return True


def erkennen(text: str) -> list[Finding]:
    """Namen und Orte, die das Modell sicher erkennt – als Funde mit Quelle „ki“."""
    global fehler
    if not text.strip():
        return []
    try:
        with _SPERRE:
            roh = _spannen(text)
    except Exception as e:  # noqa: BLE001 – das Modell darf die Prüfung nie verhindern; Regeln laufen weiter
        fehler = str(e)
        return []
    out: list[Finding] = []
    for art, s, e, sicher in roh:
        if art not in _ARTEN or sicher < SCHWELLE:
            continue
        s2, e2 = s, e   # auf ganze Wörter erweitern; war nur ein Wortstück gemeint („Ko“ in „Koloskopie“): weglassen
        while s2 > 0 and (text[s2 - 1].isalnum() or text[s2 - 1] == "-"):
            s2 -= 1
        while e2 < len(text) and (text[e2].isalnum() or text[e2] == "-"):
            e2 += 1
        if (e2 - s2) > (e - s) + 2:
            continue
        while s2 < e2 and text[s2] in _RAND:
            s2 += 1
        while e2 > s2 and text[e2 - 1] in _RAND:
            e2 -= 1
        wort = text[s2:e2]
        if not _plausibel(art, wort) or re.search(r"\n", wort):
            continue
        kind, label = _ARTEN[art]
        out.append(Finding(kind, label, wort, s2, e2, MITTEL, "ki", round(sicher, 3)))
    return out
