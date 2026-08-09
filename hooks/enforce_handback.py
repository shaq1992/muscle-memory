"""Stop-event hook enforcing the orchestrated-session handback obligation.

A dispatched session writes .claude/handback_session.json when it reads a
prompt carrying an "## Orchestration" block. This hook then blocks that
session's closing turn until a schema-valid handback exists at the path the
marker names -- and only that file: the check is scoped to the single path
the marker names, never to any other document that happens to carry a
"Status:" line.

That "## Orchestration" heading string is named here for documentation only.
This hook never parses a prompt; it keys off .claude/handback_session.json
alone. The heading itself is owned by commands/orchestrator.md Step 7, so a
rename there means updating this docstring too.

No marker, or a marker whose session_id does not match this invocation, is a
structural no-op -- the hook allows unconditionally. Enforcement only ever
applies to the session that created the marker, so an abandoned session's
marker never blocks anyone else.

This hook and enforce_phase_closing.py are MUTUALLY EXCLUSIVE by
construction: they read different marker files and neither honors the
other's. An orchestrated session writes a handback marker INSTEAD OF a
phase-closing marker; for it the handback replaces the per-phase learnings
file and the ledger merge entirely.

Checks, in order, each blocking with a reason that names the failed check:
  1. a file exists at the marker's handback_path;
  2. a "Status:" line is present and carries a value from the closed
     vocabulary OPEN / PARTIAL / ABANDONED / COMPLETE. This is the
     SESSION-level Status vocabulary, owned by
     harness/templates/handback_schema.md. It is NOT the PLAN-level
     vocabulary of an orchestrated plan's state file
     (harness/templates/state_schema.md), which is separate and never
     enforced here even though both fields are spelled "Status";
  3. that value is a TERMINAL state. OPEN is in the file vocabulary but is
     not terminal: the stub is written at session START, so accepting OPEN
     would make this hook demand a file the session already wrote in minute
     one. OPEN is reserved as positive evidence that a session DIED, and a
     session reaching its Stop hook is alive;
  4. for PARTIAL and COMPLETE only -- the statuses that claim real work
     landed -- the three required sections are present.
ABANDONED is deliberately exempt from check 4. The abandon path must cost
about THREE LINES: a status field and one sentence. Every block message
prints that minimal content VERBATIM, because a blocked session has by
definition already failed to guess the required shape, and pointing it at a
schema is telling it to guess again.

Deliberately ignores the "stop_hook_active" re-entry flag: the block
condition here is fully within the model's control (write the missing or
malformed file), so re-blocking on every retry until the state is correct is
the intended behavior, not a runaway loop.
"""

import json
import os
import re
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HOOK_DIR)
PROJECT_DIR = os.path.dirname(CLAUDE_DIR)
MARKER_PATH = os.path.join(CLAUDE_DIR, "handback_session.json")

STATUS_RE = re.compile(r"^Status:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
STATUS_VOCABULARY = ("OPEN", "PARTIAL", "ABANDONED", "COMPLETE")
TERMINAL_STATUSES = ("PARTIAL", "ABANDONED", "COMPLETE")
SECTIONED_STATUSES = ("PARTIAL", "COMPLETE")
REQUIRED_SECTIONS = (
    "## Delta",
    "## For the next session",
    "## Structural observations",
)

# The minimal content that unblocks this hook. Printed verbatim in every
# block reason -- not described, not pointed at.
ABANDON_MINIMUM = (
    "Status: ABANDONED\n"
    "\n"
    "Blocked on the staging credentials; nothing was changed.\n"
)


def _allow():
    sys.exit(0)


def _block(reason):
    full = "{0}\n\nThe MINIMAL content that unblocks this, verbatim -- a status field and one sentence, nothing else:\n\n{1}".format(
        reason, ABANDON_MINIMUM
    )
    print(json.dumps({"decision": "block", "reason": full}))
    sys.exit(0)


def _resolve_path(path):
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_DIR, path)


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _allow()
        return

    if not isinstance(payload, dict):
        _allow()
        return

    current_session_id = payload.get("session_id")

    if not os.path.isfile(MARKER_PATH):
        _allow()
        return

    try:
        with open(MARKER_PATH, "r", encoding="utf-8") as f:
            marker = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError):
        _allow()
        return

    if not isinstance(marker, dict) or marker.get("session_id") != current_session_id:
        _allow()
        return

    handback_path = marker.get("handback_path")
    plan_name = marker.get("plan_name")
    session_number = marker.get("session_number")

    if not handback_path:
        _allow()
        return

    resolved_path = _resolve_path(handback_path)

    if not os.path.isfile(resolved_path):
        _block(
            "Handback is missing: {0} (plan: {1}, session: {2}). An "
            "orchestrated session's handback is its whole durable output; "
            "write the file before stopping.".format(
                handback_path, plan_name, session_number
            )
        )
        return

    content = _read_text(resolved_path)
    if content is None:
        _block(
            "Handback at {0} could not be read. Fix the file before "
            "stopping.".format(handback_path)
        )
        return

    match = STATUS_RE.search(content)
    if match is None:
        _block(
            "Handback schema check failed: {0} has no 'Status:' line. The "
            "first part of a handback is the header -- a 'Status:' line "
            "carrying one of {1}.".format(
                handback_path, " / ".join(STATUS_VOCABULARY)
            )
        )
        return

    status = match.group(1)
    if status not in STATUS_VOCABULARY:
        _block(
            "Handback schema check failed: {0} carries 'Status: {1}', which "
            "is outside the closed vocabulary {2} (case-sensitive).".format(
                handback_path, status, " / ".join(STATUS_VOCABULARY)
            )
        )
        return

    if status not in TERMINAL_STATUSES:
        _block(
            "Handback schema check failed: {0} is still 'Status: {1}' -- the "
            "unadvanced stub. OPEN is reserved as evidence that a session "
            "died, so it is not a state a live session may close in. Advance "
            "the status to one of {2} before stopping.".format(
                handback_path, status, " / ".join(TERMINAL_STATUSES)
            )
        )
        return

    if status in SECTIONED_STATUSES:
        for section in REQUIRED_SECTIONS:
            if not re.search(
                r"^{0}[ \t]*$".format(re.escape(section)), content, re.MULTILINE
            ):
                _block(
                    "Handback schema check failed: {0} is 'Status: {1}' but "
                    "has no '{2}' section. A handback claiming work landed "
                    "carries all three sections -- {3} -- after the header. "
                    "Add the missing section before stopping.".format(
                        handback_path,
                        status,
                        section,
                        ", ".join("'{0}'".format(s) for s in REQUIRED_SECTIONS),
                    )
                )
                return

    os.remove(MARKER_PATH)
    _allow()


if __name__ == "__main__":
    main()
