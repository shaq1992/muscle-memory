"""Behavioral tests for the Phase 2 guardrail-hook contract (PR git law).

Contract classes 1-8 below are the ten ratified test cases from the phase
prompt. Classes 12-13 are the Phase 3 contract cases (parameters read from
the consolidated .claude/preferences.md; inline-default fallback when it is
absent). Classes 9-11 are EXPLICITLY FLAGGED EXTRAS beyond the contract:
  9  - allow-path regression guard (normal phase/PR-law operations must pass;
       protects against a fail-closed rewrite that bricks every git call)
  10 - non-git passthrough guard (quoted git-looking strings, plain commands)
  11 - settings.json registration (bare python3, no venv, no approvals deny
       rules). Its former closing-hook contract test moved to
       test_closing_hook.py when Phase 4 added the content checks.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import json
import shutil
import unittest

from helpers import (
    BASE_PARAMS,
    GUARDRAIL_HOOK,
    MATCHING_REMOTE_PATTERN,
    MISMATCHING_REMOTE_PATTERN,
    PLAN_NAME,
    SETTINGS_JSON,
    GuardrailEnv,
    decision_and_reason,
    git,
    run_hook,
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
# 4. Protected branch: any PROJECT-repo push targeting it is flat-blocked
#    (harness-repo pushes are governed solely by the allowlist -- class 6b)
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

    def test_project_main_push_blocked_even_with_harness_key(self):
        # the harness allowlist key never loosens the PROJECT-repo law
        self.set_harness_push_remote(MATCHING_REMOTE_PATTERN)
        self.assert_denied("git push origin main")


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


# ---------------------------------------------------------------------------
# 6b. Harness main: the allowlist is the ONLY gate (self-improver sync path).
#     The protected-branch push block is project-repo law and must not fire
#     on harness-repo pushes; the fail-closed allowlist still governs them.
# ---------------------------------------------------------------------------
class TestHarnessMainPushAllowlistOnly(GuardrailEnv):
    def test_harness_main_push_allowed_with_matching_key(self):
        self.set_harness_push_remote(MATCHING_REMOTE_PATTERN)
        self.assert_allowed("git -C .claude push origin main")
        # bare push while ON harness main
        self.assert_allowed("git push origin main", cwd=self.harness)

    def test_harness_main_push_key_absent_blocked(self):
        self.set_harness_push_remote(None)
        self.assert_denied(
            "git -C .claude push origin main",
            reason_contains="harness_push_remote",
        )

    def test_harness_main_push_mismatching_remote_blocked(self):
        self.set_harness_push_remote(MISMATCHING_REMOTE_PATTERN)
        self.assert_denied(
            "git -C .claude push origin main",
            reason_contains="harness_push_remote",
        )

    def test_harness_main_force_push_still_blocked(self):
        # destructive-op law is universal; the exemption never reaches it
        self.set_harness_push_remote(MATCHING_REMOTE_PATTERN)
        self.assert_denied("git -C .claude push --force origin main")


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
# 11. FLAGGED EXTRA: settings registration (python3). The former
# test_hook_contract_unchanged is SUPERSEDED by test_closing_hook.py (Phase 4
# learnings revision): a bare-existence learnings file no longer satisfies
# the Stop hook, and the plan-level ledger check resolves against the hook's
# own project root, so the contract now runs through a hook copy in a temp
# tree over there.
# ---------------------------------------------------------------------------
class TestClosingHookRegistrationFlaggedExtra(GuardrailEnv):
    @unittest.skipUnless(
        SETTINGS_JSON.is_file(),
        "settings.json is a gitignored environment file: present only in the "
        "live .claude checkout, absent from a linked worktree checkout",
    )
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


# ---------------------------------------------------------------------------
# 12. Phase 3 contract: parameters resolved from the single preferences.md
# ---------------------------------------------------------------------------
class TestParamsReadFromPreferencesMd(GuardrailEnv):
    def test_params_read_from_preferences_md(self):
        # protected_branch comes from the key block, not the inline default:
        # with a custom value, 'main' is no longer protected and the custom
        # branch is. (The block also carries the branch-pattern keys --
        # integration_branch_prefix, phase_branch_pattern,
        # phase_number_padding -- proving the single-file block parses; the
        # hook takes no branch-name-pattern decision observable beyond this.)
        self.params_file.write_text(
            BASE_PARAMS.replace(
                "protected_branch: main", "protected_branch: trunk"
            ),
            encoding="utf-8",
        )
        self.assert_denied(
            "git push origin trunk", reason_contains="trunk"
        )
        self.assert_allowed("git push origin feature-x:main")

        # harness_push_remote comes from the same file's key block.
        self.set_harness_push_remote(MATCHING_REMOTE_PATTERN)
        self.assert_allowed("git -C .claude push origin feature-x")
        self.set_harness_push_remote(MISMATCHING_REMOTE_PATTERN)
        self.assert_denied(
            "git -C .claude push origin feature-x",
            reason_contains="harness_push_remote",
        )


# ---------------------------------------------------------------------------
# 13. Phase 3 contract: absent preferences.md -> inline defaults still work
# ---------------------------------------------------------------------------
class TestMissingPreferencesFileFallsBack(GuardrailEnv):
    def test_missing_preferences_file_falls_back_to_defaults(self):
        self.params_file.unlink()

        # Run a COPY of the hook from inside the temp tree so its
        # hook-relative fallback candidate cannot find the real project's
        # preferences.md -- only the inline defaults remain.
        hook_home = self.repo.parent / "hookhome"
        hook_dir = hook_home / ".claude" / "hooks"
        hook_dir.mkdir(parents=True)
        hook_copy = hook_dir / "git_guardrails.py"
        shutil.copyfile(str(GUARDRAIL_HOOK), str(hook_copy))

        def verdict(command):
            return decision_and_reason(
                run_hook(command, self.repo, hook_path=hook_copy)
            )

        # Default protected_branch ('main') still enforced.
        v, reason = verdict("git push origin main")
        self.assertEqual("deny", v, "default protected branch must hold")
        # Ordinary project pushes still pass (hook functions, no crash).
        v, _ = verdict("git push origin feature-x")
        self.assertEqual("allow", v)
        # Harness pushes stay fail-closed: no file means no allowlist key.
        v, reason = verdict("git -C .claude push origin feature-x")
        self.assertEqual("deny", v)
        self.assertIn("harness_push_remote", reason)


# ---------------------------------------------------------------------------
# 14. Harness attribution covers linked worktrees of the harness repo.
# Failure prevented: a harness plan editing via a linked worktree (e.g.
# .claude/worktrees/<plan>) could push to an ARBITRARY remote, because
# attribution matched only a repo root whose basename is ".claude" -- a
# linked worktree's root carries the worktree's own name, so its pushes
# silently bypassed the fail-closed harness_push_remote allowlist.
# ---------------------------------------------------------------------------
class TestHarnessWorktreePushAllowlist(GuardrailEnv):
    def _add_harness_worktree(self, dest, branch):
        git(self.harness, "worktree", "add", str(dest), "-b", branch)
        return dest

    def test_worktree_push_key_absent_blocked(self):
        wt = self._add_harness_worktree(
            self.harness / "worktrees" / "wt", "wt-branch"
        )
        self.set_harness_push_remote(None)
        # both invocation forms: cwd inside the worktree, and -C from outside
        self.assert_denied(
            "git push origin wt-branch",
            cwd=wt,
            reason_contains="harness_push_remote",
        )
        self.assert_denied(
            "git -C .claude/worktrees/wt push origin wt-branch",
            reason_contains="harness_push_remote",
        )

    def test_worktree_push_matching_remote_allowed(self):
        wt = self._add_harness_worktree(
            self.harness / "worktrees" / "wt", "wt-branch"
        )
        self.set_harness_push_remote(MATCHING_REMOTE_PATTERN)
        self.assert_allowed("git push origin wt-branch", cwd=wt)
        self.assert_allowed("git -C .claude/worktrees/wt push origin wt-branch")

    def test_worktree_push_mismatching_remote_blocked(self):
        wt = self._add_harness_worktree(
            self.harness / "worktrees" / "wt", "wt-branch"
        )
        self.set_harness_push_remote(MISMATCHING_REMOTE_PATTERN)
        self.assert_denied(
            "git push origin wt-branch",
            cwd=wt,
            reason_contains="harness_push_remote",
        )

    def test_worktree_outside_harness_dir_still_attributed(self):
        # attribution follows the gitdir pointer, not the worktree's location
        wt = self._add_harness_worktree(
            self.repo.parent / "outside_wt", "outside-branch"
        )
        self.set_harness_push_remote(None)
        self.assert_denied(
            "git push origin outside-branch",
            cwd=wt,
            reason_contains="harness_push_remote",
        )

    def test_project_repo_worktree_not_attributed_as_harness(self):
        # a linked worktree of the PROJECT repo is not a harness push and is
        # never subject to the harness allowlist
        proj_wt = self.repo.parent / "proj_wt"
        git(self.repo, "worktree", "add", str(proj_wt), "-b", "proj-branch")
        self.set_harness_push_remote(None)
        self.assert_allowed("git push origin proj-branch", cwd=proj_wt)
