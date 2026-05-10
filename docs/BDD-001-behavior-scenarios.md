# BDD-001: Behavior Scenarios (Gherkin)

| Field | Value |
|-------|-------|
| **Status** | Draft v0.1 |
| **Date** | 2026-05-10 |
| **Owner** | Steven Chen |
| **Depends on** | [`PRD.md`](PRD.md) §5 (F-1 ~ F-10), [`UIUX-001-design-system.md`](UIUX-001-design-system.md), [`DESIGN-001-detailed-design.md`](DESIGN-001-detailed-design.md) |
| **Consumers** | TDD-001 (test fixtures derive from these scenarios), implementation work (acceptance check) |

---

## 0. Document Control

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 0.1 | 2026-05-10 | Steven (with Claude Code) | Initial — Gherkin scenarios for F-1~F-10, edge cases, fixtures |

**Reading order**:
- §1 Methodology → §2 Background fixtures (defines actors and shared state)
- §3 Per-feature scenarios (F-1 ~ F-10, one section each)
- §4 Cross-cutting scenarios (security, error recovery)
- §5 Implementation guidance (which BDD framework)
- §6 Coverage tracker

---

## 1. Methodology

### 1.1 Why BDD here

Per PRD §11 (Acceptance Criteria) the system has 10 ACs that map 1:1 to F-1~F-10. ACs answer "is the feature done?" but they're terse — they don't capture **the way users get there**, **what edge cases matter**, or **what the system says when things go wrong**.

BDD scenarios fill that gap with **executable, human-readable specifications** in Gherkin form (`Given / When / Then`). Each scenario:
- Names a concrete situation in the user's terms
- Provides assertable expected behavior
- Doubles as an automated test seed (TDD-001 §X explains the executable layer)

### 1.2 Gherkin conventions used

```gherkin
Feature: <name>
  As a <persona>
  I want <capability>
  So that <outcome>

  Background:
    Given <shared setup>

  Scenario: <imperative title>
    Given <precondition>
    When <action>
    Then <expectation>

  Scenario Outline: <parametrized title>
    Given <precondition with <param>>
    When ...
    Then ...
    Examples:
      | param | ... |
      | ...   | ... |
```

**Tags** signal scope:
- `@happy` — primary success path
- `@edge` — boundary or unusual input
- `@error` — failure handling
- `@slow` — long-running (audio processing, batch)
- `@external` — requires real Drive / OpenRouter (not pure mock)
- `@security` — PII or auth boundary

### 1.3 Granularity rule

One scenario per **observable user-facing outcome**, not per code path. If two code paths produce the same outcome, one scenario suffices. Per `lessons-learned/testing.md`: ground-truth lives in a manifest, not in scattered assertions.

---

## 2. Background Fixtures

> All scenarios share these fixtures unless overridden.

### 2.1 Personas

```gherkin
@background
Given a teacher named "張老師" (email "zhang@school.example.com")
  with Google account "zhang@school.example.com"
  and they are using a deployed instance at "https://comments.zhang.example"
```

### 2.2 Drive fixture (canonical "happy class" — small)

```
教學資料根目錄/
├── 113-1 上學期/
│   ├── 王小明/
│   │   ├── 學習紀錄/
│   │   │   ├── notes_20240915.txt
│   │   │   └── homework1.docx
│   │   ├── 教師與學生互動紀錄/
│   │   │   └── talk_20240920.m4a   (3 minutes, 2 speakers)
│   │   └── 作品成果/
│   │       └── final_essay.pdf
│   └── 李小華/
│       └── (similar shape — 3 files)
└── (no second semester)
```

**Total**: 2 students × 4 files + 1 audio = 9 files.

### 2.3 Drive fixture (non-standard naming — for D14 mapping wizard tests)

```
教學/
├── 上學期/
│   └── 王小明/
│       ├── 課堂筆記/         (= 學習紀錄)
│       ├── 晤談紀錄/         (= 教師與學生互動紀錄)
│       ├── 報告作品/         (= 作品成果)
│       └── 雜項/             (≠ any standard category)
```

### 2.4 Drive fixture (edge cases)

- Empty student folder (no files in any of the 3 categories)
- Encrypted docx (`exam_scan_encrypted.docx` with OLE encryption signature)
- Corrupt PDF (`malformed.pdf` — header looks valid but contents truncated)
- Unsupported format (`weird.psd` Photoshop file)
- Very long audio (90-minute recording — hits §6.1 perf budget cliff)

### 2.5 LLM mock contract

```gherkin
Given a mock OpenRouter that:
  - Accepts requests for model "google/gemini-2.5-flash-lite"
  - Returns the canned response keyed by SHA-256 of the input prompt
  - For unknown prompts: returns a deterministic 6-sentence Chinese summary
  - Tracks call count and accumulated cost
  - Can be configured to inject:
    - 429 rate limits (with Retry-After header)
    - 5xx errors
    - Timeouts
    - Daily quota exhaustion (RESOURCE_EXHAUSTED with no retry hint)
```

(Detailed mock implementation — TDD-001 §X.)

### 2.6 Time fixture

```gherkin
Given the system clock is fixed at 2026-05-10 09:00:00 +0800
```

(Frees scenarios from real-time dependencies; consistent state-machine timestamps.)

---

## 3. Per-Feature Scenarios

### F-1: Google OAuth + Onboarding Attestation

#### Feature

```gherkin
Feature: Google OAuth + onboarding attestation
  As a teacher new to the system
  I want to log in with my Google account and acknowledge consent
  So that the system can access my Drive with appropriate legal coverage
```

#### Scenarios

```gherkin
@happy
Scenario: First-time login with valid attestation
  Given the teacher has never logged in before
    And the attestation version is "v1"
  When the teacher clicks "使用 Google 登入"
    And completes Google OAuth with scope "drive.readonly"
    And reaches the attestation dialog
    And checks the agreement checkbox
    And clicks "我同意"
  Then a teacher row should be created in the database
    And teacher.consent_attestation_at should equal "2026-05-10 09:00:00"
    And teacher.consent_attestation_version should be "v1"
    And the system_event log should contain "oauth_login" and "attestation_signed"
    And the teacher should be redirected to /onboarding/drive-root

@error
Scenario: Teacher cancels attestation
  Given the teacher has just completed OAuth
  When the attestation dialog appears
    And the teacher clicks "取消"
  Then the OAuth session should be terminated (server-side cookie cleared)
    And the teacher row should be deleted
    And the teacher should be redirected to /login

@error @security
Scenario: Attestation version updated; previous user must re-sign
  Given the teacher previously signed attestation version "v1"
    And the deployed attestation version is now "v2"
  When the teacher logs in
  Then they should be redirected to /onboarding/attestation
    And the attestation dialog should display the v2 text
    And after signing, teacher.consent_attestation_version should equal "v2"
    And the system_event log should contain "attestation_invalidated" then "attestation_signed"

@security
Scenario: OAuth refresh token revoked externally
  Given the teacher has previously logged in
    And they revoked the OAuth grant via Google's account settings
  When the teacher next attempts to load /dashboard
  Then the system should detect the 403 from Drive API
    And the system_event log should contain "oauth_revoked"
    And the teacher should be redirected to /login with explanation
    And the encrypted refresh_token should be cleared from storage

@security
Scenario: Single-account violation
  Given a teacher row exists with email "alice@example.com"
  When a user with email "bob@example.com" completes OAuth
  Then the response should be HTTP 403
    And the UI should display "本系統實例已綁定 alice@example.com"
    And no second teacher row should be created
    And the OAuth session for "bob" should be terminated
```

### F-2: 教學資料根目錄選擇

```gherkin
Feature: Pick teaching root folder
  As a teacher new to the system
  I want to browse my Drive and select the folder containing teaching materials
  So that the system knows where to scan

@happy
Scenario: Pick a folder with sub-folders matching standard naming
  Given the teacher has just signed attestation
    And their Drive contains a folder "教學資料" at the root
  When they reach /onboarding/drive-root
  Then "教學資料" should be visually highlighted as a recommended pick
  When they click "教學資料"
    And click "下一步"
  Then teacher.drive_root_folder_id should equal the Drive ID of "教學資料"
    And the system should automatically initiate a scan

@happy
Scenario: Pick a folder by manual navigation
  Given the teacher's Drive has no auto-recommended folder
  When they expand "My Drive" -> "教學" -> "2024 學年度"
    And select "2024 學年度"
    And click "下一步"
  Then teacher.drive_root_folder_id should equal the Drive ID of "2024 學年度"

@edge
Scenario: Change root folder later
  Given the teacher has set drive_root_folder_id to folder X
    And has already indexed 100 files
  When they navigate to Settings > 資料夾對應 and click "重設並重新掃描"
    And confirm in the warning dialog
  Then all rows in drive_file should be soft-deleted (deleted_at set)
    And teacher.drive_root_folder_id should be cleared
    And the teacher should be redirected to /onboarding/drive-root
```

### F-3: Drive 結構掃描 + Mapping Wizard

```gherkin
Feature: Drive structure scan with mapping wizard
  As a teacher
  I want the system to recognize my folder structure even if I named folders non-standardly
  So that I don't have to rename my existing teaching files

@happy
Scenario: Standard folder names — no wizard needed
  Given the teacher has set drive_root_folder_id to a folder containing the canonical fixture (§2.2)
  When the scan runs
  Then the scan completes without invoking the mapping wizard
    And drive_file should contain 9 rows
    And no folder_mapping should be set on the teacher

@happy
Scenario: Non-standard folder names — wizard prompts for mapping
  Given the teacher has set drive_root_folder_id to the non-standard fixture (§2.3)
  When the scan begins traversing 王小明's folder
  Then the scan should suspend
    And an SSE event "needs_folder_mapping" should fire with the detected folder names
      ["課堂筆記", "晤談紀錄", "報告作品", "雜項"]

  When the teacher provides the mapping:
    | category    | actual_name |
    | learning    | 課堂筆記     |
    | interaction | 晤談紀錄     |
    | work        | 報告作品     |
    And clicks "儲存對應關係"
  Then teacher.folder_mapping should equal the chosen JSON
    And the scan should resume
    And only files in the 3 mapped folders should be indexed
    And files in "雜項" should NOT be indexed

@edge
Scenario: Mapping wizard cancelled mid-scan
  Given the scan has suspended awaiting mapping
  When the teacher closes the wizard without saving
  Then the scan should remain suspended
    And subsequent visit to /dashboard should re-prompt the wizard

@edge
Scenario: PII anonymization triggered by student folder names
  Given the standard fixture has students named "王小明" and "李小華"
  When the scan completes
  Then pii_mapping should contain rows for both names
    And drive_file rows should have student_pseudo_id like "S001" and "S002"
    And the original student names should NOT appear in any drive_file column
    And no LLM call has yet occurred

@edge
Scenario: Re-scan idempotency
  Given a previous scan has indexed 9 files
    And no Drive content has changed
  When the teacher manually triggers another scan
  Then the scan should report "0 files indexed, 9 files unchanged"
    And no drive_file rows should be modified
```

### F-4: 文件 → Markdown 摘要 pipeline

```gherkin
Feature: Document → Markdown summary
  As a teacher
  I want my students' learning records and work outputs to be summarized
  So that I can quickly review semester materials

  Background:
    Given the standard Drive fixture has been scanned
      And the LLM mock returns canned summaries

@happy
Scenario Outline: Process a single learning record file
  Given a drive_file with category=<category> and mime_type=<mime>
  When the BatchWorker processes this file
  Then a processed_artifact row should be created with state="processed"
    And artifact_type should be "markdown_summary"
    And content_markdown should match the schema (frontmatter + 摘要 + 重點 + 引用)
    And the LLM tier used should be <tier>
  Examples:
    | category  | mime                                                                  | tier            |
    | learning  | text/plain                                                            | summary_cheap   |
    | learning  | application/vnd.openxmlformats-officedocument.wordprocessingml.document | summary_cheap |
    | learning  | image/png                                                             | vision_cheap    |
    | work      | application/pdf                                                       | summary_cheap   |
    | work      | image/jpeg                                                            | vision_cheap    |

@happy
Scenario: Mermaid generation for content with diagram structure
  Given the LLM mock returns content containing a Mermaid block
  When the BatchWorker processes the file
  Then the resulting markdown should contain a "```mermaid" block
    And the block should be syntactically valid (parsable)

@edge
Scenario: PII names in source text get replaced before LLM call
  Given a docx file containing the text "今天王小明做了實驗"
  When the BatchWorker processes this file
  Then the LLM mock receives prompt content containing "S001" not "王小明"
    And the resulting content_markdown shown to the teacher contains "王小明" again (restored)
    And llm_call_audit should record pii_replacement_count >= 1

@error @edge
Scenario: Encrypted docx → unprocessable
  Given a drive_file pointing to a docx with OLE encryption signature
  When the BatchWorker attempts to process it
  Then DocumentExtractionError or UnsupportedFormatError should be raised
    And the artifact state should transition to "unprocessable"
    And failure_reason should explain "encrypted"
    And NO LLM call should have occurred for this file
    And retry_count should remain 0 (no auto-retry attempted)

@error
Scenario: Network error during LLM call → failed (retriable)
  Given the LLM mock is configured to return 500 on the first 2 attempts
    And succeed on the 3rd
  When the BatchWorker processes a file
  Then the artifact should transition through processing → failed → processing → processed
    And retry_count should equal 2
    And the file should be reflected as "已處理" in the UI

@error
Scenario: Persistent LLM rate limit (429)
  Given the LLM mock returns 429 on all attempts
  When the BatchWorker processes a file
  Then after 3 retries the state should be "failed"
    And retry_count should equal 3
    And the file should be reflected as "處理失敗" badge in the UI
    And an upper-level retry button should be available

@error @security
Scenario: PII boundary check fails (anonymizer bug)
  Given the PIIAnonymizer is buggy and fails to replace "王小明"
  When the BatchWorker tries to send the prompt to LLM
  Then PIILeakageError should be raised before any HTTP call to OpenRouter
    And the system_event log should contain "pii_leakage_detected"
    And the artifact should transition to "unprocessable"
    And NO data should reach OpenRouter
```

### F-5: 音訊 → 講者拆解逐字稿

```gherkin
Feature: Audio → speaker-diarized transcript
  As a teacher
  I want my recorded teacher-student conversations transcribed with speaker labels
  So that I can search and reference key exchanges

  Background:
    Given the standard Drive fixture has 1 audio file (talk_20240920.m4a, 3 min, 2 speakers)
      And the audio LLM mock returns a transcript with 2 speakers detected

@happy
Scenario: 2-speaker audio produces dialog format transcript
  When the BatchWorker processes the audio file
  Then a processed_artifact with artifact_type="transcript" should exist
    And content_markdown should be in dialog format
    And content_markdown should contain "Speaker_1" AND "Speaker_2" labels
    And content_markdown should contain timestamps like "[00:00:12]"
    And the audio file should NOT be persisted in any local cache after processing

@happy @slow
Scenario: 1-speaker audio produces monologue format
  Given a teacher's solo notes recording (5 min, 1 speaker)
  When the BatchWorker processes the file
  Then content_markdown should be in monologue format (no Speaker labels)
    And it should contain timestamps and verbatim text

@edge
Scenario: Teacher renames Speaker labels
  Given a transcript exists with Speaker_1 and Speaker_2
  When the teacher edits the artifact and renames labels to "王小明" and "老師"
    And clicks save
  Then content_markdown should contain "王小明" and "老師" (not Speaker_1/Speaker_2)
    And state should transition to "teacher_edited"

@edge @security
Scenario: PII in transcript is anonymized after STT, restored for display
  Given the audio mock transcript contains "王小明說他不會"
  When the BatchWorker processes the audio
  Then the persisted content_markdown shown to teacher contains "王小明"
    And any subsequent LLM call (e.g., regenerate summary) sends "S001"
    And the audit trail records the PII replacement count

@error @slow
Scenario: Audio processing timeout (>30 min)
  Given a 90-minute recording
    And the audio LLM mock takes 35 minutes
  When the BatchWorker processes it
  Then ProcessingError should be raised
    And the state should transition to "failed"
    And user-message should say "請手動切片重試"

@error
Scenario: Audio file unreadable (corrupt header)
  Given a drive_file pointing to a .m4a with a corrupt header
  When the BatchWorker processes it
  Then DocumentExtractionError should be raised
    And state should transition to "unprocessable"
    And the audio file should be deleted from local cache
```

### F-6: PII Anonymizer + Min UI

```gherkin
Feature: PII anonymization with minimal teacher UI
  As a teacher
  I want to see what the system has anonymized
  So that I trust the privacy mechanism

@happy
Scenario: View current PII mappings
  Given the teacher has had a scan that anonymized "王小明" → S001 and "李小華" → S002
  When they navigate to /settings/pii
  Then the table should display rows with original_value (decrypted) and pseudonym
    And the source column should show "auto" for both

@happy
Scenario: Rename pseudonym display name
  Given a row with pseudonym "S001" and display_name=null
  When the teacher clicks "改顯示名" and enters "小明"
    And clicks save
  Then pii_mapping.display_name should be "小明"
    And the next time content is restored, S001 should resolve to "小明" not "王小明"

@happy
Scenario: Add manual mapping for a nickname
  Given the teacher knows "阿明" is also "王小明" (S001)
  When they click "+ 新增手動映射"
    And enter original_value="阿明", pseudonym="S001"
    And clicks save
  Then a new pii_mapping row should exist with source="manual"
    And subsequent anonymize() should replace "阿明" with "S001" too

@edge
Scenario: Manual mapping for non-existent pseudonym should fail
  When the teacher tries to add manual mapping with pseudonym="S999"
    But no S999 exists for this teacher
  Then a 400 response should explain "pseudonym does not exist"

@security
Scenario: Original PII value is encrypted at rest
  Given the encryption key is rotated
  When pii_mapping.original_value_encrypted is read raw from SQLite
  Then it should NOT be the plaintext "王小明"
    And it should be a binary blob >= 28 bytes (12-byte nonce + ciphertext + 16-byte tag)
```

### F-7: Batch Processing — start, track, recover

```gherkin
Feature: Batch processing with persistent state and recovery
  As a teacher
  I want to process all my files in one batch and trust resume after interrupt

  Background:
    Given the canonical fixture is scanned (9 files)

@happy
Scenario: Start batch and complete normally
  When the teacher clicks "處理本學期"
    And confirms the file list
  Then a batch_job row should be created with status="running" and total_files=9
    And after all files process, status should be "completed"
    And total_cost_usd should equal the sum of llm_call_audit.cost_usd for the batch

@edge
Scenario: Concurrent worker pool processes multiple files in parallel
  Given BATCH_WORKER_CONCURRENCY=4
  When the batch starts
  Then at any moment, up to 4 artifacts should be in state="processing"

@error
Scenario: Service crashes mid-batch; recovery on restart
  Given a batch is processing 5 files
    And 3 files have completed (state="processed")
    And 2 files are state="processing" with updated_at < 5 min ago
  When the service is killed and restarted
  Then on startup, recover_stale_jobs() should be called
    And artifacts older than 5 min in "processing" should reset to "pending"
    And the BatchWorker should pick them up
    And NO file should be processed twice (no duplicate llm_call_audit rows)

@error
Scenario: Reprocess pending — teacher chooses to keep edits
  Given an artifact is in state="teacher_edited" with content_markdown="my edits"
    And the original Drive file's content_hash has changed
  When the next batch runs
  Then the artifact should transition to "reprocess_pending"
    And the UI should show the conflict prompt for this file
  When the teacher clicks "保留我的編輯"
  Then the artifact should transition back to "teacher_edited"
    And source_content_hash should be updated to match the new Drive file

@error
Scenario: Reprocess pending — teacher chooses to overwrite
  Given the same setup as above
  When the teacher clicks "覆蓋我的編輯"
  Then the artifact should transition to "processing"
    And after LLM call, content_markdown should be overwritten with the new generation
    And state should be "processed"
    And the prior teacher_edited content should be lost (not undoable in V1)

@edge
Scenario: Bulk overwrite all reprocess_pending
  Given 5 files are in reprocess_pending state
  When the teacher clicks "全部覆蓋"
  Then all 5 should transition to "processing"
    And all 5 should be reprocessed

@error
Scenario: Daily quota exhausted mid-batch
  Given a batch is processing
    And the LLM mock returns RESOURCE_EXHAUSTED with no retry hint
  When the batch encounters this
  Then the batch_job status should transition to "paused"
    And the UI should display "LLM 每日配額已用罄"
    And the teacher should be able to manually resume the next day
```

### F-8: 教師編輯保護與覆蓋確認

```gherkin
Feature: Teacher edit protection
  As a teacher
  I want my manual edits to processed artifacts to never be silently overwritten

@happy
Scenario: Editing changes state from processed to teacher_edited
  Given an artifact in state="processed" with content_markdown="LLM output"
  When the teacher opens File Detail, modifies the markdown, and saves
  Then state should transition to "teacher_edited"
    And teacher_edited_at should equal current timestamp
    And content_markdown should reflect the teacher's changes

@happy
Scenario: Auto-save during editing
  Given the teacher is editing an artifact for 90 seconds
  When 30 seconds elapse with no manual save
  Then the system should auto-save at least once (UI shows "已儲存" indicator)

@edge
Scenario: Detect Drive file change after teacher edit
  Given an artifact in state="teacher_edited"
    And the original Drive file is later modified externally (new content_hash)
  When the next scan or batch runs
  Then the artifact should transition to "reprocess_pending"
    And the conflict UI should be shown

@edge
Scenario: UI shows "已修改" badge persistently
  Given an artifact is in state="teacher_edited"
  When the teacher views the file in any list
  Then the badge should display "✏️ 已修改" with purple color
    And clicking it should reveal the edit timestamp
```

### F-9: 學期評語生成

```gherkin
Feature: Semester evaluation generation
  As a teacher
  I want to write a brief observation and have the system produce a 300-500 character draft
  So that I can refine instead of write from scratch

  Background:
    Given a student "S001 (王小明)" with all 3 categories of artifacts processed
      And the LLM mock returns canned evaluations keyed by style

@happy
Scenario Outline: Generate evaluation in each style
  When the teacher inputs seed "認真負責，能將複雜問題拆解" (32 chars)
    And selects style <style>
    And clicks 生成評語
  Then a semester_evaluation row should be created
    And generated_text should be a Traditional Chinese paragraph
    And char_count should be reported (no validation per OQ-10)
    And cost_usd should be recorded
    And the LLM tier used should be evaluation_quality
  Examples:
    | style       |
    | formal      |
    | encouraging |
    | objective   |

@happy
Scenario: Editing the generated evaluation persists separately
  Given a semester_evaluation has generated_text="LLM original draft"
  When the teacher edits to "Teacher refined version"
    And saves
  Then semester_evaluation.edited_text should equal "Teacher refined version"
    And generated_text should remain "LLM original draft"
    And edited_at should be set

@happy
Scenario: Regenerate with new seed
  Given an existing semester_evaluation
  When the teacher modifies the seed and clicks "重新生成"
  Then the same row should be updated (no new evaluation_id)
    And generated_text should be replaced with the new generation
    And edited_text should be cleared (teacher's old edit no longer applies)

@edge
Scenario: Seed validation
  Given the seed input field
  When the teacher enters a 10-char seed
  Then the [生成評語] button should remain disabled
    And a hint should display "請輸入 30-100 字的評價"

@edge
Scenario: Evaluation cites materials it should
  When generation is requested
  Then the prompt sent to LLM should include summaries from all 3 categories
    And those summaries should be PII-anonymized
    And the LLM response (after PII restore) should reference at least 2 specific events from materials (per AC-9)

@error
Scenario: Materials are sparse
  Given a student with ZERO artifacts in any category
  When the teacher tries to generate evaluation
  Then the UI should warn "此學生本學期無素材，僅能依種子內容生成"
    And the teacher can proceed (LLM call still happens, prompt notes sparse context)

@security
Scenario: PII is round-tripped correctly
  Given the seed includes the student's name "王小明"
  When the LLM call happens
  Then the prompt sent to OpenRouter contains "S001" (anonymized)
    And the response shown to the teacher contains "王小明" (restored)
```

### F-10: 瀏覽 / 編輯 / 下載 UI + Settings

```gherkin
Feature: Browse, edit, download, and settings
  As a teacher
  I want a complete UI for navigating my semester materials

@happy
Scenario: Drill-down navigation
  Given the teacher is on /dashboard
  When they click semester "113-1"
  Then they should be on /semester/113-1
    And see the student list
  When they click student "王小明"
  Then they should be on /student/<S001>
    And see the 3-category tabs
  When they click learning records tab and a specific file
  Then they should be on /file/<file_id>
    And see the editor

@happy
Scenario: Download original file
  Given the teacher is on a File Detail page
  When they click [下載原檔]
  Then a Drive direct-download URL should be opened (no proxy through server)

@happy
Scenario: Download processed artifact as .md
  Given the teacher is viewing an artifact
  When they click [下載產出]
  Then a .md file with frontmatter + content should download
    And it should match exactly content_markdown column (no transformation)

@happy
Scenario: Bulk download semester package
  Given the teacher is on a Semester Detail page
  When they click [下載整學期]
  Then a .zip should download containing:
    - For each student: a folder with original files + processed .md files
    - The semester evaluations as a single 評語.txt file
    - A README.txt explaining the structure

@happy
Scenario: Settings — change LLM tier model
  Given the teacher is on /settings/llm
  When they change tier "evaluation_quality" model to "anthropic/claude-haiku-4-5"
    And click save
  Then teacher.llm_tier_config should reflect the change
    And the next evaluation generation should use the new model
    And the audit log should reflect the new model_id used

@happy
Scenario: Settings — view PII mappings
  Given pii_mapping has 3 rows for the teacher
  When they navigate to /settings/pii
  Then they should see all 3 rows in the table
    And the teacher's name should NOT appear (only student names + types)
```

---

## 4. Cross-Cutting Scenarios

### 4.1 Security boundary

```gherkin
Feature: PII boundary enforcement (cross-cutting)

@security
Scenario: System refuses to send PII to OpenRouter even if anonymizer is bypassed
  Given a malicious code path tries to call openrouter_client.chat() directly
  When the call is made
  Then it should fail because LLMService is the only path
    And openrouter_client.chat() rejects calls not annotated as "post-anonymizer"

@security
Scenario: All LLM calls produce audit log entries
  Given any LLM call completes (success or failure)
  Then an llm_call_audit row should exist
    And tier, model_id, input_tokens, output_tokens, cost_usd, pii_replacement_count should all be set
```

### 4.2 Recovery and idempotency

```gherkin
Feature: Recovery and idempotency

@error
Scenario: Service restart during scan
  Given a scan is in progress at 50% completion
  When the service is killed and restarted
  Then the scan should NOT be auto-resumed (scan is not persistently stateful in V1 — it's quick enough to restart)
    And the teacher must manually re-trigger via "重新掃描" in Settings
  
@error
Scenario: Database write queue overflow
  Given DBWriteQueue is at capacity (>1000 backlog)
  When a new write is submitted
  Then it should raise QueueFull
    And the calling service should propagate to a 503 with retry-after
```

### 4.3 Cost budget

```gherkin
Feature: Budget cap

@error
Scenario: Monthly budget exceeded mid-batch
  Given budget_monthly_usd=$5.00 and current month spend=$4.95
    And a batch is mid-processing
    And the next file's estimated cost is $0.10
  When the BatchWorker would call the LLM
  Then the batch should pause with status="paused"
    And the UI should show "本月成本已達上限 $5.00"
    And buttons [調高上限] and [下個月再處理] should be available
```

---

## 5. Implementation Guidance

### 5.1 Recommended BDD framework: `pytest-bdd`

> **V1 walking-skeleton status**: NOT YET ADOPTED. Backend `pyproject.toml`
> does not include `pytest-bdd`; behaviour coverage is currently provided by
> 129 plain pytest unit + integration tests. This section describes the
> intended V1.x adoption path once the test pyramid grows past what plain
> pytest test names communicate clearly. See [`docs/work-plan.md`](work-plan.md)
> for the active roadmap.

For the Python backend (FastAPI):
- `pytest-bdd` integrates Gherkin into pytest's runner
- Each `.feature` file becomes a parametrizable test fixture set
- Step definitions live in `tests/bdd/steps/`

**Example mapping** (V1.x):
```
docs/BDD-001-behavior-scenarios.md   <-- this doc (human spec)
tests/bdd/features/F-1-oauth.feature  <-- Gherkin extracted
tests/bdd/steps/oauth_steps.py        <-- step implementations
```

### 5.2 Frontend behavior testing: Playwright + Gherkin layer (optional)

For E2E flows:
- Playwright tests CAN be written to mirror Gherkin scenarios (one-test-per-scenario)
- Or pure Playwright `test.describe` with descriptive names — looser coupling
- TDD-001 §X picks the recommended pattern

### 5.3 Don't over-couple to Gherkin

Per `lessons-learned/testing.md`: **manifests, not magic strings**.

Anti-pattern: extracting every Gherkin step into 100s of step-definition functions for trivial assertions.

Right pattern: Gherkin documents **intent**; implementation can use:
- Python: `pytest-bdd` for high-value happy path; pure pytest for unit-level
- TS: pure Playwright `test()` blocks; let test names mirror Gherkin titles

### 5.4 Background fixtures live in code, not Gherkin

The fixtures in §2 are **implemented as Python factory functions** (or TypeScript/Playwright fixtures). The Gherkin `Background:` clauses just **invoke** them by name.

### 5.5 PII fixtures — content-hash addressed (per lessons-learned/testing.md)

Test data for vision/OCR/audio:
```
tests/fixtures/
├── images/
│   ├── lab_report_chinese.png       (SHA-256: abc123...)
│   └── _hash_index.json             (maps hash → expected content)
├── docs/
│   ├── homework_clean.docx
│   ├── homework_encrypted.docx      (OLE encrypted signature)
│   └── _hash_index.json
└── audio/
    ├── 2speaker_3min.m4a
    ├── 1speaker_5min.m4a
    └── _hash_index.json
```

Mock LLM looks up by SHA-256 of input → returns canned response.

---

## 6. Coverage Tracker

| Feature | Scenarios written | Edge cases | Error cases | Security cases |
|---------|------|-----|------|----|
| F-1 | 5 | — | 4 | 2 |
| F-2 | 3 | 1 | — | — |
| F-3 | 5 | 2 | — | — |
| F-4 | 7 | 1 | 3 | 1 |
| F-5 | 5 | 2 | 2 | 1 |
| F-6 | 5 | 1 | — | 1 |
| F-7 | 7 | 2 | 4 | — |
| F-8 | 4 | 2 | — | — |
| F-9 | 7 | 2 | 1 | 1 |
| F-10 | 6 | — | — | — |
| Cross-cutting | 4 | — | 2 | 2 |
| **TOTAL** | **58** | **13** | **16** | **8** |

**Open coverage gaps** (V2 candidates):
- Multi-teacher scenarios (out of scope per A6)
- Concurrent edit conflict (single-user A6)
- Internationalization (zh-TW only V1)
- Performance scenarios (covered in TDD-001 §X under load tests, not BDD)

---

## 7. References

- [`docs/PRD.md`](PRD.md) §5 (F-1~F-10), §11 (AC)
- [`docs/UIUX-001-design-system.md`](UIUX-001-design-system.md) §5 (screen specs)
- [`docs/DESIGN-001-detailed-design.md`](DESIGN-001-detailed-design.md) §4 (service contracts), §6 (error matrix)
- `~/.claude/lessons-learned/testing.md` — manifest-driven, content-hash fixtures
- pytest-bdd: https://pytest-bdd.readthedocs.io/

---

> **End of BDD-001 v0.1**. Next doc: TDD-001 (test pyramid + Playwright E2E + mock strategy).
