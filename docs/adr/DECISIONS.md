# teacher-comments Decisions Log

> **Lightweight chronological log of design decisions.**
>
> - **ADRs** (`docs/adr/ADR-XXX.md`) — heavy decisions requiring evaluation, options, consequences
> - **This log** — everything else (config tweaks, tool selections, small refactors, reversals)
> - **Commits** — atomic implementation; this log indexes the *why* across multiple commits
>
> **Rules:**
> 1. Append-only — never edit past entries. Reverse via new entry citing the old one.
> 2. ID format: `D-YYYY-MM-DD-NN` (NN = sequence within that day). IDs never reused.
> 3. Status tags: active (no tag), `[REVERSED]`, `[SUPERSEDED]`, `[DEPRECATED]`.
> 4. When reversing an old decision: new entry MUST have `Reverses:` line; old entry MUST be edited only to add `Reversed by:` (the only allowed edit).
> 5. Grep-friendly: include relevant keywords in `Decision` line for future searchability.

---

## 2026-05-10

### D-2026-05-10-08 Implementation Phase 3 — PII Anonymizer + LLM Service chokepoints; lookup_hash schema refinement; alembic async commit fix
- **Decision**: Implement V1 chokepoints per ARCH-001 §4.1 invariants:
  (a) `app/services/pii_anonymizer.py` — regex layer (TW phone / email / TW national ID) with stable per-(teacher, pii_type) pseudonyms (S/PH/EM/NID/...), in-process cache, deterministic `lookup_hash` (HMAC-SHA-256 keyed with PII_ENCRYPTION_KEY) for O(1) "have we seen this plaintext before" queries — random-nonce AES-GCM kept for at-rest encryption.
  (b) `app/adapters/openrouter_client.py` — openai SDK pointed at OpenRouter; classified errors (`LLMRateLimitError` / `LLMTimeoutError`) using two-level (typed-attr + regex) per framework-gotcha.md.
  (c) `app/services/llm_service.py` — single chokepoint enforcing anonymise → boundary trip-wire (`no_pii_in_anonymized`, security.md Layer 2) → OpenRouter call → restore → audit. PII boundary trip raises `PIILeakageError` AND writes `system_event(pii_leakage_detected, severity=critical)` AND logs to stderr — three-channel alerting per security.md "boundary firing is a real incident" rule.
  Also adds new alembic migration `20260510_0002` introducing `pii_mapping.lookup_hash` (deterministic) and replacing the `UNIQUE (teacher_id, pii_type, original_value_encrypted)` constraint with `UNIQUE (teacher_id, pii_type, lookup_hash)`. Also fixes a previously-undetected bug in `alembic/env.py`: standard async template missing explicit `await connection.commit()`, silently dropping `alembic_version` updates (would have surfaced on Phase 4 migration; caught here).
- **Rationale**: Random-nonce AES-GCM (chosen for at-rest pattern hiding) makes the original schema's `UNIQUE` constraint un-enforceable — same plaintext encrypts to different ciphertexts each call. Without `lookup_hash`, "have we already mapped this PII?" is O(n) decrypt-and-compare per anonymise call (~200ms at design scale, unacceptable in batch). HMAC-SHA-256 with the existing PII key adds nothing to the trust scope (compromise the key, you compromise both) but gives O(1) lookup. Schema migration written as a NEW alembic revision (not edit of 0001) per engineering-process.md governance — even on greenfield project, append-only migration history communicates "we discovered X during implementation" honestly. The alembic env.py async commit fix is critical: without it, ALL future migrations would silently re-run from scratch and collide; documented as new entry in `framework-gotcha.md`.
- **Files**: `backend/alembic/env.py`, `backend/alembic/versions/20260510_0002_add_pii_lookup_hash.py`, `backend/app/models/pii_mapping.py`, `backend/app/services/pii_anonymizer.py`, `backend/app/adapters/openrouter_client.py`, `backend/app/services/llm_service.py`, `backend/tests/unit/test_pii_anonymizer.py`, `backend/tests/integration/test_llm_service.py`, `~/.claude/lessons-learned/framework-gotcha.md`, `~/.claude/lessons-learned/README.md`
- **Commit**: _fill after commit_
- **Lesson**: Recorded in `framework-gotcha.md` "Alembic Async env.py Silently Drops Migrations Without Explicit Commit" — the bug was hidden in Phase 1 (only one migration, only DDL which SQLite implicit-commits) and surfaced when Phase 3's second migration's `alembic_version` UPDATE was lost. README's framework-gotcha count incremented from 5→6 per feedback rule.

### D-2026-05-10-07 Implementation Phase 2 — OAuth happy path (login / callback / logout / /me)
- **Decision**: Implement V1 OAuth flow: stateless signed-cookie sessions (itsdangerous, NOT Redis), `app/core/session.py` with purpose-bound salts ("session" vs "oauth-state"), `app/adapters/google_oauth.py` wrapping authlib's `AsyncOAuth2Client` with `access_type=offline` + `prompt=consent` baked in, `app/services/auth_service.py` enforcing V1 single-user rule (D1 / A6) at the application layer, `app/services/audit_logger.py` writing `system_event` rows through DBWriteQueue, `app/routers/auth.py` exposing `/auth/login`, `/auth/callback` (CSRF-checked via state cookie), `/auth/logout`, `/me`. Defers attestation flow (D17) and Drive scan to later phases.
- **Rationale**: Walking-skeleton step 2 — OAuth had to come before any feature touching Google Drive or any user-scoped LLM call, since both require `teacher_id` from the session. Single-user enforcement implemented at the app layer (not DB CHECK) to keep schema V2-compatible (V2 may relax to multi-user with same schema). `prompt=consent` baked into the adapter prevents the most common Google OAuth gotcha — refresh_token is only issued on first consent or with explicit `prompt=consent`; without it the system silently can't refresh access tokens after the first login. itsdangerous + purpose-bound salts chosen over server-side session store: D1 single-user + D16 SQLite mean Redis would violate "zero external runtime deps."
- **Files**: `backend/app/core/session.py`, `backend/app/adapters/__init__.py`, `backend/app/adapters/google_oauth.py`, `backend/app/services/audit_logger.py`, `backend/app/services/auth_service.py`, `backend/app/schemas/__init__.py`, `backend/app/schemas/auth.py`, `backend/app/routers/auth.py`, `backend/app/main.py`, `backend/tests/unit/test_session.py`, `backend/tests/integration/test_auth_flow.py`
- **Commit**: `823e0c6`
- **Lesson**: To file in `framework-gotcha.md` after Phase 3 (Drive sync) confirms the refresh-token path actually works end-to-end: "Google OAuth `access_type=offline` is necessary but not sufficient — `prompt=consent` is also required to guarantee a refresh_token is issued every time, otherwise the second login silently returns a token bundle with empty refresh_token and the system can't refresh access tokens unattended."

### D-2026-05-10-06 Implementation phase started — backend Phase 1 (foundations)
- **Decision**: Begin V1 implementation. Phase 1 scope = backend foundations only (no auth/LLM/Drive yet): pyproject.toml + uv lock, `app/config.py` Pydantic Settings, `app/core/exceptions.py` hierarchy, `app/db/session.py` (lazy async engine + WAL PRAGMAs via SQLAlchemy event listener), `app/db/write_queue.py` (single-writer queue per ARCH-001 §6.5), all 8 SQLAlchemy models, `app/services/encryption.py` (AES-256-GCM), Alembic init + initial migration covering all 8 tables, FastAPI app with /healthz + /readyz, Dockerfile + docker-compose.yml + fly.toml. Test foundation: 16 unit + integration tests covering encryption round-trip / tamper detection / AD binding / boundary cases, write queue serialisation / exception propagation / FIFO ordering / lifecycle, and TestClient-driven /healthz /readyz.
- **Rationale**: Walking skeleton requires foundations before vertical slices. Building auth + LLM + Drive on a missing/buggy DBWriteQueue or encryption layer would force constant retrofitting. Phase 1 establishes the chokepoints (LLM Service singularity, DBWriteQueue serialisation, AES-GCM helpers) called out in ARCH-001 §4.1 invariants. Lazy engine + queue singletons (resettable in tests) chosen over module-level eager init to avoid the "fixture env vars don't take effect because module imported earlier" antipattern that would otherwise plague every integration test. Manual first migration (not autogenerate) for precise CHECK constraint / index control on SQLite. uv preferred over pip-tools (already endorsed in ARCH-001 §2.1; ~10x faster sync). All ARCH-001 §5.3 env vars enumerated in `.env.example` + validated at startup (base64 + 32-byte enforcement on encryption keys).
- **Files**: `backend/pyproject.toml`, `backend/.env.example`, `backend/.dockerignore`, `backend/Dockerfile`, `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/20260510_0001_initial_schema.py`, `backend/app/__init__.py`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/core/__init__.py`, `backend/app/core/exceptions.py`, `backend/app/core/lifespan.py`, `backend/app/db/__init__.py`, `backend/app/db/session.py`, `backend/app/db/write_queue.py`, `backend/app/models/*.py` (9 files), `backend/app/services/__init__.py`, `backend/app/services/encryption.py`, `backend/app/routers/__init__.py`, `backend/app/routers/system.py`, `backend/tests/conftest.py`, `backend/tests/unit/test_encryption.py`, `backend/tests/unit/test_write_queue.py`, `backend/tests/integration/test_health.py`, `docker-compose.yml`, `fly.toml`, `.gitignore`
- **Commit**: `b270b74`
- **Lesson**: None yet — implementation will surface lessons during Phase 2 (auth) and Phase 3 (LLM/PII chokepoint).

### D-2026-05-10-05 Add `system_event` audit table (per OAQ-5 / DESIGN-001 §2.5)
- **Decision**: Add `system_event` table to PRD §4.2 schema for non-LLM audit events: `oauth_login` / `oauth_logout` / `oauth_revoked` / `attestation_signed` / `attestation_invalidated` / `key_rotated` / `schema_migrated` / `batch_started` / `batch_completed` / `batch_failed` / `pii_leakage_detected`. Two indexes on `(teacher_id, created_at)` and `(event_type)`. Resolves ARCH-001 OAQ-5.
- **Rationale**: Non-LLM events were previously only in stdout logs (ephemeral). For debugging "why did batch fail at 03:42 last week?" / "did the user actually attest?" / security incident review, persistent structured audit is high-leverage at low cost (one small table). Especially the `pii_leakage_detected` event is a critical alert channel — it must never be silently lost. Additive change, no decision reversal.
- **Files**: `docs/PRD.md` §4.2, `docs/DESIGN-001-detailed-design.md` §2.5, §4.8, §9
- **Commit**: `04050bc`

### D-2026-05-10-04 Add `unprocessable` (terminal) state separate from `failed` (retriable)
- **Decision**: Refine PRD §4.3 file processing state machine — split previously monolithic `failed` into two states: `failed` (retriable; auto-retry up to 3x with exponential backoff for rate_limit / timeout / API 5xx) and `unprocessable` (terminal; not auto-retried; manual retry only with UI warning, for encrypted_file / corrupt_file / unsupported_format / daily_quota_exhausted). Updates `processed_artifact.state` CHECK constraint, error hierarchy in DESIGN-001 §6, and worker error→state mapping in DESIGN-001 §6.3. Resolves ARCH-001 OAQ-1.
- **Rationale**: Lessons-learned `architecture.md` "Distinguish Terminal Failures from Retriable Failures" — a single `failed` state causes bulk retries to hammer permanently-broken files (encrypted PDFs, corrupt docx, unsupported formats), wasting LLM budget on hopeless cases. Observed pattern in past projects. PRD §4.3 originally had only `failed`; this is a refinement (additive new state, no semantics removed) but does change behavior for previously-failing terminal cases. Not a full reversal of D4 (batch + state machine + edit protection still in force) — just refines the state set.
- **Files**: `docs/PRD.md` §4.2 (schema CHECK constraint), §4.3 (state diagram + key-design-points), `docs/DESIGN-001-detailed-design.md` §2.1, §3, §6
- **Commit**: `04050bc`

### D-2026-05-10-03 Resolve 13 Open Questions; PRD v0.2 with 10 refinement decisions (D8-D17)
- **Decision**: Resolved all 13 Open Questions (10 from v0.1 §13 + 3 author-added) across 4 review rounds. Locks 10 additional architectural decisions documented as D8-D17 in `docs/PRD.md` §2.2:
  (D8) Tier-based LLM routing with 4 tiers (`summary_cheap`, `vision_cheap`, `audio_standard`, `evaluation_quality`); models settable via Settings.
  (D9) V1 default = `google/gemini-2.5-flash-lite` for all tiers (cost ~$1/semester).
  (D10) STT exclusively via OpenRouter; Whisper API as V2 fallback only.
  (D11) Audio pipeline auto-detects speaker count; outputs monologue or dialog format accordingly.
  (D12) Evaluation styles = formal / encouraging / objective (replaces prior "neutral"); word count 300-500 is prompt suggestion only, no validation.
  (D13) PII Min UI scope = view + rename pseudonym + manual mapping addition; regex rule editor → V2.
  (D14) Drive folder mapping wizard for non-standard naming; mapping persisted per-teacher.
  (D15) V1 ships as Docker container + docker-compose.yml + fly.toml; multi-target deploy.
  (D16) Database = SQLite + WAL mode + aiosqlite driver; DB-write serialization queue.
  (D17) Onboarding requires parental-consent attestation checkbox; recorded in `teacher.consent_attestation_at`.
  Compliance Assumptions extended with A6 (single-account assumption).
- **Rationale**: All 13 questions deliberated with explicit cost / complexity / risk trade-offs in chat. User selected recommended options on most (Min UI, mapping wizard, attestation, SQLite, Docker, no auto-schedule, no archive, single-account); diverged from recommendation on OQ-6 (chose stricter "no account concept" instead of "logout-to-switch") and OQ-10 (chose pure suggestion over retry-once). Cost target ($5/semester) far overshot — predicted ~$1 with Flash Lite default. PRD §12 (Out of Scope) expanded to 18 items to make V1 boundary explicit and prevent scope creep.
- **Files**: `docs/PRD.md` (full rewrite to v0.2)
- **Commit**: `95f2962`
- **Lesson**: None yet — implementation TODOs (T-1 through T-10) tracked in PRD §13 will surface lessons during build.

### D-2026-05-10-02 Adopt PRD v0.1 with 7 locked baseline decisions
- **Decision**: Lock 7 architectural baselines for the teacher comments system (D1-D7 in `docs/PRD.md` §2): (D1) personal cloud single-user SaaS; (D2) Python/FastAPI backend + Next.js frontend; (D3) PII anonymization before any LLM call; (D4) batch trigger with persistent job state machine and teacher-edit protection; (D5) processed artifacts stored server-side, Drive remains read-only; (D6) target scale ~40 students × ~40 docs + 3 audio recordings per teacher per semester; (D7) V1 ships complete, no phased delivery.
- **Rationale**: Captured after a 7-question discussion. Decisions chosen to minimize compliance risk (D3 — minors' PII), avoid over-engineering for unknown scale (D6 baseline), and prevent half-shipped product (D7 — semester continuity is non-negotiable in education context). Stack choice (D2) reflects Python's maturity in LLM tooling and async I/O. Read-only Drive scope (D5) keeps OAuth audit lightweight and avoids write-failure modes. Full PRD: `docs/PRD.md`. Detailed ADR with options-evaluated-and-rejected to follow at `docs/adr/ADR-001-system-foundation.md` after first PRD review.
- **Files**: `docs/PRD.md`, `CLAUDE.md` (added Python stack lessons-learned trigger rules)
- **Commit**: `95f2962` (PRD v0.1 was an intermediate session draft superseded by v0.2 in same commit; D1-D7 content lives in PRD §2.1 of `95f2962`)
- **Lesson**: None yet — will surface during implementation.

### D-2026-05-10-01 Adopt governance kit (DECISIONS.md + protocols + link-check CI)
- **Decision**: Install governance kit from `code-agent-skill-command/templates/governance-kit/`. Establishes 三層決策治理 (ADR / DECISIONS.md / commit), Pre-Action Verification, Reversal Protocol, Sub-Agent Verification, plus lychee two-stage markdown link CI.
- **Rationale**: Project is greenfield; cheaper to install governance now than retrofit after design pivots accumulate. Lychee CI specifically chosen for `--include-fragments` anchor validation (the main reason over alternatives like markdown-link-check).
- **Files**: `docs/adr/DECISIONS.md`, `.github/workflows/link-check.yml`, `lychee.toml`, `.lycheeignore`, `.gitignore`, `CLAUDE.md`, `README.md`
- **Commit**: `2e0d2b6`

---

## How to add a new entry

1. Determine date (today): `date +%Y-%m-%d`
2. Find next NN: `grep -c "^### D-$(date +%Y-%m-%d)" docs/adr/DECISIONS.md` and add 1
3. Write entry following template above
4. Commit DECISIONS.md update in SAME commit as the implementation (when possible)
5. Backfill commit hash if entry is part of the commit creating itself (self-referential)

## How to reverse a decision

1. **Add new entry** with `Reverses: D-XXX` line; explain root cause in **Rationale**
2. **Edit old entry** — only allowed edit: add `[REVERSED]` to title and `Reversed by: D-YYY` line
3. **Commit message** — include `Reverses: <old-commit-hash>` line
4. **Consider lessons-learned** — if this is a repeated mistake, write/update a lesson

## Anti-patterns

- ❌ Editing past entries (only `[REVERSED]` + `Reversed by` allowed)
- ❌ Reusing or renumbering IDs
- ❌ Reversal entry without `Reverses:` field
- ❌ Reversal rationale of "user changed mind" — must explain why original was wrong
- ❌ Squashing multiple decisions into one entry — each decision stands alone
