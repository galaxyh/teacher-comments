"""ImageExtractor — passes image bytes through unmodified for vision-tier LLM.

Per DESIGN-001 §8.2: images don't have a text-extraction step in V1; the file
bytes are forwarded to the vision tier directly. This extractor exists to fit
the Protocol surface — `extract` returns `text=""` + carries the bytes via a
side channel: ProcessingPipeline detects the image MIME type and reads the
original bytes for the LLM call.

V1 supports JPEG / PNG / WEBP only. HEIC / RAW / TIFF deferred.
"""

from __future__ import annotations

from typing import Final

from app.adapters.document_extractors import ExtractionResult

SUPPORTED_IMAGE_MIMES: Final[frozenset[str]] = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
})

# Hard cap on image size sent to the LLM. Most vision models accept ≤20MB but
# at base64-encoded inflation that's ~27MB body. 5MB pre-encode is a generous
# cap for V1 student-work photos and keeps prompt+image under typical limits.
MAX_IMAGE_BYTES: Final[int] = 5 * 1024 * 1024


class ImageExtractor:
    def supports(self, *, mime_type: str, filename: str) -> bool:
        if mime_type in SUPPORTED_IMAGE_MIMES:
            return True
        return filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))

    async def extract(
        self, *, file_bytes: bytes, filename: str
    ) -> ExtractionResult:
        """Image extraction is a no-op text-wise; ProcessingPipeline routes the
        bytes directly to the vision tier.
        """
        warnings: list[str] = []
        if len(file_bytes) > MAX_IMAGE_BYTES:
            # Don't fail — pipeline can decide to skip or shrink. Phase 9 walks
            # the simple path: return empty text + warning, pipeline will still
            # try to send. Phase 9+ may add Pillow-based resize.
            warnings.append(
                f"image larger than {MAX_IMAGE_BYTES} bytes "
                f"(actual {len(file_bytes)}); LLM may reject"
            )
        return ExtractionResult(
            text="",  # vision tier consumes bytes via Pipeline, not text
            has_images=True,
            page_count=None,
            warnings=warnings,
        )
