# Template: Multi-Phase Plan Schema

Single source of truth for plan document structure. Written by the grilling
command; read by the prompt writer (the "phase compiler") to know what it is
compiling. Neither command restates this schema inline.

## File location

`docs/multi_phase_plans/<plan_name>_plan.md`

## Document header

The plan opens with:

```
# Multi-Phase Plan: <plan_name>

PRD: `docs/prds/<plan_name>_prd.md` (read in full before any phase).

## Git strategy for THIS plan (read first)
[Resolved against harness/procedures/git_strategy.md: integration branch name
and the per-phase boolean values. Note any plan-specific exceptions, e.g.
branches living in a different repo.]

## Slicing note (ratified)
[Which tracer-bullet ruling applies -- sliced phases, or the exemption with its
stated reason (see Tracer-bullet slicing rule below).]
```

## Phase structure block

Every phase uses this exact structure:

```
## Phase N -- <Phase Name>

### Complexity
[Low | Medium]

### Objective
[1-2 sentences]

### Behavioral Tests
[OPTIONAL -- only for phases that actually expect a behavior change. See the
Behavioral Tests block spec below. Omit the heading entirely for phases with no
behavior change (doc-only, scaffolding, refactor-without-behavior-change).]

### Deliverables
[Bulleted concrete outputs]

### Handoff Artifact
[Name the exact primary artifact this phase produces that the NEXT phase (or a
later phase) consumes -- including its concrete file path. If that artifact is a
markdown/spec document rather than code, state exactly what it contains and
which downstream phase reads it, by exact filename. If this phase produces no
downstream handoff (purely terminal work), state "None -- terminal phase" or
name the durable output instead.]

### Definition of Done
[Checklist]

### Verification
[Exact commands: run the project's test suite, plus any phase-specific checks.
Human checks state exactly what the reviewer must confirm.]
```

## Complexity sizing

For each phase drafted:
(a) Assess Low (<75k tokens expected), Medium (<95k), or High (>95k) based on
    distinct subsystems touched and expected file reads.
(b) If High, split into two phases before writing.
(c) Tag each phase with `### Complexity` immediately after the phase heading.
Aim for all phases to be Low or Medium.

## Behavioral Tests block spec

Test specs are born at PLAN time, not implementation time. The technical/mixed
grilling session emits a `### Behavioral Tests` block per ratified phase:
concrete, named test cases stating expected observable behavior, ratified by the
user during the session's stop-sequence choreography.

- Only phases that actually expect a behavior change carry a block.
- The block opens with a parenthetical stating: write these test cases FIRST,
  run them RED, implement to green; where the suite lives; and that no tests
  beyond this contract may be added without flagging them explicitly.
- Scope filter: the contract covers production-path code. Experiment, analysis,
  and throwaway scripts stay exempt per the project's tests-as-deliverables
  policy.
- The implementation prompt copies the block VERBATIM into the generated prompt.

## Tracer-bullet slicing rule

Where feasible, Phase 1 is the thinnest end-to-end slice through every layer the
plan touches; later phases widen the slice. Exemption: inherently non-sliceable
plans (doc-only, refactors, dependency-ordered infrastructure) may instead
follow dependency order -- the plan MUST say so explicitly in its Slicing note,
naming the exemption reason. The grilling session's tracer-bullet question batch
decides which ruling applies; the plan records the ratified outcome.

## Amendments section

Every plan document may end with an `## Amendments` section. It is appended
ONLY by the closing sequence's user-gated document-reconciliation step
(`harness/procedures/closing_sequence.md`) -- never by direct mid-phase edits;
that reconciliation step is the sanctioned mutation path past the append-only
rule. Each phase close that amends the document appends ONE dated entry:

```
## Amendments

### YYYY-MM-DD -- phase NN
- <what changed, one line> (superseding decision: <the mid-phase decision>)
- ...
```

The section is absent until the first amendment. Approved amendments edit the
body text surgically AND log the change here, so the body is always current
truth and the trail records how it got there.

## context/ update-on-touch rule

Any phase whose deliverables change a fact recorded in a `context/` file MUST
carry an explicit "update context/<file>" deliverable in its Deliverables list,
naming the specific file. The durable `context/` files are `context/architecture.md`
(Layer 1-3 semantics, cache/join contracts, invariants), `context/decisions.md`
(closed experiments, feature history, guardrail numbers, local-artifacts index),
and `context/glossary.md` (domain glossary). This is the staleness-governance
convention that keeps durable project knowledge truthful; the plan author checks
each phase against the current `context/` contents while drafting.

Exception when live code diverges from a prior specification document: when any
phase (of any kind) finds the live code diverging from a prior specification --
the PRD (`docs/prds/`), the multi-phase plan (`docs/multi_phase_plans/`),
CLAUDE.md, or a gitignored `context/` file -- THE LIVE CODE WINS, but ONLY for
DESCRIPTIVE claims: statements about what the system does, how a module behaves,
what a parameter resolved to, what an artifact contains. The tiebreaker NEVER
applies to PRESCRIPTIVE constraints -- hard rules, security invariants, legal /
permitted-use boundaries, budget law, encoding rules, the ambiguity protocol, or
any other "MUST / MUST NOT" the project imposes on itself (the project
CLAUDE.md's hard-constraint sections). Code that violates a prescriptive constraint is a BUG to
surface and fix, never evidence that the constraint has changed; only the user
may relax one. The tracked,
reviewed code is what actually ships and what a reviewer diffs against; a prior
spec written before the code -- especially one the phase is forbidden to edit,
or a gitignored `context/` file with no CI and no reviewer -- can silently go
stale and must not override a claim verifiable in the code. RECORD every such
divergence explicitly, naming the document, the specific clause/line, and the
contradicting code path -- do not silently propagate the stale claim. Where the
diverging document is one the phase is FORBIDDEN to edit (`docs/prds/`,
`docs/multi_phase_plans/`), the record MUST land in the phase's durable trail --
the `context/` deliverable if the phase carries one, otherwise the phase
learnings -- AND must be surfaced to the user in the closing
summary so they can authorise a follow-on reconciliation phase. Divergences
against a gitignored `context/` file additionally feed the update-on-touch rule
above so a follow-on phase can carry the corresponding `update context/<file>`
deliverable. This mirrors the matching conditional bullet in
`.claude/commands/write_prompt.md` section 8 (Constraints).
