"""ProcessingPipeline — download → extract → LLM summarise → restore.

Per DESIGN-001 §4.5: pure (no DB writes). Caller (BatchWorker in Phase 5,
files router in Phase 4b) persists the resulting `ProcessingResult` into
`processed_artifact`.

Tier routing for Phase 4b:
- learning / work × text formats (.docx, .txt) → `summary_cheap`
- interaction × text → `summary_cheap` (audio routing is Phase 5+)
- everything else → UnsupportedFormatError (terminal)

Vision and audio tiers extend this in later phases.
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

        # 4. Tier routing — Phase 4b only handles text. Vision / audio are TODOs.
        tier = self._route_tier(drive_file=drive_file)

        # 5. Build prompt + summarise via LLMService chokepoint
        prompt = _build_summary_prompt(drive_file=drive_file, extracted=extracted)
        result = await self._llm.call(
            tier=tier,
            teacher_id=teacher_id,
            prompt=prompt,
            purpose=f"{drive_file.category}_summary",
            max_output_tokens=600,
        )

        return ProcessingResult(
            artifact_type="markdown_summary",
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
        """Phase 4b: text-only. Vision/audio routing in later phases."""
        if drive_file.mime_type not in TEXT_SUMMARY_MIMES and not _filename_is_text(
            drive_file.filename
        ):
            raise UnsupportedFormatError(
                f"Phase 4b only routes text MIME types; got {drive_file.mime_type!r}",
                context={"filename": drive_file.filename},
            )
        return TaskTier.SUMMARY_CHEAP


def _filename_is_text(filename: str) -> bool:
    return filename.lower().endswith(
        (".docx", ".xlsx", ".pptx", ".pdf", ".txt", ".md", ".markdown")
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
        "你是教師助手，請將以下「{category}」資料整理為 markdown 格式的精要摘要。\n"
        "- 學期：{semester}\n"
        "- 學生（已匿名化）：{pseudo}\n"
        "- 檔名：{filename}\n\n"
        "請輸出三段：\n"
        "1. **主題**（1-2 句）\n"
        "2. **觀察重點**（3-5 個 bullet）\n"
        "3. **教師值得關注的細節**（簡短說明）\n\n"
        "原始內容：\n----\n{content}\n----"
    ).format(
        category=category_zh,
        semester=drive_file.semester_label,
        pseudo=drive_file.student_pseudo_id,
        filename=drive_file.filename,
        content=extracted.text,
    )
