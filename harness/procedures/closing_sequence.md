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
blocks the closing turn until a file at that exact path exists on disk, so any
drift between the two dates is a false-negative block.

**Marker + Stop-hook interplay.** The marker is read by the
`enforce_phase_closing.py` Stop hook (registered in `.claude/settings.json`,
invoked via `venv/bin/python`). Mechanics:
- No marker present, or a marker whose `session_id` does not match the current
  session, is a structural no-op -- the hook allows unconditionally. A marker
  left by an abandoned session never blocks other sessions.
- If the marker matches the current session and the file at `learnings_path`
  does not exist, the hook BLOCKS the closing turn with a reason; it re-blocks
  on every retry until the file exists (the block condition is fully within the
  model's control, so this is intended behavior, not a runaway loop).
- Once the learnings file exists, the hook self-deletes the marker and allows.
Write the marker unconditionally, even if unsure whether the hook is registered
-- the marker is inert without it.

Then create the learnings file at the marker's `learnings_path`, with exactly
this schema:

```
**Branch:** <branch name active during this phase>

## Carry Forward
(bullets injected into all future phase prompts for this plan -- ONLY this
section is read by the prompt writer; bias toward including here when uncertain)
- bullet
- ...

## Phase-Specific Only
(everything relevant only to this phase; not injected anywhere)
```

The `**Branch:**` line is mandatory and must be the first line of the file,
before `## Carry Forward`. Populate it with the actual git branch this phase
worked on -- the phase branch per git_strategy.md naming, or `main` for
local-only phases (run `git branch --show-current` if uncertain). This is the
only mechanism by which other commands (e.g. `/jira_and_status_update`'s grep
for `**Branch:**`) can discover which branch a plan's work landed on without ad
hoc lookups. Only the `## Carry Forward` section is extracted into future
prompts; the `**Branch:**` line is never injected downstream.

Bias toward Carry Forward when uncertain -- a spurious bullet in a future prompt
is less harmful than missing a load-bearing constraint.

The learnings file lives in `docs/learnings/`, which is gitignored -- never
commit it.

## Step 5: Commit

[For no-commit / local-only phases: skip the instructions below entirely. State
plainly that there is nothing to commit this phase, and name why (e.g. "all
deliverables are gitignored -- .claude/, context/, docs/ outputs"). Do not stage
or run any git commit command, except any single tracked edit the plan itself
explicitly mandates.]

Before staging any enumerated artifact from the plan's Deliverables (e.g.
retrained model pkls, training summaries, cache DBs, generated CSVs, benchmark
JSONs), verify each path is git-tracked -- run `git check-ignore <path>` (exit 0
means gitignored, exit 1 means tracked or tracked-eligible). Treat model/data
build outputs as "stage only if tracked in this repo" -- do not attempt to stage
a path the project gitignores. If this phase's build outputs are gitignored, the
phase's durable committable output is the code/test changes only; state that
plainly in the commit report.

Stage and commit the phase's tracked changes. If `.claude/` is gitignored in
this project, any self-improver edits to command files are local-only -- nothing
to stage for that path.

Commit message: `feat: <plan_name> phase <N> -- <brief description>`. No AI
attribution anywhere, ever.

## Step 6: Autonomous git close

(Replaces the old standby/handover step. Full law: `git_strategy.md`; parameters
from `preferences/git_parameters.md`.)

For local-only phases: nothing to push. Confirm the phase ends on the expected
branch (`git branch --show-current`) and tell the user where the phase's
outputs live (the gitignored paths written this phase).

For committing phases, perform the autonomous close -- no user confirmation, no
surfacing of commands for manual execution:

1. Push the phase branch to origin.
2. `git checkout integration/<plan_name>`, then
   `git merge --no-ff <phase-branch> -m "merge: <plan_name> phase <N> -- <brief description>"`.
3. Push the integration branch.
4. Delete the phase branch, remote and local.

Report each operation's outcome (hashes, branch states) to the user.

If `is_final_phase` is true: after the integration merge lands, request
EXPLICIT user permission for the single integration-to-main merge + main push.
This is permission-gated always, even in auto mode -- never assume or infer it.
If permission is withheld, the integration branch stays as the artifact and the
plan closes without touching main.

## Step 7: Next phase

If the user asks for the next phase's implementation prompt, run
`/write_prompt <plan_name> <N+1>`, re-reading the PRD and plan first -- the
session may have been compacted.
