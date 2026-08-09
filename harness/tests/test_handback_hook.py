"""Behavioral tests for the handback Stop-hook contract.

The eight ratified cases of the handback Stop-hook contract:
no-marker, foreign-session, missing handback, bad status, the three-line
abandon path, complete-and-self-delete, mutual exclusivity with the
phase-closing marker, and the verbatim unblocking content in every block
reason.

Like test_closing_hook.py, the contract is exercised through hook COPIES
inside a temp tree, so each hook's own-location-derived project root (and
therefore the marker path and the relative handback_path resolution) points
at the temp tree, never at the real repository.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import CLOSING_HOOK, PLAN_NAME, PROJECT_ROOT

HANDBACK_HOOK = PROJECT_ROOT / ".claude" / "hooks" / "enforce_handback.py"

SESSION_NUMBER = 7

# The minimal content that unblocks the hook, exactly as the handback schema's
# binding constraint spells it. Every block reason must carry this verbatim.
ABANDON_MINIMUM = (
    "Status: ABANDONED\n"
    "\n"
    "Blocked on the staging credentials; nothing was changed.\n"
)

STUB_HANDBACK = (
    "Status: OPEN\n"
    "\n"
    "**Handed to this session (read receipt):**\n"
    "- | greenlist | the fixture row |\n"
)

COMPLETE_HANDBACK = (
    "Status: COMPLETE\n"
    "\n"
    "**Handed to this session (read receipt):**\n"
    "- | greenlist | the fixture row |\n"
    "\n"
    "## Delta\n"
    "\n"
    "none\n"
    "\n"
    "## For the next session\n"
    "\n"
    "Nothing outstanding.\n"
    "\n"
    "## Structural observations\n"
    "\n"
    "none\n"
)


class HandbackHookEnv(unittest.TestCase):
    """Fixture running a COPY of enforce_handback.py in a temp project tree."""

    SESSION = "unittest-handback-hook-session"

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmp = Path(self._tmpdir.name)

        self.proj = tmp / "proj"
        hooks_dir = self.proj / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        self.hook_copy = hooks_dir / "enforce_handback.py"
        shutil.copyfile(str(HANDBACK_HOOK), str(self.hook_copy))
        self.closing_hook_copy = hooks_dir / "enforce_phase_closing.py"
        shutil.copyfile(str(CLOSING_HOOK), str(self.closing_hook_copy))

        self.marker_path = self.proj / ".claude" / "handback_session.json"
        self.closing_marker_path = self.proj / ".claude" / "phase_closing.json"
        self.handback_rel = "docs/orchestration/{0}/handbacks/{1:02d}.md".format(
            PLAN_NAME, SESSION_NUMBER
        )
        self.handback_path = self.proj / self.handback_rel
        self.handback_path.parent.mkdir(parents=True)

    # -- fixture writers ---------------------------------------------------

    def write_marker(self, session=None, handback_path=None):
        self.marker_path.write_text(
            json.dumps(
                {
                    "session_id": session or self.SESSION,
                    "plan_name": PLAN_NAME,
                    "session_number": SESSION_NUMBER,
                    "handback_path": (
                        self.handback_rel if handback_path is None
                        else handback_path
                    ),
                }
            ),
            encoding="utf-8",
        )

    def write_closing_marker(self, session=None):
        self.closing_marker_path.write_text(
            json.dumps(
                {
                    "session_id": session or self.SESSION,
                    "plan_name": PLAN_NAME,
                    "phase": 3,
                    "learnings_path": "docs/learnings/090826/x_learnings.md",
                }
            ),
            encoding="utf-8",
        )

    def write_handback(self, text=COMPLETE_HANDBACK):
        self.handback_path.write_text(text, encoding="utf-8")

    # -- hook drivers ------------------------------------------------------

    def _run(self, hook, session=None):
        r = subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps({"session_id": session or self.SESSION}),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            0, r.returncode,
            "stop hook exited non-zero: stdout={0!r} stderr={1!r}".format(
                r.stdout, r.stderr
            ),
        )
        if not r.stdout.strip():
            return "allow", ""
        out = json.loads(r.stdout)
        return out.get("decision", "allow"), out.get("reason", "")

    def stop_decision(self, session=None):
        return self._run(self.hook_copy, session)

    def closing_decision(self, session=None):
        return self._run(self.closing_hook_copy, session)

    def assert_blocked(self, reason_contains=None, session=None):
        verdict, reason = self.stop_decision(session)
        self.assertEqual("block", verdict, "expected BLOCK; got allow")
        if reason_contains is not None:
            self.assertIn(
                reason_contains, reason,
                "block reason must name {0!r}; got {1!r}".format(
                    reason_contains, reason
                ),
            )
        return reason

    def assert_allowed_stop(self, session=None):
        verdict, reason = self.stop_decision(session)
        self.assertEqual(
            "allow", verdict, "expected ALLOW; blocked with: {0}".format(reason)
        )


class TestNoMarkerAllows(HandbackHookEnv):
    def test_no_marker_allows(self):
        # Case 1: no handback marker at all -> structural no-op, allow.
        self.assert_allowed_stop()
        # Still allows with no handback file anywhere on disk.
        self.assertFalse(self.handback_path.exists())
        self.assert_allowed_stop()


class TestForeignSessionAllows(HandbackHookEnv):
    def test_foreign_session_allows(self):
        # Case 2: an abandoned session's marker never blocks another session,
        # and is never consumed.
        self.write_marker(session="some-other-session")
        self.assert_allowed_stop()
        self.assertTrue(self.marker_path.exists())


class TestMissingHandbackBlocks(HandbackHookEnv):
    def test_missing_handback_blocks(self):
        # Case 3: marker matches, no file at handback_path -> block naming
        # that exact path.
        self.write_marker()
        reason = self.assert_blocked(reason_contains=self.handback_rel)
        self.assertIn(ABANDON_MINIMUM, reason)
        self.assertTrue(self.marker_path.exists())


class TestBadStatusBlocks(HandbackHookEnv):
    def test_bad_status_blocks(self):
        # Case 4: Status absent, or outside the closed vocabulary.
        self.write_marker()
        for label, text in [
            ("absent", "**Handed to this session:**\n- row\n"),
            ("outside-vocabulary", "Status: DONE\n\nSomething happened.\n"),
            ("lowercase", "Status: complete\n\nSomething happened.\n"),
        ]:
            with self.subTest(case=label):
                self.write_handback(text)
                reason = self.assert_blocked(reason_contains="Status")
                self.assertIn(ABANDON_MINIMUM, reason)
                self.assertTrue(self.marker_path.exists())

    def test_open_stub_is_not_a_terminal_state(self):
        # OPEN is in the file-level vocabulary but is NOT a terminal state.
        # The stub is written at session start, so accepting OPEN here would
        # make the hook vacuous -- it would demand a file the session already
        # wrote in minute one. A session that reaches its Stop hook is alive,
        # and OPEN is reserved as positive evidence that a session died.
        self.write_marker()
        self.write_handback(STUB_HANDBACK)
        reason = self.assert_blocked(reason_contains="OPEN")
        self.assertIn(ABANDON_MINIMUM, reason)
        self.assertTrue(self.marker_path.exists())


class TestAbandonedThreeLinerAllows(HandbackHookEnv):
    def test_abandoned_three_liner_allows(self):
        # Case 5: the binding constraint. Status plus one sentence, nothing
        # else -- no ## Delta, no advisory section, no observation.
        self.write_marker()
        self.write_handback(ABANDON_MINIMUM)
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())

    def test_abandon_path_costs_about_three_lines(self):
        # The escape hatch must stay cheap: the passing content is a status
        # field and one sentence, and nothing more.
        body = [ln for ln in ABANDON_MINIMUM.splitlines() if ln.strip()]
        self.assertLessEqual(
            len(body), 3,
            "abandon path must cost about three lines; got {0}".format(body),
        )


class TestCompleteAllowsAndSelfDeletes(HandbackHookEnv):
    def test_complete_allows_and_self_deletes(self):
        # Case 6: COMPLETE with all four blocks -> allow, marker removed.
        self.write_marker()
        self.write_handback(COMPLETE_HANDBACK)
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())

    def test_complete_missing_a_section_blocks(self):
        # The four-part structure is only enforced for the statuses that
        # claim real work landed.
        self.write_marker()
        for missing in [
            "## Delta",
            "## For the next session",
            "## Structural observations",
        ]:
            with self.subTest(missing=missing):
                stripped = COMPLETE_HANDBACK.replace(missing + "\n", "")
                self.write_handback(stripped)
                reason = self.assert_blocked(reason_contains=missing)
                self.assertIn(ABANDON_MINIMUM, reason)
        self.write_handback(COMPLETE_HANDBACK)
        self.assert_allowed_stop()


class TestMarkersMutuallyExclusive(HandbackHookEnv):
    def test_markers_mutually_exclusive(self):
        # Case 7: neither hook honors the other's marker, for the same
        # session id and with nothing else on disk.

        # A phase-closing marker alone: the handback hook is a no-op, and the
        # closing marker survives untouched.
        self.write_closing_marker()
        self.assert_allowed_stop()
        self.assertTrue(self.closing_marker_path.exists())

        # A handback marker alone: the closing hook is a no-op, and the
        # handback marker survives untouched.
        self.closing_marker_path.unlink()
        self.write_marker()
        verdict, reason = self.closing_decision()
        self.assertEqual(
            "allow", verdict,
            "closing hook must ignore a handback marker; blocked: {0}".format(
                reason
            ),
        )
        self.assertTrue(self.marker_path.exists())


class TestBlockMessageStatesUnblockingContent(HandbackHookEnv):
    def test_block_message_states_unblocking_content(self):
        # Case 8: EVERY block reason carries the minimal unblocking content
        # verbatim -- not a description of it, and not a pointer to a schema.
        self.write_marker()
        reasons = []

        # Missing file.
        reasons.append(self.assert_blocked())

        # Status absent.
        self.write_handback("no status line here\n")
        reasons.append(self.assert_blocked())

        # Status outside the vocabulary.
        self.write_handback("Status: FINISHED\n\nA sentence.\n")
        reasons.append(self.assert_blocked())

        # Status OPEN.
        self.write_handback(STUB_HANDBACK)
        reasons.append(self.assert_blocked())

        # PARTIAL missing a required section.
        self.write_handback(
            COMPLETE_HANDBACK.replace("Status: COMPLETE", "Status: PARTIAL")
            .replace("## Delta\n", "")
        )
        reasons.append(self.assert_blocked())

        for i, reason in enumerate(reasons):
            with self.subTest(block=i):
                self.assertIn(
                    ABANDON_MINIMUM, reason,
                    "block reason {0} omits the verbatim unblocking "
                    "content: {1!r}".format(i, reason),
                )
