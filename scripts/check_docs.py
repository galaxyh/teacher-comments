#!/usr/bin/env python3
"""Cross-doc consistency checks for the teacher-comments project.

Runs in CI on every PR touching .md files. Catches the kind of "ripple-effect
drift" bugs that surfaced in PRD v0.1 → v0.2 review (e.g., AC-10 saying "5 項"
when F-10 listed 6).

Checks performed:
  C1. F-N count == AC-N count in PRD
  C2. All D-NN short refs (D1, D2, ..., D17) used in PRD/ADR/DESIGN are defined
      in PRD §2 (the canonical decision table)
  C3. All D-YYYY-MM-DD-NN long refs used anywhere are defined in DECISIONS.md
  C4. State machine consistency: PRD §4.3 mermaid diagram and DESIGN-001 §3
      table list the same set of states (no drift after D-04 unprocessable add)
  C5. Mermaid blocks have minimal valid syntax (open with known directive)
  C6. No remaining `_fill after commit_` placeholders in DECISIONS.md
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# Files that participate in cross-ref checks
PRD = DOCS / "PRD.md"
ARCH = DOCS / "ARCH-001-architecture.md"
DESIGN = DOCS / "DESIGN-001-detailed-design.md"
UIUX = DOCS / "UIUX-001-design-system.md"
BDD = DOCS / "BDD-001-behavior-scenarios.md"
TDD = DOCS / "TDD-001-testing-strategy.md"
ADR_001 = DOCS / "adr" / "ADR-001-system-foundation.md"
DECISIONS = DOCS / "adr" / "DECISIONS.md"

ALL_DOCS = [PRD, ARCH, DESIGN, UIUX, BDD, TDD, ADR_001, DECISIONS]

VALID_MERMAID_DIRECTIVES = {
    "graph",
    "flowchart",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "erDiagram",
    "journey",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
}


class CheckError(Exception):
    pass


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Check C1: F-N count == AC-N count in PRD
# ─────────────────────────────────────────────────────────────────────────────


def check_f_ac_parity() -> list[str]:
    text = read(PRD)
    f_headings = re.findall(r"^### F-(\d+)", text, flags=re.MULTILINE)
    ac_rows = re.findall(r"^\| \*\*AC-(\d+)\*\*", text, flags=re.MULTILINE)
    errors = []
    f_set, ac_set = set(f_headings), set(ac_rows)
    if f_set != ac_set:
        missing_ac = f_set - ac_set
        missing_f = ac_set - f_set
        if missing_ac:
            errors.append(
                f"C1: F-N entries without matching AC: F-{sorted(missing_ac)}"
            )
        if missing_f:
            errors.append(
                f"C1: AC-N entries without matching F: AC-{sorted(missing_f)}"
            )
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Check C2: D-NN short refs (D1..D17) all defined in PRD §2
# ─────────────────────────────────────────────────────────────────────────────


def check_short_d_refs() -> list[str]:
    prd = read(PRD)
    # Locked decisions table rows: lines starting with "| **D{N}** |"
    defined_short = set(
        m.group(1) for m in re.finditer(r"^\| \*\*(D\d+)\*\*", prd, flags=re.MULTILINE)
    )
    errors = []

    # Files where short D refs MAY appear (PRD itself, ADR-001, DESIGN-001, UIUX-001)
    refs_check_files = [PRD, ARCH, DESIGN, UIUX, BDD, TDD, ADR_001]
    pattern = re.compile(r"\bD(\d{1,2})\b")
    for path in refs_check_files:
        text = read(path)
        # Filter false positives: D after letters (e.g., "D-2026-...", "RFD3D2"),
        # numbers (3D), or in code blocks. Quick heuristic.
        used = set()
        for m in pattern.finditer(text):
            start = m.start()
            # Skip if part of D-NNNN-... long ref
            if start + len(m.group(0)) < len(text) and text[start + len(m.group(0))] == "-":
                continue
            # Skip if preceded by alphanumeric
            if start > 0 and text[start - 1].isalnum():
                continue
            ref = "D" + m.group(1)
            used.add(ref)

        missing = used - defined_short
        # Filter likely false positives: D0, D18+, D9999
        missing = {r for r in missing if 1 <= int(r[1:]) <= 99}
        if missing:
            # Only flag if these aren't defined in PRD
            real_missing = missing - defined_short
            if real_missing:
                errors.append(
                    f"C2: {path.relative_to(ROOT)} references undefined short D refs: "
                    f"{sorted(real_missing)}"
                )
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Check C3: All D-YYYY-MM-DD-NN long refs are defined in DECISIONS.md
# ─────────────────────────────────────────────────────────────────────────────


def check_long_d_refs() -> list[str]:
    decisions_text = read(DECISIONS)
    defined_long = set(
        re.findall(r"^### (D-\d{4}-\d{2}-\d{2}-\d+)", decisions_text, flags=re.MULTILINE)
    )
    errors = []
    pattern = re.compile(r"D-\d{4}-\d{2}-\d{2}-\d+")
    for path in ALL_DOCS:
        text = read(path)
        used = set(pattern.findall(text))
        missing = used - defined_long
        if missing:
            errors.append(
                f"C3: {path.relative_to(ROOT)} references undefined long D refs: "
                f"{sorted(missing)}"
            )
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Check C4: State machine consistency between PRD §4.3 and DESIGN-001 §3
# ─────────────────────────────────────────────────────────────────────────────

# Canonical V1 states (after D-2026-05-10-04 unprocessable addition)
EXPECTED_STATES = {
    "pending",
    "processing",
    "processed",
    "teacher_edited",
    "reprocess_pending",
    "failed",
    "unprocessable",
}


def check_state_machine_consistency() -> list[str]:
    errors = []
    # Extract from PRD §4.3 — find the state machine mermaid block
    prd_text = read(PRD)
    prd_state_section = re.search(
        r"### 4\.3.+?###",
        prd_text,
        flags=re.DOTALL,
    )
    if not prd_state_section:
        errors.append("C4: PRD §4.3 not found")
        return errors

    section_text = prd_state_section.group(0)
    # Find tokens used in transitions (left or right of -->)
    prd_states = set(re.findall(r"\b([a-z_]+)\b", section_text))
    prd_states &= EXPECTED_STATES  # keep only known state names

    if prd_states != EXPECTED_STATES:
        missing = EXPECTED_STATES - prd_states
        if missing:
            errors.append(
                f"C4: PRD §4.3 state machine missing states: {sorted(missing)}"
            )

    # Extract from DESIGN-001 §3
    design_text = read(DESIGN)
    design_section = re.search(r"## 3\..+?## 4\.", design_text, flags=re.DOTALL)
    if design_section:
        section_text = design_section.group(0)
        design_states = set(re.findall(r"`([a-z_]+)`", section_text))
        design_states &= EXPECTED_STATES
        if design_states != EXPECTED_STATES:
            missing = EXPECTED_STATES - design_states
            if missing:
                errors.append(
                    f"C4: DESIGN-001 §3 state table missing states: {sorted(missing)}"
                )

    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Check C5: Mermaid blocks have valid opening directive
# ─────────────────────────────────────────────────────────────────────────────


def check_mermaid_blocks() -> list[str]:
    errors = []
    block_pattern = re.compile(r"^```mermaid\n(.+?)^```", flags=re.MULTILINE | re.DOTALL)
    for path in ALL_DOCS:
        text = read(path)
        for match in block_pattern.finditer(text):
            body = match.group(1).strip()
            first_line = body.splitlines()[0].strip() if body else ""
            # First word is the directive
            directive = first_line.split()[0] if first_line else ""
            # Strip optional theme/init prefix like "graph TD"
            if directive not in VALID_MERMAID_DIRECTIVES:
                # Allow `flowchart TD`, `graph LR`, etc. — directive is first word
                errors.append(
                    f"C5: {path.relative_to(ROOT)} has Mermaid block with unknown "
                    f"directive: {directive!r} (first line: {first_line!r})"
                )
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Check C6: No `_fill after commit_` placeholders in DECISIONS.md
# ─────────────────────────────────────────────────────────────────────────────


def check_no_unfilled_commits() -> list[str]:
    errors = []
    text = read(DECISIONS)
    # Match common variants
    bad = re.findall(r"_fill (?:after )?(?:commit|first commit)_", text)
    if bad:
        errors.append(
            f"C6: DECISIONS.md has {len(bad)} unfilled commit hash placeholders. "
            "Run `git rev-parse --short HEAD` after committing and backfill."
        )
    return errors


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    all_errors: list[str] = []
    checks = [
        ("C1 F-N/AC-N parity", check_f_ac_parity),
        ("C2 short D-ref definitions", check_short_d_refs),
        ("C3 long D-ref definitions", check_long_d_refs),
        ("C4 state machine consistency", check_state_machine_consistency),
        ("C5 Mermaid syntax", check_mermaid_blocks),
        ("C6 unfilled commit placeholders", check_no_unfilled_commits),
    ]

    print("Doc consistency checks:\n")
    for name, fn in checks:
        try:
            errors = fn()
        except Exception as e:  # noqa: BLE001
            errors = [f"{name}: check raised {type(e).__name__}: {e}"]
        if errors:
            print(f"  ✗ {name}")
            for err in errors:
                print(f"      {err}")
            all_errors.extend(errors)
        else:
            print(f"  ✓ {name}")

    print()
    if all_errors:
        print(f"FAIL: {len(all_errors)} consistency issue(s) found.")
        return 1
    print("PASS: all checks green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
