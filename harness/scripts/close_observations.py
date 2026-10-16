"""Close earlier observations in docs/observations.md, or count open ones.

Usage:
  python3 .claude/harness/scripts/close_observations.py
      [--observations docs/observations.md] --plan <plan_name>
      [--session <NN>|-] --refs 5,7 --verdict <verdict> --note "<text>"
      [--date YYYY-MM-DD]
  python3 .claude/harness/scripts/close_observations.py
      [--observations docs/observations.md] --count

CLOSE (the default mode) appends ONE closing ("disposition") line, in the
shape harness/templates/handback_schema.md defines:

    YYYY-MM-DD | <plan_name> | <NN or -> | disposition | L<n>[,L<n>...] <verdict>: <note>

L<n> is the 1-based line number of an earlier observation line; line numbers
are stable because the file is append-only. --plan is the plan whose
orchestrator closes the lines (the plan that fixed them, or the one judging
them); --session the session that did the work, or "-". This script is the
ONLY writer of the line: the orchestrator cannot Edit docs/observations.md
under hooks/enforce_orchestrator_isolation.py, and a handback cannot carry
one (the reserved word "disposition" is not in the tag vocabulary of
handback_validation.py). Fail-closed: every ref must name an existing
observation line -- not a closing line, not one an earlier closing line
already names; the verdict must be in VERDICTS; the note must be non-empty
and carry no "|" or newline; --session must be "-" or two or more digits.
Any failure prints "FAIL <check>: <detail>" lines and exits 1 with the file
untouched. Success prints "OK: ..." and exits 0. No existing line is ever
edited.

COUNT (--count) prints "<tag> <N>" per tag, most frequent first, over the
OPEN observation lines: closing lines are skipped, and so is every
observation a closing line names. This is the mechanical count behind the
two-strikes notice (commands/orchestrator.md Step 10).

Stdlib-only, ASCII, no host-project paths.
"""

import argparse
import datetime
import re
import sys

DISPOSITION_TAG = "disposition"
VERDICTS = ("fixed", "wontfix", "duplicate", "not-structural")
# date | plan | NN or - | tag | description
LINE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \| [^|]*\S[^|]* \| [^|]*\S[^|]* \| "
    r"([A-Za-z][A-Za-z-]*) \| (.+)$"
)
DISPOSITION_DESC_RE = re.compile(
    r"^(L\d+(?:,L\d+)*) ([a-z-]+): \S"
)
REFS_ARG_RE = re.compile(r"^\d+(?:,\d+)*$")
SESSION_RE = re.compile(r"^(?:-|\d{2,})$")


def classify(lines):
    """(observations, closed) -- observations maps line number -> tag for
    every observation line; closed is the set of line numbers some closing
    line names."""
    observations = {}
    closed = set()
    for number, line in enumerate(lines, start=1):
        m = LINE_RE.match(line.rstrip("\n"))
        if m is None:
            continue
        tag, desc = m.group(1), m.group(2)
        if tag == DISPOSITION_TAG:
            d = DISPOSITION_DESC_RE.match(desc)
            if d is not None:
                closed.update(int(ref[1:]) for ref in d.group(1).split(","))
            continue
        observations[number] = tag
    return observations, closed


def count(lines):
    observations, closed = classify(lines)
    counts = {}
    for number, tag in observations.items():
        if number not in closed:
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Close earlier observations, or count open ones.")
    parser.add_argument("--observations", default="docs/observations.md")
    parser.add_argument("--count", action="store_true",
                        help="print open observation counts per tag")
    parser.add_argument("--plan")
    parser.add_argument("--session", default="-")
    parser.add_argument("--refs", help="comma-separated line numbers, e.g. 5,7")
    parser.add_argument("--verdict", help="one of: " + ", ".join(VERDICTS))
    parser.add_argument("--note")
    parser.add_argument("--date", default=None,
                        help="YYYY-MM-DD (default: today)")
    args = parser.parse_args(argv)

    try:
        with open(args.observations, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError as exc:
        print("FAIL observations: cannot read {0}: {1}".format(
            args.observations, exc))
        return 1

    if args.count:
        for tag, n in count(lines):
            print("{0} {1}".format(tag, n))
        return 0

    failures = []
    for name in ("plan", "refs", "verdict", "note"):
        if not getattr(args, name):
            failures.append("FAIL args: --{0} is required".format(name))
    if args.plan and ("|" in args.plan or not args.plan.strip()):
        failures.append("FAIL args: --plan must be a plan name with no '|'")
    if not SESSION_RE.match(args.session):
        failures.append(
            "FAIL args: --session must be '-' or a session number such as "
            "03, got {0!r}".format(args.session))
    if args.verdict and args.verdict not in VERDICTS:
        failures.append("FAIL args: --verdict {0!r} is not one of {1}".format(
            args.verdict, ", ".join(VERDICTS)))
    if args.note is not None and (
            "|" in args.note or "\n" in args.note or not args.note.strip()):
        failures.append(
            "FAIL args: --note must be one non-empty line with no '|'")
    date = args.date or datetime.date.today().isoformat()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        failures.append("FAIL args: --date must be YYYY-MM-DD")

    refs = []
    if args.refs:
        if not REFS_ARG_RE.match(args.refs):
            failures.append(
                "FAIL refs: --refs must be comma-separated line numbers "
                "(e.g. 5,7), got {0!r}".format(args.refs))
        else:
            observations, closed = classify(lines)
            for ref in sorted(set(int(r) for r in args.refs.split(","))):
                if ref < 1 or ref > len(lines):
                    failures.append(
                        "FAIL refs: line {0} does not exist ({1} has {2} "
                        "lines)".format(ref, args.observations, len(lines)))
                elif ref not in observations:
                    failures.append(
                        "FAIL refs: line {0} is not an observation line (a "
                        "closing line, or not in the fixed shape)".format(ref))
                elif ref in closed:
                    failures.append(
                        "FAIL refs: line {0} is already closed".format(ref))
                else:
                    refs.append(ref)

    if failures:
        for line in failures:
            print(line)
        return 1

    new_line = "{0} | {1} | {2} | {3} | {4} {5}: {6}".format(
        date, args.plan.strip(), args.session, DISPOSITION_TAG,
        ",".join("L{0}".format(r) for r in refs), args.verdict,
        args.note.strip())
    with open(args.observations, "rb") as f:
        data = f.read()
    with open(args.observations, "a", encoding="utf-8") as f:
        if data and not data.endswith(b"\n"):
            f.write("\n")
        f.write(new_line + "\n")
    print("OK: appended to {0}: {1}".format(args.observations, new_line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
