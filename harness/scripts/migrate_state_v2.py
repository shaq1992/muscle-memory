"""One-shot migration of an orchestrated plan's state file to schema v2.

Usage: python3 .claude/harness/scripts/migrate_state_v2.py <state_file> [--check]

Schema v2 (harness/templates/state_schema.md) adds two things this script
installs mechanically, changing nothing else:

  1. an immutable ID column on the ## Established table: E + 3 zero-padded
     digits (E001..E999), consumed in ascending order from the counter and
     never reused, with the table kept in strictly DECREASING ID order
     top-down -- newest rows at the top (state_schema.md, user decision
     2026-08-31). Migrating a v1 file (rows oldest-first top-down) stamps the
     OLDEST (topmost pre-migration) row with the LOWEST new ID, then reverses
     the data rows so the migrated table lands newest-at-top;
  2. the ## Orchestrator log section (appended LAST), carrying the ID counter
     as a "Next row ID: ENNN" line so an ID is never reissued after a trim,
     plus an incarnation count and a dated migration note.

The script is IDEMPOTENT: an already-migrated file is a no-op (exit 0), and a
partially-stamped v2 file (new unstamped rows sitting at the TOP of the
table, per the decreasing-order convention) is stamped from the recorded
counter onward -- bottom-up, so the table stays strictly decreasing -- never
renumbering or reordering an existing stamped row. It is also the ONLY
sanctioned pen for applying v2 to a live state file -- it acts as its
invoker's pen under the one-writer rule, not as a second writer.

Fail-closed: on any structural surprise (missing ## Established, unparseable
table, duplicate or out-of-range IDs, counter behind the table, or a stamping
that would not leave the table strictly decreasing) it prints
"FAIL <check>: <detail>" lines and exits 1 WITHOUT writing. --check reports
what would change and never writes. Success prints an "OK: ..." line, exit 0.

Portable: stdlib-only, ASCII, no host-project paths; the state file path is
the single positional argument.
"""

import datetime
import os
import re
import sys

ESTABLISHED_HEADING = "## Established"
LOG_HEADING = "## Orchestrator log"

V1_HEADER = "| Statement | Provenance | Disposition | Revisit trigger |"
V2_HEADER = "| ID | Statement | Provenance | Disposition | Revisit trigger |"
V2_SEPARATOR = "|---|---|---|---|---|"

ID_RE = re.compile(r"^E(\d{3})$")
NEXT_ID_LINE_RE = re.compile(r"^- Next row ID: E(\d{3})\s*$")
ID_MAX = 999


def fmt_id(n):
    return "E{0:03d}".format(n)


def first_cell(line):
    """Content of the first cell of a table row line ('| a | b |' -> 'a')."""
    return line[1:].split("|", 1)[0].strip()


def section_bounds(lines, heading):
    """(start, end) line indexes of a section's body; start is the line after
    the heading, end is the next '## ' heading or EOF. None if absent."""
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


def migrate(text):
    """Return (new_text, summary, failures). new_text == text means no-op."""
    failures = []
    lines = text.splitlines()
    trailing_newline = text.endswith("\n")

    bounds = section_bounds(lines, ESTABLISHED_HEADING)
    if bounds is None:
        return text, "", ["FAIL sections: no '## Established' section found"]
    est_start, est_end = bounds

    header_idx = None
    separator_idx = None
    row_idxs = []
    for i in range(est_start, est_end):
        line = lines[i]
        if not line.startswith("|"):
            continue
        if header_idx is None:
            header_idx = i
        elif separator_idx is None and line.startswith("|-"):
            separator_idx = i
        else:
            row_idxs.append(i)

    if header_idx is None or separator_idx is None:
        return text, "", [
            "FAIL table: no markdown table found under '## Established'"
        ]

    header = lines[header_idx].strip()
    if header == V1_HEADER:
        header_needs_stamp = True
    elif header == V2_HEADER:
        header_needs_stamp = False
    else:
        return text, "", [
            "FAIL table: unrecognized '## Established' header: {0!r}".format(
                header
            )
        ]

    stamped = {}
    unstamped_idxs = []
    for i in row_idxs:
        cell = first_cell(lines[i])
        m = ID_RE.match(cell)
        if m:
            n = int(m.group(1))
            if n in stamped:
                failures.append(
                    "FAIL ids: duplicate row ID {0} (lines {1} and {2})".format(
                        fmt_id(n), stamped[n] + 1, i + 1
                    )
                )
            stamped[n] = i
        else:
            unstamped_idxs.append(i)
    if failures:
        return text, "", failures

    # Counter: the recorded 'Next row ID' wins; absent that, max stamped + 1.
    log_bounds = section_bounds(lines, LOG_HEADING)
    counter = None
    counter_line_idx = None
    if log_bounds is not None:
        for i in range(log_bounds[0], log_bounds[1]):
            m = NEXT_ID_LINE_RE.match(lines[i].strip())
            if m:
                counter = int(m.group(1))
                counter_line_idx = i
                break
    if counter is not None and stamped and counter <= max(stamped):
        return text, "", [
            "FAIL ids: recorded counter {0} is not past the highest stamped "
            "ID {1}; refusing to stamp".format(
                fmt_id(counter), fmt_id(max(stamped))
            )
        ]
    if counter is None:
        counter = (max(stamped) + 1) if stamped else 1

    if counter + len(unstamped_idxs) - 1 > ID_MAX:
        return text, "", [
            "FAIL ids: stamping {0} rows from {1} would exceed {2}".format(
                len(unstamped_idxs), fmt_id(counter), fmt_id(ID_MAX)
            )
        ]

    new_lines = list(lines)
    if header_needs_stamp:
        new_lines[header_idx] = V2_HEADER
        new_lines[separator_idx] = V2_SEPARATOR
        # v1 migration: rows are oldest-first top-down. Stamp in table order
        # (the OLDEST, topmost row gets the LOWEST new ID), then reverse the
        # data rows in place so the migrated table lands newest-at-top --
        # strictly decreasing ID order, per state_schema.md.
        for i in unstamped_idxs:
            new_lines[i] = "| {0} {1}".format(fmt_id(counter), new_lines[i])
            counter += 1
        contents = [new_lines[i] for i in row_idxs]
        for i, content in zip(row_idxs, reversed(contents)):
            new_lines[i] = content
    else:
        # v2 table: unstamped rows sit at the TOP (newest first). Stamp them
        # bottom-up so the topmost gets the highest new ID and the table
        # stays strictly decreasing; stamped rows are never reordered.
        for i in reversed(unstamped_idxs):
            new_lines[i] = "| {0} {1}".format(fmt_id(counter), new_lines[i])
            counter += 1
    next_id = fmt_id(counter)

    # Order post-condition: whenever anything was stamped, the resulting
    # table must be strictly decreasing top-down. Fail closed (no write)
    # otherwise -- e.g. an unstamped row misplaced BELOW stamped rows in a
    # v2 table. A fully-stamped file is never checked (and never reordered):
    # a legacy increasing-order file re-run stays a byte-identical no-op.
    if unstamped_idxs:
        ids = []
        for i in row_idxs:
            m = ID_RE.match(first_cell(new_lines[i]))
            ids.append(int(m.group(1)) if m else -1)
        if any(a <= b for a, b in zip(ids, ids[1:])):
            return text, "", [
                "FAIL order: stamping would not leave '## Established' in "
                "strictly decreasing ID order top-down (on a v2 table, "
                "unstamped rows must sit at the TOP); refusing to write"
            ]

    if log_bounds is None:
        today = datetime.date.today().isoformat()
        while new_lines and new_lines[-1].strip() == "":
            new_lines.pop()
        new_lines.extend(
            [
                "",
                LOG_HEADING,
                "",
                "- Incarnations: 1",
                "- Next row ID: {0}".format(next_id),
                "- {0}: migrated to schema v2 by migrate_state_v2.py "
                "(stamped {1} row IDs; section added).".format(
                    today, len(unstamped_idxs)
                ),
            ]
        )
    elif counter_line_idx is not None:
        new_lines[counter_line_idx] = "- Next row ID: {0}".format(next_id)
    else:
        return text, "", [
            "FAIL log: '## Orchestrator log' exists but carries no "
            "'- Next row ID:' line; fix the section before re-running"
        ]

    new_text = "\n".join(new_lines) + ("\n" if trailing_newline else "")
    summary = (
        "stamped {0} row(s) ({1} already stamped); next row ID {2}; "
        "orchestrator log {3}".format(
            len(unstamped_idxs),
            len(stamped),
            next_id,
            "added" if log_bounds is None else "updated",
        )
    )
    return new_text, summary, []


def main(argv):
    args = [a for a in argv[1:] if a != "--check"]
    check = "--check" in argv[1:]
    if len(args) != 1:
        print(
            "Usage: python3 migrate_state_v2.py <state_file> [--check]"
        )
        return 2
    path = args[0]
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        print("FAIL read: state file unreadable: {0}".format(exc))
        return 1

    new_text, summary, failures = migrate(text)
    if failures:
        for line in failures:
            print(line)
        return 1

    if new_text == text:
        print("OK: already at v2, nothing to do ({0})".format(path))
        return 0
    if check:
        print("OK (check only, nothing written): would have {0}".format(summary))
        return 0

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    os.replace(tmp_path, path)
    print("OK: {0} ({1})".format(summary, path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
