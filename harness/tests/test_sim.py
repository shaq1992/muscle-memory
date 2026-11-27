"""Behavioral tests for harness/scripts/sim.py, the SIM notebook tool.

The notebook is a directory (normally a git clone) holding append-only JSONL
records and a rendered NOTEBOOK.md; the record shapes and the verdict rule are
defined in harness/templates/sim_record_schema.md. Each case states the
failure it prevents.

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import HARNESS_ROOT, BASE_PARAMS, GuardrailEnv

SCRIPT = HARNESS_ROOT / "harness" / "scripts" / "sim.py"
DOMAIN = "harness"
JSONL = ("problems.jsonl", "attempts.jsonl", "links.jsonl",
         "aliases.jsonl", "sessions.jsonl")


def _git(cwd, *args, check=True):
    return subprocess.run(["git"] + list(args), cwd=str(cwd), check=check,
                          capture_output=True, text=True, timeout=30)


def _git_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.com")
    return path


def problem(**kw):
    rec = {"hypothesis": "reminder conflicts with the attribution law",
           "opened": "2026-11-01", "opened_by": "user", "project": "proj-a",
           "tags": ["sources-conflict"]}
    rec.update(kw)
    return rec


def attempt(pid, **kw):
    rec = {"problem": pid, "date": "2026-11-02", "model": "model-x",
           "harness_version": "6.0", "project": "proj-a",
           "change": "state the precedence rule", "why": "two sources disagree",
           "files": ["harness/procedures/git_strategy.md"],
           "commits": ["abc1234"], "accepted": True, "landed": "2026-11-02",
           "prediction": {"problem": pid,
                          "signature": "no attribution-conflict observation",
                          "expect_absent_tags": ["sources-conflict"],
                          "prevents": ["L78"], "at_risk": ["commit hook"]},
           "review": {"verdict": "accept", "reasons": "small and targeted"}}
    rec.update(kw)
    return rec


def link(pid, obs_date="2026-11-10", proposed=None, verdict="accepted", **kw):
    rec = {"observation": {"project": "proj-a", "ref": "docs/observations.md:L90",
                           "date": obs_date},
           "problem": pid, "proposed": proposed or pid, "proposed_by": "orchestrator",
           "verdict": verdict, "date": obs_date}
    rec.update(kw)
    return rec


class SimEnv(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.nb = _git_repo(self.tmp / "notebook")

    def sim(self, *args, nb=None, domain=DOMAIN, record=None, ok=True):
        cmd = [sys.executable, str(SCRIPT), args[0],
               "--notebook", str(nb or self.nb), "--domain", domain] + list(args[1:])
        if record is not None:
            cmd += ["--record", json.dumps(record)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if ok is True:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        elif ok is False:
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def init(self, *extra, nb=None):
        return self.sim("init", *extra, nb=nb)

    def session(self, n, started="2026-11-05", kind="implement", project="proj-a"):
        return self.sim("verdict", "--project", project, "--plan", "plan-x",
                        "--session", "%02d" % n, "--kind", kind,
                        "--started", started)

    def lines(self, name, nb=None):
        p = (nb or self.nb) / name
        if not p.exists():
            return []
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]

    def snapshot(self):
        return {n: (self.nb / n).read_bytes() if (self.nb / n).exists() else None
                for n in JSONL + ("NOTEBOOK.md", "notebook.json")}

    def commits(self, nb=None):
        return int(_git(nb or self.nb, "rev-list", "--count", "HEAD").stdout)

    def notebook_md(self):
        return (self.nb / "NOTEBOOK.md").read_text(encoding="utf-8")

    def landed_problem(self, **kw):
        self.init(*kw.pop("init_args", ()))
        self.sim("append", "problem", record=problem())
        self.sim("append", "attempt", record=attempt("P-0001", **kw))


class TestInitAndAppend(SimEnv):
    def test_init_declares_domain_and_thresholds(self):
        # Prevents: a notebook with no declared domain, where two domains'
        # records could mix unnoticed.
        self.init()
        meta = json.loads((self.nb / "notebook.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["domain"], DOMAIN)
        self.assertEqual(meta["thresholds"], {"hold_after": 10, "fold_after": 30,
                                              "agreement_last": 30,
                                              "agreement_threshold": 0.9})
        probs = self.lines("problems.jsonl")
        self.assertEqual(probs[0]["id"], "P-0000")
        self.assertIn("unattributed", probs[0]["hypothesis"])
        self.assertEqual(self.commits(), 1)
        self.assertEqual(_git(self.nb, "status", "--porcelain").stdout, "")

    def test_init_twice_refused(self):
        self.init()
        self.sim("init", ok=False)

    def test_domain_mismatch_refused(self):
        # Prevents: a record from another domain landing in this notebook.
        self.init()
        before = self.snapshot()
        self.sim("append", "problem", domain="other-domain", record=problem(), ok=False)
        self.assertEqual(self.snapshot(), before)

    def test_append_only_and_ids_in_order(self):
        # Prevents: a write that rewrites history instead of appending to it.
        self.init()
        r = self.sim("append", "problem", record=problem())
        self.assertIn("P-0001", r.stdout)
        before = (self.nb / "problems.jsonl").read_bytes()
        self.sim("append", "problem", record=problem(hypothesis="second cause"))
        after = (self.nb / "problems.jsonl").read_bytes()
        self.assertTrue(after.startswith(before))
        probs = self.lines("problems.jsonl")
        self.assertEqual([p["id"] for p in probs], ["P-0000", "P-0001", "P-0002"])
        seqs = [p["seq"] for p in probs]
        self.assertEqual(seqs, sorted(seqs))
        self.assertTrue(all(p["domain"] == DOMAIN for p in probs))
        self.sim("append", "attempt", record=attempt("P-0001"))
        self.sim("append", "attempt", record=attempt("P-0001"))
        self.assertEqual([a["id"] for a in self.lines("attempts.jsonl")],
                         ["P-0001/A1", "P-0001/A2"])

    def test_bad_shapes_refused_and_files_untouched(self):
        # Prevents: malformed records entering the truth files.
        self.init()
        self.sim("append", "problem", record=problem())
        self.sim("append", "problem", record=problem(hypothesis="other"))
        before = self.snapshot()
        bad = [
            ("problem", problem(hypothesis="")),
            ("attempt", attempt("P-0099")),
            ("attempt", attempt("P-0001", prediction={
                "problem": "P-0002", "signature": "x", "expect_absent_tags": [],
                "prevents": [], "at_risk": []})),
            ("attempt", attempt("P-0001", review={"verdict": "maybe",
                                                  "reasons": "x"})),
            ("attempt", attempt("P-0001", accepted=False)),  # rejected but landed
            ("attempt", attempt("P-0001", landed="last tuesday")),
            ("link", link("P-0001", verdict="changed")),  # changed but same id
            ("alias", {"alias": "P-0001", "of": "P-0001", "reason": "x",
                       "date": "2026-11-03", "approved_by": "user"}),
        ]
        for rtype, rec in bad:
            with self.subTest(rtype=rtype, rec=rec):
                self.sim("append", rtype, record=rec, ok=False)
                self.assertEqual(self.snapshot(), before)

    def test_alias_cycle_refused(self):
        self.init()
        self.sim("append", "problem", record=problem())
        self.sim("append", "problem", record=problem(hypothesis="dup"))
        self.sim("append", "alias", record={"alias": "P-0002", "of": "P-0001",
                                            "reason": "same root cause",
                                            "date": "2026-11-03",
                                            "approved_by": "user"})
        self.sim("append", "alias", record={"alias": "P-0001", "of": "P-0002",
                                            "reason": "loop", "date": "2026-11-03",
                                            "approved_by": "user"}, ok=False)

    def test_write_commits_and_never_pushes(self):
        # Prevents: sim.py pushing (the caller owns the push and its gh
        # account switch) or leaving uncommitted changes behind.
        remote = self.tmp / "remote.git"
        _git(self.tmp, "init", "-q", "--bare", str(remote))
        _git(self.nb, "remote", "add", "origin", str(remote))
        self.init()
        _git(self.nb, "push", "-q", "-u", "origin", "main")
        remote_head = _git(remote, "rev-parse", "main").stdout
        n = self.commits()
        self.sim("append", "problem", record=problem())
        self.assertEqual(self.commits(), n + 1)
        self.assertEqual(_git(self.nb, "status", "--porcelain").stdout, "")
        self.assertEqual(_git(remote, "rev-parse", "main").stdout, remote_head)


class TestVerdicts(SimEnv):
    def test_held_after_ten_counted_sessions(self):
        # Prevents: "fixed at commit" -- an attempt must survive 10 counted
        # sessions before it is called held.
        self.landed_problem()
        for n in range(1, 10):
            r = self.session(n)
            self.assertNotIn("held", r.stdout)
        self.assertIn("under observation", self.notebook_md())
        r = self.session(10)
        self.assertIn("P-0001 attempt 1: held", r.stdout)
        verdicts = [a for a in self.lines("attempts.jsonl") if a["type"] == "verdict"]
        self.assertEqual([(v["attempt"], v["state"]) for v in verdicts],
                         [("P-0001/A1", "held")])

    def test_repeat_session_counted_once(self):
        # Prevents: a double ingest of one handback speeding up "held".
        self.landed_problem(init_args=("--hold-after", "2"))
        self.session(1)
        r = self.session(1)
        self.assertNotIn("held", r.stdout)
        self.assertEqual(len(self.lines("sessions.jsonl")), 1)
        r = self.session(2)
        self.assertIn("held", r.stdout)

    def test_sessions_before_landing_do_not_count(self):
        self.landed_problem(init_args=("--hold-after", "1"))
        r = self.session(1, started="2026-11-01")
        self.assertNotIn("held", r.stdout)
        r = self.session(2, started="2026-11-03")
        self.assertIn("held", r.stdout)

    def test_thresholds_are_parameters(self):
        self.landed_problem(init_args=("--hold-after", "3"))
        self.session(1)
        self.session(2)
        self.assertIn("held", self.session(3).stdout)

    def test_recurred_at_once_on_confirmed_link(self):
        # Prevents: a recurrence inside the window being missed.
        self.landed_problem()
        self.session(1)
        r = self.sim("append", "link", record=link("P-0001"))
        self.assertIn("P-0001 attempt 1: recurred", r.stdout)
        self.assertIn("recurred", self.notebook_md())
        for n in range(2, 12):
            self.assertNotIn("held", self.session(n).stdout)

    def test_link_dated_before_landing_is_not_a_recurrence(self):
        self.landed_problem()
        r = self.sim("append", "link", record=link("P-0001", obs_date="2026-11-01"))
        self.assertNotIn("recurred", r.stdout)

    def test_recurred_through_alias(self):
        self.landed_problem()
        self.sim("append", "problem", record=problem(hypothesis="dup"))
        self.sim("append", "alias", record={"alias": "P-0002", "of": "P-0001",
                                            "reason": "same root cause",
                                            "date": "2026-11-03",
                                            "approved_by": "user"})
        r = self.sim("append", "link", record=link("P-0002"))
        self.assertIn("P-0001 attempt 1: recurred", r.stdout)

    def test_link_after_held_reopens_and_keeps_verdict(self):
        # Prevents: a held verdict being silently flipped, or a recurrence
        # after the window going unseen.
        self.landed_problem(init_args=("--hold-after", "1"))
        self.session(1)
        r = self.sim("append", "link", record=link("P-0001", obs_date="2026-11-20"))
        self.assertNotIn("recurred", r.stdout)
        self.assertIn("P-0001 reopened", r.stdout)
        md = self.notebook_md()
        self.assertIn("reopened", md)
        states = [a["state"] for a in self.lines("attempts.jsonl")
                  if a["type"] == "verdict"]
        self.assertEqual(states, ["held"])

    def test_rejected_and_unattributed_get_no_verdict(self):
        self.init("--hold-after", "1")
        self.sim("append", "problem", record=problem())
        rej = attempt("P-0001", accepted=False, landed=None,
                      review={"verdict": "reject", "reasons": "too broad"})
        self.sim("append", "attempt", record=rej)
        una = attempt("P-0000", prediction=None, review=None,
                      change="old improve commit")
        self.sim("append", "attempt", record=una)
        r = self.session(1)
        self.assertNotIn("held", r.stdout)
        md = self.notebook_md()
        self.assertIn("## Unattributed", md)
        self.assertIn("old improve commit", md)
        self.assertIn("rejected", md)


class TestRenderValidate(SimEnv):
    def test_fold_after_threshold(self):
        # Prevents: an unreadable view -- long-held problems fold to one line.
        self.landed_problem(init_args=("--hold-after", "1", "--fold-after", "2"))
        self.session(1)
        self.session(2)
        md = self.notebook_md()
        self.assertNotIn("## Folded", md)
        self.assertIn("small and targeted", md)
        self.session(3)
        md = self.notebook_md()
        self.assertIn("## Folded", md)
        self.assertNotIn("small and targeted", md)

    def test_validate_passes_on_fresh_notebook(self):
        self.landed_problem()
        self.session(1)
        self.sim("validate")

    def test_validate_fails_on_stale_view(self):
        # Prevents: a reader trusting an out-of-date NOTEBOOK.md.
        self.landed_problem()
        md = self.nb / "NOTEBOOK.md"
        md.write_text(md.read_text(encoding="utf-8") + "hand edit\n", encoding="utf-8")
        r = self.sim("validate", ok=False)
        self.assertIn("stale", r.stdout + r.stderr)
        self.sim("render")
        self.sim("validate")

    def test_validate_fails_on_hand_appended_record(self):
        self.landed_problem()
        with open(self.nb / "problems.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"seq": 99, "type": "problem", "domain": DOMAIN,
                                "id": "P-0002", "hypothesis": "x",
                                "opened": "2026-11-03", "opened_by": "user",
                                "project": "proj-a", "tags": []}) + "\n")
        self.sim("validate", ok=False)

    def test_validate_fails_on_bad_line_and_duplicate_seq(self):
        self.landed_problem()
        probs = self.lines("problems.jsonl")
        dup = dict(probs[-1], id="P-0002")
        with open(self.nb / "problems.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(dup) + "\n")
        self.sim("validate", ok=False)
        _git(self.nb, "checkout", "--", "problems.jsonl")
        with open(self.nb / "links.jsonl", "a", encoding="utf-8") as f:
            f.write("{not json\n")
        self.sim("validate", ok=False)


class TestReports(SimEnv):
    def test_agreement_over_last_window(self):
        self.init("--agreement-last", "30")
        self.sim("append", "problem", record=problem())
        self.sim("append", "problem", record=problem(hypothesis="other"))
        # 5 old "changed" links fall outside the window of the last 30.
        recs = [link("P-0001", proposed="P-0002", verdict="changed")] * 5
        recs += [link("P-0001", proposed="P-0002", verdict="changed")] * 3
        recs += [link("P-0001")] * 27
        for rec in recs:
            self.sim("append", "link", record=rec)
        r = self.sim("agreement")
        self.assertIn("27/30", r.stdout)
        self.assertIn("threshold 0.9: met", r.stdout)
        # Four more "changed" links push the 8 old ones and one accepted out.
        for _ in range(4):
            self.sim("append", "link",
                     record=link("P-0001", proposed="P-0002", verdict="changed"))
        r = self.sim("agreement")
        self.assertIn("26/30", r.stdout)
        self.assertIn("threshold 0.9: not met", r.stdout)

    def test_count(self):
        self.landed_problem()
        self.sim("append", "problem", record=problem(hypothesis="other"))
        self.session(1)
        r = self.sim("count")
        self.assertIn("problems: 2", r.stdout)
        self.assertIn("under observation 1", r.stdout)
        self.assertIn("open 1", r.stdout)
        self.assertIn("attempts: 1", r.stdout)
        self.assertIn("sessions: 1", r.stdout)


class TestPull(SimEnv):
    def setUp(self):
        super().setUp()
        self.remote = self.tmp / "remote.git"
        _git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.remote))
        _git(self.nb, "remote", "add", "origin", str(self.remote))
        self.init()
        _git(self.nb, "push", "-q", "-u", "origin", "main")
        _git(self.tmp, "clone", "-q", str(self.remote), "other")
        self.other = self.tmp / "other"
        _git(self.other, "config", "user.name", "Other")
        _git(self.other, "config", "user.email", "other@example.com")

    def test_write_pulls_first(self):
        # Prevents: two machines forking the append-only files.
        self.sim("append", "problem", nb=self.other, record=problem())
        _git(self.other, "push", "-q", "origin", "main")
        r = self.sim("append", "problem", record=problem(hypothesis="mine"))
        self.assertIn("P-0002", r.stdout)
        self.assertEqual([p["id"] for p in self.lines("problems.jsonl")],
                         ["P-0000", "P-0001", "P-0002"])

    def test_diverged_write_refuses_read_warns(self):
        self.sim("append", "problem", nb=self.other, record=problem())
        _git(self.other, "push", "-q", "origin", "main")
        # Local commit not on the remote -> fast-forward pull is impossible.
        (self.nb / "README.md").write_text("local\n", encoding="utf-8")
        _git(self.nb, "add", "README.md")
        _git(self.nb, "commit", "-q", "-m", "local")
        before = self.snapshot()
        r = self.sim("append", "problem", record=problem(), ok=False)
        self.assertIn("pull", (r.stdout + r.stderr).lower())
        self.assertEqual(self.snapshot(), before)
        r = self.sim("count")
        self.assertIn("warning", r.stderr.lower())
        self.assertIn("problems: 0", r.stdout)


class TestLocate(SimEnv):
    """`sim.py locate --preferences FILE`: the fallback detection (E025) the
    self-improver runs first. It prints exactly one line and its exit code
    picks the flow: 0 on, 3 off, 4 configured but missing."""

    def locate(self, prefs_text, home=None):
        prefs = self.tmp / "preferences.md"
        prefs.write_text(BASE_PARAMS + prefs_text, encoding="utf-8")
        env = dict(os.environ)
        if home is not None:
            env["HOME"] = str(home)
        return subprocess.run([sys.executable, str(SCRIPT), "locate",
                               "--preferences", str(prefs)],
                              capture_output=True, text=True, timeout=60, env=env)

    def test_no_key_is_off(self):
        # Prevents: an improver on a project that never set the key crashing,
        # or silently running a SIM-less flow without saying so.
        r = self.locate("")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip().splitlines(),
                         ["SIM notebook: off (no sim_notebook key) -- running "
                          "without memory, prediction or recurrence tracking."])

    def test_no_preferences_file_is_off(self):
        # Prevents: a project with no preferences file crashing the improver.
        r = subprocess.run([sys.executable, str(SCRIPT), "locate",
                            "--preferences", str(self.tmp / "absent.md")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("off (no sim_notebook key)", r.stdout)

    def test_key_set_path_absent_is_missing(self):
        # Prevents: a missing clone being treated as plain "off" with no warning.
        gone = self.tmp / "no-such-clone"
        r = self.locate("sim_notebook: {0}\n".format(gone))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("SIM notebook: configured at {0} but missing".format(gone),
                      r.stdout)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1)

    def test_not_a_repo_or_not_initialised_is_missing(self):
        # Prevents: the flow starting on a path where every sim.py write fails.
        plain = self.tmp / "plain-dir"
        plain.mkdir()
        r = self.locate("sim_notebook: {0}\n".format(plain))
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("but missing", r.stdout)
        r = self.locate("sim_notebook: {0}\n".format(self.nb))  # repo, no init
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("but missing", r.stdout)

    def test_valid_notebook_is_on_with_domain(self):
        # Prevents: the improver guessing the notebook's domain.
        self.init()
        r = self.locate("sim_notebook: {0}\n".format(self.nb))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(),
                         "SIM notebook: on at {0} (domain harness)".format(self.nb))

    def test_tilde_is_expanded(self):
        # Prevents: a valid home-relative key reported as missing.
        self.init()
        r = self.locate("sim_notebook: ~/notebook\n", home=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("on at", r.stdout)


class TestHistory(SimEnv):
    def test_history_shows_the_whole_problem(self):
        # Prevents: the reviewer judging a draft without the cited problem's
        # past attempts, predictions, reviews and links.
        self.landed_problem()
        self.sim("append", "link", record=link("P-0001"))
        r = self.sim("history", "--problem", "P-0001")
        out = r.stdout
        self.assertIn("P-0001: reminder conflicts with the attribution law", out)
        self.assertIn("Status: recurred", out)
        self.assertIn("state the precedence rule", out)
        self.assertIn("Prediction: no attribution-conflict observation", out)
        self.assertIn("review: accept (small and targeted)", out)
        self.assertIn("Link: docs/observations.md:L90", out)
        # Same block as the rendered view, so the two never disagree.
        block = out.strip().splitlines()
        md = self.notebook_md().splitlines()
        start = md.index(block[0])
        self.assertEqual(md[start:start + len(block)], block)

    def test_history_of_alias_shows_merged_problem(self):
        # Prevents: history split across a merge being missed.
        self.landed_problem()
        self.sim("append", "problem", record=problem(hypothesis="same cause, reworded"))
        self.sim("append", "alias", record={"alias": "P-0002", "of": "P-0001",
                                            "reason": "same", "date": "2026-11-03",
                                            "approved_by": "user"})
        r = self.sim("history", "--problem", "P-0002")
        self.assertIn("P-0001: reminder conflicts", r.stdout)
        self.assertIn("aliases: P-0002", r.stdout)

    def test_unknown_problem_is_an_error(self):
        # Prevents: an empty history read as "this problem has no past".
        self.init()
        r = self.sim("history", "--problem", "P-0042", ok=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("P-0042", r.stderr)


class TestReviewOverride(SimEnv):
    def setUp(self):
        super().setUp()
        self.init()
        self.sim("append", "problem", record=problem())

    def test_accepted_reject_without_override_refused(self):
        # Prevents: a reviewer reject silently landing as a normal accept.
        before = self.snapshot()
        self.sim("append", "attempt", ok=False, record=attempt(
            "P-0001", review={"verdict": "reject", "reasons": "too broad"}))
        self.sim("append", "attempt", ok=False, record=attempt(
            "P-0001", review={"verdict": "revise", "reasons": "second revise"}))
        self.assertEqual(self.snapshot(), before)

    def test_override_on_accepted_reject_or_revise_recorded(self):
        # Prevents: a legitimate user override being unrecordable.
        self.sim("append", "attempt", record=attempt(
            "P-0001", review={"verdict": "reject", "reasons": "too broad",
                              "override": "user: yes"}))
        self.sim("append", "attempt", record=attempt(
            "P-0001", review={"verdict": "revise", "reasons": "second revise",
                              "override": "user: go"}))
        self.assertEqual(self.lines("attempts.jsonl")[0]["review"]["override"],
                         "user: yes")
        self.assertIn("overridden by user: yes", self.notebook_md())

    def test_contradictory_override_refused(self):
        # Prevents: records claiming an override that cannot have happened.
        before = self.snapshot()
        bad = [
            dict(accepted=False, landed=None,
                 review={"verdict": "reject", "reasons": "r", "override": "user: yes"}),
            dict(review={"verdict": "accept", "reasons": "r", "override": "user: yes"}),
            dict(review={"verdict": "reject", "reasons": "r", "override": 1}),
            dict(review={"verdict": "reject", "reasons": "r", "override": " "}),
        ]
        for kw in bad:
            self.sim("append", "attempt", ok=False, record=attempt("P-0001", **kw))
        self.assertEqual(self.snapshot(), before)


class TestNewProblemWithAttempt(SimEnv):
    def test_new_problem_and_attempt_in_one_commit(self):
        # Prevents: a problem opened with no attempt when a second append fails.
        self.init()
        before = self.commits()
        rec = attempt("new", new_problem={
            "hypothesis": "draft left uncommitted across the review hop",
            "opened": "2026-11-27", "opened_by": "user", "project": "proj-a",
            "tags": ["step-misbehaves"]})
        r = self.sim("append", "attempt", record=rec)
        self.assertEqual(self.commits(), before + 1)
        probs = self.lines("problems.jsonl")
        self.assertEqual(probs[-1]["id"], "P-0001")
        self.assertEqual(probs[-1]["hypothesis"],
                         "draft left uncommitted across the review hop")
        att = self.lines("attempts.jsonl")[-1]
        self.assertEqual(att["id"], "P-0001/A1")
        self.assertEqual(att["problem"], "P-0001")
        self.assertEqual(att["prediction"]["problem"], "P-0001")
        self.assertNotIn("new_problem", att)
        self.assertIn("P-0001", r.stdout)
        self.sim("validate")

    def test_bad_new_problem_writes_nothing(self):
        # Prevents: a half-write (attempt without problem, or the reverse).
        self.init()
        before = self.snapshot()
        commits = self.commits()
        self.sim("append", "attempt", ok=False, record=attempt(
            "new", new_problem={"opened": "2026-11-27", "opened_by": "user",
                                "project": "proj-a", "tags": []}))
        self.sim("append", "attempt", ok=False, record=attempt("new"))
        self.sim("append", "attempt", ok=False, record=attempt(
            "P-0000", new_problem=problem()))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.commits(), commits)


class TestSimNotebookFixtureKey(GuardrailEnv):
    def test_setter_keeps_both_optional_keys(self):
        # Prevents: setting one optional key silently dropping the other.
        self.set_harness_push_remote("*harness_remote*")
        self.set_sim_notebook("/tmp/sim-notebook")
        text = self.params_file.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(BASE_PARAMS))
        self.assertIn("harness_push_remote: *harness_remote*\n", text)
        self.assertIn("sim_notebook: /tmp/sim-notebook\n", text)
        self.set_sim_notebook(None)
        text = self.params_file.read_text(encoding="utf-8")
        self.assertNotIn("sim_notebook", text)
        self.assertIn("harness_push_remote", text)


class TestLand(SimEnv):
    """Landed means the merge-to-main date (sim-harness S05): an attempt
    committed on a plan branch is appended with landed null, and a land
    record appended after the user's merge starts its count."""

    def pending(self):
        self.init()
        self.sim("append", "problem", record=problem())
        self.sim("append", "attempt", record=attempt("P-0001", landed=None))

    def state_line(self):
        return [l for l in self.notebook_md().splitlines() if "verdict:" in l][-1]

    def test_land_starts_the_count(self):
        # Prevents: sessions that ran before the merge counting toward held.
        self.pending()
        for n in range(1, 11):
            self.session(n, started="2026-11-05")
        self.assertIn("accepted, not landed", self.state_line())
        self.sim("append", "land",
                 record={"attempt": "P-0001/A1", "date": "2026-11-06"})
        self.assertIn("landed 2026-11-06, under observation", self.state_line())
        for n in range(11, 20):
            self.session(n, started="2026-11-07")
        self.assertIn("under observation", self.state_line())
        r = self.session(20, started="2026-11-07")
        self.assertIn("P-0001 attempt 1: held", r.stdout)
        self.sim("validate")

    def test_land_refusals(self):
        # Prevents: a bogus landing corrupting verdicts.
        self.pending()
        self.sim("append", "attempt", record=attempt(
            "P-0001", accepted=False, landed=None, commits=[]))
        self.sim("append", "attempt", record=attempt("P-0001"))
        before = self.snapshot()
        for rec in ({"attempt": "P-0009/A1", "date": "2026-11-06"},
                    {"attempt": "P-0001/A2", "date": "2026-11-06"},
                    {"attempt": "P-0001/A3", "date": "2026-11-06"},
                    {"attempt": "P-0001/A1", "date": "2026-11-01"},
                    {"attempt": "P-0001/A1"}):
            self.sim("append", "land", record=rec, ok=False)
        self.assertEqual(self.snapshot(), before)
        self.sim("append", "land",
                 record={"attempt": "P-0001/A1", "date": "2026-11-06"})
        before = self.snapshot()
        self.sim("append", "land", ok=False,
                 record={"attempt": "P-0001/A1", "date": "2026-11-07"})
        self.assertEqual(self.snapshot(), before)

    def test_land_command_uses_main(self):
        # Prevents: landing an attempt whose commit never reached main.
        repo = _git_repo(self.tmp / "harness")
        (repo / "f").write_text("a", encoding="utf-8")
        _git(repo, "add", "f")
        _git(repo, "commit", "-q", "-m", "base")
        _git(repo, "checkout", "-q", "-b", "plan")
        (repo / "f").write_text("b", encoding="utf-8")
        _git(repo, "commit", "-q", "-am", "on plan")
        on_plan = _git(repo, "rev-parse", "HEAD").stdout.strip()
        _git(repo, "checkout", "-q", "-b", "side", "main")
        (repo / "g").write_text("c", encoding="utf-8")
        _git(repo, "add", "g")
        _git(repo, "commit", "-q", "-m", "side only")
        side = _git(repo, "rev-parse", "HEAD").stdout.strip()
        self.init()
        self.sim("append", "problem", record=problem())
        self.sim("append", "attempt", record=attempt(
            "P-0001", landed=None, commits=[on_plan]))
        self.sim("append", "attempt", record=attempt(
            "P-0001", landed=None, commits=[side]))
        land = ("land", "--repo", str(repo), "--ref", "main",
                "--date", "2026-11-08")
        r = self.sim(*land)
        self.assertIn("no attempts to land", r.stdout)
        _git(repo, "checkout", "-q", "main")
        _git(repo, "merge", "-q", "--no-ff", "plan", "-m", "merge plan")
        r = self.sim(*land)
        self.assertIn("landed P-0001/A1", r.stdout)
        self.assertNotIn("P-0001/A2", r.stdout)
        lands = [x for x in self.lines("attempts.jsonl") if x["type"] == "land"]
        self.assertEqual([(x["attempt"], x["date"]) for x in lands],
                         [("P-0001/A1", "2026-11-08")])
        commits = self.commits()
        r = self.sim(*land)
        self.assertIn("no attempts to land", r.stdout)
        self.assertEqual(self.commits(), commits)
        self.sim("validate")

    def test_render_unchanged_without_land(self):
        # Prevents: the existing notebook view shifting under the new code.
        self.landed_problem()
        self.sim("append", "link", record=link("P-0001"))
        view = self.notebook_md()
        self.sim("render")
        self.assertEqual(self.notebook_md(), view)
        self.assertIn("recurred (docs/observations.md:L90, 2026-11-10)", view)


class TestNewProblemWithLink(SimEnv):
    NEW = {"hypothesis": "ingest drops the link batch", "opened": "2026-11-27",
           "opened_by": "user", "project": "proj-a", "tags": ["step-misbehaves"]}

    def test_link_with_new_problem_one_write(self):
        # Prevents: a problem opened with no link (or the reverse) when one
        # of two writes fails, and a confirmed "new" proposal reading "changed".
        self.init()
        before = self.commits()
        r = self.sim("append", "link", record=link(
            "new", proposed="new", new_problem=dict(self.NEW)))
        self.assertEqual(self.commits(), before + 1)
        self.assertEqual(self.lines("problems.jsonl")[-1]["id"], "P-0001")
        lk = self.lines("links.jsonl")[-1]
        self.assertEqual((lk["problem"], lk["proposed"], lk["verdict"],
                          lk["opened_problem"]),
                         ("P-0001", "new", "accepted", True))
        self.assertNotIn("new_problem", lk)
        self.assertIn("P-0001", r.stdout)
        self.sim("validate")

    def test_half_specified_or_unopened_new_refused(self):
        # Prevents: a half-write, and "accepted" on a "new" proposal that
        # names a problem not opened with it.
        self.init()
        self.sim("append", "problem", record=problem())
        before = self.snapshot()
        self.sim("append", "link", ok=False, record=link("new", proposed="new"))
        self.sim("append", "link", ok=False, record=link(
            "P-0001", new_problem=dict(self.NEW)))
        self.sim("append", "link", ok=False, record=link(
            "P-0001", proposed="new", verdict="accepted"))
        self.sim("append", "link", ok=False, record=link(
            "P-0001", proposed="new", verdict="accepted", opened_problem=True))
        self.assertEqual(self.snapshot(), before)
        self.sim("append", "link", record=link(
            "P-0001", proposed="new", verdict="changed"))


if __name__ == "__main__":
    unittest.main()
