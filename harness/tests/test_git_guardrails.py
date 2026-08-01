"""Behavioral tests for the Phase 2 guardrail-hook contract (PR git law).

Contract classes 1-8 below are the ten ratified test cases from the phase
prompt. Classes 9-11 are EXPLICITLY FLAGGED EXTRAS beyond the contract:
  9  - allow-path regression guard (normal phase/PR-law operations must pass;
       protects against a fail-closed rewrite that bricks every git call)
  10 - non-git passthrough guard (quoted git-looking strings, plain commands)
  11 - closing-hook regression + settings.json registration (Stop hook is
       untouched this phase; settings must invoke bare python3, no venv)

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import json
import subprocess
import sys

from helpers import (
    CLOSING_HOOK,
    MATCHING_REMOTE_PATTERN,
    MISMATCHING_REMOTE_PATTERN,
    PLAN_NAME,
    PROJECT_ROOT,
    SETTINGS_JSON,
    GuardrailEnv,
    git,
)


# ---------------------------------------------------------------------------
# 1. Destructive ops: force push in every variant
# ---------------------------------------------------------------------------
class TestBlocksForcePush(GuardrailEnv):
    def test_blocks_force_push(self):
        for command in [
            "git push --force",
            "git push -f origin feature-x",
            "git push --force-with-lease origin main",
            "git push origin feature-x --force",
        ]:
            with self.subTest(command=command):
                self.assert_denied(command)


# ---------------------------------------------------------------------------
# 2. Destructive ops: reset --hard, branch -D, clean -f
# ---------------------------------------------------------------------------
class TestBlocksDestructiveOps(GuardrailEnv):
    def test_blocks_reset_hard(self):
        self.assert_denied("git reset --hard HEAD~1")

    def test_blocks_branch_D(self):
        self.assert_denied("git branch -D {0}-phase-02".format(PLAN_NAME))

    def test_blocks_clean_f(self):
        self.assert_denied("git clean -f")
        self.assert_denied("git clean -fd")


# ---------------------------------------------------------------------------
# 3. Protected branch: merge while on it is flat-blocked (no exceptions)
# ---------------------------------------------------------------------------
class TestBlocksMergeOnProtectedBranch(GuardrailEnv):
    def test_blocks_merge_on_protected_branch(self):
        self.assert_denied(
            'git merge integration/{0} -m "merge: final"'.format(PLAN_NAME)
        )


# ---------------------------------------------------------------------------
# 4. Protected branch: any push targeting it is flat-blocked
# ---------------------------------------------------------------------------
class TestBlocksPushTargetingProtected(GuardrailEnv):
    def test_blocks_push_targeting_protected(self):
        for command in [
            "git push origin main",
            "git push origin main:main",
            "git push origin HEAD:main",
            "git push origin feature-x:refs/heads/main",
            "git push",  # bare push while ON main targets main
        ]:
            with self.subTest(command=command):
                self.assert_denied(command)


# ---------------------------------------------------------------------------
# 5. Protected branch: gh pr merge is user-only, flat-blocked for Claude
# ---------------------------------------------------------------------------
class TestBlocksGhPrMerge(GuardrailEnv):
    def test_blocks_gh_pr_merge_into_protected(self):
        for command in [
            "gh pr merge 12 --merge",
            "gh pr merge --merge --delete-branch",
            "gh pr merge 3 --repo example/some-repo --squash",
            "cd .claude && gh pr merge 1 --merge",
        ]:
            with self.subTest(command=command):
                self.assert_denied(command)


# ---------------------------------------------------------------------------
# 6-8. Push-remote allowlist (fail-closed) + repo-context attribution
# ---------------------------------------------------------------------------
class TestPushRemoteAllowlist(GuardrailEnv):
    def test_push_allowlist_match_allowed(self):
        self.set_harness_push_remote(MATCHING_REMOTE_PATTERN)
        self.assert_allowed("git -C .claude push origin feature-x")

    def test_push_allowlist_mismatch_blocked(self):
        self.set_harness_push_remote(MISMATCHING_REMOTE_PATTERN)
        self.assert_denied(
            "git -C .claude push origin feature-x",
            reason_contains="harness_push_remote",
        )

    def test_push_allowlist_key_absent_blocks_all(self):
        self.set_harness_push_remote(None)
        self.assert_denied(
            "git -C .claude push origin feature-x",
            reason_contains="harness_push_remote",
        )
        # fail-closed applies from inside the harness repo too
        self.assert_denied(
            "git push origin feature-x",
            cwd=self.harness,
            reason_contains="harness_push_remote",
        )


class TestRepoContextAttribution(GuardrailEnv):
    def test_repo_context_attribution(self):
        # Key absent: harness pushes blocked in every invocation form ...
        self.set_harness_push_remote(None)
        self.assert_denied("git -C .claude push origin feature-x")
        self.assert_denied("cd .claude && git push origin feature-x")
        # ... while the SAME push in the project repo is not subject to the
        # harness allowlist and passes.
        self.assert_allowed("git push origin feature-x")

        # Key present and matching: both harness forms pass.
        self.set_harness_push_remote(MATCHING_REMOTE_PATTERN)
        self.assert_allowed("git -C .claude push origin feature-x")
        self.assert_allowed("cd .claude && git push origin feature-x")


# ---------------------------------------------------------------------------
# Marker logic gone: a file at the old approvals path grants nothing
# ---------------------------------------------------------------------------
class TestMarkerLogicGone(GuardrailEnv):
    def test_marker_logic_gone(self):
        approvals = self.repo / ".claude" / "approvals"
        approvals.mkdir(parents=True)
        marker = approvals / "{0}_main_merge.json".format(PLAN_NAME)
        marker.write_text(
            json.dumps({"approved_by": "user", "plan": PLAN_NAME}),
            encoding="utf-8",
        )
        # The marker grants nothing: protected-branch ops still flat-blocked.
        self.assert_denied("git push origin main")
        self.assert_denied(
            'git merge integration/{0} -m "merge: final"'.format(PLAN_NAME)
        )
        self.assertTrue(marker.exists(), "hook must not consume the stale marker")
        # The approvals-directory Bash backstop is retired with the marker:
        # merely referencing the old path is no longer a special deny.
        self.assert_allowed("ls .claude/approvals")


# ---------------------------------------------------------------------------
# 9. FLAGGED EXTRA: normal operations under the PR law must pass
# ---------------------------------------------------------------------------
class TestNormalOperationsPassFlaggedExtra(GuardrailEnv):
    def setUp(self):
        super().setUp()
        git(self.repo, "branch", "integration/{0}".format(PLAN_NAME))
        git(self.repo, "branch", "{0}-phase-02".format(PLAN_NAME))
        git(self.repo, "checkout", "integration/{0}".format(PLAN_NAME))

    def test_phase_close_operations_allowed(self):
        for command in [
            "git push origin {0}-phase-02".format(PLAN_NAME),
            'git merge {0}-phase-02 -m "merge: phase 02"'.format(PLAN_NAME),
            "git push origin integration/{0}".format(PLAN_NAME),
            "git branch -d {0}-phase-02".format(PLAN_NAME),
            "git push origin --delete {0}-phase-02".format(PLAN_NAME),
        ]:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_pr_law_gh_commands_allowed(self):
        for command in [
            'gh pr create --title "feat: x" --body "body"',
            "gh pr view 12",
            "gh pr checks 12",
        ]:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_harness_close_operations_allowed_with_matching_key(self):
        self.set_harness_push_remote(MATCHING_REMOTE_PATTERN)
        git(self.harness, "branch", "integration/{0}".format(PLAN_NAME))
        for command in [
            "git -C .claude push origin integration/{0}".format(PLAN_NAME),
            "cd .claude && git push -u origin integration/{0}".format(PLAN_NAME),
        ]:
            with self.subTest(command=command):
                self.assert_allowed(command)


# ---------------------------------------------------------------------------
# 10. FLAGGED EXTRA: non-git commands pass through (no false positives)
# ---------------------------------------------------------------------------
class TestNonGitCommandsPassFlaggedExtra(GuardrailEnv):
    def test_allowed(self):
        for command in [
            "ls -la",
            "python3 -m unittest discover .claude/harness/tests",
            "grep -rn 'git push --force' docs/",
            "echo done && cat README.md",
        ]:
            with self.subTest(command=command):
                self.assert_allowed(command)


# ---------------------------------------------------------------------------
# 11. FLAGGED EXTRA: Stop-hook regression + settings registration (python3)
# ---------------------------------------------------------------------------
def _run_closing(payload):
    return subprocess.run(
        [sys.executable, str(CLOSING_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestClosingHookRegressionFlaggedExtra(GuardrailEnv):
    def test_hook_contract_unchanged(self):
        marker_path = PROJECT_ROOT / ".claude" / "phase_closing.json"
        self.assertFalse(
            marker_path.exists(),
            "pre-existing real phase_closing.json -- aborting to avoid clobber",
        )
        learnings = self.repo / "learnings.md"
        session = "unittest-regression-session-p2"
        try:
            # no marker -> allow
            r = _run_closing({"session_id": session})
            self.assertEqual(0, r.returncode)
            self.assertEqual("", r.stdout.strip())

            # marker + matching session + missing learnings -> block
            marker_path.write_text(
                json.dumps(
                    {
                        "session_id": session,
                        "plan_name": PLAN_NAME,
                        "phase": 2,
                        "learnings_path": str(learnings),
                    }
                ),
                encoding="utf-8",
            )
            r = _run_closing({"session_id": session})
            out = json.loads(r.stdout)
            self.assertEqual("block", out.get("decision"))
            self.assertTrue(marker_path.exists())

            # non-matching session -> no-op allow, marker untouched
            r = _run_closing({"session_id": "some-other-session"})
            self.assertEqual(0, r.returncode)
            self.assertEqual("", r.stdout.strip())
            self.assertTrue(marker_path.exists())

            # learnings file written -> allow + marker self-deletes
            learnings.write_text("**Branch:** main\n", encoding="utf-8")
            r = _run_closing({"session_id": session})
            self.assertEqual(0, r.returncode)
            self.assertEqual("", r.stdout.strip())
            self.assertFalse(marker_path.exists())
        finally:
            if marker_path.exists():
                marker_path.unlink()

    def test_hooks_registered_with_stdlib_python3(self):
        settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        pre_hooks = json.dumps(settings.get("hooks", {}).get("PreToolUse", []))
        stop_hooks = json.dumps(settings.get("hooks", {}).get("Stop", []))
        self.assertIn("git_guardrails.py", pre_hooks)
        self.assertIn("enforce_phase_closing.py", stop_hooks)
        for blob in (pre_hooks, stop_hooks):
            self.assertIn("python3", blob)
            self.assertNotIn("venv/bin/python", blob)
        deny = json.dumps(settings.get("permissions", {}).get("deny", []))
        self.assertIn(".env", deny, ".env read-denies must remain")
        self.assertNotIn("approvals", deny, "approvals deny rules are retired")
