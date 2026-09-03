"""Stop-event hook enforcing the orchestrated-session handback obligation.

.claude/handback_session.json is written deterministically by the companion
UserPromptSubmit hook hooks/arm_handback_marker.py the moment the dispatched
prompt carrying an "## Orchestration" block is SUBMITTED, before the model
has read a word of it; the session-side write in
commands/grill_and_implement.md Step 0a item 2 is retained as a fallback
(re-writing the same marker is idempotent). This hook then blocks that
session's closing turn until a schema-valid handback exists at the path the
marker names -- and only that file: the check is scoped to the single path
the marker names, never to any other document that happens to carry a
"Status:" line.

That "## Orchestration" heading string is named here for documentation only.
This hook never parses a prompt; it keys off .claude/handback_session.json
alone (the prompt parsing lives in arm_handback_marker.py). The heading
itself is owned by commands/orchestrator.md Step 7, so a rename there means
updating this docstring too.

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
  3. READ-RECEIPT VERIFICATION (schema v2, D3), for every status except
     ABANDONED: when a dispatch manifest exists at
     docs/orchestration/<plan>/dispatches/<NN>.json (written by
     harness/scripts/assemble_dispatch.py; plan and NN come from the
     marker), the receipt's "- Rows:" E-ID list must SET-match the
     manifest's row_ids and its "- Prompt-SHA256:" must equal the
     manifest's prompt_sha256 (case-insensitive). Receipt semantics are
     owned by harness/templates/handback_schema.md. A MISSING or
     unreadable manifest is a structural no-op -- the manifest is the
     ORCHESTRATOR's artifact and a session cannot legitimately create it,
     so blocking on its absence would put the session outside its own
     power to unblock. This check runs on EVERY Stop evaluation,
     question pauses included: the FIRST pause of a freshly dispatched
     session is exactly the minute-one moment the receipt exists for. A
     receipt block never consumes a pause declaration;
  4. that value is a TERMINAL state, UNLESS the session has declared a
     question pause (below). OPEN is in the file vocabulary but is not
     terminal: the stub is written at session START, so accepting OPEN
     would make this hook demand a file the session already wrote in minute
     one. OPEN is reserved as positive evidence that a session DIED, and a
     session reaching its Stop hook is alive;
  5. for PARTIAL and COMPLETE only -- the statuses that claim real work
     landed -- the three required sections are present.
ABANDONED is deliberately exempt from checks 3 and 5. The abandon path must
cost about THREE LINES: a status field and one sentence. Every block message
prints that minimal content VERBATIM, because a blocked session has by
definition already failed to guess the required shape, and pointing it at a
schema is telling it to guess again.

THE MANUAL MODE. `python3 hooks/enforce_handback.py --check-receipt
<handback_path> [--manifest <manifest_path>]` runs check 3's verification
logic standalone -- same code, no Stop event, no marker. Absent --manifest
the path is derived from the standard layout
(.../<plan>/handbacks/<NN>.md -> .../<plan>/dispatches/<NN>.json). Unlike
the hook path, a missing manifest FAILS here (exit 1): the manual caller is
the orchestrator, the manifest's owner, for whom its absence is a real
defect. Prints "OK: ..." exit 0, or "FAIL <check>: ..." lines exit 1.

THE QUESTION PAUSE. A session that stops to put a question to the user --
the STOP-and-ask ambiguity protocol, or the grilling step of
commands/grill_and_implement.md -- is NOT a session that died, and must
never be pushed to declare itself ABANDONED or PARTIAL to hand control back.
Such a session declares the pause by writing .claude/handback_pause.json
carrying its own session_id; check 3 then accepts the non-terminal status,
the declaration is CONSUMED (single use, so every pause is re-declared), and
the handback marker is DELIBERATELY LEFT IN PLACE so the obligation still
fires at the real close.

The pause declaration is a hook-owned ephemeral file, not part of the
handback document: the SESSION-level Status vocabulary and the four-part
handback shape owned by harness/templates/handback_schema.md are unchanged
by it, and a pause leaves the handback exactly as the schema describes it --
`Status: OPEN`, read receipt intact. Checks 1 and 2 are NOT waived by a
pause: a session that never wrote its stub is blocked whether it is pausing
or closing, which is the failure this hook exists to catch.

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
PAUSE_MARKER_PATH = os.path.join(CLAUDE_DIR, "handback_pause.json")

STATUS_RE = re.compile(r"^Status:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
RECEIPT_ROWS_RE = re.compile(r"^- Rows:[ \t]*(.*?)[ \t]*$", re.MULTILINE)
RECEIPT_SHA_RE = re.compile(
    r"^- Prompt-SHA256:[ \t]*([0-9A-Fa-f]+)[ \t]*$", re.MULTILINE
)
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

# The other cheap exit: a session pausing to ASK, which is not a death and
# must not be dressed up as one. Printed verbatim alongside ABANDON_MINIMUM
# whenever the status is merely unadvanced, for the same reason -- a blocked
# session must not have to guess.
PAUSE_INSTRUCTION = (
    "If you are NOT closing but PAUSING to put a question to the user -- the "
    "STOP-and-ask ambiguity protocol, or the grilling step -- do NOT advance "
    "the status: a pause is not a death, and ABANDONED would misreport a "
    "healthy session. Declare the pause instead, then stop again. Verbatim, "
    "one Bash line:\n"
    "\n"
    '  echo "{\\"session_id\\": \\"$CLAUDE_CODE_SESSION_ID\\"}" > '
    ".claude/handback_pause.json\n"
    "\n"
    "The handback stays 'Status: OPEN' with its read receipt intact. The "
    "declaration is single use -- this hook consumes it, keeps the handback "
    "marker, and the handback obligation fires again at the real close."
)


def _allow():
    sys.exit(0)


def _block(reason, extra=None):
    full = "{0}\n\nThe MINIMAL content that unblocks this, verbatim -- a status field and one sentence, nothing else:\n\n{1}".format(
        reason, ABANDON_MINIMUM
    )
    if extra:
        full = "{0}\n{1}".format(full, extra)
    print(json.dumps({"decision": "block", "reason": full}))
    sys.exit(0)


def _consume_pause_declaration(session_id):
    """True if THIS session declared a question pause; consumes the file."""
    if not os.path.isfile(PAUSE_MARKER_PATH):
        return False
    try:
        with open(PAUSE_MARKER_PATH, "r", encoding="utf-8") as f:
            declaration = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError):
        return False
    if not isinstance(declaration, dict):
        return False
    if declaration.get("session_id") != session_id:
        return False
    try:
        os.remove(PAUSE_MARKER_PATH)
    except OSError:
        pass
    return True


def _resolve_path(path):
    if os.path.isabs(path):
        return path
    return os.path.join(PROJECT_DIR, path)


def _manifest_path_for(plan_name, session_number):
    """Conventional dispatch-manifest path, or None if underivable."""
    if not plan_name or session_number is None:
        return None
    try:
        session = "{0:02d}".format(int(session_number))
    except (TypeError, ValueError):
        session = str(session_number)
    return os.path.join(
        PROJECT_DIR,
        "docs",
        "orchestration",
        str(plan_name),
        "dispatches",
        "{0}.json".format(session),
    )


def _load_manifest(path):
    """The manifest dict, or None if absent, unreadable or malformed."""
    if path is None or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, ValueError, OSError):
        return None
    if not isinstance(manifest, dict):
        return None
    if not isinstance(manifest.get("row_ids"), list):
        return None
    if not isinstance(manifest.get("prompt_sha256"), str):
        return None
    return manifest


def _verify_receipt(content, manifest):
    """List of human-readable failures; empty means the receipt verifies."""
    failures = []
    rows_match = RECEIPT_ROWS_RE.search(content)
    sha_match = RECEIPT_SHA_RE.search(content)
    if rows_match is None:
        failures.append("the receipt has no '- Rows:' line")
    if sha_match is None:
        failures.append("the receipt has no '- Prompt-SHA256:' line")
    if failures:
        return failures

    expected_ids = [str(rid) for rid in manifest["row_ids"]]
    got_ids = [tok.strip() for tok in rows_match.group(1).split(",")
               if tok.strip()]
    if set(got_ids) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(got_ids))
        unexpected = sorted(set(got_ids) - set(expected_ids))
        detail = []
        if missing:
            detail.append("missing {0}".format(", ".join(missing)))
        if unexpected:
            detail.append("unexpected {0}".format(", ".join(unexpected)))
        failures.append(
            "row-ID mismatch ({0})".format("; ".join(detail))
        )

    expected_sha = manifest["prompt_sha256"]
    if sha_match.group(1).lower() != expected_sha.lower():
        failures.append(
            "Prompt-SHA256 mismatch: receipt has {0}, manifest has "
            "{1}".format(sha_match.group(1), expected_sha)
        )
    return failures


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

    if status not in TERMINAL_STATUSES:
        if _consume_pause_declaration(current_session_id):
            # A declared question pause: allow the turn to close WITHOUT a
            # terminal status, and keep the marker so the real close is
            # still enforced.
            _allow()
            return
        _block(
            "Handback schema check failed: {0} is still 'Status: {1}' -- the "
            "unadvanced stub. OPEN is reserved as evidence that a session "
            "died, so it is not a state a live session may CLOSE in. Advance "
            "the status to one of {2} before stopping.".format(
                handback_path, status, " / ".join(TERMINAL_STATUSES)
            ),
            extra=PAUSE_INSTRUCTION,
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


def _derive_manifest_from_handback(handback_path):
    """.../<plan>/handbacks/<NN>.md -> .../<plan>/dispatches/<NN>.json."""
    directory, filename = os.path.split(handback_path)
    parent, leaf = os.path.split(directory)
    if leaf != "handbacks" or not filename.endswith(".md"):
        return None
    return os.path.join(parent, "dispatches", filename[:-3] + ".json")


def check_receipt_cli(argv):
    """Manual entry point: verify a receipt without the Stop event."""
    args = [a for a in argv[1:] if a != "--check-receipt"]
    manifest_path = None
    if "--manifest" in args:
        i = args.index("--manifest")
        if i + 1 >= len(args):
            print("FAIL usage: --manifest needs a path")
            return 1
        manifest_path = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        print(
            "FAIL usage: --check-receipt <handback_path> "
            "[--manifest <manifest_path>]"
        )
        return 1
    handback_path = args[0]

    if manifest_path is None:
        manifest_path = _derive_manifest_from_handback(handback_path)
        if manifest_path is None:
            print(
                "FAIL usage: cannot derive a manifest path from {0} (not "
                "the standard .../<plan>/handbacks/<NN>.md layout); pass "
                "--manifest".format(handback_path)
            )
            return 1

    content = _read_text(handback_path)
    if content is None:
        print("FAIL handback: cannot read {0}".format(handback_path))
        return 1
    if not os.path.isfile(manifest_path):
        print(
            "FAIL manifest: no dispatch manifest at {0}".format(
                manifest_path
            )
        )
        return 1
    manifest = _load_manifest(manifest_path)
    if manifest is None:
        print(
            "FAIL manifest: unreadable or malformed manifest at {0}".format(
                manifest_path
            )
        )
        return 1

    failures = _verify_receipt(content, manifest)
    if failures:
        for failure in failures:
            print("FAIL receipt: {0}".format(failure))
        return 1
    print(
        "OK: receipt matches the dispatch manifest at {0} (rows: {1}; "
        "sha256: {2})".format(
            manifest_path,
            ",".join(str(rid) for rid in manifest["row_ids"]),
            manifest["prompt_sha256"],
        )
    )
    return 0


if __name__ == "__main__":
    if "--check-receipt" in sys.argv:
        sys.exit(check_receipt_cli(sys.argv))
    main()
