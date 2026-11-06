"""Python (Windows-App) und JavaScript (Browser-Erweiterung, Handy-App) müssen genau dasselbe finden.

Prüft alle Texte aus tests/fixtures (und, falls heruntergeladen, die GraSCCo-Arztbriefe aus benchmark_grascco.py).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from datenwaechter.detectors import scan_text

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"

JS = """
const DW = require(process.argv[1]);
let input = "";
process.stdin.on("data", (c) => (input += c)).on("end", () => {
  const { texte, gruppen } = JSON.parse(input);
  const out = texte.map((t) => DW.scan(t, { ...gruppen, themen_nur_mit_person: true }).map((f) => [f.kind, f.start, f.end]));
  process.stdout.write(JSON.stringify(out));
});
"""


def _texte() -> list[str]:
    texte = [b["text"] for b in json.loads((FIX / "namen.json").read_text(encoding="utf-8"))["beispiele"]]
    texte += [d["text"] for d in json.loads((FIX / "korpus.json").read_text(encoding="utf-8"))["dokumente"]]
    try:
        from benchmark_grascco import CACHE, laden
        if (CACHE / "json").exists():
            texte += [d["text"] for d in laden()]
    except Exception:
        pass
    return texte


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js fehlt")
@pytest.mark.parametrize("gruppen", [{"firmen": True, "betraege": False, "medizin": False},
                                     {"firmen": True, "betraege": True, "medizin": True}])
def test_python_und_javascript_finden_dasselbe(gruppen):
    texte = _texte()
    lauf = subprocess.run(["node", "-e", JS, str(ROOT / "extension" / "detectors.js")],
                          input=json.dumps({"texte": texte, "gruppen": gruppen}), capture_output=True,
                          text=True, encoding="utf-8", check=True, timeout=120)
    js = json.loads(lauf.stdout)
    unterschiede = []
    for text, js_funde in zip(texte, js):
        py = {(f.kind, f.start, f.end) for f in scan_text(text, gruppen=gruppen)}
        jsm = {tuple(x) for x in js_funde}
        for kind, s, e in sorted(py ^ jsm):
            seite = "nur Python" if (kind, s, e) in py else "nur JS"
            unterschiede.append(f"{seite}: {kind} „{text[s:e]}“ … {text[max(0, s - 30):s]!r}")
    assert not unterschiede, "\n".join(unterschiede[:30])
