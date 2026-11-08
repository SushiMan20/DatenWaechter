"""Gesamtprüfung einer Datei: sensible Daten + Gesichter + Inhalts-Check („was ist das?“)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import content_check, faces as face_mod
from .anonymize import Anonymizer
from .content_check import Verdict
from .detectors import MITTEL, Finding, scan_text
from .files import Document, docx_bild, load, write_anonymized
from .ocr import Box


@dataclass
class Report:
    doc: Document
    findings: list[Finding]
    faces: list[Box] = field(default_factory=list)
    verdict: Verdict = field(default_factory=Verdict)
    info: list[str] = field(default_factory=list)   # Hinweise, die allein keine Warnung auslösen

    @property
    def name(self) -> str:
        return self.doc.path.name

    @property
    def needs_attention(self) -> bool:
        return bool(self.findings or self.faces or self.verdict.warning or self.doc.notes)

    @property
    def can_anonymize(self) -> bool:
        return bool(self.findings or self.faces)

    @property
    def severity(self) -> int:
        return max([f.severity for f in self.findings] + [MITTEL if self.faces else 0, self.verdict.severity])

    def rows(self) -> list[dict]:
        """Zeilen für die Anzeige (Fenster und Browser)."""
        out = [{"kind": f.kind, "label": f.label + (" (KI)" if f.source == "ki" else ""), "display": f.masked(),
                "severity": f.severity, "source": f.source} for f in self.findings]
        if self.faces:
            wo = "auf dem Bild" if self.doc.kind == "image" else "auf Fotos im Dokument"
            out.append({"kind": "GESICHT", "label": f"Gesicht(er) {wo}", "display": f"{len(self.faces)} erkannt",
                        "severity": MITTEL, "source": "bild"})
        return out

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.doc.kind, "rows": self.rows(), "content": self.verdict.to_dict(),
                "notes": self.doc.notes, "info": self.info, "can_anonymize": self.can_anonymize, "severity": self.severity}


def analyze(path: str | Path, use_ki: bool = False, use_llm: bool | str = "auto") -> Report:
    doc = load(path)
    findings = scan_text(doc.text, use_ki=use_ki)
    found_faces: list[Box] = []
    if face_mod.available():
        for pg in doc.pages:                        # Fotos, Scans und PDF-Seiten mit Bildern
            if pg.foto:
                pg.faces = face_mod.detect(pg.render())
                found_faces += pg.faces
        for name in doc.bilder:                     # Fotos in Word-Dateien
            img = docx_bild(doc.path, name)
            if img is not None:
                doc.bild_faces[name] = face_mod.detect(img)
                found_faces += doc.bild_faces[name]
    image = doc.preview() if doc.preview else None
    verdict = content_check.check(doc.text, image=image, name=doc.path.name, use_llm=use_llm)
    verdict = content_check.nur_mit_personenbezug(verdict, findings, faces=len(found_faces) + (doc.kind == "image" and
                                                                                 "Fotos von Personen" in verdict.categories))
    info = []
    if doc.kind == "image" and not verdict.by_ai:
        info.append("Motiv des Bildes nicht bewertet – dafür einen KI-Server mit Bildverständnis einrichten")
    return Report(doc, findings, found_faces, verdict, info)


def anonymize(report: Report, anonymizer: Anonymizer, out_dir: str | Path | None = None) -> Path:
    return write_anonymized(report.doc.path, anonymizer, out_dir, doc=report.doc, findings=report.findings)
