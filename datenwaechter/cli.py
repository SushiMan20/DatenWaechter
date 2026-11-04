"""Kommandozeile:  datenwaechter scan|anonymisieren|gui|native-host"""

from __future__ import annotations

import argparse
import sys

from .anonymize import Anonymizer
from .detectors import HOCH
from .files import UnsupportedFile, scan_file, write_anonymized


def _scan(args) -> int:
    worst = 0
    for path in args.dateien:
        try:
            _, findings = scan_file(path, use_ki=args.ki)
        except (UnsupportedFile, OSError) as e:
            print(f"{path}: übersprungen – {e}", file=sys.stderr)
            continue
        if not findings:
            print(f"✔ {path}: keine sensiblen Daten gefunden")
            continue
        print(f"⚠ {path}: {len(findings)} Fund(e)")
        for f in findings:
            print(f"   [{f.severity_label:7}] {f.label:30} {f.masked()}")
        worst = max(worst, max(f.severity for f in findings))
    return 2 if worst >= HOCH else (1 if worst else 0)


def _anonymize(args) -> int:
    anon = Anonymizer()
    for path in args.dateien:
        out = write_anonymized(path, anon, out_dir=args.ziel, use_ki=args.ki)
        print(f"→ {out}")
    if args.zuordnung:
        for ph, orig in anon.mapping.items():
            print(f"   {ph} = {orig}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="datenwaechter", description="Sensible Daten vor dem KI-Upload finden.")
    p.add_argument("--ki", action="store_true", help="zusätzlich lokales KI-Modell (GLiNER) nutzen")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("scan", help="Dateien prüfen (Exit-Code 2 = kritische Funde)")
    s.add_argument("dateien", nargs="+")
    s.set_defaults(func=_scan)

    a = sub.add_parser("anonymisieren", help="anonymisierte Kopien erstellen")
    a.add_argument("dateien", nargs="+")
    a.add_argument("--ziel", help="Ausgabeordner (Standard: neben dem Original)")
    a.add_argument("--zuordnung", action="store_true", help="Platzhalter-Zuordnung ausgeben")
    a.set_defaults(func=_anonymize)

    sub.add_parser("gui", help="Wächter-Fenster starten").set_defaults(func=lambda a: _gui())
    sub.add_parser("native-host", help="(intern) Brücke für die Browser-Erweiterung").set_defaults(
        func=lambda a: _native())

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        return _gui()
    return args.func(args)


def _gui() -> int:
    from .gui import main as gui_main
    gui_main()
    return 0


def _native() -> int:
    from .native_host import main as host_main
    host_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
