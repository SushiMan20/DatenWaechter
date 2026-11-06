"""Browser-Brücke einrichten: meldet den lokalen Scanner bei Chrome, Edge und Brave an (Native Messaging).

Ohne Admin-Rechte (nur HKCU). Funktioniert für beide Installationsarten:
- installiertes Programm (PyInstaller): der Browser startet direkt datenwaechter-cli.exe
- pip-Installation: der Browser startet eine kleine host.bat, die `python -m datenwaechter native-host` aufruft
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOST = "de.datenwaechter.host"
# Feste ID der Erweiterung (aus dem „key“ in extension/manifest.json)
EXTENSION_ID = "cfehnnbcppbopfbeiledoobmkgdffomd"
REG_KEYS = [
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
    r"Software\Chromium\NativeMessagingHosts",
]


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "Datenwaechter"


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _host_executable(target: Path) -> Path:
    if frozen():
        exe = Path(sys.executable)
        cli = exe.with_name("datenwaechter-cli.exe")
        return cli if cli.exists() else exe
    if sys.platform == "win32":
        bat = target / "host.bat"
        bat.write_text(f'@echo off\r\n"{sys.executable}" -m datenwaechter native-host\r\n', encoding="ascii")
        return bat
    sh = target / "host.sh"
    sh.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m datenwaechter native-host\n', encoding="utf-8")
    sh.chmod(0o755)
    return sh


def install(ext_id: str = EXTENSION_ID) -> Path:
    """Schreibt das Host-Manifest und trägt es für alle Chromium-Browser ein. Gibt den Manifest-Pfad zurück."""
    target = data_dir()
    target.mkdir(parents=True, exist_ok=True)
    manifest = target / f"{HOST}.json"
    manifest.write_text(json.dumps({
        "name": HOST,
        "description": "Datenwächter – lokaler Scanner für sensible Daten",
        "path": str(_host_executable(target)),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{ext_id}/"],
    }, indent=2), encoding="utf-8")
    if sys.platform == "win32":
        import winreg
        for key in REG_KEYS:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, f"{key}\\{HOST}") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(manifest))
    return manifest


def uninstall() -> None:
    if sys.platform == "win32":
        import winreg
        for key in REG_KEYS:
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{key}\\{HOST}")
            except OSError:
                pass
    manifest = data_dir() / f"{HOST}.json"
    if manifest.exists():
        manifest.unlink()


def is_installed() -> bool:
    manifest = data_dir() / f"{HOST}.json"
    if not manifest.exists():
        return False
    if sys.platform != "win32":
        return True
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{REG_KEYS[0]}\\{HOST}") as k:
            return winreg.QueryValueEx(k, "")[0] == str(manifest)
    except OSError:
        return False
