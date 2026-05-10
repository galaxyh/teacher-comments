"""PIIAnonymizer + boundary tripwire tests.

Per security.md "Anonymize-Restore Round-Trip" testing strategy:
1. Anonymizer detection rate ≥ 95% on PII test corpus
2. Round-trip fidelity 100% — anonymize+restore returns the original
3. Boundary regex catches anonymizer's known gaps (zero false negatives on
   the boundary-known patterns)
"""

from __future__ import annotations

import subprocess

import pytest

from app.services.pii_anonymizer import PIIAnonymizer, no_pii_in_anonymized


@pytest.fixture
async def anonymizer(isolated_env, write_queue):
    """Anonymizer wired to a real test DB through the write queue."""
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd="/home/steven/projects/teacher-comments/backend",
        capture_output=True,
    )
    # Seed a teacher row so FK passes
    from app.models import Teacher

    async def insert_teacher(session) -> str:
        t = Teacher(
            id="test-teacher-1",
            google_sub="test-sub",
            email="t@example.com",
        )
        session.add(t)
        return "test-teacher-1"

    await write_queue.submit(insert_teacher)
    return PIIAnonymizer(db_write_queue=write_queue)


# ── Boundary tripwire (cheap, no DB) ─────────────────────────────


class TestBoundaryTripwire:
    @pytest.mark.parametrize(
        "anonymized_text, expected_clean",
        [
            ("S001 表現優異", True),
            ("聯絡方式：S001 的家長 P001", True),
            ("打 0912345678 給家長", False),       # mobile leak
            ("聯絡 02-12345678 學校", False),       # landline leak
            ("email teacher@school.edu.tw", False),  # email leak
            ("ID: A123456789", False),                  # TW national ID leak
            ("住在台北市 — no PII here", True),
        ],
    )
    def test_boundary_pattern_matrix(
        self, anonymized_text: str, expected_clean: bool
    ) -> None:
        assert no_pii_in_anonymized(anonymized_text) is expected_clean


# ── End-to-end anonymise/restore (requires DB) ────────────────────


@pytest.mark.asyncio
class TestAnonymizeRestore:
    async def test_phone_round_trip(self, anonymizer: PIIAnonymizer) -> None:
        text = "請打 0912345678 聯絡家長"
        result = await anonymizer.anonymize(text=text, teacher_id="test-teacher-1")
        assert "0912345678" not in result.anonymized_text
        assert result.replacements == 1
        assert result.new_mappings_added == 1
        assert "PH001" in result.anonymized_text

        # Round-trip
        restored = await anonymizer.restore(
            text=result.anonymized_text, teacher_id="test-teacher-1"
        )
        assert "0912345678" in restored

    async def test_stable_pseudonym_across_calls(self, anonymizer: PIIAnonymizer) -> None:
        """Same value on two separate calls → same pseudonym."""
        r1 = await anonymizer.anonymize(
            text="0912345678 was the number", teacher_id="test-teacher-1"
        )
        r2 = await anonymizer.anonymize(
            text="Number again: 0912345678", teacher_id="test-teacher-1"
        )
        assert r2.new_mappings_added == 0
        # Both texts contain the same pseudonym
        ps1 = next(t for t in r1.anonymized_text.split() if t.startswith("PH"))
        ps2 = next(t for t in r2.anonymized_text.split() if t.startswith("PH"))
        assert ps1 == ps2

    async def test_dedupe_within_one_call(self, anonymizer: PIIAnonymizer) -> None:
        """Same value appearing N times → 1 mapping, N replacements."""
        text = "Email a@b.com or a@b.com or a@b.com"
        result = await anonymizer.anonymize(text=text, teacher_id="test-teacher-1")
        assert result.replacements == 3
        assert result.new_mappings_added == 1
        # All replacements use same pseudonym
        assert result.anonymized_text.count("EM001") == 3

    async def test_multiple_pii_types(self, anonymizer: PIIAnonymizer) -> None:
        text = (
            "聯絡 0912345678 / 02-12345678 / email t@s.edu / ID A123456789"
        )
        result = await anonymizer.anonymize(text=text, teacher_id="test-teacher-1")
        # 4 separate PII items → 4 unique pseudonyms
        assert result.replacements == 4
        assert result.new_mappings_added == 4
        anonymized = result.anonymized_text
        # No raw PII left
        assert "0912345678" not in anonymized
        assert "02-12345678" not in anonymized
        assert "t@s.edu" not in anonymized
        assert "A123456789" not in anonymized
        # Boundary check passes after anonymisation
        assert no_pii_in_anonymized(anonymized) is True

    async def test_restore_unknown_pseudonym_left_literal(
        self, anonymizer: PIIAnonymizer
    ) -> None:
        """Per security.md: restore must not silently drop unknown pseudonyms."""
        text = "Reference S999 which has no mapping"
        restored = await anonymizer.restore(text=text, teacher_id="test-teacher-1")
        # Pattern matched but no mapping → literal preserved
        assert "S999" in restored

    async def test_no_pii_returns_unchanged(self, anonymizer: PIIAnonymizer) -> None:
        text = "Just plain text with no PII at all."
        result = await anonymizer.anonymize(text=text, teacher_id="test-teacher-1")
        assert result.anonymized_text == text
        assert result.replacements == 0
        assert result.new_mappings_added == 0
