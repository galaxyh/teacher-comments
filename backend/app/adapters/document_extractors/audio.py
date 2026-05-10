"""AudioExtractor — passes audio bytes through for the audio_standard tier.

Per DESIGN-001 §8.2: audio is forwarded directly to the LLM (D10 — STT exclusively
via OpenRouter). No client-side STT in V1. The `audio_standard` tier
(`google/gemini-2.5-flash-lite` by default per D9) receives audio + text prompt
and returns a transcript.

V1 supports common consumer formats: mp3, wav, m4a, webm, ogg, flac.

Size cap: 25MB pre-encode. Audio over 25MB needs the streaming download path
in DriveClient (Phase 5+ scope) and possibly chunking. V1 walking-skeleton
warns on oversize but doesn't auto-chunk; teacher sees `unprocessable` for
files exceeding the cap.
"""

from __future__ import annotations

from typing import Final

from app.adapters.document_extractors import ExtractionResult

SUPPORTED_AUDIO_MIMES: Final[frozenset[str]] = frozenset({
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/m4a",
    "audio/x-m4a",
    "audio/webm",
    "audio/ogg",
    "audio/flac",
})

MAX_AUDIO_BYTES: Final[int] = 25 * 1024 * 1024


class AudioExtractor:
    def supports(self, *, mime_type: str, filename: str) -> bool:
        if mime_type.lower() in SUPPORTED_AUDIO_MIMES:
            return True
        return filename.lower().endswith((".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac"))

    async def extract(
        self, *, file_bytes: bytes, filename: str
    ) -> ExtractionResult:
        warnings: list[str] = []
        if len(file_bytes) > MAX_AUDIO_BYTES:
            warnings.append(
                f"audio larger than {MAX_AUDIO_BYTES} bytes "
                f"(actual {len(file_bytes)}); may exceed model context"
            )
        return ExtractionResult(
            text="",  # audio_standard tier consumes bytes via Pipeline
            has_images=False,
            page_count=None,
            warnings=warnings,
        )
