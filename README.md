# teacher-comments

[![Markdown Link Check](https://github.com/galaxyh/teacher-comments/actions/workflows/link-check.yml/badge.svg)](https://github.com/galaxyh/teacher-comments/actions/workflows/link-check.yml)

> 教師評語系統 — 基於 Google Drive 教學素材自動產生 300-500 字學期評語的單人 SaaS 工具。
> 設計給中小學個人教師：以教師「評價種子 + 個人觀察」為核心，AI 僅輔助整合素材、產出初稿。

## Status

**Stage**: Engineering design freeze — V1 implementation ready

- **Functional spec**: [`docs/PRD.md`](docs/PRD.md) (v0.2, 17 locked decisions)
- **Decision log**: [`docs/adr/DECISIONS.md`](docs/adr/DECISIONS.md) (D-01 through D-05)
- **Architectural rationale**: [`docs/adr/ADR-001-system-foundation.md`](docs/adr/ADR-001-system-foundation.md) (7 axes, options evaluated)

**Engineering design docs**:
- [`docs/ARCH-001-architecture.md`](docs/ARCH-001-architecture.md) — modules, data flow, deployment, cross-cutting concerns (1/5)
- [`docs/DESIGN-001-detailed-design.md`](docs/DESIGN-001-detailed-design.md) — service contracts, error matrix, config plumbing (2/5)
- [`docs/UIUX-001-design-system.md`](docs/UIUX-001-design-system.md) — design tokens, components, 8 screen specs (3/5)
- [`docs/BDD-001-behavior-scenarios.md`](docs/BDD-001-behavior-scenarios.md) — 58 Gherkin scenarios across F-1~F-10 (4/5)
- [`docs/TDD-001-testing-strategy.md`](docs/TDD-001-testing-strategy.md) — test pyramid, mock strategy, Playwright E2E, CI (5/5)

**Design mockup** (informational, not V1 production code): [`mockups/`](mockups/) — standalone React UMD prototype, codenamed 「墨痕」

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI / SQLAlchemy + Alembic / aiosqlite (D2, D16)
- **Frontend**: Next.js / React (D2)
- **Storage**: SQLite + WAL mode (D16)
- **LLM**: OpenRouter (tier-based routing) — V1 default `google/gemini-2.5-flash-lite` (D8, D9)
- **Auth**: Google OAuth 2.0 / OIDC (`drive.readonly` scope) (D5)
- **Deployment**: Docker container + `docker-compose.yml` + `fly.toml` (D15)

## Governance

This project uses the lightweight governance kit:
- [`docs/adr/DECISIONS.md`](docs/adr/DECISIONS.md) — chronological decision log
- [`docs/adr/ADR-001-system-foundation.md`](docs/adr/ADR-001-system-foundation.md) — architectural rationale (7 axes, options evaluated)
- [`CLAUDE.md`](CLAUDE.md) — Pre-Action Verification, Reversal Protocol, lessons-learned trigger rules for Claude Code sessions

## Continuous Integration

| Workflow | Triggers | What it checks |
|----------|----------|----------------|
| [`link-check.yml`](.github/workflows/link-check.yml) | PR + weekly cron | Markdown link integrity (lychee, anchor-aware) |
| [`doc-consistency.yml`](.github/workflows/doc-consistency.yml) | PR on `.md` change | F-N↔AC-N parity, D-NN cross-refs, state machine consistency, Mermaid syntax (via [`scripts/check_docs.py`](scripts/check_docs.py)) |
| [`test.yml`](.github/workflows/test.yml) | PR + push to main | Backend pytest unit/integration + ruff + mypy + no-hardcoded-models check (DESIGN-001 §5.3); Frontend vitest + tsc + eslint + no-provider-specific-state check (TDD-001 §5.4); Playwright E2E gated behind unit tests. Auto-skips jobs whose target directory does not yet exist. |

[`.github/dependabot.yml`](.github/dependabot.yml) keeps GitHub Actions, Python, and npm dependencies current (weekly).

[`.pre-commit-config.yaml`](.pre-commit-config.yaml) provides matching local hooks. Install once with `pre-commit install`.

## Local link check

```bash
lychee --config lychee.toml --offline --include-fragments \
  --exclude-path '\.claude/' './*.md' './docs/**/*.md'
```
