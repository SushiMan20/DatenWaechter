"""„Mit Windows starten“: Eintrag unter HKCU\\…\\Run (Windows) bzw. ~/.config/autostart (Linux)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

NAME = "Datenwaechter"


def command() -> str:
    if getattr(sys, "frozen", False):   # installiertes Programm (Datenwaechter.exe)
        return f'"{sys.executable}" --minimiert'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")  # ohne schwarzes Konsolenfenster
    if sys.platform == "win32" and pythonw.exists():
        exe = pythonw
    return f'"{exe}" -m datenwaechter gui --minimiert'


def _desktop_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / "datenwaechter.desktop"


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, NAME)
                return True
        except OSError:
            return False
    return _desktop_file().exists()


def set_enabled(on: bool) -> None:
    if sys.platform == "win32":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except OSError:
                    pass
        return
    f = _desktop_file()
    if on:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"[Desktop Entry]\nType=Application\nName=Datenwächter\nExec={command()}\n"
                     "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
    elif f.exists():
        f.unlink()
