"""UserPromptSubmit hook: deterministic ARMING of the handback marker.

Companion to enforce_handback.py, which enforces the orchestrated-session
handback obligation at Stop time but is a structural no-op unless
.claude/handback_session.json exists with a matching session_id. Before this
hook, that marker was written only by the dispatched session itself
(commands/grill_and_implement.md Step 0a item 2) -- model obedience, not
mechanism. A session that skipped Step 0a was never armed, and the Stop hook
silently allowed a free-form handback to close (observed: plan
peer-route-advantage session 40, 2026-09-03). This hook makes the arming
deterministic: the marker is written the moment the dispatched prompt is
SUBMITTED, before the model has read a word of it.

Trigger: the submitted prompt carries a "## Orchestration" block with a
"- **Handback:**" field. That is the SAME presence signal
commands/grill_and_implement.md keys its orchestrated mode on. The block's
shape is owned by commands/orchestrator.md Step 7 and produced by
harness/scripts/assemble_dispatch.py (orchestration_block()); this hook is a
third consumer of it, so a change to the heading or the bolded field names
there must update the regexes here in lockstep.

On trigger, the hook writes .claude/handback_session.json with EXACTLY the
key names and value shapes that grill_and_implement.md Step 0a item 2
specifies and enforce_handback.py reads:

    {
      "session_id":     <the UserPromptSubmit event's session_id>,
      "plan_name":      <plan name>,
      "session_number": <NN, as the string from the block>,
      "handback_path":  <verbatim value of the block's Handback: field>
    }

plan_name and session_number are parsed from the "- **Branch:**" field's
value, "<plan_name>-session-<NN>" (the value is the text on the field's own
line only -- the "(cut from ...)" continuation line is annotation, never part
of it); if the Branch field is absent or unparseable, they are derived from
the conventional handback path docs/orchestration/<plan>/handbacks/<NN>.md,
and failing that are written as null, which enforce_handback.py already
treats as manifest-underivable (its receipt check degrades to a structural
no-op while the handback obligation itself still fires).

The session-side write in grill_and_implement.md Step 0a item 2 remains in
place as a FALLBACK for projects whose settings.json predates this hook's
registration; re-writing the same marker is idempotent and harmless.

No "## Orchestration" block, no Handback field, or no usable session_id ->
exit 0 silently, writing nothing. FAIL SOFT everywhere: this hook must never
block or delay a prompt, so every parse oddity and every write failure exits
0 with no output. (On UserPromptSubmit, exit 2 blocks the prompt and stdout
is injected as context; this hook deliberately does neither.) The marker is
written atomically (temp file + os.replace) so a half-written file can never
trip enforce_orchestrator_isolation.py-style corruption handling downstream.

Stdlib-only, ASCII-only, like every hook in this corpus.
"""

import json
import os
import re
import sys
import tempfile

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HOOK_DIR)
MARKER_PATH = os.path.join(CLAUDE_DIR, "handback_session.json")

# The block heading, exactly as commands/orchestrator.md Step 7 fixes it and
# commands/grill_and_implement.md detects it.
BLOCK_HEADING_RE = re.compile(r"^## Orchestration[ \t]*$", re.MULTILINE)
# The next H2 heading ends the block's scope (by construction the block is
# appended last, so this is usually end-of-prompt).
NEXT_HEADING_RE = re.compile(r"^## ", re.MULTILINE)

# The bolded field lines per assemble_dispatch.py orchestration_block().
HANDBACK_FIELD_RE = re.compile(
    r"^-[ \t]*\*\*Handback:\*\*[ \t]*(\S+)[ \t]*$", re.MULTILINE
)
BRANCH_FIELD_RE = re.compile(
    r"^-[ \t]*\*\*Branch:\*\*[ \t]*(\S+)[ \t]*$", re.MULTILINE
)

# <plan_name>-session-<NN>, per orchestrator.md Step 7.
BRANCH_VALUE_RE = re.compile(r"^(.+)-session-(\d+)$")
# Conventional handback path fallback: .../docs/orchestration/<plan>/
# handbacks/<NN>.md.
HANDBACK_PATH_RE = re.compile(
    r"(?:^|/)docs/orchestration/([^/]+)/handbacks/([^/]+)\.md$"
)


def _parse_orchestration(prompt):
    """(handback_path, plan_name, session_number) from the prompt's
    "## Orchestration" block, or None when the prompt carries no block or
    the block has no Handback field. plan_name/session_number are None when
    underivable -- the caller still arms on the handback path alone."""
    if not isinstance(prompt, str):
        return None
    heading = BLOCK_HEADING_RE.search(prompt)
    if heading is None:
        return None
    block = prompt[heading.end():]
    nxt = NEXT_HEADING_RE.search(block)
    if nxt is not None:
        block = block[:nxt.start()]

    handback_match = HANDBACK_FIELD_RE.search(block)
    if handback_match is None:
        return None
    handback_path = handback_match.group(1)

    plan_name = None
    session_number = None
    branch_match = BRANCH_FIELD_RE.search(block)
    if branch_match is not None:
        value_match = BRANCH_VALUE_RE.match(branch_match.group(1))
        if value_match is not None:
            plan_name = value_match.group(1)
            session_number = value_match.group(2)
    if plan_name is None:
        path_match = HANDBACK_PATH_RE.search(handback_path)
        if path_match is not None:
            plan_name = path_match.group(1)
            session_number = path_match.group(2)
    return handback_path, plan_name, session_number


def _write_marker_atomically(marker):
    """Write MARKER_PATH via temp file + os.replace; exceptions propagate
    to main()'s fail-soft catch."""
    fd, tmp_path = tempfile.mkstemp(
        prefix=".handback_session.", suffix=".tmp", dir=CLAUDE_DIR
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(marker, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, MARKER_PATH)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if not isinstance(payload, dict):
        sys.exit(0)

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        # A marker without a real session_id can never legitimately match
        # a Stop event; arming with one would be noise, not enforcement.
        sys.exit(0)

    parsed = _parse_orchestration(payload.get("prompt"))
    if parsed is None:
        sys.exit(0)

    handback_path, plan_name, session_number = parsed
    _write_marker_atomically(
        {
            "session_id": session_id,
            "plan_name": plan_name,
            "session_number": session_number,
            "handback_path": handback_path,
        }
    )
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Fail SOFT: an arming hook must never block or delay a prompt.
        sys.exit(0)
