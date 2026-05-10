# ADR-001: System Foundation — Architectural Axes for Teacher Comments System

| Field | Value |
|-------|-------|
| **Status** | Accepted |
| **Date** | 2026-05-10 |
| **Decider(s)** | Steven Chen (with Claude Code in advisory role) |
| **Supersedes** | — |
| **Superseded by** | — |
| **Related** | [`docs/PRD.md`](../PRD.md), [`docs/adr/DECISIONS.md`](DECISIONS.md) D-2026-05-10-02 / D-2026-05-10-03 |

---

## 1. Context

This document records **the architectural foundation** of the Teacher Comments System, captured after a 2-stage discussion (7-baseline + 13 OQ resolution) with the deciding engineer. The PRD (`docs/PRD.md` v0.2) freezes the **decisions**; this ADR records the **alternatives considered and rejected**, so future agents / engineers can audit the reasoning rather than repeat the analysis.

### 1.1 Problem domain

A K-12 individual teacher needs to write **300-500 character semester comments** for ~40 students per semester. Source materials live in Google Drive across three categories per student (learning records, teacher-student interactions, work outputs) in heterogeneous formats (text, documents, images, audio recordings). The teacher has the materials and the observations but lacks the time/cognitive bandwidth to integrate them into precise prose. **Templated comments** (which parents detect) are the failure mode this system is designed to prevent.

### 1.2 Constraints (binding)

| Constraint | Source | Notes |
|------------|--------|-------|
| **Compliance**: minor's PII must not leave system boundary | A2 in PRD §2.3 | Drives every data-flow decision |
| **Single teacher use** | A6 in PRD §2.3 | No multi-tenant complexity |
| **V1 ships complete** | D7 | No phased delivery; PRD is one full spec |
| **Cost target**: < $5/teacher/semester | §1.3 metric | Drives LLM tier choice |
| **Reliability**: batch processing must be interruptible/resumable | D4 | Drives state machine + DB choice |

### 1.3 What this ADR covers

Seven architectural axes whose decisions cut across the entire system:

1. **Deployment & Tenancy** — who runs it, who uses it
2. **Tech Stack** — what language/framework
3. **Data & Privacy** — how PII is handled
4. **Processing Model** — when and how files become summaries
5. **LLM Architecture** — model selection and routing
6. **Persistence** — what database
7. **Distribution** — how V1 is packaged and delivered

Per-axis detail is below. Decisions outside these axes (D5, D6, D7, D10-D14, D17) are sufficiently captured in PRD §2 and DECISIONS.md and do not warrant ADR-level depth.

---

## 2. Axis 1 — Deployment & Tenancy

**Question**: Who deploys the system, and who uses each instance?

### 2.1 Options Evaluated

| # | Option | Pros | Cons |
|---|--------|------|------|
| A | Multi-tenant SaaS (school-deployed, many teachers) | Economies of scale; institutional billing | Tenant isolation, billing, IT governance, multi-teacher consent flows; ~6+ months extra engineering |
| B | **Single-user single-tenant SaaS (one teacher, one cloud instance)** | Minimal auth/permissions complexity; OAuth simple; cloud always-on | Per-teacher deployment friction; not viral |
| C | Local-first (teacher runs on own laptop) | Strongest privacy; no cloud cost | OAuth callback over HTTPS hard from desktop; background processing needs always-on; audio CPU-intensive |
| D | Hybrid local-first with cloud sync | Best of both? | Dual codebase; sync conflict resolution; effectively two products |

### 2.2 Decision: **B** (D1 in PRD)

### 2.3 Rationale

- **A rejected**: V1 is a personal pilot, not a platform. The complexity of multi-tenancy (per-tenant data isolation, RBAC, billing, school-IT compliance reviews) would extend V1 by 6+ months. Even if the project later grows, a working single-tenant version validates the core value before investing in tenancy infrastructure.
- **C rejected**: Three blockers — (i) Google OAuth requires HTTPS callback URLs, awkward from a residential network; (ii) batch processing of audio is CPU-bound for tens of minutes — running this while the teacher uses their laptop is a poor experience; (iii) the system needs to be reachable from any browser the teacher happens to use, not just the laptop where it's installed.
- **D rejected**: A "best of both worlds" architecture in early-stage projects becomes a "both worst of both" — sync conflict resolution alone is a multi-week project, the codebase forks into local-and-cloud branches, and shipping V1 stalls waiting for parity.
- **B chosen**: Each teacher runs their own cloud instance (own VPS, own Fly.io app, etc.). OAuth is simple (one server callback URL). No tenant isolation logic. No billing (deployment cost is between teacher and cloud provider). Implementation footprint matches V1 scope.

### 2.4 Consequences

- ✅ Auth model is trivial: one OAuth grant per instance; no user-permission tables
- ✅ DB schema can use `teacher` as a single-row constraint (logically — schema still parametrized for future migration to multi-tenant)
- ⚠️ Teacher must self-deploy or find a hosted-by-someone option (mitigated by D15 — Docker + fly.toml ready-to-deploy)
- ⚠️ Migration to multi-tenant SaaS in V3+ requires schema changes (foreseen — see Axis 6 / persistence)

---

## 3. Axis 2 — Tech Stack

**Question**: What language and framework stack for backend and frontend?

### 3.1 Options Evaluated

| # | Option | LLM ecosystem | Doc/audio libs | Type safety | Iteration speed |
|---|--------|---------------|----------------|-------------|-----------------|
| A | **Python (FastAPI) + Next.js (React)** | Best (anthropic, openai, langchain native) | Best (`pypdf`, `python-docx`, `openpyxl`, `python-pptx`) | Pyright/mypy strict mode | High |
| B | Node.js full-stack (Next.js end-to-end) | Good (TS SDKs lag Python) | OK (`pdf-parse`, `mammoth` weaker than Python equivalents) | TS native | High |
| C | Go backend + React frontend | Limited (no first-class anthropic SDK) | Build-from-scratch territory | Strong native | Medium |
| D | Rust backend + React frontend | Limited (community SDKs only) | Build-from-scratch | Strongest native | Low (greenfield Rust = slow) |
| E | Python full-stack (Django + templates / FastHTML) | Best | Best | Same as A | Medium (frontend richness limited) |

### 3.2 Decision: **A — Python (FastAPI) + Next.js (React)** (D2 in PRD)

### 3.3 Rationale

- **A chosen**: Two load-bearing reasons:
  1. **LLM and document-processing ecosystem maturity is in Python**. Anthropic SDK, OpenAI SDK, and OpenRouter integration are first-class in Python; community libs lag in TS by months. `pypdf`, `python-docx`, `openpyxl`, `python-pptx` together cover all V1 document formats with mature codebases. Equivalent JS libs exist but have known parsing edge cases for complex Office files.
  2. **FastAPI's async-native model** matches the batch-processing pipeline (multiple concurrent LLM calls with shared rate-limit budget). Pydantic V2 + FastAPI means request/response schemas double as runtime validation.
- **B rejected**: Node has the unification appeal (one language, one tooling), but the LLM-and-document-processing penalty would force us to pick between (i) calling Python services from Node (worst of both), (ii) rebuilding mature Python libs in TS (massive scope creep), or (iii) accepting weaker output quality. The DX win of one language doesn't compensate.
- **C rejected**: Go's typing is excellent for backend services, but the LLM ecosystem is too immature. We'd be the SDK author for several integrations. Unacceptable risk for V1.
- **D rejected**: Rust's borrow-checker overhead in a greenfield project where requirements are still settling would slow iteration substantially. Reserved for V3+ if performance requires it.
- **E rejected**: Mixing UI logic into Python templates limits frontend richness. The PRD has at least three rich UI components (mapping wizard D14, batch progress with edit-conflict prompts F-7/F-8, evaluation editor with Markdown preview F-10) that benefit from React state management. Server-rendered templates make these awkward.

### 3.4 Consequences

- ✅ Backend can use SQLAlchemy + Alembic (mature ORM + migrations) regardless of DB choice (Axis 6)
- ✅ Frontend can use Next.js App Router with Server Actions for simple cases, REST API for batch state polling
- ✅ Frontend / backend repo separation: easy to deploy as one Docker image (Next.js builds static + FastAPI serves both API and static) OR two services
- ⚠️ Two-language codebase means two test suites (pytest backend, vitest/jest frontend); two dependency managers (uv/pip + npm/pnpm)
- ⚠️ Type definitions for API contracts must be shared — recommended pattern: generate TS types from OpenAPI schema (FastAPI native)

---

## 4. Axis 3 — Data & Privacy

**Question**: How is student PII handled when sending content to external LLM providers?

### 4.1 Options Evaluated

| # | Option | Privacy guarantee | Implementation cost | Quality impact |
|---|--------|-------------------|---------------------|----------------|
| A | No special handling (trust LLM ToS) | None | Zero | None |
| B | PII detection + warn before send | Soft (user clicks "yes") | Low | None |
| C | **PII anonymization (replace before send, restore after)** | Strong (no PII in LLM context) | Medium | Minimal (LLM still gets full context with placeholders) |
| D | Fully on-device LLM | Strongest (no data leaves) | Very high (GPU, model deployment) | Significant (local models < frontier models for evaluation) |
| E | Federated (split sensitive vs non-sensitive) | Variable | Very high (decision logic itself error-prone) | Variable |

### 4.2 Decision: **C** (D3 in PRD)

### 4.3 Rationale

- **A rejected**: Insufficient. Three converging reasons: (i) minors' personal data has stronger legal protections (Taiwan 個資法 §21 cross-border transfer requirements; equivalent regimes elsewhere); (ii) OpenRouter is a router — final providers' training-data policies vary, even with `data-policy: no-training` headers, providing zero compliance evidence; (iii) the *appearance* of carelessness alone could destroy parent trust if discovered.
- **B rejected**: A halfway measure that fails the specific failure mode it tries to address. Teacher encounters "do you want to send PII?" → clicks yes → PII goes anyway. The friction either trains the teacher to click through (ineffective) or stops them from using the system (useless). Either way, no compliance value.
- **D rejected**: Local LLMs strong enough for the evaluation generation task (frontier-class quality) require server GPUs that defeat the personal-cloud-SaaS model (Axis 1). Whisper-class STT can run on CPU but slowly. V1 audio generation alone would be unbearably slow. Reserved for V3+ if hardware drops in price.
- **E rejected**: "Decide what's sensitive" logic is itself a PII detection problem in disguise. Either we have a robust PII detector (in which case use it for full anonymization C), or we have a partial one (in which case the federation logic leaks PII through the cracks). Composing E adds error surfaces without removing them.
- **C chosen**: Provides a *hard guarantee* — if the anonymizer is correct, no PII reaches the LLM. The LLM still receives full context (replaced with stable pseudonyms like `S001`), preserving its ability to do its job. After response, the system restores `S001` → `display_name` for the teacher's view. Audit-friendly: every anonymize/restore call logged.

### 4.4 Consequences

- ✅ Compliance: hard answer to "does PII leave system?" = no (assuming anonymizer correctness)
- ✅ All LLM calls go through one chokepoint (LLM Service) which enforces anonymizer pre-call (PRD §8 architecture diagram)
- ⚠️ Anonymizer correctness becomes a **critical security boundary** — must be tested with high coverage (AC-6 mandates ≥95% detection on 100-row test fixture)
- ⚠️ V1 uses rule-based detection (regex + folder-name strong signals); known limitations on short Chinese names (`子涵`); V2 may add NER (TODO T-3)
- ⚠️ Audio is special — original file can't be anonymized in audio form, so STT must produce text-with-PII first, then immediately anonymize before storing or sending to subsequent LLM calls. Audio file is deleted from local cache after STT (PRD §A3).

---

## 5. Axis 4 — Processing Model

**Question**: When and how does the system process Drive files into summaries/transcripts?

### 5.1 Options Evaluated

| # | Option | First-time UX | Resilience to interrupts | Cost predictability | Complexity |
|---|--------|---------------|--------------------------|---------------------|------------|
| A | Lazy on-demand (process when teacher opens a file) | Bad (30s-2min wait per file) | Trivial (no batch state) | Bad (cost spikes when teacher browses) | Low |
| B | Eager daemon (background polls Drive, processes on change) | Good (always pre-processed) | Hard (long-running daemon) | Bad (idle polling cost; reprocess churn) | High |
| C | **Batch trigger (teacher clicks button to process semester)** | Good after one click | Designed-in (state machine + resume) | Good (teacher knows when cost happens) | Medium (state machine + edit protection) |
| D | Hybrid (eager for new files, lazy for existing) | Mixed | Hard (mode synchronization) | Mixed | High |

### 5.2 Decision: **C** (D4 in PRD)

### 5.3 Rationale

- **A rejected**: First-time browse is broken — teacher opens semester to browse, every click costs 30-120s. Even with caching, the first traversal of 1,600 files = several hours of click-and-wait. Defeats "browse semester at a glance" need.
- **B rejected**: Three real costs: (i) Drive change webhooks require a public callback URL and certain Drive API permissions, adding deployment friction; (ii) polling intervals trade off freshness against cost — even minimal polls (every 30 min) accumulate over a semester; (iii) reprocess churn — every minor edit to a Drive file triggers reprocessing, but teachers don't want reprocessing immediately, they want it before the next semester batch. Teacher's natural rhythm is **semester-batch**, not **continuous-stream**.
- **D rejected**: Mixing modes requires defining "what counts as new" boundary — every such boundary becomes a state-management bug surface. The PRD's `reprocess_pending` state already requires teacher confirmation; adding an "automatic-for-new-files" path that bypasses this confirmation creates trust failures (teacher doesn't realize a file got reprocessed without their consent).
- **C chosen**: Matches teacher's mental model. Persistent state (`batch_job` + per-artifact `state`) means resumability is designed in, not retrofitted. Progress UI gives teacher transparency. Edit-conflict prompts (D4 secondary requirement) preserve teacher trust — a critical boundary for a system that processes their judgement-laden materials.

### 5.4 Consequences

- ✅ State machine (PRD §4.3) is the load-bearing architectural element — the diagram is the spec
- ✅ Resume-after-crash logic is straightforward: `state='processing' AND updated_at > 5min ago` → reset to `pending`
- ✅ Edit-protection state (`teacher_edited` → `reprocess_pending`) is the trust-preservation feature; absent in lazy or daemon models
- ⚠️ Worker pool concurrency (default N=4) needs tuning under real Drive API rate limits (TODO T-6)
- ⚠️ DB write serialization required (see Axis 6 — SQLite single-writer constraint)

---

## 6. Axis 5 — LLM Architecture

**Question**: How are LLM model selections structured across the system?

### 6.1 Options Evaluated

| # | Option | Cost predictability | Quality fit per task | Future-proofing | Auditability |
|---|--------|---------------------|----------------------|-----------------|--------------|
| A | Single hardcoded model | Bad (one cost/quality point fits no task) | Bad | Bad (model deprecation = code change) | OK |
| B | Per-call config (each caller specifies model) | OK | OK (caller's choice) | Bad (changes touch many files) | Bad (must read every call site) |
| C | **Tier-based routing (4 abstract tiers, models settable in config)** | Good (per-tier cost ceiling) | Good (tier matches task) | Good (model swap is config change) | Good (one LLM Service module) |
| D | Cost-aware dynamic routing (system picks cheapest meeting quality) | Best in theory | Hard to measure quality | Complex | Hard |

### 6.2 Decision: **C** (D8 in PRD), with V1 default = `google/gemini-2.5-flash-lite` for all tiers (D9)

### 6.3 Rationale

- **A rejected**: All-Sonnet costs ~$15/semester (3x target); all-Haiku produces poor evaluation (the high-stakes output for parents). One model is the wrong tool for at least one of the four very different tasks.
- **B rejected**: Distributing model selection across many call sites means "which model does our system use?" requires reading code, not config. Auditability matters (T-5: confirm `data-policy: no-training` coverage). Hard to satisfy compliance asks like "list every model touching student data" if it's scattered.
- **D rejected**: Quality measurement for natural language output is fuzzy at best. Building a routing oracle is itself an ML problem. Premature optimization for V1.
- **C chosen**: Four task tiers cover the actual cost/quality variance:
  - `summary_cheap` — extractive summarization (text/document → markdown). Cheap models adequate.
  - `vision_cheap` — image OCR + structural description. Cheap multimodal models adequate.
  - `audio_standard` — STT + speaker diarization. Mid-tier quality matters (diarization fragile).
  - `evaluation_quality` — semester comment generation. High-stakes parent-facing output; quality matters most.

  PRD §6.2 sets each tier's default model in Settings; teacher can swap individually. V1 ships with all-Flash-Lite (cheapest known acceptable model) and an upgrade path documented for evaluation tier specifically.

### 6.4 Consequences

- ✅ LLM Service is a single module = single chokepoint for PII anonymizer enforcement (Axis 3 synergy)
- ✅ Cost dashboard (PRD §6.5) can break down by tier
- ✅ Model deprecation by provider (Flash Lite is `preview` — see TODO T-1) handled by Settings change, not code change
- ⚠️ V1 quality calibration — Flash Lite's evaluation quality is the largest unknown (TODO T-7)
- ⚠️ Tier definitions are an implicit contract — adding a 5th tier later is fine, but renaming an existing tier requires a migration

---

## 7. Axis 6 — Persistence

**Question**: What database for V1?

### 7.1 Options Evaluated

| # | Option | Deployment complexity | Concurrent writes | Backup | Migration to multi-tenant |
|---|--------|----------------------|-------------------|--------|---------------------------|
| A | PostgreSQL | High (separate process, config) | Native MVCC | pg_dump | Already there |
| B | **SQLite + WAL + aiosqlite** | Zero (embedded) | Single-writer, multi-reader (WAL) | File copy | Migration needed (1-2 days via SQLAlchemy) |
| C | MongoDB | High | Native | mongodump | Already document-oriented |
| D | File-based JSON / no DB | Zero | Race conditions | tarball | Total rewrite |

### 7.2 Decision: **B — SQLite + WAL + aiosqlite** (D16 in PRD)

### 7.3 Rationale

- **A rejected**: Postgres is the right answer for multi-tenant SaaS, but Axis 1 ruled that out for V1. For single-user, the deployment overhead (separate process; needs `pg_hba.conf`, `postgresql.conf`; backup is its own discipline; container orchestration adds a second service to docker-compose) is pure complexity tax with no compensating benefit.
- **C rejected**: No clear advantage over relational for this schema. Document-oriented features (flexible schema, embedded subdocuments) are unused — the schema is well-defined and relational. JSON-like fields are covered by SQLite's `json1` module.
- **D rejected**: Concurrent batch worker writes would race-condition without DB-level transactions. Querying by state (`SELECT * FROM processed_artifact WHERE state='pending'`) becomes a full file scan. Atomicity (state transitions during interrupts) requires DIY locking.
- **B chosen**: SQLite's "no external dependency" is the deciding factor for SaaS-of-one. WAL mode enables concurrent reads under writers (matching FastAPI async request load). `aiosqlite` provides async-compatible I/O. SQLAlchemy + Alembic operate identically against SQLite or Postgres, so V2 migration to Postgres (if multi-tenant happens) is 1-2 days of work, not a rewrite.

### 7.4 Consequences

- ✅ Backup is `cp teacher-comments.db backup-2026-05-10.db` — no operational discipline required
- ✅ docker-compose.yml has one service (app), not two
- ✅ Tests can use in-memory `:memory:` SQLite for fast unit/integration coverage
- ⚠️ **SQLite single-writer limitation** — concurrent batch workers cannot all `INSERT` simultaneously. Mitigation: `asyncio.Queue` in the app layer serializes all DB writes (PRD §6.3, §10). Adds ~5ms latency per write but eliminates the writer-lock contention class of bug entirely.
- ⚠️ **No native full-text search at scale** — SQLite FTS5 is fine for ~10K rows but degrades on 1M+. Not a V1 concern; relevant for V3+ multi-tenant.
- ⚠️ **Migration to Postgres requires** (i) `aiosqlite` → `asyncpg`, (ii) some boolean/datetime type adjustments, (iii) replacing SQLite-specific features (JSON1 → JSONB). SQLAlchemy abstracts most of this; estimated 1-2 days V2 work.

---

## 8. Axis 7 — Distribution

**Question**: How is V1 packaged and delivered to its users (teachers)?

### 8.1 Options Evaluated

| # | Option | Onboarding friction | Vendor lock-in | Update path | Cost transparency |
|---|--------|---------------------|----------------|-------------|-------------------|
| A | Source code only (DIY) | High (Python venv, Node, OAuth setup) | None | `git pull` | Variable |
| B | Single Docker image | Medium | None | Image tag | Clear |
| C | **Docker compose + fly.toml + README guides** | Low | None (multi-target) | `docker-compose pull && up` | Clear (per-deploy) |
| D | Cloud-native (locked to one of Fly.io / Render / Railway) | Lowest | Severe | Provider-managed | Provider-managed |
| E | Native binary (PyInstaller / similar) | Low | None | Re-download | Clear |

### 8.2 Decision: **C** (D15 in PRD)

### 8.3 Rationale

- **A rejected**: First-impression onboarding requires a teacher (technical or not) to handle Python venv, Node setup, environment variables, OAuth client registration — too many ways to fail. Even technical users find a 30-minute setup off-putting for "just trying it."
- **B partially adopted**: Single Docker image is the *building block*, but alone it doesn't address (i) data persistence (volume mount), (ii) OAuth secrets handling (env vars), (iii) reverse proxy / TLS termination guidance. Compose handles all of these.
- **D rejected**: Locking to one provider (e.g., Fly.io only) creates "the day Fly.io changes pricing" risk. Even Fly's own customers have been surprised by retired regions. For a tool that we want teachers to deploy themselves, vendor lock-in moves their data hostage to a third party.
- **E rejected**: Python doesn't compile cleanly to single binary. PyInstaller works but bloats binary, has flagship libraries (e.g., `pypdf`) that don't always bundle cleanly. Frontend still needs separate web server. Net: doesn't simplify anything for the user vs. Docker.
- **C chosen**: Compose + fly.toml + README means **one Docker image, three deploy paths** — own VPS, Fly.io, local development. README's deployment section walks through each. No vendor lock-in. No per-target image variation.

### 8.4 Consequences

- ✅ Teacher chooses cost/control trade-off (Hetzner VPS at ~$5/mo, Fly.io at ~$5-10/mo, or local for free during pilot)
- ✅ Single Docker image used across all targets means CI builds once, deploys anywhere
- ✅ Migration between targets is a redeploy + DB file copy
- ⚠️ Each deploy path has its own gotchas (volume mounts for persistence, TLS for production) — README must be carefully written
- ⚠️ Fly.io's `fly.toml` includes secrets management; VPS deploys need a `.env` discipline. Both documented but operationally different.

---

## 9. Cross-Axis Consequences

Several axes compound:

| Combination | Compound effect |
|-------------|-----------------|
| **Axis 1 (single-user) × Axis 6 (SQLite)** | Backup = `cp` is a coherent story. Multi-tenant would need both axes revisited. |
| **Axis 3 (anonymizer) × Axis 5 (LLM Service chokepoint)** | Single enforcement boundary — anonymizer can be `assert`-checked at LLM Service entry. Audit log proves compliance. |
| **Axis 4 (state machine) × Axis 6 (SQLite WAL)** | DB write serialization queue is the meeting point — state transitions are atomic, batch resume is correct. |
| **Axis 2 (Python) × Axis 3 (anonymizer)** | Python's regex + `python-docx`/`pypdf` text extraction → anonymizer text replacement → LLM call: all in one async call chain, no IPC. |
| **Axis 5 (tier routing) × Axis 7 (Docker deploy)** | Tier model IDs in env vars / config — change deployed instance's models without rebuilding image. |

---

## 10. Status Tracking

| Axis | Decision ID(s) | Status | Reverse risk* |
|------|---------------|--------|---------------|
| 1 — Deployment & Tenancy | D1, A6 | Accepted | Low for V1; high if going multi-tenant V3+ |
| 2 — Tech Stack | D2 | Accepted | Very low (sunk cost) |
| 3 — Data & Privacy | D3 | Accepted | Very low (compliance-driven) |
| 4 — Processing Model | D4 | Accepted | Low; daemon mode is V2 candidate |
| 5 — LLM Architecture | D8, D9 | Accepted | Low for tier model (config-driven); medium for tier definitions |
| 6 — Persistence | D16 | Accepted | Medium — Postgres migration if V2 multi-tenant |
| 7 — Distribution | D15 | Accepted | Low |

\* "Reverse risk" = how disruptive a future ADR-NN reversal would be. Low = config / module-local change. Medium = schema or interface change. High = cross-cutting refactor.

---

## 11. References

- [`docs/PRD.md`](../PRD.md) v0.2 §2 — full decision table with short rationales
- [`docs/adr/DECISIONS.md`](DECISIONS.md) `D-2026-05-10-02` and `D-2026-05-10-03` — decision-log entries
- `~/.claude/lessons-learned/engineering-process.md` — Three-Tier Decision Governance (the framework this ADR participates in)
- `~/.claude/lessons-learned/architecture.md` — explicit state machines for pipelines (informs Axis 4)
- `~/.claude/lessons-learned/database.md` — SQLite concurrency caveats (informs Axis 6)

---

## 12. How to Reverse This ADR

If a future decision supersedes any axis here:

1. Create new ADR (`ADR-002-...md`) with `Supersedes: ADR-001 §X` field in header
2. In this file, update §10 status row to `Superseded` and add `Superseded by: ADR-002` link
3. Add a `D-YYYY-MM-DD-NN` entry to DECISIONS.md with `Reverses:` field pointing to the original D-NN
4. **Explain the root cause** (per `engineering-process.md` Reversal Protocol) — not "user changed mind", but "why was the original axis wrong"

This file is **append-mostly**; the only allowed edits are §10 status updates per the protocol above.
