"""Namen und Geburtsdaten ohne KI – dieselben Beispiele prüft tests/detectors.test.js für Browser und Handy."""

import json
from pathlib import Path

import pytest

from datenwaechter import Anonymizer, scan_text
from datenwaechter import namen

ROOT = Path(__file__).resolve().parent.parent
BEISPIELE = json.loads((ROOT / "tests" / "fixtures" / "namen.json").read_text(encoding="utf-8"))["beispiele"]


@pytest.mark.parametrize("b", BEISPIELE, ids=[b["text"][:40] for b in BEISPIELE])
def test_beispiele(b):
    found = scan_text(b["text"])
    assert [f.text for f in found if f.kind == "PERSON"] == b.get("personen", [])
    assert [f.text for f in found if f.kind == "GEBURTSDATUM"] == b.get("daten", [])


def test_browser_namen_sind_aktuell():
    js = (ROOT / "extension" / "vornamen.js").read_text(encoding="utf-8")
    data = json.loads(js.split("globalThis.DWVornamen = ", 1)[1].rstrip().rstrip(";"))
    assert data == namen.extension_data(), "extension/vornamen.js neu erzeugen: namen.write_extension_names()"


def test_vorname_allein_bekommt_platzhalter_der_person():
    a = Anonymizer()
    out = a.anonymize("Mia Schneider ist 7. Mia geht in die Kita, Thomas Schneider zahlt. Schneider ist einverstanden.")
    assert out == "[PERSON_1] ist 7. [PERSON_1] geht in die Kita, [PERSON_2] zahlt. [PERSON_3] ist einverstanden."


def test_liste_ohne_doppelte_und_gueltig():
    sicher, mehrdeutig = namen.lexikon()
    assert len(sicher) > 1200 and not sicher & mehrdeutig
    assert {"Claude", "Ernst", "August", "Rose"} <= mehrdeutig, "mehrdeutige Wörter nie allein als Name"
