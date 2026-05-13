# ARCH-001: System Architecture

| Field | Value |
|-------|-------|
| **Status** | Draft v0.1 |
| **Date** | 2026-05-10 |
| **Owner** | Steven Chen |
| **Depends on** | [`PRD.md`](PRD.md) v0.2, [`adr/ADR-001-system-foundation.md`](adr/ADR-001-system-foundation.md) |
| **Consumers** | DESIGN-001, UIUX-001, BDD-001, TDD-001 |

---

## 0. Document Control

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 0.1 | 2026-05-10 | Steven (with Claude Code) | Initial — module structure, data flow, deployment topology |

**Reading order**:
- §2 Module Structure → §3 Data Flow → §4 Component Architecture (these are mutually reinforcing)
- §5 Deployment / §6 Cross-cutting / §7 Performance / §8 Security (independent, read as needed)
- §9 Open Architectural Questions punt to DESIGN-001

---

## 1. Context

This document expands on PRD §8 (high-level architecture diagram) and ADR-001 (architectural axes). It freezes:
- **Module names** that all subsequent design docs reference
- **Data flow paths** through the system
- **Deployment topology** for V1

It is **not** a detailed module API spec — that's DESIGN-001's job. Where this doc says "the LLM Service does X", DESIGN-001 will say "`class LLMService` exposes async method Y with signature Z".

**Binding decisions from ADR-001**:
- Single-tenant single-user (Axis 1)
- Python (FastAPI) backend + Next.js (React) frontend (Axis 2)
- PII anonymization at LLM Service boundary (Axis 3)
- Batch processing with persistent state machine (Axis 4)
- Tier-based LLM routing (Axis 5)
- SQLite + WAL + write serialization queue (Axis 6)
- Docker container, multi-target deploy (Axis 7)

---

## 2. Module Structure

### 2.1 Backend module tree (FastAPI)

```
backend/
├── pyproject.toml                # uv / pip-tools managed
├── alembic.ini
├── alembic/                      # DB migrations
│   └── versions/
├── app/
│   ├── main.py                   # FastAPI app + lifespan
│   ├── config.py                 # Pydantic Settings (env vars)
│   ├── routers/                  # HTTP endpoint layer (thin)
│   │   ├── auth.py               # OAuth callback, logout, revoke
│   │   ├── drive.py              # /drive/list, /drive/select-root
│   │   ├── files.py              # /file/<id>, /file/<id>/download
│   │   ├── batch.py              # /batch/start, /batch/status, /batch/cancel
│   │   ├── evaluation.py         # /eval/generate, /eval/<id>
│   │   ├── settings.py           # /settings/* (LLM tier, PII, folder mapping)
│   │   └── system.py             # /healthz, /readyz
│   ├── services/                 # Business logic (where the work happens)
│   │   ├── auth_service.py
│   │   ├── drive_sync_service.py
│   │   ├── pii_anonymizer.py     # ONE chokepoint for all PII
│   │   ├── llm_service.py        # ONE chokepoint for all OpenRouter calls
│   │   ├── processing_pipeline.py  # File → markdown / transcript
│   │   ├── batch_worker.py       # Async task pool + state machine
│   │   ├── evaluation_generator.py
│   │   ├── audit_logger.py
│   │   └── encryption.py         # AES-256 helpers (PII + OAuth tokens)
│   ├── adapters/                 # External-API gateways
│   │   ├── drive_client.py       # Wraps google-api-python-client
│   │   ├── openrouter_client.py  # Wraps openai SDK pointing at OpenRouter
│   │   └── document_extractors/  # python-docx, openpyxl, pypdf, etc.
│   │       ├── docx.py
│   │       ├── xlsx.py
│   │       ├── pptx.py
│   │       └── pdf.py
│   ├── models/                   # SQLAlchemy ORM models
│   │   ├── teacher.py
│   │   ├── drive_file.py
│   │   ├── processed_artifact.py
│   │   ├── pii_mapping.py
│   │   ├── semester_evaluation.py
│   │   ├── batch_job.py
│   │   └── llm_call_audit.py
│   ├── schemas/                  # Pydantic request/response DTOs
│   │   └── ... (mirror routers)
│   ├── db/
│   │   ├── session.py            # aiosqlite engine + session
│   │   └── write_queue.py        # asyncio.Queue serializer
│   └── core/
│       ├── exceptions.py         # Custom exception hierarchy
│       └── lifespan.py           # Startup: WAL checkpoint, stale-recovery
└── tests/
    ├── unit/
    ├── integration/
    └── e2e/                      # Backend-driven E2E (pre-Playwright)
```

**Layer rules** (enforced by code review and `import-linter`):
- `routers` may import `services`, `schemas`, `core` — never `models` directly, never `adapters`
- `services` may import `adapters`, `models`, `core`
- `adapters` may import only `core` and external libs
- `models` are pure SQLAlchemy — no business logic
- `schemas` are pure Pydantic — no business logic

### 2.2 Frontend module tree (Next.js App Router)

> **V1 walking-skeleton scope vs full vision** — the tree below is the full V1 vision.
> The shipped walking skeleton (Phases 1-12) collapses several paths to keep page count
> low; per-screen splits reactivate as needed in V1.x. **Actually shipped routes**:
> `/`, `/onboarding`, `/batch`, `/evaluation/new`, `/pii`, `/settings`. Not yet shipped:
> per-screen splits under `/onboarding/{attestation,drive-root,folder-mapping}` (one
> wizard page handles all 3 steps); per-section split under `/settings/{llm,pii,...}`
> (one settings page); browsing screens (`/semester/[label]`, `/student/[pseudo_id]`,
> `/file/[drive_file_id]`, `/evaluation/[semester]/[pseudo_id]`) — login is folded into
> `/` with conditional rendering on `/me` 401.

```
frontend/
├── package.json                  # pnpm preferred (smaller lockfile)
├── tsconfig.json
├── next.config.mjs
├── public/
├── src/
│   ├── app/                      # Next.js App Router
│   │   ├── layout.tsx
│   │   ├── page.tsx              # / (dashboard; login CTA when 401) — SHIPPED
│   │   ├── batch/page.tsx        # /batch (Phase 7) — SHIPPED
│   │   ├── evaluation/
│   │   │   ├── new/page.tsx              # /evaluation/new (Phase 6) — SHIPPED
│   │   │   └── [semester]/[pseudo_id]/page.tsx  # detail view — V1.x
│   │   ├── onboarding/page.tsx   # /onboarding (single wizard, Phase 8) — SHIPPED
│   │   │   # V1.x split: attestation/, drive-root/, folder-mapping/
│   │   ├── pii/page.tsx          # /pii (Phase 11) — SHIPPED
│   │   ├── settings/page.tsx     # /settings (Phase 12) — SHIPPED
│   │   │   # V1.x split: llm/, pii/, folder-mapping/, budget/, account/
│   │   ├── login/page.tsx        # /login — folded into /; standalone page is V1.x
│   │   ├── semester/[label]/page.tsx        # browsing — V1.x
│   │   ├── student/[pseudo_id]/page.tsx     # browsing — V1.x
│   │   └── file/[drive_file_id]/page.tsx    # browsing — V1.x
│   ├── components/               # Reusable presentational (V1.x — walking-skeleton inlines)
│   │   ├── ui/                   # Primitives (Button, Card, Badge, Dialog…)
│   │   ├── editor/               # Markdown editor + Mermaid preview
│   │   ├── badges/               # State badges (pending / processing / …)
│   │   ├── wizard/               # Mapping wizard (D14)
│   │   └── progress/             # Batch progress bar + cost meter
│   ├── lib/
│   │   ├── api.ts                # Hand-written client in walking-skeleton; V1.x → openapi-typescript
│   │   ├── auth/                 # Cookie / session helpers (V1.x — currently inlined)
│   │   ├── hooks/                # React hooks (useFiles, useBatch, …) (V1.x)
│   │   └── utils/                # (V1.x)
│   ├── styles/
│   │   └── globals.css           # Tailwind directives; tokens.css extraction → V1.x
│   └── test/                     # vitest setup
└── (tests colocated as *.test.ts; e2e/ for Playwright is V1.x)
```

**Frontend conventions**:
- Server-side API calls go through `lib/api/client.ts` (generated, type-safe)
- All UI state names are **provider-agnostic** (e.g., `llmQuotaPaused`, NOT `geminiQuotaPaused`) — see lessons-learned `frontend.md`
- Async-set state required for `:disabled` / `x-show` equivalents must be `await`-ed before render — see lessons-learned `frontend.md`
- SSE / WebSocket connections deferred until after `useEffect` settles to avoid Chrome tab spinner issue (lessons-learned `frontend.md`)

### 2.3 Shared types

OpenAPI is the single source of truth:

```
backend (FastAPI native /openapi.json)
    ↓ openapi-typescript codegen
frontend/src/types/api.ts (read-only)
```

Build pipeline regenerates `api.ts` on backend schema change. CI fails if `api.ts` is out of date relative to backend.

---

## 3. Data Flow

### 3.1 Onboarding flow (OAuth → Attestation → Drive root → Folder mapping)

**易讀說明 — 4 個階段**：

**A. OAuth handshake**（步驟 1-11）
1. Teacher → Frontend：按 [使用 Google 登入]
2. Frontend → Backend：`GET /auth/login`
3. Backend → Google OAuth：redirect 到同意畫面（scope: `drive.readonly`）
4. Google → Teacher：顯示 OAuth 同意畫面
5. Teacher → Google：核准
6. Google → Backend：`GET /auth/callback?code=...`
7. Backend → Google：`code` 換 token
8. Google → Backend：`access_token` + `refresh_token`
9. Backend：`encrypt(refresh_token, OAUTH_TOKEN_ENCRYPTION_KEY)`
10. Backend → DB：`UPSERT teacher (google_sub, email, encrypted_token)`
11. Backend → Frontend：設 session cookie + redirect 至 `/onboarding/attestation`

**B. Attestation 同意聲明**（步驟 12-16，per D17）
12. Frontend → Teacher：顯示同意聲明 dialog
13. Teacher → Frontend：勾選同意 + 送出
14. Frontend → Backend：`POST /onboarding/attest {version: "v1"}`
15. Backend → DB：`UPDATE teacher SET consent_attestation_at, consent_attestation_version`
16. Backend → Frontend：200 OK

**C. Drive 根目錄選擇 + 掃描啟動**（步驟 17-25）
17. Frontend → Backend：`GET /drive/list`（根層）
18. Backend → Google Drive：`drive.files.list` (folders only, root)
19. Google Drive → Backend：folder list
20. Backend → Frontend：tree node JSON
21. Teacher → Frontend：選擇資料夾 X
22. Frontend → Backend：`POST /onboarding/drive-root {folder_id: X}`
23. Backend → DB：`UPDATE teacher SET drive_root_folder_id`
24. Backend：觸發 initial scan（背景任務）
25. Backend → Frontend：202 Accepted (`scan_job_id`)

**D. Mapping wizard + scan 完成**（步驟 26-32，per D14）
- 掃描走 3 層：學期 / 學生 / 三類資料夾
- 第一個非標準類別資料夾名觸發 wizard

26. Backend → Frontend：SSE event `needs_folder_mapping`
27. Frontend → Teacher：顯示 mapping wizard
28. Teacher → Frontend：選擇對應關係
29. Frontend → Backend：`POST /onboarding/folder-mapping {mapping: {...}}`
30. Backend → DB：`UPDATE teacher SET folder_mapping`
31. Backend：用 mapping 恢復掃描
32. Backend → Frontend：SSE event `scan_complete` → Frontend → Teacher：redirect 至 `/dashboard`

**Mermaid（機器精確版）**：

```mermaid
sequenceDiagram
    actor T as Teacher
    participant FE as Frontend
    participant BE as Backend
    participant G as Google OAuth
    participant GD as Google Drive
    participant DB as SQLite

    T->>FE: Click "Login with Google"
    FE->>BE: GET /auth/login
    BE->>G: Redirect to OAuth consent
    G-->>T: OAuth consent screen (scope: drive.readonly)
    T->>G: Approve
    G->>BE: GET /auth/callback?code=...
    BE->>G: Exchange code for tokens
    G-->>BE: access_token + refresh_token
    BE->>BE: encrypt(refresh_token, OAUTH_TOKEN_ENCRYPTION_KEY)
    BE->>DB: UPSERT teacher (google_sub, email, encrypted_token)
    BE->>FE: Set session cookie + redirect /onboarding/attestation
    FE->>T: Show attestation dialog (D17)
    T->>FE: Check + submit
    FE->>BE: POST /onboarding/attest {version: "v1"}
    BE->>DB: UPDATE teacher SET consent_attestation_at, consent_attestation_version
    BE-->>FE: 200 OK
    FE->>BE: GET /drive/list (root level)
    BE->>GD: drive.files.list (folders only, root)
    GD-->>BE: folder list
    BE-->>FE: tree node JSON
    T->>FE: Pick folder X as 教學資料根目錄
    FE->>BE: POST /onboarding/drive-root {folder_id: X}
    BE->>DB: UPDATE teacher SET drive_root_folder_id
    BE->>BE: Trigger initial scan (background task)
    BE-->>FE: 202 Accepted (scan_job_id)
    Note over BE: Scan walks 3 levels: semester / student / category
    Note over BE: First non-standard category folder → trigger wizard
    BE->>FE: SSE event: needs_folder_mapping
    FE->>T: Show mapping wizard (D14)
    T->>FE: Choose mappings
    FE->>BE: POST /onboarding/folder-mapping {mapping: {...}}
    BE->>DB: UPDATE teacher SET folder_mapping
    BE->>BE: Resume scan with mapping
    BE->>FE: SSE event: scan_complete
    FE->>T: Redirect /dashboard
```

**Key observations**:
- OAuth callback is the **only** server endpoint that touches Google Auth — wrapped in `auth_service.py`
- Mapping wizard interrupts scan **mid-flow**; scan resume requires the mapping to be persisted before continuing
- Scan progress communicated via SSE (Server-Sent Events) — frontend defers connection per `frontend.md` lesson

### 3.2 Batch processing flow

> **V1 walking-skeleton vs full vision**: the per-file `reprocess_pending`
> overwrite/keep prompt UX (originally Phase A steps 1-7) is **deferred to V1.x**
> per Phase 5alt's documented out-of-scope list (D-2026-05-10-13). V1 walks
> straight from "Click [處理本學期]" → `POST /batch/start` and the worker
> processes any drive_files with state ∈ {null, pending, reprocess_pending}
> without a per-file UI gate. The two-step preview/confirm UX returns when
> bulk actions become a real safety concern (V1.x).

**易讀說明 — 2 個階段**：

**A. 啟動批次**（步驟 1-4）
1. Teacher → Frontend：按 [處理本學期]
2. Frontend → Backend：`POST /batch/start {semester_label: X}`
3. Backend → DB：`INSERT batch_job (status='running', total: N)`; BatchWorker._collect_candidates picks files where artifact state ∈ {null, pending, reprocess_pending}
4. Backend → Frontend：202 `{batch_job_id, total, status}` + Frontend opens SSE `/batch/<id>/events`

**B. 並行處理 loop**（每檔重複；最多 N=4 並行）
- BatchWorker → DBWriteQueue → DB：`state='processing'`（atomic）
- BatchWorker → 抽取內容（docx / image / audio）
- BatchWorker → LLMService：`anonymize(content)` + `call(tier)`
- LLMService：assert PII boundary（pre-anonymize 後仍含 PII → 拋 PIILeakageError）
- LLMService → OpenRouter：HTTP POST（**僅匿名化文字**）
- OpenRouter → LLMService：response
- LLMService：`restore(response)`
- LLMService → BatchWorker：artifact text + cost
- BatchWorker → DBWriteQueue → DB：`state='processed'`、`content_markdown=...`、`cost_usd=...`
- BatchWorker → Backend → Frontend：SSE event `file_done`

**完成**：
- BatchWorker → DB：`UPDATE batch_job SET status='completed', total_cost`
- BatchWorker → Backend → Frontend：SSE event `batch_done`
- Frontend → Teacher：顯示總結

> 失敗路徑（為清晰省略於圖）：`state='failed'` 含 `failure_reason`，自動 retry 最多 3x（exponential backoff）；終端錯誤（encrypted、unsupported）走 `state='unprocessable'` 不重試 — 詳 DESIGN-001 §6.3。

**Mermaid（機器精確版）**：

```mermaid
sequenceDiagram
    actor T as Teacher
    participant FE as Frontend
    participant BE as Backend
    participant W as BatchWorker
    participant Q as DB Write Queue
    participant DB as SQLite
    participant LLM as LLM Service
    participant OR as OpenRouter

    T->>FE: Click "Process this semester"
    FE->>BE: POST /batch/start {semester_label: X}
    BE->>BE: BatchWorker._collect_candidates (state IN null|pending|reprocess_pending)
    BE->>DB: INSERT batch_job (status='running', total: N)
    BE->>W: enqueue N file tasks
    BE-->>FE: 202 {batch_job_id, total, status}
    FE->>BE: Open SSE /batch/<id>/events
    loop Per file (up to N=4 in parallel)
        W->>Q: state='processing' (atomic write)
        Q->>DB: UPDATE
        W->>BE: extract content (docx / image / audio)
        W->>LLM: anonymize(content) + call(tier)
        LLM->>LLM: assert PII boundary
        LLM->>OR: HTTP POST (with anonymized text only)
        OR-->>LLM: response
        LLM->>LLM: restore(response)
        LLM-->>W: artifact text + cost
        W->>Q: state='processed', content_markdown=..., cost_usd=...
        Q->>DB: UPDATE
        W->>BE: SSE event 'file_done'
        BE->>FE: forward SSE
    end
    W->>DB: UPDATE batch_job SET status='completed', total_cost
    W->>BE: SSE event 'batch_done'
    BE->>FE: forward SSE
    FE->>T: Show summary
```

**Key observations**:
- `BatchWorker` runs as **asyncio task pool** with concurrency N (default 4, configurable)
- All DB writes funnel through `DBWriteQueue` (single-writer serialization for SQLite WAL — see §6.5)
- LLM Service is the **chokepoint** that enforces PII anonymization (Axis 3 ADR)
- SSE updates are forwarded via the API process (worker and API share process — Axis 4)
- Failure paths (omitted from diagram for clarity): `state='failed'` with `failure_reason`; retried up to 3x with exponential backoff before terminal

### 3.3 Evaluation generation flow

**易讀說明 — 線性流程**：

| # | Actor | → | Target | Action |
|---|-------|---|--------|--------|
| 1 | Teacher | → | Frontend | 進入 `/evaluation/<semester>/<pseudo_id>` |
| 2 | Frontend | → | Backend | `GET /eval/<semester>/<pseudo_id>/context` |
| 3 | Backend | → | DB | `SELECT processed_artifact for student` |
| 4 | DB | → | Backend | artifacts |
| 5 | Backend | → | Frontend | artifact 摘要（已還原 PII，供顯示） |
| 6 | Teacher | → | Frontend | 輸入 seed（30-100 字）+ 選風格（formal / encouraging / objective） |
| 7 | Frontend | → | Backend | `POST /eval/generate {seed, style, semester, pseudo_id}` |
| 8 | Backend | → | EvalGenerator | `build_prompt(seed, style, artifacts)` |
| 9 | EvalGenerator | → | PII Anonymizer | `anonymize(prompt)` |
| 10 | PII Anonymizer | → | EvalGenerator | anonymized prompt |
| 11 | EvalGenerator | → | LLMService | `call(tier='evaluation_quality', prompt=anonymized)` |
| 12 | LLMService | → | OpenRouter | HTTP POST |
| 13 | OpenRouter | → | LLMService | response text |
| 14 | LLMService | → | PII Anonymizer | `restore(text)` |
| 15 | PII Anonymizer | → | LLMService | restored text |
| 16 | LLMService | → | EvalGenerator | text + cost |
| 17 | EvalGenerator | → | DB | `INSERT semester_evaluation` |
| 18 | EvalGenerator | → | Backend → Frontend | evaluation |
| 19 | Frontend | → | Teacher | 顯示在 editor（Markdown preview） |
| 20 | Teacher | → | Frontend | 編輯 + save |
| 21 | Frontend | → | Backend | `PUT /eval/<id> {edited_text}` |
| 22 | Backend | → | DB | `UPDATE semester_evaluation SET edited_text, edited_at` |
| 23 | Backend | → | Frontend | 200 OK |

**關鍵點**：
- prompt builder 在 `EvalGenerator` — token 預算管理在這裡，不在 LLMService
- PII anonymizer 跑兩次：pre-call（步驟 9-10）+ post-call（步驟 14-15），對稱 round-trip
- 編輯後的文字存於不同欄位（`edited_text` ≠ `generated_text`），保留 audit trail

**Mermaid（機器精確版）**：

```mermaid
sequenceDiagram
    actor T as Teacher
    participant FE as Frontend
    participant BE as Backend
    participant EG as EvalGenerator
    participant LLM as LLM Service
    participant PII as PII Anonymizer
    participant DB as SQLite

    T->>FE: /evaluation/<semester>/<pseudo_id>
    FE->>BE: GET /eval/<semester>/<pseudo_id>/context
    BE->>DB: SELECT processed_artifact for student
    DB-->>BE: artifacts
    BE-->>FE: artifact summaries (already PII-restored for display)
    T->>FE: Type seed (30-100 chars) + pick style (formal / encouraging / objective)
    FE->>BE: POST /eval/generate {seed, style, semester, pseudo_id}
    BE->>EG: build_prompt(seed, style, artifacts)
    EG->>PII: anonymize(prompt)
    PII-->>EG: anonymized_prompt
    EG->>LLM: call(tier='evaluation_quality', prompt=anonymized_prompt)
    LLM->>OR: HTTP POST
    OR-->>LLM: text
    LLM->>PII: restore(text)
    PII-->>LLM: restored_text
    LLM-->>EG: text + cost
    EG->>DB: INSERT semester_evaluation
    EG-->>BE: evaluation
    BE-->>FE: evaluation
    FE->>T: Show in editor (Markdown preview)
    T->>FE: Edit + save
    FE->>BE: PUT /eval/<id> {edited_text}
    BE->>DB: UPDATE semester_evaluation SET edited_text, edited_at
    BE-->>FE: 200 OK
```

**Key observations**:
- The **prompt builder** (in `evaluation_generator.py`) selects which artifacts to include — token budget management lives here, not in LLM Service
- PII anonymizer runs both **pre-call** (on prompt) and **post-call** (on response) — symmetric round-trip
- Editing the LLM-generated text is a different DB column (`edited_text`) from the original (`generated_text`) — preserves audit trail per ADR-001 Axis 3 implications

### 3.4 PII anonymize / restore cycle

**易讀說明 — 對稱 round-trip**：

```
ServiceCaller.call(tier, raw_text_with_PII)
   │
   │ 1. anonymize ────────────────────────┐
   ▼                                       │
LLMService                                 │
   │                                       ▼
   │ 2. SELECT pii_mapping              PIIAnonymizer
   │    WHERE teacher_id=X
   │                                       │
   │ 3. detect new PII (regex + folder)    │
   │ 4. (if new) INSERT pii_mapping        │
   │ 5. substitute raw → anonymized        │
   │                                       │
   │◀──────────────── anonymized_text ─────┘
   │
   │ 6. assert no_pii_in_anonymized()  ← boundary check（防 anonymizer bug）
   │
   │ 7. HTTP POST anonymized_text
   ▼
OpenRouter
   │
   │ 8. response (含 pseudonyms 如 S001)
   ▼
LLMService
   │ 9. restore ──────────────────────────┐
   ▼                                       │
PIIAnonymizer                              │
   │ 10. SELECT display_name FROM         │
   │     pii_mapping WHERE pseudonym='S001'│
   │ 11. substitute pseudonyms → display  │
   │                                       │
   │◀──────────── restored_response ───────┘
   │
   ▼
Caller 取得：restored_response + cost + audit_record
```

**Boundary assertion 是 load-bearing safety net**：步驟 6 的 `no_pii_in_anonymized()` 對 anonymized_text 跑已知 PII regex（台灣電話 / Email / 國民身分證）。命中即拋 `PIILeakageError`，**HTTP POST 不會發生**。這是第二道防線 — 即使 anonymizer 有 bug，PII 仍不會出系統邊界。

**Mermaid（機器精確版）**：

```mermaid
sequenceDiagram
    participant Caller as ServiceCaller
    participant LLM as LLM Service
    participant PII as PII Anonymizer
    participant DB as SQLite (pii_mapping)
    participant OR as OpenRouter

    Caller->>LLM: call(tier, raw_text_with_PII)
    LLM->>PII: anonymize(raw_text_with_PII, teacher_id)
    PII->>DB: SELECT pii_mapping WHERE teacher_id=X
    DB-->>PII: existing mappings
    PII->>PII: detect new PII (regex + folder name)
    alt new PII found
        PII->>DB: INSERT pii_mapping (encrypted original, pseudonym=Snnn)
    end
    PII->>PII: substitute raw_text → anonymized_text
    PII-->>LLM: anonymized_text
    LLM->>LLM: assert anonymized_text has no PII (boundary check)
    LLM->>OR: HTTP POST {anonymized_text}
    OR-->>LLM: response (contains pseudonyms)
    LLM->>PII: restore(response, teacher_id)
    PII->>DB: SELECT pseudonym → display_name
    PII->>PII: substitute pseudonyms → display_names
    PII-->>LLM: restored_response
    LLM-->>Caller: restored_response + cost + audit_record
```

**Boundary assertion** is the load-bearing safety check. Before HTTP POST, LLM Service runs the `anonymized_text` against a known-PII regex (e.g., Taiwan phone numbers, common name patterns); any positive match raises `PIILeakageError` and aborts the call. This catches anonymizer bugs before data leaves the system.

---

## 4. Component Architecture

### 4.1 Backend component diagram (refines PRD §8)

**易讀說明 — 4 層 + 1 共用 queue**：

```
┌─────────────────────────────────────────────────────────────────┐
│ HTTP Layer (thin routers)                                       │
│   AuthR ── DriveR ── BatchR ── EvalR ── SettingsR              │
│      │       │         │         │         │                    │
│      ▼       ▼         ▼         ▼         ▼                    │
└─────────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────┐
│ Service Layer (business logic)                                  │
│                                                                  │
│   AuthService    DriveSyncService   BatchWorker                 │
│        │              │                  │                       │
│        │              │                  ▼                       │
│        │              │        ProcessingPipeline               │
│        │              │              │                          │
│        │              │              ▼                          │
│   EvalGenerator ────────────► LLMService ◄──── (chokepoint #2)  │
│                                  │ │                            │
│                                  │ ▼                            │
│                              PIIAnonymizer ◄──── (chokepoint #1)│
│                                  │                              │
│                              AuditLogger                         │
└──────────────────┬──────────────────────────────────────────────┘
                   │ (every write goes via this single asyncio.Queue)
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│ DBWriteQueue (single-writer serializer for SQLite WAL)          │
└──────────────────┬──────────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Persistence: SQLite WAL (aiosqlite)                             │
└─────────────────────────────────────────────────────────────────┘

External adapters:
  DriveClient (Google API) ◄── DriveSyncService
  OpenRouterClient        ◄── LLMService（唯一出口）
  DocumentExtractors      ◄── ProcessingPipeline
                              (docx / xlsx / pptx / pdf / 圖片 / 音訊路由)
```

**3 個關鍵不變式**：
1. 所有 Routers 都 thin — 處理 auth、Pydantic validation、呼叫一個 service、回 DTO；**不直接 import models / adapters**
2. 所有 DB write **都經 DBWriteQueue 序列化** — services 不直接 commit（reads OK）
3. **LLMService 是 OpenRouterClient 的唯一呼叫者** — services 想呼 LLM 必走此路
4. **PIIAnonymizer 在 LLMService 內部執行** — pre-call + boundary check + post-call

**Mermaid（機器精確版）**：

```mermaid
graph TB
    subgraph Routers [HTTP layer - thin]
        AuthR[auth.py]
        DriveR[drive.py]
        BatchR[batch.py]
        EvalR[evaluation.py]
        SettingsR[settings.py]
    end

    subgraph Services [Business logic]
        AuthSvc[AuthService]
        DriveSync[DriveSyncService]
        Pipeline[ProcessingPipeline]
        Worker[BatchWorker]
        EvalGen[EvaluationGenerator]
        PII[PIIAnonymizer]
        LLMSvc[LLMService]
        Audit[AuditLogger]
    end

    subgraph Adapters [External APIs]
        DriveAd[DriveClient]
        ORAd[OpenRouterClient]
        DocAd[DocumentExtractors]
    end

    subgraph Persistence
        WriteQ[DBWriteQueue<br/>asyncio.Queue]
        DB[(SQLite WAL)]
    end

    AuthR --> AuthSvc
    DriveR --> DriveSync
    BatchR --> Worker
    EvalR --> EvalGen
    SettingsR --> AuthSvc

    AuthSvc --> WriteQ
    DriveSync --> DriveAd
    DriveSync --> WriteQ
    Worker --> Pipeline
    Worker --> WriteQ
    Pipeline --> DocAd
    Pipeline --> LLMSvc
    EvalGen --> LLMSvc
    EvalGen --> WriteQ
    LLMSvc --> PII
    LLMSvc --> ORAd
    LLMSvc --> Audit
    PII --> WriteQ
    Audit --> WriteQ
    WriteQ --> DB
```

**Key invariants**:
- **All `*_R` Routers are thin** — they handle auth, request validation (Pydantic), call one service, return DTO
- **All DB writes go through `WriteQ`** — services NEVER call DB session directly for writes (reads OK)
- **`LLMSvc` is the only path to `ORAd`** — services that need LLM go through `LLMSvc`, never direct
- **`PII` precedes `ORAd`** — enforced inside `LLMSvc`

### 4.2 Frontend component layers

**易讀說明 — 3 層**：

```
┌─────────────────────────────────────────────────────────────────┐
│ Routes (Next.js App Router pages)                               │
│   layout.tsx / page.tsx / loading.tsx                          │
│   /onboarding/* /semester/* /student/* /file/*                 │
│   /evaluation/* /settings/*                                    │
└──────────────────┬──────────────────────────────────────────────┘
                   │ uses
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Components (reusable presentational)                            │
│                                                                  │
│   UI Primitives        Editor          Wizard                   │
│   - Button             - Markdown      - Mapping Wizard         │
│   - Card               - Mermaid       (D14 onboarding)         │
│   - Badge (7 states)   preview                                  │
│   - Dialog             Progress        State Badges            │
│   - Input/Select       - Batch         (per processing state)  │
│   - Segmented          progress bar                             │
│                        - Cost meter                             │
└──────────────────┬──────────────────────────────────────────────┘
                   │ uses
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│ Lib (shared logic)                                              │
│                                                                  │
│   Custom hooks         API Client            Auth helpers       │
│   - useFiles           (generated TS         (cookie/session)   │
│   - useBatch           from FastAPI                             │
│   - useEvaluation      OpenAPI)                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Mermaid（機器精確版）**：

```mermaid
graph TB
    subgraph Routes [App Router pages]
        Pages[layout / page / loading]
    end

    subgraph Components [Reusable]
        UIPrim[UI Primitives<br/>Button / Card / Badge / Dialog]
        Editor[Markdown Editor<br/>+ Mermaid preview]
        Wizard[Mapping Wizard]
        Progress[Batch Progress + Cost meter]
        Badges[State Badges]
    end

    subgraph Lib [Shared logic]
        Hooks[Custom hooks<br/>useFiles / useBatch]
        APIClient[API Client<br/>generated TS]
        Auth[Auth helpers]
    end

    Pages --> UIPrim
    Pages --> Editor
    Pages --> Wizard
    Pages --> Progress
    Pages --> Badges
    Pages --> Hooks
    Hooks --> APIClient
    Hooks --> Auth
```

### 4.3 External dependencies map

| External | Role | Failure mode | V1 fallback |
|----------|------|--------------|-------------|
| Google OAuth | Authentication | Token expiry / revocation | UI redirects to re-OAuth |
| Google Drive | Source data | Rate limit (429) / permission revoke (403) | Backoff with `Retry-After`; pause batch on 403 |
| OpenRouter | LLM gateway | Rate limit (429) / model deprecated / timeout | Retry up to 3x; fall through to `failed` state |
| SQLite | Local persistence | DB locked (concurrent write) | Retry 3x with backoff (10/100/1000ms) |
| Local FS (audio cache) | Transient | Disk full | Pre-check available space before download; fail batch with clear error |

---

## 5. Deployment Topology

### 5.1 Docker Compose (default — local & VPS)

```yaml
# docker-compose.yml
services:
  app:
    image: teacher-comments:latest
    build: .
    ports:
      - "8000:8000"        # FastAPI
    volumes:
      - ./data:/app/data   # SQLite DB + WAL files
      - ./tmp:/app/tmp     # audio cache (auto-cleaned)
    environment:
      - DATABASE_URL=sqlite+aiosqlite:////app/data/teacher.db
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - PII_ENCRYPTION_KEY=${PII_ENCRYPTION_KEY}
      - OAUTH_TOKEN_ENCRYPTION_KEY=${OAUTH_TOKEN_ENCRYPTION_KEY}
      - PUBLIC_BASE_URL=${PUBLIC_BASE_URL}
    restart: unless-stopped
```

**TLS termination**: assumed external (nginx / Caddy / Traefik) in front. README documents two patterns:
- Behind a reverse proxy on the same host (Caddy auto-TLS)
- Behind a cloud TLS termination (Cloudflare in front of bare TCP)

### 5.2 Fly.io topology

```toml
# fly.toml
app = "teacher-comments-<owner>"
primary_region = "nrt"  # Tokyo for Taiwan latency

[mounts]
  source = "data"
  destination = "/app/data"

[[services]]
  internal_port = 8000
  protocol = "tcp"
  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]
```

Fly secrets supply the same env vars; volume mount preserves SQLite across deploys.

### 5.3 Environment variables (catalogue)

| Variable | Purpose | Example | Required |
|----------|---------|---------|----------|
| `DATABASE_URL` | SQLAlchemy URL | `sqlite+aiosqlite:////app/data/teacher.db` | Yes |
| `GOOGLE_CLIENT_ID` | OAuth client ID | from Google Cloud Console | Yes |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret | from Google Cloud Console | Yes |
| `OPENROUTER_API_KEY` | OpenRouter API access | `sk-or-...` | Yes |
| `PII_ENCRYPTION_KEY` | AES-256 key for `pii_mapping.original_value_encrypted` | base64 32 bytes | Yes |
| `OAUTH_TOKEN_ENCRYPTION_KEY` | AES-256 for refresh token | base64 32 bytes | Yes |
| `PUBLIC_BASE_URL` | **Frontend (user-facing) origin** — used by backend to construct OAuth callback URI `{PUBLIC_BASE_URL}/auth/callback` and the post-login default redirect target. Must point at the origin the browser actually sees, NOT the backend port. Dev: `http://localhost:3000` (Next.js dev server proxies `/auth/*` → :8000). Prod: `https://teacher.example.com`. | `https://teacher.example.com` | Yes |
| `LLM_TIER_SUMMARY_CHEAP` | Override default model for tier | `google/gemini-2.5-flash-lite` | No |
| `LLM_TIER_VISION_CHEAP` | Same | (same default) | No |
| `LLM_TIER_AUDIO_STANDARD` | Same | (same default) | No |
| `LLM_TIER_EVALUATION_QUALITY` | Same | (same default) | No |
| `BATCH_WORKER_CONCURRENCY` | Override default N=4 | `4` | No |
| `BUDGET_MONTHLY_USD` | Hard cap per month | `5.00` | No |
| `LOG_LEVEL` | Python logging level | `INFO` | No |
| `SENTRY_DSN` | Optional error tracking | — | No |

**Secrets generation**:
```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

---

## 6. Cross-cutting Concerns

### 6.1 Logging

- **Format**: JSON structured logs (`structlog`)
- **Required fields**: `timestamp`, `level`, `logger`, `event`, `teacher_id` (when in request context), `request_id`
- **Redaction**: `pii_anonymizer` writes audit logs that contain pseudonyms (`S001`), never raw PII
- **Output**: stdout (Docker / Fly capture)
- **Retention**: out of scope — handled by hosting platform

### 6.2 Configuration management

Per ADR-001 Axis 5 (LLM tiers) and lessons-learned `architecture.md` "Declared Config Must Be Plumbed":

```python
# app/config.py
class Settings(BaseSettings):
    database_url: str
    google_client_id: SecretStr
    google_client_secret: SecretStr
    openrouter_api_key: SecretStr
    pii_encryption_key: SecretStr
    oauth_token_encryption_key: SecretStr
    public_base_url: AnyHttpUrl

    # LLM tier defaults (overridable via env)
    llm_tier_summary_cheap: str = "google/gemini-2.5-flash-lite"
    llm_tier_vision_cheap: str = "google/gemini-2.5-flash-lite"
    llm_tier_audio_standard: str = "google/gemini-2.5-flash-lite"
    llm_tier_evaluation_quality: str = "google/gemini-2.5-flash-lite"

    batch_worker_concurrency: int = 4
    budget_monthly_usd: Decimal = Decimal("5.00")
    ...
```

**Lint rule**: `LLMService.__init__` MUST accept `Settings` and route tier→model via `settings.llm_tier_*`. CI grep test fails the build if any service hardcodes a model ID.

### 6.3 Error propagation

Custom exception hierarchy in `app/core/exceptions.py`:

```
AppError (base)
├── AuthError
│   ├── OAuthRevokedError
│   └── AttestationRequiredError
├── DriveError
│   ├── DriveQuotaExceededError
│   └── DriveFileNotFoundError
├── ProcessingError
│   ├── UnsupportedFormatError      # terminal
│   ├── DocumentExtractionError      # terminal (corrupt files)
│   ├── LLMRateLimitError            # retriable
│   └── LLMTimeoutError              # retriable
├── PIIError
│   ├── PIILeakageError              # boundary check failed (alert!)
│   └── PIIRestorationError          # restore failed (display fallback)
└── ConfigError
```

**Routing**: thrown exceptions mapped to HTTP responses in `routers/` via FastAPI exception handlers. Worker catches at outer level → mapped to `state='failed'` (retriable) or `state='unprocessable'` (terminal — see lessons-learned `architecture.md` "Distinguish Terminal Failures from Retriable Failures").

> **Note for V1**: PRD §4.3 state machine has `failed` only. ARCH-001 recommends adding `unprocessable` (terminal) as a sub-decision in DESIGN-001 — this is **flagged as Open Architectural Question OAQ-1** (§9).

### 6.4 Async coordination

- **Single event loop** per process (FastAPI default uvicorn)
- **`BatchWorker` runs as asyncio tasks** in the same loop as request handling
  - Pros: shared connection pools, no IPC, simpler
  - Cons: long-running CPU-bound work (e.g., docx extraction) can block event loop briefly. Mitigation: `asyncio.to_thread()` for known-blocking operations
- **No multi-processing** for V1 — at the design scale (40 students × 40 docs), single process suffices
- **V2 escape hatch**: `arq` task queue + Redis if scale grows

### 6.5 Database concurrency strategy (SQLite WAL + write queue)

The load-bearing pattern from ADR-001 Axis 6:

```python
# app/db/write_queue.py
class DBWriteQueue:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def submit(self, write_fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
        future = asyncio.Future()
        await self._queue.put((write_fn, future))
        return await future

    async def _drain(self):
        async with AsyncSessionLocal() as session:
            while True:
                write_fn, future = await self._queue.get()
                try:
                    result = await write_fn(session)
                    await session.commit()
                    future.set_result(result)
                except Exception as e:
                    await session.rollback()
                    future.set_exception(e)
```

**Caller pattern**:
```python
# In a service:
async def update_artifact_state(self, artifact_id, state):
    async def _do_update(session):
        artifact = await session.get(ProcessedArtifact, artifact_id)
        artifact.state = state
        return artifact
    return await self.db_write_queue.submit(_do_update)
```

**Why this pattern wins**:
- Single writer (one task draining the queue) — eliminates SQLite `database is locked` errors
- Transactional integrity — each `submit` is one transaction
- Backpressure — queue depth observable for performance monitoring
- ~5ms added latency per write — acceptable for V1's batch profile

**Reads bypass the queue** — they create their own short-lived sessions.

---

## 7. Performance Architecture

### 7.1 Worker pool sizing

V1 default `BATCH_WORKER_CONCURRENCY = 4`. Tuning guidance (TODO T-4):

| Constraint | Approximate cap |
|-----------|------------------|
| Drive API rate limit | 1000 reqs / 100s / user → ~10/s sustained |
| OpenRouter rate limit | Provider-dependent; typically 60+ rpm Tier 1 free → 1/s sustained for Flash Lite |
| SQLite write queue | ~1000 writes/s observed locally |
| Single CPU core (audio extract) | 1-2 in parallel safely |

Worker count of 4 keeps all upstream limits comfortable without saturating. Higher concurrency (8+) risks 429s and audio extraction CPU contention.

### 7.2 Token budget per tier

Calculated for default Flash Lite at $0.10/1M input, $0.40/1M output (approximate):

| Tier | Avg input tokens | Avg output tokens | Cost / call | Calls / semester |
|------|------------------|-------------------|-------------|------------------|
| `summary_cheap` | 2,000 | 600 | ~$0.0004 | 1,500 |
| `vision_cheap` | 3,000 (incl. image) | 800 | ~$0.0006 | 100 |
| `audio_standard` | 100,000 (audio = 32 tokens/sec × 30min) | 5,000 | ~$0.012 | 120 |
| `evaluation_quality` | 5,000 (3-category context) | 600 | ~$0.0007 | 40 |

Total ~$2/semester for ALL Flash Lite. PRD §6.2 conservative estimate held.

### 7.3 Cost tracking implementation

Every `LLMService.call()` writes one `llm_call_audit` row with: `tier`, `model_id`, `input_tokens`, `output_tokens`, `cost_usd`. Settings dashboard SUMs by month for the budget cap (PRD §6.2 — Budget pause logic).

---

## 8. Security Architecture

### 8.1 Authn/Authz flow

**易讀說明 — 線性連結**：

```
Browser
   │ (session cookie: HttpOnly + Secure + SameSite=Lax)
   ▼
Frontend (SSR via Next.js)
   │ (forwards cookie)
   ▼
Backend API
   │ (verify session) ─────► DB: SELECT teacher WHERE google_sub=...
   │
   │ (use refresh_token) ─► Google OAuth: refresh access_token
   │                              │
   │                              ▼ (returns new access_token)
   │ (use access_token)  ─► Google Drive: drive.files.list
```

**3 個重點**：
- Session 儲存於 HttpOnly + Secure cookie，由 `SECRET_KEY` 簽章
- Token refresh 為 lazy：Drive API 收到 401 才 refresh，不主動更新
- 單帳號 enforcement（A6）：session 取出 `teacher_id` 若與 DB 中唯一一行不同 → 直接 403

**Mermaid（機器精確版）**：

```mermaid
graph LR
    Browser -->|cookie| FE[Frontend SSR]
    FE -->|cookie| BE[Backend API]
    BE -->|verify session| DB[(teacher table)]
    BE -->|use refresh_token| GO[Google OAuth]
    GO -->|new access_token| BE
    BE -->|access_token| GD[Google Drive]
```

- **Session storage**: HttpOnly + Secure cookies signed by `SECRET_KEY` (in env)
- **Token refresh**: lazy, on Drive call 401 → refresh → retry
- **Single-user enforcement** (per A6): if a session lookup returns a `teacher_id` different from the only existing row, **route reject** (403). For V1, the `teacher` table can have only one row.

### 8.2 PII boundary enforcement

The system has **two layers** of PII protection:

1. **PIIAnonymizer Service** — replaces PII with pseudonyms (regex + folder-name detection)
2. **LLMService boundary check** — runs known-PII regex on `anonymized_text` immediately before HTTP POST; raises `PIILeakageError` if any hit

The boundary check is intentionally redundant — if Anonymizer has a bug, the boundary catches it. Both layers are tested with the same `pii_test_corpus.json` (TDD-001 §X).

### 8.3 Encryption key management (V1)

| Key | Storage | Rotation policy | If lost |
|-----|---------|-----------------|---------|
| `OAUTH_TOKEN_ENCRYPTION_KEY` | Env var | Manual rotation = re-encrypt all `oauth_refresh_token_encrypted` rows; users may need to re-OAuth | All sessions invalidated; users re-login |
| `PII_ENCRYPTION_KEY` | Env var | Manual rotation = re-encrypt all `pii_mapping.original_value_encrypted` rows | PII mapping lost; system can no longer restore display names (functional but degraded) |

**Key rotation script** is part of the admin CLI (DESIGN-001 §X). Both encryptions use AES-256-GCM with random per-record nonce.

V2 may move keys to AWS KMS / GCP Secret Manager — escape hatch documented in ADR-001 Axis 6 consequences.

---

## 9. Open Architectural Questions

| OAQ | Question | Disposition |
|-----|----------|-------------|
| **OAQ-1** | Should V1 add `unprocessable` (terminal) state alongside `failed` (retriable)? Lessons-learned `architecture.md` strongly recommends. PRD §4.3 has only `failed`. | Recommend YES; defer concrete schema decision to DESIGN-001 — if accepted there, log as `D-2026-05-NN-NN` reversal of PRD §4.3 fragment |
| **OAQ-2** | Should the worker run in-process (current ARCH plan) or as a separate worker container? | V1 in-process (Axis 4 commitment); V2 split if scale demands |
| **OAQ-3** | Should the frontend be served by FastAPI's static-file mount or a separate Next.js server? | Single container with Next.js standalone build mounted under `/app` — DESIGN-001 to confirm Dockerfile pattern |
| **OAQ-4** | How is the frontend's session cookie set when frontend and backend share a domain vs subdomains? | Same domain in V1 (`teacher.example.com`); subdomain split out of scope |
| **OAQ-5** | Should there be a `system_event` table for non-LLM audit (login attempts, key rotations, schema migrations)? | Recommend YES for V1 — small schema, big debugging value |

These resolve in DESIGN-001 (or follow-up ADR if architecturally significant).

---

## 10. References

- [`docs/PRD.md`](PRD.md) v0.2 — functional spec
- [`docs/adr/ADR-001-system-foundation.md`](adr/ADR-001-system-foundation.md) — architectural axes
- [`docs/adr/DECISIONS.md`](adr/DECISIONS.md) — decision log
- `~/.claude/lessons-learned/architecture.md` — pipeline / state machine patterns
- `~/.claude/lessons-learned/frontend.md` — Alpine/React reactive state pitfalls
- `~/.claude/lessons-learned/api-design.md` — retry / rate limit (informs §4.3, §6.3)

---

> **End of ARCH-001 v0.1**. Next doc: DESIGN-001 (per-module API contracts, error matrices, config plumbing details).
