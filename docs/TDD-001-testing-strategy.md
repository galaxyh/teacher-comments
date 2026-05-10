# TDD-001: Testing Strategy (incl. Playwright E2E)

| Field | Value |
|-------|-------|
| **Status** | Draft v0.1 |
| **Date** | 2026-05-10 |
| **Owner** | Steven Chen |
| **Depends on** | [`PRD.md`](PRD.md) §11 (AC), [`DESIGN-001-detailed-design.md`](DESIGN-001-detailed-design.md), [`BDD-001-behavior-scenarios.md`](BDD-001-behavior-scenarios.md), [`UIUX-001-design-system.md`](UIUX-001-design-system.md) |

---

## 0. Document Control

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 0.1 | 2026-05-10 | Steven (with Claude Code) | Initial — pyramid, mock strategy, Playwright E2E, fixtures, CI, coverage |

**Reading order**:
- §1 Strategy → §2 Pyramid (set the picture)
- §3 Mock Strategy (load-bearing — many lessons-learned hits)
- §4 Backend tests → §5 Frontend tests → §6 Playwright E2E
- §7 Test data management → §8 CI integration → §9 Coverage targets

---

## 1. Strategy

### 1.1 Goals

1. **Catch regressions before users see them** — every code change verified by automated tests
2. **Document expected behavior** — tests double as executable spec (BDD-001 scenarios materialize here)
3. **Enable refactoring** — high coverage on critical paths so internal changes are safe
4. **Survive AI-generated code** — assume LLM-written code may have subtle bugs; tests are the safety net

### 1.2 Non-goals

- 100% coverage (diminishing returns past ~85%)
- Performance benchmarking (separate effort, not part of CI)
- Manual QA replacement (manual exploratory testing still needed pre-release)

### 1.3 Test pyramid

```
                   ▲
                   │  E2E (Playwright)        ~30 tests
                   │  ───────────────         ~5 min CI
                   │
                   │  Integration             ~150 tests
                   │  ──────────────          ~3 min CI
                   │  (FastAPI TestClient
                   │   + real SQLite + mock LLM)
                   │
                   │  Unit                    ~600 tests
                   │  ────                    ~30 sec CI
                   │  (services, utils, types)
                   ▼
```

| Layer | Count target | Speed | Confidence | Where bugs caught |
|-------|--------------|-------|------------|-------------------|
| Unit | ~600 | < 30s | Logic correctness | Function-level |
| Integration | ~150 | < 3min | Service composition + DB | Service-to-service |
| E2E (Playwright) | ~30 | < 5min | User flow correctness | UI/UX + integration gaps |

**Why this shape**:
- Unit tests are cheap and run fast — give the most coverage per dollar
- Integration tests verify composition (the place where TDD pyramid traditionally fails)
- E2E tests are expensive but catch the "did the user actually see it?" failure mode
- Lessons-learned `testing.md` "Audit the full request chain before E2E" — keeping E2E count low (~30) makes that audit affordable

---

## 2. Test Pyramid Composition

### 2.1 Unit tests (target: ~600)

**What**: pure functions, isolated services with mocked collaborators.

**Coverage focus**:
- All `app/services/*.py` public methods (PIIAnonymizer, LLMService, etc. — DESIGN-001 §4)
- All `app/adapters/document_extractors/*.py`
- All `app/core/exceptions.py` mapping logic
- All Pydantic schema round-trips
- All utility functions

**Tools**:
- `pytest` + `pytest-asyncio` for async tests
- `pytest-mock` for collaborator mocks
- `hypothesis` for property-based testing of PII detection (V2 stretch — V1 if time allows)

**Frontend unit (~150 of the 600)**:
- React component rendering with mocked props
- Custom hook behavior with mocked API client
- Tools: `vitest` + `@testing-library/react`

### 2.2 Integration tests (target: ~150)

**What**: multi-service composition, real DB (in-memory SQLite), mock LLM, mock Drive.

**Coverage focus**:
- BatchWorker end-to-end with real DB transactions
- DriveSyncService scan flow with mocked DriveClient
- ProcessingPipeline routing per category × mime
- DBWriteQueue under load (100+ concurrent submits)
- Auth + attestation flow with mocked Google OAuth

**Tools**:
- `pytest` + FastAPI's `TestClient` (or `httpx.AsyncClient` directly)
- `pytest-asyncio`
- `aiosqlite` with `:memory:` URI for fast isolated DBs

**Pattern**:
```python
@pytest.fixture
async def app_with_test_db():
    test_settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        ...
    )
    app = create_app(test_settings)
    async with LifespanManager(app):
        yield app
```

### 2.3 E2E tests (target: ~30)

**What**: real browser via Playwright, real frontend, real backend, mock LLM and Drive.

**Coverage focus**:
- The 10 happy-path BDD scenarios (one per feature F-1 to F-10)
- 5 critical edge cases (mapping wizard, PII conflict resolution, batch crash recovery, eval regenerate, attestation re-sign)
- Mobile read-only behavior (3 scenarios)
- Accessibility audit (axe-core integration on every page)

**Tools**:
- Playwright (`@playwright/test`)
- `axe-core` for a11y
- Custom test fixtures for backend setup (per §6.4)

---

## 3. Mock Strategy (load-bearing)

> Per `lessons-learned/testing.md`: mocks must produce **structurally valid output** for every schema; otherwise tests fail deep in business logic with cryptic errors.

### 3.1 LLM mock — content-hash addressed canned responses

**Location**: `tests/mocks/llm_mock.py`

```python
class MockLLMProvider:
    """Drop-in replacement for OpenRouterClient in tests.

    Behavior:
    - Accept request as if real provider
    - Compute SHA-256 of input prompt (or image/audio bytes)
    - Look up canned response from `tests/fixtures/llm/_hash_index.json`
    - Fall through to deterministic generated response if hash unknown
    - Track all calls for assertion
    """

    def __init__(self, fixture_dir: Path = None):
        self._fixtures = self._load_fixtures(fixture_dir or DEFAULT_FIXTURE_DIR)
        self._calls: list[dict] = []
        self._inject_failures: dict = {}  # for error injection

    async def chat(self, model: str, messages: list, **kw) -> dict:
        # Compute hash from messages
        prompt_hash = sha256(json.dumps(messages).encode()).hexdigest()

        self._calls.append({"model": model, "messages": messages, "hash": prompt_hash})

        # Failure injection
        if model in self._inject_failures:
            raise self._inject_failures[model]

        # Canned response or deterministic fallback
        canned = self._fixtures.get(prompt_hash)
        if canned:
            return canned
        return self._deterministic_response(messages)

    def inject_failure(self, model: str, exc: Exception):
        """For testing rate-limit / quota / timeout paths."""
        self._inject_failures[model] = exc

    @property
    def calls(self): return self._calls
```

**Fixture format** (`tests/fixtures/llm/_hash_index.json`):
```json
{
  "abc123...": {
    "scenario": "happy summary of homework1.docx",
    "response": {
      "id": "fake-resp-1",
      "model": "google/gemini-2.5-flash-lite",
      "choices": [{"message": {"content": "## 摘要\n王小明這次..."}, "finish_reason": "stop"}],
      "usage": {"prompt_tokens": 1500, "completion_tokens": 400}
    }
  }
}
```

**Anti-pattern guard** (per lessons-learned/testing.md "Mock LLM Must Produce Valid Structured Output"): the fixture loader **validates** every canned response against expected schema before any test runs. If a fixture is malformed, tests fail fast at session-setup, not deep in business logic.

```python
# tests/conftest.py
def pytest_sessionstart(session):
    """Validate LLM fixture index before any test runs."""
    fixtures = load_llm_fixtures()
    for hash_, entry in fixtures.items():
        try:
            ChatResponse.model_validate(entry["response"])  # Pydantic round-trip
        except ValidationError as e:
            raise RuntimeError(
                f"LLM fixture {hash_} ({entry['scenario']}) is malformed: {e}"
            )
```

### 3.2 Drive mock — recorded fixture replay

**Location**: `tests/mocks/drive_mock.py`

```python
class MockDriveClient:
    """Replays recorded Drive API responses from JSON fixtures.

    Test setup:
    1. Pre-record real Drive API response (one-off, manual) for a known
       fixture folder structure
    2. Save as `tests/fixtures/drive/<scenario>.json`
    3. Mock returns these on matching list/get calls

    Doesn't mock OAuth — see oauth_mock.py for that.
    """

    def __init__(self, scenario: str = "canonical_class"):
        self._fixture = load_json(f"tests/fixtures/drive/{scenario}.json")

    async def list_children(self, folder_id: str) -> list[dict]:
        return self._fixture["folders"].get(folder_id, [])

    async def download(self, file_id: str) -> bytes:
        # Returns real file bytes from tests/fixtures/files/
        return (FIXTURES / "files" / self._fixture["files"][file_id]["path"]).read_bytes()
```

**Why fixture-based not full mock**: real Drive API responses have nuances (paging tokens, modified-time format, mime-type values) that are hard to invent by hand. Recording once gets us a fidelity floor.

### 3.3 OAuth mock — per-test-context Google session

**Pattern from lessons-learned/testing.md "Lazy-Import SDKs Break Standard mock.patch Patterns"**:

```python
def make_test_auth_service(teacher_id="test-teacher-1"):
    """Bypass __init__ to avoid lazy import of google-auth-oauthlib."""
    svc = AuthService.__new__(AuthService)
    svc._settings = test_settings()
    svc._encryption = MockEncryptionService()
    svc._db_write_queue = MockDBWriteQueue()
    svc._oauth_client = MagicMock()  # all methods AsyncMock
    return svc
```

### 3.4 Async time mock

Per lessons-learned/testing.md "Mock asyncio.sleep in Tests That Exercise Retry-With-Delay Paths":

```python
@pytest.fixture
def fake_sleep(monkeypatch):
    """Replace asyncio.sleep with no-op in retry tests."""
    monkeypatch.setattr(
        "app.services.batch_worker.asyncio.sleep",
        AsyncMock(return_value=None)
    )
```

### 3.5 Mock validation principle

**Before any E2E test runs**, the mock layer must be validated:

```python
# tests/test_mocks_layer.py
@pytest.mark.asyncio
async def test_mock_llm_produces_valid_responses_for_all_fixtures():
    """Every canned LLM response round-trips through the real Pydantic schema."""
    mock = MockLLMProvider()
    for hash_, entry in mock._fixtures.items():
        response = await mock.chat("google/gemini-2.5-flash-lite", entry.get("messages", []))
        # Should not raise
        ChatResponse.model_validate(response)

@pytest.mark.asyncio
async def test_mock_drive_responses_match_real_schema():
    """Drive fixtures parse correctly under DriveAPIResponse schema."""
    mock = MockDriveClient()
    files = await mock.list_children("test-root")
    for f in files:
        DriveFileItem.model_validate(f)
```

This implements the lesson "Audit the full request chain before E2E tests" — failures here surface in <5 seconds, not in 10-minute Playwright runs.

---

## 4. Backend Test Plan

### 4.1 Test directory layout

```
backend/tests/
├── conftest.py                      # session-wide fixtures
├── mocks/
│   ├── llm_mock.py
│   ├── drive_mock.py
│   ├── oauth_mock.py
│   └── encryption_mock.py
├── fixtures/
│   ├── llm/
│   │   └── _hash_index.json
│   ├── drive/
│   │   ├── canonical_class.json
│   │   ├── nonstandard_naming.json
│   │   └── empty_class.json
│   ├── files/                       # real file bytes
│   │   ├── homework1.docx
│   │   ├── homework_encrypted.docx
│   │   ├── lab_report.png
│   │   ├── 2speaker_3min.m4a
│   │   └── _hash_index.json
│   └── pii_test_corpus.json         # 100 PII examples
├── unit/
│   ├── test_pii_anonymizer.py
│   ├── test_llm_service.py
│   ├── test_extractors_docx.py
│   ├── test_extractors_pdf.py
│   ├── test_state_machine.py
│   └── ...
├── integration/
│   ├── test_batch_flow.py           # full batch happy path
│   ├── test_recovery.py             # service-restart recovery
│   ├── test_pii_round_trip.py
│   ├── test_evaluation_generation.py
│   └── ...
└── bdd/                             # pytest-bdd, optional
    ├── features/
    │   ├── F-1-oauth.feature
    │   └── ...
    └── steps/
        └── ...
```

### 4.2 Critical unit tests (DESIGN-001 service contracts)

| Service | Required test coverage |
|---------|------------------------|
| PIIAnonymizer | Regex matches all 6 PII types; round-trip fidelity (anonymize→restore = original); handles overlapping matches; encryption integration; manual-mapping precedence |
| LLMService | Tier→model resolution; PII boundary check rejects pre-anonymized text; retry classification (rate-limit vs quota); audit log written for success and failure |
| BatchWorker | State transitions correct for each error class; concurrency limit enforced (semaphore); recovery resets stale rows |
| ProcessingPipeline | Routes by category × mime correctly; raises UnsupportedFormatError for unhandled extensions; PII anonymizer called before LLM |
| EvaluationGenerator | Style options produce different prompts; seed validation (30-100 chars); regenerate updates same row |
| DBWriteQueue | Single-writer ordering preserved; transaction rollback on exception; backpressure metrics accurate |
| EncryptionService | Encrypt + decrypt round-trips; tampered ciphertext rejected (AES-GCM); per-record nonce uniqueness |

### 4.3 Critical integration tests

| Test name | What it covers |
|-----------|----------------|
| `test_full_batch_flow` | Scan canonical fixture → process all 9 files → verify all states + cost |
| `test_recovery_after_kill` | Kill mid-batch → restart → verify no duplicate processing, all eventually complete |
| `test_pii_leakage_alert` | Inject anonymizer bug → boundary check fires → system_event logged → no LLM call |
| `test_reprocess_pending_overwrite` | Edit artifact → modify Drive file hash → batch shows reprocess_pending → user clicks overwrite → state goes processed |
| `test_reprocess_pending_keep` | Same as above but user clicks keep → state goes back to teacher_edited |
| `test_oauth_revocation_mid_batch` | Mock 403 from Drive → batch pauses → system_event 'oauth_revoked' |
| `test_quota_exhaustion_pauses_batch` | Inject RESOURCE_EXHAUSTED → batch transitions to paused (not failed) |
| `test_attestation_invalidation_blocks_drive_access` | Bump attestation version → existing teacher hits 412 |

### 4.4 Property-based tests (V1 if time, else V2)

`hypothesis` strategies for:
- PII detection: random string sequences containing names → `anonymize→restore` is identity
- State machine: sequence of valid transitions never reaches invalid state
- DBWriteQueue: arbitrary write closures preserve commit order

---

## 5. Frontend Test Plan

### 5.1 Layout

```
frontend/tests/
├── unit/
│   ├── components/
│   │   ├── Button.test.tsx
│   │   ├── Badge.test.tsx
│   │   ├── Editor.test.tsx
│   │   └── ...
│   ├── hooks/
│   │   ├── useFiles.test.ts
│   │   └── useBatch.test.ts
│   └── lib/
│       └── api/...
└── e2e/                             # Playwright
    └── (see §6)
```

### 5.2 Component tests

For each component in `frontend/src/components/`:
- Renders with default props
- Accessibility: passes axe-core check
- Interaction: click → callback fires
- States: loading / empty / error variants
- Theme: works in both light + dark mode

```typescript
// Button.test.tsx (illustrative)
import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";

test("Button is accessible", async () => {
  const { container } = render(<Button>Click me</Button>);
  expect(await axe(container)).toHaveNoViolations();
});
```

### 5.3 Hook tests

```typescript
// useBatch.test.ts (illustrative)
test("useBatch handles SSE reconnect", async () => {
  const { result } = renderHook(() => useBatch("batch-id-1"));

  // Simulate SSE disconnect
  mockEventSource.dispatchEvent(new Event("error"));

  // Should attempt reconnect
  await waitFor(() => expect(result.current.connectionState).toBe("reconnecting"));

  // After max retries, fall through to polling
  for (let i = 0; i < 5; i++) {
    mockEventSource.dispatchEvent(new Event("error"));
  }
  await waitFor(() => expect(result.current.mode).toBe("polling"));
});
```

### 5.4 Provider-agnostic state naming check

Per lessons-learned/frontend.md:

```typescript
// tests/test_no_provider_specific_state.test.ts
test("no provider-specific state names in frontend code", () => {
  const forbidden = [/gemini\w*State/i, /openrouter\w*State/i, /openai\w*State/i];
  for (const file of glob.sync("frontend/src/**/*.{ts,tsx}")) {
    const content = fs.readFileSync(file, "utf-8");
    for (const pattern of forbidden) {
      expect(content).not.toMatch(pattern);
    }
  }
});
```

---

## 6. Playwright E2E

### 6.1 Layout

```
frontend/tests/e2e/
├── playwright.config.ts
├── fixtures/
│   ├── auth.fixture.ts            # signed-in teacher fixture
│   ├── seeded-db.fixture.ts       # fresh DB with canonical scan
│   └── mock-services.fixture.ts   # spawn mock backend services
├── helpers/
│   ├── pages/                     # Page Object Model
│   │   ├── DashboardPage.ts
│   │   ├── BatchConsolePage.ts
│   │   ├── EvaluationPage.ts
│   │   └── ...
│   └── selectors.ts               # data-testid map
├── happy-paths/
│   ├── F-1-onboarding.spec.ts
│   ├── F-3-mapping-wizard.spec.ts
│   ├── F-7-batch-completion.spec.ts
│   ├── F-9-evaluation-generation.spec.ts
│   └── ...
├── edge-cases/
│   ├── batch-crash-recovery.spec.ts
│   ├── pii-conflict-resolution.spec.ts
│   ├── attestation-resign.spec.ts
│   └── ...
└── a11y/
    └── all-pages-axe.spec.ts
```

### 6.2 Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 4 : undefined,
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
    locale: "zh-TW",
    timezoneId: "Asia/Taipei",
  },
  projects: [
    { name: "chromium", use: devices["Desktop Chrome"] },
    { name: "firefox", use: devices["Desktop Firefox"] },
    { name: "mobile-readonly", use: devices["iPhone 13"] },
  ],
  webServer: {
    command: "./scripts/start-test-stack.sh",
    port: 3000,
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
});
```

### 6.3 Page Object Model example

```typescript
// helpers/pages/EvaluationPage.ts
export class EvaluationPage {
  constructor(public page: Page) {}

  async goto(semester: string, pseudoId: string) {
    await this.page.goto(`/evaluation/${semester}/${pseudoId}`);
  }

  async fillSeed(text: string) {
    await this.page.fill('[data-testid="eval-seed-input"]', text);
  }

  async pickStyle(style: "formal" | "encouraging" | "objective") {
    await this.page.click(`[data-testid="style-${style}"]`);
  }

  async clickGenerate() {
    await this.page.click('[data-testid="generate-button"]');
  }

  async waitForResult(timeoutMs = 30_000) {
    await this.page.waitForSelector('[data-testid="generated-eval-text"]', {
      timeout: timeoutMs,
    });
  }

  async getResult() {
    return this.page.textContent('[data-testid="generated-eval-text"]');
  }
}
```

### 6.4 Test fixture setup

Per lessons-learned/testing.md "Audit the full request chain before E2E":

```typescript
// fixtures/seeded-db.fixture.ts
import { test as base } from "@playwright/test";
import { execSync } from "child_process";

export const test = base.extend<{ seededDb: void }>({
  seededDb: [async ({}, use) => {
    // 1. Reset DB to fresh state
    execSync("./scripts/reset-test-db.sh");

    // 2. Seed canonical fixture (teacher signed in, scan complete)
    execSync("./scripts/seed-canonical.sh");

    // 3. Verify seed worked
    const r = await fetch("http://localhost:8000/test/__seed_check");
    if (r.status !== 200) throw new Error("Seed failed");

    await use();

    // No teardown — next test resets again
  }, { auto: true }],
});
```

### 6.5 Example E2E spec — F-9 evaluation generation happy path

```typescript
// happy-paths/F-9-evaluation-generation.spec.ts
import { test, expect } from "../fixtures/seeded-db.fixture";
import { EvaluationPage } from "../helpers/pages/EvaluationPage";

test("teacher generates evaluation in encouraging style", async ({ page }) => {
  const evalPage = new EvaluationPage(page);
  await evalPage.goto("113-1", "S001");

  await evalPage.fillSeed("認真負責，能將複雜問題拆解並提出解決方案，與同學互動良好");
  await evalPage.pickStyle("encouraging");
  await evalPage.clickGenerate();

  await evalPage.waitForResult();

  const result = await evalPage.getResult();
  expect(result).toContain("王小明");  // PII restored
  expect(result.length).toBeGreaterThanOrEqual(280);  // soft 300-500 range
  expect(result.length).toBeLessThanOrEqual(550);

  // Verify cost recorded
  await expect(page.locator('[data-testid="eval-cost"]')).toContainText("$0.00");
});
```

### 6.6 a11y E2E

```typescript
// a11y/all-pages-axe.spec.ts
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const PAGES = [
  "/login",
  "/onboarding/attestation",
  "/dashboard",
  "/semester/113-1",
  "/student/S001",
  "/file/test-file-id",
  "/evaluation/113-1/S001",
  "/settings/llm",
  "/settings/pii",
];

for (const path of PAGES) {
  test(`a11y: ${path}`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  });
}
```

### 6.7 Mobile read-only E2E

```typescript
test.describe("mobile read-only", () => {
  test.use({ ...devices["iPhone 13"] });

  test("evaluation page shows read-only banner", async ({ page }) => {
    await page.goto("/evaluation/113-1/S001");
    await expect(page.locator('[data-testid="readonly-banner"]'))
      .toContainText("在電腦上編輯");
    await expect(page.locator('[data-testid="generate-button"]'))
      .toBeDisabled();
  });
});
```

### 6.8 E2E flakiness mitigation

Per lessons-learned/testing.md and observed best practices:

| Flakiness source | Mitigation |
|------------------|-----------|
| Network latency | All external calls mocked at backend; only local network in test stack |
| Animation timing | `page.evaluate` to disable transitions for test runs (CSS class added in test mode) |
| State machine timing | Time fixture frozen via mock clock |
| Parallel test interference | Fresh DB per test (seeded-db fixture) — no shared state |
| LLM response variability | Mock returns deterministic responses |
| Test isolation | `--workers=4` with separate DB files per worker |

---

## 7. Test Data Management (manifest-driven)

> Per lessons-learned/engineering-process.md "E2E Test Planning: Manifest-Driven Ground Truth Over Hardcoded Assertions" and lessons-learned/testing.md "Content-Hash Fixture Lookup".

### 7.1 Manifest structure

```
tests/fixtures/
├── manifest.json          ← single source of truth
├── images/
│   ├── lab_report.png
│   ├── chart_handdrawn.jpg
│   └── encrypted_doc.pdf
├── audio/
│   ├── 2speaker_3min.m4a
│   └── 1speaker_5min.m4a
├── docs/
│   ├── homework1.docx
│   └── homework_encrypted.docx
└── llm/
    └── _hash_index.json   ← keyed by SHA-256 of input prompt
```

```json
// manifest.json
{
  "version": "1.0",
  "files": [
    {
      "id": "lab_report",
      "path": "images/lab_report.png",
      "mime": "image/png",
      "category": "learning",
      "expected_extraction_keywords": ["實驗", "結論"],
      "expected_pii_replacements": ["王小明"],
      "llm_canned_response_hash": "abc123..."
    },
    {
      "id": "homework_encrypted",
      "path": "docs/homework_encrypted.docx",
      "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "category": "learning",
      "expected_terminal_failure": "encrypted_ole_signature",
      "expected_state": "unprocessable"
    },
    {
      "id": "talk_2speaker",
      "path": "audio/2speaker_3min.m4a",
      "mime": "audio/mp4",
      "category": "interaction",
      "expected_speakers": 2,
      "expected_format": "dialog",
      "llm_canned_response_hash": "def456..."
    }
  ]
}
```

**Why manifest-driven**:
- Adding a new test image: drop file in directory, add manifest entry, add LLM hash → no test code changes
- Removing test data: remove from manifest → all tests skip gracefully
- Reusable across unit / integration / E2E layers

### 7.2 PII test corpus

```json
// fixtures/pii_test_corpus.json
{
  "version": "1.0",
  "samples": [
    {
      "id": "p001",
      "input": "今天王小明做了實驗，他的電話是 0912-345-678",
      "expected_replacements": [
        { "type": "student_name", "original": "王小明", "anonymized_pattern": "S\\d{3}" },
        { "type": "phone", "original": "0912-345-678", "anonymized_pattern": "PH\\d{3}" }
      ]
    },
    ... 99 more
  ]
}
```

PII tests parametrize over this — `pytest.mark.parametrize` from manifest.

---

## 8. CI Integration

### 8.1 GitHub Actions workflows

> **Status note**: This section was authored as an early sketch (v0.1 had only 4 jobs). The actual implementation (commit `efb7c98`, 2026-05-10) is more comprehensive — full implementation lives in [`.github/workflows/`](../.github/workflows/) and is the canonical source. Below describes what's there.

Three workflows split by purpose:

#### 8.1.1 `test.yml` — code testing (7 jobs)

Triggers: PR + push to main. Each job has `if: hashFiles(...)` guard so jobs auto-skip when target directory is absent (activates as `backend/` and `frontend/` are created during V1 implementation).

| Job | Triggers when | Runs |
|-----|---------------|------|
| `backend-unit` | `backend/pyproject.toml` exists | `pytest tests/unit` with coverage; uploads to Codecov |
| `backend-integration` | same | `pytest tests/integration --maxfail=3`; depends on `backend-unit` |
| `backend-quality` | same | `ruff check`, `mypy --strict`, **DESIGN-001 §5.3 hardcoded-model-ID grep check** |
| `frontend-unit` | `frontend/package.json` exists | `pnpm test --run --coverage` |
| `frontend-quality` | same | `tsc --noEmit`, `eslint`, **TDD-001 §5.4 provider-specific-state-name grep check** |
| `e2e` | both backend + frontend present | Playwright on chromium + firefox + iPhone 13; depends on `backend-unit` + `frontend-unit`; uploads report + trace on failure |
| `ci-summary` | always | Aggregates all jobs; the single check to mark "required" in branch protection |

Concurrency: in-progress runs are cancelled when a new push lands on the same branch (saves CI minutes).

#### 8.1.2 `doc-consistency.yml` — cross-doc consistency

Triggers: PR + push touching `.md` files. Runs [`scripts/check_docs.py`](../scripts/check_docs.py) which performs 6 checks (C1-C6 — see comment block in the script). Catches the "ripple-effect drift" class of bugs (e.g., F-N count vs AC-N count, D-NN refs not defined, state machine drift).

#### 8.1.3 `link-check.yml` — markdown link integrity

Triggers: PR (offline mode, fast) + weekly cron (full check including external URLs). Tool: lychee. Already in place since the governance kit was installed (commit `2e0d2b6`).

#### 8.1.4 Quality gates summary (per §8.3 detail below)

The custom grep checks in `backend-quality` and `frontend-quality` enforce two architectural invariants that no off-the-shelf linter can detect:

- **No hardcoded model IDs** in `backend/app/services/*` or `backend/app/adapters/openrouter_client.py` — must read `settings.llm_tier_*` per DESIGN-001 §5.3 (config plumbing pattern from `lessons-learned/architecture.md`)
- **No provider-specific state names** in `frontend/src/**/*.{ts,tsx}` — must use `llmQuotaPaused` not `geminiQuotaPaused` per `lessons-learned/frontend.md`

### 8.2 Pre-commit hooks

> **Status note**: This section was authored as a sketch (2 hooks); the actual [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) (commit `efb7c98`) has 14 hooks. Below describes the implemented shape.

Install once: `pre-commit install`. The hooks mirror CI checks for fast local feedback.

| Category | Hooks | Auto-skip behavior |
|----------|-------|---------------------|
| **Generic hygiene** | trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, check-json, check-merge-conflict, check-added-large-files (1MB cap) | Always run |
| **Doc consistency** | `check-docs` (runs `scripts/check_docs.py`) | Always run on `.md` change |
| **Backend** | `backend-ruff`, `backend-mypy`, `backend-pytest-fast` | Skip if `backend/pyproject.toml` absent |
| **Frontend** | `frontend-tsc`, `frontend-eslint`, `frontend-vitest-fast` | Skip if `frontend/package.json` absent |

The skip-if-absent guards mirror the workflow guards (§8.1.1) — same activation pattern across CI and local pre-commit.

### 8.3 Quality gates (enforce)

CI fails on:
- Any test failure (no skips without explicit `pytest.mark.skip` reason)
- Coverage drops below threshold (§9)
- a11y violations (axe-core in E2E)
- TypeScript errors in frontend
- mypy errors in backend (`--strict`)
- Hardcoded model IDs in services (DESIGN-001 §5.3)
- Provider-specific state names in frontend (TDD-001 §5.4)

---

## 9. Coverage Targets

| Layer | Target | Measurement | Enforcement |
|-------|--------|-------------|-------------|
| Backend (overall) | ≥ 85% line coverage | `pytest-cov` | CI fails if below |
| Backend critical services | ≥ 95% line coverage | per-file coverage report | CI fails if below |
| Backend critical services list | PIIAnonymizer, LLMService, BatchWorker, EvaluationGenerator, EncryptionService | — | — |
| Frontend (overall) | ≥ 75% line coverage | `vitest --coverage` | Soft (warning, not fail) V1 |
| Frontend critical components | ≥ 90% line coverage | per-component | CI fails if below |
| Frontend critical components list | Editor, BatchProgress, ConflictPrompt, AttestationDialog, MappingWizard | — | — |
| E2E happy paths | 100% (10 BDD happy paths covered) | Manual checklist | CI fails if any spec missing |
| a11y violations | 0 critical/serious | axe-core | CI fails if any |

**Coverage anti-patterns to avoid**:
- Targeting 100% — last 5% becomes test-for-the-sake-of-test
- Counting LoC, not branches — `if/else` paths matter more
- Letting coverage drop "temporarily" — always enforce, fix, then merge

### 9.1 Target ramp

Coverage targets above apply at **V1 freeze** (not day-one). During active V1 development:

| Sprint | Backend overall | Frontend overall | E2E |
|--------|----------------|-------------------|-----|
| Sprint 1 (foundation) | ≥ 60% | ≥ 50% | 3 happy paths |
| Sprint 2 (services) | ≥ 75% | ≥ 65% | 6 happy paths |
| Sprint 3 (UI integration) | ≥ 85% | ≥ 75% | 10 happy paths |
| V1 freeze | ≥ 85% (95% critical) | ≥ 75% (90% critical) | 100% happy + edge |

---

## 10. Test Hygiene Rules

### 10.1 Naming conventions

```python
# Bad
def test_eval():
    ...

# Good
def test_evaluation_generator_uses_evaluation_quality_tier_for_llm_call():
    ...
```

Test names should make the assertion clear without reading the body.

### 10.2 One assertion per test (mostly)

Multiple assertions OK if testing the **same behavior** (e.g., return shape includes 3 fields). Multiple assertions across different behaviors → multiple tests.

### 10.3 No conditional logic in tests

No `if/else` in test bodies. If a test needs to differ based on input, use `parametrize`.

### 10.4 Don't test framework code

Don't write tests asserting that FastAPI returns 200 for valid requests, or that React renders a `<button>` tag. Test **your code's specific behavior**.

### 10.5 Tests as documentation

Reading `test_pii_anonymizer.py` should teach a newcomer:
- What inputs trigger which behaviors
- What edge cases exist
- What invariants are maintained

If tests are hard to read, refactor them — they have an audience beyond CI.

---

## 11. Implementation TODOs

Tracked here; resolved during V1 build:

| TODO | Description |
|------|-------------|
| **TT-1** | Validate `MockLLMProvider` against actual OpenRouter response schema (Pydantic round-trip) — see lessons-learned/testing.md |
| **TT-2** | Build `pii_test_corpus.json` with 100 examples covering all 6 PII types + edge cases |
| **TT-3** | Decide pytest-bdd vs pure pytest for BDD execution — lean toward pure pytest with descriptive names per BDD-001 §5.3 |
| **TT-4** | Set up Playwright trace artifact upload to GitHub Actions for failure debugging |
| **TT-5** | Investigate test parallelism: SQLite-per-worker pattern needs database file isolation; verify aiosqlite handles concurrent dbs |
| **TT-6** | Decide: should E2E test run against real OpenRouter periodically (`@external` tagged, manual trigger) for sanity check? V1 likely no, but document the decision |

---

## 12. References

- [`docs/PRD.md`](PRD.md) §11 (Acceptance Criteria)
- [`docs/BDD-001-behavior-scenarios.md`](BDD-001-behavior-scenarios.md) — scenarios this strategy implements
- [`docs/DESIGN-001-detailed-design.md`](DESIGN-001-detailed-design.md) §4 (services to test) §5.3 (config plumbing CI test)
- [`docs/UIUX-001-design-system.md`](UIUX-001-design-system.md) §8 (a11y target = WCAG 2.1 AA)
- `~/.claude/lessons-learned/testing.md` — load-bearing for §3 (mock strategy)
- `~/.claude/lessons-learned/engineering-process.md` — manifest-driven E2E (§7)
- `~/.claude/lessons-learned/frontend.md` — provider-agnostic state names (§5.4)
- Playwright: https://playwright.dev/
- pytest-bdd: https://pytest-bdd.readthedocs.io/
- axe-core: https://github.com/dequelabs/axe-core

---

> **End of TDD-001 v0.1**. All 5 design docs complete. Next: cross-doc audit + commit hash backfill.
