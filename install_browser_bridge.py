"""Meldet den Datenwächter-Scanner bei Chrome, Edge und Brave an (ohne Admin-Rechte).

Aufruf:  python install_browser_bridge.py            (feste ID der mitgelieferten Erweiterung)
         python install_browser_bridge.py <ID>       (andere Erweiterungs-ID)
Gleichwertig:  datenwaechter browser-bruecke
"""

import sys

from datenwaechter import browser_bridge

if __name__ == "__main__":
    manifest = browser_bridge.install(sys.argv[1] if len(sys.argv) > 1 else browser_bridge.EXTENSION_ID)
    print(f"✔ Browser-Brücke eingerichtet ({manifest}). Browser einmal neu starten.")
