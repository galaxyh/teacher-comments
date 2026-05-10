"""PII anonymisation chokepoint #1 (security.md "Anonymize-Restore Round-Trip").

Two-layer protection plan:
- LAYER 1 (this module): replace PII with stable pseudonyms BEFORE any LLM call,
  restore after. Backed by `pii_mapping` rows; encryption is per-record AES-GCM.
- LAYER 2 (LLMService): boundary check tripwire — known-PII regex on the anonymised
  text immediately before HTTP POST. See `pii_boundary.no_pii_in_anonymized`.

Detection layers (V1):
- Regex layer: TW phone (mobile / landline), email, TW national ID
- Strong-signal name layer: deferred to Phase 4 (Drive sync) where folder-name
  sources of truth become available. For Phase 3 walking skeleton, names are
  detected only via manually-added mappings (PRD §4 D13 "PII Min UI" — manual
  add path).

Lookup architecture (per migration 20260510_0002 / D-2026-05-10-08):
- `lookup_hash` = HMAC-SHA-256(plaintext) keyed with PII_ENCRYPTION_KEY.
  Deterministic so we can ask "have we seen this plaintext before?" in O(1).
- `original_value_encrypted` = AES-256-GCM (random nonce). Used only to restore
  back to plaintext when displaying to the teacher.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.db.write_queue import DBWriteQueue
from app.models import PIIMapping
from app.models._helpers import gen_uuid
from app.services.encryption import Cipher, get_pii_cipher

logger = logging.getLogger(__name__)


class PIIType(str, Enum):
    STUDENT_NAME = "student_name"
    STUDENT_ID = "student_id"
    PARENT_NAME = "parent_name"
    PHONE = "phone"
    EMAIL = "email"
    TW_NATIONAL_ID = "other"  # stored under 'other' since schema doesn't have a TID enum
    OTHER_NAME = "other_name"
    OTHER = "other"


# Pseudonym prefix per PII type. Stable across the codebase — UI / tests rely on these.
PSEUDONYM_PREFIX: Final[dict[PIIType, str]] = {
    PIIType.STUDENT_NAME: "S",
    PIIType.STUDENT_ID: "SID",
    PIIType.PARENT_NAME: "P",
    PIIType.PHONE: "PH",
    PIIType.EMAIL: "EM",
    PIIType.OTHER_NAME: "T",
    PIIType.OTHER: "O",
    PIIType.TW_NATIONAL_ID: "NID",
}


# Detection regex set. Order matters: longer/more-specific patterns first to avoid
# email being shredded by phone regex via overlap.
@dataclass(frozen=True)
class DetectionPattern:
    pii_type: PIIType
    regex: re.Pattern[str]


DETECTION_PATTERNS: Final[tuple[DetectionPattern, ...]] = (
    # email — `\.[a-z]{2,}` ASCII TLD; matches typical school accounts
    DetectionPattern(
        PIIType.EMAIL,
        re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    ),
    # TW national ID: 1 letter + 9 digits. Surrounded by word boundary to avoid
    # matching mid-string in arbitrary alphanumeric blobs.
    DetectionPattern(
        PIIType.TW_NATIONAL_ID,
        re.compile(r"\b[A-Z]\d{9}\b"),
    ),
    # TW mobile: 09 + 8 digits
    DetectionPattern(
        PIIType.PHONE,
        re.compile(r"\b09\d{8}\b"),
    ),
    # TW landline: 0X-XXXXXXX or 0XX-XXXXXXX
    DetectionPattern(
        PIIType.PHONE,
        re.compile(r"\b0\d{1,2}-\d{6,8}\b"),
    ),
)


@dataclass(frozen=True)
class AnonymizeResult:
    anonymized_text: str
    replacements: int
    new_mappings_added: int


# ────────────────────────────────────────────────────────────────────


class PIIAnonymizer:
    """Stateful chokepoint. Maintains an in-process cache keyed by (teacher_id, hash)
    so repeated calls within the same batch don't hit the DB.

    Cache invalidation is deliberate: any new mapping created via DB write also
    seeds the cache, and the cache lifetime is bounded by the process. Restarts
    reload from DB on first lookup.
    """

    def __init__(
        self, db_write_queue: DBWriteQueue, cipher: Cipher | None = None
    ) -> None:
        self._queue = db_write_queue
        self._cipher = cipher  # If None, resolved lazily via get_pii_cipher() per call
        # Cache shape: (teacher_id, lookup_hash) → (pseudonym, pii_type)
        self._fwd_cache: dict[tuple[str, str], tuple[str, PIIType]] = {}
        # Cache shape: (teacher_id, pseudonym) → (display_name, plaintext)
        self._rev_cache: dict[tuple[str, str], tuple[str | None, str]] = {}
        # Per-call counter; reset at start of each anonymize() call. Used to compute
        # AnonymizeResult.new_mappings_added without polluting cache shape.
        self._fresh_inserts_in_call = 0

    # ── Anonymise / restore ────────────────────────────────────────

    async def anonymize(self, *, text: str, teacher_id: str) -> AnonymizeResult:
        """Detect PII via regex, substitute with stable pseudonyms, return result.

        Detection results are deduplicated: if the same value appears multiple
        times in `text`, it gets the same pseudonym (and one INSERT, not N).
        """
        cipher = self._cipher or get_pii_cipher()
        self._fresh_inserts_in_call = 0

        # Step 1: detect — collect (start, end, pii_type, original_value).
        detections = self._detect_all(text)
        if not detections:
            return AnonymizeResult(anonymized_text=text, replacements=0, new_mappings_added=0)

        # Step 2: dedupe + resolve pseudonyms
        resolved: dict[tuple[PIIType, str], str] = {}
        for det in detections:
            key = (det.pii_type, det.value)
            if key not in resolved:
                resolved[key] = await self._resolve_or_create(
                    teacher_id=teacher_id, pii_type=det.pii_type, value=det.value, cipher=cipher
                )

        # Step 3: substitute right-to-left so earlier spans aren't invalidated
        result_text = text
        for det in sorted(detections, key=lambda d: -d.start):
            pseudonym = resolved[(det.pii_type, det.value)]
            result_text = result_text[: det.start] + pseudonym + result_text[det.end :]

        return AnonymizeResult(
            anonymized_text=result_text,
            replacements=len(detections),
            new_mappings_added=self._fresh_inserts_in_call,
        )

    async def restore(self, *, text: str, teacher_id: str) -> str:
        """Substitute pseudonyms back to display_name (or original_value if no display set).

        Idempotent: text without pseudonyms is unchanged. Unknown pseudonym pattern
        matches that have no DB row remain literal — caller should surface a banner
        per security.md anti-pattern guidance ("don't silently drop restoration failures").
        """
        # Pseudonym pattern: prefix (1-3 letters) + 3+ digits. Conservative; won't catch
        # human-formatted text accidentally.
        pseudonym_re = re.compile(r"\b([A-Z]{1,3})(\d{3,})\b")

        async def lookup(pseudonym: str) -> str | None:
            return await self._lookup_pseudonym(teacher_id=teacher_id, pseudonym=pseudonym)

        # Find all candidates in one pass
        candidates = pseudonym_re.findall(text)
        if not candidates:
            return text

        # Map pseudonym → display
        replacements: dict[str, str] = {}
        for prefix, num in set(candidates):
            pseudonym = f"{prefix}{num}"
            display = await lookup(pseudonym)
            if display is not None:
                replacements[pseudonym] = display

        # Substitute
        def repl(m: re.Match[str]) -> str:
            ps = m.group(0)
            return replacements.get(ps, ps)  # leave literal if unknown

        return pseudonym_re.sub(repl, text)

    # ── Internals ───────────────────────────────────────────────────

    @dataclass(frozen=True)
    class _Detection:
        start: int
        end: int
        pii_type: PIIType
        value: str

    def _detect_all(self, text: str) -> list[_Detection]:
        """Run all regex patterns; resolve overlapping matches by keeping the first one."""
        matches: list[PIIAnonymizer._Detection] = []
        used_spans: list[tuple[int, int]] = []

        for pattern in DETECTION_PATTERNS:
            for m in pattern.regex.finditer(text):
                start, end = m.span()
                if any(not (end <= s or start >= e) for s, e in used_spans):
                    continue  # overlaps with already-claimed span
                matches.append(
                    PIIAnonymizer._Detection(
                        start=start, end=end, pii_type=pattern.pii_type, value=m.group(0)
                    )
                )
                used_spans.append((start, end))
        return matches

    def _hash_value(self, value: str) -> str:
        """HMAC-SHA-256 keyed with PII_ENCRYPTION_KEY (re-using key — same trust scope)."""
        from app.config import get_settings
        import base64

        key_b64 = get_settings().pii_encryption_key.get_secret_value()
        key = base64.b64decode(key_b64)
        digest = hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()
        return digest

    async def _resolve_or_create(
        self, *, teacher_id: str, pii_type: PIIType, value: str, cipher: Cipher
    ) -> str:
        """Return pseudonym for (teacher, value). Creates a new mapping if absent."""
        h = self._hash_value(value)
        cache_key = (teacher_id, h)

        if cache_key in self._fwd_cache:
            return self._fwd_cache[cache_key][0]

        # Lookup in DB by hash
        async with get_sessionmaker()() as session:
            existing = await session.execute(
                select(PIIMapping).where(
                    PIIMapping.teacher_id == teacher_id,
                    PIIMapping.lookup_hash == h,
                )
            )
            row = existing.scalar_one_or_none()

        if row is not None:
            self._fwd_cache[cache_key] = (row.pseudonym, PIIType(row.pii_type))
            self._rev_cache[(teacher_id, row.pseudonym)] = (row.display_name, value)
            return row.pseudonym

        # No mapping → allocate new pseudonym number, INSERT
        pseudonym = await self._allocate_pseudonym(teacher_id=teacher_id, pii_type=pii_type)
        encrypted = cipher.encrypt_str(value)

        async def insert(session: AsyncSession) -> str:
            mapping = PIIMapping(
                id=gen_uuid(),
                teacher_id=teacher_id,
                pii_type=pii_type.value,
                lookup_hash=h,
                original_value_encrypted=encrypted,
                pseudonym=pseudonym,
                source="auto",
            )
            session.add(mapping)
            return pseudonym

        await self._queue.submit(insert)
        self._fwd_cache[cache_key] = (pseudonym, pii_type)
        self._rev_cache[(teacher_id, pseudonym)] = (None, value)
        self._fresh_inserts_in_call += 1
        return pseudonym

    async def _allocate_pseudonym(self, *, teacher_id: str, pii_type: PIIType) -> str:
        """Find next free pseudonym number for the (teacher, pii_type) pair.

        Race-free because all writes go through DBWriteQueue (single drainer).
        Reads can happen concurrently but we re-check inside the write step to
        avoid double-allocation.
        """
        prefix = PSEUDONYM_PREFIX[pii_type]
        pattern = f"{prefix}%"  # SQL LIKE
        async with get_sessionmaker()() as session:
            rows = (
                await session.execute(
                    select(PIIMapping.pseudonym).where(
                        PIIMapping.teacher_id == teacher_id,
                        PIIMapping.pseudonym.like(pattern),
                    )
                )
            ).scalars().all()

        used: set[int] = set()
        for ps in rows:
            try:
                used.add(int(ps[len(prefix):]))
            except ValueError:
                continue

        # Pick next free number starting at 1
        n = 1
        while n in used:
            n += 1
        return f"{prefix}{n:03d}"

    async def _lookup_pseudonym(
        self, *, teacher_id: str, pseudonym: str
    ) -> str | None:
        """Resolve pseudonym → display_name (preferred) or decrypted original_value."""
        cache_key = (teacher_id, pseudonym)
        if cache_key in self._rev_cache:
            display, plaintext = self._rev_cache[cache_key]
            return display or plaintext

        async with get_sessionmaker()() as session:
            row = (
                await session.execute(
                    select(PIIMapping).where(
                        PIIMapping.teacher_id == teacher_id,
                        PIIMapping.pseudonym == pseudonym,
                    )
                )
            ).scalar_one_or_none()

        if row is None:
            return None  # caller decides how to surface (banner / log)

        cipher = self._cipher or get_pii_cipher()
        plaintext = cipher.decrypt_str(row.original_value_encrypted)
        self._rev_cache[cache_key] = (row.display_name, plaintext)
        return row.display_name or plaintext


# ────────────────────────────────────────────────────────────────────
# Boundary tripwire (security.md Layer 2)
# ────────────────────────────────────────────────────────────────────

PII_BOUNDARY_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"09\d{8}"),                                      # TW mobile
    re.compile(r"0\d{1,2}-\d{6,8}"),                             # TW landline
    re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),  # email
    re.compile(r"\b[A-Z]\d{9}\b"),                               # TW national ID
    # NOTE: name detection intentionally absent — Chinese names are too variable
    # for a regex catch-net. Rely on PIIAnonymizer's strong-signal detection.
)


def no_pii_in_anonymized(text: str) -> bool:
    """Return False if any boundary pattern matches.

    LLMService calls this immediately before HTTP POST. A False return aborts
    the call and triggers `pii_leakage_detected` in system_event.
    """
    return not any(p.search(text) for p in PII_BOUNDARY_PATTERNS)
