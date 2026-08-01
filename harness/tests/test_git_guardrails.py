"""Behavioral tests for the Phase 2 git-autonomy machinery (harness-improv-v3).

The seven ratified behavioral tests (classes 1-7 below), plus ONE explicitly
FLAGGED extra (class 8: approvals-directory Bash backstop) that guards the
"Claude mechanically cannot create the marker" deliverable -- see the phase
report for the flag.

Local-only suite (never committed): .claude/ is gitignored.
Run with: venv/bin/pytest .claude/harness/tests/ -v
"""

import json
import subprocess

import pytest

from conftest import (
    CLOSING_HOOK,
    HELPER_SCRIPT,
    PROJECT_ROOT,
    SETTINGS_JSON,
    SETUP_SCRIPT,
    VENV_PYTHON,
    _git,
    decision,
    make_marker,
    run_hook,
)

FAKE_PAT = "FAKE_PAT_1a2b3c4d5e_not_a_real_token"


# ---------------------------------------------------------------------------
# Behavioral test 1: destructive git commands always denied
# ---------------------------------------------------------------------------
class TestDestructiveCommandsBlocked:
    @pytest.mark.parametrize(
        "command",
        [
            "git push --force",
            "git push -f origin feature-x",
            # implementation extension of the ratified force-push rule:
            # --force-with-lease is caught by the same --force* pattern
            "git push --force-with-lease origin main",
            "git reset --hard HEAD~1",
            "git branch -D harness-improv-v3-phase-02",
            "git clean -f",
            "git clean -fd",
        ],
    )
    def test_denied(self, fake_repo, command):
        assert decision(run_hook(command, fake_repo)) == "deny"

    def test_denied_even_with_marker_present(self, fake_repo):
        make_marker(fake_repo)
        assert decision(run_hook("git push --force origin main", fake_repo)) == "deny"


# ---------------------------------------------------------------------------
# Behavioral test 2: protected-branch ops denied without the approval marker
# ---------------------------------------------------------------------------
class TestProtectedBranchGatedWithoutMarker:
    @pytest.mark.parametrize(
        "command",
        [
            'git merge --no-ff integration/harness-improv-v3 -m "merge: final"',
            "git push origin main",
            "git push origin main:main",
            "git push origin HEAD:main",
            "git push",  # bare push while ON main targets main
        ],
    )
    def test_denied_on_main_without_marker(self, fake_repo, command):
        assert decision(run_hook(command, fake_repo)) == "deny"


# ---------------------------------------------------------------------------
# Behavioral test 3: marker allows the gated ops; consumed by the merge
# ---------------------------------------------------------------------------
class TestMarkerAllowsAndIsConsumed:
    def test_push_to_main_allowed_with_marker(self, fake_repo):
        marker = make_marker(fake_repo)
        assert decision(run_hook("git push origin main", fake_repo)) == "allow"
        # push alone does not consume the marker; the merge does
        assert marker.exists()

    def test_merge_allowed_with_marker_then_consumed(self, fake_repo):
        marker = make_marker(fake_repo)
        cmd = 'git merge --no-ff integration/harness-improv-v3 -m "merge: final"'
        assert decision(run_hook(cmd, fake_repo)) == "allow"
        assert not marker.exists(), "marker must be deleted after the allowed merge"
        # one-shot: the same merge is denied once the marker is gone
        assert decision(run_hook(cmd, fake_repo)) == "deny"

    def test_compound_merge_and_push_covered_by_single_marker(self, fake_repo):
        marker = make_marker(fake_repo)
        cmd = (
            'git merge --no-ff integration/harness-improv-v3 -m "merge: final" '
            "&& git push origin main"
        )
        assert decision(run_hook(cmd, fake_repo)) == "allow"
        assert not marker.exists()


# ---------------------------------------------------------------------------
# Behavioral test 4: normal phase operations pass through untouched
# ---------------------------------------------------------------------------
class TestNormalPhaseOperationsPass:
    @pytest.fixture
    def integration_repo(self, fake_repo):
        _git(fake_repo, "branch", "integration/harness-improv-v3")
        _git(fake_repo, "branch", "harness-improv-v3-phase-02")
        _git(fake_repo, "checkout", "integration/harness-improv-v3")
        return fake_repo

    @pytest.mark.parametrize(
        "command",
        [
            "git push origin harness-improv-v3-phase-02",
            'git merge --no-ff harness-improv-v3-phase-02 -m "merge: phase 02"',
            "git push origin integration/harness-improv-v3",
            "git branch -d harness-improv-v3-phase-02",
            "git push origin --delete harness-improv-v3-phase-02",
        ],
    )
    def test_allowed(self, integration_repo, command):
        assert decision(run_hook(command, integration_repo)) == "allow"


# ---------------------------------------------------------------------------
# Behavioral test 5: non-git Bash commands pass through (no false positives)
# ---------------------------------------------------------------------------
class TestNonGitCommandsPass:
    @pytest.mark.parametrize(
        "command",
        [
            "ls -la",
            "venv/bin/pytest tests/ -v",
            # quoted git-looking string must NOT trip the matcher
            "grep -rn 'git push --force' docs/",
            "echo done && cat README.md",
            "venv/bin/python scripts/orch_health_check.py",
        ],
    )
    def test_allowed(self, fake_repo, command):
        assert decision(run_hook(command, fake_repo)) == "allow"


# ---------------------------------------------------------------------------
# Behavioral test 6: credential helper -- push works, token never leaks
# ---------------------------------------------------------------------------
class TestCredentialHelper:
    def test_push_succeeds_and_token_never_leaks(self, fake_repo, tmp_path):
        (fake_repo / ".env").write_text(
            "ODATA_URL=https://example.invalid\nGIT_PAT={0}\n".format(FAKE_PAT),
            encoding="utf-8",
        )
        setup = subprocess.run(
            ["bash", str(SETUP_SCRIPT)],
            cwd=str(fake_repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert setup.returncode == 0, setup.stderr
        assert FAKE_PAT not in setup.stdout + setup.stderr

        helper_cfg = subprocess.run(
            ["git", "config", "--local", "credential.helper"],
            cwd=str(fake_repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert helper_cfg.returncode == 0
        assert "git_credential_env.sh" in helper_cfg.stdout

        remote = tmp_path / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(remote)],
            check=True,
            capture_output=True,
            timeout=30,
        )
        _git(fake_repo, "remote", "add", "origin", str(remote))
        push_cmd = ["git", "push", "origin", "main"]
        assert FAKE_PAT not in " ".join(push_cmd)
        push = subprocess.run(
            push_cmd,
            cwd=str(fake_repo),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert push.returncode == 0, push.stderr
        assert FAKE_PAT not in push.stdout + push.stderr

    def test_helper_emits_credentials_from_env_file(self, fake_repo):
        (fake_repo / ".env").write_text(
            "GIT_PAT={0}\n".format(FAKE_PAT), encoding="utf-8"
        )
        result = subprocess.run(
            ["bash", str(HELPER_SCRIPT), "get"],
            cwd=str(fake_repo),
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        lines = result.stdout.strip().splitlines()
        assert "username=x-access-token" in lines
        assert "password={0}".format(FAKE_PAT) in lines

    def test_helper_silent_for_non_get_actions(self, fake_repo):
        (fake_repo / ".env").write_text(
            "GIT_PAT={0}\n".format(FAKE_PAT), encoding="utf-8"
        )
        result = subprocess.run(
            ["bash", str(HELPER_SCRIPT), "store"],
            cwd=str(fake_repo),
            input="",
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == ""


# ---------------------------------------------------------------------------
# Behavioral test 7: enforce_phase_closing regression guard
# ---------------------------------------------------------------------------
def _run_closing(payload):
    return subprocess.run(
        [str(VENV_PYTHON), str(CLOSING_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestEnforcePhaseClosingRegression:
    def test_hook_contract_unchanged(self, tmp_path):
        marker_path = PROJECT_ROOT / ".claude" / "phase_closing.json"
        assert not marker_path.exists(), (
            "pre-existing real phase_closing.json -- aborting to avoid clobber"
        )
        learnings = tmp_path / "learnings.md"
        session = "pytest-regression-session-p2"
        try:
            # no marker -> allow
            r = _run_closing({"session_id": session})
            assert r.returncode == 0 and r.stdout.strip() == ""

            # marker + matching session + missing learnings -> block
            marker_path.write_text(
                json.dumps(
                    {
                        "session_id": session,
                        "plan_name": "harness-improv-v3",
                        "phase": 2,
                        "learnings_path": str(learnings),
                    }
                ),
                encoding="utf-8",
            )
            r = _run_closing({"session_id": session})
            out = json.loads(r.stdout)
            assert out.get("decision") == "block"
            assert marker_path.exists()

            # non-matching session -> no-op allow, marker untouched
            r = _run_closing({"session_id": "some-other-session"})
            assert r.returncode == 0 and r.stdout.strip() == ""
            assert marker_path.exists()

            # learnings file written -> allow + marker self-deletes
            learnings.write_text("**Branch:** main\n", encoding="utf-8")
            r = _run_closing({"session_id": session})
            assert r.returncode == 0 and r.stdout.strip() == ""
            assert not marker_path.exists()
        finally:
            if marker_path.exists():
                marker_path.unlink()

    def test_both_hooks_registered_in_settings(self):
        settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        stop_hooks = json.dumps(settings.get("hooks", {}).get("Stop", []))
        assert "enforce_phase_closing.py" in stop_hooks
        pre_hooks = json.dumps(settings.get("hooks", {}).get("PreToolUse", []))
        assert "git_guardrails.py" in pre_hooks


# ---------------------------------------------------------------------------
# FLAGGED EXTRA (beyond the seven ratified tests): approvals-dir Bash backstop.
# Guards the deliverable "Claude mechanically cannot create the marker" --
# settings.json deny rules cover Write/Edit; this covers arbitrary Bash forms.
# ---------------------------------------------------------------------------
class TestApprovalsWriteBackstopFlaggedExtra:
    @pytest.mark.parametrize(
        "command",
        [
            "touch .claude/approvals/harness-improv-v3_main_merge.json",
            "echo '{}' > .claude/approvals/harness-improv-v3_main_merge.json",
            "cp /tmp/x.json .claude/approvals/harness-improv-v3_main_merge.json",
        ],
    )
    def test_denied(self, fake_repo, command):
        assert decision(run_hook(command, fake_repo)) == "deny"
