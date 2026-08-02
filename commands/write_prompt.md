---
description: Compile a reference-based phase implementation prompt (~200 lines) from a plan's PRD, phase section, accumulated learnings, and the harness procedure files.
argument-hint: <plan_name> <phase_number> (e.g. /write_prompt example-plan 3)
---

Compile a reference-based implementation prompt for one phase of a multi-phase plan.

This command is a PHASE COMPILER. The generated prompt inlines ONLY phase-specific
content -- objective, deliverables, Definition of Done, `### Behavioral Tests` copied
verbatim, filtered learnings, and a resolved-parameters block -- and @-references all
stable law from `.claude/harness/procedures/`. It never restates procedure text:
improvements to a procedure land once and every previously- or newly-generated prompt
executes current law. Target: ~200 lines per generated prompt (learnings-heavy late
phases may run longer; the non-learnings core stays near 200).

Single-source files this command READS at the step that needs them (never restated):

- `.claude/harness/templates/plan_schema.md` -- the plan/phase structure being compiled,
  including the `### Behavioral Tests` block spec and gate conventions.
- `.claude/harness/procedures/git_strategy.md` + `.claude/preferences.md` (key
  block) -- branch model, the two booleans, autonomous vs permission-gated
  operations, machine-parseable naming parameters.
- `.claude/harness/procedures/verification_cases.md` + `.claude/preferences.md`
  (`## Verification` section) -- the five human-verification CASE patterns and
  their project parameters.
- `.claude/harness/procedures/closing_sequence.md` -- referenced BY THE OUTPUT, not
  restated in it.

Portability fallbacks: if `.claude/preferences.md` is absent, use the defaults
stated inline in the corresponding procedure file (git_strategy.md defaults;
verification_cases.md generic placeholders; monitoring.md generic protocol) and say so
in the generated prompt.

## Step 1 -- Parse inputs and resolve dates

`$ARGUMENTS` contains two tokens in either order: a phase number (positive integer) and
a plan name (kebab-case string). Identify them by type:

- **phase_number**: whichever token is a positive integer. Zero-pad to two digits (`NN`).
- **plan_name**: whichever token is not a positive integer.
- **today_ddmmyy**: run `date +%d%m%y` (Bash tool) -- do NOT compute the date from memory.

Output path: `docs/prompts/<today_ddmmyy>/<plan_name>_phase_<NN>_implementation_prompt.md`

If either token is missing or no token is a positive integer, stop and say:
"Usage: /write_prompt <plan_name> <phase_number>"

`today_ddmmyy` dates only the prompt's own output directory. The LEARNINGS path inside
the generated prompt is resolved at EXECUTION time by the implementation session running
`date +%d%m%y` itself (see the template's closing section) -- never substitute the
generation date into it. There is no date-token hand-editing anywhere in this system.

## Step 2 -- Read the schema, PRD, and plan

Read `.claude/harness/templates/plan_schema.md` -- it defines the phase structure you
are compiling (Objective / Behavioral Tests / Deliverables / Handoff Artifact /
Definition of Done / Verification, plus gate conventions).

Read `docs/prds/<plan_name>_prd.md` in full.
Read `docs/multi_phase_plans/<plan_name>_plan.md` in full. Extract the complete section
for the requested phase (starts at `## Phase N --`, ends before the next `## Phase`
heading or end of file). Count the total number of phases. Note whether the phase
carries a `### Behavioral Tests` block or gate language, and read the plan's own
"Git strategy for THIS plan" section.

## Step 3 -- Resolve the git parameters (the two booleans)

Read `.claude/harness/procedures/git_strategy.md` and the key block of
`.claude/preferences.md`, then resolve:

- `is_first_phase` = (phase_number == 1); `is_final_phase` = (phase_number == total).
- Resolve concrete names from the key-block patterns -- integration branch
  `integration/<plan_name>`, phase branch `<plan_name>-phase-<NN>` -- plus the commit
  message (`feat: <plan_name> phase <N> -- <brief>`) and merge message
  (`merge: <plan_name> phase <N> -- <brief>`). If the plan's git-strategy section
  explicitly names DIFFERENT branches or a different repo (e.g. a harness plan whose
  branches live in the nested repo at `.claude/`), the plan wins on branch NAMES and
  repo location; BEHAVIOR always follows git_strategy.md (autonomous phase-level
  close with git-default merges and explicit messages; plan-end PR merged by the
  USER) -- a plan predating the PR law does not reintroduce standby/manual-merge
  handovers or any Claude-run path to the protected branch.
- State the zero-commit rule in the resolved block: a phase branch that ends with
  zero commits skips push/merge/delete and reports "no tracked changes this phase"
  (git_strategy.md).
- **If `is_final_phase`**: resolve the plan-end PR flow for emission -- after the
  last integration merge, push the integration branch and open the PR autonomously
  with `gh pr create` (title/body per git_strategy.md's PR convention: plan
  one-liner, bulleted phase list drawn from the per-phase `feat:` commits --
  under git-default merges a phase merge FAST-FORWARDS whenever the integration
  branch has not moved since the phase branch was cut, so per-phase merge commits
  may not exist -- pointer note; no AI attribution). Then the USER merges with a
  `!`-prefixed `gh pr merge <n> --merge`
  per the `merge_style` / `retain_integration_branch` preference keys -- the
  keystroke is the approval and its output lands in the transcript. Claude never
  runs `gh pr merge` (the guardrail hook flat-blocks it). Emit the user-run merge
  command verbatim in template section 9.

## Step 4 -- Accumulated learnings (ledger read, inline filtering)

**Phase 1 short-circuit:** if phase_number == 1, set the learnings section to
"No prior learnings for this plan yet." and skip this step.

**Otherwise**, read the plan's rolling ledger -- the ONLY learnings source:
`docs/learnings/<plan_name>_ledger.md` (plan-level path, not date-nested;
current-truth-only, maintained by every phase close per closing_sequence.md).
Do NOT read the per-phase learnings files -- they are immutable history, and
anything current lives in the ledger.

**No-ledger branch:** if the file does not exist, set the learnings section to
"No prior learnings for this plan yet." and continue.

Filter the ledger's bullets IN-CONTEXT against the current phase's Objective and
Deliverables (from Step 2), then inject the survivors verbatim:

- Bias toward INCLUDING a bullet when uncertain. A spurious bullet in a future
  prompt is less harmful than missing a load-bearing constraint. Only drop
  bullets whose subject matter clearly cannot affect the current phase's work.
- Preserve surviving bullet wording verbatim, including the trailing `(PN)`
  origin stamps -- do not paraphrase, shorten, or restructure. Filtering is
  inclusion/exclusion only.
- Keep the ledger's theme headers for the surviving bullets; drop a header
  whose bullets were all filtered out. Do not add commentary or summaries.
- If a bullet is a definitive plan-wide finding (e.g. a field rejected in N/N
  phases tried), include it regardless of the current phase's immediate scope.

(The ledger is kept internally contradiction-free at every close -- merge law
in closing_sequence.md -- so there is no read-time contradiction check. If the
ledger nonetheless plainly contradicts the PRD/plan phase content, that is a
close-time failure: STOP and surface it per the ambiguity protocol rather than
silently picking a side.)

## Step 5 -- Codebase snapshot (scoped, live-derived)

CLAUDE.md's skeletal directory map is ORIENTATION ONLY -- there is no authoritative
per-file map anywhere to copy from. Derive per-file detail live:

1. From the phase's Deliverables and Verification sections, list the directory TREES
   this phase will touch, and scope the find at each touched tree's ROOT -- not only
   at the leaf subdirectories the deliverables happen to name. A phase that touches
   several subdirectories of a tree almost always also touches (or must at least be
   shown) that tree's root-level files; scoping the find to the leaves silently drops
   them from the snapshot. If scoping a whole tree is genuinely too broad, explicitly
   list the root-level files of any partially-touched tree alongside the leaf finds.
   Special case -- research/Explore-driven phases: if the phase's real
   working set is a set of read-only SOURCE files consumed by dispatched Explore agents
   (plus an OUTPUT directory the phase writes into) rather than files being edited in
   place, the meaningful working set is (a) the OUTPUT directory's current contents and
   (b) the per-initiative/per-topic SOURCE files the Explore agents are scoped to. In
   that case snapshot the output directory's contents (via the scoped find in item 2, or
   the `ls` fallback in item 2 if it is out-of-repo) AND list the source files by path
   -- do NOT full-read them (they are Explore-delegated) -- rather than listing only
   directories being edited in place.
2. Run a scoped find over ONLY those directories:
```bash
find <phase_dirs> -type f \
  -not -path '*/.git/*' \
  -not -path '*/__pycache__/*' \
  -not -path '*/projects/*' \
  -not -name '*.pyc' -not -name '*.pkl' -not -name '*.db' -not -name '*.log' \
  | sort
```
   The find template and its exclusions apply to IN-REPO directories only. If the
   phase's working set includes an out-of-repo directory (e.g. the persistent memory
   directory at `~/.claude/projects/<project-slug>/memory/`), list its files
   separately with a plain `ls` -- the `*/projects/*` exclusion would otherwise
   silently drop that path from the snapshot.
3. Write a one-line description per file. **Never describe a source file from memory**:
   for any file whose content you are uncertain about, run
   `grep -n "^def \|^class " <file>` (or read a targeted excerpt) first. Re-verify after
   any branch switch -- do not rely on a pre-switch read.
4. Note any large files to flag for Explore delegation in the generated prompt's
   section 1. Cover BOTH classes: (a) large SOURCE files surfaced by the find in
   item 2 -- schemas, generated JSON, long pipeline scripts; AND (b) large
   DATA-INPUT files the phase CONSUMES (e.g. gitignored derived artifacts named
   in the plan's Deliverables / Verification / reference table, even when they
   live outside the item-2 find scope). For every data input identified, run
   `wc -c -l <file>` and, if the byte or line count would not safely fit inline
   (rule of thumb: > ~1 MB or > ~10k lines), emit an explicit
   "Explore / programmatic-only -- never Read inline" flag naming that file in
   the generated prompt's section 1, alongside the existing large-source flags.

## Step 6 -- Select the verification case

Read `.claude/harness/procedures/verification_cases.md` and the `## Verification`
section of `.claude/preferences.md`. Select exactly ONE case (A-E) matching the phase,
resolve its text with the project parameters, and note it for the template. Include the
project's test-suite command in the Automated subsection ONLY if the phase touches
production code covered by the tests-as-deliverables policy; always carry the
phase-specific verification commands from the plan verbatim. If a plan verification
command contains an angle-bracket placeholder (e.g. `<memory_dir>`), keep the command
verbatim and state the resolved concrete value alongside it -- never silently rewrite
the command.

## Step 7 -- Write the prompt file

Create `docs/prompts/<today_ddmmyy>/` if needed and write the output using the template
below. Fill every [PLACEHOLDER]; emit no bracketed instruction text into the output.

---

## Output template

```
# Session Prompt: Phase [N] -- [Phase Name]

**Project:** [one-line project descriptor drawn from CLAUDE.md -- never hardcoded here]
**Plan:** [plan_name]
**Phase:** [N] of [total]
**Generated:** [YYYY-MM-DD]

---

## 1. Before You Start -- Read These in Full

- @CLAUDE.md
- @docs/prds/[plan_name]_prd.md
- @docs/multi_phase_plans/[plan_name]_plan.md (focus on the Phase [N] section)
[Reference-files block only if the phase has specific file dependencies: derive the list
from the plan's reference table or the phase scope; one line each: - @path (purpose).
A `branch:file` path is a git reference -- emit "Read via: git show \"branch:file\"",
never an @path.]
[Only if Step 5 flagged large files:]
Use Explore sub-agent for: [file -- what to extract]. Do not read these inline.

---

## 2. Project Overview

[2-3 sentences from the PRD: what the system is and what this plan changes. For the
system's current architecture, defer to CLAUDE.md's project-state snapshot -- NEVER
name a model architecture from template guidance or an older prompt; it goes stale.]

---

## 3. Current Codebase State

[The Step 5 scoped list, one line per file.]

For the rest of the repository, see CLAUDE.md's skeletal directory map; derive
per-file detail on demand via Agent(subagent_type="Explore").

---

## 4. Phase Objective

[Verbatim from the plan.]

---

## 5. Deliverables

[Verbatim from the plan, including any Implementation Notes subsection.]

[If the plan phase carries a `### Behavioral Tests` block: copy it here VERBATIM,
including its write-first / run-RED / implement-to-green parenthetical. The plan is
kept true at every phase close by the reconciliation step (closing_sequence.md), so
the verbatim copy is simply correct -- no supersession annotation is emitted. Omit
the whole block entirely if the plan has none.]

---

## 6. Definition of Done

[Verbatim from the plan.]

---

## 7. Verification

### Automated -- run these and confirm all pass:

[Test-suite command per Step 6, if warranted; then the plan's phase-specific
verification commands, verbatim.]

Tests-as-deliverables policy: per @.claude/preferences.md (Verification section).

### Human ([selected case title])

[The ONE resolved case text from Step 6.]

---

## 8. Constraints

- Environment (interpreter invocation, encoding constraint, encoding="utf-8" on
  open()): follow the `interpreter` / `encoding_constraint` keys of
  @.claude/preferences.md.
- Implement only what section 5 lists -- no scope creep from future phases. Precedence:
  a section 5 deliverable always beats a generic constraint in this section.
- [DEFAULT:] Do not modify CLAUDE.md, docs/prds/, or docs/multi_phase_plans/.
  [OVERRIDE -- only if a section 5 deliverable names CLAUDE.md:] Do not modify
  docs/prds/ or docs/multi_phase_plans/. CLAUDE.md IS modifiable this phase -- surgical
  updates only, reflecting only what the Deliverables specify.
- PRD/plan provenance tags ("R5.6", "A1", "Q8"-style) are session-time citations ONLY --
  never copy them into portable harness files (commands/, agents/, hooks/, harness/, incl.
  docstrings and tests); restate any PRD rule self-contained in the file that carries it.
- If, during implementation, you find the live code diverges from any prior
  specification document -- the PRD (`docs/prds/`), the multi-phase plan
  (`docs/multi_phase_plans/`), CLAUDE.md, or a gitignored `context/` file -- the
  tiebreaker is: THE LIVE CODE WINS -- but ONLY for DESCRIPTIVE claims (what the system does, how a
  module behaves, what a parameter resolved to, what an artifact contains). It NEVER
  applies to PRESCRIPTIVE constraints: hard rules, security invariants, legal /
  permitted-use boundaries, budget law, encoding rules, or the ambiguity protocol.
  Code that violates one of those is a BUG to surface and fix, never evidence that
  the constraint has changed -- only the user may relax one.
  The tracked, reviewed code is what actually ships and what a
  reviewer diffs against; a prior spec written before the code -- especially one this
  phase is forbidden to edit, or a gitignored `context/` file with no CI and no reviewer
  -- can silently go stale and must not override a claim verifiable in the code. RECORD
  every such divergence explicitly, naming the document, the specific clause/line, and
  the contradicting code path -- do not silently propagate the stale claim. Where the
  diverging document is one this phase is FORBIDDEN to edit (docs/prds/,
  docs/multi_phase_plans/ per the default rule above), the record MUST land in the
  phase's durable trail -- the `context/` deliverable if the phase carries one,
  otherwise the phase learnings -- AND must be surfaced to the user in
  the closing summary so they can authorise a follow-on reconciliation phase if they
  want one. Divergences against a gitignored `context/` file additionally feed the
  update-on-touch rule (@.claude/harness/templates/plan_schema.md) so a follow-on phase
  can carry the corresponding `update context/<file>` deliverable.
- [Only if the phase includes any script/training run expected to exceed ~45s:] Before
  running ANY such command, read and follow @.claude/harness/procedures/monitoring.md
  plus @.claude/preferences.md (Monitoring section). Never run long ops synchronously.
- The phase is NOT complete until section 7 passes. If the environment cannot run a
  check, state so explicitly rather than claiming success.
- If task-tracking tools (TaskCreate/TaskUpdate) are available, use them to track
  section 5 progress.
- Context budget: when the session is well underway, ask the user to run /context once
  (it is a user-typed CLI command -- a session cannot invoke it). If suggesting a
  handoff: one line only (tokens used + remaining deliverables + "suggest handoff");
  if accepted, write [output_path minus .md]_handoff.md with completed and remaining
  deliverables, in-flight state, and a pointer back to this prompt. One handoff
  suggestion per session.

---

## 9. Resolved Parameters

(per @.claude/harness/procedures/git_strategy.md + @.claude/preferences.md)

- plan_name: [plan_name] -- phase [NN] of [total]
- is_first_phase: [bool] -- is_final_phase: [bool]
- integration branch: [name]; phase branch: [name]; commit message: "[...]"; merge
  message: "[...]" (merge with git defaults + explicit -m; delete the phase branch
  with -d, never -D)
- Zero-commit rule: if the phase branch ends with zero commits, skip
  push/merge/delete and report "no tracked changes this phase" plainly.
- [Final phase only:] plan-end PR flow: push [integration-branch], then open the PR
  autonomously with `gh pr create` (title/body per
  @.claude/harness/procedures/git_strategy.md's PR convention -- no AI attribution).
  The USER merges it with a `!`-prefixed command in this session:

      ! gh pr merge <n> --merge

  (per the merge_style / retain_integration_branch preference keys: merge-commit
  style; the integration branch is retained). Claude never runs `gh pr merge` --
  the guardrail hook flat-blocks it; the user's keystroke IS the approval, and if
  it is withheld the plan closes with the integration branch and open PR as the
  durable artifacts.
- Learnings path: docs/learnings/<DDMMYY>/[plan_name]_phase_[NN]_learnings.md, where
  <DDMMYY> is resolved AT EXECUTION TIME -- see section 11.
- Verification case: [letter -- title]

---

## 10. Accumulated Learnings from Prior Phases

[Step 4's surviving ledger content verbatim -- theme headers plus stamped
bullets -- or "No prior learnings for this plan yet."]

---

## 11. End of Phase -- Closing Sequence

[If the plan phase carries gate language: quote the plan's gate block verbatim here,
before the closing steps.]

Once all deliverables are complete and section 7 has passed[, and the gate decision is
confirmed], follow @.claude/harness/procedures/closing_sequence.md end to end
(structural brief -> approval -> self-improver per
@.claude/harness/procedures/self_improvement.md -> phase-closing marker + learnings
file -> ledger merge + stamp -> document reconciliation -> commit -> git close per
@.claude/harness/procedures/git_strategy.md), using section 9's resolved values.

Date rule: run `date +%d%m%y` ONCE at write time and use that single DDMMYY value in
BOTH the marker's learnings_path and the learnings file path -- never hand-type a date.

[Non-final phase:] Next phase: if asked, generate the next prompt with
/write_prompt [plan_name] [N+1] (re-read the PRD and plan first -- the session may have
been compacted).
[Final phase:] This is the final phase of plan [plan_name] -- no next prompt. [If the
phase touches production serving/training paths, add the project's end-to-end
verification pointer per @.claude/preferences.md (Verification section).]
```

---

## Step 8 -- Validate and confirm

Run the deterministic validator from the PROJECT ROOT (its @-reference check
resolves paths against the current working directory):
```bash
python3 .claude/harness/scripts/validate_prompt.py <output_file>
```
It checks: every template-emitted @-reference resolves on disk; no leftover
`[PLACEHOLDER]` / bracketed template instruction text; all required template
sections present; resolved branch names sane (`integration/<slug>`,
`<slug>-phase-NN` zero-padded, NN <= total). Fenced code blocks, inline code
spans, and section 10 (the verbatim-injected learnings) are exempt from the
@-reference and residue scans by design -- verbatim learnings must NEVER be
reworded to satisfy the validator.

Surface the validator's output verbatim. On any `FAIL` line, fix the prompt (or
the missing file) and RERUN until it exits green -- never report the prompt done
with a failing validation.

Then tell the user: the output path; phase N of total; whether the ledger was
found and how many bullets survived the Step 4 filter; codebase files listed;
any Explore-delegation flags; the resolved git parameters; the validator
verdict; and the line count.

## Step 9 -- HITL self-improvement

Review observations about THIS command (`.claude/commands/write_prompt.md`) collected
while executing it -- template ambiguities, missing constraints, incorrect find
patterns. Run the shared flow in `.claude/harness/procedures/self_improvement.md`
(brief -> approve -> spawn -> surface -> one-level drift cascade); do not restate it.
Project- or plan-specific notes belong in the implementation session's learnings file,
not here.
