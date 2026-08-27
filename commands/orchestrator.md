---
description: Drive a long-running, progressively-disclosed plan from a single durable state file. The same invocation initialises a new plan or resumes an existing one, writes state through before replying, dispatches one session at a time on the user's word, and ingests each session's handback. `improve` is a reserved first token that routes accumulated structural observations into the existing self-improvement flow.
argument-hint: <plan_name> [additional text] -- or `improve` (reserved word, runs a structural improvement pass instead)
---

Orchestrate the plan named in $ARGUMENTS.

This command serves the plan shape the canonical arc handles poorly: work whose
later steps are not knowable in advance, that pivots mid-flight, and that runs
across many sessions. It is not a replacement for the canonical arc -- a plan
that can genuinely be specified up front should still be run as a PRD plus a
multi-phase plan, which is the only path that produces a stakeholder-readable
spec.

An orchestrated plan has exactly ONE document: its state file. The structure of
that file, everything it subsumes, and the one-writer rule are defined in
@.claude/harness/templates/state_schema.md -- read it before touching state and
never restate it here or in a dispatched prompt.

The reason the file exists: conversation context is a cache, and a cache can be
silently dropped or corrupted by compaction. Anything held only in the
conversation is already lost. Write it down first, then reply.

## Step 1 -- Parse arguments

`$ARGUMENTS` is a plan name followed by optional additional text.

1. **Reserved words.** The FIRST token is checked against the reserved list
   before anything else. The reserved list is exactly: `improve`. If the first
   token is `improve`, this invocation is the improve subcommand (Step 11) and
   nothing in Steps 2-10 runs. Because the list is declared, a plan can never be
   named one of these words: if a user asks to initialise a plan whose
   normalized slug is a reserved word, refuse, say which word collided, and ask
   for a different name.
2. **plan_name** -- the first token, normalized per the "Slug normalization"
   rule in the branch-model section of
   @.claude/harness/procedures/git_strategy.md. That rule is the single source
   for slug shape and for the one-line notice that states the normalized value;
   it is not restated here.
3. **additional text** -- everything after the first token. What it means
   depends on whether this is an init or a resume (Steps 3 and 4).

If no plan name is given, stop and say:
"Usage: /orchestrator <plan_name> [additional text], or /orchestrator improve".

## Step 2 -- Detect init vs resume, and write the session marker

The state file lives at the path given by
@.claude/harness/templates/state_schema.md. Check whether it exists:

- **absent** -> this is an INIT (Step 3);
- **present** -> this is a RESUME (Step 4).

There is no `init` subcommand and no `resume` subcommand. The file on disk is
the only signal, so the user never has to remember which mode they are in.

Then write the orchestrator session marker, at init and at resume alike. The
marker is PER-PLAN: its filename carries the plan slug, so concurrent
orchestrators on DIFFERENT plans each hold their own marker and neither can
overwrite -- and thereby silently disarm -- the other's guardrail.

**Same-plan refusal first.** Before writing, read
`.claude/orchestrator_<plan_name>_session.json` if it exists. If its
`session_id` is not this session's, REFUSE to orchestrate this plan: say that
another orchestrator session holds it, and name the marker path so the user
can delete the file if that orchestrator is dead. The refusal is the WHOLE
mechanism -- there is no staleness heuristic and no automatic cleanup, by
decision: only the user can tell a dead orchestrator from one that is merely
quiet, so eviction is only ever the user's deletion of the named file.
Concurrent orchestrators on DIFFERENT plans are the supported case; what
their dispatched sessions may hold is still governed by the tree broker
(Step 8).

Otherwise get the session id by running `echo $CLAUDE_CODE_SESSION_ID` (Bash
tool) -- do not guess or invent a value -- and write
`.claude/orchestrator_<plan_name>_session.json` with exactly these keys:

```json
{
  "session_id": "<value of $CLAUDE_CODE_SESSION_ID>",
  "plan_name": "<plan_name>",
  "state_path": "<the state file path>"
}
```

Write the marker unconditionally, even if unsure whether the enforcing hook is
registered -- the marker is inert without it. Remove the marker when this
session's orchestration work is done. The enforcing hook
(`hooks/enforce_orchestrator_isolation.py`) scans ALL
`orchestrator_*_session.json` markers and matches on session_id, and it is
FAIL-CLOSED on a corrupt marker file: while one exists, every guarded write is
denied with the corrupt path named, and deleting that file -- the user's call
-- is the remedy.

**Cutover note.** Per-plan markers became the law at the v6 plan-end merge;
until that merge, orchestrators wrote the single-slot
`.claude/orchestrator_session.json`. That legacy filename does not match the
hook's scan pattern and is INERT. On the first resume that finds one left over
from before the cutover, delete it as housekeeping and record the deletion in
`## Orchestrator log`.

## Step 3 -- INIT (no state file exists)

Ask a short grilling, HARD-CAPPED at FIVE questions, targeting exactly four
things:

1. the objective;
2. its acceptance criteria;
3. any pinned invariants and gates already known;
4. the first committed session.

Those four are the targets because they are the only fields with no other
source. Acceptance criteria in particular cannot be recovered later: once a
result is visible, a criterion can no longer be stated without being fitted to
it, and a plan whose criteria are fitted to its results can never fail.

**The cap is a ceiling, not a quota.** Stop asking the moment those four are
pinned. One question is a fine init. Asking a fifth question because four have
been asked is the failure this sentence exists to prevent.

Then write the state file per @.claude/harness/templates/state_schema.md, before
replying:

- `## Objective` carries the objective and the acceptance criteria as stated.
- `## Established` starts NEARLY EMPTY -- only the invariants and gates the user
  actually named. Do not seed it with plausible-sounding rows.
- `## Open` is seeded ONLY from uncertainties the five questions surfaced. It is
  not a phase list under another name.
- `## Next` carries the one committed session, fully specified.
- `## Maybe` may be empty, and usually should be at init.
- `## Dispatched` is empty until the first dispatch.
- `## Orchestrator log` seeds its two required lines: `- Incarnations: 1` and
  `- Next row ID: E001`.

Initialising the plan does not create any branch. The integration branch is cut
by the plan's first work unit under the per-work-unit flow in
@.claude/harness/procedures/git_strategy.md; the orchestrator's only git actions
are the plan-end push and pull request in Step 12.

## Step 4 -- RESUME (a state file exists)

Read the state file and resume from IT ALONE. Nothing else is recovered
context. Rebirth is state-file-only: there is no successor-prompt artifact,
and hand-written orchestrator resume prompts are a retired practice. As the
first state edit of the resume, bump the incarnation count in
`## Orchestrator log`.

- Any additional text in the invocation is NEW INPUT -- a new instruction, a new
  constraint, a new correction. It is never treated as context handed forward
  from a previous session. This is what frees an outgoing session from having to
  remember anything for the incoming one.
- There is no summary ritual, no validator script and no schema test on this
  path. Resume is meant to be light and rare; attaching ceremony to it would
  make the cheap path expensive and push sessions toward not resuming at all.
- If the header `Status:` -- the PLAN-level status of the state file, owned by
  @.claude/harness/templates/state_schema.md -- is terminal, follow that file's
  terminal-status rule: report it and stop.

If the state file is missing a section, is out of order, or contradicts itself,
say so plainly and fix it as a state edit before doing anything else. Do not
work around a malformed state file.

## Step 5 -- WRITE-THROUGH (the load-bearing rule)

State is written BEFORE replying, on these five triggers:

- **(a)** a handback is ingested;
- **(b)** a dispatch is issued;
- **(c)** an entry is added to, or resolved in, `## Open`;
- **(d)** a decision is made;
- **(e)** **the user states a preference, a constraint or a correction.**

**Trigger (e) is the load-bearing one.** A preference the user states in
conversation and the orchestrator merely holds in context is exactly what a
compaction silently corrupts: the orchestrator continues confidently, with a
value nobody chose, and nothing on disk shows the swap. When the user says how
they want something done, that goes into the file before the acknowledgement is
typed.

Two further rules on every write:

- **Row-level edits only.** Edit the affected rows or lines. NEVER rewrite the
  document. A rewrite makes every row a fresh authorship event and lets an
  unrelated row change silently; a row edit bounds the blast radius of a bad
  write, which matters because the file is untracked.
- **Conversational turns write nothing.** A turn that answers a question,
  explains state, or thinks out loud is not a trigger. Only the five above are.

## Step 6 -- NEVER DISPATCH UNBIDDEN

The orchestrator NEVER dispatches a session on its own initiative. Every
dispatch is the user's word.

Progressive disclosure means the plan is not specified in advance. It does not
mean sequencing is handed to the machine. The orchestrator may propose what
looks like the strongest next session, and should when asked; the user decides
whether it happens.

## Step 7 -- DISPATCH

Runs only on the user's instruction (Step 6), and only after the tree broker in
Step 8 clears.

1. **Number the session.** Take the next number after the highest ever recorded
   in `## Dispatched`. Numbers are monotonic and NEVER reused -- including for
   sessions that were abandoned or never run -- because a reused number collides
   two sessions onto one set of artifact paths. Zero-pad to two digits.
2. **Resolve the prompt path.** DERIVE the dated directory with a Bash command
   AT EACH dispatch -- never type the date token by hand and never reuse a value
   from an earlier dispatch, session or turn. Interpolate `$(date +%d%m%y)`
   directly in the same invocation that creates the directory and writes the
   file, so the date is resolved fresh every time:

   ```
   mkdir -p "docs/prompts/$(date +%d%m%y)"
   # then write the prompt to
   #   docs/prompts/$(date +%d%m%y)/<plan_name>_session_<NN>_prompt.md
   ```

   The filename convention `<plan_name>_session_<NN>_prompt.md` is unchanged.
3. **Assemble the prompt with the dispatch script.** The orchestrator authors
   ONLY the task body (to a scratch file) and selects the row E-IDs this
   session must obey; `harness/scripts/assemble_dispatch.py` writes the WHOLE
   prompt file and the dispatch manifest in the same run:

   ```
   python3 .claude/harness/scripts/assemble_dispatch.py \
     --state docs/orchestration/<plan_name>_state.md \
     --body <task_body_file> --plan <plan_name> --session <NN> \
     --branch <plan_name>-session-<NN> --rows E006,E007,... \
     --out "docs/prompts/$(date +%d%m%y)/<plan_name>_session_<NN>_prompt.md"
   ```

   The script extracts the named rows VERBATIM from the state file
   (fail-closed on a missing E-ID), appends the fixed `## Orchestration`
   block below, and writes the manifest to
   `docs/orchestration/<plan_name>/dispatches/<NN>.json` -- session number,
   row IDs, and the SHA-256 of the prompt file's exact bytes, so the
   manifest matches the prompt by construction. That hash is what the
   session's read receipt is verified against
   (`harness/templates/handback_schema.md`); a prompt hand-edited after
   assembly is a different dispatch and fails verification by design, so on
   any change to the body, re-run the assembler rather than editing the
   prompt. It is deterministic-validation law: surface the script's output
   verbatim, and never dispatch on a FAIL.

   The block's presence is the ONLY signal by which a receiving command
   knows it is orchestrated, so the heading is spelled exactly this way and
   the block is never renamed, nested, or made conditional:

   ```
   ## Orchestration

   - **State file:** docs/orchestration/<plan_name>_state.md
   - **Handback:** docs/orchestration/<plan_name>/handbacks/<NN>.md
   - **Branch:** <plan_name>-session-<NN>
     (cut from integration/<plan_name>)
   - **Rows this session must obey:**
     | <verbatim row copied from the state file's Established table> |
     | ... |
   ```

   The `Branch:` field's VALUE is read VERBATIM as a branch name by the
   receiving command, so nothing but the branch name may appear in it -- which
   is why the "cut from" clause sits outside the value, on its own continuation
   line.

   The receiving command is `/grill_and_implement`: it detects the block's
   PRESENCE and switches out of its standalone quick lane into orchestrated
   mode, so a renamed heading silently drops it back into standalone, where it
   would open a pull request. What comes back is a session that worked on the
   branch the block names and merged into `integration/<plan_name>`, opening no
   pull request of its own, per the orchestrated-no-self-PR rule in the plan-end
   PR flow of @.claude/harness/procedures/git_strategy.md.

   The rows are the relevant do-not-re-validate entries, pinned invariants and
   gates, FILTERED to what this session actually touches. Filtering is the
   point: a session handed the whole table reads none of it.

   **The authored task body carries exactly ONE TDD-posture line** --
   `TDD posture: WARRANTED` or `TDD posture: OPTIONAL` -- decided by task type
   per the tests-as-deliverables rule in `.claude/preferences.md` (that rule is
   project opinion and lives there alone: reference it, never restate it). The
   stamp sets the posture ONLY; the receiving implementer derives the
   behavioral tests itself during grilling, into the quick brief's
   `## Behavioral tests` section (`commands/grill_and_implement.md` Step 2).
4. **Verbatim rows only.** Single-source is about AUTHORSHIP, not physical
   uniqueness of bytes. A row copied verbatim and unedited from state, with
   state named as its source, has ONE author and cannot drift into disagreement;
   a paraphrase has two, and two authors of one fact is how the copies come
   apart. So the prompt may carry verbatim rows and nothing else -- no
   paraphrase, no summary, no tightened wording. The assembler enforces this
   by construction: it copies each row line byte-for-byte from state, so the
   orchestrator's part is SELECTING IDs, never transcribing text.
5. **A fact in a prompt and absent from state is a BUG.** If, while writing the
   prompt, something needs saying that exists nowhere in state, stop writing the
   prompt: put it in state first, as a row, then copy that row into the prompt.
   The prompt is a view of state, never a second store.
6. **Record the expectation BEFORE the session runs.** Write the row into
   `## Dispatched` (write-through trigger (b)) as part of the dispatch, not on
   return. A session that is never run at all must still be visible on a cold
   resume as a dispatched row with no handback behind it.
7. **Report the path ONLY.** Say where the prompt was written and stop. NEVER
   echo the prompt body into the conversation -- the body is for the receiving
   session, and echoing it burns orchestrator context on text that is already on
   disk.

## Step 8 -- TREE BROKER

**ONE tree-holding session at a time.** A tree-holding session is one that
checks out a branch and edits files in the plan's repository.

A second concurrent session is permitted only when it holds no tree:

- read-only or scratchpad-only work -- investigation, drafting, analysis; or
- work in a DIFFERENT repository, such as an improve run against the harness
  repo.

While a tree-holding session is outstanding in `## Dispatched`, the orchestrator
REFUSES to dispatch a second one. The refusal is explicit: name the outstanding
session number and its handback path, and say that the second dispatch waits on
that handback. Do not silently queue it and do not dispatch it anyway with a
warning.

**Worktree opt-out.** A plan that genuinely needs parallel implementers declares
git worktrees explicitly, as a `settled` row in `## Established`. With that row
present the broker permits the parallelism the row describes. Absent the row,
the single-tree rule holds -- parallelism is never inferred from convenience.

## Step 9 -- INGEST a handback

A handback's structure and vocabularies are defined in
@.claude/harness/templates/handback_schema.md.

**What triggers an ingest.** The USER does, by saying the session came back.
There is no polling, no watching and no background work: the orchestrator has no
turn except the one the user gives it, and while a dispatched session is running
there may be no orchestrator session alive at all. The other entry point is
RESUME -- an outstanding row in `## Dispatched` is a standing instruction to look
at that handback path on disk before doing anything else, and what is found there
is the answer: a finalized handback gets ingested, a stub still at `OPEN` is
positive evidence the session died, and no file at all means the session was
never run.

**What MECHANICAL means.** It describes HOW the rows are applied, not what sets
the ingest off. The mechanical legs are EXECUTED by
`harness/scripts/ingest_handback.py` -- the orchestrator's pen under the
one-writer rule, invoked only by the orchestrator -- and the orchestrator reads
the script's ~10-line summary, never re-parsing what the script already parsed.
Nothing is interpreted, summarised or re-authored on the way through: the rows
arrive pre-formatted in the state file's own table shape (the session that did
the work is the author) and the script applies them verbatim. That is what
keeps an ingest nearly free in orchestrator context, which is what lets a plan
run for months.

**Never read back the read receipt.** When ingesting, read ONLY the script's
summary and the `## For the next session` section (sliced to by its fixed
heading) -- the script consumes `Status:`, `## Delta` and `## Structural
observations` so the orchestrator does not have to. NEVER
read the `**Handed to this session (read receipt):**` block -- it is a row-ID
list plus the dispatched prompt's hash, derivable entirely from the dispatch
the orchestrator itself issued, so it carries zero new information. Its
verification against the dispatch manifest is the CLOSING HOOK's job
(`hooks/enforce_handback.py`, minute one), never the ingest's; while the live
hook predates that check, run it manually instead --
`python3 hooks/enforce_handback.py --check-receipt <handback_path>` -- and
read only its OK/FAIL verdict. Reading the receipt back only burns
orchestrator context on text already on disk.

The whole of an ingest is these five actions. Actions 1, 3 and 4 are the
SCRIPT's -- run it once and read the summary:

```
python3 .claude/harness/scripts/ingest_handback.py \
  --state docs/orchestration/<plan_name>_state.md \
  docs/orchestration/<plan_name>/handbacks/<NN>.md
```

`--check` first is a free dry-run: same validation, same summary, nothing
written. The script is FAIL-CLOSED: on a malformed handback, or a Delta row it
cannot apply unambiguously, it exits 1 with the state file untouched --
surface its FAIL lines verbatim and resolve with the user, never by quietly
hand-editing the handback into an ingestable shape.

1. **`## Delta` rows go into state VERBATIM -- applied by the script.** It
   honours each marker block's stated add / change / retire intent against
   `## Established` ONLY (the block grammar is owned by
   @.claude/harness/templates/handback_schema.md); nothing is re-worded,
   tightened, merged or re-classified on the way through. On an `add` row the
   script replaces the `-` placeholder in the ID cell with the `Next row ID`
   value from `## Orchestrator log` and advances that counter in the same
   write; a `change` replaces the identified row and keeps its ID; a `retire`
   HARD-DELETES the row line -- the ID is never reused, the summary names the
   retired IDs, and the retiring handback is the durable trail. Rows under an
   `OPEN (orchestrator-manual):` marker are NOT applied: the script only
   counts them in the summary, and the orchestrator applies them to `## Open`
   by hand -- `## Open` is orchestrator-manual, always. The script also runs
   the STRUCTURAL side of the no-contradiction check: an incoming statement
   duplicating an existing row is FLAGGED in the summary, never resolved.
   Judging SEMANTIC contradiction stays the orchestrator's: on a flagged pair
   or a clash the orchestrator notices in the applied rows, apply the
   no-contradiction law from @.claude/harness/templates/state_schema.md
   rather than inventing a resolution.
2. **`## For the next session` is ADVISORY.** It informs the orchestrator's
   judgement and nothing more. Where it conflicts with state, STATE WINS. A line
   from it enters the file only as the orchestrator's own decision, under
   write-through trigger (d) -- never by transcription. This section is the one
   part of the handback the orchestrator still reads itself; the script
   deliberately never parses it.
3. **Structural observations are appended by the script** to
   `docs/observations.md`, verbatim, one line per observation in the fixed
   dated shape defined in the handback schema. Append only; never edit, reorder
   or delete an existing line.
4. **`## Dispatched` is updated by the script.** It clears the row on a
   `COMPLETE` handback; updates its status for `PARTIAL` or `ABANDONED`; leaves
   it standing, visibly outstanding, for a handback still at `OPEN`. A
   handback's `Status` is the SESSION-level vocabulary of
   @.claude/harness/templates/handback_schema.md and belongs only in that row
   -- NEVER copy it into the state file's header `Status:` line, whose
   PLAN-level vocabulary is separate even though both fields are named
   `Status`.
5. **Refill or empty `## Next`.** Once the ingested session's scope is finished,
   the committed horizon is STALE -- it now describes work that is already done.
   Either write the next committed session into it, or empty it with an explicit
   line saying the plan is awaiting the user's next call. Never leave a finished
   session sitting in `## Next`: a cold resume reads that section as what happens
   next, and would re-derive a session that has already returned. Refilling
   `## Next` is not dispatching, so it does not breach Step 6 -- but a horizon
   the user has not chosen is a proposal, and must be written as one.

The summary's last line reports `## Established`'s row count and byte size
against the GC threshold (80 rows OR 45 KB -- either bound trips). An OVER
report is the trigger EVIDENCE for suggesting a garbage-collection pass
(Step 10a); GC never auto-runs. The summary also WARNS on incoming rows over ~600 bytes per
the row-discipline law -- a prompt for judgement, never a block.

All five happen before replying (write-through trigger (a)).

## Step 10 -- The two-strikes notice

After ingesting, count occurrences of each observation tag ACROSS THE WHOLE of
`docs/observations.md` -- not just this plan's lines. The same defect showing up
in two unrelated plans is stronger evidence of a pattern than the same defect
twice in one plan.

When a tag reaches TWO occurrences, emit exactly ONE LINE: that N structural
observations are pending, and that `/orchestrator improve` may be run in a fresh
session.

**That is the entire behaviour.** The orchestrator composes no brief, spawns no
sub-agent, reviews no diff and runs no drift cascade of its own. The division of
labour is deliberate: sessions report, the orchestrator judges by mechanical
count, execution happens out of process. The orchestrator's privileged position
is POSSESSION of the evidence, not deliberation about it -- which is exactly why
the firewall costs nothing.

## Step 10a -- GARBAGE COLLECTION (user-gated; never auto-runs)

The trigger is EVIDENCE, never a schedule: the ingest summary's last line
reports `## Established` against the GC threshold (Step 9), and on an OVER
report the orchestrator emits at most ONE line suggesting a GC pass -- the
same restraint as Step 10's notice. GC itself runs only on the user's word.
(Numbered 10a so the step numbers ratified elsewhere -- Step 11 improve,
Step 12 plan end -- stay stable.)

On that word:

1. **Derive the archive path fresh** with Bash -- never a date from memory:
   `docs/orchestration/<plan_name>_state_archive_$(date +%d%m%y).md`.
2. **Invoke the garbage_collector sub-agent** (`agents/garbage_collector.md`),
   handing it the plan name, the state file path, the archive path just
   derived, and the dated archives and retained handbacks to read. The agent
   is PROPOSE-ONLY: it returns RETIRE / CONDENSE / PROMOTE batches keyed on
   E-IDs, pre-formatted in the state table shape with their
   "replaces <IDs>; archive: <path>" markers, and writes nothing outside its
   scratchpad. Its judgement rules live in its own file, per the doctrine
   that each rule lives with the actor who can violate it.
3. **Snapshot BEFORE applying.** Copy the state file VERBATIM to the archive
   path. The archive is the recoverable copy of every row a batch touches; no
   batch is applied before the snapshot exists.
4. **Gate EACH batch with the user** -- batch by batch, never one bulk okay.
   A PROMOTE batch is doubly explicit: promotion of a row to CLAUDE.md is a
   user-gated, surgical move, never bulk, and on apply the promoted row is
   RETIRED from `## Established` in the same batch so CLAUDE.md becomes the
   fact's single home. (Accepted cost, decided at session 04: the dispatch
   assembler can no longer hand that row by E-ID; dispatched sessions see it
   through CLAUDE.md instead.)
5. **Apply approved batches as row-level edits** -- the orchestrator's own pen,
   never `ingest_handback.py`, whose input is a handback. A condensed row's ID
   is stamped from the `Next row ID` counter and the counter advanced in the
   same write; replaced and retired rows are HARD-DELETED -- IDs never reused,
   the archive is the durable trail. A batch the user declines is dropped
   without residue.
6. **Record the trim** in `## Orchestrator log`: date, batches applied, archive
   path (write-through trigger (d)).

## Step 11 -- The `improve` subcommand

`/orchestrator improve` runs in a FRESH session with ZERO plan context. It never
runs inside a session that is orchestrating a plan; the point is to judge
structural proposals from a sample of many sessions rather than a sample of one,
without polluting orchestrator context.

1. **Refuse a concurrent improve run.** Read `.claude/improve_session.json` if
   present. If it exists and its `session_id` is not this session's, refuse to
   start, say another improve run is in progress, and name the marker path so
   the user can delete it if that run is dead. Otherwise write the marker with
   this session's `session_id` and a start stamp, and remove it when the run
   finishes.
2. **Never run `git checkout` or `git switch` in the harness repo during an
   improve run.** Edit files in place and commit on whatever branch is already
   checked out. The observed collision was a checkout removing files underneath
   a concurrently running session, so the banned operation is the one that
   caused the harm. This is what makes an improve run safe to execute IN
   PARALLEL with ongoing plan work -- it holds no tree in the plan's repository,
   and it never moves the harness repo's HEAD.
3. **Read `docs/observations.md` and the harness corpus** (`commands/`,
   `agents/`, `hooks/`, `harness/`) before proposing anything. Count the tags
   mechanically; look at the actual file that would change.
4. **Compose the brief and SURFACE it.** Show it to the user and gate on their
   okay before anything is edited.
5. **Invoke the EXISTING flow, unchanged.** Hand the approved items to
   @.claude/harness/procedures/self_improvement.md and follow it as written --
   per-item user approval, one file per invocation, one commit, surfacing the
   diff there, and the one-level drift cascade. This subcommand is a new CALLER
   of that procedure; it does not modify it, extend it, or substitute its own
   version of any step.
6. **Mark the handled items dispositioned** in `docs/observations.md`. That file
   is append-only, so a disposition is itself an appended line, not an edit to
   the original.

## Step 12 -- PLAN END

There is no `is_final_phase` analogue under progressive disclosure -- by
construction nothing knows in advance which session is the last. The ONLY signal
is the user's declaration that the plan is done.

On that declaration:

1. Push the integration branch and open the pull request per the plan-end PR
   flow in @.claude/harness/procedures/git_strategy.md -- including its
   active-account check and its title/body convention. Nothing about that flow
   is special-cased here.
2. Record the PR link in the state file.
3. Set the header `Status:` -- the PLAN-level status, owned by
   @.claude/harness/templates/state_schema.md -- to its terminal value per that
   schema.
4. The USER merges. The orchestrator never runs `gh pr merge`.

If the user withholds the merge, the plan still ends: the integration branch and
the open PR are its durable artifacts, and the state file still carries its
terminal status so a later resume does not re-dispatch against finished work.

## Delegating to sub-agents (caller-side rules)

These are the CALLER's obligations. The isolation law that binds the sub-agent
itself lives in the sub-agent's own definition (`.claude/agents/investigator.md`,
`.claude/agents/experimenter.md`) so that it applies whether or not the caller
remembered to state it -- hand-writing isolation clauses per call is the failure
that design replaces. There is no separate delegation procedure file; each rule
lives with the actor who can violate it.

- **What to delegate.** Work whose OUTPUT is small but whose INPUT is large:
  searching a corpus, reading long files, reproducing a defect, surveying
  options. Anything that would otherwise pull thousands of tokens of raw
  material into the orchestrator, where every later turn pays for it.
- **Which sibling.** A question answerable by READING alone -- searching,
  excerpting, reproducing from what already exists -- goes to the
  `investigator`. A question that needs code WRITTEN AND RUN (in the session
  scratchpad only) or WEB evidence goes to the `experimenter`. When in doubt,
  start with the investigator: it is the cheaper, narrower tool, and its
  empty-handed report is the evidence that the experimenter is warranted.
- **What NOT to delegate.** Decisions, dispatch, and any write to the state
  file. The orchestrator's job is to decide and to record; a sub-agent's job is
  to find out.
- **Hard output budget.** State a maximum output size in every call and keep it
  small -- findings and their evidence, not transcripts. A sub-agent that
  returns everything it read has moved the context problem rather than solved
  it.
- **Findings land in state BEFORE the orchestrator replies.** A finding that
  exists only in the sub-agent's returned text is in the cache, not the memory
  of record -- the same failure the state file exists to prevent, arriving by a
  different door.
- **One writer.** Sub-agents NEVER write the state file, per the one-writer rule
  in @.claude/harness/templates/state_schema.md. Two writers on the single
  source of truth would mean the orchestrator can no longer trust the file to
  reflect its own decisions.

## What this command does NOT do

- **It emits no PRD, and ships no render subcommand.** A section kept current
  for a reader who is usually absent is write-only ceremony. When a plan needs a
  stakeholder-readable spec, that is what the canonical arc is for.
- **The Edit/Write allowlist is an ANTI-DRIFT GUARDRAIL, not a sandbox.** While
  the orchestrator session marker is in place, a hook blocks Edit / Write /
  NotebookEdit outside the state file, `docs/orchestration/`, `docs/prompts/`,
  the session scratchpad, and two exact-file allowances -- the project-root
  CLAUDE.md (the GC PROMOTE target) and the user-global `~/.claude/CLAUDE.md`
  (user-ordered global-law additions). Say plainly what that is worth: a Bash heredoc
  bypasses it entirely, and so does any other write that does not go through
  those tools. It exists to catch the orchestrator drifting into doing the
  implementation work itself, which is a mistake made by accident. It stops
  nothing done on purpose, and no reader should be left thinking otherwise.
- **It never hot-reloads law into a live session.** A session executes the law
  it read when it started. An amendment made mid-flight -- to this command, to a
  schema, to a procedure -- reaches the NEXT dispatch, never the running one.
  This is an explicit non-goal, not a limitation to work around: the alternative
  makes a session's behaviour depend on wall-clock timing, so the same prompt
  run twice could follow two different rules.
