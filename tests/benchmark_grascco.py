"""Messung auf echten Forschungsdaten: GraSCCo (Graz Synthetic Clinical text Corpus) mit PII-Annotationen.

63 deutsche Arztbriefe mit erfundenen Daten; Fachleute haben jede personenbezogene Stelle markiert.
Quelle: Lohr et al., GraSCCo_PII_V2, Zenodo https://zenodo.org/records/15747389 – Lizenz CC BY 4.0.
Die Daten werden nur heruntergeladen, nicht im Repository gespeichert.

    python tests/benchmark_grascco.py              # Trefferquote je Kategorie + Beispiele für Verpasstes
    python tests/benchmark_grascco.py --alle       # alle verpassten Stellen anzeigen
    python tests/benchmark_grascco.py --modell     # mit lokalem KI-Modell (muss geladen sein)
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datenwaechter.detectors import scan_text  # noqa: E402

URL = "https://zenodo.org/api/records/15747389/files/grascco_pii_2_json.zip/content"
CACHE = Path(os.environ.get("DATENWAECHTER_BENCHMARK", Path.home() / ".cache" / "datenwaechter-benchmark")) / "grascco"

# GraSCCo-Kategorie -> unsere Kategorie (None = für den Datenwächter bewusst kein Fund, z. B. Aufnahmedatum, „Dr. med.“)
KATEGORIEN = {
    "NAME_PATIENT": "Name", "NAME_DOCTOR": "Name", "NAME_RELATIVE": "Name", "NAME_EXT": "Name",
    "DATE_BIRTH": "Geburtsdatum", "ID": "Kennnummer",
    "LOCATION_STREET": "Adresse", "LOCATION_ZIP": "Adresse", "LOCATION_CITY": "Ort",
    "CONTACT_PHONE": "Kontakt", "CONTACT_FAX": "Kontakt", "CONTACT_EMAIL": "Kontakt",
    "LOCATION_HOSPITAL": "Klinik/Organisation", "LOCATION_ORGANIZATION": "Klinik/Organisation",
    "DATE": None, "NAME_TITLE": None, "AGE": None, "PROFESSION": None, "LOCATION_COUNTRY": None, "NAME_USERNAME": None,
}


STATION = __import__("re").compile(r"(?i)(?:station|zi\.?|zimmer|op|ambulanz|aufenthalte auf|zuvor auf|zertifiziert nach|"
                                   r"sozialtherapie|intensiv)[:\s]*$")


def laden() -> list[dict]:
    ordner = CACHE / "json"
    if not ordner.exists():
        print(f"Lade GraSCCo (CC BY 4.0) nach {CACHE} …", file=sys.stderr)
        daten = urllib.request.urlopen(URL, timeout=120).read()
        zipfile.ZipFile(io.BytesIO(daten)).extractall(ordner)
    docs = []
    for p in sorted(ordner.rglob("*.json")):
        fs = json.loads(p.read_text(encoding="utf-8"))["%FEATURE_STRUCTURES"]
        text = next(f for f in fs if f.get("%TYPE") == "uima.cas.Sofa")["sofaString"]
        anno = [(f["kind"], f["begin"], f["end"]) for f in fs if f.get("%TYPE") == "webanno.custom.PHI"]
        docs.append({"name": p.name.split(".")[0], "text": text, "anno": anno})
    return docs


def messen(docs: list[dict], gruppen: dict, modell: bool = False) -> tuple[dict, dict, collections.Counter, list]:
    treffer = collections.defaultdict(lambda: [0, 0])
    verpasst = collections.defaultdict(list)
    fremd = collections.Counter()
    fremd_bsp = []
    for d in docs:
        text = d["text"]
        funde = scan_text(text, gruppen=gruppen, modell=modell)
        for kind, b, e in d["anno"]:
            art = KATEGORIEN.get(kind)
            if kind == "ID" and STATION.search(text[max(0, b - 30):b]):
                art = "Station/Zimmer"   # Station, Zimmer, OP-Saal: Ort im Haus, keine Kennung der Person
            if art is None or e <= b:
                continue
            gedeckt = sum(1 for i in range(b, e) if not text[i].isspace() and any(f.start <= i < f.end for f in funde))
            zeichen = sum(1 for i in range(b, e) if not text[i].isspace())
            ok = zeichen and gedeckt / zeichen >= 0.8
            treffer[art][0] += bool(ok)
            treffer[art][1] += 1
            if not ok:
                verpasst[art].append((d["name"], text[b:e], text[max(0, b - 40):b].replace("\n", " ")))
        for f in funde:   # Funde ohne passende Annotation (mögliche Fehlalarme)
            if not any(b < f.end and f.start < e for _k, b, e in d["anno"]):
                fremd[f.kind] += 1
                if len(fremd_bsp) < 40:
                    fremd_bsp.append((d["name"], f.kind, f.text))
    return treffer, verpasst, fremd, fremd_bsp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alle", action="store_true")
    ap.add_argument("--modell", action="store_true", help="lokales KI-Modell dazunehmen")
    args = ap.parse_args()
    if args.modell:
        from datenwaechter import lokales_modell
        if not lokales_modell.bereit():
            sys.exit("Lokales KI-Modell fehlt: in den Einstellungen laden oder python -m datenwaechter modell laden")
    docs = laden()
    gruppen = {"firmen": True, "betraege": False, "medizin": False}
    treffer, verpasst, fremd, fremd_bsp = messen(docs, gruppen, args.modell)
    print(f"GraSCCo: {len(docs)} Arztbriefe, {sum(len(d['anno']) for d in docs)} annotierte Stellen\n")
    alle = [0, 0]
    for art, (ok, n) in sorted(treffer.items()):
        print(f"  {art:<20} {ok:>4}/{n:<4} {100 * ok / n:5.1f} %")
        if art not in ("Ort", "Klinik/Organisation", "Station/Zimmer"):
            alle[0] += ok
            alle[1] += n
    print(f"  {'Kern (ohne Ort/Klinik/Station)':<20} {alle[0]:>4}/{alle[1]:<4} {100 * alle[0] / alle[1]:5.1f} %\n")
    for art, liste in verpasst.items():
        print(f"Verpasst – {art} ({len(liste)}):")
        for name, wert, davor in (liste if args.alle else liste[:8]):
            print(f"   {name:<12} „{wert}“   … {davor[-35:]}")
    print(f"\nFunde ohne Annotation (mögliche Fehlalarme): {dict(fremd)}")
    for name, kind, wert in fremd_bsp[:20]:
        print(f"   {name:<12} {kind:<14} „{wert}“")


if __name__ == "__main__":
    main()
