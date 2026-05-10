# teacher-comments

[![Markdown Link Check](https://github.com/galaxyh/teacher-comments/actions/workflows/link-check.yml/badge.svg)](https://github.com/galaxyh/teacher-comments/actions/workflows/link-check.yml)

> 教師評語系統 — 基於 Google Drive 教學素材自動產生 300-500 字學期評語的單人 SaaS 工具。
> 設計給中小學個人教師：以教師「評價種子 + 個人觀察」為核心，AI 僅輔助整合素材、產出初稿。

## Status

**Stage**: Spec freeze — V1 implementation kickoff
- Full requirements: [`docs/PRD.md`](docs/PRD.md) (v0.2, 17 locked decisions)
- Decision log: [`docs/adr/DECISIONS.md`](docs/adr/DECISIONS.md)

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
- [`CLAUDE.md`](CLAUDE.md) — Pre-Action Verification, Reversal Protocol, lessons-learned trigger rules for Claude Code sessions
- [`.github/workflows/link-check.yml`](.github/workflows/link-check.yml) — markdown link CI (PR offline check + weekly full check)

## Local link check

```bash
lychee --config lychee.toml --offline --include-fragments \
  --exclude-path '\.claude/' './*.md' './docs/**/*.md'
```
