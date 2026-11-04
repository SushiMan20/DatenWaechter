from pathlib import Path

import pytest

from datenwaechter import Anonymizer, scan_text
from datenwaechter.detectors import iban_valid, luhn_valid, steuer_id_valid
from datenwaechter.files import extract_text, write_anonymized

BEISPIEL = """Sehr geehrte Frau Müller,
bitte überweisen Sie an DE89 3704 0044 0532 0130 00. Rückfragen an Herrn Dr. Klaus Becker,
klaus.becker@example.de oder +49 30 1234 5678. Adresse: Hauptstraße 12a, 10115 Berlin.
Steuer-ID 86095742719, geb. am 03.04.1985. Karte 4111 1111 1111 1111.
ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789
db: postgres://admin:geheim123@db.intern:5432/kunden
Server 192.168.10.5
"""


def kinds(text):
    return [(f.kind, f.text) for f in scan_text(text)]


def test_prüfsummen():
    assert iban_valid("DE89 3704 0044 0532 0130 00")
    assert not iban_valid("DE89 3704 0044 0532 0130 01")
    assert luhn_valid("4111 1111 1111 1111")
    assert not luhn_valid("4111 1111 1111 1112")
    assert steuer_id_valid("86095742719")
    assert not steuer_id_valid("86095742718")


def test_findet_alles_im_beispiel():
    found = dict((t, k) for k, t in kinds(BEISPIEL))
    assert found["DE89 3704 0044 0532 0130 00"] == "IBAN"
    assert found["Müller"] == "PERSON"
    assert found["Klaus Becker"] == "PERSON"
    assert found["klaus.becker@example.de"] == "EMAIL"
    assert found["+49 30 1234 5678"] == "TELEFON"
    assert found["Hauptstraße 12a"] == "ADRESSE"
    assert found["10115 Berlin"] == "ADRESSE"
    assert found["86095742719"] == "STEUER_ID"
    assert found["03.04.1985"] == "GEBURTSDATUM"
    assert found["4111 1111 1111 1111"] == "KREDITKARTE"
    assert found["postgres://admin:geheim123@db.intern:5432/kunden"] == "ZUGANGSDATEN_URL"
    assert found["192.168.10.5"] == "IP_ADRESSE"
    assert any(k == "API_SCHLUESSEL" and t.startswith("sk-ant-") for k, t in kinds(BEISPIEL))


@pytest.mark.parametrize("harmlos", [
    "Das Meeting ist am 01.02.2024 um 14:30 Uhr.",
    "Wir haben 12345 Euro Umsatz und 40000 Nutzer.",
    "Version 1.2.3 ist stabil, Ticket #123456789.",
    "Die Funktion hat 3 Parameter und gibt 0 zurück.",
])
def test_keine_fehlalarme(harmlos):
    assert scan_text(harmlos) == []


def test_anonymisieren_und_zurück():
    a = Anonymizer()
    text = "Frau Müller schreibt an Frau Müller: IBAN DE89 3704 0044 0532 0130 00"
    anon = a.anonymize(text)
    assert "Müller" not in anon and "DE89" not in anon
    assert anon.count("[PERSON_1]") == 2
    antwort = "Ich habe [PERSON_1] geantwortet, Konto [IBAN_1]."
    assert a.restore(antwort) == "Ich habe Müller geantwortet, Konto DE89 3704 0044 0532 0130 00."


def test_secrets_werden_maskiert_angezeigt():
    f = [x for x in scan_text("token: sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX12") if x.kind == "API_SCHLUESSEL"][0]
    assert "ABCDEFGHIJ" not in f.masked()


def test_dateien(tmp_path: Path):
    src = tmp_path / "brief.txt"
    src.write_text(BEISPIEL, encoding="utf-8")
    out = write_anonymized(src, Anonymizer())
    neu = out.read_text(encoding="utf-8")
    assert out.name == "brief_anonymisiert.txt"
    assert "Becker" not in neu and "[PERSON_" in neu

    import docx
    d = docx.Document()
    d.add_paragraph("Ansprechpartner: Herr Klaus Becker, Tel. 030 12345678")
    d.save(str(tmp_path / "a.docx"))
    out = write_anonymized(tmp_path / "a.docx", Anonymizer())
    assert "Becker" not in extract_text(out) and "[TELEFON_1]" in extract_text(out)
