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

### D-2026-05-10-01 Adopt governance kit (DECISIONS.md + protocols + link-check CI)
- **Decision**: Install governance kit from `code-agent-skill-command/templates/governance-kit/`. Establishes 三層決策治理 (ADR / DECISIONS.md / commit), Pre-Action Verification, Reversal Protocol, Sub-Agent Verification, plus lychee two-stage markdown link CI.
- **Rationale**: Project is greenfield; cheaper to install governance now than retrofit after design pivots accumulate. Lychee CI specifically chosen for `--include-fragments` anchor validation (the main reason over alternatives like markdown-link-check).
- **Files**: `docs/adr/DECISIONS.md`, `.github/workflows/link-check.yml`, `lychee.toml`, `.lycheeignore`, `.gitignore`, `CLAUDE.md`, `README.md`
- **Commit**: _fill after first commit_

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
