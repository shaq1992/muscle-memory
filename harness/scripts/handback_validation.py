"""Shared handback Delta-grammar validators and state/section primitives.

Pure, stdlib-only primitives lifted VERBATIM out of
harness/scripts/ingest_handback.py so that more than one consumer can import
the SAME grammar and the SAME state/section helpers instead of re-deriving
them: the ingest script (the orchestrator's pen), the handback Stop hook
(hooks/enforce_handback.py), and the on-demand state-structure check
(check_state_structure, hosted here).

This module hosts two families:

  - Delta marker-block / row-shape GRAMMAR validators (OBSERVATION_TAGS,
    OPEN_MANUAL_MARKER, the ID/observation regexes, first_cell/cells/
    is_separator_row/is_header_row, the Delta class, parse_delta,
    parse_observations);
  - shared STATE/SECTION primitives the ingest, the Stop hook, and the
    state-structure check all need (the ESTABLISHED_HEADING / LOG_HEADING
    section names, the ID_MAX ceiling, the NEXT_ID_RE counter regex, and the
    fmt_id / section_bounds / normalized pure helpers), PLUS the whole-file
    state-structure validator itself (check_state_structure) that checks the
    seven-section order, E-ID uniqueness and strictly-decreasing order, the
    ID counter, and pipe-free table rows against the structure DEFINED in
    harness/templates/state_schema.md -- that template and this check are a
    lockstep contract, exactly as the Delta grammar is with
    harness/templates/handback_schema.md.

Contract of this module:

  - NO file I/O and NO import-time side effects -- importing it only compiles
    the module-level regexes and defines the constants, class, and functions
    below (a Stop hook imports this on every session close);
  - every parser takes a `failures` list and APPENDS structured "FAIL <check>:
    <detail>" strings to it, returning its parsed result -- it NEVER calls
    sys.exit and NEVER writes anywhere. The CALLER owns fail-closed policy
    (ingest_handback.py exits 1 when the list is non-empty and writes nothing);
  - ASCII-only, host-project-path-free, stdlib-only (portable).

The Delta marker-block grammar these functions enforce is DEFINED in
harness/templates/handback_schema.md; this module and that template are a
lockstep contract -- any change to the grammar (marker words, cell counts,
placeholder shape, observation line shape, tag vocabulary) must update BOTH.
"""

import re

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

ID_RE = re.compile(r"^E(\d{3})$")
ID_FIND_RE = re.compile(r"\bE\d{3}\b")
OBSERVATION_RE = re.compile(r"^-\s*([A-Za-z][A-Za-z-]*)\s*\|\s*(.+)$")

# Shared state/section primitives (copied VERBATIM from ingest_handback.py).
# The section heading names and the `- Next row ID:` counter regex the ingest,
# the Stop hook, and the state-structure check all key off of.
ESTABLISHED_HEADING = "## Established"
LOG_HEADING = "## Orchestrator log"

NEXT_ID_RE = re.compile(r"^- Next row ID: E(\d{3})\s*$")
ID_MAX = 999


def fmt_id(n):
    return "E{0:03d}".format(n)


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


def first_cell(line):
    """Content of the first cell of a table row line ('| a | b |' -> 'a')."""
    return line[1:].split("|", 1)[0].strip()


def cells(line):
    """Stripped cell contents of a '| a | b |' table row line."""
    stripped = line.strip()
    return [c.strip() for c in stripped.strip("|").split("|")]


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


def check_state_structure(lines):
    """Structure-check an orchestration state file, PURELY.

    `lines` is the state file split into lines with NO trailing newlines.
    Returns a list of "FAIL state: ..." strings -- empty when the file is
    well-formed. Does NO file I/O, NO printing and NEVER exits: the caller
    owns fail-closed, exactly like every other validator in this module.

    The structure enforced is DEFINED in harness/templates/state_schema.md
    (this check and that template are a lockstep contract). It verifies:

      1. the SEVEN sections are present, unique, and in the fixed order;
      2. ## Established carries no duplicate E-IDs;
      3. ## Established E-IDs run in strictly DECREASING order top-down
         (newest at the top);
      4. the '- Next row ID: E<NNN>' counter in ## Orchestrator log parses
         and exceeds the highest E-ID in ## Established;
      5. every data row in ## Established and ## Open is pipe-clean (splits
         into exactly 5 cells -- more signals an embedded literal pipe).
    """
    failures = []

    # Section names in their fixed order (state_schema.md "Structure").
    state_sections = [
        "## Objective",
        ESTABLISHED_HEADING,
        "## Open",
        "## Next",
        "## Maybe",
        "## Dispatched",
        LOG_HEADING,
    ]

    # (1) Seven sections present, unique, and in order.
    first_idx = {}
    counts = {}
    for idx, line in enumerate(lines):
        s = line.strip()
        if s in state_sections:
            counts[s] = counts.get(s, 0) + 1
            if s not in first_idx:
                first_idx[s] = idx
    for h in state_sections:
        c = counts.get(h, 0)
        if c == 0:
            failures.append(
                "FAIL state: required section heading {0!r} is missing".format(
                    h)
            )
        elif c > 1:
            failures.append(
                "FAIL state: section heading {0!r} appears {1} times (each "
                "section must appear exactly once)".format(h, c)
            )
    present_in_file_order = sorted(first_idx, key=lambda h: first_idx[h])
    expected_present = [h for h in state_sections if h in first_idx]
    if present_in_file_order != expected_present:
        failures.append(
            "FAIL state: sections are out of order -- found {0}, expected "
            "order {1}".format(present_in_file_order, expected_present)
        )

    # (2)+(3) ## Established E-IDs: unique and strictly decreasing top-down.
    est_ids = []
    est_bounds = section_bounds(lines, ESTABLISHED_HEADING)
    if est_bounds is not None:
        start, end = est_bounds
        seen = set()
        ids_in_order = []
        for i in range(start, end):
            s = lines[i].strip()
            if not s.startswith("|"):
                continue
            if is_separator_row(s) or is_header_row(s):
                continue
            cell = first_cell(s)
            if not ID_RE.match(cell):
                continue
            if cell in seen:
                failures.append(
                    "FAIL state: duplicate E-ID {0} in {1}".format(
                        cell, ESTABLISHED_HEADING)
                )
            seen.add(cell)
            ids_in_order.append(cell)
        est_ids = ids_in_order
        for earlier, later in zip(ids_in_order, ids_in_order[1:]):
            n_earlier = int(ID_RE.match(earlier).group(1))
            n_later = int(ID_RE.match(later).group(1))
            if n_earlier <= n_later:
                failures.append(
                    "FAIL state: {0} is not strictly greater than {1} in {2} "
                    "-- rows must run in strictly DECREASING E-ID order "
                    "top-down (newest at the top)".format(
                        earlier, later, ESTABLISHED_HEADING)
                )
                break

    # (4) Counter consistency: '- Next row ID: E<NNN>' > highest E-ID.
    counter = None
    log_bounds = section_bounds(lines, LOG_HEADING)
    if log_bounds is not None:
        for i in range(log_bounds[0], log_bounds[1]):
            m = NEXT_ID_RE.match(lines[i].strip())
            if m:
                counter = int(m.group(1))
                break
    if counter is None:
        failures.append(
            "FAIL state: no parseable '- Next row ID: E<NNN>' counter line "
            "in {0}".format(LOG_HEADING)
        )
    elif est_ids:
        top = max(int(ID_RE.match(r).group(1)) for r in est_ids)
        if counter <= top:
            failures.append(
                "FAIL state: counter {0} does not exceed the highest E-ID "
                "{1} in {2} -- the counter must name the NEXT id to "
                "assign".format(fmt_id(counter), fmt_id(top),
                                 ESTABLISHED_HEADING)
            )

    # (5) No literal pipes: every data row of ## Established and ## Open
    # must split into exactly 5 cells; more means an embedded pipe.
    for heading in (ESTABLISHED_HEADING, "## Open"):
        bounds = section_bounds(lines, heading)
        if bounds is None:
            continue
        for i in range(bounds[0], bounds[1]):
            s = lines[i].strip()
            if not s.startswith("|"):
                continue
            if is_separator_row(s) or is_header_row(s):
                continue
            n = len(cells(s))
            if n > 5:
                failures.append(
                    "FAIL state: row in {0} splits into {1} cells (expected "
                    "5) -- a literal pipe in cell text breaks the row shape; "
                    "use a slash or 'or' instead: {2!r}".format(
                        heading, n, s[:80])
                )

    return failures
