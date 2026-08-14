"""Behavioral tests for the D4 handback-ingest script.

ingest_handback.py is the orchestrator's pen for Step 9's mechanical ingest
actions: it parses a handback's Status line and ## Delta / ## Structural
observations sections, applies add/change/retire by row ID to the state
file's ## Established table (stamping ADD IDs from the ## Orchestrator log
counter), appends observation lines to docs/observations.md, updates
## Dispatched, and prints a ~10-line summary. Each test names the failure
it prevents.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import HARNESS_ROOT

INGEST = HARNESS_ROOT / "harness" / "scripts" / "ingest_handback.py"

DATE = "2026-08-14"
PLAN = "example-plan"
SESSION = "03"

STATE_DOC = """# Orchestration State: example-plan

Status: ACTIVE

## Objective

Do the thing. Acceptance: the thing is done.

## Established

| ID | Statement | Provenance | Disposition | Revisit trigger |
|---|---|---|---|---|
| E001 | Alpha fact about the system. | `measured` | `fact` | - |
| E002 | Beta decision with a `code span`. | `reported` | `settled` | If re-opened. |
| E003 | Gamma invariant holds everywhere. | `inferred` | `invariant` | - |

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
| 03 | docs/prompts/x.md | docs/orchestration/example-plan/handbacks/03.md | Dispatched 2026-08-14; outstanding. |

## Orchestrator log

- Incarnations: 1
- Next row ID: E004
"""

OBSERVATIONS_SEED = (
    "2026-08-01 | earlier-plan | - | other | a pre-existing line\n"
)

RECEIPT = (
    "**Handed to this session (read receipt):**\n"
    "- Rows: E001, E002\n"
    "- Prompt-SHA256: " + "0" * 64 + "\n"
)


def handback_text(status="COMPLETE", delta="none", obs="none",
                  advisory="- nothing to hand forward."):
    return (
        "Status: {0}\n\n{1}\n"
        "## Delta\n\n{2}\n\n"
        "## For the next session\n\n{3}\n\n"
        "## Structural observations\n\n{4}\n"
    ).format(status, RECEIPT, delta, advisory, obs)


class IngestEnv(unittest.TestCase):
    """Temp docs/ tree: state file, seeded observations, handback 03."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmp = Path(self._tmpdir.name)
        self.docs = tmp / "docs"
        self.orch = self.docs / "orchestration"
        self.handbacks = self.orch / PLAN / "handbacks"
        self.handbacks.mkdir(parents=True)
        self.state = self.orch / "{0}_state.md".format(PLAN)
        self.state.write_text(STATE_DOC, encoding="utf-8")
        self.observations = self.docs / "observations.md"
        self.observations.write_text(OBSERVATIONS_SEED, encoding="utf-8")
        self.handback = self.handbacks / "{0}.md".format(SESSION)

    def run_ingest(self, hb_text, *extra):
        self.handback.write_text(hb_text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(INGEST), "--state", str(self.state),
             str(self.handback), "--date", DATE] + list(extra),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def state_text(self):
        return self.state.read_text(encoding="utf-8")

    def obs_text(self):
        return self.observations.read_text(encoding="utf-8")

    def assert_ok(self, result):
        self.assertEqual(
            0, result.returncode,
            "expected exit 0; stdout={0!r} stderr={1!r}".format(
                result.stdout, result.stderr),
        )

    def assert_failed_untouched(self, result):
        """Exit 1 and neither the state file nor observations changed."""
        self.assertEqual(
            1, result.returncode,
            "expected exit 1; stdout={0!r} stderr={1!r}".format(
                result.stdout, result.stderr),
        )
        self.assertEqual(STATE_DOC, self.state_text(),
                         "a failed ingest must leave the state file untouched")
        self.assertEqual(OBSERVATIONS_SEED, self.obs_text(),
                         "a failed ingest must leave observations untouched")


class TestDeltaApply(IngestEnv):

    def test_add_stamps_ids_and_bumps_counter(self):
        # Prevents: ID reuse or a stale counter after an ingest.
        delta = (
            "ADD (two rows, ID cell is the orchestrator's `-` placeholder):\n"
            "| - | New fact one. | `measured` | `fact` | - |\n"
            "| - | New fact two. | `reported` | `settled` | - |"
        )
        r = self.run_ingest(handback_text(delta=delta))
        self.assert_ok(r)
        text = self.state_text()
        self.assertIn("| E004 | New fact one. | `measured` | `fact` | - |",
                      text)
        self.assertIn("| E005 | New fact two. | `reported` | `settled` | - |",
                      text)
        self.assertIn("- Next row ID: E006", text)
        self.assertNotIn("- Next row ID: E004", text)
        self.assertIn("E004", r.stdout)
        # New rows land inside ## Established, before ## Open.
        self.assertLess(text.index("New fact two."), text.index("## Open"))

    def test_change_replaces_row_and_keeps_id(self):
        # Prevents: a change silently re-keying or duplicating a row.
        delta = (
            "CHANGE (row E002 -- refined):\n"
            "| E002 | Beta decision, refined wording. | `reported` "
            "| `settled` | If re-opened. |"
        )
        r = self.run_ingest(handback_text(delta=delta))
        self.assert_ok(r)
        text = self.state_text()
        self.assertIn("Beta decision, refined wording.", text)
        self.assertNotIn("Beta decision with a `code span`.", text)
        self.assertEqual(1, text.count("| E002 |"))
        # Order preserved: E002 still sits between E001 and E003.
        self.assertLess(text.index("| E001 |"), text.index("| E002 |"))
        self.assertLess(text.index("| E002 |"), text.index("| E003 |"))
        self.assertIn("- Next row ID: E004", text)

    def test_retire_hard_deletes_and_summary_names_ids(self):
        # Prevents: tombstone clutter, counter drift, or an unnamed deletion.
        delta = "RETIRE (E001): superseded by the refined beta row."
        r = self.run_ingest(handback_text(delta=delta))
        self.assert_ok(r)
        text = self.state_text()
        self.assertNotIn("| E001 |", text)
        self.assertNotIn("Alpha fact", text)
        self.assertIn("| E002 |", text)
        self.assertIn("- Next row ID: E004", text)
        self.assertIn("E001", r.stdout)

    def test_retire_ids_in_reason_are_ignored(self):
        # Prevents: an ID mentioned in the free-text reason being deleted.
        delta = "RETIRE (E001): superseded by E003 which stays."
        r = self.run_ingest(handback_text(delta=delta))
        self.assert_ok(r)
        text = self.state_text()
        self.assertNotIn("| E001 |", text)
        self.assertIn("| E003 |", text)

    def test_handback02_on_disk_shape_parses(self):
        # Prevents: a grammar that breaks the existing handback corpus (02).
        delta = (
            "ADD (one row, ID cell is the orchestrator's `-` placeholder):\n"
            "| - | D-something shipped (session 02, merge abc123): details. "
            "| `measured` | `fact` | - |\n"
            "\n"
            "CHANGE (row E002 -- test-count sentence only; quote of the "
            "current tail: \"with a `code span`.\"):\n"
            "| E002 | Beta decision with an amended tail. | `reported` "
            "| `settled` | If re-opened. |"
        )
        r = self.run_ingest(handback_text(delta=delta))
        self.assert_ok(r)
        text = self.state_text()
        self.assertIn("| E004 | D-something shipped", text)
        self.assertIn("Beta decision with an amended tail.", text)


class TestFailClosed(IngestEnv):

    def test_unmarked_delta_row_fails_closed(self):
        # Prevents: a half-applied ingest from an ambiguous delta.
        delta = "| - | A row with no marker line above it. | `measured` | `fact` | - |"
        self.assert_failed_untouched(self.run_ingest(handback_text(delta=delta)))

    def test_prose_line_in_delta_fails_closed(self):
        # Prevents: silently skipping content the script cannot classify
        # (handback 01's legacy prose shape is exactly this).
        delta = (
            "All rows are ADD, written in the v1 table shape.\n"
            "| A legacy ID-less row. | `measured` | `fact` | - |"
        )
        self.assert_failed_untouched(self.run_ingest(handback_text(delta=delta)))

    def test_change_on_missing_id_fails_closed(self):
        # Prevents: applying a delta to a row that does not exist.
        delta = (
            "CHANGE (row E099):\n"
            "| E099 | No such row. | `measured` | `fact` | - |"
        )
        self.assert_failed_untouched(self.run_ingest(handback_text(delta=delta)))

    def test_retire_on_missing_id_fails_closed(self):
        # Prevents: a retire silently doing nothing on a typo'd ID.
        delta = "RETIRE (E099): no such row."
        self.assert_failed_untouched(self.run_ingest(handback_text(delta=delta)))

    def test_add_row_with_nonplaceholder_id_fails_closed(self):
        # Prevents: a session pre-stamping its own IDs (counter is the
        # orchestrator's alone).
        delta = (
            "ADD (one row):\n"
            "| E050 | A row that names its own ID. | `measured` | `fact` | - |"
        )
        self.assert_failed_untouched(self.run_ingest(handback_text(delta=delta)))

    def test_change_and_retire_same_id_fails_closed(self):
        # Prevents: an ambiguous delta applying in file order by accident.
        delta = (
            "CHANGE (row E002):\n"
            "| E002 | Changed beta. | `reported` | `settled` | - |\n"
            "\n"
            "RETIRE (E002): also retired."
        )
        self.assert_failed_untouched(self.run_ingest(handback_text(delta=delta)))

    def test_complete_without_delta_section_fails_closed(self):
        # Prevents: a malformed terminal handback being half-ingested.
        hb = (
            "Status: COMPLETE\n\n" + RECEIPT +
            "\n## For the next session\n\nnothing\n\n"
            "## Structural observations\n\nnone\n"
        )
        self.assert_failed_untouched(self.run_ingest(hb))

    def test_bad_status_value_fails_closed(self):
        # Prevents: an open-ended Status vocabulary.
        self.assert_failed_untouched(self.run_ingest(handback_text(status="DONE")))


class TestFlagsAndWarnings(IngestEnv):

    def test_exact_duplicate_statement_flagged_not_resolved(self):
        # Prevents: silent duplicate accumulation AND silent resolution --
        # the script flags, the orchestrator judges.
        delta = (
            "ADD (one row):\n"
            "| - | Alpha fact about the system. | `measured` | `fact` | - |"
        )
        r = self.run_ingest(handback_text(delta=delta))
        self.assert_ok(r)
        self.assertIn("FLAG", r.stdout)
        self.assertIn("E001", r.stdout)
        # Still applied: resolution is the orchestrator's judgement.
        self.assertIn("| E004 | Alpha fact about the system.",
                      self.state_text())

    def test_overlong_incoming_row_warns_and_applies(self):
        # Prevents: a hard-block D7 that was never ratified (warn, never block).
        long_statement = "Very long statement. " * 40  # ~840 bytes
        delta = (
            "ADD (one row):\n"
            "| - | {0} | `measured` | `fact` | - |".format(long_statement.strip())
        )
        r = self.run_ingest(handback_text(delta=delta))
        self.assert_ok(r)
        self.assertIn("WARN", r.stdout)
        self.assertIn("600", r.stdout)
        self.assertIn("| E004 |", self.state_text())

    def test_threshold_trips_on_row_count(self):
        # Prevents: the GC trigger never firing on the row bound.
        rows = "\n".join(
            "| E{0:03d} | Fact number {0}. | `measured` | `fact` | - |".format(n)
            for n in range(1, 82)
        )
        doc = STATE_DOC.replace(
            "| E001 | Alpha fact about the system. | `measured` | `fact` | - |\n"
            "| E002 | Beta decision with a `code span`. | `reported` | `settled` | If re-opened. |\n"
            "| E003 | Gamma invariant holds everywhere. | `inferred` | `invariant` | - |",
            rows,
        ).replace("- Next row ID: E004", "- Next row ID: E082")
        self.state.write_text(doc, encoding="utf-8")
        r = self.run_ingest(handback_text())
        self.assert_ok(r)
        self.assertIn("OVER", r.stdout)
        self.assertIn("81", r.stdout)

    def test_threshold_trips_on_byte_size(self):
        # Prevents: the GC trigger never firing on the byte bound.
        huge = "x" * 50000
        doc = STATE_DOC.replace("Alpha fact about the system.", huge)
        self.state.write_text(doc, encoding="utf-8")
        r = self.run_ingest(handback_text())
        self.assert_ok(r)
        self.assertIn("OVER", r.stdout)

    def test_within_threshold_reports_ok(self):
        # Prevents: a threshold report that cries wolf on a healthy file.
        r = self.run_ingest(handback_text())
        self.assert_ok(r)
        self.assertIn("3 rows", r.stdout)
        self.assertNotIn("OVER", r.stdout)


class TestObservations(IngestEnv):

    def test_observation_appends_in_fixed_shape(self):
        # Prevents: shape drift in the append-only observations file.
        obs = "- prompt-underspecified | the prompt omitted the test path"
        r = self.run_ingest(handback_text(obs=obs))
        self.assert_ok(r)
        expected = (
            OBSERVATIONS_SEED +
            "2026-08-14 | example-plan | 03 | prompt-underspecified "
            "| the prompt omitted the test path\n"
        )
        self.assertEqual(expected, self.obs_text())

    def test_observations_none_appends_nothing(self):
        # Prevents: fabricated filler lines in the observations file.
        r = self.run_ingest(handback_text(obs="none"))
        self.assert_ok(r)
        self.assertEqual(OBSERVATIONS_SEED, self.obs_text())

    def test_unknown_observation_tag_fails_closed(self):
        # Prevents: erosion of the closed tag vocabulary.
        obs = "- bogus-tag | not a real tag"
        self.assert_failed_untouched(self.run_ingest(handback_text(obs=obs)))


class TestDispatchedTransitions(IngestEnv):

    def test_complete_clears_dispatched_row(self):
        # Prevents: a finished session lingering as an outstanding expectation.
        r = self.run_ingest(handback_text(status="COMPLETE"))
        self.assert_ok(r)
        self.assertNotIn("| 03 |", self.state_text())

    def test_partial_updates_dispatched_status(self):
        # Prevents: a partial return reading as still-outstanding on resume.
        delta = (
            "ADD (one row):\n"
            "| - | Partial progress landed. | `measured` | `fact` | - |"
        )
        r = self.run_ingest(handback_text(status="PARTIAL", delta=delta))
        self.assert_ok(r)
        text = self.state_text()
        self.assertIn("| 03 |", text)
        self.assertIn("PARTIAL", text)
        self.assertIn(DATE, text)
        self.assertIn("| E004 | Partial progress landed.", text)

    def test_minimal_abandoned_handback_ingests(self):
        # Prevents: the ~3-line abandon escape hatch getting more expensive.
        hb = "Status: ABANDONED\n\nBlocked on credentials; nothing was changed.\n"
        r = self.run_ingest(hb)
        self.assert_ok(r)
        text = self.state_text()
        self.assertIn("ABANDONED", text)
        self.assertIn("| E001 |", text)
        self.assertIn("| E003 |", text)
        self.assertEqual(OBSERVATIONS_SEED, self.obs_text())

    def test_open_stub_changes_nothing(self):
        # Prevents: ingesting a dead session's placeholder stub as content.
        hb = (
            "Status: OPEN\n\n" + RECEIPT +
            "\n## Delta\n\n(not yet finalized)\n\n"
            "## For the next session\n\n(not yet finalized)\n\n"
            "## Structural observations\n\n(not yet finalized)\n"
        )
        r = self.run_ingest(hb)
        self.assert_ok(r)
        self.assertEqual(STATE_DOC, self.state_text())
        self.assertEqual(OBSERVATIONS_SEED, self.obs_text())
        self.assertIn("OPEN", r.stdout)


class TestModes(IngestEnv):

    def test_check_mode_writes_nothing(self):
        # Prevents: a dry-run that isn't.
        delta = (
            "ADD (one row):\n"
            "| - | Would be added. | `measured` | `fact` | - |"
        )
        obs = "- other | would be appended"
        r = self.run_ingest(handback_text(delta=delta, obs=obs), "--check")
        self.assert_ok(r)
        self.assertEqual(STATE_DOC, self.state_text())
        self.assertEqual(OBSERVATIONS_SEED, self.obs_text())
        self.assertIn("check", r.stdout.lower())

    def test_open_manual_block_counted_not_applied(self):
        # Prevents: the script writing ## Open (orchestrator-manual scope).
        delta = (
            "ADD (one row):\n"
            "| - | An established fact. | `measured` | `fact` | - |\n"
            "\n"
            "OPEN (orchestrator-manual):\n"
            "| A new open question? | The next step. | Low. | The user. | open |"
        )
        r = self.run_ingest(handback_text(delta=delta))
        self.assert_ok(r)
        text = self.state_text()
        self.assertNotIn("A new open question?", text)
        self.assertIn("| E004 | An established fact.", text)
        self.assertIn("1", r.stdout)
        self.assertIn("manual", r.stdout.lower())

    def test_missing_dispatched_row_warns_but_applies(self):
        # Prevents: a hand-tidied ## Dispatched blocking a valid ingest.
        doc = STATE_DOC.replace(
            "| 03 | docs/prompts/x.md | docs/orchestration/example-plan/handbacks/03.md | Dispatched 2026-08-14; outstanding. |\n",
            "",
        )
        self.state.write_text(doc, encoding="utf-8")
        delta = (
            "ADD (one row):\n"
            "| - | Applies anyway. | `measured` | `fact` | - |"
        )
        r = self.run_ingest(handback_text(delta=delta))
        self.assert_ok(r)
        self.assertIn("WARN", r.stdout)
        self.assertIn("| E004 | Applies anyway.", self.state_text())


if __name__ == "__main__":
    unittest.main()
