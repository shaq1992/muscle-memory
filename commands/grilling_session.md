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

## Session start -- read the glossaries (R6.6)

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
- `mixed` (bare, no mode token): the regression baseline -- grill what/why AND how, write
  the full PRD and the plan in one pass, behaving byte-for-byte as the pre-modes command.
- `functional`: grill only the what/why; write the functional PRD, no plan.
- `technical`: read the existing functional PRD, grill only the how, append the technical
  sections to it, write the plan.

### Slug auto-normalization (R1.9a)

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

## Environment verification -- mandatory before location/git questions (R1.9b)

Before asking ANY question that proposes file locations, git behavior, or version-control
assumptions, you MUST first read `.gitignore` and `.claude/preferences.md` (key block:
interpreter invocation, encoding constraint, integration prefix, phase-branch pattern,
protected branch, merge defaults; prose sections: file-location rules), then
answer from them. This is the "read the codebase instead of asking" rule made mandatory
for its highest-leverage instance: a location or git-workflow fact recoverable from these
files is never a question.

## Mode preconditions -- confirm-and-proceed, never halt, never silently adapt (R1.6)

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

## Grilling rules

- **CRITICAL -- NEVER stop asking questions on your own.** You MUST keep asking questions
  turn after turn. The ONLY thing that ends the Q&A loop is the user saying the exact stop
  sequence: "stop asking questions". Even if you believe you have gathered all necessary
  requirements, ask at least one more follow-up rather than self-terminating. If you have
  no open ambiguities, say so in one sentence, then ask a question probing edge cases or
  constraints not yet verified. Stopping early without the stop sequence is a violation.
- Every question MUST be a multiple-choice question with 3-4 options. Never ask open-ended
  prose questions.
- One question at a time, always.
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
  format.
- **General notes / asides:** If the user supplies a general note or requirement that is
  not an answer to the current question's options, acknowledge it in one sentence, record
  it as a standalone requirement for the eventual PRD, and continue the current question
  without spending a question slot on it.

## Mode-specific grilling scope

- `mixed`: grill both the what/why and the how. No boundary.
- `functional`: grill ONLY the what/why. NEVER ask a technical question (architecture,
  technology choice, implementation mechanism). Technical content that arrives anyway
  (model drift, or a user aside) is NOT grilled -- record it verbatim to be written into
  the PRD's `## Technical Parking Lot`, marked non-binding (R1.5). The parking lot is the
  technical session's opening agenda, not a settled decision.
- `technical`: grill ONLY the how. Append-only: you may NOT rewrite the functional
  sections of the existing PRD. If a technical finding invalidates a functional decision,
  SURFACE it to the user explicitly and let them decide -- never silently edit a functional
  section (R1.3).

## When the user says "stop asking questions" -- post-stop choreography

Run the steps below in this EXACT order. `mixed` and `technical` run all six steps.
`functional` SKIPS steps 1 and 2 entirely (no vestigial slicing or behavioral-test
questions) and runs steps 3-6 only.

1. **Tracer-bullet batch.** Ask a batch of maximum 4 and minimum 1 questions (all in a
   single turn) on how to integrate vertical-slicing discipline into the phase breakdown --
   asked INSTEAD of directly surfacing the decision log. The tracer-bullet slicing rule and
   its exemption for inherently non-sliceable plans live in
   `.claude/harness/templates/plan_schema.md` -- read them there; do not restate. Record the
   ratified ruling for the plan's Slicing note.
2. **Behavioral-test ratification.** A QnA-style question that formally ratifies the list
   of phases and their `### Behavioral Tests` (briefly described): decide which phases
   should have a behavior test (phases that actually expect a behavior change) and what
   that test should be. The block spec lives in `plan_schema.md`.
3. **Decision log + user confirmation.** Show a decision log -- every key decision made
   during the session, grouped by area. The group NAMES may be renamed to fit the plan's
   domain (e.g. rename "Data" to something apter), but the Phase Structure portion is a
   FIXED contract: render it as a markdown table with exactly these three columns -- `#`,
   `Phase`, `One-line objective` -- with one-line objectives per phase. Cite the question
   number each decision originated from (e.g. `Q<N>`). This is the single, final,
   everything-included confirmation gate. Wait for user confirmation or corrections.
4. **Glossary sweep.** Ratify any terms coined during the session (add to the appropriate
   glossary surface -- harness terms to `.claude/harness/harness_glossary.md`, domain terms
   to `context/glossary.md`) and propose retiring obsolete or unused terms. This is the
   glossary's only garbage-collection point. If a glossary file does not exist yet, note
   what would be added and move on.
5. **Self-diagnosis.** Ask whether this session revealed a STRUCTURAL issue with the Q&A
   mechanics, document templates, or grilling rules that would improve future sessions
   generally -- not a one-off patch, and not project domain logic or threshold values. If
   nothing found, state "No self-improvements needed." If suggestions are found, run the
   shared spawn flow in `.claude/harness/procedures/self_improvement.md` (brief -> approve
   -> spawn -> surface -> one-level drift cascade). Do not restate that flow here.
6. **Write the documents** (next section).

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
