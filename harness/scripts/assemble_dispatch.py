"""Assemble an orchestrated dispatch prompt and its dispatch manifest (D2).

Usage: python3 .claude/harness/scripts/assemble_dispatch.py
           --state <state_file> --body <body_file> --plan <plan_name>
           --session <NN> --branch <branch> --rows E001,E002,... --out <prompt_path>
           [--accumulation-branch <branch>] [--command <name>|none]

Run from the PROJECT ROOT with project-relative paths: the --state value is
echoed VERBATIM into the prompt's "State file:" field, and the reading
session resolves it against its own working directory.

The orchestrator authors only the task body; this script writes the WHOLE
prompt file. It ensures the body carries the receiving command's invocation
line (below), extracts the requested rows VERBATIM by E-ID from the state
file's ## Established table, appends the fixed ## Orchestration block --
heading, field names and value convention owned by commands/orchestrator.md
Step 7; the receiving command detects the block's PRESENCE, so its shape is
load-bearing -- and writes the per-session dispatch manifest to
<state_dir>/<plan_name>/dispatches/<NN>.json in the same run:

    {"plan_name", "session_number", "row_ids", "accumulation_branch",
     "prompt_path", "prompt_sha256"}

--accumulation-branch names the branch the plan's sessions are cut from and
merge back into; it defaults to integration/<plan_name>, and a plan that
declares a different one (e.g. fix/<name>) as a settled state-file row
passes it on every dispatch. It is ALWAYS emitted, both as the Branch
field's "(cut from <accumulation branch>)" continuation line and as the
"- **Accumulation branch:** <branch>" field on its own line immediately
after it. The field is read by commands/grill_and_implement.md (absent ->
integration/<plan_name>, for older prompts); hooks/arm_handback_marker.py
parses only the Branch field and ignores it. A change to its spelling must
update orchestrator.md Step 7 and grill_and_implement.md in lockstep.

prompt_sha256 is the SHA-256 (lowercase hex) over the EXACT BYTES of the
prompt file as written, so the manifest matches the prompt by construction.
The dispatched session echoes that hash (plus the row-ID list) in its
handback read receipt, and hooks/enforce_handback.py verifies the receipt
against this manifest.

Fail-closed: on any problem (malformed or missing E-ID, missing
## Established table, pre-existing prompt or manifest file -- session
numbers are never reused, a task body without exactly ONE TDD-posture
line, a body invoking a command other than --command, an invalid
--accumulation-branch or --command value) it prints
"FAIL <check>: <detail>" lines and exits 1 WITHOUT writing anything.
Success prints an "OK: ..." line, exit 0.

The --accumulation-branch value must be non-empty, contain no whitespace
and no "..", and must not start with "-" or end with "/" or ".lock".

The TDD-posture check enforces commands/orchestrator.md Step 7: the
authored task body must carry exactly one line reading
"TDD posture: WARRANTED" or "TDD posture: OPTIONAL" (surrounding
whitespace allowed); the receiving command obeys that stamp, so a
dispatch without it forces the session to self-derive the posture.

The invocation line (--command, default grill_and_implement) tells the
session that opens the prompt via "@docs/prompts/..." WHICH command to run
-- the ## Orchestration block alone says only that it is orchestrated. The
written body carries exactly one line invoking "/<command>": an existing
line that invokes it (bare, or followed by arguments such as
"/grill_and_implement <plan> session <NN> -- <title>") is kept as is;
otherwise the bare line "/<command>" is inserted on its own line directly
after the body's first H1 title line, blank-line separated, ahead of the
TDD-posture stamp (or as the first line when the body has no H1):

    # Session 06 -- <title>

    /grill_and_implement

    TDD posture: WARRANTED

A body that invokes a DIFFERENT command ("^/[a-z_]+" at line start), or
invokes the requested one more than once, fails closed like the posture
rule. "--command none" is the explicit opt-out for a dispatch that is not a
grill_and_implement one: nothing is inserted and no invocation line is
required or checked. The inserted line lands before the manifest hash is
taken, so it is covered by prompt_sha256 by construction.

Portable: stdlib-only, ASCII, no host-project paths; every path arrives as
an argument.
"""

import argparse
import hashlib
import json
import os
import re
import sys

ESTABLISHED_HEADING = "## Established"
ID_RE = re.compile(r"^E\d{3}$")
POSTURE_RE = re.compile(r"^\s*TDD posture: (?:WARRANTED|OPTIONAL)\s*$")
POSTURE_LEGAL = "'TDD posture: WARRANTED' or 'TDD posture: OPTIONAL'"
DEFAULT_COMMAND = "grill_and_implement"
COMMAND_NONE = "none"
COMMAND_NAME_RE = re.compile(r"^[a-z_]+$")
# A slash-command invocation line: "/<name>" alone, or followed by
# whitespace-separated arguments. Group 1 is the command name.
INVOCATION_RE = re.compile(r"^/([a-z_]+)(?:\s+\S.*)?\s*$")
H1_RE = re.compile(r"^#\s+\S")


def first_cell(line):
    """Content of the first cell of a table row line ('| a | b |' -> 'a')."""
    return line[1:].split("|", 1)[0].strip()


def section_bounds(lines, heading):
    """(start, end) indexes of a section's body, or None if absent."""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return start, end


def extract_rows(state_text, row_ids, failures):
    """Verbatim ## Established row lines for row_ids, in the given order."""
    lines = state_text.splitlines()
    bounds = section_bounds(lines, ESTABLISHED_HEADING)
    if bounds is None:
        failures.append(
            "FAIL state: no '{0}' section in the state file".format(
                ESTABLISHED_HEADING
            )
        )
        return []
    start, end = bounds
    by_id = {}
    for line in lines[start:end]:
        stripped = line.rstrip()
        if not stripped.startswith("|"):
            continue
        cell = first_cell(stripped)
        if not ID_RE.match(cell):
            continue
        if cell in by_id:
            failures.append(
                "FAIL state: duplicate row ID {0} in the state file".format(
                    cell
                )
            )
            continue
        by_id[cell] = stripped
    rows = []
    for rid in row_ids:
        if rid not in by_id:
            failures.append(
                "FAIL rows: row ID {0} not found in {1}".format(
                    rid, ESTABLISHED_HEADING
                )
            )
            continue
        rows.append(by_id[rid])
    return rows


def default_accumulation_branch(plan):
    """The plan's accumulation branch when none is declared."""
    return "integration/{0}".format(plan)


def accumulation_branch_problems(value):
    """Reasons the --accumulation-branch value is unusable ([] if valid)."""
    if not value:
        return ["is empty"]
    problems = []
    if any(ch.isspace() for ch in value):
        problems.append("contains whitespace")
    if ".." in value:
        problems.append("contains '..'")
    if value.startswith("-"):
        problems.append("starts with '-'")
    if value.endswith("/"):
        problems.append("ends with '/'")
    if value.endswith(".lock"):
        problems.append("ends with '.lock'")
    return problems


def with_invocation_line(body_text, command, failures):
    """body_text carrying exactly one line invoking /<command>.

    command None (the --command none opt-out) -> body_text unchanged, no
    check. A body already invoking <command> (bare or with arguments) is
    returned as is. A body invoking a DIFFERENT command, or the requested
    one more than once, appends a FAIL line and returns body_text unchanged
    -- the caller writes nothing on failures. Otherwise the bare line
    "/<command>" is inserted after the first H1 line (blank-line separated
    on both sides), or as the first line when there is no H1."""
    if command is None:
        return body_text
    lines = body_text.splitlines()
    invoked = [m.group(1) for m in map(INVOCATION_RE.match, lines) if m]
    others = sorted(set(name for name in invoked if name != command))
    if others:
        failures.append(
            "FAIL body: task body invokes {0}, not /{1}; pass --command "
            "<name> for the intended command, or --command none for a "
            "dispatch that is not a /{1} one".format(
                ", ".join("/" + name for name in others), command
            )
        )
        return body_text
    if len(invoked) > 1:
        failures.append(
            "FAIL body: {0} lines invoke /{1} in the task body; it must "
            "carry exactly one".format(len(invoked), command)
        )
        return body_text
    if invoked:
        return body_text
    invocation = "/{0}".format(command)
    insert_at = 0
    for i, line in enumerate(lines):
        if H1_RE.match(line):
            insert_at = i + 1
            break
    block = [invocation]
    if insert_at > 0:
        block.insert(0, "")
    if insert_at < len(lines) and lines[insert_at].strip():
        block.append("")
    new_lines = lines[:insert_at] + block + lines[insert_at:]
    text = "\n".join(new_lines)
    if body_text.endswith("\n"):
        text += "\n"
    return text


def orchestration_block(state_path, plan, session, branch, row_lines,
                        accumulation_branch=None):
    """The fixed ## Orchestration block per orchestrator.md Step 7.

    accumulation_branch None -> integration/<plan> (the default)."""
    if accumulation_branch is None:
        accumulation_branch = default_accumulation_branch(plan)
    lines = [
        "## Orchestration",
        "",
        "- **State file:** {0}".format(state_path),
        "- **Handback:** docs/orchestration/{0}/handbacks/{1}.md".format(
            plan, session
        ),
        "- **Branch:** {0}".format(branch),
        "  (cut from {0})".format(accumulation_branch),
        "- **Accumulation branch:** {0}".format(accumulation_branch),
        "- **Rows this session must obey:**",
    ]
    for row in row_lines:
        lines.append("  {0}".format(row))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assemble a dispatch prompt and its manifest."
    )
    parser.add_argument("--state", required=True,
                        help="state file path, echoed verbatim into the prompt")
    parser.add_argument("--body", required=True,
                        help="orchestrator-authored task-body file")
    parser.add_argument("--plan", required=True, help="plan name (slug)")
    parser.add_argument("--session", required=True,
                        help="session number, e.g. 07")
    parser.add_argument("--branch", required=True,
                        help="session branch name, used verbatim")
    parser.add_argument("--rows", required=True,
                        help="comma-separated row E-IDs, e.g. E001,E003")
    parser.add_argument("--out", required=True,
                        help="prompt file path to write")
    parser.add_argument("--accumulation-branch", default=None,
                        help="branch sessions are cut from and merge into "
                             "(default: integration/<plan>)")
    parser.add_argument("--command", default=DEFAULT_COMMAND,
                        help="receiving command whose invocation line "
                             "'/<name>' the body must carry; inserted after "
                             "the body's H1 title when absent (default: "
                             "{0}); 'none' = insert and require nothing, "
                             "for a dispatch that is not a /{0} one".format(
                                 DEFAULT_COMMAND))
    args = parser.parse_args(argv)

    failures = []

    if args.command == COMMAND_NONE:
        command = None
    elif COMMAND_NAME_RE.match(args.command):
        command = args.command
    else:
        failures.append(
            "FAIL args: --command {0!r} is not a command name ([a-z_]+) "
            "or 'none'".format(args.command)
        )
        command = None

    if args.accumulation_branch is None:
        accumulation_branch = default_accumulation_branch(args.plan)
    else:
        accumulation_branch = args.accumulation_branch
    for problem in accumulation_branch_problems(accumulation_branch):
        failures.append(
            "FAIL args: --accumulation-branch {0!r} {1}".format(
                accumulation_branch, problem
            )
        )

    try:
        session = "{0:02d}".format(int(args.session))
    except ValueError:
        failures.append(
            "FAIL args: --session must be a number, got {0!r}".format(
                args.session
            )
        )
        session = args.session

    row_ids = [tok.strip() for tok in args.rows.split(",") if tok.strip()]
    if not row_ids:
        failures.append("FAIL args: --rows is empty")
    for rid in row_ids:
        if not ID_RE.match(rid):
            failures.append(
                "FAIL args: malformed row ID {0!r} (expected ENNN)".format(
                    rid
                )
            )

    try:
        with open(args.state, "r", encoding="utf-8") as f:
            state_text = f.read()
    except OSError as exc:
        failures.append("FAIL state: cannot read {0}: {1}".format(
            args.state, exc))
        state_text = ""

    try:
        with open(args.body, "r", encoding="utf-8") as f:
            body_text = f.read()
    except OSError as exc:
        failures.append("FAIL body: cannot read {0}: {1}".format(
            args.body, exc))
        body_text = ""
    else:
        body_text = with_invocation_line(body_text, command, failures)
        posture_count = sum(
            1 for line in body_text.splitlines() if POSTURE_RE.match(line)
        )
        if posture_count == 0:
            failures.append(
                "FAIL body: no TDD-posture line in the task body; it must "
                "carry exactly one ({0})".format(POSTURE_LEGAL)
            )
        elif posture_count > 1:
            failures.append(
                "FAIL body: {0} TDD-posture lines in the task body; it must "
                "carry exactly one ({1})".format(posture_count, POSTURE_LEGAL)
            )

    if os.path.exists(args.out):
        failures.append(
            "FAIL out: prompt file already exists: {0} (session numbers "
            "are never reused)".format(args.out)
        )

    manifest_path = os.path.join(
        os.path.dirname(os.path.abspath(args.state)),
        args.plan,
        "dispatches",
        "{0}.json".format(session),
    )
    if os.path.exists(manifest_path):
        failures.append(
            "FAIL manifest: manifest already exists: {0} (session numbers "
            "are never reused)".format(manifest_path)
        )

    if not failures:
        row_lines = extract_rows(state_text, row_ids, failures)

    if failures:
        for line in failures:
            print(line)
        return 1

    prompt_text = (
        body_text.rstrip("\n")
        + "\n\n"
        + orchestration_block(args.state, args.plan, session, args.branch,
                              row_lines, accumulation_branch)
    )
    prompt_bytes = prompt_text.encode("utf-8")

    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "wb") as f:
        f.write(prompt_bytes)

    digest = hashlib.sha256(prompt_bytes).hexdigest()
    manifest = {
        "plan_name": args.plan,
        "session_number": session,
        "row_ids": row_ids,
        "accumulation_branch": accumulation_branch,
        "prompt_path": args.out,
        "prompt_sha256": digest,
    }
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")

    print(
        "OK: wrote {0} and {1} (rows: {2}; sha256: {3})".format(
            args.out, manifest_path, ",".join(row_ids), digest
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
