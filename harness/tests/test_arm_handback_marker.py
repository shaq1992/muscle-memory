"""Behavioral tests for the handback-marker ARMING hook.

hooks/arm_handback_marker.py is the UserPromptSubmit companion to
enforce_handback.py: the moment a dispatched prompt carrying the
"## Orchestration" block with a "- **Handback:**" field is submitted, it
writes .claude/handback_session.json deterministically, before the model
has read a word of the prompt. These tests pin the three-file marker
contract (arm_handback_marker.py writes it, enforce_handback.py reads it,
commands/grill_and_implement.md Step 0a item 2 specifies it) and the
block-shape contract (the block is produced by
harness/scripts/assemble_dispatch.py orchestration_block(); the arming
regexes must keep parsing its EXACT output).

Cases and the failures they prevent:

1. exact-block arming -- the real orchestration_block() output must arm a
   marker with exactly the keys session_id / plan_name / session_number /
   handback_path (a shape drift between assembler and arming hook would
   silently disarm every dispatched session);
2. Branch-less fallback -- plan/NN derive from the conventional handback
   path when the Branch field is absent or unparseable (a hand-edited
   dispatch must still arm);
3. silent no-ops -- no block, no Handback field, no session_id, and
   malformed stdin all exit 0 writing NOTHING (an arming hook that ever
   blocks or delays a prompt is worse than no hook);
4. end-to-end -- a marker written by the arming hook is honored by a copy
   of enforce_handback.py (blocks a missing handback for the same
   session_id), proving the writer and the reader agree on the schema.

Also pinned as ACTUAL implemented behavior: the hook overwrites an
existing marker unconditionally (there is no not-clobber rule), and the
block's scope ends at the next H2 heading.

Like test_handback_hook.py, the hooks run as COPIES inside a temp tree,
so each hook's own-location-derived marker path (and enforce_handback's
project root) points at the temp tree, never at the real repository.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import HARNESS_ROOT, PLAN_NAME

# The arming hook parses the block that assemble_dispatch.py emits; build
# the fixture prompts from the REAL orchestration_block() so any shape
# change there is exercised here automatically.
sys.path.insert(0, str(HARNESS_ROOT / "harness" / "scripts"))
from assemble_dispatch import orchestration_block  # noqa: E402

ARM_HOOK = HARNESS_ROOT / "hooks" / "arm_handback_marker.py"
HANDBACK_HOOK = HARNESS_ROOT / "hooks" / "enforce_handback.py"

SESSION_NUMBER = "07"
BRANCH = "{0}-session-{1}".format(PLAN_NAME, SESSION_NUMBER)
HANDBACK_REL = "docs/orchestration/{0}/handbacks/{1}.md".format(
    PLAN_NAME, SESSION_NUMBER
)

# The exact key set the marker contract fixes across
# arm_handback_marker.py, enforce_handback.py and
# grill_and_implement.md Step 0a item 2.
MARKER_KEYS = {"session_id", "plan_name", "session_number", "handback_path"}

BODY_TEXT = (
    "/grill_and_implement {0} session {1} -- do the thing\n"
    "\n"
    "# Session {1}: the thing\n"
    "\n"
    "## Context\n"
    "\n"
    "Build the thing per the ratified design.\n"
    "\n"
    "TDD posture: OPTIONAL\n"
    "\n"
).format(PLAN_NAME, SESSION_NUMBER)

ROW_LINES = [
    "| E001 | The nightly export completes in 6-8 minutes. | `measured` "
    "| `fact` | - |",
]


def assembled_block(branch=BRANCH):
    """The verbatim ## Orchestration block for the fixture session."""
    return orchestration_block(
        "docs/orchestration/{0}_state.md".format(PLAN_NAME),
        PLAN_NAME,
        SESSION_NUMBER,
        branch,
        ROW_LINES,
    )


def dispatched_prompt(branch=BRANCH):
    """A dispatch prompt as assemble_dispatch.py lays it out: task body
    first, the ## Orchestration block appended last."""
    return BODY_TEXT + assembled_block(branch)


class ArmHookEnv(unittest.TestCase):
    """Fixture running a COPY of arm_handback_marker.py in a temp tree."""

    SESSION = "unittest-arm-hook-session"

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmp = Path(self._tmpdir.name)

        self.proj = tmp / "proj"
        hooks_dir = self.proj / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        self.hook_copy = hooks_dir / "arm_handback_marker.py"
        shutil.copyfile(str(ARM_HOOK), str(self.hook_copy))
        self.marker_path = self.proj / ".claude" / "handback_session.json"

    def run_arm(self, stdin_text):
        """Feed raw stdin to the arming hook; assert the universal posture:
        exit 0, no stdout, no stderr (on UserPromptSubmit, stdout would be
        injected as context and a non-zero exit would block the prompt)."""
        r = subprocess.run(
            [sys.executable, str(self.hook_copy)],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            0, r.returncode,
            "arming hook exited non-zero: stdout={0!r} stderr={1!r}".format(
                r.stdout, r.stderr
            ),
        )
        self.assertEqual("", r.stdout, "arming hook must never emit stdout")
        self.assertEqual("", r.stderr, "arming hook must never emit stderr")
        return r

    def arm(self, prompt, session=None):
        payload = {"prompt": prompt}
        if session is not None:
            payload["session_id"] = session
        self.run_arm(json.dumps(payload))

    def read_marker(self):
        return json.loads(self.marker_path.read_text(encoding="utf-8"))


class TestExactBlockArms(ArmHookEnv):
    def test_assembled_block_arms_full_marker(self):
        # Prevents: a shape drift between assemble_dispatch.py's block and
        # the arming regexes silently disarming every dispatched session.
        self.arm(dispatched_prompt(), session=self.SESSION)
        self.assertTrue(self.marker_path.exists(), "marker was not armed")
        marker = self.read_marker()
        self.assertEqual(
            MARKER_KEYS, set(marker),
            "marker key set must match the three-file contract exactly",
        )
        self.assertEqual(self.SESSION, marker["session_id"])
        self.assertEqual(PLAN_NAME, marker["plan_name"])
        self.assertEqual(SESSION_NUMBER, marker["session_number"])
        self.assertEqual(HANDBACK_REL, marker["handback_path"])

    def test_block_scope_ends_at_next_h2(self):
        # Prevents: a Handback-looking line in a LATER section being read
        # as the block's field -- the block's scope is heading to next H2.
        prompt = (
            dispatched_prompt()
            + "\n## Appendix\n\n- **Handback:** docs/decoy/never.md\n"
        )
        self.arm(prompt, session=self.SESSION)
        self.assertEqual(HANDBACK_REL, self.read_marker()["handback_path"])

    def test_overwrites_existing_marker_unconditionally(self):
        # Pins ACTUAL behavior: re-arming clobbers whatever marker exists
        # (a stale marker from an abandoned session must never survive a
        # fresh dispatch). There is deliberately NO not-clobber rule.
        self.marker_path.write_text(
            json.dumps(
                {
                    "session_id": "stale-earlier-session",
                    "plan_name": "old-plan",
                    "session_number": "01",
                    "handback_path": "docs/orchestration/old/handbacks/01.md",
                }
            ),
            encoding="utf-8",
        )
        self.arm(dispatched_prompt(), session=self.SESSION)
        marker = self.read_marker()
        self.assertEqual(self.SESSION, marker["session_id"])
        self.assertEqual(HANDBACK_REL, marker["handback_path"])


class TestBranchlessFallback(ArmHookEnv):
    def _strip_branch(self, prompt):
        lines = [
            ln for ln in prompt.splitlines()
            if not ln.startswith("- **Branch:**")
            and "(cut from" not in ln
        ]
        return "\n".join(lines) + "\n"

    def test_branchless_block_derives_from_handback_path(self):
        # Prevents: a hand-edited dispatch without a Branch field arming a
        # marker with null plan/NN when both are derivable from the
        # conventional handback path docs/orchestration/<plan>/handbacks/
        # <NN>.md.
        self.arm(
            self._strip_branch(dispatched_prompt()), session=self.SESSION
        )
        marker = self.read_marker()
        self.assertEqual(PLAN_NAME, marker["plan_name"])
        self.assertEqual(SESSION_NUMBER, marker["session_number"])
        self.assertEqual(HANDBACK_REL, marker["handback_path"])

    def test_unparseable_branch_falls_back_to_path(self):
        # Prevents: a branch value outside <plan>-session-<NN> poisoning
        # the marker instead of triggering the same path fallback.
        self.arm(
            dispatched_prompt(branch="weird/branch-name"),
            session=self.SESSION,
        )
        marker = self.read_marker()
        self.assertEqual(PLAN_NAME, marker["plan_name"])
        self.assertEqual(SESSION_NUMBER, marker["session_number"])


class TestSilentNoOps(ArmHookEnv):
    def test_no_ops_write_nothing_and_stay_silent(self):
        # Prevents: the fail-soft posture regressing -- an arming hook that
        # blocks, delays, or pollutes a normal prompt is worse than none.
        # Every no-op is asserted to exit 0 with no output (run_arm) AND to
        # leave no marker behind.
        no_block = json.dumps(
            {"session_id": self.SESSION,
             "prompt": "just a normal prompt, Handback: nothing"}
        )
        block_without_handback = json.dumps(
            {"session_id": self.SESSION,
             "prompt": BODY_TEXT + "## Orchestration\n\n"
             "- **Branch:** {0}\n".format(BRANCH)}
        )
        missing_session_id = json.dumps({"prompt": dispatched_prompt()})
        blank_session_id = json.dumps(
            {"session_id": "   ", "prompt": dispatched_prompt()}
        )
        for label, stdin_text in [
            ("no-orchestration-block", no_block),
            ("block-without-handback-field", block_without_handback),
            ("missing-session-id", missing_session_id),
            ("blank-session-id", blank_session_id),
            ("malformed-stdin", "this is not json {"),
            ("non-dict-payload", json.dumps(["not", "a", "dict"])),
            ("empty-stdin", ""),
        ]:
            with self.subTest(case=label):
                self.run_arm(stdin_text)
                self.assertFalse(
                    self.marker_path.exists(),
                    "{0} must not arm a marker".format(label),
                )


class TestArmedMarkerHonoredEndToEnd(ArmHookEnv):
    def setUp(self):
        super(TestArmedMarkerHonoredEndToEnd, self).setUp()
        self.stop_hook_copy = (
            self.proj / ".claude" / "hooks" / "enforce_handback.py"
        )
        shutil.copyfile(str(HANDBACK_HOOK), str(self.stop_hook_copy))

    def stop_decision(self, session):
        r = subprocess.run(
            [sys.executable, str(self.stop_hook_copy)],
            input=json.dumps({"session_id": session}),
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(
            0, r.returncode,
            "stop hook exited non-zero: stdout={0!r} stderr={1!r}".format(
                r.stdout, r.stderr
            ),
        )
        if not r.stdout.strip():
            return "allow", ""
        out = json.loads(r.stdout)
        return out.get("decision", "allow"), out.get("reason", "")

    def test_armed_marker_blocks_missing_handback(self):
        # Prevents: the writer and the reader disagreeing on the marker
        # schema -- the whole point of deterministic arming is that a
        # session which then writes NO handback gets blocked at Stop.
        self.arm(dispatched_prompt(), session=self.SESSION)
        verdict, reason = self.stop_decision(self.SESSION)
        self.assertEqual(
            "block", verdict,
            "an armed session with no handback must be blocked at Stop",
        )
        self.assertIn(
            HANDBACK_REL, reason,
            "block reason must name the armed handback path",
        )
        self.assertTrue(self.marker_path.exists())

    def test_armed_marker_ignores_foreign_session(self):
        # Prevents: an armed marker leaking enforcement onto a DIFFERENT
        # session's Stop -- the session_id captured at arming time is the
        # one the Stop hook keys on.
        self.arm(dispatched_prompt(), session=self.SESSION)
        verdict, _ = self.stop_decision("some-other-session")
        self.assertEqual("allow", verdict)
        self.assertTrue(self.marker_path.exists())
