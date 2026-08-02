---
description: Run a structured requirements session in one of three modes (mixed default, functional, technical), then produce a PRD and multi-phase implementation plan. Requires docs/ folder with subdirs prds/, multi_phase_plans/, learnings/, prompts/ -- created by /bootstrap.
argument-hint: <plan_name> [functional|technical] <custom_instructions> (plan_name = short kebab-case slug max 20 chars; optional mode token; then describe what you want to build + @file references)
---

Enter "grilling session" mode. Your objective is to extract fine-grained requirements
for the task described in $ARGUMENTS, then produce the PRD and multi-phase implementation
plan the active mode calls for.

This command is pure flow logic. It does NOT restate document structure or the
self-improver spawn flow -- those live in single-source files you READ when you reach the
step that needs them: PRD structure in `.claude/harness/templates/prd_schema.md`; plan
structure (phase block, Behavioral Tests spec, tracer-bullet slicing rule + exemption,
context/ update-on-touch rule) in `.claude/harness/templates/plan_schema.md`; the
self-improver spawn flow in `.claude/harness/procedures/self_improvement.md`.

Read any @file references in $ARGUMENTS in full before generating your first response.
If the context contains internal contradictions, surface those first as your opening
question.

## Session open -- controls legend

Your FIRST response of the session opens with this 3-line legend, verbatim, before the
glossary block and before Question 1, so the user knows the session's controls up front:

```
Controls: say "stop asking questions" to end the Q&A and move to wrap-up.
Say "linger" for a freeform deep-dive on the current question ("fully defined" resumes).
Asides that are not answers are recorded as requirements without costing a question.
```

## Session start -- read the glossaries

Before Question 1, read the two glossary surfaces so established shorthand is spoken
natively for the rest of the session:

- Harness glossary: `.claude/harness/harness_glossary.md` (terms owned by the command
  system).
- Domain glossary: `context/glossary.md` (project domain terms).

If either file does not exist yet, note it in one line and proceed -- they are seeded by
a later harness phase and their absence is not an error. Do not block the session on them.

After the read, and before Question 1, PRESENT a "Relevant Glossary Definitions" block to
the user: a curated SUBSET of terms drawn from `context/glossary.md` (and, where useful, the
harness glossary) filtered for relevance to the initial prompt / custom instructions in
$ARGUMENTS -- not the entire glossary. This is a lightweight surfacing step to establish a
shared baseline vocabulary at the start of the session. Render each surfaced term with its
one-line definition as it appears in the source glossary; do not paraphrase or expand. If no
term is relevant, state "No relevant glossary terms surfaced." in one line and continue. If
neither glossary file exists yet, skip this surfacing step entirely.

## Mode parsing -- do this before Question 1

Parse `$ARGUMENTS` in this order:

1. **plan_name** -- the FIRST token (before the first space or newline).
2. **mode** -- the SECOND token IF it is exactly `functional` or `technical`; otherwise
   there is no mode token and the mode is `mixed` (the bare default).
3. **custom_instructions** -- everything remaining after the tokens consumed above.

Mode semantics (grilling scope and outputs are detailed further below):
- `mixed` (bare, no mode token): the default -- grill what/why AND how, write
  the full PRD and the plan in one pass.
- `functional`: grill only the what/why; write the functional PRD, no plan.
- `technical`: read the existing functional PRD, grill only the how, append the technical
  sections to it, write the plan.

### Slug auto-normalization

If `plan_name` is present but not already a valid kebab-case slug (lowercase alphanumeric
+ hyphens, max 20 chars), auto-normalize it: lowercase, replace underscores/spaces with
hyphens, strip invalid characters, truncate to 20 chars. State the normalized slug in a
one-line notice and proceed -- do NOT spend Question 1 asking the user to approve it. Only
if `plan_name` is entirely absent do you ask Question 1 below.

`plan_name` governs all downstream artifacts:
- PRD: `docs/prds/<plan_name>_prd.md`
- Plan: `docs/multi_phase_plans/<plan_name>_plan.md`
- Prompts: `docs/prompts/DDMMYY/<plan_name>_phase_N_implementation_prompt.md`
- Learnings: `docs/learnings/DDMMYY/<plan_name>_phase_N_learnings.md`

### Question 1 -- only if plan_name entirely absent

Propose a `plan_name` slug for the user to approve. Derive a short kebab-case slug (max 20
chars) from $ARGUMENTS and present three variants as options.

## Environment verification -- mandatory before location/git questions

Before asking ANY question that proposes file locations, git behavior, or version-control
assumptions, you MUST first read `.gitignore` and `.claude/preferences.md` (key block:
interpreter invocation, encoding constraint, integration prefix, phase-branch pattern,
protected branch, merge defaults; prose sections: file-location rules), then
answer from them. This is the "read the codebase instead of asking" rule made mandatory
for its highest-leverage instance: a location or git-workflow fact recoverable from these
files is never a question.

## Mode preconditions -- confirm-and-proceed, never halt, never silently adapt

Check the precondition for the parsed mode and, if it is unmet, open with a single
confirm-and-proceed question offering the options below. Never halt outright and never
silently adapt.

- `technical` with NO existing functional PRD at `docs/prds/<plan_name>_prd.md` -- offer:
  (a) switch to mixed mode; (b) halt so the user can run a functional session first;
  (c) proceed, treating the typed custom_instructions as the functional baseline.
- `functional` with an EXISTING PRD at that path -- offer: (a) append-extend the existing
  PRD; (b) restart it from scratch; (c) switch to technical mode on it.

This deliberately supports the hand-written-PRD workflow: the user may draft a functional
PRD by hand, then run `technical` mode on it.

For `technical` mode with a functional PRD present: read that PRD in full, including its
`## Technical Parking Lot` if one exists. Every parked item becomes a seed question for
this session and gets full challenge-and-recommend treatment -- a parked aside was never
grilled, so it is the user's opening position, not a settled decision.

## Output format -- follow this exactly every turn

---
<One sentence acknowledging the user's previous answer (starting from Question 2)>

**Question <N>** [Question here]

- Option A -- <description and trade-offs>
- Option B -- <description and trade-offs>
- Option C -- <description and trade-offs>
- Other (describe)

<Your recommendation and brief reasoning.>
---

When a turn batches questions (see the batching rule below), repeat the question block --
number, options, recommendation -- once per question in the same turn, sequential question
numbers, one acknowledgment sentence at the top of the turn. The per-question format never
changes.

## Grilling rules

- **CRITICAL -- NEVER stop asking questions on your own.** You MUST keep asking questions
  turn after turn. The ONLY thing that ends the Q&A loop is the user saying the exact stop
  sequence: "stop asking questions". Even if you believe you have gathered all necessary
  requirements, ask at least one more follow-up rather than self-terminating. If you have
  no open ambiguities, say so in one sentence, then ask a question probing edge cases or
  constraints not yet verified. Stopping early without the stop sequence is a violation.
- Every question MUST be a multiple-choice question with 3-4 options. Never ask open-ended
  prose questions.
- **Batching rule:** up to 3 questions may share one turn ONLY when they are GENUINELY
  independent -- no question's best answer could change based on another's answer, and none
  probes the same decision area. When in doubt, or whenever questions build on each other,
  ask one at a time. Answers to a batch are processed together before the next turn.
- Always include "Other (describe)" as the last option.
- Questions get progressively more specific as context builds.
- Surface contradictions before requirements questions.
- If a question can be answered by reading the codebase, read it instead of asking (see
  the mandatory environment-verification read above for location/git questions).
- Recommendation always comes after the options.
- **Novel-idea surfacing:** If you identify a novel non-obvious improvement, optimisation,
  or architectural idea the user has not mentioned, surface it as one of the options in the
  relevant question -- not as a separate prompt.
- **Linger mode:** If the user says `linger`, enter a freeform back-and-forth sub-loop on
  the current question. Suspend multiple-choice format. Hold the current question number.
  Continue until the user says "fully defined" in the affirmative. Acknowledge in one
  sentence ("Locked.") then immediately present the next numbered question in standard
  format. If `linger` arrives on a batched turn, the sub-loop covers the question the user
  names (or the first of the batch if unnamed); the batch's other questions are re-presented
  after "fully defined".
- **General notes / asides:** If the user supplies a general note or requirement that is
  not an answer to the current question's options, acknowledge it in one sentence, record
  it as a standalone requirement for the eventual PRD, and continue the current question
  without spending a question slot on it.

## Mode-specific grilling scope

- `mixed`: grill both the what/why and the how. No boundary.
- `functional`: grill ONLY the what/why. NEVER ask a technical question (architecture,
  technology choice, implementation mechanism). Technical content that arrives anyway
  (model drift, or a user aside) is NOT grilled -- record it verbatim to be written into
  the PRD's `## Technical Parking Lot`, marked non-binding. The parking lot is the
  technical session's opening agenda, not a settled decision.
- `technical`: grill ONLY the how. Append-only: you may NOT rewrite the functional
  sections of the existing PRD. If a technical finding invalidates a functional decision,
  SURFACE it to the user explicitly and let them decide -- never silently edit a functional
  section.

## When the user says "stop asking questions" -- post-stop choreography

Run the three steps below in this EXACT order. `mixed` and `technical` run all three.
`functional` SKIPS step 1 entirely (no vestigial slicing or behavioral-test questions)
and runs steps 2-3 only.

1. **Slicing + behavioral-test ratification (one combined turn).** In a SINGLE turn, ask
   a batch of maximum 4 and minimum 1 questions on how to integrate vertical-slicing
   discipline into the phase breakdown, AND a question that formally ratifies the list of
   phases and their `### Behavioral Tests` (briefly described): which phases actually
   expect a behavior change and what each test should be. The tracer-bullet slicing rule
   and its exemption for inherently non-sliceable plans live in
   `.claude/harness/templates/plan_schema.md` -- read them there; do not restate. The
   Behavioral Tests block spec lives there too. Record the ratified slicing ruling for
   the plan's Slicing note and the ratified test list for the phase blocks.
2. **Decision log + single confirmation.** Show a decision log -- every key decision made
   during the session, grouped by area. The group NAMES may be renamed to fit the plan's
   domain (e.g. rename "Data" to something apter), but the Phase Structure portion is a
   FIXED contract: render it as a markdown table with exactly these three columns -- `#`,
   `Phase`, `One-line objective` -- with one-line objectives per phase. Cite the question
   number each decision originated from (e.g. `Q<N>`). Append two one-liner subsections
   at the end of the same turn:
   - **Glossary:** "Propose adding <terms>, retiring <terms> -- object or accept." (Terms
     coined this session go to the appropriate surface -- harness terms to
     `.claude/harness/harness_glossary.md`, domain terms to `context/glossary.md`; this is
     the glossary's only garbage-collection point. If a glossary file does not exist yet,
     note what would be added. If nothing to add or retire, say so in the one line.)
   - **Self-diagnosis:** "None found." -- or one line naming a STRUCTURAL issue this
     session revealed with the Q&A mechanics, document templates, or grilling rules
     (never a one-off patch, project domain logic, or threshold values) + asking whether
     to run the spawn flow.
   This whole turn -- decision log, phase table, glossary line, self-diagnosis line -- is
   covered by ONE confirmation gate. Wait for user confirmation or corrections. If
   self-diagnosis found something and the user says run it, run the shared spawn flow in
   `.claude/harness/procedures/self_improvement.md` (do not restate it here) AFTER the
   gate clears, before writing documents.
3. **Write the documents** (next section).

## Writing the documents

### Capture discipline (applies to every mode)

Be very pedantic capturing the decisions made in the session into the PRD, and reflect
them at the appropriate locations in the plan. Downstream tasks depend ONLY on these
documents; any missed detail is a disaster. Pay special attention to things the user says
beyond choosing an option, and copy the user's words verbatim where they elaborate.

Before finalizing, perform an explicit re-audit pass: re-read every user message from this
session (not just the decision log) and confirm each decision AND each aside/elaboration
is represented in the PRD, then reflected at the appropriate location in the plan. Asides
volunteered during a `linger` sub-loop are the highest-risk for loss -- verify those
explicitly. Fix any partial capture before writing is considered complete. The full
capture rules live in `prd_schema.md`; follow them.

**Provenance-tag self-containment note:** if the PRD or plan you write cites session-time
provenance tags -- question numbers (`Q<N>`), register item IDs, or any identifier
resolvable only from this session's context -- the document MUST open with a
self-containment note declaring those tags citations-only and the document text
authoritative, so downstream sessions never attempt to resolve them (the session
transcript is not downstream-readable). The standing rule lives in `prd_schema.md`'s
capture rules; emit the note whenever such tags are used.

### Step 1 -- ensure directories exist

Create `docs/prds/` (and, for modes that write a plan, `docs/multi_phase_plans/`) if they
do not already exist.

### Step 2 -- write the PRD

Write `docs/prds/<plan_name>_prd.md` against the structure in
`.claude/harness/templates/prd_schema.md`. Per-mode:

- `mixed`: write the FULL section set, including the technical section, in this one pass.
- `functional`: write the functional sections only. Record any technical content that
  arrived during grilling verbatim in the `## Technical Parking Lot` section, marked
  non-binding. Do NOT write a plan file.
- `technical`: APPEND the technical sections to the existing PRD. Do not rewrite functional
  sections. Remove the `## Technical Parking Lot` once its items are dispositioned.

### Step 3 -- write the multi-phase plan (`mixed` and `technical` only)

Write `docs/multi_phase_plans/<plan_name>_plan.md` against the structure in
`.claude/harness/templates/plan_schema.md` (phase block, complexity sizing, the ratified
Slicing note, per-phase `### Behavioral Tests` blocks for phases ratified as behavior-
changing, and the context/ update-on-touch rule). Determine the phase breakdown from the
scope of work -- each phase independently completable in one session -- and apply the
tracer-bullet ruling ratified in choreography step 1. `functional` mode writes no plan.

### Step 4 -- save a project memory

Save a memory entry recording: plan_name, PRD path, plan path (or "functional-only, no
plan yet" for functional mode), and a one-line goal summary, so future sessions pick up
the active plan immediately.
