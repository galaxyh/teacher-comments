"""PlainTextExtractor — UTF-8 with big5 / cp950 fallback chain.

Per DESIGN-001 §8.2: text-encoding fallback for legacy Taiwanese files. Many
older notes from Word for Windows (pre-Unicode) live as `.txt` saved in big5
or cp950. UTF-8 is tried first; on failure we walk the chain.
"""

from __future__ import annotations

import logging
from typing import Final

from app.adapters.document_extractors import ExtractionResult

logger = logging.getLogger(__name__)

ENCODING_CHAIN: Final[tuple[str, ...]] = ("utf-8", "big5", "cp950")


class PlainTextExtractor:
    def supports(self, *, mime_type: str, filename: str) -> bool:
        return (
            mime_type == "text/plain"
            or filename.lower().endswith((".txt", ".md", ".markdown"))
        )

    async def extract(
        self, *, file_bytes: bytes, filename: str
    ) -> ExtractionResult:
        text, used_encoding, warnings = _decode_with_fallback(file_bytes)
        if used_encoding != "utf-8":
            warnings.append(f"decoded as {used_encoding} (UTF-8 failed)")
        return ExtractionResult(
            text=text.strip(),
            has_images=False,
            page_count=None,
            warnings=warnings,
        )


def _decode_with_fallback(file_bytes: bytes) -> tuple[str, str, list[str]]:
    """Try each encoding; return on first success. Replace undecodable as last resort."""
    last_err: Exception | None = None
    for enc in ENCODING_CHAIN:
        try:
            return file_bytes.decode(enc), enc, []
        except UnicodeDecodeError as exc:
            last_err = exc
            continue
    # Last resort — replace bad bytes so we don't lose the whole document
    text = file_bytes.decode("utf-8", errors="replace")
    return (
        text,
        "utf-8-replace",
        [f"unable to decode cleanly with any of {ENCODING_CHAIN}; replaced bad bytes"],
    )
