# Harness Glossary

Portable vocabulary owned by the command system itself. Ported verbatim with the
harness (it lives inside `.claude/` and travels with it). Definitions, not
documentation: 1-2 lines each; anything longer points at the authoritative doc.
Every entry earns its place -- seeded terms are subject to the same end-of-session
retirement sweeps, no grandfathering. A term whose meaning is guessable from its
words gets no entry.

## Ratified terms

- **repo-recovery test** -- The criterion for what survives in CLAUDE.md and
  `context/`: a fact stays only if it CANNOT be recovered by reading the repo
  (decisions, rationale, invariants code does not express, tribal knowledge).
  Mechanical detail is deleted outright, not moved -- Explore re-derives it.
- **armed pointer** -- A 1-2 line always-loaded trigger in CLAUDE.md that names a
  condition and the procedure/context file to read BEFORE acting, instead of
  inlining the procedure body.
- **procedure file** -- A portable law file under `.claude/harness/procedures/`
  (git_strategy, closing_sequence, monitoring, verification_cases,
  self_improvement). Commands @-reference these rather than restate them, so a
  fix lands once and every consumer executes current law.
- **preferences file** -- The single project-specific opinion surface at
  `.claude/preferences.md`: a machine-parseable key block supplying parameters
  (git, interpreter, test command, encoding) plus short Verification/Monitoring
  prose sections. What makes the harness portable by design; out of
  self-improver jurisdiction (user-edited only).
- **phase compiler** -- The `/write_prompt` command: it compiles a reference-based
  implementation prompt by inlining ONLY phase-specifics (objective, deliverables,
  DoD, behavioral tests, learnings, resolved parameters) and @-referencing stable
  law from `harness/procedures/*`.
- **parking lot** -- The `## Technical Parking Lot` section of a functional PRD:
  non-binding technical asides captured during functional-mode grilling. The
  technical session reads it as its opening agenda -- an opening position, never a
  settled decision.
- **preserve-then-extend** -- The command-rewrite discipline: first verify existing
  behavior against the newly extracted files, THEN add new machinery -- isolating
  "extraction broke something" from "the new feature is wrong".
- **update-on-touch** -- The staleness rule (in `plan_schema.md`): any phase whose
  deliverables change a fact recorded in a `context/` file MUST carry an explicit
  "update context/<file>" deliverable naming that file.
- **stop-sequence choreography** -- The fixed 3-step order a grilling session runs once
  the user says "stop asking questions": slicing + behavioral-test ratification in one
  combined turn -> decision log + phase table with glossary and self-diagnosis one-liners
  under a single confirmation -> write documents. (functional mode skips the first step.)

## Pre-existing vocabulary

- **linger** -- Grilling sub-mode: when the user types `linger`, the session
  suspends multiple-choice format and holds the current question number for a
  freeform back-and-forth until the user says the topic is "fully defined".
- **decision log** -- The grouped list of every key decision made during a grilling
  session (each citing its originating `Q<N>`), shown as the final confirmation
  gate before documents are written.
- **drift warning** -- A flag the self-improver raises that a DIFFERENT file has a
  related issue, paired with a ready-to-use "suggested brief". Not an edit -- it
  seeds the one-level drift cascade.
- **gate phase** -- A phase whose completion is held pending an explicit user
  decision (a gate), e.g. the user-performed plan-end PR merge or a
  ratification checkpoint.
- **stop sequence** -- The user's "stop asking questions" trigger that ends the Q&A
  loop and starts the stop-sequence choreography.
- **phase-closing marker** -- `.claude/phase_closing.json`: the file the closing
  sequence writes recording session_id + plan + phase + learnings_path; the
  `enforce_phase_closing.py` Stop hook blocks the closing turn until the learnings
  file exists in the required schema (`**Branch:**` first line, `## Learnings`
  header) and the plan ledger's `Last merged: phase NN` stamp matches the
  marker's phase, then self-deletes the marker.
- **behavioral test contract** -- The `### Behavioral Tests` block ratified at PLAN
  time (not implementation time): named test cases per behavior-changing phase,
  written FIRST and run RED before implementation, with no tests beyond the
  contract added silently. The prompt writer copies the block VERBATIM; the plan
  is kept true at every phase close by the document-reconciliation step, so the
  verbatim copy is simply correct.
- **integration branch** -- `integration/<plan_name>`, cut from the default branch
  in a plan's first phase; the single accumulation point all phase branches merge
  into, kept off the protected branch until the plan-end PR is merged by the USER.
- **shakedown** -- The first real plan run on the new harness -- the live exercise
  of the machinery, protected by the integration branch and the verified
  guardrail hook.
