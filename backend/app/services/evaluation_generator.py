"""EvaluationGenerator — semester evaluation draft generation (PRD §3.2 Flow C).

Per DESIGN-001 §4.7. The flow:
  1. gather_context: pull all `processed_artifact` rows for (teacher, semester, student)
     across the 3 categories (learning / interaction / work).
  2. generate: build a style-aware prompt → LLMService.call (anonymise → boundary →
     OpenRouter → restore → audit) → persist `semester_evaluation` row.
  3. save_edit: teacher's final version stored in `edited_text` (audit trail —
     `generated_text` preserved per ARCH-001 §3.3).

Prompt design (V1, walking-skeleton):
- Style governs tone instructions
- D12: word count is suggestion-only (300-500 chars), no validation on output
- Categories prefixed `## 學習紀錄` / `## 教師與學生互動紀錄` / `## 作品成果`
- Per-category token budget ~2K (rough cap; LLM may truncate)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.db.write_queue import DBWriteQueue
from app.models import DriveFile, ProcessedArtifact, SemesterEvaluation
from app.models._helpers import gen_uuid, utcnow_iso
from app.services.llm_service import LLMService, TaskTier

logger = logging.getLogger(__name__)


class EvaluationStyle(str, Enum):
    FORMAL = "formal"            # 正式
    ENCOURAGING = "encouraging"  # 鼓勵
    OBJECTIVE = "objective"      # 客觀


# Style → Chinese label + tone instruction
_STYLE_INSTRUCTIONS: Final[dict[EvaluationStyle, tuple[str, str]]] = {
    EvaluationStyle.FORMAL: (
        "正式",
        "語氣專業正式，避免口語；引用具體素材作佐證；用第三人稱稱呼學生。",
    ),
    EvaluationStyle.ENCOURAGING: (
        "鼓勵",
        "語氣溫暖鼓勵，著重學生進步與努力；提及具體成長點；不迴避實情但保持積極。",
    ),
    EvaluationStyle.OBJECTIVE: (
        "客觀",
        "語氣中性客觀；只描述觀察到的事實與結果；避免主觀讚美或批評。",
    ),
}

_CATEGORY_HEADINGS: Final[dict[str, str]] = {
    "learning": "學習紀錄",
    "interaction": "教師與學生互動紀錄",
    "work": "作品成果",
}

# Per-category content cap (chars). Walking-skeleton heuristic;
# Phase 5+ may swap for true tokenizer-aware truncation.
_PER_CATEGORY_CHAR_CAP: Final[int] = 4000


@dataclass
class EvaluationContext:
    seed_text: str
    style: EvaluationStyle
    learning_summaries: list[str]
    interaction_transcripts: list[str]
    work_summaries: list[str]

    def has_any_artifacts(self) -> bool:
        return bool(
            self.learning_summaries
            or self.interaction_transcripts
            or self.work_summaries
        )


@dataclass
class GeneratedEvaluation:
    evaluation_id: str
    text: str             # PII-restored, ready for display
    char_count: int
    style: EvaluationStyle
    llm_cost_usd: Decimal


class NoArtifactsError(Exception):
    """No processed_artifact rows for the requested student × semester.

    Caller (router) maps to 412 Precondition Failed — the teacher needs to run
    file processing first.
    """


class EvaluationGenerator:
    def __init__(
        self,
        *,
        llm: LLMService,
        db_write_queue: DBWriteQueue,
    ) -> None:
        self._llm = llm
        self._queue = db_write_queue

    async def gather_context(
        self,
        *,
        teacher_id: str,
        semester_label: str,
        pseudo_id: str,
        seed_text: str = "",
        style: EvaluationStyle = EvaluationStyle.FORMAL,
    ) -> EvaluationContext:
        """Read processed artifacts for the (teacher, semester, student) tuple.

        Joins on `drive_file` to filter by category — the artifact table itself
        has no semester/student/category fields (those live on drive_file).
        """
        async with get_sessionmaker()() as session:
            rows = (
                await session.execute(
                    select(DriveFile, ProcessedArtifact)
                    .join(
                        ProcessedArtifact,
                        ProcessedArtifact.drive_file_id == DriveFile.id,
                    )
                    .where(
                        DriveFile.teacher_id == teacher_id,
                        DriveFile.semester_label == semester_label,
                        DriveFile.student_pseudo_id == pseudo_id,
                        ProcessedArtifact.state.in_(
                            ("processed", "teacher_edited")
                        ),
                        ProcessedArtifact.content_markdown.isnot(None),
                    )
                )
            ).all()

        learning: list[str] = []
        interaction: list[str] = []
        work: list[str] = []
        for drive_file, artifact in rows:
            content = artifact.content_markdown or ""
            if drive_file.category == "learning":
                learning.append(content)
            elif drive_file.category == "interaction":
                interaction.append(content)
            elif drive_file.category == "work":
                work.append(content)

        return EvaluationContext(
            seed_text=seed_text,
            style=style,
            learning_summaries=learning,
            interaction_transcripts=interaction,
            work_summaries=work,
        )

    async def generate(
        self,
        *,
        teacher_id: str,
        semester_label: str,
        pseudo_id: str,
        seed_text: str,
        style: EvaluationStyle,
    ) -> GeneratedEvaluation:
        """Full pipeline: gather → build prompt → LLM → restore → persist."""
        context = await self.gather_context(
            teacher_id=teacher_id,
            semester_label=semester_label,
            pseudo_id=pseudo_id,
            seed_text=seed_text,
            style=style,
        )
        if not context.has_any_artifacts():
            raise NoArtifactsError(
                "No processed artifacts for this student × semester — "
                "run file processing first"
            )

        prompt = _build_evaluation_prompt(context=context, pseudo_id=pseudo_id)
        result = await self._llm.call(
            tier=TaskTier.EVALUATION_QUALITY,
            teacher_id=teacher_id,
            prompt=prompt,
            purpose="evaluation_draft",
            max_output_tokens=800,
        )

        evaluation_id = await self._upsert_evaluation(
            teacher_id=teacher_id,
            semester_label=semester_label,
            pseudo_id=pseudo_id,
            seed_text=seed_text,
            style=style,
            generated_text=result.output_text,
            llm_model=result.model_used,
            llm_cost_usd=float(result.cost_usd),
        )

        return GeneratedEvaluation(
            evaluation_id=evaluation_id,
            text=result.output_text,
            char_count=len(result.output_text),
            style=style,
            llm_cost_usd=result.cost_usd,
        )

    async def save_edit(
        self, *, evaluation_id: str, edited_text: str
    ) -> SemesterEvaluation:
        """Persist teacher's edited version. Preserves `generated_text` (audit trail)."""
        async def update(session: AsyncSession) -> SemesterEvaluation:
            row = await session.get(SemesterEvaluation, evaluation_id)
            if row is None:
                raise ValueError(f"No semester_evaluation with id={evaluation_id!r}")
            row.edited_text = edited_text
            row.edited_at = utcnow_iso()
            return row

        return await self._queue.submit(update)

    async def get(self, *, evaluation_id: str) -> SemesterEvaluation | None:
        async with get_sessionmaker()() as session:
            return await session.get(SemesterEvaluation, evaluation_id)

    # ── internals ────────────────────────────────────────────────

    async def _upsert_evaluation(
        self,
        *,
        teacher_id: str,
        semester_label: str,
        pseudo_id: str,
        seed_text: str,
        style: EvaluationStyle,
        generated_text: str,
        llm_model: str,
        llm_cost_usd: float,
    ) -> str:
        """UPSERT — `regenerate` updates the same row to keep one evaluation per
        (teacher, semester, student) triple (uniqueness enforced by schema)."""
        async def upsert(session: AsyncSession) -> str:
            existing = (
                await session.execute(
                    select(SemesterEvaluation).where(
                        SemesterEvaluation.teacher_id == teacher_id,
                        SemesterEvaluation.semester_label == semester_label,
                        SemesterEvaluation.student_pseudo_id == pseudo_id,
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                new_id = gen_uuid()
                session.add(
                    SemesterEvaluation(
                        id=new_id,
                        teacher_id=teacher_id,
                        semester_label=semester_label,
                        student_pseudo_id=pseudo_id,
                        seed_text=seed_text,
                        style=style.value,
                        generated_text=generated_text,
                        llm_model=llm_model,
                        llm_cost_usd=llm_cost_usd,
                    )
                )
                return new_id

            # Regenerate: replace generated_text + cost; clear stale edit
            existing.seed_text = seed_text
            existing.style = style.value
            existing.generated_text = generated_text
            existing.llm_model = llm_model
            existing.llm_cost_usd = llm_cost_usd
            existing.edited_text = None
            existing.edited_at = None
            existing.generated_at = utcnow_iso()
            return existing.id

        return await self._queue.submit(upsert)


# ── Prompt builder ─────────────────────────────────────────────


def _build_evaluation_prompt(
    *, context: EvaluationContext, pseudo_id: str
) -> str:
    """Compose the full prompt the LLM sees.

    Note: context strings already passed through ProcessingPipeline → are PII-restored
    (display-ready). LLMService will re-anonymise before the actual API call, so any
    restored names get replaced with stable pseudonyms before leaving the system.
    """
    style_label, style_instruction = _STYLE_INSTRUCTIONS[context.style]

    sections: list[str] = []
    for items, key in (
        (context.learning_summaries, "learning"),
        (context.interaction_transcripts, "interaction"),
        (context.work_summaries, "work"),
    ):
        if not items:
            continue
        joined = "\n\n".join(items)
        if len(joined) > _PER_CATEGORY_CHAR_CAP:
            joined = joined[:_PER_CATEGORY_CHAR_CAP] + "\n…（已截斷）"
        sections.append(f"## {_CATEGORY_HEADINGS[key]}\n{joined}")

    sections_text = "\n\n".join(sections)

    return (
        "你是教師助手。請根據以下素材，為學生撰寫一份{style_label}風格的學期評語。\n"
        "\n"
        "風格指引：{style_instruction}\n"
        "\n"
        "字數建議：300-500 字（不嚴格驗證；以表達完整為優先）。\n"
        "\n"
        "教師的評價種子（請以此為主軸，素材作佐證）：\n"
        "{seed}\n"
        "\n"
        "學生：{pseudo}（已匿名化）\n"
        "\n"
        "{sections}\n"
        "\n"
        "請輸出評語本文（不要附加標題或前言；直接以教師口吻寫一段）："
    ).format(
        style_label=style_label,
        style_instruction=style_instruction,
        seed=context.seed_text or "（無，請依素材總結）",
        pseudo=pseudo_id,
        sections=sections_text,
    )
