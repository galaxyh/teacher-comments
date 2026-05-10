"""PdfExtractor — pypdf text-only extraction.

Per DESIGN-001 §8.2: V1 is text-only; encrypted PDFs raise `UnsupportedFormat`
(pypdf raises `PdfReadError` which we map). OCR fallback is Phase 7+ scope.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import Final

from pypdf import PdfReader
from pypdf.errors import (
    DependencyError,
    EmptyFileError,
    FileNotDecryptedError,
    PdfReadError,
)

from app.adapters.document_extractors import ExtractionResult
from app.core.exceptions import DocumentExtractionError, UnsupportedFormatError

logger = logging.getLogger(__name__)

PDF_MIME: Final[str] = "application/pdf"


class PdfExtractor:
    def supports(self, *, mime_type: str, filename: str) -> bool:
        return mime_type == PDF_MIME or filename.lower().endswith(".pdf")

    async def extract(self, *, file_bytes: bytes, filename: str) -> ExtractionResult:
        try:
            return await asyncio.to_thread(self._sync_extract, file_bytes, filename)
        except FileNotDecryptedError as exc:
            # Encrypted PDF — terminal (no OCR / decrypt path in V1)
            raise UnsupportedFormatError(
                "Encrypted PDF — V1 cannot decrypt",
                context={"filename": filename},
            ) from exc
        except UnsupportedFormatError:
            raise
        except (PdfReadError, EmptyFileError, DependencyError) as exc:
            raise DocumentExtractionError(
                f"Failed to read PDF: {exc.__class__.__name__}: {exc}",
                context={"filename": filename},
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise DocumentExtractionError(
                f"Failed to parse .pdf: {exc.__class__.__name__}: {exc}",
                context={"filename": filename},
            ) from exc

    def _sync_extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        reader = PdfReader(io.BytesIO(file_bytes))
        # Try empty password — many PDFs are "encrypted" with empty pw for printing
        # restrictions only. If that fails, treat as truly-encrypted.
        if reader.is_encrypted and reader.decrypt("") == 0:  # 0 = decryption failed
            raise UnsupportedFormatError(
                "Encrypted PDF — V1 cannot decrypt",
                context={"filename": filename},
            )

        warnings: list[str] = []
        text_parts: list[str] = []
        empty_pages = 0
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"page {i} text extraction failed: {exc}")
                continue
            text = text.strip()
            if not text:
                empty_pages += 1
                continue
            text_parts.append(f"## 第 {i} 頁\n{text}")

        if empty_pages:
            warnings.append(
                f"{empty_pages} page(s) had no extractable text — likely scanned image PDF"
            )
        return ExtractionResult(
            text="\n\n".join(text_parts).strip(),
            has_images=False,  # pypdf surfaces images as XObjects; out of scope V1
            page_count=len(reader.pages),
            warnings=warnings,
        )
