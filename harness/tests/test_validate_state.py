"""Behavioral tests for the on-demand state-structure validator.

validate_state.py is a thin CLI wrapper around check_state_structure() in
handback_validation.py: it reads a state file, hands its lines to the pure
validator, and owns the fail-closed exit policy -- exit 0 with an "OK: ..."
line on stdout when the file is well-formed; exit 1 with one
"FAIL state: <detail>" line per finding on stderr; exit 2 with a usage line
on a missing argument. The structure it enforces is a lockstep contract with
harness/templates/state_schema.md. Each test names the malformation it catches;
the control test proves the validator does not false-fail a well-formed file.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import HARNESS_ROOT

VALIDATE_STATE = HARNESS_ROOT / "harness" / "scripts" / "validate_state.py"

# A minimal WELL-FORMED state file: the seven sections in fixed order, a
# ## Established table with two rows in strictly-decreasing E-ID order (five
# cells each), a 5-column ## Open table, and a counter that exceeds the highest
# E-ID. Every malformation test below mutates a COPY of this constant.
WELL_FORMED = """# Orchestration State: example-plan

Status: ACTIVE

## Objective

Do the thing. Acceptance: the thing is done.

## Established

| ID | Statement | Provenance | Disposition | Revisit trigger |
|---|---|---|---|---|
| E002 | Beta decision here. | `reported` | `settled` | If re-opened. |
| E001 | Alpha fact here. | `measured` | `fact` | - |

## Open

| Question | Blocks | Cost to resolve | Who can resolve | Status |
|---|---|---|---|---|
| An open question? | Next step. | Low. | The user. | open |

## Next

One committed session.

## Maybe

- (GUESS) a candidate -- trigger: something becomes true.

## Dispatched

| Session | Prompt path | Handback path | Status |
|---|---|---|---|

## Orchestrator log

- Incarnations: 1
- Next row ID: E003
"""


class ValidateStateEnv(unittest.TestCase):
    """Writes a state fixture to a tempfile and runs validate_state.py on it."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.state = Path(self._tmpdir.name) / "example-plan_state.md"

    def run_validator(self, text):
        self.state.write_text(text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(VALIDATE_STATE), str(self.state)],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def assert_valid(self, text):
        r = self.run_validator(text)
        self.assertEqual(
            0, r.returncode,
            "expected exit 0; stdout={0!r} stderr={1!r}".format(
                r.stdout, r.stderr),
        )
        self.assertIn("OK:", r.stdout)
        self.assertEqual(
            "", r.stderr,
            "a valid state file must print nothing to stderr; got {0!r}".format(
                r.stderr),
        )
        return r

    def assert_fails(self, text, needle):
        r = self.run_validator(text)
        self.assertEqual(
            1, r.returncode,
            "expected exit 1; stdout={0!r} stderr={1!r}".format(
                r.stdout, r.stderr),
        )
        self.assertIn(
            "FAIL state:", r.stderr,
            "expected a 'FAIL state:' line on stderr; got {0!r}".format(
                r.stderr),
        )
        self.assertIn(
            needle, r.stderr,
            "expected {0!r} on stderr; got {1!r}".format(needle, r.stderr),
        )
        return r


class TestWellFormedControl(ValidateStateEnv):

    def test_well_formed_state_validates(self):
        # The control: proves the validator does not false-fail a file that
        # satisfies all five structure checks (no OK => every mutation test
        # below would be meaningless).
        self.assert_valid(WELL_FORMED)


class TestMalformations(ValidateStateEnv):

    def test_missing_section_maybe_fails(self):
        # Prevents: a state file silently dropping a required section.
        doc = WELL_FORMED.replace(
            "## Maybe\n\n- (GUESS) a candidate -- trigger: something becomes "
            "true.\n\n",
            "",
        )
        self.assert_fails(
            doc, "required section heading '## Maybe' is missing")

    def test_sections_out_of_order_fails(self):
        # Prevents: the seven sections appearing in the wrong order. Swap the
        # ## Next and ## Maybe headings (bodies stay put) via a sentinel.
        doc = (
            WELL_FORMED.replace("## Next", "@@SENTINEL@@")
            .replace("## Maybe", "## Next")
            .replace("@@SENTINEL@@", "## Maybe")
        )
        self.assert_fails(doc, "sections are out of order")

    def test_duplicate_eid_fails(self):
        # Prevents: two ## Established rows sharing an E-ID. (Equal IDs also
        # break the strictly-decreasing check; we assert the duplicate line.)
        doc = WELL_FORMED.replace(
            "| E001 | Alpha fact here.", "| E002 | Alpha fact here.")
        self.assert_fails(doc, "duplicate E-ID E002")

    def test_non_decreasing_eid_order_fails(self):
        # Prevents: ## Established rows not running newest-at-the-top. Swap the
        # two rows so E001 sits above E002.
        doc = WELL_FORMED.replace(
            "| E002 | Beta decision here. | `reported` | `settled` "
            "| If re-opened. |\n"
            "| E001 | Alpha fact here. | `measured` | `fact` | - |",
            "| E001 | Alpha fact here. | `measured` | `fact` | - |\n"
            "| E002 | Beta decision here. | `reported` | `settled` "
            "| If re-opened. |",
        )
        self.assert_fails(doc, "E001 is not strictly greater than E002")

    def test_counter_not_exceeding_highest_eid_fails(self):
        # Prevents: a stale/bad '- Next row ID:' counter that would re-issue a
        # live E-ID. Point it below the highest E-ID (E002).
        doc = WELL_FORMED.replace(
            "- Next row ID: E003", "- Next row ID: E001")
        self.assert_fails(
            doc, "counter E001 does not exceed the highest E-ID E002")

    def test_embedded_pipe_in_established_cell_fails(self):
        # Prevents: a literal pipe in a cell silently reshaping the row (a row
        # that splits into more than five cells).
        doc = WELL_FORMED.replace(
            "Beta decision here.", "Beta | decision here.")
        self.assert_fails(doc, "splits into 6 cells")


class TestUsage(ValidateStateEnv):

    def test_missing_argument_exits_2(self):
        # Prevents: an argument-less invocation exiting as if the (absent) file
        # were valid or as a structure failure.
        r = subprocess.run(
            [sys.executable, str(VALIDATE_STATE)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            2, r.returncode,
            "expected exit 2; stdout={0!r} stderr={1!r}".format(
                r.stdout, r.stderr),
        )
        self.assertIn("Usage:", r.stdout)
        self.assertIn("validate_state.py", r.stdout)


if __name__ == "__main__":
    unittest.main()
