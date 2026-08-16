# Template: Handback Schema

Single source of truth for the report an orchestrated session writes back to
the orchestrator. Written by the dispatched session; read and ingested by the
orchestrator; its shape is checked deterministically by the closing hook. No
command restates this schema inline.

A handback is the ONLY channel by which a dispatched session returns anything
durable. The session never writes the plan's state file -- there is exactly one
writer for that file, and it is the orchestrator
(`harness/templates/state_schema.md`).

## File location

`docs/orchestration/<plan_name>/handbacks/<NN>.md`

`<NN>` is the dispatched session number, zero-padded to two digits, taken from
the orchestrator's dispatch record. Session numbers are monotonic and never
reused, so a handback path is never reused either.

`<plan_name>` is the plan slug, normalized exactly once per the branch-model
section of `harness/procedures/git_strategy.md`.

## Written at session START, not at session end

The handback file is CREATED AS A STUB the moment the session reads its prompt,
before any work begins. The stub carries `Status: OPEN` and the read receipt
(below). The session then advances it in place as the work progresses and
finalizes it at close.

This ordering is deliberate and is not negotiable: a file written only at the
end is absent when a session dies, and an absent file is indistinguishable from
a session that was never dispatched. See "The three legible terminal states".

## The read receipt

The stub carries, under the header `**Handed to this session (read
receipt):**`, exactly TWO lines derived from the dispatched prompt:

```
- Rows: E006, E007, E043
- Prompt-SHA256: <64 lowercase hex digits>
```

- `- Rows:` is the comma-separated list of E-IDs from the FIRST CELL of each
  row in the prompt's "Rows this session must obey" block.
- `- Prompt-SHA256:` is the SHA-256 digest over the EXACT BYTES of the
  dispatched prompt file -- the file the session was invoked with -- as one
  `sha256sum <prompt file>` call produces it. That same digest was recorded
  at dispatch time in the dispatch manifest
  (`docs/orchestration/<plan_name>/dispatches/<NN>.json`, written by
  `harness/scripts/assemble_dispatch.py` in the same run that wrote the
  prompt, so manifest and prompt match by construction).

This is a READ RECEIPT. Its value is timing: it catches a session that never
registered its isolation clauses IN MINUTE ONE, while the session can still
be corrected, rather than in a post-mortem after the clause was already
breached. `hooks/enforce_handback.py` VERIFIES the receipt against the
dispatch manifest -- row-ID set equality plus case-insensitive hash equality
-- on every Stop evaluation except an ABANDONED close, question pauses
included, and also offers the same verification manually as
`--check-receipt <handback> [--manifest <path>]`. When NO manifest exists at
the conventional path, the hook skips verification (the manifest is the
orchestrator's artifact; a session cannot legitimately create it), while the
manual mode fails loudly -- its caller is the orchestrator, the manifest's
owner.

Because the receipt carries no content of its own -- it is derivable
entirely from the dispatched prompt -- the orchestrator's ingest (Step 9 of
`commands/orchestrator.md`, the "Never read back the read receipt" law)
deliberately does NOT read it back; verification is the hook's job, never
the ingest's. Any change that repurposes the receipt to carry content must
update both files in lockstep.

The retired v5 shape -- a verbatim echo of every handed row, ~11 KB per
handback -- proved only that the session could copy text and was never
actually verified. The ID-plus-hash receipt is both cheaper and the first
shape a hook can CHECK.

## Structure

Exactly FOUR parts, in this order.

```
Status: OPEN | PARTIAL | ABANDONED | COMPLETE

**Handed to this session (read receipt):**
- Rows: <comma-separated row E-IDs from the prompt's orchestration block>
- Prompt-SHA256: <sha256 of the dispatched prompt file, lowercase hex>

## Delta
[rows to add / change / retire, written in the state file's exact table format]

## For the next session
[the departing session's judgement: posture, gate, deltas -- ADVISORY]

## Structural observations
[closed vocabulary, or "none"]
```

Part one is the header: the `Status` line plus the read receipt. Parts two
through four are the three `##` sections. There is no fifth part and no
optional section.

### `Status` -- closed vocabulary

| Value | Meaning |
|---|---|
| `OPEN` | The stub, never advanced. |
| `PARTIAL` | Real work landed; the dispatched scope was not finished. |
| `ABANDONED` | The session stopped deliberately without completing the work. |
| `COMPLETE` | The dispatched scope was finished. |

All four are the FILE-level vocabulary, but only `PARTIAL`, `ABANDONED` and
`COMPLETE` are TERMINAL states: `OPEN` is the stub written at session start,
it is not a state a live session may close in, and the enforcing Stop hook
blocks a closing turn still carrying it. A session that reaches its Stop hook
is by definition alive, and `OPEN` is reserved as positive evidence that a
session DIED (see "The three legible terminal states"); accepting it would
make the hook vacuous, since it would demand a file the session already wrote
in minute one.

### `## Delta`

The rows the orchestrator should add to, change in, or retire from the state
file's `## Established` and `## Open` tables.

They are written PRE-FORMATTED, in the state file's own table shape, with the
same columns and the same closed vocabularies. Mark each row's intent
explicitly -- add, change, or retire -- with the marker-block grammar below;
a change or retire names the existing row by its E-ID (quote enough of its
text as well where that helps a human reader).

**The ID cell on an `add` row is written as `-`.** The `## Established` ID
counter lives in the state file's `## Orchestrator log` and belongs to the
orchestrator alone; a session inventing a concrete ID would be guessing
another plan-writer's counter. The orchestrator stamps the real ID at ingest.

Pre-formatting is what makes ingestion MECHANICAL rather than interpretive. The
orchestrator appends rows it does not have to author, so each fact is written
ONCE, in final form, by the session that actually knows it. A session that
hands back prose forces the orchestrator to author the row from a summary --
which is a second author, a second chance to get it wrong, and a second copy to
drift. It is also what keeps ingestion nearly free in the orchestrator's
context, which is what lets an orchestrated plan run for months.

Write `none` if the session established nothing.

**The marker-block grammar (schema v2 -- machine-ingested).** The section is
applied mechanically by `harness/scripts/ingest_handback.py` (the
orchestrator's pen; see Step 9 of `commands/orchestrator.md`), so intent is
marked in this exact shape:

- A line whose FIRST WORD is `ADD`, `CHANGE` or `RETIRE` (case-insensitive)
  opens a block; everything after the first word is free annotation. A block's
  rows are the table lines under it, up to the next marker line.
- ADD rows carry the literal `-` placeholder in the ID cell (`| - | ... |`).
  The orchestrator's counter stamps the real ID at ingest; a session never
  invents its own.
- CHANGE rows carry the existing row's E-ID and are FULL replacement rows --
  the whole row as it should now read, same five cells, same ID.
- RETIRE names its E-IDs on the marker line BEFORE the colon --
  `RETIRE (E012, E015): <reason>` -- and takes no table rows. IDs mentioned
  after the colon (in the reason) are never read. Retirement is HARD-DELETE:
  the row line is removed from state, the ID is never reused, and this
  handback is the durable trail of what the retired row said.
- `## Open` proposals go under a marker line starting exactly
  `OPEN (orchestrator-manual):`, still pre-formatted in the Open table's
  shape. The script counts these rows in its summary and NEVER applies them
  -- `## Open` is orchestrator-manual, always.
- Anything else in the section -- an unmarked table row, a prose paragraph, a
  row the script cannot apply unambiguously -- FAILS the ingest closed, with
  the state file untouched.

Handbacks written before this grammar (pre-v2, quoting target rows by text
rather than E-ID) remain valid historical records: they were ingested by hand
and are never re-fed to the script.

### `## For the next session`

The departing session's judgement, handed forward: recommended posture, a gate
it thinks should fire, deltas it suspects but could not confirm.

This section is ADVISORY. Nothing in it binds the orchestrator or the next
session, and nothing in it is ingested into the state file without the
orchestrator's own decision. It is explicitly the place for the judgement that
does NOT meet the bar for an `## Established` row -- which is why the section
exists rather than pushing everything through `## Delta`.

### `## Structural observations`

Defects in the WORKFLOW MACHINERY that this session ran under -- never defects
in the project's domain logic, and never plan-specific notes.

Closed vocabulary. Each observation is one line in the exact machine shape
`- <tag> | <description>` -- dash, tag, pipe, short free-text description.
`harness/scripts/ingest_handback.py` fails closed on any other line shape;
edit the two in lockstep.

| Tag | Means |
|---|---|
| `prompt-underspecified` | The dispatched prompt did not carry enough to do the work. |
| `session-split` | The dispatched scope should have been two sessions. |
| `gate-leaked` | A gate was passed without the approval it required. |
| `greenlist-wrong` | A do-not-re-validate entry turned out not to hold. |
| `invariant-moved` | A pinned invariant is no longer true. |
| `handback-thin` | An earlier handback did not carry what this session needed. |
| `isolation-breached` | The session wrote, or nearly wrote, outside its allowed paths. |
| `other` | Anything else -- REQUIRES one free-text line saying what. |

Write `none` when there is nothing to report. Do not fabricate an observation
to fill the section.

`other` is deliberately part of the vocabulary and is how the vocabulary grows:
a tag that recurs as `other` across the observations file is the evidence an
improve session uses to propose a new named tag. The list is not frozen at what
was guessed when it was written.

## `docs/observations.md`

Structural observations accumulate in ONE project-level file,
`docs/observations.md`. It is APPEND-ONLY: entries are added at the end and
never edited, reordered or deleted. Dispositioning an entry is itself an
append, not an edit.

Two writers append to it:

1. orchestrated handback ingestion -- the orchestrator copies each observation
   line across when it ingests a handback;
2. a standalone quick-lane close -- a single appended line at the end of the
   run.

One line per observation, in this fixed shape, so the file stays greppable:

```
YYYY-MM-DD | <plan_name> | <NN or ->  | <tag> | <one-line description>
```

The improve path reads this file and counts occurrences of a tag MECHANICALLY,
across the WHOLE file -- the same defect appearing in two unrelated plans is
stronger evidence of a pattern than the same defect twice in one plan. The
fixed line shape exists to make that count mechanical rather than a judgement
call, which is what keeps the loop cheap.

## The three legible terminal states

Three distinguishable end states are the POINT of writing the stub early:

1. **`OPEN` on a stub that was never advanced** is POSITIVE EVIDENCE that the
   session died -- it was dispatched, it read its prompt, and it never came
   back.
2. **`PARTIAL` or `ABANDONED`** is an honest early exit, with whatever real
   work landed captured in `## Delta`.
3. **`COMPLETE`** is a real close.

A design that writes the handback only at the end cannot achieve this: a dead
session and a never-dispatched session both leave no file, so the failure is
invisible. Writing early is what makes a stale stub distinguishable from a real
report.

## The abandon path -- BINDING CONSTRAINT

This is a constraint on the implementation, not a statement of intent.

**The abandon path must cost about THREE LINES: the `Status` field and one
sentence.** A session that decides to stop must be able to close honestly at
that price -- nothing else required, no `## Delta` rows, no advisory section, no
observation:

```
Status: ABANDONED

Blocked on the staging credentials; nothing was changed.
```

**The enforcing hook's block message must state, VERBATIM, the minimal content
that unblocks it** -- the exact text above, not a description of it and not a
pointer to this file. A session that is blocked has by definition already
failed to guess the required shape; telling it to go read a schema is telling
it to guess again.

If the escape hatch cannot be kept this cheap, the enforcement has degraded
into ceremony and the design is wrong. An expensive escape hatch does not
produce better handbacks -- it produces sessions that abandon silently, which
is the exact failure the three legible terminal states exist to eliminate.
Treat any change that raises this cost as a defect in the change, not as a
tightening of the standard.

## What the handback replaces

For an orchestrated session the handback REPLACES the canonical end-of-phase
apparatus ENTIRELY:

- NO phase-closing marker,
- NO per-phase learnings file,
- NO ledger merge and no `Last merged` stamp.

The handback is the session's whole durable output. The canonical closing
sequence and its ledger enforcement are untouched and continue to serve
canonical multi-phase plans unchanged.
