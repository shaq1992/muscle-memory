"""PreToolUse hook: Edit/Write isolation for an orchestrator session.

While .claude/orchestrator_session.json names THIS session, Edit, Write and
NotebookEdit are confined to an allowlist:

  1. the state file the marker names (state_path);
  2. docs/orchestration/;
  3. docs/prompts/;
  4. the session scratchpad (any path with a "scratchpad" component -- it
     lives outside the project tree and has no fixed location).

This is an ANTI-DRIFT GUARDRAIL, not a sandbox. A Bash heredoc bypasses it
entirely, and so does any other write that does not go through those three
tools. It exists to catch an orchestrator drifting into doing the
implementation work itself, which is a mistake made by accident. It stops
nothing done on purpose, and no reader should be left thinking otherwise.
The orchestrator can still CAUSE code to be written -- through a sub-agent,
which is a different session and unaffected.

No marker, or a marker whose session_id does not match this invocation, is a
structural no-op: Edit/Write behavior is entirely unchanged. The marker is
never consumed here; the orchestrator removes it when its work is done.

Fires on a different matcher (Edit|Write|NotebookEdit) than
git_guardrails.py (Bash), so the two never interact.

Allow = exit 0 with no stdout (the normal permission flow continues).
Deny  = PreToolUse JSON decision on stdout, exit 0.
Fail-open on malformed payloads and unreadable markers.
"""

import json
import os
import sys

HOOK_DIR = os.path.dirname(os.path.realpath(__file__))
CLAUDE_DIR = os.path.dirname(HOOK_DIR)
PROJECT_DIR = os.path.dirname(CLAUDE_DIR)
MARKER_PATH = os.path.join(CLAUDE_DIR, "orchestrator_session.json")

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


def _allowlist_text(state_path):
    return (
        "  1. the state file: {0}\n"
        "  2. docs/orchestration/\n"
        "  3. docs/prompts/\n"
        "  4. the session scratchpad".format(state_path)
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

    if not os.path.isfile(MARKER_PATH):
        _allow()
        return

    try:
        with open(MARKER_PATH, "r", encoding="utf-8") as f:
            marker = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError):
        _allow()
        return

    if not isinstance(marker, dict) or marker.get("session_id") != payload.get(
        "session_id"
    ):
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
    state_path = marker.get("state_path") or ""

    if state_path and resolved == _resolve(state_path):
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
            _allowlist_text(state_path or "(none recorded in the marker)"),
            MARKER_PATH,
        )
    )


if __name__ == "__main__":
    main()
