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

### D-2026-05-10-20 Implementation Phase 12 — Settings page (LLM tier overrides + budget gauge)
- **Decision**: Per-teacher LLM tier override + monthly budget visibility per PRD §5 / D8:
  (a) `app/services/settings_service.py` — `get_view(teacher_id)` returns the effective tier→model map (process default overlaid by `teacher.llm_tier_config` JSON), plus the current calendar-month sum of `llm_call_audit.cost_usd` and the process-wide budget cap. `set_tier_overrides` validates tier names against the four-tier set and persists; empty string clears that tier's override.
  (b) `app/routers/settings.py` — `GET /settings` (returns config + monthly cost + budget) and `PUT /settings/llm-tier` (replace overrides). Unknown tier → 400.
  (c) Frontend `/settings` page: budget progress bar (warn-coloured at >100%), per-tier text input pre-filled with effective model ID, save button. Uses the convention that "value matches default" → backend treats as cleared.
  (d) Logout button moved here from home page.
  Tests: 6 new — defaults, set override, clear override, unknown tier 400, anonymous 401, monthly cost aggregation.
- **Rationale**: Per-tier override at runtime (no env var change) is what D8 demands — teachers can shift evaluation_quality to Pro for one student without restarting the container. The "type the model ID" field is intentionally unconstrained: framework-gotcha.md "OpenRouter Model Names Don't Always Match Documentation" — better to let the teacher copy-paste from OpenRouter dashboard than maintain a hardcoded allowed-list that goes stale. Budget cap stays process-wide for V1; per-teacher budget needs a DB column + accounting service that's V2 scope.
- **Files**: `backend/app/services/settings_service.py`, `backend/app/schemas/settings.py`, `backend/app/routers/settings.py`, `backend/app/main.py` (wired router), `backend/tests/integration/test_settings.py`, `frontend/src/lib/api.ts` (settings calls), `frontend/src/app/settings/page.tsx`
- **Commit**: _fill after commit_

### D-2026-05-10-19 Implementation Phase 11 — PII Min UI (D13)
- **Decision**: Surface PII mapping management to the teacher per D13:
  (a) `PIIAnonymizer.list_mappings(teacher_id)` returns rows with decrypted `original_value` so the UI can show "PH001 ↔ 0912345678". `update_display_name` sets/clears a per-row override. `add_manual_mapping` inserts an alias row sharing the existing pseudonym (e.g., `阿明 → S001`).
  (b) Schema migration `20260510_0003`: drops `UNIQUE (teacher_id, pseudonym)` (replaced by alias-permitting design). The `(teacher_id, pii_type, lookup_hash)` constraint from 0002 still prevents duplicate plaintexts.
  (c) `app/routers/pii.py` — `GET /pii/mappings`, `PUT /pii/mappings/{pseudonym}/display-name`, `POST /pii/mappings`. Anonymous → 401; unknown pseudonym → 404 / 400 depending on context.
  (d) Frontend `/pii` page: list table with inline edit-display-name, alias add form below.
  Tests: 7 new — list returns seeded rows with decrypted originals, display-name set/clear, unknown pseudonym 404, manual-mapping happy path, manual mapping on unknown pseudonym 400, anonymous 401.
- **Rationale**: V1 UI skips regex editor (D13 explicitly defers to V2) — teachers can fix specific values via aliases. Discovery of the schema bug ("uq_pii_pseudonym blocks aliases") happened during Phase 11 implementation, was fixed via migration 0003 in same commit; this is the kind of mid-phase schema evolution `engineering-process.md` "OAQ Defer Don't Reverse" applies to (raise + fix in next layer rather than retroactively edit Phase 1's initial migration).
- **Files**: `backend/alembic/versions/20260510_0003_drop_pii_pseudonym_unique.py`, `backend/app/models/pii_mapping.py` (drop UQ), `backend/app/services/pii_anonymizer.py` (3 new methods), `backend/app/schemas/pii.py`, `backend/app/routers/pii.py`, `backend/app/main.py` (wired router), `backend/tests/integration/test_pii_min_ui.py`, `frontend/src/lib/api.ts` (PII calls), `frontend/src/app/pii/page.tsx`, `frontend/src/app/page.tsx` (added cards for /pii + /settings)
- **Commit**: _fill after commit_

### D-2026-05-10-18 Implementation Phase 10 — audio STT tier
- **Decision**: Add audio transcription via the `audio_standard` tier (D10 / D11):
  (a) `OpenRouterClient.chat` extended with `audio_bytes` + `audio_mime`. Audio is included as an `input_audio` content part with `format` derived from MIME (mp3/wav/m4a/webm/ogg/flac). Co-exists with `image_bytes`.
  (b) `LLMService.call` passes audio kwargs through chokepoint. Text prompt still anonymised + boundary-checked + restored — but PII inside the audio (spoken names) is the same residual risk as vision (LLM transcribes); mitigated via prompt instruction asking the model to substitute placeholders for student names / IDs / phones.
  (c) `AudioExtractor` (mp3/wav/m4a/webm/ogg/flac; 25MB pre-encode warning). Returns `text=""` so pipeline routes bytes directly.
  (d) `ProcessingPipeline._route_tier` extends to "text → summary_cheap, image → vision_cheap, audio → audio_standard". Vision branch returns `artifact_type='markdown_summary'`; audio branch returns `artifact_type='transcript'` (matches schema). max_output_tokens=5000 for transcripts (longer than summaries).
  (e) D11: speaker count auto-detection delegated to the LLM via prompt — no client-side classification. Output format (monologue vs dialog) decided by the model.
  Tests: 5 new (audio routes correctly, OpenRouter receives audio_bytes + format detection, message builder produces input_audio part, oversize warning, octet-stream MIME with .mp3/.m4a filename still routes to audio). FakeOpenRouter signatures updated in 2 existing test files. Full suite 116 passed.
- **Rationale**: `input_audio` with base64 data part chosen over the OpenAI Whisper-style `audio.transcriptions.create` API because (1) we already use chat completions for vision tier — single code path, (2) Gemini Flash family natively handles audio via chat content parts, (3) we keep PII anonymise/restore round-trip in the same code path (transcriptions API would bypass it). The 25MB cap is generous (~30 minutes of 128kbps mp3) and aligns with PRD §6.1's "~3 audio recordings per teacher per semester" baseline. Streaming download for huge files deferred — V1 walking-skeleton flags `unprocessable` for >25MB; teacher trims in audio editor first.
- **Files**: `backend/app/adapters/openrouter_client.py` (audio in `_build_messages`, format mapper), `backend/app/services/llm_service.py` (audio kwargs), `backend/app/adapters/document_extractors/audio.py`, `backend/app/adapters/document_extractors/__init__.py` (registry), `backend/app/services/processing_pipeline.py` (AUDIO_MIMES + audio prompt + transcript artifact_type), `backend/tests/integration/test_audio_pipeline.py`, `backend/tests/integration/test_llm_service.py` + `test_processing_pipeline.py` (FakeOpenRouter signatures)
- **Commit**: `98b38e4`

### D-2026-05-10-17 Implementation Phase 9 — vision tier (image extractor + multimodal LLM)
- **Decision**: Add image processing via the vision_cheap tier:
  (a) `OpenRouterClient.chat` extended with optional `image_bytes` + `image_mime` kwargs. Multimodal `messages` payload constructed via `_build_messages`: text-only → simple `{role:user, content:str}`; with image → `content` is a parts list (text part + `image_url` data URL with base64-inline image). Stays under chat completions API (no streaming or audio yet).
  (b) `LLMService.call` exposes the same kwargs end-to-end. Text prompt is still anonymised + boundary-checked + restored; image bytes forwarded as-is — anonymizer cannot redact pixels.
  (c) `ImageExtractor` (jpeg/png/webp; 5MB pre-encode warning cap). Returns `text=""` because the bytes go to the vision tier directly, not as transcribed text. `has_images=True` set so future routing logic stays consistent.
  (d) `ProcessingPipeline._route_tier` switches from "text-only or fail" to "text → summary_cheap, image → vision_cheap, else UnsupportedFormat". Vision branch builds a vision-specific prompt with **explicit instruction not to transcribe PII** (handwritten names / printed IDs in images can leak through if the model OCRs; this prompt is the V1 mitigation, paired with the existing boundary check on the response text).
  (e) `Settings.llm_tier_vision_cheap` already plumbed (D9 default = Flash Lite). No new env vars; cost table now applies to vision-tier calls automatically.
  Tests: 4 new (image routes to vision tier, OpenRouter receives image_bytes + correct mime, multimodal message builder generates data URL parts, oversize warning). Updated 3 existing tests to accept the new kwargs in their FakeOpenRouter stubs and to use a true non-routable MIME (`video/mp4`) for the unsupported-format test (image/png is now supported). Full suite 111 passed.
- **Rationale**: Inline-base64 data URLs were chosen over pre-uploading to a CDN because (1) V1 has no image-host infrastructure, (2) flask-flask payload (~5MB pre-encode → ~7MB encoded) is well within OpenRouter's request limits, (3) it leaves no third-party trace of student images outside the LLM provider chain. The PII-restriction prompt is intentionally just a soft instruction — there's no provable guarantee the model obeys; this is the same threat profile as the document tier where the LLM could in theory reproduce the input text verbatim. The boundary check on the response text remains the load-bearing tripwire.
- **Files**: `backend/app/adapters/openrouter_client.py` (multimodal messages + base64 import), `backend/app/services/llm_service.py` (image kwargs through chokepoint), `backend/app/adapters/document_extractors/image.py`, `backend/app/adapters/document_extractors/__init__.py` (registry order), `backend/app/services/processing_pipeline.py` (vision routing + vision prompt), `backend/tests/integration/test_vision_pipeline.py`, `backend/tests/integration/test_llm_service.py` + `test_processing_pipeline.py` (FakeOpenRouter signature update)
- **Commit**: `a5e2e5d`

### D-2026-05-10-16 Implementation Phase 8 — onboarding wizard (D17 attestation + D14 mapping)
- **Decision**: Complete the post-OAuth onboarding flow per ARCH-001 §3.1 / PRD §3.2 Flow A:
  (a) Backend: `AuthService.attest(teacher_id, version)` updates `teacher.consent_attestation_at` + `consent_attestation_version`, writes `attestation_signed` system_event for legal-grade audit. New endpoint `POST /onboarding/attest {version}`. Idempotent — same version may be re-signed.
  (b) Frontend `/onboarding` 4-step wizard (`attest → pick-root → mapping → done`):
      - Step 1: attestation text + checkbox + submit (D17 explicit consent)
      - Step 2: pick teaching root from `GET /drive/list` (radio list)
      - Step 3: D14 mapping wizard — for each `unmapped_category_names` entry, dropdown to learning/interaction/work/`__skip__`. Validation: all entries must be assigned before submit
      - Step 4: scan summary (semesters / students / files indexed)
  (c) Bootstrap-on-load: useEffect calls `/me`, jumps to first incomplete step (if `has_attested` + `has_drive_root` already set, runs scan and either lands at `mapping` or `done`).
  (d) Home page (`/`) gains an "尚有設定步驟未完成" banner linking to `/onboarding` when `has_attested=false` OR `has_drive_root=false`.
  Tests: 5 new backend (test_onboarding.py — happy path / system_event recorded / 401 anonymous / 422 empty version / idempotent), full suite 107 passed.
- **Rationale**: `attest` shipped in `AuthService` (not its own service) because attestation is an auth-flow extension — the audit trail is OAuth-adjacent, the `teacher` row carries the state. Frontend wizard built as a single page with step-state machine (rather than nested routes) so abandoning + returning lands the user at the same step seamlessly via the bootstrap effect — refresh-resume costs zero session state on the server.
- **Files**: `backend/app/services/auth_service.py` (added `attest`), `backend/app/routers/drive.py` (added `POST /onboarding/attest`), `backend/tests/integration/test_onboarding.py`, `frontend/src/lib/api.ts` (added Drive + onboarding calls), `frontend/src/app/onboarding/page.tsx`, `frontend/src/app/page.tsx` (onboarding banner)
- **Commit**: `414e127`

### D-2026-05-10-15 Implementation Phase 7 — batch dashboard UI + SSE wiring
- **Decision**: Add `/batch` dashboard route to frontend with live progress via EventSource:
  (a) `src/lib/api.ts` extended with `BatchStatusResponse` / `BatchEvent` types and `startBatch` / `cancelBatch` / `getBatchStatus` / `openBatchEventStream` calls.
  (b) `src/app/batch/page.tsx` — 3-state UI (idle / starting / running / finished). Start triggers `/batch/start` (202), then `openBatchEventStream` opens an EventSource to `/batch/{id}/events`. Each `data: {...}` event updates the snapshot + progress bar. `onerror` handler does one polling fetch as graceful degradation when the stream terminates.
  (c) Cleanup discipline: `useRef<EventSource>` + `useEffect` cleanup `close()`s any open stream on unmount. React 19 strict mode dev double-invokes effects; the close+reopen is benign.
  (d) Home page updated with two-card grid (批次處理 + 評語產生).
  Verification: `pnpm build` ✓ (4 static routes), `pnpm typecheck` ✓.
- **Rationale**: EventSource is the right primitive (browser native, auto-reconnect, CORS-friendly via `withCredentials`); WebSocket would be overkill for unidirectional progress. The polling fallback in `onerror` covers two cases at once: stream prematurely closed, or browser restored from bfcache without a fresh stream. UI surfaces last-event drive_file_id + reason so failures (e.g. `unprocessable`) are visible without drilling into a separate log view.
- **Files**: `frontend/src/lib/api.ts`, `frontend/src/app/batch/page.tsx`, `frontend/src/app/page.tsx`
- **Commit**: `8721866`

### D-2026-05-10-14 Implementation Phase 5b — extractors for xlsx / pptx / pdf
- **Decision**: Add 3 V1 document extractors per DESIGN-001 §8.2:
  (a) `XlsxExtractor` (openpyxl, `read_only=True data_only=True`) — sheet-per-section, GFM pipe tables, 1000-row cap per sheet with warning surface, blank-sheet warning, legacy `.xls` (OLE) → `UnsupportedFormatError`.
  (b) `PptxExtractor` (python-pptx) — slide-per-section with title detection (placeholder idx==0), bullet-list rendering of body text frames, `has_images=True` flagged on picture shapes (Phase 7+ vision-tier hook), legacy `.ppt` (OLE) → `UnsupportedFormatError`.
  (c) `PdfExtractor` (pypdf) — text-only V1; tries empty password on `is_encrypted=True` (handles common print-restriction-only "encryption"); true encrypted → `UnsupportedFormatError`; per-page warnings for pages with no text layer (likely scanned-image PDF, OCR fallback is Phase 7+).
  Registry order updated: `Docx → Xlsx → Pptx → Pdf → PlainText`. `ProcessingPipeline.TEXT_SUMMARY_MIMES` extended; `_filename_is_text` extended to recognise `.xlsx/.pptx/.pdf`.
  Tests: 11 new (4 xlsx + 3 pptx + 3 pdf + 1 registry routing) — full suite 102 passed.
- **Rationale**: One commit per format would be 3 PRs; bundling them into Phase 5b is justified because they share structure (all are zip-or-stream parsers wrapped via `asyncio.to_thread`, all map narrow OLE-magic to `UnsupportedFormat`, all surface warnings rather than fail-hard for partial extraction). The Protocol+Registry pattern from Phase 4b absorbs all three with no signature changes — proves the abstraction. Image-bearing pptx flagged via `has_images=True` deliberately routes nowhere yet — adding the boolean now means Phase 7+ (vision tier) only adds the routing logic, not a schema change. PDF empty-password retry handles a real-world failure mode (Drive-stored homework scans where the teacher set print-restrictions years ago) — without this, those PDFs would land in `unprocessable` despite being readable.
- **Files**: `backend/app/adapters/document_extractors/xlsx.py`, `backend/app/adapters/document_extractors/pptx.py`, `backend/app/adapters/document_extractors/pdf.py`, `backend/app/adapters/document_extractors/__init__.py` (registry), `backend/app/services/processing_pipeline.py` (TEXT_SUMMARY_MIMES + filename test), `backend/tests/unit/test_extractors_phase5b.py`
- **Commit**: `f5d9928`

### D-2026-05-10-13 Implementation Phase 5alt — BatchWorker + SSE progress
- **Decision**: Add concurrent batch processing with live progress via Server-Sent Events:
  (a) `app/services/sse_publisher.py` — minimal in-process pub/sub keyed by topic. Subscribers attached via async generator (`subscribe(topic)`); publishers broadcast non-blocking (drop on full queue rather than stall). Late subscribers miss earlier events; combine with `/batch/{id}/status` for snapshot.
  (b) `app/services/batch_worker.py` — `start_job` creates `batch_job` row, picks all `drive_file` rows for `(teacher, semester)` whose artifact state is `null`/`pending`/`reprocess_pending`, fans out as `asyncio.create_task` with `Semaphore(BATCH_WORKER_CONCURRENCY)` (default 4). Failure mapping: `UnsupportedFormat`/`DocumentExtraction` → `state='unprocessable'` (terminal, D-2026-05-10-04); `LLMRateLimit`/`Timeout`/`DriveError` → `state='failed'` + `retry_count++`; `LLMQuotaExhausted` → pause batch (resets to `pending`, returns `failed` status). `recover_stale_jobs` resets any `state='processing'` rows on lifespan startup (interrupted-process safety).
  (c) Routes: `POST /batch/start` (202 + batch_job_id), `POST /batch/{id}/cancel` (soft cancel via `asyncio.Event`), `GET /batch/{id}/status` (snapshot for polling fallback), `GET /batch/{id}/events` (SSE stream — `text/event-stream` with leading `retry: 5000` hint, terminates on `state ∈ {completed, failed, cancelled}`).
  (d) `system_event` audit on `batch_started` / `batch_completed` / `batch_failed`.
  (e) Tests (10 new, full suite 91 passed): start_job → 3 files all processed; terminal failure → state='unprocessable'; rate limit → state='failed'+retry_count=1; recover_stale_jobs resets processing→pending; SSE pub/sub broadcasts; router 202/status poll/anonymous 401/unknown batch 404.
  Out of scope (Phase 5alt-2): auto-retry inside worker (currently leaves `failed` for manual retry), reprocess_pending overwrite/keep prompt UI flow, multi-batch queueing.
- **Rationale**: `asyncio.Semaphore` chosen over `arq`/Redis-backed worker pool because V1 single-process invariant (Axis 4 / OAQ-2 confirmed) — adding Redis would violate "zero external runtime deps." Concurrency default `4` matches ARCH-001 §7.1 worker-sizing analysis (Drive 10/s + OpenRouter 1/s sustained). SSE chosen over WebSocket because batch progress is server-push-only — WS bidirectional is overkill, SSE works behind any HTTP-only proxy and reconnects automatically. Built without `sse-starlette` dep — protocol is trivial (`data: {...}\n\n`) and walking-skeleton doesn't need that lib's graceful-disconnect refinements yet.
- **Files**: `backend/app/services/sse_publisher.py`, `backend/app/services/batch_worker.py`, `backend/app/schemas/batch.py`, `backend/app/routers/batch.py`, `backend/app/main.py` (wired router), `backend/tests/conftest.py` (added SSE cache reset), `backend/tests/integration/test_batch_worker.py`
- **Commit**: `4425ff5`

### D-2026-05-10-12 Implementation Phase 6 — frontend Next.js scaffold + login + evaluation editor
- **Decision**: Bring up V1 frontend scaffold (Next.js 15 / React 19 / TypeScript 5.7 / Tailwind 3.4):
  (a) `frontend/package.json` — pnpm-managed (pinned to v9 — pnpm 11+ requires Node 22.13 but the dev env runs Node 20.20.2; ARCH-001 §2.2 states "pnpm preferred for smaller lockfile" so we stay on pnpm). Build target: `next build` produces `output: 'standalone'` (per OAQ-3 / DESIGN-001 §2.3 single-container deploy plan).
  (b) `next.config.mjs` rewrites `/auth/*`, `/drive/*`, `/onboarding/*`, `/file/*`, `/eval/*`, `/me`, `/healthz`, `/readyz` → backend on `http://localhost:8000`. Means dev frontend at `:3000` cookies auto-attach to proxied requests; production single-container Caddy will replicate this routing.
  (c) `src/lib/api.ts` — typed wrapper around backend endpoints; `ApiError` carries status + reason codes (e.g., `no_session`, `no_artifacts`) so UI can branch without parsing strings. Hand-written types for V1 walking skeleton; Phase 7+ swaps for `openapi-typescript` codegen per ARCH-001 §2.3.
  (d) Pages: `/` (login CTA + post-login dashboard hint, calls `/me`), `/evaluation/new` (3-step form: load context → seed/style → editor with cost meter + revert-to-AI button).
  (e) Tailwind config carries minimal design tokens (`accent #3a5a40 = 墨痕`, `warn`, `terminal`); UIUX-001 full token extraction in Phase 7+.
  Verification: `pnpm build` succeeds (3 routes, ~107KB first-load JS); smoke test confirms `GET /` (Next.js 200), `GET /me` (proxy → backend 401), `GET /auth/login` (proxy → backend 302 to Google with full OAuth params).
- **Rationale**: Next.js rewrites + cookie-based auth means we DON'T need a separate API client base URL config or CORS handling — backend issues cookies on `:8000`, Next.js dev server proxies to `:8000` via the same origin from the browser's perspective, and prod single-container collapses both onto the same host. This trades a 2-3ms extra hop in dev for zero auth-config divergence between dev and prod, which was DESIGN-001 §2.4 (OAQ-4) intent. Kept the API client hand-written for Phase 6 because the surface is small (5 calls); generated types add codegen pipeline complexity that's only worth it when 3+ devs touch the schema or surface grows past ~20 endpoints. Pinned pnpm@9 because pnpm@11 hard-requires Node 22.13 — upgrading Node out of scope for this phase.
- **Files**: `frontend/package.json`, `frontend/pnpm-lock.yaml`, `frontend/tsconfig.json`, `frontend/next.config.mjs`, `frontend/tailwind.config.ts`, `frontend/postcss.config.mjs`, `frontend/.eslintrc.json`, `frontend/next-env.d.ts`, `frontend/src/styles/globals.css`, `frontend/src/lib/api.ts`, `frontend/src/app/layout.tsx`, `frontend/src/app/page.tsx`, `frontend/src/app/evaluation/new/page.tsx`
- **Commit**: `4aee7ae`
- **Lesson**: One small one — Next 15's lint rule `no-html-link-for-pages` blocks `<a href="/">` in favour of `<Link>` even in static layouts. Easy fix; not promoted to lessons-learned because it's framework-version-specific guidance the linter itself surfaces.

### D-2026-05-10-11 Implementation Phase 5 — EvaluationGenerator + /eval/* endpoints
- **Decision**: Implement V1 evaluation draft generation per PRD §3.2 Flow C / DESIGN-001 §4.7:
  (a) `app/services/evaluation_generator.py` — `gather_context` joins `drive_file × processed_artifact` to pull all 3-category summaries for one (teacher, semester, student). `generate` builds a style-aware prompt (formal/encouraging/objective per D12, Chinese instruction strings + per-category headings + 4K-char per-category cap), sends through `LLMService.call(tier=evaluation_quality)` (anonymise → boundary → restore → audit), UPSERTs `semester_evaluation` row keyed by uniqueness `(teacher, semester, student)`. `save_edit` writes `edited_text` while preserving `generated_text` (audit trail per ARCH-001 §3.3). `regenerate` is just `generate` again — UPSERT semantics.
  (b) `app/routers/evaluation.py` — 4 endpoints: `GET /eval/{semester}/{pseudo_id}/context` (artifact summaries before generation), `POST /eval/generate` (returns `EvaluationResponse`), `PUT /eval/{evaluation_id}` (edit), `GET /eval/{evaluation_id}` (single fetch). Maps `NoArtifactsError` → 412 (teacher must process files first), `LLMRateLimitError`/`Timeout` → 503, `PIILeakageError` → 500 with no leak in response body.
  (c) Tests: 5 service-level (gather_context per-category split, generate persists row, regenerate UPSERTs same row, save_edit preserves generated_text, no-artifacts raises) + 6 router-level (context fetch, generate happy path, 412 no_artifacts, edit persists, 422 invalid style, 401 anonymous) — full suite 81 passed.
- **Rationale**: Phase 5 closes the OAuth → process → generate → edit narrative for a single student × semester. UPSERT semantics on `semester_evaluation` reflect D-2026-05-10-04 mindset — one canonical evaluation per (teacher, semester, student); regenerate replaces but `edited_text` discipline preserves audit history. Char-cap per category (4K) is a heuristic; Phase 5+ can swap for tokenizer-aware truncation when adding image/audio tiers (`vision_cheap`/`audio_standard`) where token budgets matter more. The router fixture had to be rebuilt to NOT depend on the service-level fixture — `TestClient` lifespan creates a fresh event loop, and an `asyncio.Queue` is bound to its creating loop; fixture-built queues from `gen_harness` would cross-loop deadlock. Documented inline in test fixture.
- **Files**: `backend/app/services/evaluation_generator.py`, `backend/app/schemas/evaluation.py`, `backend/app/routers/evaluation.py`, `backend/app/main.py` (wired evaluation router), `backend/tests/integration/test_evaluation.py`
- **Commit**: `27b2cfd`
- **Lesson**: None new for cross-tool documentation. The `asyncio.Queue` cross-loop binding gotcha was already implicit in Phase 4b test fixture; explicit code comment in Phase 5 fixture suffices for future readers.

### D-2026-05-10-10 Implementation Phase 4b — Document extractors + ProcessingPipeline + single-file endpoint
- **Decision**: Implement V1 walking-skeleton vertical slice end-to-end:
  (a) `app/adapters/document_extractors/` — `DocumentExtractor` Protocol + `DocumentExtractorRegistry` (first-match-wins) + 2 V1 extractors: `DocxExtractor` (python-docx; encrypted-OLE pre-screen via narrow `CDFV2 Encrypted` signature; markdown rendering of headings/lists/tables) + `PlainTextExtractor` (utf-8 → big5 → cp950 fallback chain for legacy TW files). Other formats (xlsx/pptx/pdf/image/audio) deferred to dedicated phases.
  (b) `DriveClient.download_file` via `MediaIoBaseDownload` chunked stream → in-memory bytes (V1 scale; >100MB audio gets streaming variant in Phase 5+).
  (c) `app/services/processing_pipeline.py` — `ProcessingPipeline.process(teacher_id, drive_file)` orchestrates download → extract → LLMService.call (which itself anonymises → boundary-checks → calls OpenRouter → restores → audits) → returns `ProcessingResult` (PII-restored markdown + cost + content_hash + audit_id). Per DESIGN-001 §4.5 the pipeline is **pure** — caller persists.
  (d) `app/routers/files.py` — `POST /file/{id}/process` (synchronous single-file run; persists `processed_artifact` row + updates `drive_file.content_hash` via DBWriteQueue) and `GET /file/{id}/artifact`. Maps exception classes to HTTP semantics: `UnsupportedFormatError`/`DocumentExtractionError` → 415 + writes `state='unprocessable'` (terminal per D-2026-05-10-04); `LLMRateLimitError`/`LLMTimeoutError` → 503; `DriveError` → 502.
  (e) Tier routing in pipeline: text MIMEs → `summary_cheap`. Image/audio raise `UnsupportedFormatError` (Phase 5 adds vision/audio routing).
  Walking-skeleton verification: 13 new tests (extractors) + 2 (pipeline e2e) + 5 (router e2e via TestClient with dependency_overrides) — total suite 70 passed.
- **Rationale**: Phase 4b closes the OAuth → Drive scan → file process → markdown artifact loop. Two extractors (.docx + .txt) is the minimum to prove extensibility — the Registry/Protocol pattern means adding xlsx/pptx/pdf is each a self-contained PR. `MediaIoBaseDownload` over `get_media().execute()` matters for the 100MB audio path (Phase 5) — installing the streaming primitive now means Phase 5 only needs to switch to `next_chunk` per-chunk instead of buffer everything. Single-file route (not /batch) chosen for Phase 4b because it's testable without the worker pool; serves as "manual retry single file" feature in V1 even after batch ships.
- **Files**: `backend/app/adapters/document_extractors/__init__.py`, `backend/app/adapters/document_extractors/docx.py`, `backend/app/adapters/document_extractors/text.py`, `backend/app/adapters/drive_client.py` (added `download_file`), `backend/app/services/processing_pipeline.py`, `backend/app/schemas/files.py`, `backend/app/routers/files.py`, `backend/app/main.py` (wired files router), `backend/tests/unit/test_extractors.py`, `backend/tests/integration/test_processing_pipeline.py`, `backend/tests/integration/test_files_router.py`
- **Commit**: `6bf2dd9`
- **Lesson**: Two surfaced during implementation but neither generalises beyond this codebase's specific test layout: (1) cross-fixture queue singleton confusion — Phase 5 fixtures should accept the harness's queue instead of re-fetching `get_write_queue()` to avoid two-instances deadlock; (2) FK-bound seed inserts in a single submit can fail on SQLite's immediate FK enforcement; split into one-table-per-submit. Both already documented inline in test fixtures via comments; not promoted to lessons-learned because they're test-harness concerns rather than cross-tool patterns.

### D-2026-05-10-09 Implementation Phase 4a — Drive auth refresh + folder index + mapping wizard
- **Decision**: Implement V1 Drive sync (read-only, indexing only — Phase 4b adds file processing):
  (a) `app/adapters/drive_client.py` — google-api-python-client wrapped via `asyncio.to_thread`. No async-Drive SDK introduced (`aiogoogle` would add deps without measurable benefit at design scale).
  (b) `AuthService.get_credentials(teacher_id)` — decrypts refresh_token, returns `google.oauth2.credentials.Credentials` with built-in lazy access-token refresh via google-auth library (no manual refresh logic in our code).
  (c) `app/services/drive_sync_service.py` — `list_root_candidates`, `list_children`, `set_drive_root`, `set_folder_mapping`, `scan_root`. The 3-level walk (semester / student / category) detects standard category names (`學習紀錄` / `教師與學生互動紀錄` / `作品成果`) and persisted mapping (D14); unknown names are returned in `ScanResult.unmapped_category_names` so caller can show the mapping wizard.
  (d) Routes: `GET /drive/list`, `GET /drive/folder/{id}/children`, `POST /drive/scan`, `POST /onboarding/drive-root`, `POST /onboarding/folder-mapping`. All gated by the session cookie (verified via 401-anonymous smoke test).
  (e) Idempotent rescans: if `drive_modified_at` matches the indexed row, count as `files_unchanged`; otherwise UPDATE.
  Walking-skeleton simplification: scan is single-shot rather than DESIGN-001's suspend/resume pattern. When mapping is needed, scan returns the candidate names; caller posts mapping then re-scans. Two API round-trips total — no observable UX difference, much simpler implementation. (DESIGN-001 §4.4's suspend/resume API can be added in V2 if Drive grows beyond the design scale where rescan cost becomes a concern.)
- **Rationale**: D5 (Drive read-only) and D14 (mapping wizard) are non-negotiable; this implements them with minimal moving parts. `asyncio.to_thread` over the sync google-api-python-client is the right trade at design scale (~5 list calls per scan). Persisted folder mapping (D14) lives in `teacher.folder_mapping` JSON — no separate table needed. Phase 4a deliberately leaves `download_file` / `stream_audio` / `content_hash` to Phase 4b (file processing pipeline) to keep this commit reviewable.
- **Files**: `backend/app/adapters/drive_client.py`, `backend/app/services/auth_service.py` (added `get_credentials`), `backend/app/services/drive_sync_service.py`, `backend/app/schemas/drive.py`, `backend/app/routers/drive.py`, `backend/app/main.py`, `backend/tests/integration/test_drive_sync.py`
- **Commit**: `7efad05`
- **Lesson**: None new. The D-2026-05-10-08 alembic-async-commit lesson already covers the test-fixture migration path. Phase 4b may surface lessons around document extraction error classification.

### D-2026-05-10-08 Implementation Phase 3 — PII Anonymizer + LLM Service chokepoints; lookup_hash schema refinement; alembic async commit fix
- **Decision**: Implement V1 chokepoints per ARCH-001 §4.1 invariants:
  (a) `app/services/pii_anonymizer.py` — regex layer (TW phone / email / TW national ID) with stable per-(teacher, pii_type) pseudonyms (S/PH/EM/NID/...), in-process cache, deterministic `lookup_hash` (HMAC-SHA-256 keyed with PII_ENCRYPTION_KEY) for O(1) "have we seen this plaintext before" queries — random-nonce AES-GCM kept for at-rest encryption.
  (b) `app/adapters/openrouter_client.py` — openai SDK pointed at OpenRouter; classified errors (`LLMRateLimitError` / `LLMTimeoutError`) using two-level (typed-attr + regex) per framework-gotcha.md.
  (c) `app/services/llm_service.py` — single chokepoint enforcing anonymise → boundary trip-wire (`no_pii_in_anonymized`, security.md Layer 2) → OpenRouter call → restore → audit. PII boundary trip raises `PIILeakageError` AND writes `system_event(pii_leakage_detected, severity=critical)` AND logs to stderr — three-channel alerting per security.md "boundary firing is a real incident" rule.
  Also adds new alembic migration `20260510_0002` introducing `pii_mapping.lookup_hash` (deterministic) and replacing the `UNIQUE (teacher_id, pii_type, original_value_encrypted)` constraint with `UNIQUE (teacher_id, pii_type, lookup_hash)`. Also fixes a previously-undetected bug in `alembic/env.py`: standard async template missing explicit `await connection.commit()`, silently dropping `alembic_version` updates (would have surfaced on Phase 4 migration; caught here).
- **Rationale**: Random-nonce AES-GCM (chosen for at-rest pattern hiding) makes the original schema's `UNIQUE` constraint un-enforceable — same plaintext encrypts to different ciphertexts each call. Without `lookup_hash`, "have we already mapped this PII?" is O(n) decrypt-and-compare per anonymise call (~200ms at design scale, unacceptable in batch). HMAC-SHA-256 with the existing PII key adds nothing to the trust scope (compromise the key, you compromise both) but gives O(1) lookup. Schema migration written as a NEW alembic revision (not edit of 0001) per engineering-process.md governance — even on greenfield project, append-only migration history communicates "we discovered X during implementation" honestly. The alembic env.py async commit fix is critical: without it, ALL future migrations would silently re-run from scratch and collide; documented as new entry in `framework-gotcha.md`.
- **Files**: `backend/alembic/env.py`, `backend/alembic/versions/20260510_0002_add_pii_lookup_hash.py`, `backend/app/models/pii_mapping.py`, `backend/app/services/pii_anonymizer.py`, `backend/app/adapters/openrouter_client.py`, `backend/app/services/llm_service.py`, `backend/tests/unit/test_pii_anonymizer.py`, `backend/tests/integration/test_llm_service.py`, `~/.claude/lessons-learned/framework-gotcha.md`, `~/.claude/lessons-learned/README.md`
- **Commit**: `4c990f3`
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
