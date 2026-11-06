"""Lokales KI-Modell: Laden (Prüfsumme, Fortsetzen, Abbrechen), Auswerten der Modell-Ausgabe, Einbindung."""

from __future__ import annotations

import hashlib
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from datenwaechter import lokales_modell as lm
from datenwaechter import settings
from datenwaechter.detectors import scan_text

np = pytest.importorskip("numpy")


@pytest.fixture(autouse=True)
def frische_sitzung():
    lm._sitzung.cache_clear()
    yield
    getattr(lm._sitzung, "cache_clear", lambda: None)()   # im Test evtl. durch ein Ersatzmodell ersetzt


# --------------------------------------------------------------------------- Laden

@pytest.fixture
def server(monkeypatch):
    """Liefert drei kleine „Modelldateien“ aus, kann Range (Fortsetzen) und zählt Anfragen."""
    inhalte = {"config.json": b'{"id2label": {"0": "O"}}', "tokenizer.json": b"{}" * 50, "onnx/model.onnx": os.urandom(300_000)}
    state = {"inhalte": inhalte, "ranges": [], "kaputt": False}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            pfad = self.path.split(f"/resolve/{lm.REVISION}/", 1)[1]
            daten = state["inhalte"][pfad]
            if state["kaputt"]:
                daten = b"x" * len(daten)
            rng = self.headers.get("Range")
            if rng:
                state["ranges"].append(rng)
                ab = int(re.match(r"bytes=(\d+)-", rng).group(1))
                self.send_response(206)
                daten = daten[ab:]
            else:
                self.send_response(200)
            self.send_header("Content-Length", str(len(daten)))
            self.end_headers()
            self.wfile.write(daten)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(lm, "QUELLE", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(lm, "DATEIEN", {
        "config.json": ("config.json", len(inhalte["config.json"]), hashlib.sha256(inhalte["config.json"]).hexdigest()),
        "tokenizer.json": ("tokenizer.json", len(inhalte["tokenizer.json"]), hashlib.sha256(inhalte["tokenizer.json"]).hexdigest()),
        "model.onnx": ("onnx/model.onnx", len(inhalte["onnx/model.onnx"]), hashlib.sha256(inhalte["onnx/model.onnx"]).hexdigest()),
    })
    monkeypatch.setattr(lm, "GROESSE", sum(len(v) for v in inhalte.values()))
    yield state
    srv.shutdown()


def test_laden_prueft_und_setzt_fort(server):
    assert not lm.installiert() and not lm.aktiv()
    o = lm.ordner()
    o.mkdir(parents=True)
    (o / "model.onnx.teil").write_bytes(server["inhalte"]["onnx/model.onnx"][:100_000])   # abgebrochener Download
    stand = []
    lm.laden(lambda n, gesamt: stand.append((n, gesamt)))
    assert lm.installiert()
    assert server["ranges"] == ["bytes=100000-"], "nur der Rest wird geladen"
    assert stand[-1] == (lm.GROESSE, lm.GROESSE) and all(a[0] <= b[0] for a, b in zip(stand, stand[1:]))
    assert (o / "model.onnx").read_bytes() == server["inhalte"]["onnx/model.onnx"]
    assert not list(o.glob("*.teil"))
    lm.entfernen()
    assert not lm.installiert() and not o.exists()


def test_falsche_pruefsumme_wird_verworfen(server):
    server["kaputt"] = True
    with pytest.raises(lm.LadeFehler, match="Prüfsumme"):
        lm.laden()
    assert not lm.installiert()
    assert not list(lm.ordner().glob("*.teil")), "kaputte Datei bleibt nicht liegen"


def test_abbrechen(server):
    halt = threading.Event()
    halt.set()
    with pytest.raises(lm.Abgebrochen):
        lm.laden(abbrechen=halt)
    assert not lm.installiert()


def test_anderer_stand_gilt_nicht_als_geladen(server, monkeypatch):
    lm.laden()
    assert lm.installiert()
    monkeypatch.setattr(lm, "REVISION", "0" * 40)
    assert not lm.installiert(), "neue Modellversion muss neu geladen werden"


# --------------------------------------------------------------------------- Auswerten (Ersatzmodell)

class _Kodierung:
    def __init__(self, text):
        self.ids, self.offsets, self.word_ids, self.woerter = [101], [(0, 0)], [None], []
        for w, m in enumerate(re.finditer(r"\w+|[^\w\s]", text)):
            a, b = m.span()
            teile = [(a, a + 2), (a + 2, b)] if text[a:b] == "Koloskopie" else [(a, b)]   # zwei Wortstücke
            for s, e in teile:
                self.ids.append(1)
                self.offsets.append((s, e))
                self.word_ids.append(w)
                self.woerter.append(text[s:e])
        self.ids.append(102)
        self.offsets.append((0, 0))
        self.word_ids.append(None)
        self.attention_mask = [1] * len(self.ids)


LABELS = {0: "O", 1: "B-PER", 2: "I-PER", 3: "B-LOC", 4: "I-LOC"}


class _Ersatz:
    """Tut so, als wäre es das Modell: bekannte Wortstücke bekommen ein Label."""
    def __init__(self, karte):
        self.karte, self.letzte = karte, None

    def encode(self, text):
        self.letzte = _Kodierung(text)
        return self.letzte

    def run(self, _namen, feed):
        enc = self.letzte
        logits = np.zeros((1, len(enc.ids), len(LABELS)), dtype=np.float32)
        stuecke = [None] + enc.woerter + [None]
        for i, w in enumerate(stuecke):
            label, sicher = self.karte.get(w, ("O", 9.0))
            logits[0, i, [k for k, v in LABELS.items() if v == label][0]] = sicher
        return [logits]


def _ersatz(monkeypatch, karte):
    e = _Ersatz(karte)
    monkeypatch.setattr(lm, "_sitzung", lambda: (e, e, LABELS, {"input_ids", "attention_mask"}))
    return e


def test_namen_und_orte_aus_modell(monkeypatch):
    _ersatz(monkeypatch, {
        "Wenzeslaus": ("B-PER", 9), "Brummer": ("I-PER", 9), "Pirna": ("B-LOC", 9),
        "Leber": ("B-PER", 9),                 # Organ, kein Name
        "Ko": ("B-PER", 9),                    # nur ein Wortstück von „Koloskopie“
        "Unsicher": ("B-PER", 0.4),            # zu unsicher
        "AMBULANZ": ("B-LOC", 9),              # Überschrift
    })
    text = "Gestern rief Wenzeslaus Brummer aus Pirna an. Die Leber ist frei. Koloskopie folgt. Unsicher. AMBULANZ"
    funde = {(f.kind, f.text, f.label) for f in lm.erkennen(text)}
    assert funde == {("PERSON", "Wenzeslaus Brummer", "Name"), ("ADRESSE", "Pirna", "Ort")}


def test_lange_texte_werden_aufgeteilt(monkeypatch):
    _ersatz(monkeypatch, {"Brummer": ("B-PER", 9)})
    text = ("a, " * 1000) + "Am Ende kommt Brummer."   # > 512 Tokens je Abschnitt: wird halbiert
    funde = lm.erkennen(text)
    assert [(f.text, text[f.start:f.end]) for f in funde] == [("Brummer", "Brummer")]


# --------------------------------------------------------------------------- Einbindung

def _als_geladen(monkeypatch):
    o = lm.ordner()
    o.mkdir(parents=True, exist_ok=True)
    for name, (_, groesse, _) in lm.DATEIEN.items():
        with open(o / name, "wb") as f:
            f.truncate(groesse)
    (o / lm._MARKE).write_text(f'{{"revision": "{lm.REVISION}"}}', encoding="utf-8")
    monkeypatch.setattr(lm, "laufzeit", lambda: True)
    monkeypatch.setattr(lm, "erkennen", lambda text: [lm.Finding("PERSON", "Name", "Brummer",
                                                                   text.index("Brummer"), text.index("Brummer") + 7, 2, "ki")])


def test_scan_text_nutzt_modell_wenn_geladen_und_eingeschaltet(monkeypatch):
    text = "Rückruf an Brummer, er kommt morgen. Brummer bringt die Unterlagen."
    assert not any(f.text == "Brummer" for f in scan_text(text))
    _als_geladen(monkeypatch)
    assert lm.aktiv()
    funde = [f for f in scan_text(text) if f.text == "Brummer"]
    assert len(funde) == 2, "weitere Nennungen des Namens werden mitgefunden"
    assert not any(f.text == "Brummer" for f in scan_text(text, modell=False))
    settings.modell_nutzen_speichern(False)
    assert not lm.aktiv() and not any(f.text == "Brummer" for f in scan_text(text))
    settings.modell_nutzen_speichern(True)
    assert lm.aktiv()


def test_kaputtes_modell_verhindert_keine_pruefung(monkeypatch):
    echtes_erkennen = lm.erkennen
    _als_geladen(monkeypatch)
    monkeypatch.setattr(lm, "erkennen", echtes_erkennen)
    monkeypatch.setattr(lm, "_sitzung", lambda: (_ for _ in ()).throw(RuntimeError("Datei kaputt")))
    funde = scan_text("IBAN DE89 3704 0044 0532 0130 00, Herr Brummer")
    assert {f.kind for f in funde} == {"IBAN", "PERSON"}, "Regeln laufen weiter"
    assert lm.fehler == "Datei kaputt"


def test_cli_status(capsys):
    from datenwaechter.cli import main
    assert main(["modell"]) == 0
    assert "nicht geladen" in capsys.readouterr().out


# --------------------------------------------------------------------------- Echtes Modell (wenn vorhanden)

ECHT = os.environ.get("DATENWAECHTER_TEST_MODELL")


@pytest.mark.skipif(not ECHT or not lm.laufzeit(), reason="echtes Modell nicht geladen (DATENWAECHTER_TEST_MODELL)")
def test_echtes_modell_findet_seltene_namen(monkeypatch):
    monkeypatch.setenv("DATENWAECHTER_MODELL_ORDNER", str(Path(ECHT)))
    assert lm.aktiv()
    text = ("Gestern hat Wenzeslaus Brummer aus Klagenfurt angerufen. Er wohnt jetzt bei Kowalczyk in Pirna. "
            "Die Leber ist unauffällig, Therapie mit Xalacom.")
    funde = {(f.kind, f.text) for f in scan_text(text, gruppen={"firmen": True})}
    assert {("PERSON", "Wenzeslaus Brummer"), ("PERSON", "Kowalczyk"), ("ADRESSE", "Klagenfurt"), ("ADRESSE", "Pirna")} <= funde
    assert not any(t in ("Leber", "Xalacom") for _, t in funde)
