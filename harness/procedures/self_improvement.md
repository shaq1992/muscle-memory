# Procedure: Self-Improvement Spawn Flow

The shared flow for routing structural improvements discovered during a session
back into the workflow command files. Referenced by the grilling command (its
self-diagnosis step), by the closing sequence of every phase implementation
prompt, and by the orchestrator's self-improver spawn (`commands/orchestrator.md`
Step 11) -- none of them restates it.

## Scope rule

Briefs cover ONLY structural issues with the command/workflow machinery itself:
template ambiguities, missing constraints, incorrect find patterns, Q&A-mechanics
defects -- things that would improve future sessions across all projects.
Project-specific or plan-specific notes do NOT belong here; those go in the
phase learnings file. Never propose changes to project domain logic or threshold
values through this flow.

## The flow

1. **Collect a brief.** Review the session's observations about the command being
   executed. Write a 3-5 bullet brief; each bullet names the specific file
   location and the change needed. If no structural issues were found, state that
   explicitly -- do not fabricate findings.

2. **Surface for approval.** Show the brief to the user and ask whether to
   proceed. The user approves or rejects each item individually, or skips
   entirely. If the user declines or there is nothing to improve, stop here.

3. **Spawn the self-improver sub-agent** with the approved items as the inline
   brief:

   ```python
   Agent(
       subagent_type="self-improver",
       prompt="<approved brief bullets, each with specific file location and change needed>"
   )
   ```

   The self-improver makes exactly one targeted change per invocation and
   COMMITS it in the harness repo at `.claude/` (one commit per invocation,
   message `improve: <file> -- <summary>`, on the currently checked-out branch
   -- the phase branch during a harness plan, local `main` otherwise). A
   commit on `main` is PUSHED immediately (`git -C .claude push origin main`),
   keeping the public harness repo synced with small improvements; phase-branch
   commits are never pushed by the improver -- the plan's closing sequence owns
   those, and major version-level improvements still arrive via orchestrated
   harness plans and their user-merged PRs. On a zip install with no harness
   repo, it states that fallback plainly and reports excerpts instead of a
   diff. Wait for it to return.

   **With the SIM notebook on** (the optional `sim_notebook` preferences key;
   the improver's first act is `sim.py locate`, whose one line it reports
   first, and on "off" or "configured but missing" it runs exactly the flow
   above, reviewer skipped -- a "missing" line is also passed on as a
   structural observation, never a block), the spawn becomes a DRAFT and the
   flow gains a review hop before anything is committed:

   a. **Draft.** The improver reads the notebook, cites a problem or proposes a
      new one, writes its prediction BEFORE editing, leaves the edit
      uncommitted and returns a `## Draft` (problem, prediction, diff, the
      cited problem's history).
   b. **Review.** Spawn `Agent(subagent_type="sim-reviewer", ...)` with the
      approved brief, the history, the draft diff and the prediction. It
      returns accept, revise or reject with reasons.
   c. **Revise once.** On `revise`, resume the same improver (SendMessage)
      with the reasons; it redrafts once; review again. A second `revise` is
      handled as a reject.
   d. **Relay to the user.** Show the verdict and reasons. On a reject, the
      user may override in one word. If the draft proposes a new problem, ask
      the user to confirm it or pick an existing P-ID (a problem is opened
      only on the user's yes).
   e. **Finish.** Resume the same improver with the final verdict, its
      reasons, the user's word and the problem answer. It commits (accept or
      override) or restores its draft (kept reject), appends exactly ONE
      attempt through `sim.py` either way, and pushes the notebook. If it
      cannot be resumed, spawn a fresh self-improver in FINISH mode with the
      `## Draft` and that relay; the edit is still in the working tree.

4. **Surface the response.** Show the sub-agent's full response to the user
   (with SIM on, the FINISH response, which adds a `## SIM` section):
   `## Changes Made` (the commit hash + message and the commit's git diff; on
   the no-repo fallback, old/new excerpts) + `## Drift Warnings and Proposed
   Fix`.

5. **One-level drift cascade.** If Drift Warnings are present, show the suggested
   briefs for each affected command. For each warning the user accepts, spawn ONE
   additional self-improver invocation targeting the flagged command, using the
   suggested brief as-is. Secondary invocations never trigger further spawns --
   the cascade is exactly one level deep. Most sessions produce no Drift
   Warnings.

## Jurisdiction

The self-improver edits workflow machinery files only. `.claude/preferences.md`
is OUT of jurisdiction -- project opinion is edited by the user in normal
sessions, never by the improvement loop. (The self-improver's own instructions file is the
authoritative statement of its corpus and boundary.)
