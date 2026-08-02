"""Behavioral tests for harness/scripts/validate_prompt.py.

Checks under test: (1) template-emitted @-references resolve on disk;
(2) no leftover [PLACEHOLDER] / bracketed instruction text; (3) required
template sections present; (4) resolved-git-parameter branch-name sanity.
Failure contract: nonzero exit, one "FAIL <check>: <detail>" line each.

Exemptions pinned by the passing fixture: inline code spans, fenced code
blocks, and section 10 (verbatim-injected learnings) are never scanned for
@-references or placeholder residue; checkbox lines ("- [ ]") are not
placeholder residue.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import VALIDATE_PROMPT

VALID_PROMPT = """# Session Prompt: Phase 4 -- Fixture Phase

**Project:** fixture project
**Plan:** example-plan
**Phase:** 4 of 8
**Generated:** 2026-08-02

---

## 1. Before You Start -- Read These in Full

- @CLAUDE.md
- @docs/prds/example-plan_prd.md
- @docs/multi_phase_plans/example-plan_plan.md (focus on the Phase 4 section)

---

## 2. Project Overview

A fixture project overview.

---

## 3. Current Codebase State

- `src/thing.py` -- a file.

---

## 4. Phase Objective

Do the fixture work.

---

## 5. Deliverables

- A deliverable. Residue like `[PLACEHOLDER]` inside an inline code span is
  exempt by design.

---

## 6. Definition of Done

- [ ] A checkbox line is not placeholder residue.

---

## 7. Verification

### Automated -- run these and confirm all pass:

```bash
python3 -m unittest discover .claude/harness/tests
grep -n "@nonexistent/path.md in a fenced block is exempt" file.md
```

### Human

- A human check.

---

## 8. Constraints

- Environment: follow the keys of @.claude/preferences.md.

---

## 9. Resolved Parameters

- plan_name: example-plan -- phase 04 of 8
- is_first_phase: false -- is_final_phase: false
- integration branch: integration/example-plan; phase branch:
  example-plan-phase-04; commit message: "feat: example-plan phase 4 -- x";
  merge message: "merge: example-plan phase 4 -- x"
- Learnings path: docs/learnings/<DDMMYY>/example-plan_phase_04_learnings.md
- Verification case: D -- live mechanism sanity check

---

## 10. Accumulated Learnings from Prior Phases

- Verbatim learnings may contain @unresolvable/tokens.md and bracketed text
  like [If this were template residue it would fail] -- section 10 is exempt.

---

## 11. End of Phase -- Closing Sequence

Follow @.claude/harness/procedures/closing_sequence.md end to end.
"""


class ValidatePromptEnv(unittest.TestCase):
    """Builds a temp project root holding every @-target the fixture cites."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)
        for rel in [
            "CLAUDE.md",
            "docs/prds/example-plan_prd.md",
            "docs/multi_phase_plans/example-plan_plan.md",
            ".claude/preferences.md",
            ".claude/harness/procedures/closing_sequence.md",
        ]:
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("fixture target\n", encoding="utf-8")
        self.prompt_path = self.root / "docs" / "prompts" / "fixture_prompt.md"
        self.prompt_path.parent.mkdir(parents=True, exist_ok=True)

    def write_prompt(self, text=VALID_PROMPT):
        self.prompt_path.write_text(text, encoding="utf-8")

    def run_validator(self):
        return subprocess.run(
            [sys.executable, str(VALIDATE_PROMPT), str(self.prompt_path)],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def assert_green(self):
        r = self.run_validator()
        self.assertEqual(
            0, r.returncode,
            "expected exit 0; stdout={0!r} stderr={1!r}".format(
                r.stdout, r.stderr
            ),
        )
        self.assertNotIn("FAIL", r.stdout)
        return r

    def assert_fails(self, check, detail_contains=None):
        r = self.run_validator()
        self.assertNotEqual(
            0, r.returncode,
            "expected nonzero exit; stdout={0!r}".format(r.stdout),
        )
        needle = "FAIL {0}:".format(check)
        self.assertIn(
            needle, r.stdout,
            "expected a {0!r} line; stdout={1!r}".format(needle, r.stdout),
        )
        if detail_contains is not None:
            fail_lines = [
                l for l in r.stdout.splitlines() if l.startswith(needle)
            ]
            self.assertTrue(
                any(detail_contains in l for l in fail_lines),
                "no {0!r} line contains {1!r}; got {2!r}".format(
                    needle, detail_contains, fail_lines
                ),
            )
        return r


class TestAtRefs(ValidatePromptEnv):
    def test_at_refs_resolve(self):
        self.write_prompt()
        self.assert_green()

    def test_missing_at_ref_fails(self):
        (self.root / "docs/prds/example-plan_prd.md").unlink()
        self.write_prompt()
        self.assert_fails("at-ref", "docs/prds/example-plan_prd.md")


class TestPlaceholderResidue(ValidatePromptEnv):
    def test_placeholder_residue_fails(self):
        # Literal [PLACEHOLDER] outside any code span.
        self.write_prompt(
            VALID_PROMPT.replace(
                "- A deliverable.",
                "- A deliverable with [PLACEHOLDER] residue.",
            )
        )
        self.assert_fails("placeholder", "[PLACEHOLDER]")

        # Bracketed template instruction text.
        self.write_prompt(
            VALID_PROMPT.replace(
                "Do the fixture work.",
                "[Verbatim from the plan.]",
            )
        )
        self.assert_fails("placeholder", "[Verbatim from the plan.]")


class TestRequiredSections(ValidatePromptEnv):
    def test_required_sections_present(self):
        self.write_prompt(
            VALID_PROMPT.replace("## 6. Definition of Done", "## Done stuff")
        )
        self.assert_fails("sections", "6")


class TestBranchNameSanity(ValidatePromptEnv):
    def test_branch_name_sanity(self):
        # Phase branch not zero-padded.
        self.write_prompt(
            VALID_PROMPT.replace(
                "example-plan-phase-04;", "example-plan-phase-4;"
            )
        )
        self.assert_fails("branch-sanity")

        # Integration branch names a different slug.
        self.write_prompt(
            VALID_PROMPT.replace(
                "integration branch: integration/example-plan;",
                "integration branch: integration/other-plan;",
            )
        )
        self.assert_fails("branch-sanity")

        # Phase number exceeds the total.
        self.write_prompt(
            VALID_PROMPT.replace(
                "phase 04 of 8", "phase 09 of 8"
            ).replace(
                "example-plan-phase-04;", "example-plan-phase-09;"
            )
        )
        self.assert_fails("branch-sanity")


class TestFailReportFormat(ValidatePromptEnv):
    def test_fail_report_format(self):
        (self.root / "CLAUDE.md").unlink()
        self.write_prompt(
            VALID_PROMPT.replace(
                "Do the fixture work.", "[Verbatim from the plan.]"
            )
        )
        r = self.run_validator()
        self.assertNotEqual(0, r.returncode)
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        self.assertTrue(lines, "failing run must print FAIL lines")
        for line in lines:
            self.assertRegex(
                line, r"^FAIL [a-z-]+: .+",
                "every failure line must be 'FAIL <check>: <detail>'",
            )
        # Both independent findings are reported (one line per finding).
        self.assertTrue(any(l.startswith("FAIL at-ref:") for l in lines))
        self.assertTrue(any(l.startswith("FAIL placeholder:") for l in lines))
