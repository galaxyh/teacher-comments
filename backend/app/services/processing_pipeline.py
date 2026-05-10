"""ProcessingPipeline — download → extract → LLM summarise → restore.

Per DESIGN-001 §4.5: pure (no DB writes). Caller (BatchWorker in Phase 5,
files router in Phase 4b) persists the resulting `ProcessingResult` into
`processed_artifact`.

Tier routing:
- text formats (.docx, .xlsx, .pptx, .pdf, .txt) → `summary_cheap`
- image formats (.jpg, .png, .webp) → `vision_cheap` (Phase 9)
- audio formats → `audio_standard` (Phase 10)
- everything else → UnsupportedFormatError (terminal)
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from decimal import Decimal

from app.adapters.document_extractors import (
    DocumentExtractorRegistry,
    ExtractionResult,
)
from app.adapters.drive_client import DriveClient
from app.core.exceptions import UnsupportedFormatError
from app.models import DriveFile
from app.services.llm_service import LLMService, TaskTier

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    artifact_type: str            # 'markdown_summary' | 'transcript'
    content_markdown: str         # PII-restored
    raw_anonymized_markdown: str  # for audit
    llm_tier: TaskTier
    llm_model: str
    llm_cost_usd: Decimal
    audit_id: str
    content_hash: str             # SHA-256 of source bytes — lets caller persist
    warnings: list[str]


# Mime types we route to the text summarisation tier (Phase 4b + 5b extractors)
TEXT_SUMMARY_MIMES: frozenset[str] = frozenset({
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",        # .xlsx
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
    "application/pdf",                                                           # .pdf
    "text/plain",
    "text/markdown",
})
VISION_MIMES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})
AUDIO_MIMES: frozenset[str] = frozenset({
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav",
    "audio/mp4", "audio/m4a", "audio/x-m4a",
    "audio/webm", "audio/ogg", "audio/flac",
})


class ProcessingPipeline:
    def __init__(
        self,
        *,
        drive_client_factory: object,  # callable returning DriveClient (auth-bound)
        extractors: DocumentExtractorRegistry,
        llm: LLMService,
    ) -> None:
        # `drive_client_factory` is a coroutine `(teacher_id) -> DriveClient`. Stored
        # as object to keep the signature stable across factory implementations.
        self._client_factory = drive_client_factory
        self._extractors = extractors
        self._llm = llm

    async def process(
        self, *, teacher_id: str, drive_file: DriveFile
    ) -> ProcessingResult:
        # 1. Download
        client: DriveClient = await self._client_factory(teacher_id=teacher_id)  # type: ignore[operator]
        file_bytes = await client.download_file(drive_file_id=drive_file.drive_file_id)
        content_hash = hashlib.sha256(file_bytes).hexdigest()

        # 2. Pick extractor (raises UnsupportedFormatError on no match — terminal)
        extractor = self._extractors.get(
            mime_type=drive_file.mime_type, filename=drive_file.filename
        )

        # 3. Extract
        extracted: ExtractionResult = await extractor.extract(
            file_bytes=file_bytes, filename=drive_file.filename
        )

        # 4. Tier routing
        tier = self._route_tier(drive_file=drive_file)

        # 5. Build prompt + call LLMService chokepoint
        is_vision = tier == TaskTier.VISION_CHEAP
        is_audio = tier == TaskTier.AUDIO_STANDARD
        if is_vision:
            prompt = _build_vision_prompt(drive_file=drive_file)
            max_tokens = 800
        elif is_audio:
            prompt = _build_audio_prompt(drive_file=drive_file)
            max_tokens = 5000  # transcripts are longer than summaries
        else:
            prompt = _build_summary_prompt(drive_file=drive_file, extracted=extracted)
            max_tokens = 600

        result = await self._llm.call(
            tier=tier,
            teacher_id=teacher_id,
            prompt=prompt,
            purpose=f"{drive_file.category}_summary" if not is_audio else f"{drive_file.category}_transcript",
            image_bytes=file_bytes if is_vision else None,
            image_mime=drive_file.mime_type if is_vision else None,
            audio_bytes=file_bytes if is_audio else None,
            audio_mime=drive_file.mime_type if is_audio else None,
            max_output_tokens=max_tokens,
        )

        return ProcessingResult(
            artifact_type="transcript" if is_audio else "markdown_summary",
            content_markdown=result.output_text,
            raw_anonymized_markdown=result.raw_output_text,
            llm_tier=tier,
            llm_model=result.model_used,
            llm_cost_usd=result.cost_usd,
            audit_id=result.audit_id,
            content_hash=content_hash,
            warnings=extracted.warnings,
        )

    @staticmethod
    def _route_tier(*, drive_file: DriveFile) -> TaskTier:
        """Route by MIME type."""
        mt = drive_file.mime_type
        fname = drive_file.filename
        if mt in TEXT_SUMMARY_MIMES or _filename_is_text(fname):
            return TaskTier.SUMMARY_CHEAP
        if mt in VISION_MIMES or _filename_is_image(fname):
            return TaskTier.VISION_CHEAP
        if mt in AUDIO_MIMES or _filename_is_audio(fname):
            return TaskTier.AUDIO_STANDARD
        raise UnsupportedFormatError(
            f"No tier routing for mime_type={mt!r} (filename={fname!r})",
            context={"filename": fname, "mime_type": mt},
        )


def _filename_is_text(filename: str) -> bool:
    return filename.lower().endswith(
        (".docx", ".xlsx", ".pptx", ".pdf", ".txt", ".md", ".markdown")
    )


def _filename_is_image(filename: str) -> bool:
    return filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))


def _filename_is_audio(filename: str) -> bool:
    return filename.lower().endswith((".mp3", ".wav", ".m4a", ".webm", ".ogg", ".flac"))


def _build_audio_prompt(*, drive_file: DriveFile) -> str:
    """Audio-tier prompt: transcript with PII placeholder substitution.

    Per D10 / D11: STT exclusively via OpenRouter; auto-detects single vs multi
    speaker. The prompt asks for monologue-or-dialog format depending on what
    the model perceives — we don't pre-classify because the LLM is better at
    speaker counting from the audio than any client-side heuristic would be at
    design scale.
    """
    category_zh = {
        "learning": "學習紀錄",
        "interaction": "教師與學生互動紀錄",
        "work": "作品成果",
    }.get(drive_file.category, drive_file.category)

    return (
        "請將以下音訊轉寫為繁體中文逐字稿。\n"
        "\n"
        "**個資處理規則**（重要）：\n"
        "- 若聽到具體姓名、學號、電話、地址，請以「（學生姓名）」「（學號）」等占位符替代，\n"
        "  不要逐字轉寫個人可識別資訊。\n"
        "- 若聽到既有匿名化代號（如 S001、PH001），請保留原樣。\n"
        "\n"
        "**講者格式**：\n"
        "- 若為單講者，輸出 monologue 段落（不加講者標籤）。\n"
        "- 若為多講者對話，每行以「講者A：」「講者B：」標示。\n"
        "\n"
        f"- 類別：{category_zh}\n"
        f"- 學期：{drive_file.semester_label}\n"
        f"- 學生（已匿名化）：{drive_file.student_pseudo_id}\n"
        f"- 檔名：{drive_file.filename}\n"
        "\n"
        "請輸出純文字逐字稿，不要附加標題或說明。"
    )


def _build_vision_prompt(*, drive_file: DriveFile) -> str:
    """Vision-tier prompt. The PII restriction is load-bearing because images
    can carry text the LLM might transcribe — anonymizer can't redact pixels.
    """
    category_zh = {
        "learning": "學習紀錄",
        "interaction": "教師與學生互動紀錄",
        "work": "作品成果",
    }.get(drive_file.category, drive_file.category)

    return (
        "你是教師助手，請看圖並整理為 markdown 摘要。\n"
        "\n"
        "**重要**：圖中可能包含學生姓名、學號或其他個資。請**不要**逐字轉抄這些內容；\n"
        "改用「學生姓名」、「學號」等代詞描述存在但不複述具體值。\n"
        "\n"
        f"- 類別：{category_zh}\n"
        f"- 學期：{drive_file.semester_label}\n"
        f"- 學生（已匿名化）：{drive_file.student_pseudo_id}\n"
        f"- 檔名：{drive_file.filename}\n"
        "\n"
        "請輸出三段：\n"
        "1. **主題**（1-2 句）\n"
        "2. **觀察重點**（3-5 個 bullet）\n"
        "3. **教師值得關注的細節**（簡短說明）"
    )


def _build_summary_prompt(
    *, drive_file: DriveFile, extracted: ExtractionResult
) -> str:
    """V1 prompt — kept minimal. Future iterations move this to a template module
    so educators can tune it via Settings without touching code (D8 spirit)."""
    category_zh = {
        "learning": "學習紀錄",
        "interaction": "教師與學生互動紀錄",
        "work": "作品成果",
    }.get(drive_file.category, drive_file.category)

    return (
        f"你是教師助手，請將以下「{category_zh}」資料整理為 markdown 格式的精要摘要。\n"
        f"- 學期：{drive_file.semester_label}\n"
        f"- 學生（已匿名化）：{drive_file.student_pseudo_id}\n"
        f"- 檔名：{drive_file.filename}\n\n"
        "請輸出三段：\n"
        "1. **主題**（1-2 句）\n"
        "2. **觀察重點**（3-5 個 bullet）\n"
        "3. **教師值得關注的細節**（簡短說明）\n\n"
        f"原始內容：\n----\n{extracted.text}\n----"
    )
