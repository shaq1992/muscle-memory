"""Behavioral tests for the Phase 4 Stop-hook contract (learnings revision).

The five ratified cases from the phase prompt: the two preserved existing
behaviors (block-until-exists, wrong-session no-op) plus the three new
content checks (PRD R5.6): **Branch:** first line, ## Learnings header,
ledger Last-merged stamp matching the marker's phase.

These tests SUPERSEDE the closing-hook portion of the former
TestClosingHookRegressionFlaggedExtra.test_hook_contract_unchanged in
test_git_guardrails.py: under the new law a bare-existence learnings file no
longer satisfies the hook, and the plan-level ledger check resolves against
the hook's own project root -- so the contract is exercised here through a
hook COPY inside a temp tree (settings-registration coverage stays in
test_git_guardrails.py).

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

from helpers import (
    COMPLIANT_LEARNINGS,
    COMPLIANT_LEDGER,
    ClosingHookEnv,
)


class TestBlocksUntilLearningsFileExists(ClosingHookEnv):
    def test_blocks_until_learnings_file_exists(self):
        # No marker at all -> structural no-op, allow.
        self.assert_allowed_stop()

        # Marker present, learnings file missing -> block naming the path.
        self.write_marker()
        self.write_ledger()
        self.assert_blocked(reason_contains=self.learnings_rel)
        self.assertTrue(self.marker_path.exists())

        # Compliant learnings + ledger -> allow, marker self-deletes.
        self.write_learnings()
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())


class TestWrongSessionMarkerIsNoop(ClosingHookEnv):
    def test_wrong_session_marker_is_noop(self):
        # Another session's marker never blocks and is never consumed --
        # even when nothing else (learnings, ledger) exists.
        self.write_marker(session="some-other-session")
        self.assert_allowed_stop()
        self.assertTrue(self.marker_path.exists())


class TestBranchFirstLineRequired(ClosingHookEnv):
    def test_branch_first_line_required(self):
        self.write_marker()
        self.write_ledger()
        for bad in [
            # No **Branch:** line at all.
            "## Learnings\n\n- bullet\n",
            # Malformed: missing the colon.
            "**Branch** example-plan-phase-04\n\n## Learnings\n\n- b\n",
            # Right line, wrong position (not first).
            "\n**Branch:** example-plan-phase-04\n\n## Learnings\n\n- b\n",
        ]:
            with self.subTest(first_line=bad.splitlines()[0] if bad.strip() else ""):
                self.write_learnings(bad)
                self.assert_blocked(reason_contains="**Branch:**")
                self.assertTrue(self.marker_path.exists())

        # Compliant file clears the check.
        self.write_learnings(COMPLIANT_LEARNINGS)
        self.assert_allowed_stop()


class TestLearningsHeaderRequired(ClosingHookEnv):
    def test_learnings_header_required(self):
        self.write_marker()
        self.write_ledger()
        self.write_learnings(
            "**Branch:** example-plan-phase-04\n\n- bullet without header\n"
        )
        self.assert_blocked(reason_contains="## Learnings")
        self.assertTrue(self.marker_path.exists())

        # The retired split does not satisfy the new schema.
        self.write_learnings(
            "**Branch:** example-plan-phase-04\n\n## Carry Forward\n\n- b\n"
        )
        self.assert_blocked(reason_contains="## Learnings")

        self.write_learnings(COMPLIANT_LEARNINGS)
        self.assert_allowed_stop()


class TestLedgerStampMustMatchMarkerPhase(ClosingHookEnv):
    def test_ledger_stamp_must_match_marker_phase(self):
        self.write_marker()  # phase 4
        self.write_learnings()

        # Ledger absent entirely -> block naming the stamp check.
        self.assert_blocked(reason_contains="Last merged")
        self.assertTrue(self.marker_path.exists())

        # Ledger present, stamp reads a different phase -> block.
        self.write_ledger(
            COMPLIANT_LEDGER.replace(
                "Last merged: phase 04", "Last merged: phase 03"
            )
        )
        self.assert_blocked(reason_contains="Last merged")

        # Ledger present, stamp line missing -> block.
        self.write_ledger(
            COMPLIANT_LEDGER.replace("Last merged: phase 04\n\n", "")
        )
        self.assert_blocked(reason_contains="Last merged")

        # Matching stamp -> allow, marker self-deletes.
        self.write_ledger(COMPLIANT_LEDGER)
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())
