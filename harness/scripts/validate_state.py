"""Structure-check an orchestration state file on demand.

Usage: python3 .claude/harness/scripts/validate_state.py <state_file>

A THIN CLI wrapper around check_state_structure() in the pure module
harness/scripts/handback_validation.py -- ALL logic lives there; this script
only reads the file, hands its lines to the validator, and owns the
fail-closed exit policy (the pure validator never exits and never prints,
exactly like every other validator in that module). It lets a human or a
procedure run the same whole-file state check the ingest applies, without
staging a handback.

The structure enforced is DEFINED in harness/templates/state_schema.md; that
template and check_state_structure are a lockstep contract -- any change to
the state structure must update BOTH.

Failure contract: one "FAIL state: <detail>" line per finding on STDERR,
exit code 1. Success: one "OK: <path> is structurally valid" line on stdout,
exit code 0. Missing argument: a short usage line, exit code 2.
Portable: stdlib-only, ASCII, no host-project paths.
"""

import os
import sys

# check_state_structure lives in a pure module ALONGSIDE this script; ensure
# this script's own directory is importable when invoked by bare path,
# mirroring ingest_handback.py.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from handback_validation import check_state_structure  # noqa: E402


def main(argv):
    if len(argv) != 2:
        print("Usage: python3 validate_state.py <state_file>")
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        print("FAIL state: state file unreadable: {0}".format(exc),
              file=sys.stderr)
        return 1

    lines = text.splitlines()
    failures = check_state_structure(lines)
    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        return 1
    print("OK: {0} is structurally valid".format(path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
