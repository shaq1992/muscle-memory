"""Behavioral tests for the one-shot state-schema v2 migration script.

migrate_state_v2.py stamps immutable row IDs (E + 3 digits) onto every
## Established row of an orchestrated plan's state file and appends the v2
## Orchestrator log section carrying the ID counter. Each test names the
failure it prevents.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import HARNESS_ROOT

MIGRATE = HARNESS_ROOT / "harness" / "scripts" / "migrate_state_v2.py"

V1_HEADER = "| Statement | Provenance | Disposition | Revisit trigger |"
V2_HEADER = "| ID | Statement | Provenance | Disposition | Revisit trigger |"
V2_SEP = "|---|---|---|---|---|"

# A v1 state file mirroring the live files' shape: blank lines between some
# Established rows, and OTHER sections carrying their own tables that the
# migration must never touch.
V1_DOC = """# Orchestration State: example-plan

Status: ACTIVE

## Objective

Do the thing. Acceptance: the thing is done.

## Established

| Statement | Provenance | Disposition | Revisit trigger |
|---|---|---|---|
| First fact about the system. | `measured` | `fact` | - |
| A settled decision with a `code span` in it. | `reported` | `settled` | If re-opened. |

| An invariant row after a blank line. | `inferred` | `invariant` | - |

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
| 01 | docs/prompts/x.md | docs/orchestration/example-plan/handbacks/01.md | outstanding |
"""


def run_migrate(path, *extra):
    return subprocess.run(
        [sys.executable, str(MIGRATE), str(path)] + list(extra),
        capture_output=True,
        text=True,
        timeout=30,
    )


class MigrateEnv(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.state = Path(self._tmpdir.name) / "example-plan_state.md"

    def write(self, text=V1_DOC):
        self.state.write_text(text, encoding="utf-8")

    def read(self):
        return self.state.read_text(encoding="utf-8")


class TestStampsIdsInOrder(MigrateEnv):
    def test_stamps_ids_in_table_order(self):
        # Prevents: rows entering v2 without stable IDs, or IDs out of order.
        self.write()
        r = run_migrate(self.state)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        text = self.read()
        self.assertIn("| E001 | First fact about the system.", text)
        self.assertIn("| E002 | A settled decision", text)
        self.assertIn("| E003 | An invariant row after a blank line.", text)

    def test_header_and_separator_rewritten(self):
        # Prevents: a malformed 4/5-column mix that positional readers misparse.
        self.write()
        run_migrate(self.state)
        text = self.read()
        self.assertIn(V2_HEADER, text)
        self.assertIn(V2_SEP, text)
        # whole-line check: V1's header is a substring of V2's, so assertNotIn
        # on the raw text would always fail
        self.assertNotIn(V1_HEADER, text.splitlines())


class TestIdempotent(MigrateEnv):
    def test_second_run_is_byte_identical_noop(self):
        # Prevents: restamping/renumbering, which would break ID immutability.
        self.write()
        run_migrate(self.state)
        first = self.read()
        r = run_migrate(self.state)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual(first, self.read())
        self.assertIn("already", r.stdout.lower())


class TestOrchestratorLog(MigrateEnv):
    def test_appends_log_with_counter(self):
        # Prevents: ID reissue after a later trim (counter must outlive rows).
        self.write()
        run_migrate(self.state)
        text = self.read()
        self.assertIn("## Orchestrator log", text)
        self.assertIn("Incarnations: 1", text)
        self.assertIn("Next row ID: E004", text)
        # the section sits LAST, after ## Dispatched
        self.assertGreater(
            text.index("## Orchestrator log"), text.index("## Dispatched")
        )


class TestContentPreserved(MigrateEnv):
    def test_only_id_column_and_log_section_change(self):
        # Prevents: content corruption of the live, untracked state files.
        self.write()
        run_migrate(self.state)
        text = self.read()
        # every original line is preserved verbatim except the Established
        # table header, separator and data rows (which gain a leading cell)
        for line in V1_DOC.splitlines():
            if line.startswith("|") and V1_DOC.splitlines().index(line) < 20:
                continue  # Established table lines: transformed by design
            self.assertIn(line, text)
        # other sections' tables are untouched -- no stray IDs
        self.assertIn("| An open question? |", text)
        self.assertIn("| 01 | docs/prompts/x.md", text)
        self.assertNotIn("| E004", text)


class TestPartialStamping(MigrateEnv):
    def test_continues_from_recorded_counter(self):
        # Prevents: ID collision when new rows join an already-stamped file.
        self.write()
        run_migrate(self.state)
        # simulate the orchestrator appending a new (unstamped) row later
        text = self.read()
        text = text.replace(
            "## Open",
            "| A brand new fact. | `measured` | `fact` | - |\n\n## Open",
            1,
        )
        self.state.write_text(text, encoding="utf-8")
        r = run_migrate(self.state)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        out = self.read()
        self.assertIn("| E004 | A brand new fact.", out)
        self.assertIn("Next row ID: E005", out)
        # existing IDs unchanged
        self.assertIn("| E001 | First fact", out)


class TestFailsClosed(MigrateEnv):
    def test_missing_established_fails_without_writing(self):
        # Prevents: a half-migrated file passing as done.
        broken = V1_DOC.replace("## Established", "## Wrong heading")
        self.write(broken)
        r = run_migrate(self.state)
        self.assertEqual(1, r.returncode)
        self.assertIn("FAIL", r.stdout)
        self.assertEqual(broken, self.read())

    def test_duplicate_stamped_id_fails(self):
        # Prevents: silently accepting a corrupted table with reused IDs.
        self.write()
        run_migrate(self.state)
        corrupted = self.read().replace("| E002 |", "| E001 |", 1)
        self.state.write_text(corrupted, encoding="utf-8")
        r = run_migrate(self.state)
        self.assertEqual(1, r.returncode)
        self.assertIn("FAIL", r.stdout)


class TestCheckMode(MigrateEnv):
    def test_check_reports_and_writes_nothing(self):
        # Prevents: a dry run that silently mutates.
        self.write()
        r = run_migrate(self.state, "--check")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual(V1_DOC, self.read())
        self.assertIn("3", r.stdout)  # would stamp 3 rows


if __name__ == "__main__":
    unittest.main()
