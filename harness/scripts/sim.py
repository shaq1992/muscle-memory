#!/usr/bin/env python3
"""sim.py -- the SIM notebook tool (stdlib only).

A notebook is a directory, normally a git clone, holding append-only JSONL
records and a rendered NOTEBOOK.md. The record shapes, the verdict rule and
the folding rule are defined in harness/templates/sim_record_schema.md; this
script is their only writer.

Every command takes --notebook PATH and --domain NAME. Every command first
pulls (fast-forward only) when the clone has an upstream: a failed pull makes
a write refuse and a read warn. Every write validates the whole record set in
memory first (a refused write touches nothing), appends, derives verdicts,
appends a verdict record for each change, re-renders NOTEBOOK.md and commits.
sim.py never pushes: the caller owns the push.

Commands:
  init      [--hold-after N] [--fold-after N] [--agreement-last N]
            [--agreement-threshold F]
  append    problem|attempt|link|alias --record JSON
  verdict   --project P --plan X --session NN --kind implement|grill
            --started DATE   (one counted session)
  render    re-render NOTEBOOK.md and commit if it changed
  validate  record shapes, references, verdict log, stale view
  count     counts by status
  agreement link-agreement metric over the last N confirmed links
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_THRESHOLDS = {
    "hold_after": 10,  # counted sessions with no recurrence -> held
    "fold_after": 30,  # counted sessions after held -> folded in the view
    "agreement_last": 30,  # links in the agreement window
    "agreement_threshold": 0.9,  # accepted share that meets the bar
}

UNATTRIBUTED = "P-0000"
UNATTRIBUTED_HYPOTHESIS = "unattributed: attempts not mapped to a problem"
META = "notebook.json"
VIEW = "NOTEBOOK.md"
FILES = {
    "problem": "problems.jsonl",
    "attempt": "attempts.jsonl",
    "verdict": "attempts.jsonl",
    "link": "links.jsonl",
    "alias": "aliases.jsonl",
    "session": "sessions.jsonl",
}
JSONL_FILES = sorted(set(FILES.values()))

DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})?)?$")
PID_RE = re.compile(r"^P-\d{4}$")
REVIEW_VERDICTS = ("accept", "revise", "reject")
LINK_VERDICTS = ("accepted", "changed")
SESSION_KINDS = ("implement", "grill")


class SimError(Exception):
    pass


# ---------------------------------------------------------------- storage

def load_meta(nb):
    path = nb / META
    if not path.exists():
        raise SimError("no {0} in {1}: run `sim.py init` first".format(META, nb))
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SimError("{0} is not valid JSON: {1}".format(META, e))
    th = dict(DEFAULT_THRESHOLDS)
    th.update(meta.get("thresholds") or {})
    meta["thresholds"] = th
    return meta


def load_records(nb):
    """All records from every JSONL file, sorted by seq. Raises on bad JSON."""
    records = []
    for name in JSONL_FILES:
        path = nb / name
        if not path.exists():
            continue
        prev = 0
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                raise SimError("{0} line {1}: not valid JSON".format(name, i))
            if not isinstance(rec, dict):
                raise SimError("{0} line {1}: not a JSON object".format(name, i))
            seq = rec.get("seq")
            if not isinstance(seq, int) or seq <= prev:
                raise SimError("{0} line {1}: seq must be an integer greater "
                               "than the line before".format(name, i))
            if FILES.get(rec.get("type")) != name:
                raise SimError("{0} line {1}: record type {2!r} does not "
                               "belong in this file".format(name, i, rec.get("type")))
            prev = seq
            records.append(rec)
    records.sort(key=lambda r: r["seq"])
    return records


def append_lines(nb, new_records):
    for rec in new_records:
        with open(nb / FILES[rec["type"]], "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")


# ---------------------------------------------------------------- git

def _git(nb, *args):
    return subprocess.run(["git", "-C", str(nb)] + list(args),
                          capture_output=True, text=True, timeout=120)


def is_git_repo(nb):
    return nb.is_dir() and _git(nb, "rev-parse", "--git-dir").returncode == 0


def pull(nb, write):
    """Fast-forward-only pull when an upstream exists. A failed pull makes a
    write refuse (so clones never fork) and a read warn."""
    if not is_git_repo(nb):
        if write:
            raise SimError("{0} is not a git repo".format(nb))
        return
    if _git(nb, "rev-parse", "--abbrev-ref", "@{u}").returncode != 0:
        print("sim: note: no upstream configured; pull skipped", file=sys.stderr)
        return
    r = _git(nb, "pull", "--ff-only", "-q")
    if r.returncode != 0:
        msg = "pull --ff-only failed: {0}".format(r.stderr.strip())
        if write:
            raise SimError(msg + " -- refusing to write")
        print("sim: warning: " + msg + " -- reading the local copy",
              file=sys.stderr)


def commit(nb, message):
    paths = [p for p in [META, VIEW] + JSONL_FILES if (nb / p).exists()]
    r = _git(nb, "add", "--", *paths)
    if r.returncode != 0:
        raise SimError("git add failed: " + r.stderr.strip())
    if _git(nb, "diff", "--cached", "--quiet").returncode == 0:
        return
    r = _git(nb, "commit", "-q", "-m", "sim: " + message)
    if r.returncode != 0:
        raise SimError("git commit failed: " + r.stderr.strip())


# ---------------------------------------------------------------- validation

def _req(rec, field, kind, errors, where, allow_empty=False):
    v = rec.get(field)
    if kind == "str":
        if not isinstance(v, str) or (not allow_empty and not v.strip()):
            errors.append("{0}: {1} must be a non-empty string".format(where, field))
    elif kind == "date":
        if not isinstance(v, str) or not DATE_RE.match(v):
            errors.append("{0}: {1} must be an ISO date".format(where, field))
    elif kind == "list":
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errors.append("{0}: {1} must be a list of strings".format(where, field))
    elif kind == "bool":
        if not isinstance(v, bool):
            errors.append("{0}: {1} must be true or false".format(where, field))
    return v


def validate_records(records, domain):
    """Shape and reference checks over the whole set, in seq order. Returns
    a list of error strings (empty when valid)."""
    errors = []
    seqs = set()
    problems, attempts, alias_of, session_keys = {}, {}, {}, set()
    attempt_counts = {}
    for rec in records:
        where = "seq {0} ({1})".format(rec.get("seq"), rec.get("type"))
        if rec.get("seq") in seqs:
            errors.append(where + ": duplicate seq")
        seqs.add(rec.get("seq"))
        if rec.get("domain") != domain:
            errors.append("{0}: domain {1!r} is not the notebook's {2!r}".format(
                where, rec.get("domain"), domain))
        t = rec.get("type")
        if t == "problem":
            pid = rec.get("id")
            expected = "P-{0:04d}".format(len(problems))
            if pid != expected:
                errors.append("{0}: id {1!r}, expected {2}".format(where, pid, expected))
            _req(rec, "hypothesis", "str", errors, where)
            _req(rec, "opened", "date", errors, where)
            _req(rec, "opened_by", "str", errors, where)
            _req(rec, "project", "str", errors, where)
            _req(rec, "tags", "list", errors, where)
            problems[pid] = rec
        elif t == "attempt":
            pid = rec.get("problem")
            if pid not in problems:
                errors.append("{0}: unknown problem {1!r}".format(where, pid))
            n = attempt_counts.get(pid, 0) + 1
            attempt_counts[pid] = n
            if rec.get("id") != "{0}/A{1}".format(pid, n):
                errors.append("{0}: id {1!r}, expected {2}/A{3}".format(
                    where, rec.get("id"), pid, n))
            _req(rec, "date", "date", errors, where)
            for f in ("model", "project", "change", "why"):
                _req(rec, f, "str", errors, where)
            _req(rec, "files", "list", errors, where)
            _req(rec, "commits", "list", errors, where)
            accepted = _req(rec, "accepted", "bool", errors, where)
            landed = rec.get("landed")
            if landed is not None:
                _req(rec, "landed", "date", errors, where)
                if accepted is False:
                    errors.append(where + ": a rejected attempt cannot have landed")
            if rec.get("harness_version") is not None:
                _req(rec, "harness_version", "str", errors, where)
            pred = rec.get("prediction")
            if pred is not None:
                if not isinstance(pred, dict):
                    errors.append(where + ": prediction must be an object")
                else:
                    if pred.get("problem") != pid:
                        errors.append(where + ": prediction names problem {0!r}, "
                                      "not the attempt's {1!r}".format(
                                          pred.get("problem"), pid))
                    _req(pred, "signature", "str", errors, where + " prediction")
                    for f in ("expect_absent_tags", "prevents", "at_risk"):
                        _req(pred, f, "list", errors, where + " prediction")
            review = rec.get("review")
            if review is not None:
                if not isinstance(review, dict) or \
                        review.get("verdict") not in REVIEW_VERDICTS:
                    errors.append(where + ": review.verdict must be one of " +
                                  "/".join(REVIEW_VERDICTS))
                else:
                    _req(review, "reasons", "str", errors, where + " review")
            attempts[rec.get("id")] = rec
        elif t == "verdict":
            if rec.get("attempt") not in attempts:
                errors.append("{0}: unknown attempt {1!r}".format(
                    where, rec.get("attempt")))
            if rec.get("state") not in ("held", "recurred"):
                errors.append(where + ": state must be held or recurred")
            _req(rec, "date", "date", errors, where)
            if not isinstance(rec.get("cause_seq"), int):
                errors.append(where + ": cause_seq must be an integer")
        elif t == "link":
            obs = rec.get("observation")
            if not isinstance(obs, dict):
                errors.append(where + ": observation must be an object")
            else:
                _req(obs, "project", "str", errors, where + " observation")
                _req(obs, "ref", "str", errors, where + " observation")
                _req(obs, "date", "date", errors, where + " observation")
            pid, proposed = rec.get("problem"), rec.get("proposed")
            if pid not in problems:
                errors.append("{0}: unknown problem {1!r}".format(where, pid))
            if proposed != "new" and proposed not in problems:
                errors.append("{0}: proposed must be a known problem or "
                              "\"new\"".format(where))
            verdict = rec.get("verdict")
            if verdict not in LINK_VERDICTS:
                errors.append(where + ": verdict must be accepted or changed")
            elif (verdict == "accepted") != (proposed == pid):
                errors.append(where + ": verdict 'accepted' means proposed equals "
                              "problem; 'changed' means they differ")
            _req(rec, "proposed_by", "str", errors, where)
            _req(rec, "date", "date", errors, where)
        elif t == "alias":
            a, of = rec.get("alias"), rec.get("of")
            if a not in problems or of not in problems:
                errors.append(where + ": alias and of must be known problems")
            elif a == of or UNATTRIBUTED in (a, of):
                errors.append(where + ": alias must join two distinct real problems")
            elif a in alias_of:
                errors.append("{0}: {1} is already an alias".format(where, a))
            elif resolve(of, alias_of) == a:
                errors.append(where + ": alias would make a cycle")
            else:
                alias_of[a] = of
            for f in ("reason", "approved_by"):
                _req(rec, f, "str", errors, where)
            _req(rec, "date", "date", errors, where)
        elif t == "session":
            key = "{0}/{1}/{2}".format(rec.get("project"), rec.get("plan"),
                                       rec.get("session"))
            for f in ("project", "plan", "session"):
                _req(rec, f, "str", errors, where)
            if rec.get("key") != key:
                errors.append("{0}: key must be {1}".format(where, key))
            if key in session_keys:
                errors.append("{0}: session {1} already counted".format(where, key))
            session_keys.add(key)
            if rec.get("kind") not in SESSION_KINDS:
                errors.append(where + ": kind must be implement or grill")
            _req(rec, "started", "date", errors, where)
        else:
            errors.append("{0}: unknown record type {1!r}".format(where, t))
    if records and (records[0].get("type") != "problem" or
                    records[0].get("id") != UNATTRIBUTED):
        errors.append("the first record must be the {0} unattributed "
                      "problem".format(UNATTRIBUTED))
    return errors


# ---------------------------------------------------------------- derivation

def resolve(pid, alias_of):
    seen = set()
    while pid in alias_of and pid not in seen:
        seen.add(pid)
        pid = alias_of[pid]
    return pid


def derive(records, thresholds):
    """Replay the records in seq order (verdict records are output, not
    input). Returns (attempt_state, problem_status, changes) where changes is
    the ordered list of (attempt_id, state, date, cause_seq) transitions."""
    hold_after = thresholds["hold_after"]
    alias_of = {}
    att = {}
    order = []
    links_by_problem = {}
    changes = []
    reopened = {}
    for rec in records:
        t = rec["type"]
        if t == "alias":
            alias_of[rec["alias"]] = rec["of"]
        elif t == "attempt":
            if rec["problem"] == UNATTRIBUTED:
                state = "unattributed"
            elif not rec["accepted"]:
                state = "rejected"
            elif rec.get("landed") is None:
                state = "accepted, not landed"
            else:
                state = "under observation"
            att[rec["id"]] = {"rec": rec, "state": state, "counted": 0,
                              "since_hold": 0, "held_seq": None,
                              "cause": None}
            order.append(rec["id"])
        elif t == "session":
            for aid in order:
                a = att[aid]
                landed = a["rec"].get("landed")
                if landed is None or not rec["started"] > landed:
                    continue
                if a["state"] == "under observation":
                    a["counted"] += 1
                    if a["counted"] >= hold_after:
                        a["state"] = "held"
                        a["held_seq"] = rec["seq"]
                        a["cause"] = rec
                        changes.append((aid, "held", rec["started"], rec["seq"]))
                elif a["state"] == "held":
                    a["since_hold"] += 1
        elif t == "link":
            canon = resolve(rec["problem"], alias_of)
            links_by_problem.setdefault(canon, []).append(rec)
            obs_date = rec["observation"]["date"]
            hit = False
            for aid in order:
                a = att[aid]
                if resolve(a["rec"]["problem"], alias_of) != canon:
                    continue
                if a["state"] == "under observation" and \
                        obs_date > a["rec"]["landed"]:
                    a["state"] = "recurred"
                    a["cause"] = rec
                    hit = True
                    changes.append((aid, "recurred", rec["date"], rec["seq"]))
            if not hit:
                held = [aid for aid in order if att[aid]["state"] == "held" and
                        resolve(att[aid]["rec"]["problem"], alias_of) == canon]
                if held and canon not in reopened:
                    last = held[-1]
                    if rec["seq"] > att[last]["held_seq"] and \
                            obs_date > att[last]["rec"]["landed"]:
                        reopened[canon] = rec
    status = {}
    for rec in records:
        if rec["type"] != "problem" or rec["id"] == UNATTRIBUTED:
            continue
        pid = rec["id"]
        if pid in alias_of:
            status[pid] = "merged into " + resolve(pid, alias_of)
            continue
        group = [aid for aid in order
                 if resolve(att[aid]["rec"]["problem"], alias_of) == pid and
                 att[aid]["state"] in ("under observation", "held", "recurred")]
        if not group:
            status[pid] = "open"
            continue
        last = att[group[-1]]
        if last["state"] == "held":
            r = reopened.get(pid)
            if r is not None and r["seq"] > last["held_seq"]:
                status[pid] = "reopened"
            elif last["since_hold"] >= thresholds["fold_after"]:
                status[pid] = "held (folded)"
            else:
                status[pid] = "held"
        else:
            status[pid] = last["state"]
    return att, status, changes, alias_of, links_by_problem, reopened


def pending_verdicts(records, changes, domain):
    recorded = {(r["attempt"], r["state"]) for r in records if r["type"] == "verdict"}
    out = []
    for aid, state, date, cause in changes:
        if (aid, state) not in recorded:
            out.append({"type": "verdict", "domain": domain, "attempt": aid,
                        "state": state, "date": date, "cause_seq": cause})
    return out


def verdict_log_errors(records, changes):
    derived = {(aid, state) for aid, state, _, _ in changes}
    recorded = [(r["attempt"], r["state"]) for r in records if r["type"] == "verdict"]
    errors = []
    for v in recorded:
        if v not in derived:
            errors.append("verdict record {0} {1} does not follow from the "
                          "records".format(*v))
    for v in derived - set(recorded):
        errors.append("missing verdict record: {0} {1}".format(*v))
    return errors


# ---------------------------------------------------------------- render

def _attempt_line(a):
    rec = a["rec"]
    n = rec["id"].split("/A")[1]
    head = "- Attempt {0} ({1}; {2}{3}; {4}): {5} -- why: {6}".format(
        n, rec["date"], rec["model"],
        ", harness " + rec["harness_version"] if rec.get("harness_version") else "",
        rec["project"], rec["change"], rec["why"])
    lines = [head]
    detail = []
    if rec["files"]:
        detail.append("files: " + ", ".join(rec["files"]))
    if rec["commits"]:
        detail.append("commits: " + ", ".join(rec["commits"]))
    if rec.get("review"):
        detail.append("review: {0} ({1})".format(rec["review"]["verdict"],
                                                 rec["review"]["reasons"]))
    state = a["state"]
    if state == "under observation":
        state = "landed {0}, under observation".format(rec["landed"])
    elif state == "held":
        state = "held"
    elif state == "recurred":
        c = a["cause"]
        state = "recurred ({0}, {1})".format(c["observation"]["ref"],
                                            c["observation"]["date"])
    detail.append("verdict: " + state)
    lines.append("  - " + "; ".join(detail))
    p = rec.get("prediction")
    if p:
        lines.append("  - Prediction: {0}; expect absent tags: {1}; prevents: {2}; "
                     "at risk: {3}".format(
                         p["signature"], ", ".join(p["expect_absent_tags"]) or "-",
                         ", ".join(p["prevents"]) or "-",
                         ", ".join(p["at_risk"]) or "-"))
    return lines


def render(records, meta):
    th = meta["thresholds"]
    att, status, _, alias_of, links_by_problem, _ = derive(records, th)
    problems = [r for r in records if r["type"] == "problem"]
    aliases_for = {}
    for a, of in alias_of.items():
        aliases_for.setdefault(resolve(of, alias_of), []).append(a)
    by_problem = {}
    for aid, a in att.items():
        by_problem.setdefault(resolve(a["rec"]["problem"], alias_of), []).append(a)
    sessions = sum(1 for r in records if r["type"] == "session")
    links = sum(1 for r in records if r["type"] == "link")

    out = ["# SIM notebook: {0}".format(meta["domain"]), "",
           "Rendered by sim.py from the JSONL records; never edit by hand. "
           "An attempt is held after {0} counted sessions with no recurrence; "
           "a problem held for {1} more sessions folds to one line.".format(
               th["hold_after"], th["fold_after"]), "",
           "Totals: {0} problems, {1} attempts, {2} links, {3} counted "
           "sessions.".format(len(problems) - 1,
                              sum(1 for a in att.values()
                                  if a["state"] != "unattributed"),
                              links, sessions)]

    def section(title, pids):
        if not pids:
            return
        out.extend(["", "## " + title])
        for pid in pids:
            rec = next(r for r in problems if r["id"] == pid)
            out.extend(["", "### {0}: {1}".format(pid, rec["hypothesis"])])
            meta_line = "- Status: {0}. Opened {1} by {2} in {3}; tags: {4}".format(
                status[pid], rec["opened"], rec["opened_by"], rec["project"],
                ", ".join(rec["tags"]) or "-")
            if aliases_for.get(pid):
                meta_line += "; aliases: " + ", ".join(sorted(aliases_for[pid]))
            out.append(meta_line)
            for a in by_problem.get(pid, []):
                if a["state"] == "under observation":
                    out.append("- Counted sessions: {0}/{1}".format(
                        a["counted"], th["hold_after"]))
            for a in by_problem.get(pid, []):
                out.extend(_attempt_line(a))
            for lk in links_by_problem.get(pid, []):
                o = lk["observation"]
                out.append("- Link: {0} ({1}, {2}) proposed {3} by {4}, {5}".format(
                    o["ref"], o["project"], o["date"], lk["proposed"],
                    lk["proposed_by"], lk["verdict"]))

    real = [r["id"] for r in problems if r["id"] != UNATTRIBUTED
            and not status[r["id"]].startswith("merged")]
    section("Open", [p for p in real if status[p] in ("open", "recurred", "reopened")])
    section("Under observation", [p for p in real if status[p] == "under observation"])
    section("Held", [p for p in real if status[p] == "held"])
    folded = [p for p in real if status[p] == "held (folded)"]
    if folded:
        out.extend(["", "## Folded (held {0}+ sessions)".format(th["fold_after"]), ""])
        for pid in folded:
            rec = next(r for r in problems if r["id"] == pid)
            final = [a for a in by_problem[pid] if a["state"] == "held"][-1]["rec"]
            out.append("- {0}: {1} -- final attempt {2} ({3}), held".format(
                pid, rec["hypothesis"], final["id"].split("/A")[1],
                ", ".join(final["commits"]) or final["date"]))
    una = by_problem.get(UNATTRIBUTED, [])
    if una:
        out.extend(["", "## Unattributed ({0} attempts, not tracked for "
                    "recurrence)".format(len(una)), ""])
        for a in una:
            rec = a["rec"]
            out.append("- {0} {1}: {2}".format(
                rec["date"], ", ".join(rec["commits"]) or "-", rec["change"]))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- commands

def _check_domain(meta, domain):
    if meta["domain"] != domain:
        raise SimError("--domain {0!r} does not match this notebook's domain "
                       "{1!r}".format(domain, meta["domain"]))


def _next_seq(records):
    return max((r["seq"] for r in records), default=0) + 1


def _write(nb, meta, records, new, message):
    """Validate the full set in memory, then append, derive, log verdicts,
    render and commit. Nothing touches disk unless every check passes."""
    seq = _next_seq(records)
    for rec in new:
        rec["seq"] = seq
        seq += 1
    combined = records + new
    errors = validate_records(combined, meta["domain"])
    if errors:
        raise SimError("refused:\n  " + "\n  ".join(errors))
    reopened_before = derive(records, meta["thresholds"])[5]
    _, status, changes, _, _, reopened = derive(combined, meta["thresholds"])
    verdicts = pending_verdicts(combined, changes, meta["domain"])
    for v in verdicts:
        v["seq"] = seq
        seq += 1
    combined += verdicts
    append_lines(nb, new + verdicts)
    (nb / VIEW).write_text(render(combined, meta), encoding="utf-8")
    commit(nb, message)
    for v in verdicts:
        pid, n = v["attempt"].split("/A")
        print("{0} attempt {1}: {2}".format(pid, n, v["state"]))
    for pid in sorted(reopened):
        if pid not in reopened_before and status.get(pid) == "reopened":
            print("{0} reopened (link confirmed after held)".format(pid))
    return combined


def cmd_init(nb, domain, args):
    if not is_git_repo(nb):
        raise SimError("{0} is not a git repo".format(nb))
    pull(nb, write=True)
    if (nb / META).exists():
        raise SimError("{0} already has a {1}".format(nb, META))
    thresholds = dict(DEFAULT_THRESHOLDS)
    for key in thresholds:
        v = getattr(args, key)
        if v is not None:
            thresholds[key] = v
    meta = {"domain": domain, "schema": 1, "thresholds": thresholds}
    (nb / META).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    first = {"type": "problem", "domain": domain, "id": UNATTRIBUTED,
             "hypothesis": UNATTRIBUTED_HYPOTHESIS, "opened": "1970-01-01",
             "opened_by": "sim.py", "project": "-", "tags": []}
    _write(nb, meta, [], [first], "init notebook ({0})".format(domain))
    print("initialised {0} notebook at {1}".format(domain, nb))


def cmd_append(nb, domain, args):
    pull(nb, write=True)
    meta = load_meta(nb)
    _check_domain(meta, domain)
    records = load_records(nb)
    try:
        rec = json.loads(args.record)
    except ValueError as e:
        raise SimError("--record is not valid JSON: {0}".format(e))
    if not isinstance(rec, dict):
        raise SimError("--record must be a JSON object")
    for k in ("seq", "type", "domain"):
        rec.pop(k, None)
    rec = dict(type=args.type, domain=domain, **rec)
    if args.type == "problem":
        rec["id"] = "P-{0:04d}".format(sum(1 for r in records if r["type"] == "problem"))
        label = rec["id"]
    elif args.type == "attempt":
        pid = rec.get("problem")
        n = sum(1 for r in records if r["type"] == "attempt" and r["problem"] == pid)
        rec["id"] = "{0}/A{1}".format(pid, n + 1)
        rec.setdefault("landed", None)
        label = rec["id"]
    elif args.type == "link":
        label = "to {0}".format(rec.get("problem"))
    else:
        label = "{0} of {1}".format(rec.get("alias"), rec.get("of"))
    _write(nb, meta, records, [rec], "append {0} {1}".format(args.type, label))
    print("appended {0} {1}".format(args.type, label))


def cmd_verdict(nb, domain, args):
    pull(nb, write=True)
    meta = load_meta(nb)
    _check_domain(meta, domain)
    records = load_records(nb)
    key = "{0}/{1}/{2}".format(args.project, args.plan, args.session)
    if any(r["type"] == "session" and r["key"] == key for r in records):
        print("session {0} already counted; no verdict changes".format(key))
        return
    rec = {"type": "session", "domain": domain, "key": key,
           "project": args.project, "plan": args.plan, "session": args.session,
           "kind": args.kind, "started": args.started}
    before = sum(1 for r in records if r["type"] == "verdict")
    combined = _write(nb, meta, records, [rec], "count session " + key)
    if sum(1 for r in combined if r["type"] == "verdict") == before:
        print("no verdict changes")


def _read_state(nb, domain):
    pull(nb, write=False)
    meta = load_meta(nb)
    _check_domain(meta, domain)
    return meta, load_records(nb)


def cmd_render(nb, domain, args):
    pull(nb, write=True)
    meta = load_meta(nb)
    _check_domain(meta, domain)
    records = load_records(nb)
    errors = validate_records(records, domain)
    if errors:
        raise SimError("records invalid, not rendering:\n  " + "\n  ".join(errors))
    (nb / VIEW).write_text(render(records, meta), encoding="utf-8")
    commit(nb, "re-render " + VIEW)
    print("rendered " + VIEW)


def cmd_validate(nb, domain, args):
    meta, records = _read_state(nb, domain)
    errors = validate_records(records, domain)
    if not errors:
        _, _, changes, _, _, _ = derive(records, meta["thresholds"])
        errors += verdict_log_errors(records, changes)
        view = nb / VIEW
        current = view.read_text(encoding="utf-8") if view.exists() else None
        if current != render(records, meta):
            errors.append("{0} is stale: it is not the rendering of the current "
                          "records (run `sim.py render`)".format(VIEW))
    if errors:
        print("INVALID:\n  " + "\n  ".join(errors))
        return 1
    print("valid: {0} records".format(len(records)))
    return 0


def cmd_count(nb, domain, args):
    meta, records = _read_state(nb, domain)
    att, status, _, _, _, _ = derive(records, meta["thresholds"])
    by_status = {}
    for s in status.values():
        by_status[s] = by_status.get(s, 0) + 1
    by_state = {}
    for a in att.values():
        by_state[a["state"]] = by_state.get(a["state"], 0) + 1

    def fmt(d):
        return ", ".join("{0} {1}".format(k, d[k]) for k in sorted(d)) or "-"
    tracked = sum(v for k, v in by_state.items() if k != "unattributed")
    print("problems: {0} ({1})".format(len(status), fmt(by_status)))
    print("attempts: {0} ({1})".format(tracked, fmt(
        {k: v for k, v in by_state.items() if k != "unattributed"})))
    print("unattributed attempts: {0}".format(by_state.get("unattributed", 0)))
    print("links: {0}".format(sum(1 for r in records if r["type"] == "link")))
    print("sessions: {0}".format(sum(1 for r in records if r["type"] == "session")))


def cmd_agreement(nb, domain, args):
    meta, records = _read_state(nb, domain)
    th = meta["thresholds"]
    last = args.last or th["agreement_last"]
    threshold = args.threshold if args.threshold is not None \
        else th["agreement_threshold"]
    links = [r for r in records if r["type"] == "link"][-last:]
    accepted = sum(1 for r in links if r["verdict"] == "accepted")
    if not links:
        print("agreement: no links yet; threshold {0}: not met".format(threshold))
        return
    share = accepted / len(links)
    met = len(links) >= last and share >= threshold
    print("agreement: {0}/{1} accepted ({2:.1f}%) over the last {3} links; "
          "threshold {4}: {5}".format(accepted, len(links), share * 100, last,
                                      threshold, "met" if met else "not met"))


def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--notebook", required=True, help="notebook directory")
    common.add_argument("--domain", required=True, help="the notebook's domain")
    p = argparse.ArgumentParser(description="SIM notebook tool")
    sub = p.add_subparsers(dest="command", required=True)
    pi = sub.add_parser("init", parents=[common])
    pi.add_argument("--hold-after", dest="hold_after", type=int)
    pi.add_argument("--fold-after", dest="fold_after", type=int)
    pi.add_argument("--agreement-last", dest="agreement_last", type=int)
    pi.add_argument("--agreement-threshold", dest="agreement_threshold", type=float)
    pa = sub.add_parser("append", parents=[common])
    pa.add_argument("type", choices=("problem", "attempt", "link", "alias"))
    pa.add_argument("--record", required=True, help="the record as JSON")
    pv = sub.add_parser("verdict", parents=[common])
    pv.add_argument("--project", required=True)
    pv.add_argument("--plan", required=True)
    pv.add_argument("--session", required=True)
    pv.add_argument("--kind", required=True, choices=SESSION_KINDS)
    pv.add_argument("--started", required=True)
    sub.add_parser("render", parents=[common])
    sub.add_parser("validate", parents=[common])
    sub.add_parser("count", parents=[common])
    pg = sub.add_parser("agreement", parents=[common])
    pg.add_argument("--last", type=int)
    pg.add_argument("--threshold", type=float)
    args = p.parse_args(argv)
    nb = Path(args.notebook).expanduser()
    commands = {"init": cmd_init, "append": cmd_append, "verdict": cmd_verdict,
                "render": cmd_render, "validate": cmd_validate,
                "count": cmd_count, "agreement": cmd_agreement}
    try:
        rc = commands[args.command](nb, args.domain, args)
    except SimError as e:
        print("sim: error: {0}".format(e), file=sys.stderr)
        return 2
    return rc or 0


if __name__ == "__main__":
    sys.exit(main())
