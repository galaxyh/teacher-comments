# Work Plan

| Field | Value |
|-------|-------|
| **Status** | Living document — updated with each phase commit |
| **Date** | 2026-05-10 |
| **Owner** | Steven Chen |
| **Authoritative source for "what's shipped"** | This file + `git log` + [`docs/adr/DECISIONS.md`](adr/DECISIONS.md) |

> **What this is**: a live tracker for **what's done vs not done** at the
> phase / feature level. PRD freezes the V1 spec; ARCH/DESIGN/UIUX/BDD/TDD
> freeze the engineering plan; this doc tracks **execution progress** against
> them. When in doubt, code + git log are authoritative — this doc is the
> human-readable index pointing to specifics.

> **What this is not**: a sprint board (issues / Gantt / calendar) — those
> live in your issue tracker if you use one. This doc captures milestone-level
> truth that survives across sessions.

---

## 1. Status at a glance

| Phase | Scope | State | DECISIONS | Commit |
|------:|-------|:-----:|-----------|--------|
| **1** | Backend foundations (config, exceptions, DB, write queue, models, encryption, alembic, FastAPI app, Docker) | ✅ Shipped | [D-2026-05-10-06](adr/DECISIONS.md) | `b270b74` |
| **2** | OAuth happy path (login / callback / logout / `/me` + single-user enforcement) | ✅ Shipped | [D-2026-05-10-07](adr/DECISIONS.md) | `823e0c6` |
| **3** | PII anonymizer + LLM service chokepoint (two-layer protection) | ✅ Shipped | [D-2026-05-10-08](adr/DECISIONS.md) | `4c990f3` |
| **4a** | Drive auth refresh + 3-level scan + D14 mapping wizard | ✅ Shipped | [D-2026-05-10-09](adr/DECISIONS.md) | `7efad05` |
| **4b** | Document extractors (docx, txt) + ProcessingPipeline + single-file `/file/{id}/process` | ✅ Shipped | [D-2026-05-10-10](adr/DECISIONS.md) | `6bf2dd9` |
| **5**  | EvaluationGenerator + `/eval/*` endpoints | ✅ Shipped | [D-2026-05-10-11](adr/DECISIONS.md) | `27b2cfd` |
| **5alt** | BatchWorker + SSE progress stream | ✅ Shipped | [D-2026-05-10-13](adr/DECISIONS.md) | `4425ff5` |
| **5b** | Extractors xlsx / pptx / pdf | ✅ Shipped | [D-2026-05-10-14](adr/DECISIONS.md) | `f5d9928` |
| **6**  | Frontend Next.js scaffold + login + evaluation editor | ✅ Shipped | [D-2026-05-10-12](adr/DECISIONS.md) | `4aee7ae` |
| **7**  | Frontend batch dashboard + EventSource SSE | ✅ Shipped | [D-2026-05-10-15](adr/DECISIONS.md) | `8721866` |
| **8**  | Onboarding wizard (D17 attest + D14 mapping UI) | ✅ Shipped | [D-2026-05-10-16](adr/DECISIONS.md) | `414e127` |
| **9**  | Vision tier (image extractor + multimodal LLM) | ✅ Shipped | [D-2026-05-10-17](adr/DECISIONS.md) | `a5e2e5d` |
| **10** | Audio STT tier (D10 / D11) | ✅ Shipped | [D-2026-05-10-18](adr/DECISIONS.md) | `98b38e4` |
| **11** | PII Min UI (D13) — list / rename display name / manual aliases | ✅ Shipped | [D-2026-05-10-19](adr/DECISIONS.md) | `27bd470` |
| **12** | Settings page (LLM tier overrides + budget gauge) | ✅ Shipped | [D-2026-05-10-20](adr/DECISIONS.md) | `27bd470` |
| **Hardening** | ruff clean (89→0) + frontend vitest layer | ✅ Shipped | [D-2026-05-10-21](adr/DECISIONS.md) | `2446595` |

**Tally**: 16 phases shipped · 134 tests passing (129 backend pytest + 5 frontend vitest) · 3 alembic migrations · 27 backend endpoints · 7 frontend routes · 7 document extractors.

---

## 2. PRD F-1 ~ F-10 coverage

Mapped against [`docs/PRD.md`](PRD.md) §5 functional requirements.

| Feature | Title | Coverage | Notes / gaps |
|---------|-------|:--------:|--------------|
| **F-1** | OAuth + onboarding attestation | ✅ | Full Google OAuth round-trip, single-user enforcement, attestation `system_event` audit. Edge case: token refresh on 401 — implemented at lib level, not yet exercised in integration test. |
| **F-2** | Drive teaching root selection | ✅ | `/drive/list` + `/onboarding/drive-root` shipped + UI flow. |
| **F-3** | Drive scan + mapping wizard | ✅ | 3-level walk + D14 mapping wizard backend + frontend. Idempotent rescan via `drive_modified_at`. |
| **F-4** | Document → Markdown pipeline | ✅ | docx / xlsx / pptx / pdf / txt extractors + `summary_cheap` LLM tier. |
| **F-5** | Audio → speaker-split transcript | ⚠️ Partial | `audio_standard` tier ships; D11 speaker-count detection delegated to LLM via prompt (not validated against real audio yet). 25MB cap; >25MB audio is `unprocessable` until streaming download lands (Phase 14+). |
| **F-6** | PII anonymizer + Min UI (D13) | ✅ | Two-layer protection (anonymize + boundary tripwire) + Phase 11 Min UI (view / rename / manual aliases). Regex editor remains explicit V2 scope per D13. |
| **F-7** | Batch trigger + status + crash recovery | ✅ | Phase 5alt + Phase 7 UI; `recover_stale_jobs` on lifespan startup. **Out of scope**: in-worker auto-retry on `failed`, `reprocess_pending` overwrite/keep prompt UX (deferred to V1.x — see [§3](#3-not-yet-shipped-v1x-scope) below). |
| **F-8** | Edit protection + reprocess prompt | ⚠️ Partial | `teacher_edited` state exists; `reprocess_pending` per-file UI prompt **not yet** (V1.x). |
| **F-9** | Semester evaluation generation | ✅ | Phase 5 backend + Phase 6 frontend. Style: formal / encouraging / objective per D12; UPSERT on `(teacher, semester, student)`. |
| **F-10** | Browse / edit / download UI + Settings | ⚠️ Partial | `/settings` shipped (Phase 12). **Browsing screens** (`/semester/[label]`, `/student/[pseudo_id]`, `/file/[drive_file_id]`) **not yet** — V1.x scope. Download via direct artifact API exists but no dedicated UI. |

---

## 3. Not yet shipped (V1.x scope)

These are explicitly inside V1's spec but pushed beyond walking-skeleton:

### 3.1 Browsing screens (F-10 partial)
- [ ] `/semester/[label]/page.tsx` — list students under a semester with processing-state badges
- [ ] `/student/[pseudo_id]/page.tsx` — list files per category, status pills, link to evaluation
- [ ] `/file/[drive_file_id]/page.tsx` — file detail view with markdown preview + edit
- [ ] `/evaluation/[semester]/[pseudo_id]/page.tsx` — evaluation detail (currently only `/evaluation/new` exists)

### 3.2 BatchWorker enhancements
- [ ] `GET /batch/preview?semester=X` — preview before commit, with per-file overwrite/keep choice for `reprocess_pending` (originally ARCH-001 §3.2 step 1-7; intentionally folded out of V1 walking-skeleton — track in [D-2026-05-10-13](adr/DECISIONS.md) "out of scope")
- [ ] In-worker auto-retry with exponential backoff on `failed` (10s/60s/300s) — currently leaves `failed` rows for manual retry
- [ ] `failed` → `processing` UI button (manual retry endpoint exists via `/file/{id}/process`; batch-level retry-all-failed not yet)

### 3.3 Settings page splits
The walking-skeleton `/settings` page handles all sub-sections inline. ARCH-001 §2.2's vision splits these into 5 pages:
- [ ] `/settings/llm` (currently inline)
- [ ] `/settings/pii` — actually shipped as `/pii` (top-level), not under `/settings`
- [ ] `/settings/folder-mapping` — currently re-runnable via `/onboarding`
- [ ] `/settings/budget` — currently inline
- [ ] `/settings/account` — currently inline (logout button)

### 3.4 Onboarding wizard splits
Currently one page handles all 4 steps (attest → pick root → mapping → done). ARCH-001 §2.2 vision:
- [ ] `/onboarding/attestation` (deep-linkable for re-sign on version bump)
- [ ] `/onboarding/drive-root` (deep-linkable for "change root")
- [ ] `/onboarding/folder-mapping` (deep-linkable for "redo mapping")

### 3.5 OpenAPI codegen
- [ ] Replace hand-written `frontend/src/lib/api.ts` types with `openapi-typescript` generated types per ARCH-001 §2.3. Triggered when surface area > 20 endpoints (we're at 27 — overdue) OR when 2nd dev joins.

### 3.6 BDD test layer
- [ ] Adopt `pytest-bdd` for high-value happy paths per BDD-001 §5.1. 58 Gherkin scenarios await extraction into `.feature` files + step definitions in `backend/tests/bdd/`.

---

## 4. Hardening pass — done + remaining

### Done
- [x] Backend ruff clean (89 issues → 0 with curated narrow ignores)
- [x] Frontend vitest layer + first 5 tests covering API client error mapping
- [x] DECISIONS.md governance pattern (21 entries, all backfilled)
- [x] CI workflow (`.github/workflows/test.yml`) with auto-skip guards

### Remaining
- [ ] **`scripts/start-test-stack.sh` + `scripts/wait-for-stack.sh`** — referenced by the CI `e2e` job; currently absent → e2e job skips. Need a mock LLM (env-driven) + mock Drive (env-driven) wiring before Playwright is meaningful.
- [ ] **Playwright E2E** — at least 1 happy-path spec (login → onboarding → batch → evaluation) once the mock stack lands.
- [ ] **Integration test gaps**:
    - OAuth callback CSRF mismatch / state expiry edge cases (some happy + a couple of bad-states; missing: `state_invalid_or_expired`, replay-after-success)
    - Drive 429 backoff with `Retry-After` header parsing
    - SSE disconnect handling (client closes mid-stream — server should clean up subscriber set)
- [ ] **mypy strict** — never run end-to-end yet; CI workflow expects it. Likely a non-trivial cleanup pass (Pydantic generic narrowing, async return types).
- [ ] **import-linter** — declared in `backend/pyproject.toml` but never invoked. Would catch ARCH-001 §2.1 layer violations (routers must not import models / adapters directly, etc.).

---

## 5. Out of scope for V1 (explicit V2)

Per PRD §12 (Out of Scope) and DECISIONS entries:

- Multi-account / multi-teacher (D1 / A6 forbid)
- Auto-schedule (cron-style nightly batches)
- Data archive / export bundles
- PII regex editor (D13 explicit V2)
- Per-teacher budget cap (only process-wide currently)
- Student / parent / school-admin personas (PRD §3.1 explicit non-targets)
- Whisper API fallback (D10 — V2 backlog only if OpenRouter STT quality insufficient)
- Multi-process worker pool (Axis 4 — single process for V1)

---

## 6. How to update this file

When you ship a phase or close a checkbox above:

1. Update the row in [§1 Status at a glance](#1-status-at-a-glance) and add a DECISIONS entry link
2. Tick the checkbox in the relevant subsection of [§2-§4](#2-prd-f-1--f-10-coverage)
3. If it's a new "shipped but not in PRD F-N" item, add a row in the Notes column referencing the DECISIONS ID
4. Commit `docs/work-plan.md` together with the feature commit (or as the next commit) — the `_fill after commit_` placeholder pattern from DECISIONS.md applies if you want to reference the same hash
5. Push immediately so the file matches `git log` reality
