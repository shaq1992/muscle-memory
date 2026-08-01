"""Shared fixtures and helpers for the Phase 2 git-guardrails behavioral tests.

Local-only (never committed): .claude/ is gitignored.
Run with: venv/bin/pytest .claude/harness/tests/ -v
"""

import json
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GUARDRAIL_HOOK = PROJECT_ROOT / ".claude" / "hooks" / "git_guardrails.py"
CLOSING_HOOK = PROJECT_ROOT / ".claude" / "hooks" / "enforce_phase_closing.py"
SETUP_SCRIPT = (
    PROJECT_ROOT / ".claude" / "harness" / "scripts" / "setup_credential_helper.sh"
)
HELPER_SCRIPT = (
    PROJECT_ROOT / ".claude" / "harness" / "scripts" / "git_credential_env.sh"
)
SETTINGS_JSON = PROJECT_ROOT / ".claude" / "settings.json"
VENV_PYTHON = PROJECT_ROOT / "venv" / "bin" / "python"

PLAN_NAME = "harness-improv-v3"

GIT_PARAMETERS_CONTENT = """# Preference: Git Parameters (test fixture)

integration_branch_prefix: integration/
phase_branch_pattern: <plan_name>-phase-<NN>
phase_number_padding: 2
default_branch: main
protected_branch: main
approval_marker_path: .claude/approvals/<plan_name>_main_merge.json
"""


def _git(cwd, *args):
    """Run a git command in cwd; raise on failure."""
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def run_hook(command, cwd):
    """Feed a Bash PreToolUse payload to the guardrail hook; return the result."""
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }
    return subprocess.run(
        [str(VENV_PYTHON), str(GUARDRAIL_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
    )


def decision(result):
    """Map a hook subprocess result to 'allow' or 'deny'."""
    assert result.returncode == 0, (
        "hook exited non-zero (rc={0}): stdout={1!r} stderr={2!r}".format(
            result.returncode, result.stdout, result.stderr
        )
    )
    if not result.stdout.strip():
        return "allow"
    out = json.loads(result.stdout)
    return (
        out.get("hookSpecificOutput", {}).get("permissionDecision", "allow")
    )


def make_marker(repo, plan=PLAN_NAME):
    """Create an approval marker in the FIXTURE repo (never the real project)."""
    marker = repo / ".claude" / "approvals" / "{0}_main_merge.json".format(plan)
    marker.write_text(
        json.dumps({"approved_by": "user", "plan": plan}), encoding="utf-8"
    )
    return marker


@pytest.fixture
def fake_repo(tmp_path):
    """A throwaway git repo on branch main with fixture .claude/ scaffolding."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("test repo\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    prefs = repo / ".claude" / "preferences"
    prefs.mkdir(parents=True)
    (prefs / "git_parameters.md").write_text(
        GIT_PARAMETERS_CONTENT, encoding="utf-8"
    )
    (repo / ".claude" / "approvals").mkdir(parents=True)
    return repo
