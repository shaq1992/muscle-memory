"""Stop-event hook enforcing the orchestrated GRILLING session's handback.

A grilling session (commands/orchestrated_grill.md) stops on EVERY question
-- each AskUserQuestion round and each `linger` exchange ends a turn, with no
question cap -- so it cannot live under hooks/enforce_handback.py, which
blocks every stop while the handback is still OPEN. This hook is that hook's
grilling sibling: every stop while the handback is `Status: OPEN` is ALLOWED,
and the shape checks apply only once the file carries a TERMINAL status.

SHARED CONTRACTS (edit in lockstep):
  - The MARKER. .claude/grill_handback_session.json, written by the session
    in commands/orchestrated_grill.md Step 0a item 2 (and, once armed there,
    by hooks/arm_handback_marker.py). Its key set -- session_id, plan_name,
    session_number, handback_path, requirements_doc_path -- is OWNED by
    commands/orchestrated_grill.md and shared with hooks/arm_handback_marker.py
    and this hook: any change to it updates all three files together. This
    hook never reads .claude/handback_session.json (enforce_handback.py's
    marker), and enforce_handback.py never reads this one -- the two are
    mutually exclusive by construction.
  - The SCHEMA. The lean-handback shape, its Status vocabulary, the
    "Terminal-state checks" and the abandon text are OWNED by
    harness/templates/grill_handback_schema.md. The structural-observation
    line shape and its closed tag vocabulary, and the read-receipt semantics,
    are INHERITED from harness/templates/handback_schema.md; the tag
    vocabulary is enforced through the shared parser in
    harness/scripts/handback_validation.py. A schema change updates this
    hook in lockstep.
  - The RECEIPT LOGIC. The dispatch-manifest location, loading and receipt
    comparison are imported from hooks/enforce_handback.py, never
    duplicated here, so the two hooks cannot drift apart on it.

No marker, an unreadable or malformed marker, or a marker whose session_id
does not match this invocation's session_id (read from the Stop payload, as
enforce_handback.py does) is a structural no-op -- the hook allows
unconditionally. A marker with no handback_path also allows (fail soft).

Checks, in order, each blocking with a reason that names the failed check:
  1. a file exists at the marker's handback_path -- a missing handback is
     blocked with an instruction to write the OPEN stub per Step 0a of
     commands/orchestrated_grill.md (stubs are written before the first
     question, so a grilling session that stops without one has skipped it);
  2. a "Status:" line is present and carries a value from the closed
     vocabulary OPEN / PARTIAL / ABANDONED / COMPLETE;
  3. READ-RECEIPT VERIFICATION, for every status except ABANDONED, mirroring
     enforce_handback.py exactly: when a dispatch manifest exists at
     docs/orchestration/<plan>/dispatches/<NN>.json (plan and NN from the
     marker), the receipt must match it. A missing or unreadable manifest is
     a structural no-op. Like the sibling hook, this runs on OPEN stops too:
     the first question of a freshly dispatched session is exactly the
     minute-one moment the receipt exists for, and the block is within the
     session's power to clear once (fix the receipt), so it cannot stall the
     grilling question after question;
  4. OPEN -> ALLOW, keeping the marker in place so the obligation still
     fires once the session writes a terminal status;
  5. ABANDONED -> nothing else is required (the Status line alone);
  6. PARTIAL or COMPLETE -> the five "##" sections are present in the
     schema's order (Requirements doc, Decisions at a glance, Open questions,
     For the orchestrator, Structural observations); there is NO "## Delta"
     section; each Structural observations line matches
     "- <tag> | <description>" with a tag from the closed vocabulary (or the
     section reads "none"); and the requirements doc exists and is
     non-empty. The doc path is the marker's requirements_doc_path, falling
     back to the first line of the "## Requirements doc" section only when
     the marker carries none. The "## Decisions at a glance" bullet ceiling
     is judgement and is never counted here.
On a pass at a terminal status the hook removes the grill marker.

Every block message prints the abandon path's minimal content VERBATIM (the
grill schema's "The abandon path" block), because a blocked session has by
definition already failed to guess the required shape.

Deliberately ignores the "stop_hook_active" re-entry flag: every block
condition is within the model's control, so re-blocking on each retry until
the file is correct is the intended behavior, not a runaway loop.

Stdlib-only, ASCII-only.
"""

import json
import os
import re
import sys

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HOOK_DIR)
PROJECT_DIR = os.path.dirname(CLAUDE_DIR)
MARKER_PATH = os.path.join(CLAUDE_DIR, "grill_handback_session.json")

# Receipt logic lives in the sibling hook and the observation parser in the
# shared validation module; import both rather than re-deriving them. Importing
# enforce_handback has no side effects beyond putting harness/scripts on
# sys.path (its main() runs only under __main__), so this stays safe on every
# Stop event. Both paths are computed from THIS hook's location.
sys.path.insert(0, HOOK_DIR)
sys.path.insert(0, os.path.join(CLAUDE_DIR, "harness", "scripts"))
from enforce_handback import (  # noqa: E402
    _load_manifest,
    _manifest_path_for,
    _verify_receipt,
)
from handback_validation import (  # noqa: E402
    parse_observations,
    section_bounds,
)

STATUS_RE = re.compile(r"^Status:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
DELTA_RE = re.compile(r"^##[ \t]+Delta\b", re.MULTILINE)
STATUS_VOCABULARY = ("OPEN", "PARTIAL", "ABANDONED", "COMPLETE")
SECTIONED_STATUSES = ("PARTIAL", "COMPLETE")
REQUIRED_SECTIONS = (
    "## Requirements doc",
    "## Decisions at a glance",
    "## Open questions",
    "## For the orchestrator",
    "## Structural observations",
)

# The minimal content that unblocks this hook, verbatim from
# harness/templates/grill_handback_schema.md "The abandon path". Printed in
# every block reason -- not described, not pointed at.
ABANDON_MINIMUM = (
    "Status: ABANDONED\n"
    "\n"
    "The user ended the grilling before any requirement was settled; no "
    "requirements doc was written.\n"
)


def _allow():
    sys.exit(0)


def _block(reason):
    full = (
        "{0}\n\nThe MINIMAL content that unblocks this, verbatim -- a status "
        "field and one sentence, nothing else:\n\n{1}".format(
            reason, ABANDON_MINIMUM
        )
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
    except (OSError, UnicodeDecodeError):
        return None


def _heading_indexes(lines, heading):
    return [i for i, line in enumerate(lines) if line.strip() == heading]


def _section_failures(lines):
    """Missing or out-of-order required sections, as readable strings."""
    missing = [h for h in REQUIRED_SECTIONS if not _heading_indexes(lines, h)]
    if missing:
        return [
            "missing section(s) {0}".format(
                ", ".join("'{0}'".format(h) for h in missing)
            )
        ]
    firsts = [_heading_indexes(lines, h)[0] for h in REQUIRED_SECTIONS]
    if firsts != sorted(firsts):
        found = sorted(REQUIRED_SECTIONS, key=lambda h: firsts[
            REQUIRED_SECTIONS.index(h)])
        return [
            "sections are out of order -- found {0}".format(
                ", ".join("'{0}'".format(h) for h in found)
            )
        ]
    return []


def _doc_path_from_section(lines):
    bounds = section_bounds(lines, "## Requirements doc")
    if bounds is None:
        return None
    for line in lines[bounds[0]:bounds[1]]:
        if line.strip():
            return line.strip().strip("`")
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
    doc_path = marker.get("requirements_doc_path")

    if not handback_path:
        _allow()
        return

    resolved_path = _resolve_path(handback_path)

    if not os.path.isfile(resolved_path):
        _block(
            "Grill handback is missing: {0} (plan: {1}, session: {2}). Write "
            "the stub now, per Step 0a of commands/orchestrated_grill.md: "
            "'Status: OPEN' plus the two-line read receipt ('- Rows:' and "
            "'- Prompt-SHA256:'). Stops while the stub is OPEN are then "
            "allowed.".format(handback_path, plan_name, session_number)
        )
        return

    content = _read_text(resolved_path)
    if content is None:
        _block(
            "Grill handback at {0} could not be read. Fix the file before "
            "stopping.".format(handback_path)
        )
        return

    match = STATUS_RE.search(content)
    if match is None:
        _block(
            "Grill handback check failed: {0} has no 'Status:' line. The "
            "header is a 'Status:' line carrying one of {1}.".format(
                handback_path, " / ".join(STATUS_VOCABULARY)
            )
        )
        return

    status = match.group(1)
    if status not in STATUS_VOCABULARY:
        _block(
            "Grill handback check failed: {0} carries 'Status: {1}', which "
            "is outside the closed vocabulary {2} (case-sensitive).".format(
                handback_path, status, " / ".join(STATUS_VOCABULARY)
            )
        )
        return

    if status != "ABANDONED":
        manifest = _load_manifest(
            _manifest_path_for(plan_name, session_number)
        )
        if manifest is not None:
            receipt_failures = _verify_receipt(content, manifest)
            if receipt_failures:
                _block(
                    "Read-receipt verification failed: {0} does not match "
                    "the dispatch manifest for plan {1} session {2}: "
                    "{3}. Rebuild the receipt from the dispatched prompt "
                    "file itself ({4}): '- Rows:' lists the E-IDs from the "
                    "first cell of each row in the prompt's rows block, "
                    "comma-separated, and '- Prompt-SHA256:' is the output "
                    "of `sha256sum` on that prompt file.".format(
                        handback_path,
                        plan_name,
                        session_number,
                        "; ".join(receipt_failures),
                        manifest.get("prompt_path", "<unknown>"),
                    )
                )
                return

    if status == "OPEN":
        # Normal state of a session still grilling: allow, keep the marker.
        _allow()
        return

    if status in SECTIONED_STATUSES:
        lines = content.splitlines()
        failures = _section_failures(lines)

        if DELTA_RE.search(content):
            failures.append(
                "it carries a '## Delta' section -- a grill handback has "
                "none; the orchestrator authors any state rows itself from "
                "the requirements doc. Remove the section"
            )

        obs_failures = []
        obs_bounds = section_bounds(lines, "## Structural observations")
        if obs_bounds is not None:
            parse_observations(lines[obs_bounds[0]:obs_bounds[1]], obs_failures)
        failures.extend(obs_failures)

        if not doc_path:
            doc_path = _doc_path_from_section(lines)
        if not doc_path:
            failures.append(
                "no requirements doc path (the marker has no "
                "requirements_doc_path and '## Requirements doc' names none)"
            )
        else:
            doc_text = _read_text(_resolve_path(doc_path))
            if doc_text is None:
                failures.append(
                    "the requirements doc does not exist (or cannot be "
                    "read) at {0} -- write it BEFORE finalizing the "
                    "handback".format(doc_path)
                )
            elif not doc_text.strip():
                failures.append(
                    "the requirements doc at {0} is empty".format(doc_path)
                )

        if failures:
            _block(
                "Grill handback check failed: {0} is 'Status: {1}' but:\n"
                "{2}\n\nA PARTIAL or COMPLETE grill handback carries, after "
                "the Status line and read receipt, exactly these sections in "
                "order: {3} -- and no '## Delta'. Fix the above, then stop "
                "again.".format(
                    handback_path,
                    status,
                    "\n".join("- {0}".format(f) for f in failures),
                    ", ".join("'{0}'".format(s) for s in REQUIRED_SECTIONS),
                )
            )
            return

    try:
        os.remove(MARKER_PATH)
    except OSError:
        pass
    _allow()


if __name__ == "__main__":
    main()
