"""Stop-event hook enforcing the phase-closing "write learnings" obligation.

No marker, or a marker whose session_id does not match this invocation, is a
structural no-op -- the hook allows unconditionally. Enforcement only ever
applies to the session that created the marker.

Deliberately ignores the "stop_hook_active" re-entry flag: the block
condition here is fully within the model's control (write the missing file),
so re-blocking on every retry until the file is correct is the intended
behavior, not a runaway loop.
"""

import json
import os
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HOOK_DIR)
PROJECT_DIR = os.path.dirname(CLAUDE_DIR)
MARKER_PATH = os.path.join(CLAUDE_DIR, "phase_closing.json")


def _allow():
    sys.exit(0)


def _block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def _resolve_learnings_path(learnings_path):
    if os.path.isabs(learnings_path):
        return learnings_path
    return os.path.join(PROJECT_DIR, learnings_path)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
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

    learnings_path = marker.get("learnings_path")
    plan_name = marker.get("plan_name")
    phase = marker.get("phase")

    if not learnings_path:
        _allow()
        return

    resolved_path = _resolve_learnings_path(learnings_path)

    if not os.path.isfile(resolved_path):
        _block(
            "Phase-closing learnings file is missing: {0} (plan: {1}, phase: {2}). "
            "Write the learnings file before stopping.".format(
                learnings_path, plan_name, phase
            )
        )
        return

    os.remove(MARKER_PATH)
    _allow()


if __name__ == "__main__":
    main()
