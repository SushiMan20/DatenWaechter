"""Trefferquote auf der Testsammlung (tests/fixtures/korpus.json) – je Kategorie und je Dokument.

    python tests/korpus_bericht.py          # Bericht
    pytest tests/test_korpus.py             # dieselbe Auswertung als Test
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datenwaechter import content_check  # noqa: E402
from datenwaechter.detectors import scan_text  # noqa: E402
from datenwaechter.settings import SCHWAERZEN_STANDARD  # noqa: E402

KORPUS = json.loads((ROOT / "tests" / "fixtures" / "korpus.json").read_text(encoding="utf-8"))["dokumente"]


def _vorkommen(text: str, teil: str) -> list[tuple[int, int]]:
    out, i = [], text.find(teil)
    while i != -1:
        out.append((i, i + len(teil)))
        i = text.find(teil, i + 1)
    return out


def _abgedeckt(spannen, s: int, e: int) -> bool:
    return all(any(a <= i < b for a, b in spannen) for i in range(s, e) if not "\n".isspace() or True)


def auswerten(doc: dict) -> dict:
    gruppen = {**SCHWAERZEN_STANDARD, **doc.get("gruppen", {})}
    text = doc["text"]
    funde = scan_text(text, gruppen=gruppen)
    spannen = [(f.start, f.end) for f in funde]
    ergebnis = {"gefunden": {}, "verpasst": {}, "zu_viel": [], "thema": None}
    for art, teile in doc.get("finden", {}).items():
        for teil in teile:
            orte = _vorkommen(text, teil)
            assert orte, f"{doc['name']}: „{teil}“ steht nicht im Text"
            ok = all(_abgedeckt(spannen, s, e) for s, e in orte)
            ergebnis["gefunden" if ok else "verpasst"].setdefault(art, []).append(teil)
    for teil in doc.get("stehen", []):
        for s, e in _vorkommen(text, teil):
            if any(a < e and s < b for a, b in spannen):
                ergebnis["zu_viel"].append(teil)
                break
    if "thema" in doc:
        v = content_check.nur_mit_personenbezug(content_check.keyword_check(text), funde,
                                                aktiv=gruppen["themen_nur_mit_person"])
        ergebnis["thema"] = (bool(v.warning) == doc["thema"], v.warning)
    return ergebnis


def bericht() -> tuple[dict, list]:
    je_art: dict[str, list[int]] = {}
    probleme = []
    for doc in KORPUS:
        r = auswerten(doc)
        for art, teile in r["gefunden"].items():
            je_art.setdefault(art, [0, 0])[0] += len(teile)
            je_art[art][1] += len(teile)
        for art, teile in r["verpasst"].items():
            je_art.setdefault(art, [0, 0])[1] += len(teile)
            probleme.append(f"{doc['name']}: {art} verpasst: {teile}")
        if r["zu_viel"]:
            probleme.append(f"{doc['name']}: fälschlich markiert: {r['zu_viel']}")
        if r["thema"] is not None and not r["thema"][0]:
            probleme.append(f"{doc['name']}: Themen-Warnung falsch: {r['thema'][1]!r}")
    return je_art, probleme


if __name__ == "__main__":
    je_art, probleme = bericht()
    gesamt = [sum(v[0] for v in je_art.values()), sum(v[1] for v in je_art.values())]
    print(f"Testsammlung: {len(KORPUS)} Dokumente\n")
    for art, (ok, alle) in sorted(je_art.items()):
        print(f"  {art:<13} {ok:>3}/{alle:<3} {100 * ok / alle:5.1f} %")
    print(f"  {'GESAMT':<13} {gesamt[0]:>3}/{gesamt[1]:<3} {100 * gesamt[0] / gesamt[1]:5.1f} %\n")
    print("\n".join(probleme) if probleme else "Keine Probleme.")
