# teacher-comments

[![Markdown Link Check](https://github.com/galaxyh/teacher-comments/actions/workflows/link-check.yml/badge.svg)](https://github.com/galaxyh/teacher-comments/actions/workflows/link-check.yml)

> Newly initialized project. Tech stack and scope to be decided.

## Governance

This project uses the lightweight governance kit:

- [`docs/adr/DECISIONS.md`](docs/adr/DECISIONS.md) — chronological decision log
- [`CLAUDE.md`](CLAUDE.md) — Pre-Action Verification, Reversal Protocol, and lessons-learned trigger rules for Claude Code sessions
- [`.github/workflows/link-check.yml`](.github/workflows/link-check.yml) — markdown link CI (PR offline check + weekly full check)

## Local link check

```bash
lychee --config lychee.toml --offline --include-fragments \
  --exclude-path '\.claude/' './*.md' './docs/**/*.md'
```
