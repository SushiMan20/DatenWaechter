"""Testsammlung (tests/fixtures/korpus.json): Jedes Dokument muss vollständig erkannt werden – ohne Fehlalarme.
Bericht mit Trefferquote je Kategorie: python tests/korpus_bericht.py"""

import pytest

from korpus_bericht import KORPUS, auswerten


@pytest.mark.parametrize("doc", KORPUS, ids=[d["name"] for d in KORPUS])
def test_dokument(doc):
    r = auswerten(doc)
    assert not r["verpasst"], f"verpasst: {r['verpasst']}"
    assert not r["zu_viel"], f"fälschlich markiert: {r['zu_viel']}"
    if r["thema"] is not None:
        assert r["thema"][0], f"Themen-Warnung: {r['thema'][1]!r}"
