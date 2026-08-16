"""PreToolUse hook: Edit/Write isolation for an orchestrator session.

Per-plan marker scheme (D10). Each orchestrator session writes its own marker
at .claude/orchestrator_<plan_name>_session.json, so concurrent orchestrators
on DIFFERENT plans coexist without overwriting each other's pointer -- the
single-slot orchestrator_session.json was last-writer-wins, and the second
write silently disarmed the first orchestrator's guardrail (fail-open).

This hook scans ALL markers matching orchestrator_*_session.json and matches
on session_id. While at least one marker names THIS session, Edit, Write and
NotebookEdit are confined to an allowlist:

  1. the state file(s) the matching marker(s) name (state_path -- the UNION
     when several markers name this session);
  2. docs/orchestration/;
  3. docs/prompts/;
  4. the session scratchpad (any path with a "scratchpad" component -- it
     lives outside the project tree and has no fixed location).

FAIL-CLOSED on a corrupt marker: a marker file that cannot be parsed, or
whose content is not a JSON object, DENIES all guarded writes -- for every
session -- naming the corrupt path. The hook cannot prove a corrupt marker is
not this session's, and silently skipping it is the fail-open bug this scheme
replaces. The remedy is stated in the deny reason: delete the named file.

A readable marker naming a DIFFERENT session never constrains this one --
dispatched implementation sessions must write code -- and no marker at all is
a structural no-op. The legacy single-slot orchestrator_session.json does not
match the scan pattern and is inert; so are the other *_session.json marker
families (handback_session.json, improve_session.json), which belong to
different hooks.

This is an ANTI-DRIFT GUARDRAIL, not a sandbox. A Bash heredoc bypasses it
entirely, and so does any other write that does not go through those three
tools. It exists to catch an orchestrator drifting into doing the
implementation work itself, which is a mistake made by accident. It stops
nothing done on purpose, and no reader should be left thinking otherwise.
The orchestrator can still CAUSE code to be written -- through a sub-agent,
which is a different session and unaffected.

Markers are never consumed here; each orchestrator removes its own marker
when its work is done.

Fires on a different matcher (Edit|Write|NotebookEdit) than
git_guardrails.py (Bash), so the two never interact.

Allow = exit 0 with no stdout (the normal permission flow continues).
Deny  = PreToolUse JSON decision on stdout, exit 0.
Fail-open on a malformed hook PAYLOAD (the harness-side contract);
fail-closed on a malformed MARKER (the orchestrator-side contract).
"""

import fnmatch
import json
import os
import sys

HOOK_DIR = os.path.dirname(os.path.realpath(__file__))
CLAUDE_DIR = os.path.dirname(HOOK_DIR)
PROJECT_DIR = os.path.dirname(CLAUDE_DIR)
MARKER_GLOB = "orchestrator_*_session.json"

GUARDED_TOOLS = ("Edit", "Write", "NotebookEdit")
PATH_KEYS = ("file_path", "notebook_path")

ALLOWED_DIRS = ("docs/orchestration/", "docs/prompts/")
SCRATCHPAD_COMPONENT = "scratchpad"


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


def _resolve(path):
    if not os.path.isabs(path):
        path = os.path.join(PROJECT_DIR, path)
    return os.path.realpath(path)


def _under(child, parent):
    parent = parent.rstrip(os.sep)
    return child == parent or child.startswith(parent + os.sep)


def _in_scratchpad(resolved):
    return SCRATCHPAD_COMPONENT in resolved.split(os.sep)


def _scan_markers():
    """Return (matching_paths_to_markers, corrupt_paths).

    A marker is corrupt when it cannot be parsed as JSON or its content is
    not an object. Readable markers are returned regardless of session_id;
    the caller filters on it.
    """
    markers = []
    corrupt = []
    try:
        names = sorted(os.listdir(CLAUDE_DIR))
    except OSError:
        return markers, corrupt
    for name in names:
        if not fnmatch.fnmatch(name, MARKER_GLOB):
            continue
        path = os.path.join(CLAUDE_DIR, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError, OSError):
            corrupt.append(path)
            continue
        if not isinstance(data, dict):
            corrupt.append(path)
            continue
        markers.append((path, data))
    return markers, corrupt


def _allowlist_text(state_paths):
    if state_paths:
        first = "  1. the state file(s): {0}".format(", ".join(state_paths))
    else:
        first = "  1. the state file: (none recorded in the marker)"
    return (
        first + "\n"
        "  2. docs/orchestration/\n"
        "  3. docs/prompts/\n"
        "  4. the session scratchpad"
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _allow()
        return

    if not isinstance(payload, dict) or payload.get("tool_name") not in GUARDED_TOOLS:
        _allow()
        return

    markers, corrupt = _scan_markers()

    if corrupt:
        _deny(
            "Orchestrator isolation is FAIL-CLOSED on a corrupt marker: "
            "{0} cannot be parsed, so this hook cannot tell whether it names "
            "this session. No Edit/Write/NotebookEdit call proceeds until it "
            "is removed. If that orchestrator is dead, delete the file: "
            "{1}".format(
                ", ".join(os.path.basename(p) for p in corrupt),
                ", ".join(corrupt),
            )
        )
        return

    matching = [
        (path, data)
        for path, data in markers
        if data.get("session_id") == payload.get("session_id")
    ]
    if not matching:
        _allow()
        return

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        _allow()
        return

    target = None
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            target = value
            break
    if target is None:
        _allow()
        return

    resolved = _resolve(target)
    state_paths = [
        data.get("state_path")
        for _, data in matching
        if isinstance(data.get("state_path"), str) and data.get("state_path")
    ]

    for state_path in state_paths:
        if resolved == _resolve(state_path):
            _allow()
            return

    for rel in ALLOWED_DIRS:
        if _under(resolved, _resolve(rel)):
            _allow()
            return

    if _in_scratchpad(resolved):
        _allow()
        return

    _deny(
        "Orchestrator isolation: {0} targets {1}, which is outside this "
        "orchestrator session's allowlist:\n{2}\n\n"
        "The orchestrator does not do the implementation work itself -- it "
        "writes state, prompts and handback ingestion, and delegates "
        "everything else to a dispatched session or a sub-agent. If this "
        "session is not orchestrating, remove {3}.".format(
            payload.get("tool_name"),
            resolved,
            _allowlist_text(state_paths),
            ", ".join(path for path, _ in matching),
        )
    )


if __name__ == "__main__":
    main()
