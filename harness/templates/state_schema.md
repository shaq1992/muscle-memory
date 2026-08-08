# Template: Orchestration State Schema

Single source of truth for the structure of an orchestrated plan's state file.
Written and maintained by the orchestrator command; read by every session the
orchestrator dispatches. No command restates this schema inline.

An orchestrated plan is a long-running plan whose later steps are not knowable
in advance, that pivots mid-flight, and that runs across many sessions. It has
exactly ONE document: this state file. There is no PRD, no multi-phase plan, no
learnings ledger and no per-phase learnings file.

The reason the file exists at all: conversation context is a cache, and a cache
can be silently dropped or corrupted by compaction. The file is the memory of
record. Every decision is written through to it BEFORE the orchestrator replies,
so a fresh session with zero conversation history can resume correctly from the
file alone.

## File location

`docs/orchestration/<plan_name>_state.md`

`<plan_name>` is the plan slug, normalized exactly once per the branch-model
section of `harness/procedures/git_strategy.md`.

The file is gitignored, exactly like every other `docs/` artifact. No preference
key ships to make it tracked and no tracking option is offered. State the
consequence plainly rather than hiding it: the single source of truth for a
plan that may run for months is untracked and unbacked. That is an accepted
trade, not an oversight.

## The one-writer rule

Exactly ONE writer: the orchestrator.

- Sub-agents NEVER write the state file.
- Implementation sessions NEVER write the state file. They write handbacks
  (`harness/templates/handback_schema.md`), which the orchestrator ingests.

One writer is what makes it structurally hard for two live documents to
disagree. A second writer reintroduces exactly the drift this design removes.

## What the state file subsumes

For an orchestrated plan, the state file REPLACES, in full:

- the PRD,
- the multi-phase plan,
- the learnings ledger,
- the per-phase learnings files.

The canonical apparatus is untouched and continues to serve canonical
multi-phase plans: the ledger, its Stop-hook enforcement and the closing
sequence all behave exactly as before, and the prompt-writer command still
reads the ledger and only the ledger for accumulated learnings. Nothing in this
schema changes how a canonical plan closes.

## Structure

The file has exactly SIX sections, in this fixed order. No section is optional
and none may be reordered -- a resuming session reads positionally.

```
# Orchestration State: <plan_name>

Status: ACTIVE | COMPLETE | ABANDONED

## Objective
## Established
## Open
## Next
## Maybe
## Dispatched
```

### `## Objective`

The objective, plus its ACCEPTANCE CRITERIA, written before looking at any
result. Stating criteria up front is the whole point of the section: a
criterion authored after a result is available can be fitted to that result,
and then the plan can never fail. Once written, a criterion is changed only by
an explicit, recorded decision -- never quietly reworded to match what was
found.

### `## Established`

ONE table. These columns, in this order:

| Statement | Provenance | Disposition | Revisit trigger |

This single table replaces six lists that would otherwise be maintained
separately -- pinned invariants, the do-not-re-validate green list, traps
carried forward, limitations to carry rather than fix, established facts, and
settled decisions. They differ only in what the reader should DO with the
entry, which is precisely what the `Disposition` column records. Six lists in
one file are six chances for two of them to disagree; one table makes a
contradiction visible at a glance.

**Provenance -- closed vocabulary.** One of:

| Value | Meaning |
|---|---|
| `measured` | Observed directly, with a number or an artifact behind it. |
| `inferred` | Derived from something measured, not itself observed. |
| `reported` | Stated by a person or a document; not independently checked. |
| `assumed` | Taken as true to make progress; nothing behind it yet. |

**Disposition -- closed vocabulary.** One of:

| Value | Meaning | What the reader does |
|---|---|---|
| `fact` | Something known to be true. | Use it. |
| `invariant` | Something that must remain true. | Do not break it; do not re-derive it. |
| `settled` | A decision already taken. | Do not re-open it. |
| `avoid` | A trap already walked into. | Do not repeat it. |
| `carry` | A limitation accepted rather than fixed. | Work around it; do not "fix" it. |
| `gate` | A mandatory stop. | STOP and obtain approval before proceeding. |

The mapping from the six collapsed lists: `avoid` is what a trap becomes;
`carry` is what a limitation-to-carry-not-fix becomes; `settled` together with
`invariant` is what the do-not-re-validate green list becomes; `fact` is an
established fact; `gate` is a mandatory stop.

Neither vocabulary is open. A statement that fits none of these values is a
signal that the statement is not yet clear enough to pin, not a signal to
invent a seventh value.

**When provenance is required, and when it is `-`.**

- REQUIRED for `fact`, `invariant`, `settled` and `avoid` -- the dispositions
  where truth is at stake.
- Written as `-` for `gate` and `carry` -- the two policy dispositions.

The rationale, recorded here so it is not re-litigated: the provenance
vocabulary grades HOW WRONG a statement could be. A policy cannot be wrong; it
can only be revoked. Grading a policy on a truth scale would be a category
error, and the thing a reader actually needs to know about a policy -- what
would end it -- is already carried by the `Revisit trigger` column.

**Gates name their approver in the statement text.** When the approver is
someone other than the user, the statement says so in prose (for example,
"... requires Legal's sign-off before ..."). There is no approver column: an
approver is only ever needed for one disposition, and a column that is empty on
five rows out of six is noise on every one of them.

**Revisit trigger.** The condition under which the row should be re-examined.
Write a condition, not a date: "if the vendor changes the rate limit", not
"in two weeks". A row with no plausible trigger takes `-`.

**Worked examples.** One row per disposition, showing the intended shape:

| Statement | Provenance | Disposition | Revisit trigger |
|---|---|---|---|
| The nightly export completes in 6-8 minutes on the current dataset. | `measured` | `fact` | If the dataset grows past ~2x its current size. |
| Every write path stays idempotent; a replayed message must never double-apply. | `inferred` | `invariant` | - |
| Batch size fixed at 500; larger batches were rejected for tail-latency reasons. | `measured` | `settled` | If the tail-latency budget is renegotiated. |
| Do not call the search endpoint inside the per-item loop -- it silently truncates at 100 and the earlier attempt lost rows without erroring. | `measured` | `avoid` | If the vendor publishes pagination on that endpoint. |
| The upstream feed has no delete events, so removals are invisible; reconcile on the weekly full snapshot instead of fixing this. | `reported` | `carry` | - |
| Any schema change to the shared events table requires the platform team's sign-off before it is written. | - | `gate` | If ownership of that table moves. |

**No-contradiction law.** `## Established` may NEVER hold two rows that
contradict each other on the same subject. This law is carried over unchanged
from the canonical learnings ledger, and it is the reason a single table was
chosen over six lists.

When two rows clash:

1. The weaker provenance loses, without a conversation. The precedence order is
   `measured` > `inferred` > `reported` > `assumed`. Delete the losing row and
   keep the winner; do not keep both and do not annotate the loser as
   superseded.
2. Where the clash is AMBIGUOUS -- the rows conflict and it is not certain the
   new row FULLY replaces the old one -- STOP and ask the user. Never silently
   resolve it. The table may not keep both rows, and it may not silently lose a
   load-bearing one, so an ambiguous clash is a decision the user makes.

### `## Open`

The uncertainty register. A table with these columns:

| Question | Blocks | Cost to resolve | Who can resolve | Status |

- **Question** -- the open uncertainty, stated as something answerable.
- **Blocks** -- what cannot proceed until it is answered.
- **Cost to resolve** -- a rough sense of the effort or spend involved.
- **Who can resolve** -- the user, a named person or team, a session, or a
  sub-agent investigation.
- **Status** -- where the question currently stands.

This register replaces the phase list. Sessions are DERIVED from open
questions at the moment of dispatch, rather than pre-listed at plan time --
which is the whole reason an orchestrated plan can pivot without amending a
document.

`Cost to resolve` is INFORMATION THE USER READS when choosing what happens
next. NOTHING fires on it. No threshold, no automatic ordering, no gate, no
rule anywhere in the harness reads that column. It is stated here explicitly so
that no future reader mistakes it for a control input.

### `## Next`

Exactly ONE fully-specified next session: the committed horizon.

"Fully specified" means a session could be dispatched from it without further
conversation -- what it does, what it must not touch, and what it hands back.
One entry, not a queue: a queue of "next" items is a phase list wearing a
different hat, and the plan then cannot pivot without amending it.

### `## Maybe`

At most FIVE one-line candidates. Each carries its triggering condition -- the
thing that would have to become true for the candidate to matter.

- Every entry is explicitly marked as a GUESS.
- Every entry is deletable without ceremony: no supersession note, no dated
  trail, no approval.
- The cap of five is a schema rule, not a suggestion.

**Standing instruction: delete rather than curate.** When a sixth candidate
arrives, delete the weakest of the five rather than reorganizing, grouping or
promoting anything. The reason the cap exists, recorded so nobody relaxes it
later: uncapped, this provisional horizon silently becomes the phase list that
was just removed -- unnumbered, unratified, and carrying all the same drift
without any of the review the phase list at least received.

### `## Dispatched`

The outstanding handback expectations. One row per dispatched session:

| Session | Prompt path | Handback path | Status |

The orchestrator writes the expectation AT the moment of dispatch, before the
session runs. That ordering is the point: a session that is never run at all is
still visible on a cold resume, as a dispatched row with no handback behind it.
An expectation written only on return would leave a silently-dropped session
invisible forever.

Session numbers are monotonic and never reused, across the whole life of the
plan -- including for sessions that were abandoned or never run. Reusing a
number collides two sessions onto one handback path.

## Terminal status

The header `Status:` line takes `ACTIVE` for the life of the plan. When the
plan ends it takes a terminal value -- `COMPLETE` when the objective's
acceptance criteria are met, `ABANDONED` when the plan is stopped without
meeting them -- and the reason is recorded in `## Objective`.

An orchestrator resumed against a terminal state file reports the terminal
status and STOPS. It does not derive a next session and it does not dispatch.
Without this, a resumed orchestrator re-dispatches against finished work.
