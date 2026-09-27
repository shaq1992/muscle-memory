---
description: 'Orchestrated-only requirements grilling: open a lean handback stub, grill via AskUserQuestion with no question cap until the user says "stop asking questions", then write a full requirements doc and finalize the lean handback. No branch, no commits; writes only gitignored docs files.'
argument-hint: 'paste or @-reference an orchestrated session prompt carrying an ## Orchestration block and a Requirements doc: field (it names this command itself)'
---

Run an orchestrated requirements grilling for the session prompt in $ARGUMENTS. This
command exists for one lane only: an orchestrator dispatched a session whose product is a
REQUIREMENTS DOC, not code. It grills without a question cap, writes the requirements doc,
and hands back a lean index to it.

This command is pure flow logic. The structure and vocabulary of everything it writes --
the lean handback, its `Status` values, the read receipt, the requirements doc, the
terminal-state checks, the abandon path, manual ingest -- live in ONE file:
`.claude/harness/templates/grill_handback_schema.md`. Read it before Step 0a and follow
it; it is referenced here, never restated. Where this command and that schema disagree,
THE SCHEMA WINS.

## Step 0 -- Mode check (orchestrated only)

**The signal is the PRESENCE of a heading spelled exactly `## Orchestration`** in the
prompt -- either directly in $ARGUMENTS, or in a prompt file @-referenced from it (read
that file in full before anything else). If there is no such heading, refuse in exactly
one line and stop:

```
/orchestrated_grill runs only on an orchestrated prompt; use /grilling_session standalone
```

There is NO standalone lane. Do not grill, do not write any file, do not offer to proceed
anyway.

With the block present, read its bare-value fields -- the value is the text on the field's
own line; indented continuation lines are annotation, never part of the value:

- `State file:` -- the plan's state file. READ-ONLY for this session.
- `Handback:` -- the lean handback path (Step 0a).
- `Rows this session must obey:` -- the pinned invariants, gates and do-not-re-validate
  entries handed to this session.
- `Requirements doc:` -- the exact path the requirements doc is written to (Step 2). Use
  it verbatim; never derive your own.

`Branch:` and `Accumulation branch:` may be absent; if present they are IGNORED -- this
session holds no tree (see "Holds no tree" below). A prompt assembled by
`harness/scripts/assemble_dispatch.py` carries its own `/orchestrated_grill` line directly
under its first H1 title -- that line IS the invocation, not task text: do not re-invoke
this command and do not read it as part of the task.

**Lockstep contract.** The heading string `## Orchestration`, the bolded field names
(including `Requirements doc:`), and the bare-value convention are OWNED by
`commands/orchestrator.md` Step 7 and EMITTED by `harness/scripts/assemble_dispatch.py`.
Any change to the heading, a field name, or the value convention must land in those files
and in this one in lockstep -- a one-sided rename makes this command refuse a genuinely
orchestrated prompt, or read an empty path.

State in a one-line notice that the session is running in the orchestrated grilling lane.

## Step 0a -- Open the handback (before any question)

Do this the moment the prompt has been read, BEFORE the first question. A handback written
only at the end is absent when a session dies.

1. **Write the stub** at the `Handback:` path (create parent directories if absent):
   `Status: OPEN` plus the two-line read receipt, per the schema's "Written at session
   START" and "The read receipt" sections:
   - `- Rows:` -- the E-IDs from the FIRST CELL of each row listed under "Rows this session
     must obey", comma-separated;
   - `- Prompt-SHA256:` -- the output of ONE `sha256sum <prompt file>` call on the prompt
     file this session was invoked with. Compute it, never guess it.
2. **Write the grill marker** at `.claude/grill_handback_session.json`, with exactly these
   keys:

   ```json
   {
     "session_id": "<value of $CLAUDE_CODE_SESSION_ID>",
     "plan_name": "<plan name>",
     "session_number": "<NN>",
     "handback_path": "<path from the block's Handback: field>",
     "requirements_doc_path": "<path from the block's Requirements doc: field>"
   }
   ```

   Get the session id by running `echo $CLAUDE_CODE_SESSION_ID` (Bash tool) -- never guess
   or invent one. Take `plan_name` and `session_number` from the conventional handback
   path `docs/orchestration/<plan_name>/handbacks/<NN>.md`; if the path is not
   conventional, write them as `null`. This key set is a SHARED CONTRACT with
   `hooks/arm_handback_marker.py` and `hooks/enforce_grill_handback.py`: any change to it
   must update all three files in lockstep.
3. **NEVER write `.claude/handback_session.json`.** That marker arms
   `hooks/enforce_handback.py`, which blocks every stop while the handback is `OPEN` --
   and a grilling session stops on every question; that stall is the observed defect the
   grill marker exists to remove (schema: "Stops while `OPEN` are allowed"). If
   `.claude/handback_session.json` already exists AND its `session_id` equals THIS
   session's id (the UserPromptSubmit hook can arm it before it knows which command the
   prompt names), delete it. A marker naming a different session is not yours: leave it.

Then obey the handed rows: a do-not-re-validate entry is not an invitation to check it
again. NEVER write the state file -- the one-writer rule holds; the orchestrator authors
every row.

## Session open

Your FIRST response of the session opens with the controls legend from
`commands/grilling_session.md`, verbatim, before any question:

```
Controls: say "stop asking questions" to end the Q&A and move to wrap-up.
Say "linger" for a freeform deep-dive on the current question ("fully defined" resumes).
Asides that are not answers are recorded as requirements without costing a question.
```

Then, before Question 1:

- **Contradictions first.** If the prompt contradicts itself or the handed rows, surface
  that as the opening question.
- **Environment verification.** Before ANY question that proposes file locations, git
  behavior or version-control assumptions, read `.gitignore` and `.claude/preferences.md`
  and answer from them instead of asking.
- **Read the codebase instead of asking.** A fact recoverable from the repository is never
  a question.

## Step 1 -- Grill (no question cap)

Mixed grilling: the what/why AND the how, no boundary.

**Questions go ONLY through the AskUserQuestion tool.** Do NOT hand-roll a markdown
question block and do NOT add an "Other (describe)" option -- the tool offers "Other"
itself. `commands/grilling_session.md`'s markdown OUTPUT FORMAT does not apply here; its
grilling CONDUCT does (below). Using the tool, as in `commands/grill_and_implement.md`
Step 1:

- **The recommendation moves INTO the options.** The recommended option comes FIRST, its
  label carries "(Recommended)", and the reasoning goes in that option's description.
  Every question carries a recommendation.
- **Up to 3 genuinely independent questions per call** -- no question's best answer could
  change based on another's, and none probes the same decision area. When in doubt, or
  when questions build on each other, ask one at a time. Send a batch as ONE call; never
  invent a question to fill a slot.
- **multiSelect when the answers are additive** rather than mutually exclusive; use the
  per-option description to preview what picking it commits to.
- **Escape hatch -- narrow and honest.** Ask in prose ONLY when the tool genuinely cannot
  carry the question: its options cannot be enumerated in advance, or answering it needs a
  long worked example or code block that will not fit an option description. State in one
  line why the tool was bypassed.

Conduct carried from `commands/grilling_session.md`:

- Questions get progressively more specific as context builds.
- Surface contradictions before requirements questions.
- **Novel-idea surfacing:** a novel non-obvious improvement, optimisation or architectural
  idea the user has not mentioned is offered as one of the options in the relevant
  question -- not as a separate prompt.
- **Linger:** if the user says `linger`, enter a freeform back-and-forth sub-loop on the
  current question -- it SUSPENDS the tool -- holding the question number until the user
  says "fully defined"; acknowledge with "Locked." and present the next question.
- **Asides:** a general note or requirement that is not an answer is acknowledged in one
  sentence, recorded as a standalone requirement for the doc, and costs no question.

**There is NO question cap.** The loop ends only as below:

- **CRITICAL -- NEVER stop asking questions on your own.** You MUST keep asking questions
  turn after turn. The ONLY thing that ends the Q&A loop is the user saying the exact stop
  sequence: "stop asking questions". Even if you believe you have gathered all necessary
  requirements, ask at least one more follow-up rather than self-terminating. If you have
  no open ambiguities, say so in one sentence, then ask a question probing edge cases or
  constraints not yet verified. Stopping early without the stop sequence is a violation.

Every question round and every `linger` exchange ends a turn with the handback still
`OPEN` -- that is the normal, allowed state (schema: "Stops while `OPEN` are allowed").

If the grilling needed things the dispatched prompt should have carried, record a
`prompt-underspecified` structural observation for the handback's
`## Structural observations` (Step 2) rather than absorbing it silently.

## Holds no tree

This session opens NO branch, makes NO commit and opens NO pull request. It writes exactly
two files, both under gitignored `docs/`: the requirements doc and the lean handback (plus
the `.claude/grill_handback_session.json` marker). Nothing else is written.

## Step 2 -- After "stop asking questions": write, then finalize

There is NO confirmation gate, no decision-log turn and no ratification round. The moment
the user says the stop sequence, immediately:

1. **Write the requirements doc** at the `Requirements doc:` path (create parent
   directories if absent), per the schema's "The requirements doc" section. Then run the
   re-audit pass it names: re-read EVERY user message of the session and confirm each
   decision AND each aside is in the doc -- `linger` asides are the highest risk for loss
   and are checked explicitly. Fix any gap before moving on. The doc is written BEFORE the
   handback is finalized.
2. **Finalize the lean handback in place**: advance the stub's `Status` to its terminal
   value and fill the sections exactly as the schema's "Structure of the lean handback"
   defines them.

NEVER append to `docs/observations.md` -- structural observations go in the handback only;
the orchestrator copies them across when it ingests.

**Abandon path.** If the session ends without a requirements doc worth reading, the
handback is the `Status` line plus one sentence, per the schema's "The abandon path"
section. Nothing more is owed.

## Close

State in one closing line that ingest is MANUAL: the orchestrator never runs
`harness/scripts/ingest_handback.py` on this handback; it reads the lean handback and the
requirements doc and authors any state rows itself (schema: "Ingest is MANUAL ONLY").
