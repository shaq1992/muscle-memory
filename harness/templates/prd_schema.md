# Template: PRD Schema

Single source of truth for PRD document structure. Written by the grilling
command; read by the prompt writer. Neither command restates this schema inline.

## Path invariance

The schema is path-invariant: downstream consumers never know (and never need to
know) whether a PRD was produced by a mixed session in one pass or by a
functional session followed by a technical session. Mixed mode writes the FULL
section set, including `## Technical Requirements`, in its single pass.

## File location

`docs/prds/<plan_name>_prd.md` -- `<plan_name>` is a kebab-case slug, max 20
chars, alphanumeric + hyphens only.

## Structure

```
# PRD: <plan_name>

## Overview
[2-3 sentences: what this plan delivers and why]

## Goals
[Bulleted success criteria]

## Non-Goals
[Explicit scope exclusions]

## Requirements
[Detailed functional requirements, grouped by area (R1, R2, ... with numbered
sub-clauses R1.1, R1.2, ...). Behavioral acceptance criteria live here.]

## Technical Requirements
[Architecture decisions, technology choices, technical constraints. Written by
mixed mode in its single pass, or APPENDED by a later technical session.
Functional-only PRDs omit this section until a technical session adds it.]

## Out of Scope
[What is deliberately deferred]

## Amendments
[Absent until the first amendment -- see the Amendments spec below.]
```

### Optional section: `## Amendments`

Appended ONLY by the closing sequence's user-gated document-reconciliation
step (`harness/procedures/closing_sequence.md`) -- never by direct mid-phase
edits; that reconciliation step is the sanctioned mutation path past the
append-only rule. Each phase close that amends the PRD appends ONE dated
entry (`### YYYY-MM-DD -- phase NN`, then one line per edit naming what
changed and the superseding decision). Approved amendments edit the body
surgically AND log the change here, so the requirement text is always
current truth.

### Optional section: `## Technical Parking Lot`

Present only in a PRD produced by a FUNCTIONAL-mode session. Technical content
that arrived during functional grilling (model drift or user aside) is recorded
here VERBATIM and marked non-binding. The technical session reads the parking
lot as its opening agenda: every parked item becomes a seed question and gets
full challenge-and-recommend treatment -- a parked aside was never grilled, so
it is the user's opening position, not a settled decision. The technical session
removes the parking lot once its items are dispositioned.

## Capture rules (apply when writing any PRD)

- Be pedantic capturing session decisions. Downstream tasks depend ONLY on the
  PRD + plan pair; any missed detail is a disaster.
- Copy the user's words verbatim where they elaborate beyond choosing an option.
- Append-only rule for technical sessions: a technical session may not rewrite
  functional sections. If a technical finding invalidates a functional decision,
  surface it to the user explicitly -- never silently edit.
- Before finalizing, re-audit: re-read every user message from the session and
  confirm each decision AND each aside is represented. Asides volunteered during
  a `linger` sub-loop are the highest-risk for loss -- verify those explicitly.
