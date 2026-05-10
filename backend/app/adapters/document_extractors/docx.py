"""DocxExtractor — python-docx with encrypted-OLE detection.

Per DESIGN-001 §8.2 / lessons-learned architecture.md "Substring-Based File
Detection Must Be Narrowly Scoped": detect encrypted OLE containers via the
exact `CDFV2 Encrypted` signature in the first 8KiB. Do NOT use broad
substring matches like 'encrypted' — those false-positive on permission-flagged
.docx files that python-docx can still read.

Markdown rendering rules (V1):
- Headings (Heading 1 / Heading 2 / ...) → `# heading` / `## heading`
- Lists (bullet / numbered) → `- ` / `1. ` lines
- Tables → GitHub-flavoured Markdown pipe tables
- Plain paragraphs → blank-line-separated paragraphs
- Images → ignored in V1 text path; flagged via `has_images=True`
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Final

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.adapters.document_extractors import ExtractionResult
from app.core.exceptions import DocumentExtractionError, UnsupportedFormatError

logger = logging.getLogger(__name__)

# Narrow signature — OLE2 encrypted compound document
_OLE_HEADER_MAGIC: Final[bytes] = b"\xd0\xcf\x11\xe0"
_OLE_ENCRYPTED_SIG: Final[bytes] = b"CDFV2 Encrypted"

DOCX_MIME: Final[str] = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


class DocxExtractor:
    """Implements DocumentExtractor Protocol."""

    def supports(self, *, mime_type: str, filename: str) -> bool:
        return mime_type == DOCX_MIME or filename.lower().endswith(".docx")

    async def extract(
        self, *, file_bytes: bytes, filename: str
    ) -> ExtractionResult:
        # Step 1: encrypted-OLE pre-screen (terminal).
        # NOTE: a true .docx is a ZIP container starting with `PK\x03\x04`. An OLE
        # header on a `.docx` filename almost always means it's a legacy `.doc`
        # saved with the wrong extension OR an encrypted variant — both terminal
        # for V1.
        if file_bytes[:4] == _OLE_HEADER_MAGIC:
            head = file_bytes[:8192]
            if _OLE_ENCRYPTED_SIG in head:
                raise UnsupportedFormatError(
                    "Encrypted OLE / .doc document — cannot extract",
                    context={"filename": filename},
                )
            raise UnsupportedFormatError(
                "Legacy .doc / OLE container, not .docx (zip)",
                context={"filename": filename},
            )

        # Step 2: parse via python-docx (sync) on a worker thread
        try:
            return await asyncio.to_thread(self._sync_extract, file_bytes, filename)
        except UnsupportedFormatError:
            raise
        except Exception as exc:  # noqa: BLE001 — anything else from python-docx is a parse failure
            raise DocumentExtractionError(
                f"Failed to parse .docx: {exc.__class__.__name__}: {exc}",
                context={"filename": filename},
            ) from exc

    # ── sync helpers ────────────────────────────────────────────────

    def _sync_extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        document: DocxDocument = Document(io.BytesIO(file_bytes))
        markdown_parts: list[str] = []
        warnings: list[str] = []
        has_images = self._document_has_images(document)

        # Iterate over body in document order. python-docx doesn't expose a unified
        # iterator across paragraphs + tables, so we walk the underlying XML element
        # to preserve order.
        for child in document.element.body.iterchildren():
            tag = _localname(child.tag)
            if tag == "p":
                paragraph = Paragraph(child, document)
                rendered = self._render_paragraph(paragraph)
                if rendered:
                    markdown_parts.append(rendered)
            elif tag == "tbl":
                table = Table(child, document)
                rendered = self._render_table(table)
                if rendered:
                    markdown_parts.append(rendered)
            # `sectPr`, `bookmarkStart`, etc. ignored

        text = "\n\n".join(markdown_parts).strip()
        if not text:
            warnings.append("document had no extractable text")
        return ExtractionResult(
            text=text,
            has_images=has_images,
            page_count=None,  # python-docx doesn't expose pagination cheaply
            warnings=warnings,
        )

    @staticmethod
    def _render_paragraph(paragraph: Paragraph) -> str:
        text = paragraph.text.strip()
        if not text:
            return ""
        style = (paragraph.style.name if paragraph.style is not None else "") or ""

        # Heading styles → markdown `#` prefix
        if style.lower().startswith("heading"):
            level = _heading_level(style) or 1
            return f"{'#' * min(level, 6)} {text}"

        # Bullet / numbered list — python-docx exposes numbering via XML pPr/numPr
        # which is fiddly. V1 detects `List Bullet` / `List Number` style names.
        style_lower = style.lower()
        if "list bullet" in style_lower:
            return f"- {text}"
        if "list number" in style_lower:
            return f"1. {text}"

        return text

    @staticmethod
    def _render_table(table: Table) -> str:
        rows = [
            [cell.text.strip().replace("\n", " ") for cell in row.cells]
            for row in table.rows
        ]
        if not rows:
            return ""
        # GFM pipe table — first row treated as header even when source had no header
        # styling. Rationale: LLMs disambiguate tables better with a visible separator.
        header = "| " + " | ".join(rows[0]) + " |"
        sep = "| " + " | ".join("---" for _ in rows[0]) + " |"
        body = "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])
        return "\n".join(p for p in (header, sep, body) if p)

    @staticmethod
    def _document_has_images(document: DocxDocument) -> bool:
        # `<w:drawing>` / `<a:blip>` indicate embedded images
        body = document.element.body
        return any(body.iter(qn("w:drawing"))) or any(body.iter(qn("a:blip")))  # noqa: SIM102


# ── helpers ─────────────────────────────────────────────────────────


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _heading_level(style_name: str) -> int | None:
    parts = style_name.split()
    for p in parts:
        if p.isdigit():
            return int(p)
    return None
