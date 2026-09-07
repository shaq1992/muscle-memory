"""Shared handback Delta-grammar validators and state/section primitives.

Pure, stdlib-only primitives lifted VERBATIM out of
harness/scripts/ingest_handback.py so that more than one consumer can import
the SAME grammar and the SAME state/section helpers instead of re-deriving
them: the ingest script (the orchestrator's pen), the handback Stop hook
(hooks/enforce_handback.py), and a future on-demand state-structure check.

This module hosts two families:

  - Delta marker-block / row-shape GRAMMAR validators (OBSERVATION_TAGS,
    OPEN_MANUAL_MARKER, the ID/observation regexes, first_cell/cells/
    is_separator_row/is_header_row, the Delta class, parse_delta,
    parse_observations);
  - shared STATE/SECTION primitives the ingest, the Stop hook, and the
    state-structure check all need (the ESTABLISHED_HEADING / LOG_HEADING
    section names, the ID_MAX ceiling, the NEXT_ID_RE counter regex, and the
    fmt_id / section_bounds / normalized pure helpers).

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
