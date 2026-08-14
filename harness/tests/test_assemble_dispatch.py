"""Behavioral tests for the dispatch-assembly script (schema v2, D2).

harness/scripts/assemble_dispatch.py turns an orchestrator-authored task body,
the session args (plan name, session number, branch) and a list of row E-IDs
into the COMPLETE dispatch prompt -- including the exact ## Orchestration
block owned by commands/orchestrator.md Step 7 -- and writes the per-session
dispatch manifest (docs/orchestration/<plan>/dispatches/<NN>.json) in the
same run, so the manifest hash matches the prompt by construction.

Each case states the failure it prevents.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import HARNESS_ROOT, PLAN_NAME

ASSEMBLE_DISPATCH = (
    HARNESS_ROOT / "harness" / "scripts" / "assemble_dispatch.py"
)

STATE_FILE_TEXT = """# Orchestration State: example-plan

Status: ACTIVE

## Objective

Prove the assembler.

## Established

| ID | Statement | Provenance | Disposition | Revisit trigger |
|---|---|---|---|---|
| E001 | The nightly export completes in 6-8 minutes. | `measured` | `fact` | - |
| E002 | Every write path stays idempotent. | `inferred` | `invariant` | - |
| E003 | Batch size fixed at 500. | `measured` | `settled` | If renegotiated. |

## Open

| Question | Blocks | Cost to resolve | Who can resolve | Status |

## Next

none

## Maybe

none

## Dispatched

| Session | Prompt path | Handback path | Status |

## Orchestrator log

- Incarnations: 1
- Next row ID: E004
"""

BODY_TEXT = """/grill_and_implement example-plan session 07 -- do the thing

# Session 07: the thing

Build the thing per the ratified design.
"""


class AssembleDispatchEnv(unittest.TestCase):
    """Fixture: a temp project tree with a v2 state file and a body file."""

    SESSION = "07"

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.proj = Path(self._tmpdir.name)

        self.orch_dir = self.proj / "docs" / "orchestration"
        self.orch_dir.mkdir(parents=True)
        self.state_path = self.orch_dir / "{0}_state.md".format(PLAN_NAME)
        self.state_path.write_text(STATE_FILE_TEXT, encoding="utf-8")

        self.body_path = self.proj / "body.md"
        self.body_path.write_text(BODY_TEXT, encoding="utf-8")

        self.prompt_path = (
            self.proj / "docs" / "prompts" / "140826"
            / "{0}_session_{1}_prompt.md".format(PLAN_NAME, self.SESSION)
        )
        self.prompt_path.parent.mkdir(parents=True)

        self.manifest_path = (
            self.orch_dir / PLAN_NAME / "dispatches"
            / "{0}.json".format(self.SESSION)
        )

    def run_assembler(self, rows="E001,E003", session=None, extra=None):
        argv = [
            sys.executable,
            str(ASSEMBLE_DISPATCH),
            "--state", str(self.state_path),
            "--body", str(self.body_path),
            "--plan", PLAN_NAME,
            "--session", session or self.SESSION,
            "--branch",
            "{0}-session-{1}".format(PLAN_NAME, session or self.SESSION),
            "--rows", rows,
            "--out", str(self.prompt_path),
        ]
        if extra:
            argv.extend(extra)
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=30
        )


class TestPositiveAssembly(AssembleDispatchEnv):
    def test_prompt_carries_body_and_exact_block(self):
        # Prevents: an assembler emitting a block the receiving command does
        # not recognise, silently dropping the session into the standalone
        # lane where it would open a pull request.
        r = self.run_assembler()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        text = self.prompt_path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(BODY_TEXT.rstrip("\n")))
        self.assertIn("\n## Orchestration\n", text)
        self.assertIn(
            "- **State file:** {0}\n".format(self.state_path), text
        )
        self.assertIn(
            "- **Handback:** docs/orchestration/{0}/handbacks/07.md\n".format(
                PLAN_NAME
            ),
            text,
        )
        self.assertIn(
            "- **Branch:** {0}-session-07\n"
            "  (cut from integration/{0})\n".format(PLAN_NAME),
            text,
        )
        self.assertIn("- **Rows this session must obey:**\n", text)

    def test_rows_are_verbatim_from_state(self):
        # Prevents: the paraphrase/second-author drift D2 exists to kill --
        # a reworded clause is a second author for a fact that must have
        # exactly one.
        r = self.run_assembler(rows="E001,E003")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        text = self.prompt_path.read_text(encoding="utf-8")
        for row_line in [
            "| E001 | The nightly export completes in 6-8 minutes. "
            "| `measured` | `fact` | - |",
            "| E003 | Batch size fixed at 500. | `measured` | `settled` "
            "| If renegotiated. |",
        ]:
            self.assertIn("  {0}\n".format(row_line), text)
        # An unselected row never leaks in.
        self.assertNotIn("E002", text)

    def test_manifest_matches_prompt_by_construction(self):
        # Prevents: a manifest whose hash does not match the prompt it claims
        # to describe -- the by-construction guarantee the whole receipt
        # verification chain rests on.
        r = self.run_assembler(rows="E001,E003")
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertTrue(self.manifest_path.is_file())
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(PLAN_NAME, manifest["plan_name"])
        self.assertEqual("07", manifest["session_number"])
        self.assertEqual(["E001", "E003"], manifest["row_ids"])
        self.assertEqual(str(self.prompt_path), manifest["prompt_path"])
        digest = hashlib.sha256(
            self.prompt_path.read_bytes()
        ).hexdigest()
        self.assertEqual(digest, manifest["prompt_sha256"])


class TestFailClosed(AssembleDispatchEnv):
    def test_missing_row_id_writes_nothing(self):
        # Prevents: a dispatch silently missing an isolation clause the
        # orchestrator selected -- the session would then run without a
        # pinned invariant it was meant to obey.
        r = self.run_assembler(rows="E001,E999")
        self.assertEqual(1, r.returncode)
        self.assertIn("E999", r.stdout)
        self.assertFalse(self.prompt_path.exists())
        self.assertFalse(self.manifest_path.exists())

    def test_malformed_row_id_writes_nothing(self):
        # Prevents: a typo'd ID list producing a half-specified dispatch.
        r = self.run_assembler(rows="E001,banana")
        self.assertEqual(1, r.returncode)
        self.assertIn("banana", r.stdout)
        self.assertFalse(self.prompt_path.exists())
        self.assertFalse(self.manifest_path.exists())

    def test_existing_prompt_or_manifest_blocks(self):
        # Prevents: two sessions colliding onto one NN's artifact paths --
        # session numbers are monotonic and never reused.
        self.prompt_path.write_text("already here\n", encoding="utf-8")
        r = self.run_assembler()
        self.assertEqual(1, r.returncode)
        self.assertEqual(
            "already here\n", self.prompt_path.read_text(encoding="utf-8")
        )
        self.assertFalse(self.manifest_path.exists())

        self.prompt_path.unlink()
        self.manifest_path.parent.mkdir(parents=True)
        self.manifest_path.write_text("{}\n", encoding="utf-8")
        r = self.run_assembler()
        self.assertEqual(1, r.returncode)
        self.assertFalse(self.prompt_path.exists())
        self.assertEqual(
            "{}\n", self.manifest_path.read_text(encoding="utf-8")
        )

    def test_missing_established_section_blocks(self):
        # Prevents: extracting "rows" from a file that is not a v2 state
        # file at all.
        self.state_path.write_text("# not a state file\n", encoding="utf-8")
        r = self.run_assembler()
        self.assertEqual(1, r.returncode)
        self.assertIn("Established", r.stdout)
        self.assertFalse(self.prompt_path.exists())


if __name__ == "__main__":
    unittest.main()
