# UIUX-001: Design System & Per-Screen Specs

| Field | Value |
|-------|-------|
| **Status** | Draft v0.1 |
| **Date** | 2026-05-10 |
| **Owner** | Steven Chen |
| **Depends on** | [`PRD.md`](PRD.md) §7, [`ARCH-001-architecture.md`](ARCH-001-architecture.md) §2.2, [`mockups/`](../mockups/) |
| **Consumers** | Frontend implementation, BDD-001 |

---

## 0. Document Control

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 0.1 | 2026-05-10 | Steven (with Claude Code) | Initial — design tokens extracted from mockups, 8 screen specs |

**Reading order**:
- §2 Design Philosophy → §3 Design Tokens (foundational; everything else references these)
- §4 Component Library (atomic UI elements)
- §5 Screen Specs (composes components into screens)
- §6 Interaction Patterns (cross-cutting behaviors)
- §7-§9 a11y / responsive / open questions

**Source of design language**: [`mockups/`](../mockups/) — standalone React UMD prototype codenamed 「墨痕」 (D15 confirmed mockup is informational, not the V1 production frontend code). UIUX-001 captures the **design system** that V1 implementation must follow; it does **not** dictate framework choice (PRD D2 already locks Next.js + React).

---

## 1. Context

The mockup folder `mockups/` ships as a standalone-runnable React UMD prototype with `styles.css` containing all design tokens. UIUX-001 **codifies** what the mockup expresses tacitly — colors, type scales, spacing, components, screens — so V1 implementation can:

- Reproduce the design without re-inventing
- Check style coverage against an explicit list
- Bridge mockup → Tailwind config / CSS modules / styled-components in a controlled way

Where the mockup leaves something ambiguous (e.g., new `unprocessable` state from DESIGN-001 §2.1 doesn't yet have a badge color), this doc fills the gap with explicit decisions rather than defer to ad-hoc implementation choices.

---

## 2. Design Philosophy

**「紙感 + 墨色 + 朱砂硃批」** — paper grain + ink tones + vermillion teacher's marks.

The mockup deliberately evokes the visual language of **traditional Chinese-language education**: warm paper background (not stark white), ink-gray text (not pure black), and a single vermillion (`#c1452a`) accent color borrowed from the red ink teachers historically used to mark student work.

| Choice | Rationale |
|--------|-----------|
| Warm paper backgrounds (`#fbfaf6`) over pure white | Reduces eye strain in long editing sessions; teachers spend hours with these texts |
| Serif headings (Noto Serif TC) | Calls back to printed educational materials; signals seriousness |
| Sans-serif body text (Noto Sans TC) | Optimal screen readability |
| Single accent color (vermillion) | Used sparingly — primary CTAs, current selections, teacher-action highlights |
| Subtle shadows (`sh-1` to `sh-3`) | Depth via layering, not from drop-shadows; preserves "paper stack" aesthetic |
| Density token (`--dens` 0.85-1.15) | Teachers may use compact view on smaller screens; configurable |

**Anti-patterns** (deliberately avoided):
- **Bright "modern SaaS" gradients** — feels mismatched with educational tone
- **Pure black text** — too harsh against warm paper
- **Cute illustrations / mascots** — undermines the system's seriousness as a teacher's tool
- **Bouncy animations** — distracting; subtle 80-240ms transitions only

---

## 3. Design Tokens

> Source of truth: [`mockups/styles.css`](../mockups/styles.css). V1 implementation must replicate these tokens (e.g., as Tailwind config or CSS variables) — values copied below.

### 3.1 Color tokens

**Paper / ink palette (light theme)**:

| Token | Value | Usage |
|-------|-------|-------|
| `--paper-0` | `#fbfaf6` | Page background |
| `--paper-1` | `#f5f2ea` | Sidebar, card alt-background |
| `--paper-2` | `#ede8dc` | Hover state |
| `--paper-3` | `#e0d9c8` | Pressed / strong hover |
| `--ink-0` | `#14130f` | Primary text |
| `--ink-1` | `#2c2a25` | Headings, emphasized |
| `--ink-2` | `#5a5751` | Secondary text |
| `--ink-3` | `#8a877f` | Tertiary text, captions |
| `--ink-4` | `#b8b3a6` | Border hover |
| `--line-1` | `#e6e0d2` | Default border / divider |
| `--line-2` | `#d8d1bf` | Stronger border |

**Accent (vermillion 朱砂)**:

| Token | Value | Usage |
|-------|-------|-------|
| `--accent` | `#c1452a` | CTA buttons, current selection, teacher-action emphasis |
| `--accent-soft` | `#e87557` | Hover variant |
| `--accent-bg` | `#f7e9e2` | Accent-tinted background (avatar, accent-soft chip) |
| `--accent-ink` | `#7a2a18` | Text on accent-bg |

**Accent variants** (user-selectable in Settings, mockup `tweaks-panel.jsx`):

| Name | Primary | Soft | Background |
|------|---------|------|------------|
| 朱砂 (default) | `#c1452a` | `#e87557` | `#f7e9e2` |
| 墨綠 | `#2d5d5e` | `#4a8688` | `#dde9e9` |
| 藏青 | `#3a4d6b` | `#6580a3` | `#dde3ed` |
| 紫 | `#7a4a89` | `#a37cb0` | `#ebdef0` |

V1 ships all 4. Stored as `teacher.preferences.accent` (TEXT, default `"朱砂"`).

**State colors (file processing states)**:

> Note: `unprocessable` is **new** — added per DESIGN-001 §2.1. Token values defined below extend `mockups/styles.css`.

| State | Foreground | Background | Existed in mockup? |
|-------|-----------|------------|--------------------|
| `pending` | `#8a877f` | `#ede8dc` | ✓ |
| `processing` | `#2563a8` | `#dde7f3` | ✓ |
| `processed` | `#2f7a4d` | `#dceadf` | ✓ |
| `teacher_edited` | `#6b3aa3` | `#e8def4` | ✓ |
| `reprocess_pending` | `#b9701a` | `#f7e7cc` | ✓ |
| `failed` | `#b03030` | `#f4d9d6` | ✓ |
| **`unprocessable`** | **`#7a1f1f`** | **`#e8c8c5`** | **NEW (V1)** |

`unprocessable` uses a deeper red than `failed` to signal "more terminal" — teacher should expect the retry button to rarely help.

### 3.2 Typography

**Font families** (loaded via Google Fonts in mockup `墨痕 - 教師評語系統.html`):

| Token | Font stack |
|-------|-----------|
| `--serif` | `"Noto Serif TC", "Source Han Serif TC", ui-serif, Georgia, serif` |
| `--sans` | `"Noto Sans TC", "PingFang TC", ui-sans-serif, system-ui, sans-serif` |
| `--mono` | `"JetBrains Mono", ui-monospace, "SFMono-Regular", monospace` |

**Type scale**:

| Use | Size | Family | Weight | Line-height | Letter-spacing |
|-----|------|--------|--------|-------------|----------------|
| Page heading (h1) | 28px | Serif | 600 | 1.2 | 0.01em |
| Section heading | 18-20px | Serif | 600 | 1.3 | normal |
| Subsection | 15px | Sans | 600 | 1.4 | normal |
| Body | 14px | Sans | 400 | 1.55 | normal |
| Body small | 13.5px | Sans | 400 | 1.55 | normal |
| Caption | 12px | Sans | 400 | 1.5 | normal |
| Label small | 11px | Sans | 600 | normal | 0.06em (uppercase) |
| Nav section title | 10px | Sans | 600 | normal | 0.12em (uppercase) |
| Mono inline | 11-13px | Mono | 400 | inherit | normal |

**Special features**:
- `font-feature-settings: "palt" 1` on body — proportional alt for CJK punctuation
- `text-rendering: optimizeLegibility` — CJK glyph clarity

### 3.3 Spacing & density

```css
--dens: 1;                          /* user-tunable: 0.85, 1.0, 1.15 */
--pad-1: calc(8px * var(--dens));   /* tight inline spacing */
--pad-2: calc(12px * var(--dens));  /* component internal */
--pad-3: calc(16px * var(--dens));  /* card padding, section gap */
--pad-4: calc(24px * var(--dens));  /* page-internal vertical rhythm */
--pad-5: calc(32px * var(--dens));  /* page-level top/bottom */
--row-h: calc(40px * var(--dens));  /* table row, list item */
```

Density is **user-configurable** in Settings (3 options): `compact (0.85)` / `default (1.0)` / `comfortable (1.15)`.

### 3.4 Radii & shadows

| Token | Value | Usage |
|-------|-------|-------|
| `--r-1` | 4px | Inline chips, kbd |
| `--r-2` | 8px | Buttons, inputs, segmented |
| `--r-3` | 12px | Cards |
| `--r-4` | 18px | Large containers, dialog |

| Token | Value | Usage |
|-------|-------|-------|
| `--sh-1` | `0 1px 0 rgba(20,19,15,.04), 0 1px 2px rgba(20,19,15,.04)` | Card resting |
| `--sh-2` | `0 1px 0 rgba(20,19,15,.05), 0 4px 12px rgba(20,19,15,.05)` | Hovered card |
| `--sh-3` | `0 1px 0 rgba(20,19,15,.06), 0 12px 32px rgba(20,19,15,.08)` | Elevated panel |
| `--sh-pop` | `0 18px 60px rgba(20,19,15,.18)` | Modal / popover |

**Shadow philosophy**: subtle — preserves the "paper stack" aesthetic. No shadows over 18% opacity. No outer-glows.

### 3.5 Theme (light + dark)

Mockup ships dark mode (`[data-theme="dark"]`). V1 ships both.

**Switching mechanism**: 
- Default: follow system (`prefers-color-scheme`)
- Override: stored in `localStorage` (frontend-only — no server roundtrip)
- Settings page provides explicit selector: `system / light / dark`

**Dark mode key differences**:
- Paper → ink: dark warm browns (`#16140f` to `#2f2b23`) — not pure gray
- Ink colors lighten (`#f0ebde` to `#5a554a`)
- Accent intensifies slightly (`#c1452a` → `#e87557`) for contrast
- State colors stay the same hue but darken backgrounds

### 3.6 Density variants

In addition to `--dens`, V1 supports:

| Mode | `--dens` | Use case |
|------|----------|----------|
| Compact | 0.85 | Power user, large screen |
| Default | 1.0 | Most users |
| Comfortable | 1.15 | Touch screens, accessibility, smaller screen |

---

## 4. Component Library

> All components implement light + dark theme automatically via CSS custom properties. V1 implementation in `frontend/src/components/ui/`.

### 4.1 Button

**Variants**: `default` / `primary` / `accent` / `ghost`. **Sizes**: `sm` / `md` (default) / `lg`.

| Variant | Background | Text | Border | Use case |
|---------|-----------|------|--------|----------|
| `default` | `--paper-0` | `--ink-0` | `--line-2` | Secondary actions |
| `primary` | `--ink-0` | `--paper-0` | `--ink-0` | Main confirm action (e.g., "下一步" in onboarding) |
| `accent` | `--accent` | `#fff` | `--accent` | High-emphasis actions (e.g., "處理本學期", "生成評語") |
| `ghost` | transparent | `--ink-0` | transparent | Tertiary, navigation |

**Sizes** (vertical padding × horizontal padding × font-size):
- `sm`: 4×8 × 12px
- `md`: 7×12 × 13px (default)
- `lg`: 10×18 × 14px

**States**: hover (slight bg shift), focus (3px ring `--paper-2`), disabled (opacity 0.5).

**Icon support**: optional 14px icon left of label.

### 4.2 Card

```html
<div class="card">
  <header class="card-head">…</header>
  <div class="card-body">…</div>
  <footer class="card-foot">…</footer>
</div>
```

- Background: `--paper-0`
- Border: 1px `--line-1`
- Radius: `--r-3` (12px)
- Shadow: `--sh-1`
- Padding: `--pad-3` to `--pad-4`

**Hovering**: lift to `--sh-2` if interactive (clickable cards).

### 4.3 Badge — **state badges** (load-bearing for D4 edit protection)

7 states, each with `dot + label`:

```html
<span class="badge processed"><span class="dot"></span>已處理</span>
```

Per-state spec:

| State badge | Label (zh-TW) | Background | Foreground | Icon hint |
|-------------|---------------|-----------|-----------|-----------|
| `pending` | 待處理 | `#ede8dc` | `#8a877f` | ⏳ |
| `processing` | 處理中 | `#dde7f3` | `#2563a8` | ⚙️ |
| `processed` | 已處理 | `#dceadf` | `#2f7a4d` | ✅ |
| `teacher_edited` | 已修改 | `#e8def4` | `#6b3aa3` | ✏️ |
| `reprocess_pending` | 待你決定 | `#f7e7cc` | `#b9701a` | ⚠️ |
| `failed` | 處理失敗 | `#f4d9d6` | `#b03030` | ❌ |
| `unprocessable` | 無法處理 | `#e8c8c5` | `#7a1f1f` | 🚫 |

**Differential behavior on click**:
- `failed` badge → expand to show `[重試]` button (default)
- `unprocessable` badge → expand to show disclosure note "罕見有效，原因：encrypted/corrupt/unsupported" with `[強制重試]` button (smaller, less prominent)

### 4.4 Input / Textarea / Select

- Single class `.input` / `.textarea` / `.select`
- Padding: 8×10
- Border: 1px `--line-2`, radius `--r-2`
- Focus: border `--ink-1`, ring 3px `--paper-2`
- `.textarea`: `resize: vertical`, line-height 1.6

**Special textarea**: seed-input for evaluation generation (PRD F-9) has visible character counter (30-100 chars).

### 4.5 Segmented control

For mutually-exclusive choices (e.g., evaluation style: 正式 / 鼓勵 / 客觀):

```html
<div class="seg">
  <button data-active="true">正式</button>
  <button>鼓勵</button>
  <button>客觀</button>
</div>
```

- Background: `--paper-1`
- Padding: 3px (outer) × 5×12 (per button)
- Active button: `--paper-0` background, shadow `--sh-1`

### 4.6 Table

Used in: file lists, batch progress, PII mapping table.

**Style**:
- Header: 11px uppercase labels, color `--ink-3`, letter-spacing 0.06em
- Row hover: bg `--paper-1`
- Row padding: 12px, vertical-align middle
- Last row: no bottom border

**Features V1 needs**:
- Sortable column headers (click to toggle asc/desc) — used in students list, files list
- Row selection (checkboxes) — used in batch console for "select N to retry"
- Empty state inline ("No files yet — process this semester first")

### 4.7 Progress bar

Used during batch processing:

```html
<div class="progress"><span style="width: 47%"></span></div>
```

- Height: 6px
- Background: `--paper-2`
- Fill: linear gradient `--accent` → `--accent-soft`
- Animation: `width 200ms ease-out`

**Composite "batch progress" widget**:

```
[████████░░░░░░░░░░░] 47%
已完成 24/51   失敗 0   進行中 4   花費 $0.34
```

### 4.8 Sidebar Navigation

Fixed 248px width on desktop. Structure:

```
┌─────────────┐
│ 🖋 墨痕      │  <- brand area (28px logo + name + sub)
│ 教師評語系統 │
├─────────────┤
│ 學期        │  <- nav section title (10px uppercase)
│ ▸ 113-1     │
│ ▸ 113-2     │
│ 工具        │
│ ◯ 處理控制台│
│ ⚙ 設定      │
├─────────────┤
│ 👤 王老師    │  <- footer with avatar + email
└─────────────┘
```

**States**:
- Hover: `bg: --paper-2`
- Active (current route): `bg: --paper-0`, `box-shadow: --sh-1`, accent-colored icon

### 4.9 Topbar with breadcrumbs

52px high. Layout:

```
[≡]  Dashboard / 113-1 / 王小明           [🌙] [🔔] [👤]
```

- Breadcrumb separator `--ink-4`
- Last crumb `--ink-0` (current page)
- Right-aligned actions (theme toggle, notifications, user menu)

### 4.10 Dialog / Modal

Three variants in V1:

**4.10.1 Attestation dialog** (D17, blocking onboarding)
- Modal overlay, no dismiss-on-outside-click
- Body: 600 char attestation text in `--serif`
- Footer: `[我同意]` (primary, accent) + `[取消（登出）]` (default)
- Cannot be closed without explicit action

**4.10.2 Mapping wizard** (D14, blocking scan resume)
- Modal overlay
- Body: per-detected-folder dropdown (3 standard categories + "不歸類")
- Footer: `[儲存對應]` (primary, accent)
- Can be cancelled (returns to root selection)

**4.10.3 Reprocess conflict prompt** (D4 edit protection)
- Inline expandable card per file (NOT modal — many files may need decisions)
- Pattern:
  ```
  ⚠️ 王小明 / 學習紀錄 / lab_report.png
     你已修改此檔案的處理產出。原檔已更新，是否要重新產生並覆蓋？
     [覆蓋我的編輯]   [保留我的編輯]
  ```
- Bulk action: `[全部覆蓋]` / `[全部保留]` at top of conflict list

### 4.11 Editor (Markdown + Mermaid preview)

For .md summary editing (PRD F-10) and evaluation editing (PRD F-9).

**Layout**: split pane, 50/50 by default
- Left: source text (CodeMirror 6 or Monaco)
- Right: rendered preview (Markdown + Mermaid)

**Features**:
- Auto-save every 30s (visible "saving..." → "saved" indicator)
- Force-save on `Ctrl/Cmd+S`
- Undo/redo
- Mermaid blocks render live in preview pane
- For evaluation editor: simpler (no markdown — just plain text); preview pane shows char count

**Editor-specific tokens**:
- Code font: `--mono`
- Editor padding: `--pad-3`
- Selection background: `--accent-bg`

---

## 5. Screen Specs

### 5.1 Onboarding flow (5 steps)

Per `mockups/screens-onboarding.jsx`:

```
ScreenLogin → ScreenConsent → ScreenRoot → ScreenMapping → ScreenScan
   ↓             ↓               ↓             (conditional)    ↓
"使用 Google     [我同意 attestation]  [Pick Drive folder]   [progress]
 登入"           
```

**Layout**: full-page, no sidebar. Centered card max-width 560px.

**Step indicator**: top of card, 5 dots (• ○ ○ ○ ○) showing progress.

**Per-screen**:

**Login (5.1.1)**:
- Heading: "歡迎使用墨痕"
- Subtitle: "教師評語系統"
- Single button: `[使用 Google 登入]` (primary, lg)
- Below: small print legal links

**Consent / Attestation (5.1.2, D17)**:
- Heading: "使用前確認"
- Body: full attestation text (per PRD F-1)
- Checkbox: "我已閱讀並同意上述聲明"
- Footer: `[我同意]` (primary, disabled until checked) + `[取消]` (ghost)

**Drive Root Pick (5.1.3, F-2)**:
- Heading: "選擇教學資料根目錄"
- Body: Drive folder tree (lazy-loaded), highlighting common patterns ("教學資料" or "Teaching" pre-selected if present)
- Each tree node: `[▸] 📁 folder_name (X subfolders)`
- Footer: `[下一步]` (primary, disabled until folder selected) + `[上一步]` (ghost)

**Mapping Wizard (5.1.4, D14)**:
- Heading: "對應資料夾類別"
- Body intro: "我們發現 <student_name> 下有以下子資料夾，請對應到三類："
- Three dropdowns (one per category):
  ```
  學習紀錄        ← [課堂筆記      ▼]
  教師與學生互動  ← [晤談紀錄      ▼]
  作品成果        ← [報告作品      ▼]
  ```
- "不歸類" option for extras
- Footer: `[儲存對應關係]` (primary)

**Scan Progress (5.1.5)**:
- Heading: "正在掃描你的教學資料夾"
- Body: progress bar + live text "已掃描 X 個學期 / Y 位學生 / Z 個檔案"
- Footer: `[完成]` (appears when scan done)

### 5.2 Dashboard (`mockups/screens-main.jsx#Dashboard`)

Default landing after onboarding.

**Layout**:
- Sidebar: standard nav
- Topbar: just "Dashboard" breadcrumb
- Content: 3 sections vertical stack

**Sections**:
1. **Hero card** — current semester summary
   - Big heading: "本學期：113-1 上學期"
   - 4 stats: `學生 40 / 待處理 152 檔 / 已處理 1,420 檔 / 總成本 $1.04`
   - Primary CTA: `[處理本學期]` (accent, lg) — leads to Batch Console

2. **Recent activity** — last 5 batch jobs
   - Card with mini table: when / files / status (badge)

3. **Semester selector** — past semesters
   - Cards row, click → Students view for that semester

### 5.3 Students list (`screens-main.jsx#Students`)

Per-semester student list.

**Layout**: standard sidebar + topbar (`Dashboard / 113-1`).

**Content**:
- Filter row: `[搜尋學生]` + segment `[全部 | 待處理 | 已完成評語]`
- Table:
  | 學生 | 學期素材 | 評語狀態 | 動作 |
  |------|---------|---------|------|
  | 王小明 (S001) | 42 檔 (40 已處理) | (badge: 已生成) | `[查看]` |
  | 李小華 (S002) | 38 檔 (35 已處理 / 3 失敗) | (badge: 未生成) | `[查看]` |

### 5.4 Student Detail (`screens-main.jsx#StudentDetail`)

Per-student view: 3 categories side-by-side or as tabs.

**Layout**: sidebar + topbar (`Dashboard / 113-1 / 王小明`).

**Content**:
- Header row: student name + pseudonym + total files + last-batch info
- Tabs: `[學習紀錄]` `[教師與學生互動紀錄]` `[作品成果]`
- Each tab: file list (table), state badges per file, click row → File Detail
- Right panel: link to evaluation generator for this student-semester

### 5.5 File Detail (`screens-eval.jsx#FileDetail`)

Single file view: original metadata + processed artifact editor.

**Layout**: sidebar + topbar (`Dashboard / 113-1 / 王小明 / lab_report.png`).

**Two-column layout**:
- Left (40%): metadata card — `filename / mime / size / modified at / Drive direct link`
- Right (60%): editor (markdown + Mermaid preview, see 4.11)

**Footer actions**:
- `[儲存]` (primary)
- `[重新處理]` (default — converts to reprocess_pending)
- `[下載原檔]` `[下載產出]` (ghost)

### 5.6 Evaluation Generator (`screens-eval.jsx#EvaluationGenerator`)

The **highest-stakes screen** — drives PRD §1.2 vision.

**Layout**: sidebar + topbar (`Dashboard / 113-1 / 王小明 / 評語`).

**Content** (vertically stacked):

1. **Material summary card** (collapsible, default expanded)
   - 3 columns: 學習紀錄 / 互動 / 作品 — each shows count + key keywords (extracted from artifacts)
   - Click any item → expand inline preview

2. **Seed input card**
   - Heading: "你對 王小明 本學期的觀察（30-100 字）"
   - Textarea: large, character count visible
   - Style segmented control: `[正式 | 鼓勵 | 客觀]` (D12)
   - CTA: `[生成評語]` (accent, lg)

3. **Generation result card** (shown after first generation)
   - Plain-text editor (not markdown)
   - Char count display (no validation per OQ-10)
   - Actions: `[重新生成]` `[儲存]` `[下載]`
   - Audit info: cost / model / generated-at

### 5.7 Batch Console (`screens-system.jsx#BatchConsole`)

Where batch processing happens.

**Layout**: sidebar + topbar (`處理控制台`).

**Pre-batch state**:
- Heading: "選擇要處理的學期"
- Card per semester: filename count, last-batch info, `[處理]` button
- Below: "本月成本上限 $5.00 / 已用 $2.34" (progress bar)

**During batch state**:
- Hero progress bar (composite per §4.7)
- Live event log (last 10 events): "✅ 王小明 / 學習紀錄 / lab_report.png 已處理"
- Per-state counts (badges)
- Reprocess decisions (if any) inline expandable cards (§4.10.3)
- Footer: `[暫停]` (default) | `[取消]` (ghost) | `[隱藏到背景]` (ghost — nav stays usable)

**Post-batch state**:
- Summary card: `處理完成 / 失敗 / 無法處理 / 跳過` counts
- Cost summary
- `[查看失敗清單]` `[查看無法處理清單]` (open file lists with state filter)
- `[完成]` (returns to dashboard)

### 5.8 Settings (`screens-system.jsx#Settings`)

Settings has 6 sub-pages (per PRD §7.1 + AC-10):

```
Settings
├── LLM 模型 (D8 / D9)         <- 4 dropdowns for tier→model
├── PII 替換 (D13)             <- table, rename, manual add
├── 資料夾對應 (D14)           <- view + reset mapping
├── 預算 (PRD §6.2)             <- monthly cap input
├── 同意聲明 (D17)             <- show signed at, version, re-sign link
└── 帳號                        <- email, logout, revoke
```

**Layout**: sidebar (settings sub-nav) + content panel.

**5.8.1 LLM 模型 sub-page**:
- 4 cards (one per tier): tier name, current model, dropdown to change, "現在使用" indicator
- Below: cost calc preview ("以你目前選擇估算每學期約 $X")

**5.8.2 PII 替換 sub-page** (D13, F-6 Min UI):
- Table (per §4.6) with 5 columns: Pseudonym / 顯示名 / 原值 (decrypted) / 來源 (auto/manual) / 動作
- Below: `[+ 新增手動映射]` (default)
- Confirmation dialog on `[重設所有 mapping]`

**5.8.3 資料夾對應 sub-page**:
- Read-only view of current `teacher.folder_mapping`
- `[重設並重新掃描]` (warning button)

**5.8.4 預算 sub-page**:
- Numeric input: monthly cap USD
- Bar chart: month-by-month spending (last 6 months)

**5.8.5 同意聲明 sub-page**:
- Read-only display: "你於 2026-XX-XX 簽署了 v1 版本"
- If new version available: `[查看新版]` + `[重新簽署]`

**5.8.6 帳號 sub-page**:
- Email + Google account icon
- `[登出]` (default) / `[Revoke 並刪除 OAuth token]` (warning, double-confirm)

---

## 6. Interaction Patterns

### 6.1 Loading states

Three patterns:

| Context | Pattern | Reasoning |
|---------|---------|-----------|
| First-time data fetch (page mount) | Skeleton screens (gray paper-2 boxes) | Reduce perceived latency; don't show spinning indicator unless > 500ms |
| Inline action (e.g., `[儲存]` button) | Button → `[儲存中...]` + spinner inside | Keep user in context |
| Batch processing | Progress bar (§4.7) + live event log | Provides agency; user sees ongoing work |

### 6.2 Empty states

Pattern per case:

- **No semesters**: "尚未掃描教學資料根目錄" + `[去設定]` link
- **No students in semester**: "本學期目錄中沒有偵測到學生資料夾" + suggest checking folder structure
- **No files in category**: "此類別目前沒有檔案"
- **No evaluations yet**: "尚未為 王小明 產生評語" + `[現在生成]` accent CTA
- **No batch history**: "尚未執行過任何批次處理"

Each empty state uses subtle illustration (1 SVG line drawing, ink color) — NOT a mascot.

### 6.3 Error states

| Error | UI pattern |
|-------|-----------|
| Network down | Toast + retry button at top of page |
| OAuth revoked | Full-page redirect to login with explanation |
| Drive 403 / quota | Inline banner with `Retry-After` countdown |
| LLM rate limit during batch | Inline banner; batch auto-pauses, resumes when limit clears |
| LLM quota exhausted | Inline banner + batch paused; teacher must manually resume tomorrow |
| File processing failed | Badge + per-file action |
| File processing unprocessable | Badge + disclosure (rare-retry) |
| PII leakage (boundary check fail!) | Critical alert toast + system_event log; batch pauses |

### 6.4 Conflict prompts (D4 edit protection)

Two flows:

**Pre-batch flow** (when teacher starts batch):
- Modal showing list of `reprocess_pending` files
- Per-file: inline expand with `[覆蓋]` / `[保留]` choice
- Bulk actions at top: `[全部覆蓋]` / `[全部保留]`
- After all decisions made: `[繼續]` button proceeds with batch

**During-browse flow** (when teacher opens a file):
- Inline banner above editor: "原檔已更新。系統有新版本可用。"
- Buttons: `[查看新版]` (preview) / `[替換為新版]` (reprocess overwrite) / `[忽略]` (keep edits)

### 6.5 Progress reporting (SSE)

Real-time updates flow via Server-Sent Events (`/batch/<id>/events`).

**Reconnect logic** (per `lessons-learned/frontend.md` SSE caveat):
- Connection deferred until `useEffect` cleanup-friendly point (not in `init`)
- On disconnect, exponential backoff retry (1s / 2s / 4s, max 5 attempts)
- After max retries, fall through to `GET /batch/<id>/status` polling at 5s intervals

**State variable naming** (per `lessons-learned/frontend.md`): `llmQuotaPaused` / `batchPaused` — provider-agnostic. Never `geminiQuotaPaused` etc.

---

## 7. Responsive Rules

V1 is **desktop-first** (per PRD §6.1 — "first page load < 2s"). Mobile is read-only fallback.

Breakpoints:

| Breakpoint | Behavior |
|-----------|----------|
| ≥ 1280px | Full layout: sidebar 248px + main |
| 1024-1279px | Sidebar collapsible (toggle button) |
| 768-1023px | Sidebar always collapsed; tablet view |
| < 768px | Mobile read-only: simplified nav (drawer), no editing |

**On mobile (< 768px)**:
- Editors switch to read-only with "在電腦上編輯" banner
- Batch processing not available (read-only browse only)
- Login + dashboard + browse work normally

---

## 8. Accessibility (a11y)

Target: **WCAG 2.1 AA**.

| Concern | Approach |
|---------|----------|
| **Color contrast** | All text/background pairs verified ≥4.5:1; state badges ≥3:1 (large text exemption applies for badge labels) |
| **Keyboard navigation** | All interactive elements reachable via Tab; visible focus rings (`box-shadow 0 0 0 3px --paper-2`) |
| **Screen reader** | Semantic HTML; `aria-label` on icon-only buttons; `aria-live` regions for SSE updates |
| **Reduced motion** | Respect `prefers-reduced-motion`: disable fade-in, progress bar transitions become instant |
| **Font scaling** | Honor browser zoom; relative units (rem/em) where possible |
| **Form labels** | Every input has associated `<label>` |
| **Error association** | Form errors linked via `aria-describedby` to triggering field |

V1 audit tooling: `axe-core` integrated in Playwright E2E (TDD-001 §X).

---

## 9. Open UI Questions

| OUQ | Question | Disposition |
|-----|----------|-------------|
| **OUQ-1** | Onboarding step indicator — 5 dots vs progress bar with labels? | V1: dots (cleaner); V2 may A/B test |
| **OUQ-2** | Should `unprocessable` state surface a "diagnostic tip" (e.g., "this file appears encrypted")? | V1 yes — display `failure_reason` from DB inline below badge |
| **OUQ-3** | Density should be tied to `prefers-reduced-motion`? | V1 no — independent settings; user might want fast animation but compact density |
| **OUQ-4** | Mobile editing — V1 truly read-only or a degraded "view + minor edit" mode? | V1 strict read-only; any text edit → "在電腦上編輯" banner |
| **OUQ-5** | Conflict prompts — bulk override option needed? | YES (per §6.4); must be present V1 |
| **OUQ-6** | Mermaid render in editor — live or button-triggered? | V1 live (debounced 500ms); easier to spec, simpler mental model |

These do not block V1 implementation; treat as defaults to be adjusted on user feedback.

---

## 10. References

- [`mockups/`](../mockups/) — design system source (8 jsx + styles.css)
- [`docs/PRD.md`](PRD.md) §7 (IA + state badges) — UI surface area
- [`docs/ARCH-001-architecture.md`](ARCH-001-architecture.md) §2.2 — frontend module tree
- [`docs/DESIGN-001-detailed-design.md`](DESIGN-001-detailed-design.md) §2.1 — `unprocessable` state addition (informs §3.1, §4.3 here)
- `~/.claude/lessons-learned/frontend.md` — Alpine/React reactive state pitfalls (informs §6.5)
- WCAG 2.1 AA spec — accessibility target

---

> **End of UIUX-001 v0.1**. Next doc: BDD-001 (behavior scenarios in Gherkin form).
