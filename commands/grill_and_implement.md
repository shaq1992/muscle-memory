---
description: Lightweight grill-then-build for tasks too small for a full plan. Runs a mixed-style grilling capped at 8 questions, writes a short brief to docs/quick/<slug>_brief.md, gates go/no-go via AskUserQuestion, then implements in-session. Standalone it ends in a quick/<slug> PR the user merges; handed a prompt carrying an "## Orchestration" block it runs as an orchestrated session instead -- session branch, merge into integration, handback, no PR.
argument-hint: <slug> <task> (slug = short kebab-case slug max 20 chars; then describe the task + @file references) -- or paste an orchestrated session prompt
---

Run a compressed grill-and-implement loop for the task described in $ARGUMENTS. This is
the lightweight sibling of `/grilling_session` for work that fits in one session and does
not warrant a PRD, a multi-phase plan, a ledger, or the phase-closing apparatus -- NONE of
those are produced here.

## Step 0 -- Detect the mode

This command has exactly TWO modes, and the mode is DETECTED, never declared. There is no
flag, no mode argument and no dispatch marker to consult.

**The signal is the PRESENCE of a heading spelled exactly `## Orchestration`** in the task
text -- either directly in $ARGUMENTS, or in a prompt file @-referenced from it and read
during argument parsing. Nothing else is the signal: not a plan-shaped slug, not a branch
that happens to exist, not the user saying the work belongs to a plan.

- **No `## Orchestration` block -> STANDALONE.** Behavior is byte-identical to v4.0 of
  this command: parse -> grill -> brief -> go/no-go gate -> `quick/<slug>` branch -> PR,
  plus the single observations line at close (Step 5). Every instruction below marked
  ORCHESTRATED ONLY is inert, and nothing in the standalone path depends on a plan, a
  state file, an orchestrator, or a handback. A user who has never seen an orchestrator
  can run this command end to end.
- **`## Orchestration` block present -> ORCHESTRATED.** The block is written by
  `/orchestrator` and carries four bolded fields, spelled exactly `State file:`,
  `Handback:`, `Branch:` and `Rows this session must obey:`. Those fields are the
  session's parameters; read them, do not re-derive them. The orchestrated additions are
  listed inline below, each marked ORCHESTRATED ONLY.

The heading string `## Orchestration`, those four bolded field names, and the convention
that a field's value is BARE (the value on its own line, annotations on continuation
lines) are all OWNED by `commands/orchestrator.md` Step 7 item 3, which writes them. Any
change to the heading, to a field name, or to that value convention must land in both
files in lockstep -- and in the mentions in `commands/on_board.md` and
`harness/USER_MANUAL.md` -- because a one-sided rename silently drops a dispatched session
back into the standalone lane, where it would open a pull request.

State the detected mode in a one-line notice before doing anything else, so the user can
see which lane they are in.

## Parse arguments

1. **slug** -- the FIRST token of $ARGUMENTS. Normalize it per the "Slug normalization"
   rule in the branch-model section of `harness/procedures/git_strategy.md`, which is the
   single source for slug shape and for the one-line notice stating the normalized value;
   it is not restated here. If no slug is given, derive one from the task and state it.
2. **task** -- everything remaining. Read any @file references in full before your first
   question.

**ORCHESTRATED ONLY.** The plan slug and the session number come from the
`## Orchestration` block, not from the first token: the block's `Branch:` field carries
them as `<plan_name>-session-<NN>`. The branch name is EXACTLY the text on that field's
own line and nothing else -- any indented continuation beneath it (such as the
`(cut from integration/<plan_name>)` parenthetical) is annotation, never part of the
name. If the invocation also supplies a slug token, it names only the brief; absent one,
derive the brief slug from the plan name and session number and normalize it the same
way.

## Step 0a -- Open the handback (ORCHESTRATED ONLY)

Do this the moment the prompt has been read, BEFORE any question and before any work. A
handback written only at the end is absent when a session dies, and an absent file is
indistinguishable from a session that was never dispatched.

1. **Write the stub** at the path in the block's `Handback:` field -- the schema, the
   `Status:` vocabulary and the read receipt are defined in
   `harness/templates/handback_schema.md`; follow it and do not restate it. The stub
   carries `Status: OPEN` and the two-line read receipt: `- Rows:` with the E-IDs from
   the FIRST CELL of each row the block listed under "Rows this session must obey"
   (comma-separated), and `- Prompt-SHA256:` with the output of `sha256sum` run on the
   PROMPT FILE this session was invoked with -- compute it, never guess it; the closing
   hook verifies both against the dispatch manifest.
2. **Write the handback marker** at `.claude/handback_session.json`, with exactly these
   keys:

   ```json
   {
     "session_id": "<value of $CLAUDE_CODE_SESSION_ID>",
     "plan_name": "<plan name from the block>",
     "session_number": "<NN from the block>",
     "handback_path": "<path from the block's Handback: field>"
   }
   ```

   Get the session id by running `echo $CLAUDE_CODE_SESSION_ID` (Bash tool) -- never guess
   or invent one. Write the marker unconditionally, even if unsure whether the enforcing
   hook is registered; the marker is inert without it. `.claude/hooks/enforce_handback.py`
   is the hook that reads it, and it removes the marker itself once the handback passes.

An orchestrated session writes a handback marker INSTEAD OF a phase-closing marker. The
two are mutually exclusive by construction, so never write both.

Then obey the rows the block handed you. They are the plan's pinned invariants, gates and
do-not-re-validate entries, already filtered to what this session touches; a
do-not-re-validate entry is not an invitation to check it again.

## Step 1 -- Grill (capped at 8 questions)

Mixed-style grilling (what/why AND how), HARD-CAPPED at 8 questions total.

**Ask the questions through the AskUserQuestion tool by default, in BOTH modes.** The tool
renders the options as a natively selectable list, records WHICH option the user chose
structurally instead of leaving you to map free text like "b, b, b" back onto your own
prose, and always offers "Other" itself. So do NOT hand-roll a markdown question block
here, do NOT add an "Other (describe)" option of your own -- it is redundant -- and do not
fall back to prose questions the user has to answer in free text.

This is the one place `/grill_and_implement` DEPARTS from `/grilling_session`: that
command's markdown OUTPUT FORMAT does not apply in this lane, and nothing below inherits
it. Its grilling CONDUCT still does -- questions getting progressively more specific as
context builds, contradictions surfaced before requirements questions, a novel idea
offered as an option rather than as a separate prompt, and `linger` plus general asides
handled the same way (a `linger` sub-loop is freeform by definition, so it suspends the
tool here exactly as it suspends multiple-choice there).

Using the tool concretely:

- **The recommendation moves INTO the options, it is not dropped.** The tool's own
  guidance is that the recommended option comes FIRST and its label carries
  "(Recommended)"; the reasoning that used to sit under the options goes in that option's
  description. Every question still carries a recommendation.
- **One call carries 1-4 questions, and the batching rule caps a turn at 3** genuinely
  independent questions -- no question's best answer could change based on another's. The
  tighter of the two governs, so 3 per call is the working maximum; send a batch as ONE
  call rather than one call per question, and never invent a fourth question to fill the
  tool's slot.
- **Reach for multiSelect** when the answers are genuinely additive (which files are in
  scope, which checks to run) rather than mutually exclusive, and use the per-option
  description to preview what picking it commits the session to.
- **Escape hatch -- narrow and honest.** Ask in prose ONLY when the tool genuinely cannot
  carry the question: its options cannot be enumerated in advance, or answering it needs a
  long worked example or code block that will not fit an option description. State in one
  line why the tool was bypassed. "Typing it out was faster" is not one of those cases.

Scaled-down rules for this lane:

- Before any question that proposes file locations or git behavior, read `.gitignore` and
  `.claude/preferences.md` and answer from them instead of asking.
- Stop grilling as soon as the task is unambiguous -- the cap is a ceiling, not a quota.
  The user can also end grilling early with "stop asking questions".
- If 8 questions are not enough to pin the task down, say so plainly and recommend a full
  `/grilling_session` instead of guessing.

**The cap is EIGHT in BOTH modes, and a ceiling in both.** Three or four questions is
normal and healthy; asking a fifth because four have been asked is the failure this note
exists to prevent, and so is asking none because the prompt looked complete.

**A lower orchestrated cap is explicitly REJECTED.** It is tempting -- an orchestrated
session arrives with a written prompt, so surely it should need to ask less. But a cap
that tightens under orchestration signals that ASKING IS EVIDENCE THE PROMPT FAILED, and
a session that believes that guesses instead of asking. The failure mode being defended
against is an UNDER-SPECIFIED PROMPT, not question volume. Do not re-derive a lower
ceiling from the fact that a prompt exists.

**ORCHESTRATED ONLY.** If the questions were needed because the dispatched prompt did not
carry enough to do the work, that is a `prompt-underspecified` structural observation --
report it in the handback (Step 5) rather than absorbing it silently.

## Step 2 -- Write the brief

Write `docs/quick/<slug>_brief.md` (create `docs/quick/` if absent), SHORT by design:

```
# Quick Brief: <slug>

## Scope
[2-4 sentences: what is being built/changed and what is explicitly out]

## Decisions
[One bullet per grilling decision, with the user's elaborations captured verbatim
where they went beyond picking an option]

## Implementation outline
[Numbered steps: files to touch, changes per file, how it will be verified]
```

The brief is the ONLY document this command produces, and it doubles as the PR body
(Step 4) -- write it to stand alone for a PR reviewer.

**ORCHESTRATED ONLY.** The brief is still written, but it no longer doubles as a PR body
because no PR is opened. It is a working document for this session; the session's durable
output is the handback, and the plan's memory of record is the state file -- which this
session NEVER writes. Anything that must survive the session goes in the handback's
`## Delta`, pre-formatted in the state file's table shape, for the orchestrator to ingest.

## Step 3 -- Go/no-go gate

Gate through AskUserQuestion: proceed with the implementation as briefed / revise the
brief (free-text what to change) / abandon. Do not start implementing before the gate
clears. On revise, update the brief and re-gate.

On abandon, close honestly rather than quietly: standalone, say so and stop; ORCHESTRATED
ONLY, finalize the handback as `ABANDONED`, which costs a status field and one sentence
and nothing else.

## Step 4 -- Implement in-session

Git parameters come from `.claude/preferences.md`'s key block; the no-Claude-path-to-the-
protected-branch invariant of `harness/procedures/git_strategy.md` holds identically here.

**Standalone:**

1. Cut ONE short-lived branch `quick/<slug>` from the default branch.
2. Implement the brief in-session; commit on that branch (conventional messages, no AI
   attribution -- ever). Verify per the brief's outline and report results plainly.
3. Confirm the ACTIVE gh account owns the target repo (`gh auth status`) and switch to
   the owning account if it is not active -- `gh pr create` follows gh's active account,
   and repo-local push pinning does NOT cover it, so with two github.com identities the
   PR otherwise opens as the wrong user. Then push the branch and open the PR with
   `gh pr create`, using the brief as the PR body source (title from the brief's scope
   line; no AI attribution in title or body).
4. The USER merges with a `!`-prefixed `gh pr merge <n> --merge` -- the keystroke is the
   approval. Claude never runs `gh pr merge`. If the merge is withheld, the branch and
   open PR are the durable artifacts.

**ORCHESTRATED ONLY** -- steps 1 and 3-4 above are REPLACED by the per-work-unit flow in
`harness/procedures/git_strategy.md`, whose work unit here is the dispatched session:

1. Cut the branch named in the block's `Branch:` field, `<plan_name>-session-<NN>`, from
   `integration/<plan_name>` -- never from the default branch. Take the name from that
   field's own line only, per "Parse arguments" above.
2. Implement and commit on it exactly as above (same commit rules, same no-attribution
   law).
3. Close by merging into `integration/<plan_name>` and stop there: push the session
   branch, merge with git defaults and an explicit `-m "merge: ..."` message, push
   integration, delete the session branch remote and local with `git branch -d` (never
   `-D`).
4. **Open NO pull request.** Only the PLAN opens a PR, once, at the end, and the
   orchestrator does it. If every session opened its own PR the protected branch would be
   flooded and the integration branch would stop being the plan's single accumulation
   point. The zero-commit rule applies unchanged: a session branch with no commits skips
   push/merge/delete and says so plainly.

## Step 5 -- Close

**Standalone:** append this run's structural observations -- defects in the WORKFLOW
MACHINERY this session ran under, never defects in the project's domain logic -- to
`docs/observations.md`, one line per observation in the fixed shape and closed tag
vocabulary defined in `harness/templates/handback_schema.md`, with `-` in the session-number
field. The file is APPEND-ONLY: never edit, reorder or delete an existing line. If there is
nothing to report, append nothing; do not fabricate an observation to fill the file.

This is a ONE-LINE WRITE, not a self-improvement step. Do not compose a brief, spawn a
sub-agent, review a diff or propose an edit to the harness. The observation is evidence
for a later improve pass that reads the whole file; a single session is a sample of one,
and acting on it is exactly the failure the append-only file exists to avoid.

No phase-closing marker, no learnings file, no ledger entry, no document reconciliation
-- the brief, the PR and that one appended line are the whole paper trail.

**ORCHESTRATED ONLY:** finalize the handback INSTEAD. Advance the stub in place to its
terminal status -- `PARTIAL`, `ABANDONED` or `COMPLETE` -- and fill the three sections per
`harness/templates/handback_schema.md`: `## Delta` (rows pre-formatted in the state file's
table shape, so the orchestrator transcribes rather than authors), `## For the next
session` (advisory judgement only), and `## Structural observations` (same closed
vocabulary as above, or `none`).

Do NOT append to `docs/observations.md` yourself in this mode -- the orchestrator copies
those lines across when it ingests the handback, and appending here would double every
entry.

The handback REPLACES the canonical end-of-phase apparatus entirely: NO phase-closing
marker, NO per-phase learnings file, NO ledger merge and no `Last merged` stamp. It is the
session's whole durable output.
