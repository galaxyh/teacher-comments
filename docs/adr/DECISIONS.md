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
- **Rationale**: All 13 questions deliberated with explicit cost / complexity / risk trade-offs in chat. User selected recommended options on most (Min UI, mapping wizard, attestation, SQLite, Docker, no auto-schedule, no archive, single-account); diverged from recommendation on OQ-6 (chose stricter "no account concept" instead of "logout-to-switch") and OQ-10 (chose pure suggestion over retry-once). Cost target ($5/semester) far overshot — predicted ~$1 with Flash Lite default. Out-of-Scope §12 expanded to 18 items to make V1 boundary explicit and prevent scope creep.
- **Files**: `docs/PRD.md` (full rewrite to v0.2)
- **Commit**: _fill after commit_
- **Lesson**: None yet — implementation TODOs (T-1 through T-10) tracked in PRD §13 will surface lessons during build.

### D-2026-05-10-02 Adopt PRD v0.1 with 7 locked baseline decisions
- **Decision**: Lock 7 architectural baselines for the teacher comments system (D1-D7 in `docs/PRD.md` §2): (D1) personal cloud single-user SaaS; (D2) Python/FastAPI backend + Next.js frontend; (D3) PII anonymization before any LLM call; (D4) batch trigger with persistent job state machine and teacher-edit protection; (D5) processed artifacts stored server-side, Drive remains read-only; (D6) target scale ~40 students × ~40 docs + 3 audio recordings per teacher per semester; (D7) V1 ships complete, no phased delivery.
- **Rationale**: Captured after a 7-question discussion. Decisions chosen to minimize compliance risk (D3 — minors' PII), avoid over-engineering for unknown scale (D6 baseline), and prevent half-shipped product (D7 — semester continuity is non-negotiable in education context). Stack choice (D2) reflects Python's maturity in LLM tooling and async I/O. Read-only Drive scope (D5) keeps OAuth audit lightweight and avoids write-failure modes. Full PRD: `docs/PRD.md`. Detailed ADR with options-evaluated-and-rejected to follow at `docs/adr/ADR-001-system-foundation.md` after first PRD review.
- **Files**: `docs/PRD.md`, `CLAUDE.md` (added Python stack lessons-learned trigger rules)
- **Commit**: _fill after commit_
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
