"""PreToolUse guardrail hook for Bash: deterministic git-safety gating.

Part of the harness git layer (see .claude/harness/procedures/git_strategy.md,
"Enforcement" section). Deterministic pattern matching, never model judgement.

Two jobs, plus a push-remote guard:

  1. Always deny destructive git commands: push --force / -f (any --force*
     variant), reset --hard, branch -D, clean -f.
  2. Flat-block EVERY Claude-initiated path to the protected branch -- no
     marker, no exceptions:
       - git merge while on the protected branch;
       - any git push whose destination is the protected branch (explicit
         refspec incl. the "origin main:main" form, bare push from the
         protected branch, --all / --branches / --mirror, --delete of it);
       - gh pr merge (PR merges are user-only under the PR law; the user
         runs them as !-prefixed commands).
  3. Push-remote allowlist (fail-closed): a git push attributed to the
     HARNESS repo (the nested repo at .claude/) is allowed only when the
     resolved remote URL matches the harness_push_remote parameter. Key
     absent = ALL harness pushes denied, naming the missing key.

Repo-context attribution: each command segment's effective directory is
tracked across `cd` segments and `git -C` flags; a segment operates on the
harness repo when its enclosing git work-tree root is a `.claude` directory.

Allow = exit 0 with no stdout (the normal permission flow continues).
Deny  = PreToolUse JSON decision on stdout, exit 0.
Fail-open on malformed payloads and on parameter-read errors; fail-CLOSED
only for the harness push-remote guard (by design).

Parameters come from .claude/preferences/git_parameters.md ("key: value"
lines, one per line, no prose on the line); inline defaults apply when the
file is absent, which keeps the hook portable.
"""

import fnmatch
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
}

HARNESS_DIR_NAME = ".claude"
PUSH_REMOTE_KEY = "harness_push_remote"

_PARAM_LINE = re.compile(r"^([a-z][a-z0-9_]*):[ \t]+(\S.*)$")

_SHELL_OPERATORS = {"&&", "||", ";", ";;", "|", "|&", "&", "(", ")"}

_COMMAND_WRAPPERS = {"env", "command", "nohup", "time"}

_GIT_TWO_ARG_GLOBALS = {
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
        if os.path.isdir(os.path.join(path, HARNESS_DIR_NAME)):
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


def _repo_root(directory):
    """Walk up from directory to the nearest dir containing .git; None if outside a repo."""
    path = os.path.abspath(directory)
    while True:
        if os.path.exists(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent


def _is_harness_repo(directory):
    root = _repo_root(directory)
    return root is not None and os.path.basename(root) == HARNESS_DIR_NAME


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


def _remote_url(git_dir, remote):
    """Resolve a push destination to a URL. Literal URLs pass through."""
    if "/" in remote or ":" in remote:
        return remote
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", remote],
            cwd=git_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _remote_matches(url, pattern):
    if any(c in pattern for c in "*?["):
        return fnmatch.fnmatch(url, pattern)
    return pattern in url


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


def _skip_wrappers(tokens):
    """Skip env-assignment prefixes and command wrappers; return start index."""
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t in _COMMAND_WRAPPERS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
            continue
        break
    return i


def _parse_git(tokens, base_dir):
    """Return (subcommand, args, git_dir) if this segment is a git invocation.

    git_dir is base_dir adjusted for any -C flags (cumulative, like git).
    """
    i = _skip_wrappers(tokens)
    n = len(tokens)
    if i >= n or os.path.basename(tokens[i]) != "git":
        return None
    i += 1
    git_dir = base_dir
    while i < n:
        t = tokens[i]
        if t == "-C":
            if i + 1 < n:
                git_dir = os.path.normpath(os.path.join(git_dir, tokens[i + 1]))
            i += 2
            continue
        if t in _GIT_TWO_ARG_GLOBALS:
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        break
    if i >= n:
        return None
    return tokens[i], list(tokens[i + 1:]), git_dir


def _parse_gh(tokens):
    """Return the list of gh positional args if this segment is a gh invocation."""
    i = _skip_wrappers(tokens)
    n = len(tokens)
    if i >= n or os.path.basename(tokens[i]) != "gh":
        return None
    positionals = []
    j = i + 1
    while j < n:
        t = tokens[j]
        if t.startswith("-"):
            # conservative: skip the flag only; a flag value that looks
            # positional cannot turn a non-merge command into "pr merge"
            j += 1
            continue
        positionals.append(t)
        j += 1
    return positionals


def _destructive_reason(sub, args):
    if sub == "push":
        for a in args:
            if a == "-f" or a.startswith("--force"):
                return "Force pushes are always blocked (git push --force / -f)."
    elif sub == "reset":
        if "--hard" in args:
            return "Hard resets are always blocked (git reset --hard)."
    elif sub == "branch":
        if "-D" in args or ("--force" in args and ("-d" in args or "--delete" in args)):
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


def _push_parts(args):
    """Split push args into (remote, refspecs, is_delete, pushes_all)."""
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
    remote = positionals[0] if positionals else "origin"
    return remote, positionals[1:], is_delete, pushes_all


def _push_targets_protected(refspecs, is_delete, pushes_all, protected,
                            effective_branch):
    if pushes_all:
        return True
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

    effective_cwd = os.path.abspath(cwd)
    branch_by_dir = {}

    for tokens in _split_segments(command):
        # Track `cd` so later segments are attributed to the right repo.
        i = _skip_wrappers(tokens)
        if i < len(tokens) and tokens[i] == "cd":
            target = tokens[i + 1] if i + 1 < len(tokens) else os.path.expanduser("~")
            effective_cwd = os.path.normpath(
                os.path.join(effective_cwd, os.path.expanduser(target))
            )
            continue

        gh_positionals = _parse_gh(tokens)
        if gh_positionals is not None:
            if gh_positionals[:2] == ["pr", "merge"]:
                _deny(
                    "gh pr merge is user-only: under the PR git law the USER "
                    "merges pull requests (into the protected branch "
                    "'{0}') with a !-prefixed command. Ask the user to run "
                    "it; do not merge PRs yourself.".format(protected)
                )
                return
            continue

        parsed = _parse_git(tokens, effective_cwd)
        if parsed is None:
            continue
        sub, args, git_dir = parsed

        reason = _destructive_reason(sub, args)
        if reason:
            _deny("{0} Offending command: {1}".format(reason, " ".join(tokens)))
            return

        dir_key = os.path.realpath(git_dir)
        if dir_key not in branch_by_dir:
            branch_by_dir[dir_key] = _current_branch(git_dir)

        if sub in ("checkout", "switch"):
            branch_by_dir[dir_key] = _checkout_target(args, branch_by_dir[dir_key])
            continue

        if sub == "merge" and branch_by_dir[dir_key] == protected:
            _deny(
                "git merge on the protected branch '{0}' is always blocked. "
                "Under the PR git law, changes reach '{0}' only through a "
                "pull request merged by the USER (! gh pr merge).".format(
                    protected
                )
            )
            return

        if sub == "push":
            remote, refspecs, is_delete, pushes_all = _push_parts(args)
            if _push_targets_protected(
                refspecs, is_delete, pushes_all, protected, branch_by_dir[dir_key]
            ):
                _deny(
                    "Pushes targeting the protected branch '{0}' are always "
                    "blocked. Under the PR git law, changes reach '{0}' only "
                    "through a pull request merged by the USER "
                    "(! gh pr merge).".format(protected)
                )
                return

            if _is_harness_repo(git_dir):
                pattern = params.get(PUSH_REMOTE_KEY)
                if not pattern:
                    _deny(
                        "Harness-repo pushes are fail-closed: no "
                        "'{0}' key found in "
                        ".claude/preferences/git_parameters.md. ALL pushes "
                        "from the harness repo at .claude/ are blocked until "
                        "the user adds the key naming the allowed remote "
                        "pattern.".format(PUSH_REMOTE_KEY)
                    )
                    return
                url = _remote_url(git_dir, remote)
                if url is None:
                    _deny(
                        "Harness-repo push blocked: could not resolve remote "
                        "'{0}' to a URL to check it against the '{1}' "
                        "allowlist (fail-closed).".format(remote, PUSH_REMOTE_KEY)
                    )
                    return
                if not _remote_matches(url, pattern):
                    _deny(
                        "Harness-repo push blocked: remote '{0}' ({1}) does "
                        "not match the '{2}' allowlist pattern '{3}'. Harness "
                        "pushes may only target that remote.".format(
                            remote, url, PUSH_REMOTE_KEY, pattern
                        )
                    )
                    return

    _allow()


if __name__ == "__main__":
    main()
