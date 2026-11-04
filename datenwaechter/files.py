"""Dateien lesen (Text, Word, PDF – auch eingescannt –, Bilder) und anonymisierte Kopien schreiben.

PDFs und Bilder werden beim Anonymisieren *geschwärzt*: Layout bleibt erhalten, Funde werden mit einem
Kasten samt Platzhalter ([PERSON_1]) überdeckt, Gesichter verpixelt. Das Ergebnis ist ein Bild-PDF bzw. Bild,
das Claude/ChatGPT problemlos lesen können – der Originaltext ist darin nicht mehr enthalten.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import ocr
from .anonymize import Anonymizer
from .detectors import Finding, scan_text
from .ocr import Box, Span

TEXT_SUFFIXES = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".conf", ".env",
    ".log", ".html", ".htm", ".py", ".js", ".ts", ".java", ".cs", ".go", ".rb", ".php", ".sql", ".sh",
    ".ps1", ".bat", ".toml", ".properties", ".eml",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
PDF_SCALE = 2.5        # 180 dpi – gut lesbar für OCR und für die KI, Dateien bleiben handlich
MAX_PDF_PAGES = 50


class UnsupportedFile(Exception):
    pass


@dataclass
class Page:
    render: Callable[[], object]          # liefert das Seitenbild (PIL), passend zu den Koordinaten in spans
    spans: list[Span] = field(default_factory=list)


@dataclass
class Document:
    path: Path
    kind: str                             # "text" | "docx" | "pdf" | "image"
    text: str
    pages: list[Page] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    preview: Callable[[], object] | None = None   # Bild für das Sprachmodell (Foto / erste Scan-Seite)
    _keep: object = None                  # hält z. B. das geöffnete PDF am Leben

    @property
    def redactable(self) -> bool:
        return bool(self.pages)


# --------------------------------------------------------------------------- Laden

def load(path: str | Path) -> Document:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _load_pdf(p)
    if suffix in IMAGE_SUFFIXES:
        return _load_image(p)
    if suffix == ".docx":
        doc = _open_docx(p)
        return Document(p, "docx", "\n".join(par.text for par in _docx_paragraphs(doc)),
                        notes=["Bilder innerhalb des Word-Dokuments werden nicht geprüft"] if doc.inline_shapes else [])
    if suffix in TEXT_SUFFIXES or not suffix:
        raw = p.read_bytes()
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                return Document(p, "text", raw.decode(enc))
            except UnicodeDecodeError:
                continue
    raise UnsupportedFile(f"Dateityp {suffix or '(ohne Endung)'} wird noch nicht unterstützt")


def _load_image(p: Path) -> Document:
    from PIL import Image, ImageOps
    img = ImageOps.exif_transpose(Image.open(p))
    img.load()
    res = ocr.recognize(img)
    notes = [] if res else ["Text im Bild nicht geprüft – Texterkennung (OCR) fehlt"]
    return Document(p, "image", res.text if res else "", [Page(lambda: img, res.spans if res else [])],
                    notes, preview=lambda: img)


def _load_pdf(p: Path) -> Document:
    try:
        import pypdfium2 as pdfium
    except ImportError:
        from pypdf import PdfReader
        text = "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)
        return Document(p, "pdf", text, notes=["Ohne pypdfium2: keine Prüfung gescannter Seiten, keine Schwärzung"])

    pdf = pdfium.PdfDocument(str(p))
    parts: list[str] = []
    pages: list[Page] = []
    notes: list[str] = []
    preview = None
    pos = 0
    for i in range(len(pdf)):
        if i >= MAX_PDF_PAGES:
            notes.append(f"Nur die ersten {MAX_PDF_PAGES} Seiten geprüft")
            break
        page = pdf[i]
        render = (lambda pg=page: pg.render(scale=PDF_SCALE).to_pil())
        if i:
            parts.append("\n\n")
            pos += 2
        tp = page.get_textpage()
        n = tp.count_chars()
        text = tp.get_text_range() if n else ""
        spans: list[Span] = []
        if len(text.strip()) >= 20:
            _, height = page.get_size()
            if len(text) == n:  # Zeichenindex = Textposition -> Kästen für die Schwärzung
                for ci in range(n):
                    left, bottom, right, top = tp.get_charbox(ci)
                    spans.append(Span(pos + ci, pos + ci + 1, (left * PDF_SCALE, (height - top) * PDF_SCALE,
                                                               right * PDF_SCALE, (height - bottom) * PDF_SCALE)))
        else:  # vermutlich eingescannt -> Texterkennung
            img = render()
            preview = preview or (lambda im=img: im)
            res = ocr.recognize(img)
            if res is None:
                notes.append(f"Seite {i + 1} ist ein Scan – Texterkennung (OCR) fehlt, Inhalt nicht geprüft")
                text = ""
            else:
                text = res.text
                spans = [Span(s.start + pos, s.end + pos, s.box) for s in res.spans]
            render = (lambda im=img: im)
        parts.append(text)
        pos += len(text)
        pages.append(Page(render, spans))
    return Document(p, "pdf", "".join(parts), pages, notes, preview, _keep=pdf)


# --------------------------------------------------------------------------- Kompatible Kurzformen

def extract_text(path: str | Path) -> str:
    return load(path).text


def scan_file(path: str | Path, use_ki: bool = False) -> tuple[str, list[Finding]]:
    doc = load(path)
    return doc.text, scan_text(doc.text, use_ki=use_ki)


# --------------------------------------------------------------------------- Schreiben

def write_anonymized(path: str | Path, anonymizer: Anonymizer, out_dir: str | Path | None = None,
                     use_ki: bool = False, doc: Document | None = None, findings: list[Finding] | None = None,
                     faces: list[Box] = ()) -> Path:
    """Schreibt eine anonymisierte Kopie neben das Original (oder nach out_dir) und gibt den Pfad zurück.

    Text -> gleiche Endung, Word -> .docx, PDF -> geschwärztes PDF, Bild -> geschwärztes Bild.
    """
    p = Path(path)
    doc = doc or load(p)
    if findings is None:
        findings = scan_text(doc.text, use_ki=use_ki)
    target = Path(out_dir) if out_dir else p.parent
    target.mkdir(parents=True, exist_ok=True)
    stem = f"{p.stem}_anonymisiert"

    if doc.kind == "docx":
        d = _open_docx(p)
        for par in _docx_paragraphs(d):
            if not par.text.strip():
                continue
            new = anonymizer.anonymize(par.text, use_ki=use_ki)
            if new != par.text:
                runs = par.runs  # Formatierung des ersten Abschnitts behalten
                if runs:
                    runs[0].text = new
                    for r in runs[1:]:
                        r.text = ""
                else:
                    par.text = new
        out = target / f"{stem}.docx"
        d.save(str(out))
        return out

    if doc.redactable:
        from .redact import redact
        images = [redact(pg.render(), pg.spans, findings, anonymizer, faces if doc.kind == "image" else ())
                  for pg in doc.pages]
        if doc.kind == "pdf":
            out = target / f"{stem}.pdf"
            images[0].save(out, "PDF", save_all=True, append_images=images[1:], resolution=72 * PDF_SCALE)
        else:
            suffix = p.suffix.lower()
            fmt, ext = ("JPEG", suffix) if suffix in (".jpg", ".jpeg") else ("PNG", ".png")
            out = target / f"{stem}{ext}"
            images[0].save(out, fmt, **({"quality": 90} if fmt == "JPEG" else {}))
        return out

    out = target / f"{stem}{'.txt' if doc.kind == 'pdf' else (p.suffix or '.txt')}"
    out.write_text(anonymizer.anonymize(doc.text, findings), encoding="utf-8")
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
