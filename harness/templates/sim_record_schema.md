# Template: SIM Record Schema

Single source of truth for the records of a SIM notebook: the memory that
lets an improvement loop remember each problem, each attempt to fix it, what
the attempt predicted and whether the problem came back. The only writer is
`harness/scripts/sim.py`; no command restates this schema.

## The notebook

A notebook is a directory, normally a git clone of a private data-only repo,
found through the optional `sim_notebook` preferences key (absent = SIM off).
It holds one domain (for example `harness`, or a project's own loop), declared
once by `sim.py init`.

| File | Holds |
|---|---|
| `notebook.json` | `domain`, `schema` (1) and the `thresholds` below |
| `problems.jsonl` | problem records |
| `attempts.jsonl` | attempt records and verdict records |
| `links.jsonl` | link records (observation -> problem) |
| `aliases.jsonl` | alias (merge) records |
| `sessions.jsonl` | counted-session records |
| `NOTEBOOK.md` | the rendered view; never edited by hand |

**Append-only, always.** One JSON object per line. A line, once written, is
never edited, reordered or deleted; corrections are new records. No model
ever condenses the notebook: the view's folding is deterministic code.

**Every record** carries `seq` (an integer, unique across ALL files and
increasing within each file; sim.py assigns it), `type` and `domain` (equal
to the notebook's). Verdicts and statuses are DERIVED by replaying every
record in `seq` order; nothing mutable is stored.

**Every write** (sim.py): pull fast-forward-only (a failed pull refuses the
write), validate the whole set in memory (a refused write touches nothing),
append, derive, append a verdict record for each verdict change, re-render
`NOTEBOOK.md`, and commit in the notebook repo. sim.py never pushes; the
caller pushes. Reads pull too, and warn and use the local copy if the pull
fails.

Dates are ISO: `YYYY-MM-DD`, optionally with `THH:MM[:SS]` and a zone.

## Record types

### problem

One root-cause hypothesis with a stable ID. Tags (the closed vocabulary of
`harness/templates/handback_schema.md`) name the KIND of failure; a problem
names the CAUSE, and any number of tagged observations may link to it.

| Field | Shape |
|---|---|
| `id` | `P-NNNN`, assigned in order by sim.py |
| `hypothesis` | one-line root-cause hypothesis |
| `opened` | date |
| `opened_by` | who opened it (opened only on the user's yes) |
| `project` | where it was first seen |
| `tags` | list of observation tags seen on it |

`P-0000` is reserved and created by `init`: the **unattributed** bucket. Past
changes that map to no problem are recorded as attempts on it. They are never
tracked for recurrence and render in their own compact section.

### attempt

One try at fixing a problem. Recorded whether accepted or rejected.

| Field | Shape |
|---|---|
| `id` | `<problem>/A<n>`, n counted per problem, assigned by sim.py |
| `problem` | the problem ID |
| `date` | date of the attempt |
| `model` | the model that drafted it |
| `harness_version` | optional, the harness version it was made on |
| `project` | the project (domain context) it was made in |
| `change`, `why` | what was changed and why, one line each |
| `files`, `commits` | lists of strings |
| `prediction` | optional (absent on backfill); see below |
| `review` | optional: `verdict` accept / revise / reject, `reasons`, and `override` (below) |
| `accepted` | true / false |
| `landed` | date the change landed, or null (a rejected attempt never lands) |

`landed` means the date the change reached `main`. A commit made on `main`
lands at once (its commit date). A commit on a plan or phase branch is
appended with `landed` null and lands later through a land record.

One attempt per improvement: a revise round redrafts, and only the final
draft is recorded. A reject (or a second revise, handled as one) blocks the
commit unless the user overrides it in one word. `review.override` (a
non-empty string naming who overrode and their word, e.g. `user: yes`) is
REQUIRED on an accepted attempt whose review verdict is reject or revise,
and refused anywhere else.

**Opening a problem with its attempt.** `sim.py append attempt` may carry
`"problem": "new"` plus a `new_problem` object (the problem fields above,
without `id`). sim.py opens the next `P-NNNN`, sets the attempt's and its
prediction's `problem` to it, and writes both in one commit; a refused write
touches neither. `new_problem` is not stored on the attempt.

### prediction (inside an attempt)

Written BEFORE the edit. Predicted vs observed is evidence for the next
proposer, never a score.

| Field | Shape |
|---|---|
| `problem` | the problem ID it should stop (must equal the attempt's) |
| `signature` | a plain one-liner: what should stop being observed |
| `expect_absent_tags` | the tags it expects to stop seeing |
| `prevents` | the past observation lines it should have prevented |
| `at_risk` | areas it might break |

### land (in attempts.jsonl)

`attempt`, `date` (when the merge reached main), optional `ref` (the branch
it reached). Sets the landing date of an accepted attempt appended with
`landed` null; `sim.py land --repo R --ref REF` appends one for each such
attempt whose commits are all ancestors of REF. Refused for an unknown or
rejected attempt, one already landed (by its own field or an earlier land
record), and a date before the attempt's.

### verdict (in attempts.jsonl; written by sim.py only)

`attempt`, `state` (`held` or `recurred`), `date`, `cause_seq` (the session or
link record that caused it). The visible log of each derived verdict change;
validate fails if the log and the derivation disagree.

### link

An observation confirmed as belonging to a problem.

| Field | Shape |
|---|---|
| `observation` | `project`, `ref` (file and line, e.g. `docs/observations.md:L78`), `date` (when it was observed) |
| `problem` | the problem the user confirmed |
| `proposed` | what was proposed: a problem ID, or `new` |
| `proposed_by` | who proposed it (a session may only suggest) |
| `verdict` | `accepted` (proposed = problem) or `changed` (they differ) |
| `date` | date of the user's verdict |
| `opened_problem` | set by sim.py only: true when the problem was opened with this link |

**Opening a problem with its link.** `sim.py append link` may carry
`"problem": "new"` plus a `new_problem` object, exactly as an attempt can:
one write opens the next `P-NNNN` and the link. A `new` proposal the user
accepted is then `verdict: accepted` (sim.py sets `opened_problem`); a user
who picked a different problem than the one proposed is `changed`.

### alias

A merge: `alias` (problem ID) is the same root cause as `of`. Fields `alias`,
`of`, `reason`, `date`, `approved_by` (each merge needs the user's yes). Both
IDs keep their history; the view shows them as one entry. No cycles, no
alias of `P-0000`, a problem is an alias at most once.

### session

One counted session: `key` (`<project>/<plan>/<NN>`), `project`, `plan`,
`session`, `kind` (`implement` or `grill`), `started` (date). Appended by
`sim.py verdict` at handback ingest; a key already counted is a no-op. Only
dispatched orchestrated sessions in SIM-enabled projects are counted;
standalone sessions never are.

## Attempt states and the verdict rule

| State | Meaning |
|---|---|
| `rejected` | `accepted` false; never observed |
| `accepted, not landed` | accepted, `landed` null, no land record yet |
| `under observation` | landed; replaces "fixed at commit" |
| `recurred` | a link to its problem (through aliases) was confirmed while it was under observation, for an observation dated after landing; set at once |
| `held` | `hold_after` counted sessions started after landing, with no recurrence |
| `unattributed` | an attempt on `P-0000`; never tracked |

`held` and `recurred` are final for that attempt; a held verdict is never
flipped. A link confirmed after an attempt is held REOPENS its problem; a new
attempt is expected.

## Problem statuses

Derived from the problem's latest landed accepted attempt (aliases merged):
`open` (none yet), `under observation`, `recurred` (a new attempt is
expected), `held`, `reopened` (a link confirmed after held), `held (folded)`
(held for `fold_after` further counted sessions; one line in the view), and
`merged into P-NNNN` for an alias.

## Thresholds (`notebook.json`)

| Key | Default | Meaning |
|---|---|---|
| `hold_after` | 10 | counted sessions to `held` |
| `fold_after` | 30 | counted sessions after `held` before the view folds the problem |
| `agreement_last` | 30 | links in the agreement window |
| `agreement_threshold` | 0.9 | accepted share that meets the bar |

Set at `init`; a notebook keeps its own rule.

## Reading and locating

- `sim.py history --problem P-NNNN` prints one problem's whole entry
  (aliases merged), exactly as it appears in `NOTEBOOK.md`.
- `sim.py locate --preferences <file>` reads the `sim_notebook` key and
  prints the one fallback line: exit 0 `on at <path> (domain X)`, exit 3
  `off (no sim_notebook key)`, exit 4 `configured at <path> but missing`
  (path absent, not a git repo, or no usable `notebook.json`). It never
  blocks.

## The link-agreement metric

`sim.py agreement`: the share of the last `agreement_last` links whose
verdict is `accepted`. It is met only when the window is full and the share
reaches `agreement_threshold`. It is evidence for the user's decision to let
linking go automatic, never a switch by itself.
