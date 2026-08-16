"""Behavioral tests for the orchestrator Edit/Write isolation hook.

Per-plan marker scheme (D10): the hook scans ALL markers matching
.claude/orchestrator_*_session.json, matches on session_id, and enforces the
allowlist of every marker naming THIS session (union of their state paths).
Concurrent orchestrators on DIFFERENT plans each get their own marker, so one
orchestrator can no longer disarm another's guardrail (the single-slot
fail-open bug, evidence row E031).

The ratified cases:
  - match          -> outside-allowlist blocks, inside-allowlist allows;
  - mismatch       -> a foreign session's marker never constrains this one,
                      and is never consumed;
  - multi-marker   -> only markers naming this session constrain it; several
                      matching markers union their state paths;
  - no marker      -> Edit/Write behavior entirely unchanged;
  - malformed      -> FAIL-CLOSED: an unreadable marker denies guarded writes
                      for every session, naming the corrupt path;
  - legacy         -> the single-slot orchestrator_session.json is inert.

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

from helpers import HARNESS_ROOT, PLAN_NAME, decision_and_reason

ISOLATION_HOOK = HARNESS_ROOT / "hooks" / "enforce_orchestrator_isolation.py"

STATE_REL = "docs/orchestration/{0}_state.md".format(PLAN_NAME)

OTHER_PLAN = "other-plan"
OTHER_STATE_REL = "docs/orchestration/{0}_state.md".format(OTHER_PLAN)


class IsolationHookEnv(unittest.TestCase):
    """Fixture running a COPY of the isolation hook in a temp project tree."""

    SESSION = "unittest-isolation-hook-session"

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = Path(self._tmpdir.name)

        self.proj = self.tmp / "proj"
        self.claude_dir = self.proj / ".claude"
        hooks_dir = self.claude_dir / "hooks"
        hooks_dir.mkdir(parents=True)
        self.hook_copy = hooks_dir / "enforce_orchestrator_isolation.py"
        shutil.copyfile(str(ISOLATION_HOOK), str(self.hook_copy))

        self.scratchpad = self.tmp / "claude-scratch" / "sess" / "scratchpad"
        self.scratchpad.mkdir(parents=True)

    def marker_path(self, plan=PLAN_NAME):
        return self.claude_dir / "orchestrator_{0}_session.json".format(plan)

    def write_marker(self, plan=PLAN_NAME, session=None, state_path=None):
        if state_path is None:
            state_path = "docs/orchestration/{0}_state.md".format(plan)
        path = self.marker_path(plan)
        path.write_text(
            json.dumps(
                {
                    "session_id": session or self.SESSION,
                    "plan_name": plan,
                    "state_path": state_path,
                }
            ),
            encoding="utf-8",
        )
        return path

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

    def assert_denied(self, path, tool_name="Write", session=None,
                      reason_contains=None):
        verdict, reason = self.hook(path, tool_name, session)
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
        # Match case: this session's per-plan marker exists and the target is
        # outside the allowlist.
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
        # Match case: the state file, docs/orchestration/, docs/prompts/, and
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
        # hard-coded path -- even outside docs/orchestration/.
        other = "notes/{0}_state.md".format(PLAN_NAME)
        self.write_marker(state_path=other)
        self.assert_allowed(self.proj / other)


class TestNoMarkerRegression(IsolationHookEnv):
    def test_no_marker_regression(self):
        # No-marker case: no per-plan marker -> behavior entirely unchanged,
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
        # Mismatch case: a marker belonging to a different session never
        # constrains this one, and is never consumed.
        self.write_marker(session="some-other-session")
        for rel in ["src/engine.py", "README.md", STATE_REL]:
            for tool_name in ["Write", "Edit", "NotebookEdit"]:
                with self.subTest(path=rel, tool=tool_name):
                    self.assert_allowed(self.proj / rel, tool_name)
        self.assertTrue(self.marker_path().exists())


class TestMultiMarker(IsolationHookEnv):
    """Concurrent orchestrators on DIFFERENT plans -- the supported case."""

    def test_only_the_matching_marker_constrains(self):
        # This session orchestrates PLAN_NAME; a second orchestrator (another
        # session) holds OTHER_PLAN. This session is still constrained by its
        # own marker: the E031 fail-open bug was the second marker disarming
        # the first's guardrail.
        self.write_marker(plan=PLAN_NAME)
        self.write_marker(plan=OTHER_PLAN, session="second-orchestrator")
        self.assert_denied(self.proj / "src" / "engine.py")
        self.assert_allowed(self.proj / STATE_REL)

    def test_foreign_markers_do_not_constrain_a_third_session(self):
        # Two orchestrator markers, neither naming this session: a dispatched
        # implementation session writes code unimpeded.
        self.write_marker(plan=PLAN_NAME, session="orchestrator-a")
        self.write_marker(plan=OTHER_PLAN, session="orchestrator-b")
        self.assert_allowed(
            self.proj / "src" / "engine.py", session="implementer-session"
        )

    def test_two_matching_markers_union_their_state_paths(self):
        # One session holding two plans' markers may write BOTH state files
        # (union of allowlists), and still nothing outside it. State paths
        # sit outside docs/orchestration/ so the directory rule cannot mask
        # the union semantics.
        state_a = "notes/plan_a_state.md"
        state_b = "notes/plan_b_state.md"
        self.write_marker(plan="plan-a", state_path=state_a)
        self.write_marker(plan="plan-b", state_path=state_b)
        self.assert_allowed(self.proj / state_a)
        self.assert_allowed(self.proj / state_b)
        self.assert_denied(self.proj / "src" / "engine.py")

    def test_a_foreign_state_path_is_not_allowlisted(self):
        # The union covers MATCHING markers only: another orchestrator's
        # custom state path (outside the fixed dirs) stays outside this
        # session's allowlist.
        foreign_state = "notes/foreign_state.md"
        self.write_marker(plan=PLAN_NAME)
        self.write_marker(
            plan=OTHER_PLAN, session="second-orchestrator",
            state_path=foreign_state,
        )
        self.assert_denied(self.proj / foreign_state)


class TestMalformedMarkerFailsClosed(IsolationHookEnv):
    """An unreadable marker denies guarded writes -- for every session."""

    def write_malformed(self, plan=PLAN_NAME, text="{not json"):
        path = self.marker_path(plan)
        path.write_text(text, encoding="utf-8")
        return path

    def test_malformed_marker_denies_and_names_the_path(self):
        corrupt = self.write_malformed()
        for tool_name in ["Write", "Edit", "NotebookEdit"]:
            with self.subTest(tool=tool_name):
                reason = self.assert_denied(
                    self.proj / "src" / "engine.py", tool_name
                )
                self.assertIn(corrupt.name, reason)

    def test_malformed_marker_denies_even_a_foreign_session(self):
        # Fail-closed: the hook cannot prove the corrupt marker is not this
        # session's, so nobody's guarded writes proceed until it is removed.
        corrupt = self.write_malformed()
        self.assert_denied(
            self.proj / "src" / "engine.py",
            session="some-other-session",
            reason_contains=corrupt.name,
        )

    def test_malformed_marker_denies_even_inside_the_allowlist(self):
        corrupt = self.write_malformed()
        self.assert_denied(self.proj / STATE_REL, reason_contains=corrupt.name)

    def test_non_dict_marker_content_is_malformed(self):
        corrupt = self.write_malformed(text=json.dumps(["not", "a", "dict"]))
        self.assert_denied(
            self.proj / "src" / "engine.py", reason_contains=corrupt.name
        )

    def test_a_valid_sibling_does_not_mask_the_corrupt_marker(self):
        self.write_marker(plan=PLAN_NAME)
        corrupt = self.write_malformed(plan=OTHER_PLAN)
        self.assert_denied(
            self.proj / STATE_REL, reason_contains=corrupt.name
        )

    def test_unguarded_tools_stay_untouched(self):
        # The hook still fires on Edit|Write|NotebookEdit only.
        self.write_malformed()
        self.assert_allowed(self.proj / "src" / "engine.py", "Bash")


class TestLegacyMarkerIsInert(IsolationHookEnv):
    """The single-slot orchestrator_session.json is not read after cutover."""

    def test_legacy_marker_never_constrains(self):
        # Even a well-formed legacy marker naming THIS session is inert: the
        # per-plan scan pattern does not match the legacy filename.
        legacy = self.claude_dir / "orchestrator_session.json"
        legacy.write_text(
            json.dumps(
                {
                    "session_id": self.SESSION,
                    "plan_name": PLAN_NAME,
                    "state_path": STATE_REL,
                }
            ),
            encoding="utf-8",
        )
        self.assert_allowed(self.proj / "src" / "engine.py")
        self.assertTrue(legacy.exists())

    def test_other_session_marker_families_are_not_scanned(self):
        # handback_session.json and improve_session.json share the
        # *_session.json gitignore glob but are NOT orchestrator markers;
        # a malformed one must not trip the fail-closed path either.
        (self.claude_dir / "handback_session.json").write_text(
            "{not json", encoding="utf-8"
        )
        (self.claude_dir / "improve_session.json").write_text(
            "{not json", encoding="utf-8"
        )
        self.assert_allowed(self.proj / "src" / "engine.py")
