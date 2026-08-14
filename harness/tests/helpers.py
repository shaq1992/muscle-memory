"""Shared helpers for the guardrail-hook behavioral tests.

Stdlib-only (unittest + subprocess + tempfile); no pytest, no venv.
Run with: python3 -m unittest discover .claude/harness/tests
(pytest collects these classes natively as a courtesy; it is never required.)

Fixture layout built per test (in a throwaway temp dir):

    <tmp>/repo/                 -- fake PROJECT repo (branch main)
    <tmp>/repo/.claude/         -- nested fake HARNESS repo (branch main)
    <tmp>/repo/.claude/preferences.md  -- fixture params (single key block)
    <tmp>/project_remote.git    -- bare remote, project repo's origin
    <tmp>/harness_remote.git    -- bare remote, harness repo's origin
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Anchor on the HARNESS repo root (the directory holding hooks/, harness/,
# settings.json), not the host project root. The harness repo is normally
# checked out at <project>/.claude/, but during a harness plan it is also
# checked out as a linked git worktree elsewhere; resolving via the repo root
# keeps the suite runnable from BOTH layouts, always testing the checkout it
# lives in.
HARNESS_ROOT = Path(__file__).resolve().parents[2]
GUARDRAIL_HOOK = HARNESS_ROOT / "hooks" / "git_guardrails.py"
CLOSING_HOOK = HARNESS_ROOT / "hooks" / "enforce_phase_closing.py"
SETTINGS_JSON = HARNESS_ROOT / "settings.json"
VALIDATE_PROMPT = HARNESS_ROOT / "harness" / "scripts" / "validate_prompt.py"

PLAN_NAME = "example-plan"

# Fixture preferences.md WITHOUT harness_push_remote; tests that need the key
# call set_harness_push_remote() to append it. Mirrors the real file's layout:
# one contiguous machine-parseable key block at the top.
BASE_PARAMS = """# Preferences (test fixture)

user_name: Test User
default_branch: main
protected_branch: main
integration_branch_prefix: integration/
phase_branch_pattern: <plan_name>-phase-<NN>
phase_number_padding: 2
merge_style: merge-commit
retain_integration_branch: true
interpreter: python3
test_command: python3 -m unittest
encoding_constraint: ascii
"""

# Glob pattern matching the fixture harness remote (a local bare-repo path).
MATCHING_REMOTE_PATTERN = "*harness_remote*"
MISMATCHING_REMOTE_PATTERN = "github.com/example/some-other-repo"


def git(cwd, *args):
    """Run a git command in cwd; raise on failure."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def run_hook(command, cwd, hook_path=None):
    """Feed a Bash PreToolUse payload to the guardrail hook; return the result.

    hook_path overrides the hook file to execute (used to run a COPY of the
    hook from inside the temp tree, so its hook-relative fallback candidate
    cannot resolve to the real project's preferences file).
    """
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }
    return subprocess.run(
        [sys.executable, str(hook_path or GUARDRAIL_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )


def decision_and_reason(result):
    """Map a hook subprocess result to ('allow'|'deny', reason)."""
    if result.returncode != 0:
        raise AssertionError(
            "hook exited non-zero (rc={0}): stdout={1!r} stderr={2!r}".format(
                result.returncode, result.stdout, result.stderr
            )
        )
    if not result.stdout.strip():
        return "allow", ""
    out = json.loads(result.stdout)
    hso = out.get("hookSpecificOutput", {})
    return (
        hso.get("permissionDecision", "allow"),
        hso.get("permissionDecisionReason", ""),
    )


class GuardrailEnv(unittest.TestCase):
    """Base TestCase building the two-repo fixture. No test methods here."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmp = Path(self._tmpdir.name)

        # Project repo on main with one commit.
        self.repo = tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "user.name", "Test User")
        (self.repo / "README.md").write_text("project fixture\n", encoding="utf-8")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-m", "init")
        self.project_remote = tmp / "project_remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(self.project_remote)],
            check=True, capture_output=True, timeout=30,
        )
        git(self.repo, "remote", "add", "origin", str(self.project_remote))

        # Nested harness repo at .claude/ on main with one commit.
        self.harness = self.repo / ".claude"
        self.harness.mkdir()
        git(self.harness, "init", "-b", "main")
        git(self.harness, "config", "user.email", "test@example.com")
        git(self.harness, "config", "user.name", "Test User")
        (self.harness / "HARNESS.md").write_text("harness fixture\n", encoding="utf-8")
        git(self.harness, "add", "HARNESS.md")
        git(self.harness, "commit", "-m", "init")
        self.harness_remote = tmp / "harness_remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(self.harness_remote)],
            check=True, capture_output=True, timeout=30,
        )
        git(self.harness, "remote", "add", "origin", str(self.harness_remote))

        # Fixture parameters (no harness_push_remote by default): the single
        # consolidated preferences.md at the harness-repo root.
        self.params_file = self.harness / "preferences.md"
        self.params_file.write_text(BASE_PARAMS, encoding="utf-8")

    def set_harness_push_remote(self, pattern):
        """Append (or omit, if None) the harness_push_remote key."""
        content = BASE_PARAMS
        if pattern is not None:
            content += "harness_push_remote: {0}\n".format(pattern)
        self.params_file.write_text(content, encoding="utf-8")

    def hook(self, command, cwd=None):
        return decision_and_reason(run_hook(command, cwd or self.repo))

    def assert_denied(self, command, cwd=None, reason_contains=None):
        verdict, reason = self.hook(command, cwd)
        self.assertEqual(
            "deny", verdict,
            "expected DENY for {0!r}; got allow".format(command),
        )
        if reason_contains is not None:
            self.assertIn(
                reason_contains, reason,
                "deny reason for {0!r} must name {1!r}; got {2!r}".format(
                    command, reason_contains, reason
                ),
            )

    def assert_allowed(self, command, cwd=None):
        verdict, reason = self.hook(command, cwd)
        self.assertEqual(
            "allow", verdict,
            "expected ALLOW for {0!r}; denied with: {1}".format(command, reason),
        )


# ---------------------------------------------------------------------------
# Stop-hook (enforce_phase_closing.py) fixture
# ---------------------------------------------------------------------------

COMPLIANT_LEARNINGS = (
    "**Branch:** {0}-phase-04\n"
    "\n"
    "## Learnings\n"
    "\n"
    "- a carried-forward bullet\n"
).format(PLAN_NAME)

COMPLIANT_LEDGER = (
    "# Learnings Ledger: {0}\n"
    "\n"
    "Last merged: phase 04\n"
    "\n"
    "## Some Theme\n"
    "\n"
    "- a current-truth bullet (P4)\n"
).format(PLAN_NAME)


class ClosingHookEnv(unittest.TestCase):
    """Fixture for the Stop hook's content checks.

    Runs a COPY of enforce_phase_closing.py from inside a temp project tree,
    so the hook's own-location-derived PROJECT_DIR (and therefore both the
    relative learnings_path resolution and the plan-level ledger path
    docs/learnings/<plan>_ledger.md) point at the temp tree, never at the
    real repository.
    """

    PHASE = 4
    SESSION = "unittest-closing-hook-session"

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmp = Path(self._tmpdir.name)

        self.proj = tmp / "proj"
        hooks_dir = self.proj / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        self.hook_copy = hooks_dir / "enforce_phase_closing.py"
        shutil.copyfile(str(CLOSING_HOOK), str(self.hook_copy))

        self.marker_path = self.proj / ".claude" / "phase_closing.json"
        self.learnings_rel = (
            "docs/learnings/020826/{0}_phase_04_learnings.md".format(PLAN_NAME)
        )
        self.learnings_path = self.proj / self.learnings_rel
        self.learnings_path.parent.mkdir(parents=True)
        self.ledger_path = (
            self.proj / "docs" / "learnings" / "{0}_ledger.md".format(PLAN_NAME)
        )

    def write_marker(self, phase=None, session=None):
        self.marker_path.write_text(
            json.dumps(
                {
                    "session_id": session or self.SESSION,
                    "plan_name": PLAN_NAME,
                    "phase": self.PHASE if phase is None else phase,
                    "learnings_path": self.learnings_rel,
                }
            ),
            encoding="utf-8",
        )

    def write_learnings(self, text=COMPLIANT_LEARNINGS):
        self.learnings_path.write_text(text, encoding="utf-8")

    def write_ledger(self, text=COMPLIANT_LEDGER):
        self.ledger_path.write_text(text, encoding="utf-8")

    def run_stop(self, session=None):
        return subprocess.run(
            [sys.executable, str(self.hook_copy)],
            input=json.dumps({"session_id": session or self.SESSION}),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def stop_decision(self, session=None):
        """Return ('allow', '') or ('block', reason)."""
        r = self.run_stop(session)
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

    def assert_allowed_stop(self, session=None):
        verdict, reason = self.stop_decision(session)
        self.assertEqual(
            "allow", verdict, "expected ALLOW; blocked with: {0}".format(reason)
        )
