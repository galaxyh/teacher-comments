"""Document extractor protocol + registry.

Per ARCH-001 §2.1 / DESIGN-001 §8 — one extractor per format. Registry routes
by mime_type + filename; raises UnsupportedFormatError when no extractor matches.

Provider abstraction uses `Protocol` (structural typing) per lessons-learned/
architecture.md "Provider Abstraction with Protocol, Not Inheritance" — extractors
share no implementation, only an interface.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from app.core.exceptions import UnsupportedFormatError


class ExtractionResult(BaseModel):
    text: str
    """Extracted plain text — UTF-8, normalised. Markdown formatting where the
    source had structure (tables, lists, headings)."""

    has_images: bool = False
    """Hint to ProcessingPipeline that a vision pass MAY also be appropriate.
    V1: not yet wired; flagged for Phase 5+ image-bearing docx routing."""

    page_count: int | None = None
    warnings: list[str] = []
    """Non-fatal issues (e.g., 'sheet "Annex" was empty', 'page 5 had no text layer').
    Caller decides whether to surface in UI."""


class DocumentExtractor(Protocol):
    """Structural interface — no inheritance required."""

    async def extract(self, *, file_bytes: bytes, filename: str) -> ExtractionResult:
        ...

    def supports(self, *, mime_type: str, filename: str) -> bool:
        ...


class DocumentExtractorRegistry:
    """First-match-wins registry. Order = priority order in __init__."""

    def __init__(self, extractors: list[DocumentExtractor]) -> None:
        self._extractors = extractors

    def get(self, *, mime_type: str, filename: str) -> DocumentExtractor:
        for ext in self._extractors:
            if ext.supports(mime_type=mime_type, filename=filename):
                return ext
        raise UnsupportedFormatError(
            f"No extractor for mime_type={mime_type!r} filename={filename!r}",
            context={"mime_type": mime_type, "filename": filename},
        )


def build_default_registry() -> DocumentExtractorRegistry:
    """Default registry for V1. Order: most-specific MIME → broad suffix-based last."""
    from app.adapters.document_extractors.docx import DocxExtractor
    from app.adapters.document_extractors.pdf import PdfExtractor
    from app.adapters.document_extractors.pptx import PptxExtractor
    from app.adapters.document_extractors.text import PlainTextExtractor
    from app.adapters.document_extractors.xlsx import XlsxExtractor

    return DocumentExtractorRegistry(
        extractors=[
            DocxExtractor(),
            XlsxExtractor(),
            PptxExtractor(),
            PdfExtractor(),
            PlainTextExtractor(),  # last — broad-by-suffix, low-priority
        ]
    )


__all__ = [
    "DocumentExtractor",
    "DocumentExtractorRegistry",
    "ExtractionResult",
    "build_default_registry",
]
