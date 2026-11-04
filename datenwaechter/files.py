"""Text aus Dateien lesen und anonymisierte Kopien schreiben."""

from __future__ import annotations

from pathlib import Path

from .anonymize import Anonymizer
from .detectors import Finding, scan_text

TEXT_SUFFIXES = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".env",
    ".log", ".html", ".htm", ".py", ".js", ".ts", ".java", ".cs", ".go", ".rb", ".php", ".sql", ".sh",
    ".ps1", ".bat", ".toml", ".properties", ".eml",
}


class UnsupportedFile(Exception):
    pass


def extract_text(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(p))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    if suffix == ".docx":
        doc = _open_docx(p)
        return "\n".join(par.text for par in _docx_paragraphs(doc))
    if suffix in TEXT_SUFFIXES or not suffix:
        raw = p.read_bytes()
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
    raise UnsupportedFile(f"Dateityp {suffix or '(ohne Endung)'} wird noch nicht unterstützt")


def scan_file(path: str | Path, use_ki: bool = False) -> tuple[str, list[Finding]]:
    text = extract_text(path)
    return text, scan_text(text, use_ki=use_ki)


def write_anonymized(path: str | Path, anonymizer: Anonymizer, out_dir: str | Path | None = None,
                     use_ki: bool = False) -> Path:
    """Schreibt eine anonymisierte Kopie neben das Original (oder nach out_dir).

    PDF -> .txt (Text wird übernommen, Layout nicht), DOCX -> .docx, Textdateien -> gleiche Endung.
    """
    p = Path(path)
    target_dir = Path(out_dir) if out_dir else p.parent
    suffix = p.suffix.lower()

    if suffix == ".docx":
        doc = _open_docx(p)
        for par in _docx_paragraphs(doc):
            if not par.text.strip():
                continue
            new = anonymizer.anonymize(par.text, use_ki=use_ki)
            if new != par.text:
                # Formatierung des ersten Abschnitts behalten, Rest leeren
                runs = par.runs
                if runs:
                    runs[0].text = new
                    for r in runs[1:]:
                        r.text = ""
                else:
                    par.text = new
        out = target_dir / f"{p.stem}_anonymisiert.docx"
        doc.save(str(out))
        return out

    text = extract_text(p)
    new = anonymizer.anonymize(text, use_ki=use_ki)
    out_suffix = ".txt" if suffix == ".pdf" else (p.suffix or ".txt")
    out = target_dir / f"{p.stem}_anonymisiert{out_suffix}"
    out.write_text(new, encoding="utf-8")
    return out


def _open_docx(p: Path):
    import docx
    return docx.Document(str(p))


def _docx_paragraphs(doc):
    yield from doc.paragraphs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs
    for section in doc.sections:
        for part in (section.header, section.footer):
            yield from part.paragraphs
