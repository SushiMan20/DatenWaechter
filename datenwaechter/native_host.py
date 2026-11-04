"""Brücke zwischen Browser-Erweiterung und Python-Scanner (Chrome/Edge „Native Messaging“).

Der Browser startet dieses Programm lokal und spricht über stdin/stdout mit ihm.
Damit kann die Erweiterung auch PDFs und Word-Dateien prüfen – ohne dass Daten den PC verlassen.

Nachricht:  {"action": "scan_file", "name": "x.pdf", "data_b64": "..."}  oder  {"action": "ping"}
Antwort:    {"ok": true, "findings": [...], "anonymized": "...", "name": "x_anonymisiert.txt"}
"""

from __future__ import annotations

import base64
import json
import os
import struct
import sys
import tempfile
from pathlib import Path

from .anonymize import Anonymizer
from .files import UnsupportedFile, scan_file

MAX_REPLY = 900_000  # Chrome erlaubt max. 1 MB vom Host zur Erweiterung


def _read() -> dict | None:
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    (length,) = struct.unpack("=I", raw)
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def _write(msg: dict) -> None:
    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(data)) + data)
    sys.stdout.buffer.flush()


def handle(msg: dict) -> dict:
    action = msg.get("action")
    if action == "ping":
        return {"ok": True, "version": "0.1.0"}
    if action != "scan_file":
        return {"ok": False, "error": f"unbekannte Aktion {action!r}"}

    name = Path(msg.get("name") or "datei").name
    use_ki = bool(msg.get("ki"))
    with tempfile.TemporaryDirectory(prefix="datenwaechter_") as tmp:
        path = Path(tmp) / name
        path.write_bytes(base64.b64decode(msg["data_b64"]))
        try:
            text, findings = scan_file(path, use_ki=use_ki)
        except UnsupportedFile as e:
            return {"ok": False, "error": str(e)}
    anonymized = Anonymizer().anonymize(text, findings) if findings else None
    reply = {
        "ok": True,
        "findings": [
            {"kind": f.kind, "label": f.label, "display": f.masked(), "severity": f.severity, "source": f.source}
            for f in findings
        ],
        "anonymized": anonymized,
        "name": f"{Path(name).stem}_anonymisiert.txt",
    }
    if anonymized and len(anonymized.encode("utf-8")) > MAX_REPLY:
        reply["anonymized"] = None
        reply["error"] = "Datei zu groß für die automatische Anonymisierung – bitte mit dem Datenwächter-Fenster."
    return reply


def main() -> None:
    if sys.platform == "win32":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    while True:
        msg = _read()
        if msg is None:
            break
        try:
            _write(handle(msg))
        except Exception as e:  # noqa: BLE001 – Fehler an die Erweiterung melden statt abzustürzen
            _write({"ok": False, "error": str(e)})
