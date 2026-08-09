"""Behavioral tests for the orchestrator Edit/Write isolation hook.

The four ratified cases of the isolation-hook contract:
outside-allowlist blocks, inside-allowlist allows, and the two regressions
(no marker, foreign session) in which Edit/Write behavior is entirely
unchanged.

The hook is an ANTI-DRIFT GUARDRAIL, not a sandbox: it only sees calls that
go through the Edit / Write / NotebookEdit tools. A Bash heredoc bypasses it
entirely. These tests exercise what it does cover, not airtightness.

Like test_closing_hook.py, the hook runs as a COPY inside a temp tree, so its
own-location-derived project root points at the temp tree rather than at the
real repository.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import PLAN_NAME, PROJECT_ROOT, decision_and_reason

ISOLATION_HOOK = (
    PROJECT_ROOT / ".claude" / "hooks" / "enforce_orchestrator_isolation.py"
)

STATE_REL = "docs/orchestration/{0}_state.md".format(PLAN_NAME)


class IsolationHookEnv(unittest.TestCase):
    """Fixture running a COPY of the isolation hook in a temp project tree."""

    SESSION = "unittest-isolation-hook-session"

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name)

        self.proj = self.tmp / "proj"
        hooks_dir = self.proj / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        self.hook_copy = hooks_dir / "enforce_orchestrator_isolation.py"
        shutil.copyfile(str(ISOLATION_HOOK), str(self.hook_copy))

        self.marker_path = self.proj / ".claude" / "orchestrator_session.json"
        self.scratchpad = self.tmp / "claude-scratch" / "sess" / "scratchpad"
        self.scratchpad.mkdir(parents=True)

    def write_marker(self, session=None, state_path=STATE_REL):
        self.marker_path.write_text(
            json.dumps(
                {
                    "session_id": session or self.SESSION,
                    "plan_name": PLAN_NAME,
                    "state_path": state_path,
                }
            ),
            encoding="utf-8",
        )

    def hook(self, path, tool_name="Write", session=None):
        key = "notebook_path" if tool_name == "NotebookEdit" else "file_path"
        payload = {
            "session_id": session or self.SESSION,
            "tool_name": tool_name,
            "tool_input": {key: str(path)},
            "cwd": str(self.proj),
        }
        r = subprocess.run(
            [sys.executable, str(self.hook_copy)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return decision_and_reason(r)

    def assert_denied(self, path, tool_name="Write", reason_contains=None):
        verdict, reason = self.hook(path, tool_name)
        self.assertEqual(
            "deny", verdict,
            "expected DENY for {0!r} via {1}; got allow".format(
                path, tool_name
            ),
        )
        if reason_contains is not None:
            self.assertIn(
                reason_contains, reason,
                "deny reason must name {0!r}; got {1!r}".format(
                    reason_contains, reason
                ),
            )
        return reason

    def assert_allowed(self, path, tool_name="Write", session=None):
        verdict, reason = self.hook(path, tool_name, session)
        self.assertEqual(
            "allow", verdict,
            "expected ALLOW for {0!r} via {1}; denied with: {2}".format(
                path, tool_name, reason
            ),
        )


class TestOutsideAllowlistBlocks(IsolationHookEnv):
    def test_outside_allowlist_blocks(self):
        # Case 9: the marker matches and the target is outside the allowlist.
        self.write_marker()
        for tool_name in ["Write", "Edit", "NotebookEdit"]:
            for rel in [
                "src/engine.py",
                "docs/prds/some_prd.md",
                "README.md",
                ".claude/commands/orchestrator.md",
            ]:
                with self.subTest(tool=tool_name, path=rel):
                    target = self.proj / rel
                    reason = self.assert_denied(target, tool_name)
                    # The reason names the path...
                    self.assertIn(rel, reason.replace("\\", "/"))
                    # ...and the allowlist itself.
                    for entry in [
                        STATE_REL,
                        "docs/orchestration/",
                        "docs/prompts/",
                        "scratchpad",
                    ]:
                        self.assertIn(entry, reason)

    def test_absolute_path_outside_the_project_blocks(self):
        self.write_marker()
        self.assert_denied(self.tmp / "elsewhere" / "notes.md")


class TestInsideAllowlistAllows(IsolationHookEnv):
    def test_inside_allowlist_allows(self):
        # Case 10: the state file, docs/orchestration/, docs/prompts/, and
        # the session scratchpad.
        self.write_marker()
        for label, target in [
            ("state-file", self.proj / STATE_REL),
            (
                "orchestration-dir",
                self.proj / "docs" / "orchestration" / PLAN_NAME
                / "handbacks" / "01.md",
            ),
            (
                "prompts-dir",
                self.proj / "docs" / "prompts" / "090826" / "sess_01.md",
            ),
            ("scratchpad", self.scratchpad / "scratch.md"),
        ]:
            for tool_name in ["Write", "Edit", "NotebookEdit"]:
                with self.subTest(case=label, tool=tool_name):
                    self.assert_allowed(target, tool_name)

    def test_relative_paths_resolve_against_the_project_root(self):
        self.write_marker()
        self.assert_allowed(STATE_REL)
        self.assert_denied("src/engine.py")

    def test_state_path_from_the_marker_is_honored(self):
        # The allowlisted state file is the one the marker names, not a
        # hard-coded path.
        other = "docs/orchestration/other-plan_state.md"
        self.write_marker(state_path=other)
        self.assert_allowed(self.proj / other)


class TestNoMarkerRegression(IsolationHookEnv):
    def test_no_marker_regression(self):
        # Case 11: no orchestrator marker -> behavior entirely unchanged,
        # i.e. allow with no stdout at all.
        for rel in ["src/engine.py", STATE_REL, "README.md"]:
            for tool_name in ["Write", "Edit", "NotebookEdit"]:
                with self.subTest(path=rel, tool=tool_name):
                    self.assert_allowed(self.proj / rel, tool_name)

    def test_other_tools_are_never_touched(self):
        # The hook fires on Edit|Write|NotebookEdit only; a Bash payload is a
        # structural no-op even with the marker in place.
        self.write_marker()
        self.assert_allowed(self.proj / "src" / "engine.py", "Bash")
        self.assert_allowed(self.proj / "src" / "engine.py", "Read")


class TestForeignSessionRegression(IsolationHookEnv):
    def test_foreign_session_regression(self):
        # Case 12: a marker belonging to a different session never constrains
        # this one, and is never consumed.
        self.write_marker(session="some-other-session")
        for rel in ["src/engine.py", "README.md", STATE_REL]:
            for tool_name in ["Write", "Edit", "NotebookEdit"]:
                with self.subTest(path=rel, tool=tool_name):
                    self.assert_allowed(self.proj / rel, tool_name)
        self.assertTrue(self.marker_path.exists())
