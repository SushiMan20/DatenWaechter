"""Kommandozeile:  datenwaechter scan|anonymisieren|gui|native-host"""

from __future__ import annotations

import argparse
import sys

from .analysis import analyze, anonymize
from .anonymize import Anonymizer
from .detectors import HOCH, SEVERITY_LABEL
from .files import UnsupportedFile


def _llm(args):
    return False if args.kein_sprachmodell else "auto"


def _scan(args) -> int:
    worst = 0
    for path in args.dateien:
        try:
            r = analyze(path, use_ki=args.ki, use_llm=_llm(args))
        except (UnsupportedFile, OSError) as e:
            print(f"{path}: übersprungen – {e}", file=sys.stderr)
            continue
        print(("⚠ " if r.needs_attention else "✔ ") + f"{path}")
        if r.verdict.warning:
            print(f"   Inhalt: {r.verdict.warning}" + (f"  [{r.verdict.backend}]" if r.verdict.backend != "stichworte" else ""))
        if r.verdict.description:
            print(f"   Beschreibung: {r.verdict.description}")
        for row in r.rows():
            print(f"   [{SEVERITY_LABEL[row['severity']]:7}] {row['label']:30} {row['display']}")
        for note in r.doc.notes + r.info:
            print(f"   Hinweis: {note}")
        if not r.needs_attention:
            print("   keine sensiblen Daten gefunden")
        worst = max(worst, r.severity)
    return 2 if worst >= HOCH else (1 if worst else 0)


def _anonymize(args) -> int:
    anon = Anonymizer()
    for path in args.dateien:
        out = anonymize(analyze(path, use_ki=args.ki, use_llm=False), anon, out_dir=args.ziel)
        print(f"→ {out}")
    if args.zuordnung:
        for ph, orig in anon.mapping.items():
            print(f"   {ph} = {orig}")
    return 0


def _ki_server(args) -> int:
    from . import llm, settings
    s = settings.load_llm()
    changed = False
    tri = {"ja": True, "nein": False, "auto": None}
    if args.art:
        s.typ, changed = args.art, True
    if args.url is not None:
        s.url, changed = args.url, True
        if s.typ in ("auto", "ollama") and args.url and not args.art:
            s.typ = "openai"
    if args.token is not None:
        s.token = sys.stdin.readline().strip() if args.token == "-" else args.token
        changed = True
    if args.modell is not None:
        s.modell, changed = args.modell, True
    if args.bilder:
        s.bilder_senden, changed = tri[args.bilder], True
    if args.anonymisieren:
        s.anonymisieren, changed = tri[args.anonymisieren], True
    if changed:
        print(f"✔ Gespeichert: {settings.save_llm(s)}")
    print(f"Art:            {s.typ}")
    print(f"URL:            {s.base_url or '(keine)'}" + ("  ⚠ extern" if s.url and s.extern else ""))
    print(f"Token:          {settings.masked_token(s.token)}")
    print(f"Modell:         {s.modell or '(automatisch)'}")
    print(f"Bilder senden:  {'ja' if s.send_images else 'nein'}")
    print(f"Anonymisieren:  {'ja' if s.anonymize_first else 'nein'} (vor dem Senden)")
    if args.testen:
        ok, msg = llm.test_connection(s)
        print(msg)
        return 0 if ok else 1
    return 0


def _aktion(args) -> int:
    from . import actions, llm
    text = args.text if args.text is not None else sys.stdin.read()
    try:
        r = actions.run(args.name, text)
    except llm.LlmError as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 1
    print(r.text)
    if r.sent_to:
        print(f"(an {r.sent_to} gesendet{', vorher anonymisiert' if r.anonymized else ''})", file=sys.stderr)
    return 0


def _aktionen(args) -> int:
    from . import actions
    liste = actions.load()
    if args.zuruecksetzen:
        liste = list(actions.STANDARD)
        actions.save(liste)
    if args.loeschen:
        a = actions.find(args.loeschen, liste)
        if not a:
            print(f"Aktion „{args.loeschen}“ nicht gefunden", file=sys.stderr)
            return 1
        liste.remove(a)
        actions.save(liste)
    if args.neu:
        if not args.anweisung:
            print("Bitte mit --anweisung angeben, was die KI tun soll", file=sys.stderr)
            return 1
        alt = actions.find(args.neu, liste)
        neu = actions.Aktion(args.neu, args.anweisung, args.modus)
        if alt:
            liste[liste.index(alt)] = neu
        else:
            liste.append(neu)
        actions.save(liste)
    for a in liste:
        print(f"  {a.name:30} [{actions.MODI[a.modus]}]  {a.anweisung}")
    return 0


def _bruecke(args) -> int:
    from . import browser_bridge
    if args.entfernen:
        browser_bridge.uninstall()
        print("Browser-Brücke entfernt.")
        return 0
    manifest = browser_bridge.install(args.id or browser_bridge.EXTENSION_ID)
    print(f"✔ Browser-Brücke eingerichtet ({manifest}). Browser einmal neu starten.")
    return 0


def _utf8_output() -> None:
    """Windows schreibt umgeleitete Ausgaben (Datei, Pipe) sonst im alten Zeichensatz – „✔“ würde abstürzen."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure") and not stream.isatty():
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> int:
    args_in = sys.argv[1:] if argv is None else argv
    _utf8_output()
    # Chrome/Edge starten den Scanner mit der Herkunft der Erweiterung als erstem Argument
    if args_in and args_in[0].startswith("chrome-extension://"):
        return _native()
    if not args_in or args_in == ["--minimiert"]:   # Doppelklick bzw. Autostart des fertigen Programms
        return _gui(bool(args_in))
    p = argparse.ArgumentParser(prog="datenwaechter", description="Sensible Daten vor dem KI-Upload finden.")
    p.add_argument("--ki", action="store_true", help="zusätzlich lokales KI-Modell (GLiNER) für Namen nutzen")
    p.add_argument("--kein-sprachmodell", action="store_true",
                   help="Inhalts-Check nur mit Stichwörtern, auch wenn Ollama läuft")
    sub = p.add_subparsers(dest="cmd")

    def ki_flags(sp):  # auch hinter dem Befehl erlaubt: „scan datei.pdf --ki“
        sp.add_argument("--ki", action="store_true", default=argparse.SUPPRESS)
        sp.add_argument("--kein-sprachmodell", action="store_true", default=argparse.SUPPRESS)

    s = sub.add_parser("scan", help="Dateien prüfen (Exit-Code 2 = kritische Funde)")
    ki_flags(s)
    s.add_argument("dateien", nargs="+")
    s.set_defaults(func=_scan)

    a = sub.add_parser("anonymisieren", help="anonymisierte Kopien erstellen")
    ki_flags(a)
    a.add_argument("dateien", nargs="+")
    a.add_argument("--ziel", help="Ausgabeordner (Standard: neben dem Original)")
    a.add_argument("--zuordnung", action="store_true", help="Platzhalter-Zuordnung ausgeben")
    a.set_defaults(func=_anonymize)

    k = sub.add_parser("ki-server", help="KI-Server für den Inhalts-Check einstellen (Ollama oder OpenAI-kompatibel)",
                       description="Ohne Optionen: aktuelle Einstellung anzeigen.")
    k.add_argument("--art", choices=["auto", "openai", "ollama", "aus"])
    k.add_argument("--url", help="Basis-URL, z. B. http://localhost:1234/v1 oder https://gateway.firma.de/v1")
    k.add_argument("--token", help="API-Schlüssel; '-' liest ihn von der Eingabe (taucht dann nicht im Verlauf auf)")
    k.add_argument("--modell", help="Modellname; leer = erstes Modell des Servers")
    k.add_argument("--bilder", choices=["ja", "nein", "auto"], help="Bilder zur Bewertung mitsenden")
    k.add_argument("--anonymisieren", choices=["ja", "nein", "auto"], help="Text vor dem Senden anonymisieren")
    k.add_argument("--testen", action="store_true", help="Verbindung mit einer kleinen Testanfrage prüfen")
    k.set_defaults(func=_ki_server)

    ak = sub.add_parser("aktion", help="KI-Aktion auf Text anwenden, z. B.: datenwaechter aktion Umformulieren --text \"…\"")
    ak.add_argument("name", help="Name der Aktion (siehe: datenwaechter aktionen)")
    ak.add_argument("--text", help="Text (ohne: von der Eingabe lesen)")
    ak.set_defaults(func=_aktion)

    al = sub.add_parser("aktionen", help="KI-Aktionen anzeigen, anlegen oder löschen")
    al.add_argument("--neu", metavar="NAME", help="Aktion anlegen oder ändern")
    al.add_argument("--anweisung", help="was die KI mit dem Text tun soll")
    al.add_argument("--modus", choices=["ersetzen", "einfuegen", "anzeigen"], default="ersetzen")
    al.add_argument("--loeschen", metavar="NAME")
    al.add_argument("--zuruecksetzen", action="store_true", help="Standard-Aktionen wiederherstellen")
    al.set_defaults(func=_aktionen)

    br = sub.add_parser("browser-bruecke", help="Scanner bei Chrome/Edge/Brave anmelden (für PDFs, Bilder, KI-Aktionen)")
    br.add_argument("--id", help="andere Erweiterungs-ID als die mitgelieferte")
    br.add_argument("--entfernen", action="store_true")
    br.set_defaults(func=_bruecke)

    g = sub.add_parser("gui", help="Wächter-Fenster starten")
    g.add_argument("--minimiert", action="store_true", help="nur als Symbol im Infobereich starten (für Autostart)")
    g.set_defaults(func=lambda a: _gui(a.minimiert))
    sub.add_parser("native-host", help="(intern) Brücke für die Browser-Erweiterung").set_defaults(
        func=lambda a: _native())

    args = p.parse_args(args_in)
    if not getattr(args, "func", None):
        return _gui("--minimiert" in args_in)
    return args.func(args)


def _gui(start_hidden: bool = False) -> int:
    from .gui import main as gui_main
    gui_main(start_hidden=start_hidden)
    return 0


def _native() -> int:
    from .native_host import main as host_main
    host_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
