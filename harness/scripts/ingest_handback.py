"""Ingest an orchestrated session's handback into the plan's state file (D4).

Usage: python3 .claude/harness/scripts/ingest_handback.py
           --state <state_file> <handback_file>
           [--observations <path>] [--check] [--date YYYY-MM-DD]

The script is the ORCHESTRATOR's pen for the mechanical ingest actions of
commands/orchestrator.md Step 9 -- it acts as its invoker's pen under the
one-writer rule, never as a second writer, and is invoked only by the
orchestrator. It:

  1. parses the handback's Status line and its ## Delta and ## Structural
     observations sections, slicing by the fixed headings (it never reads
     the read-receipt block, and never reads ## For the next session --
     that section is the orchestrator's judgement, not the script's);
  2. applies the ## Delta marker blocks to ## Established by row ID:
     ADD rows (`| - |` ID cell) are appended and stamped from the
     `- Next row ID:` counter in ## Orchestrator log (bumped in the same
     write); CHANGE rows replace the identified row in place, keeping its
     ID; RETIRE (IDs named on the marker line before the colon) HARD-DELETES
     the row lines -- the ID is never reused and the summary names the
     retired IDs. Scope is ESTABLISHED-ONLY: an `OPEN (orchestrator-manual):`
     block is counted in the summary and never applied; ## Open is never
     touched;
  3. appends ## Structural observations lines to the observations file in
     the fixed dated shape (append-only; `none` appends nothing);
  4. updates ## Dispatched: clears the session's row on COMPLETE, rewrites
     its Status cell for PARTIAL/ABANDONED, leaves it standing for OPEN;
  5. runs the structural no-contradiction check: an incoming statement that
     exactly duplicates an existing row (whitespace-normalized) is FLAGGED
     in the summary, never resolved -- semantic contradiction stays the
     orchestrator's judgement per state_schema.md's no-contradiction law;
  6. WARNS (never blocks) on incoming rows over ~600 bytes (the D7 row
     discipline) and reports ## Established row count and byte size against
     the GC threshold (80 rows OR 45 KB -- either bound trips).

Fail-closed: on a malformed handback, or a Delta row it cannot apply
unambiguously, it prints "FAIL <check>: <detail>" lines and exits 1 WITHOUT
writing anything -- the state write is atomic (tempfile + os.replace) and
happens only after every check passes. Success prints a summary of roughly
ten lines, exit 0.

Portable: stdlib-only, ASCII, no host-project paths; every path arrives as
an argument (--observations defaults to <state_dir>/../observations.md,
matching the docs/orchestration/ layout).
"""

import argparse
import datetime
import os
import re
import sys

ESTABLISHED_HEADING = "## Established"
DISPATCHED_HEADING = "## Dispatched"
LOG_HEADING = "## Orchestrator log"

DELTA_HEADING = "## Delta"
ADVISORY_HEADING = "## For the next session"
OBSERVATIONS_HEADING = "## Structural observations"

STATUS_VALUES = ("OPEN", "PARTIAL", "ABANDONED", "COMPLETE")

OBSERVATION_TAGS = (
    "prompt-underspecified",
    "session-split",
    "gate-leaked",
    "greenlist-wrong",
    "invariant-moved",
    "handback-thin",
    "isolation-breached",
    "other",
)

OPEN_MANUAL_MARKER = "OPEN (orchestrator-manual):"

ROW_WARN_BYTES = 600          # D7 row discipline: warn, never block.
THRESHOLD_ROWS = 80           # D6 GC trigger: either bound trips.
THRESHOLD_BYTES = 45 * 1024   # 45 KB.

ID_RE = re.compile(r"^E(\d{3})$")
ID_FIND_RE = re.compile(r"\bE\d{3}\b")
NEXT_ID_RE = re.compile(r"^- Next row ID: E(\d{3})\s*$")
STATUS_RE = re.compile(r"^Status:\s*(\S+)\s*$")
OBSERVATION_RE = re.compile(r"^-\s*([A-Za-z][A-Za-z-]*)\s*\|\s*(.+)$")
ID_MAX = 999


def fmt_id(n):
    return "E{0:03d}".format(n)


def first_cell(line):
    """Content of the first cell of a table row line ('| a | b |' -> 'a')."""
    return line[1:].split("|", 1)[0].strip()


def cells(line):
    """Stripped cell contents of a '| a | b |' table row line."""
    stripped = line.strip()
    return [c.strip() for c in stripped.strip("|").split("|")]


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


def normalized(statement):
    return " ".join(statement.split())


def is_separator_row(line):
    body = line.strip().strip("|")
    return body != "" and set(body) <= set("-| :")


def is_header_row(line):
    return [c.lower() for c in cells(line)[:2]] == ["id", "statement"]


class Delta(object):
    def __init__(self):
        self.adds = []          # verbatim row lines with '| - |' ID cell
        self.changes = {}       # id -> verbatim replacement row line
        self.change_order = []
        self.retires = []       # ids, in marker order
        self.open_manual = 0    # rows under OPEN (orchestrator-manual):


def parse_delta(body_lines, failures):
    """Parse the ## Delta marker-block grammar (handback_schema.md)."""
    delta = Delta()
    content = [ln for ln in body_lines if ln.strip() != ""]
    if [ln.strip() for ln in content] == ["none"]:
        return delta
    mode = None
    for line in content:
        stripped = line.strip()
        if stripped.startswith("|"):
            if is_separator_row(stripped) or is_header_row(stripped):
                continue
            if mode is None:
                failures.append(
                    "FAIL delta: table row with no ADD/CHANGE/RETIRE marker "
                    "line above it: {0!r}".format(stripped[:80])
                )
            elif mode == "add":
                row_cells = cells(stripped)
                if len(row_cells) != 5:
                    failures.append(
                        "FAIL delta: ADD row does not have 5 cells: "
                        "{0!r}".format(stripped[:80])
                    )
                elif row_cells[0] != "-":
                    failures.append(
                        "FAIL delta: ADD row ID cell must be the '-' "
                        "placeholder (the counter is the orchestrator's), "
                        "got {0!r}".format(row_cells[0])
                    )
                else:
                    delta.adds.append(stripped)
            elif mode == "change":
                row_cells = cells(stripped)
                if len(row_cells) != 5 or not ID_RE.match(row_cells[0]):
                    failures.append(
                        "FAIL delta: CHANGE row must carry its existing "
                        "E-ID and 5 cells: {0!r}".format(stripped[:80])
                    )
                elif row_cells[0] in delta.changes:
                    failures.append(
                        "FAIL delta: row {0} changed twice".format(
                            row_cells[0])
                    )
                else:
                    delta.changes[row_cells[0]] = stripped
                    delta.change_order.append(row_cells[0])
            elif mode == "open":
                delta.open_manual += 1
            else:  # retire: IDs live on the marker line, never in rows
                failures.append(
                    "FAIL delta: RETIRE takes no table rows -- name the IDs "
                    "on the marker line before the colon: {0!r}".format(
                        stripped[:80])
                )
            continue
        # Non-table line: must be a marker.
        word = stripped.split(None, 1)[0].upper().rstrip(":(")
        if stripped.startswith(OPEN_MANUAL_MARKER):
            mode = "open"
        elif word == "ADD":
            mode = "add"
        elif word == "CHANGE":
            mode = "change"
        elif word == "RETIRE":
            mode = "retire"
            head = stripped.split(":", 1)[0]
            ids = ID_FIND_RE.findall(head)
            if not ids:
                failures.append(
                    "FAIL delta: RETIRE marker names no E-IDs before the "
                    "colon: {0!r}".format(stripped[:80])
                )
            for rid in ids:
                if rid in delta.retires:
                    failures.append(
                        "FAIL delta: row {0} retired twice".format(rid))
                else:
                    delta.retires.append(rid)
        else:
            failures.append(
                "FAIL delta: unrecognized line in ## Delta (not a marker, "
                "not a table row): {0!r}".format(stripped[:80])
            )
    for rid in delta.retires:
        if rid in delta.changes:
            failures.append(
                "FAIL delta: row {0} is both changed and retired -- "
                "ambiguous".format(rid)
            )
    return delta


def parse_observations(body_lines, failures):
    """Return (tag, description) pairs; 'none' (or empty) yields nothing."""
    out = []
    content = [ln.strip() for ln in body_lines if ln.strip() != ""]
    if content == ["none"] or not content:
        return out
    for line in content:
        m = OBSERVATION_RE.match(line)
        if not m:
            failures.append(
                "FAIL observations: line is not '- <tag> | <description>': "
                "{0!r}".format(line[:80])
            )
            continue
        tag, desc = m.group(1), m.group(2).strip()
        if tag not in OBSERVATION_TAGS:
            failures.append(
                "FAIL observations: unknown tag {0!r} (closed vocabulary: "
                "{1})".format(tag, ", ".join(OBSERVATION_TAGS))
            )
            continue
        out.append((tag, desc))
    return out


def apply_established(lines, delta, failures, flags, warnings):
    """Apply the delta to ## Established in-memory; return (lines, applied)
    where applied = {'added': [(id, line)], 'changed': [...], 'retired': []}."""
    applied = {"added": [], "changed": [], "retired": []}
    bounds = section_bounds(lines, ESTABLISHED_HEADING)
    if bounds is None:
        failures.append("FAIL state: no '{0}' section".format(
            ESTABLISHED_HEADING))
        return lines, applied
    start, end = bounds

    row_idx_by_id = {}
    last_row_idx = None
    for i in range(start, end):
        stripped = lines[i].rstrip()
        if not stripped.startswith("|"):
            continue
        cell = first_cell(stripped)
        if not ID_RE.match(cell):
            continue
        if cell in row_idx_by_id:
            failures.append(
                "FAIL state: duplicate row ID {0} in ## Established".format(
                    cell)
            )
        row_idx_by_id[cell] = i
        last_row_idx = i

    for rid in list(delta.changes) + delta.retires:
        if rid not in row_idx_by_id:
            failures.append(
                "FAIL delta: row ID {0} not found in ## Established".format(
                    rid)
            )

    log_bounds = section_bounds(lines, LOG_HEADING)
    counter = None
    counter_idx = None
    if log_bounds is not None:
        for i in range(log_bounds[0], log_bounds[1]):
            m = NEXT_ID_RE.match(lines[i].strip())
            if m:
                counter = int(m.group(1))
                counter_idx = i
                break
    if delta.adds and counter is None:
        failures.append(
            "FAIL state: no '- Next row ID:' line in {0} -- cannot stamp "
            "ADD rows".format(LOG_HEADING)
        )
    if counter is not None and row_idx_by_id:
        top = max(int(ID_RE.match(r).group(1)) for r in row_idx_by_id)
        if counter <= top:
            failures.append(
                "FAIL state: counter {0} is not past the highest stamped ID "
                "{1}".format(fmt_id(counter), fmt_id(top))
            )
    if counter is not None and counter + len(delta.adds) - 1 > ID_MAX:
        failures.append(
            "FAIL delta: stamping {0} rows from {1} would exceed {2}".format(
                len(delta.adds), fmt_id(counter), fmt_id(ID_MAX))
        )

    if failures:
        return lines, applied

    # Structural no-contradiction check: exact-duplicate statements are
    # FLAGGED, never resolved (resolution is the orchestrator's judgement).
    existing_statements = {}
    for rid, i in row_idx_by_id.items():
        row_cells = cells(lines[i])
        existing_statements[rid] = normalized(
            row_cells[1] if len(row_cells) > 1 else "")
    incoming = [("-", line) for line in delta.adds]
    incoming += [(rid, delta.changes[rid]) for rid in delta.change_order]
    for rid, line in incoming:
        stmt = normalized(cells(line)[1])
        for other_id, other_stmt in existing_statements.items():
            if other_id != rid and stmt == other_stmt:
                flags.append(
                    "FLAG duplicate: incoming {0} row repeats {1}'s "
                    "statement verbatim -- your judgement".format(
                        "ADD" if rid == "-" else rid, other_id)
                )
        row_bytes = len(line.encode("utf-8"))
        if row_bytes > ROW_WARN_BYTES:
            warnings.append(
                "WARN row-discipline: incoming row ({0} B) exceeds ~{1} B "
                "(D7: state the fact, cite inventories by path)".format(
                    row_bytes, ROW_WARN_BYTES)
            )

    new_lines = list(lines)
    for rid in delta.change_order:
        new_lines[row_idx_by_id[rid]] = delta.changes[rid]
        applied["changed"].append(rid)
    for i in sorted((row_idx_by_id[r] for r in delta.retires), reverse=True):
        del new_lines[i]
    applied["retired"] = list(delta.retires)

    if delta.adds:
        # Retired rows all sit at or before last_row_idx, so deleting them
        # shifts the insertion point left by exactly len(retires).
        if last_row_idx is not None:
            insert_at = last_row_idx + 1 - len(delta.retires)
        else:
            insert_at = end
        for line in delta.adds:
            rid = fmt_id(counter)
            rest = line[1:].split("|", 1)[1]
            stamped = "| {0} |{1}".format(rid, rest)
            new_lines.insert(insert_at, stamped)
            insert_at += 1
            applied["added"].append(rid)
            counter += 1
        for i, line in enumerate(new_lines):
            if NEXT_ID_RE.match(line.strip()):
                new_lines[i] = "- Next row ID: {0}".format(fmt_id(counter))
                break
    return new_lines, applied


def update_dispatched(lines, session, status, date, warnings):
    """Apply the Step 9 ## Dispatched transition; return new lines."""
    bounds = section_bounds(lines, DISPATCHED_HEADING)
    row_idx = None
    if bounds is not None:
        for i in range(bounds[0], bounds[1]):
            stripped = lines[i].rstrip()
            if stripped.startswith("|") and first_cell(stripped) == session:
                row_idx = i
                break
    if row_idx is None:
        warnings.append(
            "WARN dispatched: no ## Dispatched row for session {0} -- "
            "transition skipped".format(session)
        )
        return lines, "no row"
    new_lines = list(lines)
    if status == "COMPLETE":
        del new_lines[row_idx]
        return new_lines, "row cleared"
    if status in ("PARTIAL", "ABANDONED"):
        row_cells = cells(new_lines[row_idx])
        row_cells[-1] = "Returned {0} {1}.".format(status, date)
        new_lines[row_idx] = "| " + " | ".join(row_cells) + " |"
        return new_lines, "status set to Returned {0}".format(status)
    return lines, "left standing (OPEN)"


def established_level(lines):
    """(row_count, section_bytes) of ## Established, heading included."""
    bounds = section_bounds(lines, ESTABLISHED_HEADING)
    if bounds is None:
        return 0, 0
    start, end = bounds
    rows = 0
    for i in range(start, end):
        stripped = lines[i].rstrip()
        if stripped.startswith("|") and ID_RE.match(first_cell(stripped)):
            rows += 1
    section_text = "\n".join(lines[start - 1:end]) + "\n"
    return rows, len(section_text.encode("utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Ingest a session handback into the plan's state file."
    )
    parser.add_argument("handback", help="handback file path (<NN>.md)")
    parser.add_argument("--state", required=True, help="state file path")
    parser.add_argument("--observations", default=None,
                        help="observations file (default: "
                             "<state_dir>/../observations.md)")
    parser.add_argument("--check", action="store_true",
                        help="validate and print the summary; write nothing")
    parser.add_argument("--date", default=None,
                        help="date stamp YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)

    failures = []
    flags = []
    warnings = []

    date = args.date or datetime.date.today().isoformat()
    state_dir = os.path.dirname(os.path.abspath(args.state))
    obs_path = args.observations or os.path.join(
        os.path.dirname(state_dir), "observations.md")

    plan = os.path.basename(args.state)
    if plan.endswith("_state.md"):
        plan = plan[:-len("_state.md")]
    else:
        failures.append(
            "FAIL args: state filename is not <plan>_state.md: {0}".format(
                os.path.basename(args.state))
        )
    session = os.path.splitext(os.path.basename(args.handback))[0]
    if not re.match(r"^\d{2,}$", session):
        failures.append(
            "FAIL args: handback filename is not <NN>.md: {0}".format(
                os.path.basename(args.handback))
        )

    try:
        with open(args.handback, "r", encoding="utf-8") as f:
            hb_text = f.read()
    except OSError as exc:
        print("FAIL read: handback unreadable: {0}".format(exc))
        return 1
    try:
        with open(args.state, "r", encoding="utf-8") as f:
            state_text = f.read()
    except OSError as exc:
        print("FAIL read: state file unreadable: {0}".format(exc))
        return 1

    hb_lines = hb_text.splitlines()
    status = None
    for line in hb_lines:
        m = STATUS_RE.match(line.strip())
        if m:
            status = m.group(1)
            break
    if status is None:
        failures.append("FAIL handback: no 'Status:' line")
    elif status not in STATUS_VALUES:
        failures.append(
            "FAIL handback: Status {0!r} is not one of {1}".format(
                status, "/".join(STATUS_VALUES))
        )

    if failures:
        for line in failures:
            print(line)
        return 1

    if status == "OPEN":
        print("OK: handback {0} is still OPEN -- a stub never advanced; "
              "nothing ingested. An OPEN stub on a returned session is "
              "positive evidence the session died.".format(args.handback))
        return 0

    delta_bounds = section_bounds(hb_lines, DELTA_HEADING)
    obs_bounds = section_bounds(hb_lines, OBSERVATIONS_HEADING)
    if status in ("COMPLETE", "PARTIAL"):
        for heading, b in ((DELTA_HEADING, delta_bounds),
                           (ADVISORY_HEADING,
                            section_bounds(hb_lines, ADVISORY_HEADING)),
                           (OBSERVATIONS_HEADING, obs_bounds)):
            if b is None:
                failures.append(
                    "FAIL handback: {0} close is missing the '{1}' "
                    "section".format(status, heading)
                )

    delta = Delta()
    if delta_bounds is not None:
        delta = parse_delta(hb_lines[delta_bounds[0]:delta_bounds[1]],
                            failures)
    observations = []
    if obs_bounds is not None:
        observations = parse_observations(
            hb_lines[obs_bounds[0]:obs_bounds[1]], failures)

    state_lines = state_text.splitlines()
    trailing_newline = state_text.endswith("\n")
    applied = {"added": [], "changed": [], "retired": []}
    if not failures:
        state_lines, applied = apply_established(
            state_lines, delta, failures, flags, warnings)
    dispatched_note = ""
    if not failures:
        state_lines, dispatched_note = update_dispatched(
            state_lines, session, status, date, warnings)

    if failures:
        for line in failures:
            print(line)
        return 1

    obs_lines = [
        "{0} | {1} | {2} | {3} | {4}".format(date, plan, session, tag, desc)
        for tag, desc in observations
    ]

    new_state = "\n".join(state_lines) + ("\n" if trailing_newline else "")
    changed = new_state != state_text

    if not args.check:
        if changed:
            tmp_path = args.state + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(new_state)
            os.replace(tmp_path, args.state)
        if obs_lines:
            with open(obs_path, "a", encoding="utf-8") as f:
                for line in obs_lines:
                    f.write(line + "\n")

    rows, size = established_level(state_lines)
    over = rows > THRESHOLD_ROWS or size > THRESHOLD_BYTES
    mode = " (check only, nothing written)" if args.check else ""
    print("OK{0}: ingested {1} (Status: {2})".format(
        mode, args.handback, status))
    print("Added: {0}".format(
        ", ".join(applied["added"]) or "none"))
    print("Changed: {0}".format(", ".join(applied["changed"]) or "none"))
    print("Retired (hard-deleted): {0}".format(
        ", ".join(applied["retired"]) or "none"))
    if applied["added"]:
        print("Next row ID: {0}".format(
            fmt_id(int(applied["added"][-1][1:]) + 1)))
    print("Observations appended: {0}".format(len(obs_lines)))
    print("Dispatched: session {0} -- {1}".format(session, dispatched_note))
    if delta.open_manual:
        print("Open-table rows left for your manual apply: {0}".format(
            delta.open_manual))
    for line in flags:
        print(line)
    for line in warnings:
        print(line)
    print("## Established: {0} rows, {1} B (threshold {2} rows / {3} B) "
          "-- {4}".format(rows, size, THRESHOLD_ROWS, THRESHOLD_BYTES,
                          "OVER" if over else "OK"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
