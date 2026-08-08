# Procedure: End-of-Phase Closing Sequence

The canonical closing sequence every phase implementation session runs once all
deliverables are complete, tests pass, and the phase's verification section has
passed (and any gate decision has been confirmed by the user). Generated prompts
reference this file instead of restating it; the prompt supplies the resolved
parameters (plan name, phase number, branch names, learnings path).

## Steps 1-3: Self-improvement

Follow `harness/procedures/self_improvement.md`: collect a 3-5 bullet structural
brief about the prompt-writer command itself, surface it for user approval, and
spawn the self-improver sub-agent if approved (one-level drift cascade). If no
structural issues were found, state that explicitly -- do not fabricate
findings. Project- and plan-specific notes do NOT go in the brief; they go in
the learnings file (step 4).

## Step 4: Write learnings

**First action: write the phase-closing marker.** Before writing the learnings
file itself, get the current session_id by running `echo $CLAUDE_CODE_SESSION_ID`
(Bash tool) -- do not guess or invent a value. Then write
`.claude/phase_closing.json` (create the `.claude/` directory if it does not
already exist -- do not create a `.claude/hooks/` subdirectory here, only the
marker file) with exactly these keys:

```json
{
  "session_id": "<value of $CLAUDE_CODE_SESSION_ID>",
  "plan_name": "<plan_name>",
  "phase": <N>,
  "learnings_path": "docs/learnings/<today's actual execution DDMMYY>/<plan_name>_phase_<NN>_learnings.md"
}
```

**Date rule (critical):** resolve the date PROGRAMMATICALLY -- run `date +%d%m%y`
(Bash tool) ONCE at write time and use that single DDMMYY value in BOTH the
marker's `learnings_path` value AND the learnings file path. Never hand-type a
date and never reuse a date substituted at prompt-generation time. The two paths
MUST be byte-identical -- the Stop hook reads the marker's `learnings_path` and
blocks the closing turn until a compliant file at that exact path exists on
disk, so any drift between the two dates is a false-negative block.

**Marker + Stop-hook interplay.** The marker is read by the
`enforce_phase_closing.py` Stop hook (registered in `.claude/settings.json`,
invoked via stdlib `python3`). Mechanics:
- No marker present, or a marker whose `session_id` does not match the current
  session, is a structural no-op -- the hook allows unconditionally. A marker
  left by an abandoned session never blocks other sessions.
- If the marker matches the current session, the hook BLOCKS the closing turn
  (re-blocking on every retry -- the block condition is fully within the
  model's control, so this is intended behavior, not a runaway loop) until ALL
  of these hold:
  1. a file exists at `learnings_path`;
  2. its FIRST line starts with `**Branch:**`;
  3. it contains a `## Learnings` header;
  4. the plan ledger `docs/learnings/<plan_name>_ledger.md` carries a
     `Last merged: phase NN` stamp matching the marker's phase (step 5).
  Each block reason names the specific failed check.
- Once every check passes, the hook self-deletes the marker and allows.
Write the marker unconditionally, even if unsure whether the hook is registered
-- the marker is inert without it.

Then create the learnings file at the marker's `learnings_path`, with exactly
this schema:

```
**Branch:** <branch name active during this phase>

## Learnings
- bullet
- ...
```

Nothing else -- learnings are carry-forward BY DEFINITION. A learning not worth
carrying forward is not a learning; leave it out rather than filing it under a
side section. (The old `## Carry Forward` / `## Phase-Specific Only` split is
retired.) Bias toward including a bullet when uncertain -- a spurious bullet in
the ledger is less harmful than a missing load-bearing constraint.

The `**Branch:**` line is mandatory and must be the FIRST line of the file,
before `## Learnings`. Populate it with the actual git branch this phase worked
on -- the phase branch per git_strategy.md naming (run
`git branch --show-current` if uncertain). This is the only mechanism by which
other commands (e.g. `/jira_and_status_update`'s grep for `**Branch:**`) can
discover which branch a plan's work landed on without ad hoc lookups. Per-phase
learnings files are immutable history: never edit an earlier phase's file.

The learnings file lives in `docs/learnings/`, which is gitignored -- never
commit it.

## Step 5: Merge the ledger

The rolling per-plan ledger `docs/learnings/<plan_name>_ledger.md` is
CURRENT-TRUTH-ONLY: the single file the prompt writer reads for accumulated
learnings. Structure: a `# Learnings Ledger: <plan_name>` title, the mandatory
stamp line `Last merged: phase NN`, then bullets grouped under a few theme
headers chosen by the closing session. EVERY bullet ends with an origin stamp
`(PN)` naming the phase it came from.

At every close, merge ALL of this phase's learnings bullets in:

- **Add** each new bullet under the best-fitting theme header (create or
  retitle headers freely -- the grouping serves the reader, not history).
- **Supersede**: when a new bullet replaces an existing one, DELETE the old
  bullet and write the new one with its own `(PN)` stamp.
- **Delete stale**: remove bullets that no longer describe current truth
  (e.g. "X is pending" once X has shipped).
- **Caution rule:** err on the side of caution before deleting, and
  the ledger may NEVER hold two contradicting bullets. When a supersession
  clash is ambiguous -- the old and new bullets conflict and it is not certain
  the new one fully replaces the old -- STOP and ask the user (ambiguity
  protocol); never silently resolve it, because the ledger may not keep both
  and may not silently lose a load-bearing one.

Rewrite the `Last merged: phase NN` stamp to THIS phase's number at EVERY
close -- a close with no new learnings still updates the stamp (that is the
freshness signal the Stop hook enforces). The ledger lives at the PLAN level
(directly in `docs/learnings/`, NOT date-nested) and is gitignored -- never
commit it.

## Step 6: Document reconciliation (user-gated)

PRD/plan documents must be TRUE at every session start. Enumerate every
mid-phase decision, pivot, or recorded divergence that invalidates text in the
plan's PRD (`docs/prds/`) or multi-phase plan (`docs/multi_phase_plans/`), and
propose surgical edits:

1. **One batched presentation.** For each proposed edit: the document, the
   exact old text, the exact new text, and the causing decision -- rendered as
   numbered markdown diffs in the transcript.
2. **Gate through AskUserQuestion**: approve-all / veto-by-selection
   (multiSelect), chunked in groups of 4 when the edits exceed the option cap;
   free-text Other for tweaks. If there is nothing to reconcile, state that
   explicitly and skip the gate.
3. **Apply approved edits**, and append ONE dated entry to each touched
   document's `## Amendments` section (create the section at the end of the
   document if absent): date, phase, one line per edit -- what changed and
   which decision superseded it (schema: `plan_schema.md` / `prd_schema.md`).
   When an approved amendment supersedes a value (a count, target, threshold, or
   scope), ALSO surgically update any not-yet-executed phase's Objective prose in
   the same plan that restates that same value, so forward-looking phase
   objectives stay current truth and never require a downstream correction note.

This reconciliation step is the SANCTIONED mutation path past the append-only
rule: user-approved amendments with a dated trace are legitimate; silent drift
is not. Outside this step, PRD/plan files stay unmodifiable mid-phase.

## Step 7: Commit

Before staging any enumerated artifact from the plan's Deliverables (e.g.
retrained model pkls, training summaries, cache DBs, generated CSVs, benchmark
JSONs), verify each path is git-tracked -- run `git check-ignore <path>` (exit 0
means gitignored, exit 1 means tracked or tracked-eligible). Treat model/data
build outputs as "stage only if tracked in this repo" -- do not attempt to stage
a path the project gitignores. If this phase's build outputs are gitignored, the
phase's durable committable output is the code/test changes only; state that
plainly in the commit report.

Stage and commit the phase's tracked changes on the phase branch.

If the phase produced NO tracked changes (e.g. every deliverable was
environment/config work or landed in gitignored paths), commit nothing -- the
zero-commit rule in step 8 applies. State plainly what the phase's outputs
were and why nothing is committable.

Commit message: `feat: <plan_name> phase <N> -- <brief description>`. No AI
attribution anywhere, ever.

## Step 8: Autonomous git close

(Full law: `git_strategy.md`; parameters from `.claude/preferences.md`.)

**Zero-commit rule:** if the phase branch has zero commits, skip
push/merge/delete entirely and report "no tracked changes this phase" plainly,
then confirm the session ends on the expected branch
(`git branch --show-current`).

Otherwise, perform the autonomous close -- no user confirmation, no surfacing
of commands for manual execution:

1. Push the phase branch to origin.
2. `git checkout integration/<plan_name>`, then merge with git defaults and an
   explicit message:
   `git merge <phase-branch> -m "merge: <plan_name> phase <N> -- <brief description>"`.
3. Push the integration branch.
4. Delete the phase branch, remote and local (`git branch -d`, never `-D`).

Report each operation's outcome (hashes, branch states) to the user.

If `is_final_phase` is true: run the plan-end PR flow per git_strategy.md --
push the integration branch, open the PR autonomously with `gh pr create`
(title/body per the PR convention, no AI attribution), then hand off: the USER
merges with a `!`-prefixed `gh pr merge <n> --merge` (the keystroke is the
approval; Claude never runs `gh pr merge`). If the merge is withheld, the plan
closes with the integration branch and the open PR as the durable artifacts.

That PR flow fires UNLESS the prompt's section 9 resolved parameters record the
plan-end PR opt-out -- an explicit no-PR exception quoted from the plan's own
git-strategy section (git_strategy.md's removal-direction carve-out). When the
opt-out applies, the final phase ENDS after the last integration merge and push:
no `gh pr create`, no user-run `gh pr merge`, nothing merged to the protected
branch at any point, and the retained integration branch IS the plan's durable
artifact. Section 9's resolved values are authoritative for this choice -- do not
re-derive it from the plan at close time. The opt-out is never inferred from
silence and never assumed from a plan's tone or scope (absent an explicit,
quoted plan statement the standard PR flow applies), and it never authorizes any
Claude-run path to the protected branch -- no standby/manual-merge handover, no
Claude-run merge or push to the protected branch, ever. Everything else in this
step -- the phase push, the merge into integration, the branch delete, and the
zero-commit rule -- is unchanged.

## Step 9: Next phase

If the user asks for the next phase's implementation prompt, run
`/write_prompt <plan_name> <N+1>`, re-reading the PRD and plan first -- the
session may have been compacted.
