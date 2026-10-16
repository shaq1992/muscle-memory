"""Behavioral tests for the handback Stop-hook contract.

The eight ratified cases of the handback Stop-hook contract:
no-marker, foreign-session, missing handback, bad status, the three-line
abandon path, complete-and-self-delete, mutual exclusivity with the
phase-closing marker, and the verbatim unblocking content in every block
reason.

Schema v2 (D3) adds the read-receipt verification cases: when a dispatch
manifest exists at docs/orchestration/<plan>/dispatches/<NN>.json, the
receipt's row-ID list and prompt hash are verified against it on every Stop
evaluation except an ABANDONED close; a missing manifest is a structural
no-op on the hook path and a loud failure on the manual --check-receipt
path. Each new case states the failure it prevents.

Like test_closing_hook.py, the contract is exercised through hook COPIES
inside a temp tree, so each hook's own-location-derived project root (and
therefore the marker path and the relative handback_path resolution) points
at the temp tree, never at the real repository.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import CLOSING_HOOK, HARNESS_ROOT, PLAN_NAME

HANDBACK_HOOK = HARNESS_ROOT / "hooks" / "enforce_handback.py"

# The hook imports the shared Delta-grammar / observation validators at load
# time from a path computed off its OWN location (CLAUDE_DIR/harness/scripts),
# so a hook copy running inside the temp tree resolves the module inside that
# same tree. The fixture must therefore stage the real module alongside the
# hook copy, or every hook subprocess dies with ImportError.
HANDBACK_VALIDATION = (
    HARNESS_ROOT / "harness" / "scripts" / "handback_validation.py"
)

SESSION_NUMBER = 7

# The minimal content that unblocks the hook, exactly as the handback schema's
# binding constraint spells it. Every block reason must carry this verbatim.
ABANDON_MINIMUM = (
    "Status: ABANDONED\n"
    "\n"
    "Blocked on the staging credentials; nothing was changed.\n"
)

STUB_HANDBACK = (
    "Status: OPEN\n"
    "\n"
    "**Handed to this session (read receipt):**\n"
    "- | greenlist | the fixture row |\n"
)

# The v2 (D3) receipt shape: a row-ID list plus the SHA-256 of the dispatched
# prompt file, verified against the dispatch manifest.
PROMPT_SHA = "ab" * 32
OTHER_SHA = "cd" * 32

ID_RECEIPT_HEADER = (
    "**Handed to this session (read receipt):**\n"
    "- Rows: E001, E002\n"
    "- Prompt-SHA256: " + PROMPT_SHA + "\n"
)

ID_RECEIPT_STUB = "Status: OPEN\n\n" + ID_RECEIPT_HEADER

ID_RECEIPT_COMPLETE = (
    "Status: COMPLETE\n"
    "\n"
    + ID_RECEIPT_HEADER
    + "\n"
    "## Scope changes\n"
    "\n"
    "none\n"
    "\n"
    "## Delta\n"
    "\n"
    "none\n"
    "\n"
    "## For the next session\n"
    "\n"
    "Nothing outstanding.\n"
    "\n"
    "## Structural observations\n"
    "\n"
    "none\n"
)

COMPLETE_HANDBACK = (
    "Status: COMPLETE\n"
    "\n"
    "**Handed to this session (read receipt):**\n"
    "- | greenlist | the fixture row |\n"
    "\n"
    "## Scope changes\n"
    "\n"
    "none\n"
    "\n"
    "## Delta\n"
    "\n"
    "none\n"
    "\n"
    "## For the next session\n"
    "\n"
    "Nothing outstanding.\n"
    "\n"
    "## Structural observations\n"
    "\n"
    "none\n"
)

# A COMPLETE handback whose ## Delta carries a bare table row with no
# ADD/CHANGE/RETIRE marker line above it -- the exact malformed marker block
# parse_delta rejects with a "FAIL delta:" line. Every other section is valid,
# so the block can only come from the shared Delta grammar the hook now runs.
MALFORMED_DELTA_HANDBACK = (
    "Status: COMPLETE\n"
    "\n"
    "**Handed to this session (read receipt):**\n"
    "- | greenlist | the fixture row |\n"
    "\n"
    "## Scope changes\n"
    "\n"
    "none\n"
    "\n"
    "## Delta\n"
    "\n"
    "| E001 | a statement with no marker above it | a | b | c |\n"
    "\n"
    "## For the next session\n"
    "\n"
    "Nothing outstanding.\n"
    "\n"
    "## Structural observations\n"
    "\n"
    "none\n"
)


class HandbackHookEnv(unittest.TestCase):
    """Fixture running a COPY of enforce_handback.py in a temp project tree."""

    SESSION = "unittest-handback-hook-session"

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmp = Path(self._tmpdir.name)

        self.proj = tmp / "proj"
        hooks_dir = self.proj / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        self.hook_copy = hooks_dir / "enforce_handback.py"
        shutil.copyfile(str(HANDBACK_HOOK), str(self.hook_copy))
        self.closing_hook_copy = hooks_dir / "enforce_phase_closing.py"
        shutil.copyfile(str(CLOSING_HOOK), str(self.closing_hook_copy))

        # Stage the shared validator module where the hook's own-location
        # relative import (CLAUDE_DIR/harness/scripts) will find it inside the
        # isolated tree; without it every hook subprocess dies at ImportError.
        scripts_dir = self.proj / ".claude" / "harness" / "scripts"
        scripts_dir.mkdir(parents=True)
        shutil.copyfile(
            str(HANDBACK_VALIDATION),
            str(scripts_dir / "handback_validation.py"),
        )

        self.marker_path = self.proj / ".claude" / "handback_session.json"
        self.closing_marker_path = self.proj / ".claude" / "phase_closing.json"
        self.handback_rel = "docs/orchestration/{0}/handbacks/{1:02d}.md".format(
            PLAN_NAME, SESSION_NUMBER
        )
        self.handback_path = self.proj / self.handback_rel
        self.handback_path.parent.mkdir(parents=True)

    # -- fixture writers ---------------------------------------------------

    def write_marker(self, session=None, handback_path=None):
        self.marker_path.write_text(
            json.dumps(
                {
                    "session_id": session or self.SESSION,
                    "plan_name": PLAN_NAME,
                    "session_number": SESSION_NUMBER,
                    "handback_path": (
                        self.handback_rel if handback_path is None
                        else handback_path
                    ),
                }
            ),
            encoding="utf-8",
        )

    def write_closing_marker(self, session=None):
        self.closing_marker_path.write_text(
            json.dumps(
                {
                    "session_id": session or self.SESSION,
                    "plan_name": PLAN_NAME,
                    "phase": 3,
                    "learnings_path": "docs/learnings/090826/x_learnings.md",
                }
            ),
            encoding="utf-8",
        )

    def write_handback(self, text=COMPLETE_HANDBACK):
        self.handback_path.write_text(text, encoding="utf-8")

    def write_manifest(self, row_ids=("E001", "E002"), sha=PROMPT_SHA):
        self.manifest_rel = (
            "docs/orchestration/{0}/dispatches/{1:02d}.json".format(
                PLAN_NAME, SESSION_NUMBER
            )
        )
        path = self.proj / self.manifest_rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "plan_name": PLAN_NAME,
                    "session_number": "{0:02d}".format(SESSION_NUMBER),
                    "row_ids": list(row_ids),
                    "prompt_path": (
                        "docs/prompts/140826/{0}_session_{1:02d}_prompt.md"
                        .format(PLAN_NAME, SESSION_NUMBER)
                    ),
                    "prompt_sha256": sha,
                }
            ),
            encoding="utf-8",
        )
        return path

    def write_stale_pause_file(self, declaration):
        # The retired question-pause file. Written only to prove the hook no
        # longer reads, honours or deletes it.
        path = self.proj / ".claude" / "handback_pause.json"
        path.write_text(json.dumps(declaration), encoding="utf-8")
        return path

    # -- hook drivers ------------------------------------------------------

    def _run(self, hook, session=None):
        r = subprocess.run(
            [sys.executable, str(hook)],
            input=json.dumps({"session_id": session or self.SESSION}),
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

    def stop_decision(self, session=None):
        return self._run(self.hook_copy, session)

    def closing_decision(self, session=None):
        return self._run(self.closing_hook_copy, session)

    def assert_blocked(self, reason_contains=None, session=None):
        verdict, reason = self.stop_decision(session)
        self.assertEqual("block", verdict, "expected BLOCK; got allow")
        if reason_contains is not None:
            self.assertIn(
                reason_contains, reason,
                "block reason must name {0!r}; got {1!r}".format(
                    reason_contains, reason
                ),
            )
        return reason

    def assert_allowed_stop(self, session=None):
        verdict, reason = self.stop_decision(session)
        self.assertEqual(
            "allow", verdict, "expected ALLOW; blocked with: {0}".format(reason)
        )


class TestNoMarkerAllows(HandbackHookEnv):
    def test_no_marker_allows(self):
        # Case 1: no handback marker at all -> structural no-op, allow.
        self.assert_allowed_stop()
        # Still allows with no handback file anywhere on disk.
        self.assertFalse(self.handback_path.exists())
        self.assert_allowed_stop()


class TestForeignSessionAllows(HandbackHookEnv):
    def test_foreign_session_allows(self):
        # Case 2: an abandoned session's marker never blocks another session,
        # and is never consumed.
        self.write_marker(session="some-other-session")
        self.assert_allowed_stop()
        self.assertTrue(self.marker_path.exists())


class TestMissingHandbackBlocks(HandbackHookEnv):
    def test_missing_handback_blocks(self):
        # Case 3: marker matches, no file at handback_path -> block naming
        # that exact path.
        self.write_marker()
        reason = self.assert_blocked(reason_contains=self.handback_rel)
        self.assertIn(ABANDON_MINIMUM, reason)
        self.assertTrue(self.marker_path.exists())


class TestBadStatusBlocks(HandbackHookEnv):
    def test_bad_status_blocks(self):
        # Case 4: Status absent, or outside the closed vocabulary.
        self.write_marker()
        for label, text in [
            ("absent", "**Handed to this session:**\n- row\n"),
            ("outside-vocabulary", "Status: DONE\n\nSomething happened.\n"),
            ("lowercase", "Status: complete\n\nSomething happened.\n"),
        ]:
            with self.subTest(case=label):
                self.write_handback(text)
                reason = self.assert_blocked(reason_contains="Status")
                self.assertIn(ABANDON_MINIMUM, reason)
                self.assertTrue(self.marker_path.exists())



class TestOpenStubAllows(HandbackHookEnv):
    def test_open_stub_allows_and_keeps_marker(self):
        # Prevents: a session waiting on a background job, or pausing to ask
        # a question, being blocked on every stop (the stuck loops of E007).
        # Every stop while OPEN is allowed; the marker stays so the checks
        # still run once the status turns terminal.
        self.write_marker()
        self.write_handback(STUB_HANDBACK)
        for _ in range(3):
            self.assert_allowed_stop()
            self.assertTrue(self.marker_path.exists())

    def test_open_with_bad_receipt_allows(self):
        # Prevents: a receipt mismatch at OPEN turning every wait into a
        # block loop the session can only leave by abandoning. The receipt
        # is checked at the terminal close instead.
        self.write_marker()
        self.write_manifest(sha=OTHER_SHA)
        self.write_handback(ID_RECEIPT_STUB)
        self.assert_allowed_stop()
        self.assertTrue(self.marker_path.exists())


class TestAbandonedThreeLinerAllows(HandbackHookEnv):
    def test_abandoned_three_liner_allows(self):
        # Case 5: the binding constraint. Status plus one sentence, nothing
        # else -- no ## Delta, no advisory section, no observation.
        self.write_marker()
        self.write_handback(ABANDON_MINIMUM)
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())

    def test_abandon_path_costs_about_three_lines(self):
        # The escape hatch must stay cheap: the passing content is a status
        # field and one sentence, and nothing more.
        body = [ln for ln in ABANDON_MINIMUM.splitlines() if ln.strip()]
        self.assertLessEqual(
            len(body), 3,
            "abandon path must cost about three lines; got {0}".format(body),
        )


class TestCompleteAllowsAndSelfDeletes(HandbackHookEnv):
    def test_complete_allows_and_self_deletes(self):
        # Case 6: COMPLETE with all four blocks -> allow, marker removed.
        self.write_marker()
        self.write_handback(COMPLETE_HANDBACK)
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())

    def test_complete_missing_a_section_blocks(self):
        # The four-part structure is only enforced for the statuses that
        # claim real work landed.
        self.write_marker()
        for missing in [
            "## Scope changes",
            "## Delta",
            "## For the next session",
            "## Structural observations",
        ]:
            with self.subTest(missing=missing):
                stripped = COMPLETE_HANDBACK.replace(missing + "\n", "")
                self.write_handback(stripped)
                reason = self.assert_blocked(reason_contains=missing)
                self.assertIn(ABANDON_MINIMUM, reason)
        self.write_handback(COMPLETE_HANDBACK)
        self.assert_allowed_stop()


SCOPE_LINE = (
    '- "drop item 3, it moves to the next session" | overrides: E017 '
    "| item 3 (split close) is out of this session\n"
)


class TestScopeChangesSection(HandbackHookEnv):
    def test_well_formed_scope_lines_allow(self):
        # Prevents: a shape check that over-blocks a correctly recorded
        # re-scope, pushing the session toward writing 'none' instead.
        self.write_marker()
        text = COMPLETE_HANDBACK.replace(
            "## Scope changes\n\nnone\n", "## Scope changes\n\n" + SCOPE_LINE
        )
        self.assertIn(SCOPE_LINE, text)
        self.write_handback(text)
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())

    def test_malformed_scope_line_blocks(self):
        # Prevents: a free-prose note the orchestrator's ingest cannot surface
        # -- the user's words unquoted, or no named override target.
        self.write_marker()
        for bad in [
            "- the user dropped item 3 | overrides: E017 | item 3 out\n",
            '- "drop item 3" | item 3 is out\n',
            "The user dropped item 3.\n",
        ]:
            with self.subTest(bad=bad):
                text = COMPLETE_HANDBACK.replace(
                    "## Scope changes\n\nnone\n", "## Scope changes\n\n" + bad
                )
                self.write_handback(text)
                reason = self.assert_blocked(reason_contains="FAIL scope:")
                self.assertIn(ABANDON_MINIMUM, reason)
        self.assertTrue(self.marker_path.exists())

    def test_abandoned_needs_no_scope_section(self):
        # Prevents: the new section raising the price of the abandon path.
        self.write_marker()
        self.assertNotIn("Scope", ABANDON_MINIMUM)
        self.write_handback(ABANDON_MINIMUM)
        self.assert_allowed_stop()


class TestDeltaGrammarBlocks(HandbackHookEnv):
    def test_malformed_delta_marker_block_blocks(self):
        # A COMPLETE handback whose ## Delta carries a table row with no
        # ADD/CHANGE/RETIRE marker line above it must BLOCK the close. The hook
        # now runs the SAME shared grammar the orchestrator ingests, so the
        # malformed marker block is caught at the session's own close (the
        # verbatim "FAIL delta:" line) rather than hand-repaired at ingest.
        self.write_marker()
        self.write_handback(MALFORMED_DELTA_HANDBACK)
        reason = self.assert_blocked(reason_contains="FAIL delta:")
        self.assertIn(ABANDON_MINIMUM, reason)
        self.assertTrue(self.marker_path.exists())

    def test_well_formed_complete_still_allows(self):
        # The control that proves the grammar check does not over-block: a
        # well-formed COMPLETE (Delta 'none', observations 'none') still closes
        # and self-deletes its marker, exactly as before the grammar check.
        self.write_marker()
        self.write_handback(COMPLETE_HANDBACK)
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())


class TestMarkersMutuallyExclusive(HandbackHookEnv):
    def test_markers_mutually_exclusive(self):
        # Case 7: neither hook honors the other's marker, for the same
        # session id and with nothing else on disk.

        # A phase-closing marker alone: the handback hook is a no-op, and the
        # closing marker survives untouched.
        self.write_closing_marker()
        self.assert_allowed_stop()
        self.assertTrue(self.closing_marker_path.exists())

        # A handback marker alone: the closing hook is a no-op, and the
        # handback marker survives untouched.
        self.closing_marker_path.unlink()
        self.write_marker()
        verdict, reason = self.closing_decision()
        self.assertEqual(
            "allow", verdict,
            "closing hook must ignore a handback marker; blocked: {0}".format(
                reason
            ),
        )
        self.assertTrue(self.marker_path.exists())


class TestBlockMessageStatesUnblockingContent(HandbackHookEnv):
    def test_block_message_states_unblocking_content(self):
        # Case 8: EVERY block reason carries the minimal unblocking content
        # verbatim -- not a description of it, and not a pointer to a schema.
        self.write_marker()
        reasons = []

        # Missing file.
        reasons.append(self.assert_blocked())

        # Status absent.
        self.write_handback("no status line here\n")
        reasons.append(self.assert_blocked())

        # Status outside the vocabulary.
        self.write_handback("Status: FINISHED\n\nA sentence.\n")
        reasons.append(self.assert_blocked())

        # Status OPEN is no longer a block at all.
        self.write_handback(STUB_HANDBACK)
        self.assert_allowed_stop()

        # PARTIAL missing a required section.
        self.write_handback(
            COMPLETE_HANDBACK.replace("Status: COMPLETE", "Status: PARTIAL")
            .replace("## Delta\n", "")
        )
        reasons.append(self.assert_blocked())

        # COMPLETE with a malformed Delta.
        self.write_handback(MALFORMED_DELTA_HANDBACK)
        reasons.append(self.assert_blocked())

        for i, reason in enumerate(reasons):
            with self.subTest(block=i):
                self.assertIn(
                    ABANDON_MINIMUM, reason,
                    "block reason {0} omits the verbatim unblocking "
                    "content: {1!r}".format(i, reason),
                )
                # Prevents: block messages still telling a session to write
                # the retired pause file that nothing reads any more.
                self.assertNotIn("handback_pause", reason)
                self.assertNotIn("pause", reason.lower())


class TestReceiptVerification(HandbackHookEnv):
    def test_matching_receipt_completes(self):
        # Prevents: the new verification breaking the healthy close -- a
        # session whose receipt matches its manifest must close exactly as
        # before, marker removed.
        self.write_marker()
        self.write_manifest()
        self.write_handback(ID_RECEIPT_COMPLETE)
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())

    def test_tampered_rows_block(self):
        # Prevents: a session acknowledging rows it was not handed, or
        # silently dropping one it was -- the exact drift the manifest
        # exists to catch.
        self.write_marker()
        self.write_manifest(row_ids=("E001", "E002", "E003"))
        self.write_handback(ID_RECEIPT_COMPLETE)
        reason = self.assert_blocked(reason_contains="E003")
        self.assertIn(ABANDON_MINIMUM, reason)
        self.assertTrue(self.marker_path.exists())

    def test_hash_mismatch_blocks(self):
        # Prevents: a receipt written against an edited or wrong prompt file
        # passing as verified.
        self.write_marker()
        self.write_manifest(sha=OTHER_SHA)
        self.write_handback(ID_RECEIPT_COMPLETE)
        reason = self.assert_blocked(reason_contains="SHA256")
        self.assertIn(ABANDON_MINIMUM, reason)
        self.assertTrue(self.marker_path.exists())

    def test_missing_manifest_skips_verification(self):
        # Prevents: an unresolvable block on a hand-written dispatch -- the
        # manifest is the ORCHESTRATOR's artifact, and a session cannot
        # legitimately create it, so its absence is a structural no-op and
        # the v5 checks run unchanged.
        self.write_marker()
        self.write_handback(COMPLETE_HANDBACK)
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())

    def test_abandoned_exempt_from_receipt_check(self):
        # Prevents: the abandon path's cost creeping past the binding
        # constraint -- a status field and one sentence must still close,
        # manifest or no manifest.
        self.write_marker()
        self.write_manifest()
        self.write_handback(ABANDON_MINIMUM)
        self.assert_allowed_stop()
        self.assertFalse(self.marker_path.exists())

    def test_terminal_partial_bad_receipt_blocks(self):
        # Prevents: moving the receipt check to terminal-only silently
        # dropping it for PARTIAL, the other status that claims work landed.
        self.write_marker()
        self.write_manifest(sha=OTHER_SHA)
        self.write_handback(
            ID_RECEIPT_COMPLETE.replace("Status: COMPLETE", "Status: PARTIAL")
        )
        reason = self.assert_blocked(reason_contains="SHA256")
        self.assertIn(ABANDON_MINIMUM, reason)
        self.assertTrue(self.marker_path.exists())

    def test_v5_receipt_with_manifest_blocks(self):
        # Prevents: a script-dispatched session writing the retired verbatim
        # echo instead of the verifiable ID receipt and passing anyway.
        self.write_marker()
        self.write_manifest()
        self.write_handback(COMPLETE_HANDBACK)
        reason = self.assert_blocked(reason_contains="- Rows:")
        self.assertIn(ABANDON_MINIMUM, reason)
        self.assertTrue(self.marker_path.exists())


class TestAllTerminalFailuresTogether(HandbackHookEnv):
    def test_all_terminal_failures_reported_together(self):
        # Prevents: one round-trip per failure -- fix the receipt, stop, learn
        # about the missing section, stop, learn about the Delta grammar. A
        # terminal handback with three independent defects gets ONE block
        # naming all three.
        self.write_marker()
        self.write_manifest(sha=OTHER_SHA)
        text = (
            ID_RECEIPT_COMPLETE
            .replace("## For the next session\n", "")
            .replace(
                "## Delta\n\nnone\n",
                "## Delta\n\n| E001 | no marker above this row | a | b | c |\n",
            )
        )
        self.write_handback(text)
        reason = self.assert_blocked()
        self.assertIn("SHA256", reason)
        self.assertIn("## For the next session", reason)
        self.assertIn("FAIL delta:", reason)
        self.assertEqual(1, reason.count(ABANDON_MINIMUM))
        self.assertTrue(self.marker_path.exists())


class TestPauseFileIsInert(HandbackHookEnv):
    def test_pause_file_is_inert(self):
        # Prevents: the retired pause mechanism lingering as a way to waive
        # the terminal checks. A pause file -- plain or a standing "until" --
        # no longer changes any decision, and the hook leaves it untouched.
        self.write_marker()
        self.write_handback(MALFORMED_DELTA_HANDBACK)
        for declaration in [
            {"session_id": self.SESSION},
            {"session_id": self.SESSION, "until": 9999999999},
        ]:
            with self.subTest(declaration=declaration):
                path = self.write_stale_pause_file(declaration)
                self.assert_blocked(reason_contains="FAIL delta:")
                self.assertTrue(path.exists())
                self.assertEqual(
                    declaration, json.loads(path.read_text(encoding="utf-8"))
                )

    def test_hook_source_has_no_pause_mechanism(self):
        # Prevents: dead pause code surviving in the hook after retirement.
        source = HANDBACK_HOOK.read_text(encoding="utf-8")
        self.assertNotIn("handback_pause", source)
        self.assertNotIn("PAUSE_INSTRUCTION", source)


class TestManualCheckMode(HandbackHookEnv):
    """The --check-receipt argv mode: the dogfooding-interim entry point."""

    def run_check(self, *args):
        return subprocess.run(
            [sys.executable, str(self.hook_copy), "--check-receipt"]
            + list(args),
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_check_receipt_ok(self):
        # Prevents: the manual checker disagreeing with the hook on a
        # receipt the hook would pass.
        manifest_path = self.write_manifest()
        self.write_handback(ID_RECEIPT_STUB)
        r = self.run_check(
            str(self.handback_path), "--manifest", str(manifest_path)
        )
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)

    def test_check_receipt_mismatch_fails(self):
        # Prevents: the dogfooding interim running blind -- a tampered or
        # stale receipt must fail loudly when checked by hand.
        manifest_path = self.write_manifest(sha=OTHER_SHA)
        self.write_handback(ID_RECEIPT_STUB)
        r = self.run_check(
            str(self.handback_path), "--manifest", str(manifest_path)
        )
        self.assertEqual(1, r.returncode)
        self.assertIn("FAIL", r.stdout)

    def test_check_receipt_missing_manifest_fails(self):
        # Prevents: a silent pass when the orchestrator -- the manifest's
        # owner -- checks a dispatch that never got one. Unlike the hook
        # path, the manual path fails loudly here.
        self.write_handback(ID_RECEIPT_STUB)
        r = self.run_check(str(self.handback_path))
        self.assertEqual(1, r.returncode)
        self.assertIn("FAIL", r.stdout)
        self.assertIn("manifest", r.stdout.lower())

    def test_check_receipt_derives_manifest_path(self):
        # Prevents: the checker needing hand-fed paths for the standard
        # layout -- .../<plan>/handbacks/<NN>.md implies
        # .../<plan>/dispatches/<NN>.json.
        self.write_manifest()
        self.write_handback(ID_RECEIPT_STUB)
        r = self.run_check(str(self.handback_path))
        self.assertEqual(0, r.returncode, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)
