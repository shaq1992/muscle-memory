"""Assemble an orchestrated dispatch prompt and its dispatch manifest (D2).

Usage: python3 .claude/harness/scripts/assemble_dispatch.py
           --state <state_file> --body <body_file> --plan <plan_name>
           --session <NN> --branch <branch> --rows E001,E002,... --out <prompt_path>

Run from the PROJECT ROOT with project-relative paths: the --state value is
echoed VERBATIM into the prompt's "State file:" field, and the reading
session resolves it against its own working directory.

The orchestrator authors only the task body; this script writes the WHOLE
prompt file. It extracts the requested rows VERBATIM by E-ID from the state
file's ## Established table, appends the fixed ## Orchestration block --
heading, field names and value convention owned by commands/orchestrator.md
Step 7; the receiving command detects the block's PRESENCE, so its shape is
load-bearing -- and writes the per-session dispatch manifest to
<state_dir>/<plan_name>/dispatches/<NN>.json in the same run:

    {"plan_name", "session_number", "row_ids", "prompt_path", "prompt_sha256"}

prompt_sha256 is the SHA-256 (lowercase hex) over the EXACT BYTES of the
prompt file as written, so the manifest matches the prompt by construction.
The dispatched session echoes that hash (plus the row-ID list) in its
handback read receipt, and hooks/enforce_handback.py verifies the receipt
against this manifest.

Fail-closed: on any problem (malformed or missing E-ID, missing
## Established table, pre-existing prompt or manifest file -- session
numbers are never reused) it prints "FAIL <check>: <detail>" lines and exits
1 WITHOUT writing anything. Success prints an "OK: ..." line, exit 0.

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


def orchestration_block(state_path, plan, session, branch, row_lines):
    """The fixed ## Orchestration block per orchestrator.md Step 7."""
    lines = [
        "## Orchestration",
        "",
        "- **State file:** {0}".format(state_path),
        "- **Handback:** docs/orchestration/{0}/handbacks/{1}.md".format(
            plan, session
        ),
        "- **Branch:** {0}".format(branch),
        "  (cut from integration/{0})".format(plan),
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
    args = parser.parse_args(argv)

    failures = []

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
                              row_lines)
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
