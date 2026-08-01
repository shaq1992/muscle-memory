"""PreToolUse guardrail hook for Bash: deterministic git-safety gating.

Part of the harness git-autonomy layer (see
.claude/harness/procedures/git_strategy.md, "Enforcement" section).

Behavior (pattern matching, never model judgement):
  1. Always deny destructive git commands: push --force / -f (any --force*
     variant), reset --hard, branch -D, clean -f.
  2. Deny protected-branch operations unless the user-created approval
     marker exists: git merge while on the protected branch, and any git
     push whose destination is the protected branch (explicit refspec incl.
     the "origin main:main" form, bare push from the protected branch,
     --all / --branches / --mirror, --delete of the protected branch).
  3. Deny any Bash command that references the approvals directory -- the
     approval marker is mechanically user-creatable only (backstop to the
     settings.json Write/Edit deny rules).

The marker is one-shot: when a gated MERGE is allowed because the marker
exists, the marker is deleted after the decision. Issue the
integration-to-main merge and the main push as ONE compound command so a
single marker covers both.

Allow = exit 0 with no stdout (the normal permission flow continues).
Deny  = PreToolUse JSON decision on stdout, exit 0.
Fail-open on malformed payloads and on parameter-read errors.

Parameters come from .claude/preferences/git_parameters.md ("key: value"
lines, one per line, no prose on the line); inline defaults apply when the
file is absent, which keeps the hook portable.
"""

import glob
import json
import os
import re
import shlex
import subprocess
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
HOOK_PROJECT_DIR = os.path.dirname(os.path.dirname(HOOK_DIR))

DEFAULT_PARAMS = {
    "integration_branch_prefix": "integration/",
    "default_branch": "main",
    "protected_branch": "main",
    "approval_marker_path": ".claude/approvals/<plan_name>_main_merge.json",
}

APPROVALS_TOKEN = ".claude/approvals"

_PARAM_LINE = re.compile(r"^([a-z][a-z0-9_]*):[ \t]+(\S.*)$")

_SHELL_OPERATORS = {"&&", "||", ";", ";;", "|", "|&", "&", "(", ")"}

_COMMAND_WRAPPERS = {"env", "command", "nohup", "time"}

_GIT_TWO_ARG_GLOBALS = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
}

_PUSH_TWO_ARG_OPTS = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}


def _allow():
    sys.exit(0)


def _deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def _find_project_dir(cwd):
    """Ascend from cwd to the nearest dir containing .claude/; hook-relative fallback."""
    path = os.path.abspath(cwd)
    while True:
        if os.path.isdir(os.path.join(path, ".claude")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return HOOK_PROJECT_DIR
        path = parent


def _load_params(project_dir):
    params = dict(DEFAULT_PARAMS)
    candidates = [
        os.path.join(project_dir, ".claude", "preferences", "git_parameters.md"),
        os.path.join(HOOK_PROJECT_DIR, ".claude", "preferences", "git_parameters.md"),
    ]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    m = _PARAM_LINE.match(line.strip())
                    if m:
                        params[m.group(1)] = m.group(2).strip()
        except OSError:
            pass
        break
    return params


def _find_markers(project_dir, params):
    template = params.get(
        "approval_marker_path", DEFAULT_PARAMS["approval_marker_path"]
    )
    pattern = template.replace("<plan_name>", "*")
    return sorted(glob.glob(os.path.join(project_dir, pattern)))


def _current_branch(cwd):
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _split_segments(command):
    """Split a shell command into per-simple-command token lists.

    shlex with punctuation_chars keeps quoted strings intact, so a quoted
    'git push --force' inside e.g. a grep argument is a single token and
    never parses as a git command.
    """
    segments = []
    for line in command.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            lex = shlex.shlex(line, posix=True, punctuation_chars=True)
            lex.whitespace_split = True
            tokens = list(lex)
        except ValueError:
            tokens = line.split()
        current = []
        for tok in tokens:
            if tok in _SHELL_OPERATORS:
                if current:
                    segments.append(current)
                    current = []
            else:
                current.append(tok)
        if current:
            segments.append(current)
    return segments


def _parse_git(tokens):
    """Return (subcommand, args) if this segment is a git invocation, else None."""
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t in _COMMAND_WRAPPERS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
            continue
        break
    if i >= n or os.path.basename(tokens[i]) != "git":
        return None
    i += 1
    while i < n:
        t = tokens[i]
        if t in _GIT_TWO_ARG_GLOBALS:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        break
    if i >= n:
        return None
    return tokens[i], list(tokens[i + 1:])


def _destructive_reason(sub, args):
    if sub == "push":
        for a in args:
            if a == "-f" or a.startswith("--force"):
                return "Force pushes are always blocked (git push --force / -f)."
    elif sub == "reset":
        if "--hard" in args:
            return "Hard resets are always blocked (git reset --hard)."
    elif sub == "branch":
        if "-D" in args:
            return "Force branch deletion is always blocked (git branch -D); use -d."
    elif sub == "clean":
        for a in args:
            if a == "--force" or (
                a.startswith("-") and not a.startswith("--") and "f" in a[1:]
            ):
                return "Working-tree cleans are always blocked (git clean -f)."
    return None


def _checkout_target(args, current):
    """Best-effort tracking of the branch a checkout/switch lands on."""
    positionals = [a for a in args if not a.startswith("-")]
    if positionals:
        return positionals[0]
    return current


def _push_targets_protected(args, protected, effective_branch):
    positionals = []
    is_delete = False
    pushes_all = False
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a in _PUSH_TWO_ARG_OPTS:
            skip_next = True
            continue
        if a.startswith("-") and a != "-":
            if a in ("-d", "--delete"):
                is_delete = True
            if a in ("--all", "--branches", "--mirror"):
                pushes_all = True
            continue
        positionals.append(a)
    if pushes_all:
        return True
    refspecs = positionals[1:]
    dests = []
    if refspecs:
        if is_delete:
            dests = list(refspecs)
        else:
            for r in refspecs:
                r = r.lstrip("+")
                dest = r.split(":", 1)[1] if ":" in r else r
                dests.append(dest)
    elif effective_branch:
        dests = [effective_branch]
    for d in dests:
        if d.startswith("refs/heads/"):
            d = d[len("refs/heads/"):]
        if d == protected:
            return True
    return False


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _allow()
        return
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        _allow()
        return
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        _allow()
        return

    cwd = payload.get("cwd") or os.getcwd()
    project_dir = _find_project_dir(cwd)
    params = _load_params(project_dir)
    protected = params.get("protected_branch", "main")
    marker_template = params.get("approval_marker_path")

    if APPROVALS_TOKEN in command:
        _deny(
            "The approvals directory ({0}/) is user-managed only. Claude may not "
            "create, modify, delete, or otherwise touch approval markers; the "
            "user creates them with a !-prefixed command.".format(APPROVALS_TOKEN)
        )
        return

    segments = _split_segments(command)
    effective_branch = None
    consume_marker = False
    for tokens in segments:
        parsed = _parse_git(tokens)
        if parsed is None:
            continue
        sub, args = parsed

        reason = _destructive_reason(sub, args)
        if reason:
            _deny("{0} Offending command: {1}".format(reason, " ".join(tokens)))
            return

        if effective_branch is None:
            effective_branch = _current_branch(cwd)

        if sub in ("checkout", "switch"):
            effective_branch = _checkout_target(args, effective_branch)
            continue

        gated_merge = sub == "merge" and effective_branch == protected
        gated_push = sub == "push" and _push_targets_protected(
            args, protected, effective_branch
        )
        if gated_merge or gated_push:
            if not _find_markers(project_dir, params):
                _deny(
                    "Operation targets the protected branch '{0}' and requires "
                    "the user-created approval marker ({1}). Ask the user to "
                    "create it with a !-prefixed command; it is one-shot and "
                    "consumed by the allowed merge.".format(
                        protected, marker_template
                    )
                )
                return
            if gated_merge:
                consume_marker = True

    if consume_marker:
        for marker in _find_markers(project_dir, params):
            try:
                os.remove(marker)
            except OSError:
                pass
    _allow()


if __name__ == "__main__":
    main()
