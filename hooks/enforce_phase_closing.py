"""Stop-event hook enforcing the phase-closing "write learnings" obligation.

No marker, or a marker whose session_id does not match this invocation, is a
structural no-op -- the hook allows unconditionally. Enforcement only ever
applies to the session that created the marker.

Beyond existence of the file at the marker's learnings_path, the hook
validates the learnings schema and the plan ledger:
  1. the learnings file's first line starts with "**Branch:**";
  2. a "## Learnings" header is present in the file;
  3. the plan ledger at docs/learnings/<plan_name>_ledger.md carries a
     "Last merged: phase NN" stamp matching the marker's phase.
Each failed check blocks with a reason naming that specific check. Once all
checks pass, the hook self-deletes the marker and allows.

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
MARKER_PATH = os.path.join(CLAUDE_DIR, "phase_closing.json")

BRANCH_PREFIX = "**Branch:**"
LEARNINGS_HEADER = "## Learnings"
STAMP_RE = re.compile(r"^Last merged:\s*phase\s*(\d+)\s*$", re.MULTILINE)


def _allow():
    sys.exit(0)


def _block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
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

    resolved_path = _resolve_path(learnings_path)

    if not os.path.isfile(resolved_path):
        _block(
            "Phase-closing learnings file is missing: {0} (plan: {1}, phase: {2}). "
            "Write the learnings file before stopping.".format(
                learnings_path, plan_name, phase
            )
        )
        return

    content = _read_text(resolved_path)
    if content is None:
        _block(
            "Phase-closing learnings file at {0} could not be read. "
            "Fix the file before stopping.".format(learnings_path)
        )
        return

    first_line = content.split("\n", 1)[0].rstrip()
    if not first_line.startswith(BRANCH_PREFIX):
        _block(
            "Learnings schema check failed: the FIRST line of {0} must start "
            "with '{1}' (followed by the phase branch name). Found: {2!r}. "
            "Fix the first line before stopping.".format(
                learnings_path, BRANCH_PREFIX, first_line[:80]
            )
        )
        return

    if not re.search(
        r"^{0}\s*$".format(re.escape(LEARNINGS_HEADER)), content, re.MULTILINE
    ):
        _block(
            "Learnings schema check failed: {0} has no '{1}' header. The "
            "schema is '**Branch:** <name>' then '{1}' then bullets. Add the "
            "header before stopping.".format(learnings_path, LEARNINGS_HEADER)
        )
        return

    # Ledger freshness stamp: docs/learnings/<plan_name>_ledger.md must carry
    # 'Last merged: phase NN' matching the marker's phase.
    try:
        phase_int = int(phase)
    except (TypeError, ValueError):
        phase_int = None

    if plan_name and phase_int is not None:
        ledger_rel = os.path.join(
            "docs", "learnings", "{0}_ledger.md".format(plan_name)
        )
        ledger_content = _read_text(_resolve_path(ledger_rel))
        if ledger_content is None:
            _block(
                "Ledger check failed: {0} does not exist (or is unreadable). "
                "Merge this phase's learnings into the ledger and stamp it "
                "'Last merged: phase {1:02d}' before stopping.".format(
                    ledger_rel, phase_int
                )
            )
            return
        match = STAMP_RE.search(ledger_content)
        if match is None:
            _block(
                "Ledger check failed: {0} has no 'Last merged: phase NN' "
                "stamp line. Stamp it 'Last merged: phase {1:02d}' before "
                "stopping.".format(ledger_rel, phase_int)
            )
            return
        if int(match.group(1)) != phase_int:
            _block(
                "Ledger check failed: {0} is stamped 'Last merged: phase "
                "{1}' but this close is phase {2:02d}. Merge this phase's "
                "learnings and rewrite the stamp before stopping.".format(
                    ledger_rel, match.group(1), phase_int
                )
            )
            return

    os.remove(MARKER_PATH)
    _allow()


if __name__ == "__main__":
    main()
