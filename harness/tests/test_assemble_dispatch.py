"""Behavioral tests for the dispatch-assembly script (schema v2, D2).

harness/scripts/assemble_dispatch.py turns an orchestrator-authored task body,
the session args (plan name, session number, branch) and a list of row E-IDs
into the COMPLETE dispatch prompt -- including the exact ## Orchestration
block owned by commands/orchestrator.md Step 7 -- and writes the per-session
dispatch manifest (docs/orchestration/<plan>/dispatches/<NN>.json) in the
same run, so the manifest hash matches the prompt by construction.

The accumulation branch (--accumulation-branch, default integration/<plan>)
is the branch sessions are cut from and merge back into. It is emitted in the
Branch field's "(cut from <branch>)" continuation line, in the
"- **Accumulation branch:** <branch>" field line immediately after it, and
in the manifest's "accumulation_branch" key. An invalid value fails closed
with nothing written.

The invocation line (--command, default grill_and_implement) is the line
telling the session that opens the prompt WHICH command to run. The written
body carries exactly one "/grill_and_implement" line: an existing one (bare
or with arguments) is kept; otherwise the bare line is inserted directly
after the body's first H1, blank-line separated, ahead of the TDD-posture
stamp. A body invoking another command, or the requested one twice, fails
closed; "--command none" inserts and checks nothing. The inserted line is
covered by prompt_sha256 by construction.

Each case states the failure it prevents.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import hashlib
import json
import re
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

TDD posture: OPTIONAL
"""

# The same body WITHOUT its invocation line: H1 first, posture stamp last.
BODY_NO_INVOCATION = BODY_TEXT.split("\n", 2)[2]

INVOCATION_LINE_RE = re.compile(r"^/grill_and_implement", re.MULTILINE)


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

    def run_assembler(self, rows="E001,E003", session=None, extra=None,
                      accumulation_branch=None):
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
        if accumulation_branch is not None:
            # The '=' form, so values starting with '-' (and the empty
            # string) reach argparse as the option's value.
            argv.append(
                "--accumulation-branch={0}".format(accumulation_branch)
            )
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
            "  (cut from integration/{0})\n"
            "- **Accumulation branch:** integration/{0}\n".format(PLAN_NAME),
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

    def test_default_accumulation_branch_in_block_and_manifest(self):
        # Prevents: a flag-less dispatch (every plan that never declared an
        # accumulation branch) losing the integration/<plan> default -- the
        # session would be cut from, and merge back into, the wrong branch.
        r = self.run_assembler()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        expected = "integration/{0}".format(PLAN_NAME)
        text = self.prompt_path.read_text(encoding="utf-8")
        self.assertIn("  (cut from {0})\n".format(expected), text)
        self.assertIn(
            "- **Accumulation branch:** {0}\n".format(expected), text
        )
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(expected, manifest["accumulation_branch"])

    def test_custom_accumulation_branch_emitted_everywhere(self):
        # Prevents: a declared accumulation branch (e.g. fix/<name>) reaching
        # only some of its three emission sites, so the prompt and manifest
        # disagree on where the session is cut from and merges back into.
        custom = "fix/diff-bag-identity"
        r = self.run_assembler(accumulation_branch=custom)
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        text = self.prompt_path.read_text(encoding="utf-8")
        self.assertIn(
            "- **Branch:** {0}-session-07\n"
            "  (cut from {1})\n"
            "- **Accumulation branch:** {1}\n".format(PLAN_NAME, custom),
            text,
        )
        self.assertNotIn("integration/{0}".format(PLAN_NAME), text)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(custom, manifest["accumulation_branch"])
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

    def test_body_without_tdd_posture_blocks(self):
        # Prevents: the measured 2026-08-17 defect -- a dispatched prompt
        # going out with no 'TDD posture:' stamp, forcing the receiving
        # session to self-apply the preferences rule the orchestrator was
        # supposed to decide (orchestrator.md Step 7: exactly one line).
        self.body_path.write_text(
            BODY_TEXT.replace("TDD posture: OPTIONAL\n", ""),
            encoding="utf-8",
        )
        r = self.run_assembler()
        self.assertEqual(1, r.returncode)
        self.assertIn("TDD-posture", r.stdout)
        self.assertIn("TDD posture: WARRANTED", r.stdout)
        self.assertIn("TDD posture: OPTIONAL", r.stdout)
        self.assertFalse(self.prompt_path.exists())
        self.assertFalse(self.manifest_path.exists())

    def test_body_with_illegal_posture_value_blocks(self):
        # Prevents: a stamp carrying a value the receiving command does not
        # recognise -- only WARRANTED and OPTIONAL are legal.
        self.body_path.write_text(
            BODY_TEXT.replace(
                "TDD posture: OPTIONAL", "TDD posture: MANDATORY"
            ),
            encoding="utf-8",
        )
        r = self.run_assembler()
        self.assertEqual(1, r.returncode)
        self.assertIn("TDD-posture", r.stdout)
        self.assertFalse(self.prompt_path.exists())
        self.assertFalse(self.manifest_path.exists())

    def test_body_with_duplicate_tdd_posture_blocks(self):
        # Prevents: two contradicting stamps in one body -- the receiving
        # session would have to pick one, which is a second author for a
        # decision that must have exactly one.
        self.body_path.write_text(
            BODY_TEXT + "\nTDD posture: WARRANTED\n", encoding="utf-8"
        )
        r = self.run_assembler()
        self.assertEqual(1, r.returncode)
        self.assertIn("2 TDD-posture lines", r.stdout)
        self.assertFalse(self.prompt_path.exists())
        self.assertFalse(self.manifest_path.exists())

    def test_missing_established_section_blocks(self):
        # Prevents: extracting "rows" from a file that is not a v2 state
        # file at all.
        self.state_path.write_text("# not a state file\n", encoding="utf-8")
        r = self.run_assembler()
        self.assertEqual(1, r.returncode)
        self.assertIn("Established", r.stdout)
        self.assertFalse(self.prompt_path.exists())

    def test_invalid_accumulation_branch_writes_nothing(self):
        # Prevents: a malformed accumulation branch (whitespace, '..', a
        # leading '-' that git would read as an option, a trailing '/' or
        # '.lock', or nothing at all) being baked into a dispatch the
        # session would then fail to cut from or merge into.
        for value in [
            "fix/has space",
            "fix/../x",
            "fix/x/",
            "fix/x.lock",
            "-fix",
            "",
        ]:
            with self.subTest(accumulation_branch=value):
                r = self.run_assembler(accumulation_branch=value)
                self.assertEqual(1, r.returncode, r.stdout + r.stderr)
                self.assertIn("--accumulation-branch", r.stdout)
                self.assertFalse(self.prompt_path.exists())
                self.assertFalse(self.manifest_path.exists())


class TestInvocationLine(AssembleDispatchEnv):
    def test_missing_line_inserted_after_h1_before_posture(self):
        # Prevents: a dispatched prompt opened via "@docs/prompts/..." that
        # never names the command to run -- the ## Orchestration block says
        # only that the session is orchestrated, so the session would have
        # to guess; and an insertion landing anywhere but directly after the
        # H1 (e.g. after the posture stamp) drifting from the layout
        # orchestrator.md Step 7 documents.
        self.body_path.write_text(BODY_NO_INVOCATION, encoding="utf-8")
        r = self.run_assembler()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        expected_lead = (
            b"# Session 07: the thing\n"
            b"\n"
            b"/grill_and_implement\n"
            b"\n"
            b"Build the thing per the ratified design.\n"
            b"\n"
            b"TDD posture: OPTIONAL\n"
            b"\n"
            b"## Orchestration\n"
        )
        written = self.prompt_path.read_bytes()
        self.assertTrue(
            written.startswith(expected_lead),
            "prompt leading bytes:\n{0!r}".format(written[:len(expected_lead)]),
        )
        text = written.decode("utf-8")
        self.assertEqual(1, len(INVOCATION_LINE_RE.findall(text)))

    def test_existing_line_with_arguments_kept_not_duplicated(self):
        # Prevents: a body the orchestrator already wrote with the full
        # "/grill_and_implement <plan> session <NN> -- <title>" line gaining
        # a second, bare copy -- two invocation lines in one prompt.
        r = self.run_assembler()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        text = self.prompt_path.read_text(encoding="utf-8")
        self.assertEqual(1, len(INVOCATION_LINE_RE.findall(text)))
        self.assertTrue(text.startswith(BODY_TEXT.rstrip("\n")))

    def test_body_invoking_other_command_blocks(self):
        # Prevents: a body meant for some other command being silently
        # rewritten into a /grill_and_implement dispatch (or shipped with two
        # different invocation lines) -- the FAIL must point at the explicit
        # opt-out so the fix is a flag, not a hand edit of the body.
        self.body_path.write_text(
            BODY_TEXT.replace(
                "/grill_and_implement example-plan",
                "/other_command example-plan",
            ),
            encoding="utf-8",
        )
        r = self.run_assembler()
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        fail_lines = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
        self.assertTrue(
            any("/other_command" in l and "--command none" in l
                for l in fail_lines),
            r.stdout,
        )
        self.assertFalse(self.prompt_path.exists())
        self.assertFalse(self.manifest_path.exists())

    def test_body_invoking_command_twice_blocks(self):
        # Prevents: two invocation lines in one body -- a second author for
        # the single instruction telling the session what to run.
        self.body_path.write_text(
            BODY_TEXT + "\n/grill_and_implement\n", encoding="utf-8"
        )
        r = self.run_assembler()
        self.assertEqual(1, r.returncode, r.stdout + r.stderr)
        self.assertIn("2 lines invoke /grill_and_implement", r.stdout)
        self.assertFalse(self.prompt_path.exists())
        self.assertFalse(self.manifest_path.exists())

    def test_command_none_inserts_and_checks_nothing(self):
        # Prevents: the explicit opt-out for a non-grill_and_implement
        # dispatch still failing on, or injecting, a /grill_and_implement
        # line -- the body must go out exactly as authored.
        other_body = BODY_TEXT.replace(
            "/grill_and_implement example-plan", "/other_command example-plan"
        )
        self.body_path.write_text(other_body, encoding="utf-8")
        r = self.run_assembler(extra=["--command", "none"])
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        text = self.prompt_path.read_text(encoding="utf-8")
        self.assertEqual([], INVOCATION_LINE_RE.findall(text))
        self.assertTrue(text.startswith(other_body.rstrip("\n")))
        self.assertTrue(self.manifest_path.is_file())

    def test_invalid_command_value_writes_nothing(self):
        # Prevents: a mistyped --command (hyphen, space, capital, or nothing
        # at all) being pasted into the body as a bogus "/<value>" line, or
        # silently treated as the opt-out.
        for value in ["Bad-Name", "grill and implement", "GRILL", ""]:
            with self.subTest(command=value):
                r = self.run_assembler(
                    extra=["--command={0}".format(value)]
                )
                self.assertEqual(1, r.returncode, r.stdout + r.stderr)
                self.assertIn("--command", r.stdout)
                self.assertFalse(self.prompt_path.exists())
                self.assertFalse(self.manifest_path.exists())

    def test_manifest_hash_covers_inserted_line(self):
        # Prevents: a manifest hashed over the body BEFORE insertion -- the
        # receipt check in hooks/enforce_handback.py would then reject every
        # honest session that echoed the hash of the prompt it actually read.
        self.body_path.write_text(BODY_NO_INVOCATION, encoding="utf-8")
        r = self.run_assembler()
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        written = self.prompt_path.read_bytes()
        self.assertIn(b"\n/grill_and_implement\n", written)
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            hashlib.sha256(written).hexdigest(), manifest["prompt_sha256"]
        )
        # And the hash is NOT the pre-insertion body's prompt.
        self.assertNotEqual(
            hashlib.sha256(
                BODY_NO_INVOCATION.rstrip("\n").encode("utf-8")
            ).hexdigest(),
            manifest["prompt_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
