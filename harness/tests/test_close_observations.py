"""Behavioral tests for harness/scripts/close_observations.py.

The script writes the closing ("disposition") line of docs/observations.md
-- the only writer of that line, since the orchestrator cannot Edit the file
under its isolation hook -- and counts the OPEN observations per tag for the
two-strikes notice (commands/orchestrator.md Step 10). The line shape is
defined in harness/templates/handback_schema.md:

    YYYY-MM-DD | <plan> | <NN or -> | disposition | L<n>[,L<n>...] <verdict>: <note>

Each case states the failure it prevents.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import HARNESS_ROOT

SCRIPT = HARNESS_ROOT / "harness" / "scripts" / "close_observations.py"

SEED = (
    "2026-10-05 | pet-poc | 05 | other | Stop hook fired while waiting\n"
    "2026-10-09 | pet-poc | 07 | hook-friction | Stop hook fired again\n"
    "2026-10-12 | pet-poc | 11 | prompt-underspecified | missing path\n"
    "2026-10-13 | pet-poc | 14 | hook-friction | and again\n"
)


class CloseEnv(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.obs = Path(self._tmpdir.name) / "observations.md"
        self.obs.write_text(SEED, encoding="utf-8")

    def run_script(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--observations", str(self.obs)]
            + list(args),
            capture_output=True, text=True, timeout=30,
        )

    def close(self, refs, verdict="fixed", note="hook allows OPEN stops",
              session="03"):
        return self.run_script(
            "--plan", "harness-improv-v7", "--session", session,
            "--refs", refs, "--verdict", verdict, "--note", note,
            "--date", "2026-10-16",
        )

    def text(self):
        return self.obs.read_text(encoding="utf-8")


class TestClose(CloseEnv):
    def test_appends_one_line_in_fixed_shape(self):
        # Prevents: a closing line in a shape the count (or a grep) cannot
        # tell apart from an observation, or an edit of an existing line.
        r = self.close("2,4")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertEqual(
            SEED + "2026-10-16 | harness-improv-v7 | 03 | disposition | "
            "L2,L4 fixed: hook allows OPEN stops\n",
            self.text(),
        )

    def test_refusals_leave_file_untouched(self):
        # Prevents: a closing line naming a line that does not exist, a
        # closing line, or an already-closed observation; an unknown
        # verdict; a note that would break the line shape.
        self.assertEqual(0, self.close("1").returncode)
        after_first = self.text()
        cases = [
            ("ref out of range", dict(refs="9")),
            ("ref to line 0", dict(refs="0")),
            ("ref to a closing line", dict(refs="5")),
            ("already closed", dict(refs="1")),
            ("malformed refs", dict(refs="L2")),
            ("unknown verdict", dict(refs="2", verdict="done")),
            ("pipe in note", dict(refs="2", note="a | b")),
            ("bad session", dict(refs="2", session="3")),
        ]
        for label, kwargs in cases:
            with self.subTest(case=label):
                r = self.close(**kwargs)
                self.assertEqual(1, r.returncode, r.stdout + r.stderr)
                self.assertIn("FAIL", r.stdout)
                self.assertEqual(after_first, self.text())


class TestCount(CloseEnv):
    def test_closed_observations_and_closing_lines_do_not_count(self):
        # Prevents: a fixed defect keeping its tag at two strikes forever,
        # and closing lines being counted as a "disposition" tag.
        r = self.run_script("--count")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("hook-friction 2", r.stdout)
        self.assertEqual(0, self.close("2", verdict="fixed").returncode)
        r = self.run_script("--count")
        self.assertIn("hook-friction 1", r.stdout)
        self.assertIn("other 1", r.stdout)
        self.assertNotIn("disposition", r.stdout)


if __name__ == "__main__":
    unittest.main()
