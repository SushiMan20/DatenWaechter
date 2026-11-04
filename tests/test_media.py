"""Bilder, Scans, Schwärzen, Gesichter, Inhalts-Check und Browser-Brücke."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from datenwaechter import Anonymizer, content_check, faces, ocr
from datenwaechter.analysis import analyze, anonymize
from datenwaechter.files import load

ROOT = Path(__file__).resolve().parent.parent
needs_ocr = pytest.mark.skipif(ocr.backend() is None, reason="keine Texterkennung installiert")


def _text_image(path: Path, lines):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 22)
    except OSError:
        font = ImageFont.truetype("arial.ttf", 22)
    img = Image.new("RGB", (900, 60 + 50 * len(lines)), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((30, 30 + 50 * i), line, font=font, fill="black")
    img.save(path)
    return path


BILD = ["Überweisung an Frau Anna Müller", "IBAN: DE89 3704 0044 0532 0130 00", "Betreff: Unterhalt für unsere Tochter"]


# --------------------------------------------------------------------------- Inhalts-Check

def test_stichworte_familie_und_gesundheit():
    v = content_check.keyword_check("Arztbrief: Diagnose Depression. Kopie an meinen Ehemann wegen Sorgerecht.")
    assert "Gesundheitsdaten" in v.categories and "Familienunterlagen" in v.categories
    assert v.severity == 3 and v.warning.startswith("Du lädst gerade")


@pytest.mark.parametrize("harmlos", [
    "Kannst du diese Python-Funktion optimieren? Sie sortiert eine Liste von Zahlen.",
    "Fehlerdiagnose im Build-Prozess: Version 3.1 schlägt bei den Unit-Tests fehl.",
    "Wie mache ich ein Rezept für Apfelkuchen ohne Zucker?",
])
def test_stichworte_keine_fehlalarme(harmlos):
    assert content_check.keyword_check(harmlos).warning is None


def test_browser_kategorien_sind_aktuell():
    js = (ROOT / "extension" / "kategorien.js").read_text(encoding="utf-8")
    data = json.loads(js.split("globalThis.DWKategorien = ", 1)[1].rstrip().rstrip(";"))
    assert data == json.loads((ROOT / "datenwaechter" / "kategorien.json").read_text(encoding="utf-8")), \
        "extension/kategorien.js neu erzeugen: content_check.write_extension_categories()"


@pytest.fixture
def fake_ollama(monkeypatch):
    """Simuliert einen lokalen Ollama-Server mit festgelegter Antwort."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._json({"models": [{"name": "gemma3:4b"}]})

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(req)
            answer = {"kategorien": ["kinder", "personenfoto"], "beschreibung": "Foto eines Kindes am Strand.",
                      "warnung": "Du lädst gerade ein Foto deines Kindes hoch.", "stufe": 3}
            self._json({"response": json.dumps(answer)})

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(content_check, "OLLAMA_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(content_check, "_status_cache", None)
    yield calls
    srv.shutdown()


def test_sprachmodell_ueber_ollama(fake_ollama):
    from PIL import Image
    assert content_check.ollama_available()
    v = content_check.check("", image=Image.new("RGB", (64, 64), "white"), name="IMG_2041.jpg")
    assert v.backend == "ollama:gemma3:4b"
    assert v.warning == "Du lädst gerade ein Foto deines Kindes hoch."
    assert v.description == "Foto eines Kindes am Strand."
    assert "Daten über Kinder" in v.categories and v.severity == 3
    assert fake_ollama[0]["images"], "Bild muss ans Modell gehen"
    assert fake_ollama[0]["format"] == "json"


def test_ohne_ollama_nur_stichworte(monkeypatch):
    monkeypatch.setattr(content_check, "OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(content_check, "_status_cache", None)
    assert content_check.check("Sorgerecht für die Kinder").backend == "stichworte"


# --------------------------------------------------------------------------- Bilder, Scans, PDFs

@needs_ocr
def test_bild_mit_text_wird_erkannt_und_geschwaerzt(tmp_path):
    r = analyze(_text_image(tmp_path / "foto.png", BILD), use_llm=False)
    kinds = {row["kind"] for row in r.rows()}
    assert {"PERSON", "IBAN"} <= kinds
    assert "Familienunterlagen" in r.verdict.categories
    out = anonymize(r, Anonymizer(), tmp_path / "aus")
    assert out.name == "foto_anonymisiert.png"
    text = load(out).text
    assert "Müller" not in text and "3704" not in text and "Überweisung" in text


@needs_ocr
def test_eingescanntes_pdf(tmp_path):
    from PIL import Image
    img = Image.open(_text_image(tmp_path / "s.png", BILD))
    img.save(tmp_path / "scan.pdf", "PDF", resolution=100)
    r = analyze(tmp_path / "scan.pdf", use_llm=False)
    assert any(row["kind"] == "IBAN" for row in r.rows())
    out = anonymize(r, Anonymizer(), tmp_path / "aus")
    assert out.suffix == ".pdf" and "3704" not in load(out).text


def test_text_pdf_wird_geschwaerzt(tmp_path):
    pytest.importorskip("pypdfium2")
    reportlab = pytest.importorskip("reportlab.pdfgen.canvas")
    c = reportlab.Canvas(str(tmp_path / "v.pdf"))
    c.drawString(72, 750, "Vertrag mit Herrn Klaus Becker, IBAN DE89 3704 0044 0532 0130 00")
    c.save()
    r = analyze(tmp_path / "v.pdf", use_llm=False)
    out = anonymize(r, Anonymizer(), tmp_path / "aus")
    import pypdfium2 as pdfium
    assert out.name == "v_anonymisiert.pdf"
    assert pdfium.PdfDocument(str(out))[0].get_textpage().get_text_range().strip() == "", \
        "geschwärztes PDF darf keinen Originaltext mehr enthalten"


@pytest.mark.skipif(not faces.available(), reason="OpenCV 4 nicht installiert")
def test_gesicht_wird_erkannt_und_verpixelt(tmp_path):
    from PIL import Image
    r = analyze(ROOT / "tests" / "fixtures" / "gesicht.jpg", use_llm=False)
    assert len(r.faces) == 1 and r.can_anonymize
    out = anonymize(r, Anonymizer(), tmp_path)
    assert faces.detect(Image.open(out)) == []


# --------------------------------------------------------------------------- Browser-Brücke

@needs_ocr
def test_native_host_liefert_geschwaerztes_bild(tmp_path):
    from datenwaechter.native_host import handle
    b64 = base64.b64encode(_text_image(tmp_path / "x.png", BILD).read_bytes()).decode()
    reply = handle({"action": "scan_file", "name": "x.png", "data_b64": b64, "mapping": {"[PERSON_4]": "Anna Müller"}})
    assert reply["ok"] and reply["output"]["mime"] == "image/png"
    assert reply["mapping"]["[PERSON_4]"] == "Anna Müller", "bestehende Platzhalter aus dem Browser weiterverwenden"
    assert reply["content"]["warning"]


def test_anonymizer_uebernimmt_zuordnung():
    a = Anonymizer()
    a.load({"[PERSON_2]": "Müller", "kaputt": "x"})
    assert a.anonymize("Frau Müller und Frau Schmidt") == "Frau [PERSON_2] und Frau [PERSON_3]"
