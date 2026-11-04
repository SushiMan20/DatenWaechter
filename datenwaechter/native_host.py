"""Brücke zwischen Browser-Erweiterung und Python-Scanner (Chrome/Edge „Native Messaging“).

Der Browser startet dieses Programm lokal und spricht über stdin/stdout mit ihm. Damit prüft die
Erweiterung auch PDFs (inkl. Scans), Word-Dateien und Bilder – ohne dass Daten den PC verlassen.

Anfragen:
  {"action": "ping"}
  {"action": "check_text", "text": "..."}                         -> Inhalts-Check für eingefügten Text
  {"action": "list_actions"}                                      -> KI-Aktionen fürs Rechtsklick-Menü
  {"action": "run_action", "id": "umformulieren", "text": "..."}  -> KI-Aktion auf markiertem Text
  {"action": "scan_file", "name": "x.pdf", "data_b64": "...", "mapping": {...}}
Antworten werden in Teile zerlegt ({"part": i, "of": n, "data": "..."}), weil Chrome vom Host
höchstens 1 MB pro Nachricht annimmt; die Erweiterung setzt sie wieder zusammen.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import sys
import tempfile
from pathlib import Path

from . import __version__, actions, content_check, faces, llm, ocr
from .analysis import analyze, anonymize
from .anonymize import Anonymizer
from .files import UnsupportedFile

CHUNK = 200_000  # Zeichen pro Teilnachricht (max. 800 KB UTF-8)
MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


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


def send(reply: dict) -> None:
    s = json.dumps(reply, ensure_ascii=False)
    parts = [s[i:i + CHUNK] for i in range(0, len(s), CHUNK)] or [""]
    for i, part in enumerate(parts):
        _write({"part": i, "of": len(parts), "data": part})


def handle(msg: dict) -> dict:
    action = msg.get("action")
    if action == "ping":
        return {"ok": True, "version": __version__, "ocr": ocr.backend(), "faces": faces.available(),
                "llm": content_check.llm_status()}
    if action == "check_text":
        return {"ok": True, "content": content_check.check(msg.get("text", "")).to_dict()}
    if action == "list_actions":
        return {"ok": True, "llm": content_check.llm_status(),
                "actions": [{"id": a.id, "name": a.name, "mode": a.modus} for a in actions.load()]}
    if action == "run_action":
        try:
            return actions.run(msg.get("id", ""), msg.get("text", "")).to_dict()
        except llm.LlmError as e:
            return {"ok": False, "error": str(e)}
    if action != "scan_file":
        return {"ok": False, "error": f"unbekannte Aktion {action!r}"}

    name = Path(msg.get("name") or "datei").name
    anon = Anonymizer()
    anon.load(msg.get("mapping") or {})
    with tempfile.TemporaryDirectory(prefix="datenwaechter_") as tmp:
        path = Path(tmp) / name
        path.write_bytes(base64.b64decode(msg["data_b64"]))
        try:
            report = analyze(path, use_ki=bool(msg.get("ki")))
        except UnsupportedFile as e:
            return {"ok": False, "error": str(e)}
        reply = {"ok": True, **report.to_dict()}
        if report.can_anonymize:
            out = anonymize(report, anon, Path(tmp) / "aus")
            reply["output"] = {"name": out.name, "mime": MIME.get(out.suffix.lower(), "text/plain"),
                               "b64": base64.b64encode(out.read_bytes()).decode()}
            reply["mapping"] = anon.mapping
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
            send(handle(msg))
        except Exception as e:  # noqa: BLE001 – Fehler an die Erweiterung melden statt abzustürzen
            send({"ok": False, "error": str(e)})
