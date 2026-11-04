"""Registriert den Datenwächter als „Native Messaging Host“ für Chrome und Edge (nur Windows, ohne Admin-Rechte).

Aufruf:  python install_browser_bridge.py <ERWEITERUNGS-ID>
Die ID steht unter chrome://extensions bzw. edge://extensions, nachdem du den Ordner „extension“ geladen hast.
"""

import json
import sys
from pathlib import Path

HOST = "de.datenwaechter.host"
KEYS = [
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    ext_id = sys.argv[1].strip()
    target = Path.home() / "AppData" / "Local" / "Datenwaechter"
    target.mkdir(parents=True, exist_ok=True)

    bat = target / "host.bat"
    bat.write_text(f'@echo off\r\n"{sys.executable}" -m datenwaechter native-host\r\n', encoding="ascii")
    manifest = target / f"{HOST}.json"
    manifest.write_text(json.dumps({
        "name": HOST,
        "description": "Datenwächter – lokaler Scanner für sensible Daten",
        "path": str(bat),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/"],
    }, indent=2), encoding="utf-8")

    if sys.platform != "win32":
        print(f"Manifest geschrieben: {manifest}\n(Registry-Einträge gibt es nur unter Windows.)")
        return
    import winreg
    for key in KEYS:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{key}\\{HOST}") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(manifest))
    print(f"✔ Browser-Brücke installiert ({manifest}). Browser einmal neu starten.")


if __name__ == "__main__":
    main()
