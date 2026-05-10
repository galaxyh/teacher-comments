# teacher-comments — Claude Code Project Instructions

> Project-level guidance for Claude Code. User-level / global instructions live
> in `~/.claude/CLAUDE.md`. This file overrides global where it conflicts.

## Project status

Newly initialized. Tech stack: **undecided / docs-only** for now.

When the tech stack is chosen, update the lessons-learned trigger rules table
below to add the corresponding rows (see `~/.claude/lessons-learned/README.md`
for the full catalogue of available rules).

## 決策治理（Decision Governance）

採用三層決策紀錄機制，避免設計轉彎與重複踩雷：

| 層級 | 何時使用 | 位置 |
|------|---------|------|
| **ADR**（重 — 含選項評估、後果） | 重大架構決策（DB、tech stack、跨模組介面） | `docs/adr/ADR-XXX-*.md` |
| **DECISIONS.md**（中 — 時間軸式索引） | 一般設計決策、config 調整、工具選擇、reversal | `docs/adr/DECISIONS.md` |
| **Commit message**（輕 — 原子實作） | 每次 commit 的 why | git log |

### Pre-Action Verification Protocol（每次 non-trivial 變更前必跑）

當任務涉及「設定基礎建設、引入新依賴、改動跨 module 介面、推翻先前決策、新增 process 規範」時，**先做以下檢查再提案**：

1. **`grep -i <關鍵字> docs/adr/DECISIONS.md`** — 是否曾做過同類決策？特別注意 `[REVERSED]` 標記
2. **檢查 lessons-learned trigger rules**（下方表格）— 是否有對應已知教訓？
3. **讀 PRD / 鎖定規格相關章節** — 確認沒違反 non-negotiable 約束
4. **`git log --oneline -- <相關檔案>`** — 該檔案的修改史是否有相關脈絡？
5. **在提案中明示「Previous attempts」段落** — 即使是空的（"無前例"）也要寫，強迫自己有意識搜尋過

> **Why**：跳過這 5 步常導致「實作後立刻 reverse」的浪費。lessons-learned 已有相關教訓但沒被觸發，是最常見的失敗模式。

### Reversal Protocol（推翻先前決策時）

當 commit 會推翻先前的 commit / decision：

1. **Cite original commit** — commit message 加 `Reverses: <hash> <one-line summary>` 行
2. **Explain ROOT CAUSE** — 不寫「user 改變主意」，要寫「為何當初的決策是錯的」（後人才能避免再犯）
3. **Update DECISIONS.md** — 新 entry 帶 `Reverses:` 欄位 + 在被推翻的 entry 加 `[REVERSED]` 標題前綴 + `Reversed by:` 行（這是 DECISIONS.md 唯一允許的「編輯舊 entry」場景）
4. **若是泛用教訓，update lessons-learned** — 對應 category 加新 lesson 或修訂既有 lesson

### 子 Agent 輸出驗證（Trust but Verify）

當主 agent 透過 `Agent` tool 委派任務給子 agent：
- **寫程式類** → 主 agent 回讀 critical diff（不只看 sub-agent 的 summary）
- **研究類** → sub-agent 報告中如有 file path / commit / function 引用，主 agent 抽樣驗證
- **Plan 類** → 主 agent 重述計畫的 1-2 個關鍵假設給 user 確認

## 工程經驗庫（Lessons Learned — Trigger Rules）

`~/.claude/lessons-learned/` 存有按類別分檔的跨專案工程經驗。**實作前必須讀取相關檔案**，避免重複犯錯。

**觸發規則 — 符合任一條件時，先 Read 對應檔案再動手：**

| 觸發條件 | 必讀檔案 | 摘要 |
|----------|---------|------|
| Markdown link checker、文件交叉引用、tracked symlinks 破壞 CI | `~/.claude/lessons-learned/documentation.md` | lychee 配置、`.lycheeignore`、symlink 在 CI runner 上的失效模式 |
| 設計決策、reversal、跨 session 協作、agent 編排、新專案 init | `~/.claude/lessons-learned/engineering-process.md` | 三層決策治理（ADR/DECISIONS.md/commit）+ Pre-Action Verification + Reversal Protocol |

> **TODO**：選定 tech stack 後，根據 `~/.claude/CLAUDE.md` 的觸發規則表，補上對應的 stack-specific 規則（例如 Python 專案應加上 `api-design.md`、`concurrency.md`、`testing.md`、`database.md` 等列）。

索引見 `~/.claude/lessons-learned/README.md`。
