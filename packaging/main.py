"""Einstieg für das fertige Programm (PyInstaller).

Datenwaechter.exe       – ohne Konsole: Doppelklick startet Fenster + Tray-Symbol
datenwaechter-cli.exe   – mit Konsole: Kommandozeile und Brücke für die Browser-Erweiterung
"""

import sys

from datenwaechter.cli import main

if __name__ == "__main__":
    sys.exit(main())
