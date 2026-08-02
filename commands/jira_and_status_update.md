---
description: Write Jira tickets and a standup update for all work done on a given date.
argument-hint: [DDMMYY] [custom instructions free text] (e.g. /jira_and_status_update 240626 one ticket only, attaching notebook)
# allowed-tools is advisory (not enforced by Claude Code); kept accurate as documentation
allowed-tools:
  - Bash(git*)
  - Bash(find*)
  - Bash(mkdir*)
  - Read
  - Write
  - Agent
---

Write Jira tickets and a standup update for work done on a given date, then save the output to a dated file.

## Instructions

Follow these steps exactly, in order.

### Step 1 -- Parse arguments

`$ARGUMENTS` is parsed as follows:

- If the first token is exactly 6 digits and forms a valid date (DDMMYY), it is the **target_date**.
- If no such token is found, **target_date** = today's date.
- Everything after the DDMMYY token (or all of `$ARGUMENTS` if no date token) = **custom_instructions**. May be empty.

Derive:
- **target_ddmmyy**: target date in DDMMYY (e.g. `240626`)
- **target_yyyy_mm_dd**: same date as YYYY-MM-DD for git commands. Parse as DD=chars 1-2, MM=chars 3-4, YY=chars 5-6, YYYY=20YY. (e.g. `240626` -> `2026-06-24`)
- **exec_ddmmyy**: today's date in DDMMYY format -- used for the output file path, always today regardless of target date
- **target_display**: target date written as "DD Month YYYY" (e.g. `24 June 2026`) -- used in the output file header

Output file: `docs/jira_and_standup/<exec_ddmmyy>/jira_and_standup_<exec_ddmmyy>.md`

### Step 2 -- Gather context

Run the following, parallelising where possible.

**2a. Git log on main for the target date (non-merge commits):**
```bash
git log main --no-merges --since="<target_yyyy_mm_dd> 00:00:00" --until="<target_yyyy_mm_dd> 23:59:59" --format="%h %s"
```

**2b. Git log on main for the target date (merge commits only):**
```bash
git log main --merges --since="<target_yyyy_mm_dd> 00:00:00" --until="<target_yyyy_mm_dd> 23:59:59" --format="%h %s"
```

**2c. Full commit detail for each non-merge commit:**
For each hash found in 2a, run:
```bash
git show <hash> --stat
```
Also read the full commit message body (not just subject) for any commit that has one.

**2d. Read CLAUDE.md Project State section in full** -- authoritative record of evaluated-but-not-adopted work and current feature state.

**2e. Check for learnings files on the target date:**
```bash
find docs/learnings/<target_ddmmyy> -name "*.md" 2>/dev/null | sort
```
Read each file found. These contain phase-level outcome detail including gate decisions and validation numbers.

**2f. Check for same-day work on permanent analysis/experiment branches:**
Some work (e.g. report or deliverable tracks) lives entirely on a permanent branch that
never merges to main, so 2a/2b alone will miss it. Recover it from the learnings files
already read in 2e:

1. Grep the learnings files found in 2e for a line matching `**Branch:**`:
```bash
grep -h "^\*\*Branch:\*\*" docs/learnings/<target_ddmmyy>/*.md 2>/dev/null | sort -u
```
2. For each distinct branch name found that is not `main`, run:
```bash
git log <branch> --no-merges --since="<target_yyyy_mm_dd> 00:00:00" --until="<target_yyyy_mm_dd> 23:59:59" --format="%h %s"
```
3. Fold the resulting commits into the same context used for Step 3's ticket-boundary
reasoning, alongside the main-branch commits gathered in 2a/2b.

This is for internal context-gathering only -- it does not change what is allowed in the
final Description/Comment text. The Hardcoded Output Constraints below still apply in full:
branch names (including these analysis/experiment branch names) are never surfaced in
ticket output.

**2g. Identify and read relevant PRDs and plans:**
Based on plan names appearing in learnings filenames or commit messages, read the corresponding files in `docs/prds/` and `docs/multi_phase_plans/` for background context. These are never referenced or named in any output.

### Step 3 -- Ticket planning gate

After gathering context from Step 2, do NOT immediately write ticket descriptions.

First, reason about ticket boundaries internally:

Review all context from Step 2. Identify the set of independently deliverable units of work done on the target date. A separate ticket is warranted for:
- A feature track that shipped (enrichment + tests + retrain)
- A feature track that was fully evaluated but not adopted
- A standalone bug fix
- A refactor or infrastructure change with distinct scope

Note: some commits (e.g. gate chore commits, cleanup commits) belong inside an existing ticket's description rather than forming their own ticket. Use judgment.

For each ticket, determine:
- Whether `custom_instructions` mentions an attachment (notebook, PDF, HTML, etc.) -- if so, the Comment block must reference it

If `custom_instructions` specifies ticket count or topics, apply that guidance -- it overrides autonomous reasoning.

Then, output the proposed ticket list to the user -- one line per ticket in this format:

```
Proposed tickets:
1. <Title> -- <one sentence describing what the change does and why it matters>
2. <Title> -- <one sentence describing what the change does and why it matters>
...
```

Wait for the user (address them by the `user_name` key of `.claude/preferences.md`, read at execution time) to:
- Select a subset (e.g. "1 and 3", "all", "just 2")
- Give feedback on titles or scope
- Or confirm the full list as proposed

Write full Jira descriptions and the standup update **only for the selected tickets**. Do not proceed to Step 4 until a selection is confirmed.

### Step 4 -- Write the output file

Create `docs/jira_and_standup/<exec_ddmmyy>/` if it does not exist. Write the file below for the selected tickets only, overwriting if it exists.

---

Template:

```
# Jira Tickets and Standup -- <target_display>

---

## Ticket <N>: <Title>

**Description:**

[Subsections in bold per logical area. Rules:
- Shipped feature track: describe what was built, the data sources or inputs involved, the key implementation decisions and why, and the validation evidence (what was tested and the measured outcome). Focus on evidence and outcome.
- Evaluated-but-not-adopted work: describe the option assessed, the outcome metric, and the reason for not adopting (e.g. worse on the target metric, insufficient data quality). Never name the branch.
- Bug fix: describe root cause, the fix applied, and what tests now cover it.
- Refactor: describe what changed structurally and what is preserved for callers.
No internal plan names. No docs/ paths. No learnings file references.]

**Comment:**

[1-3 sentences summarising outcome, suitable for pasting as a Jira comment when marking Done. If custom_instructions mentions an attachment, include: "Attaching <attachment description> which contains <brief description of its contents>."]

---

[Repeat for each selected ticket]

---

## Standup Update

[2-3 sentences maximum. Lead with the key outcome or headline metric (what was built, what was found, what was gated out). Do not reference internal phase numbers (Phase 1, Phase 2, etc.) or any internal workflow steps -- describe outcomes only. If a Jira ticket was created, mention it naturally ("raised a ticket / logged a ticket"). If an attachment was added to the ticket, name it and briefly state what it contains. Written for a technical team audience who care about results, not process.]
```

---

### Step 5 -- Display output

After writing the file, display its full contents in-context so the user can review and copy directly.

### Step 6 -- Confirm

Tell the user:
- Full path of the file written
- Number of tickets written
- Target date covered
- Execution date (file date)

### Step 7 -- Self-diagnosis

After writing the file, self-diagnose this command:

"Did anything in this session -- across Steps 1-6 -- reveal a structural issue with this
command's ticket format, standup structure, context-gathering steps, or output file paths
that would improve future runs generally?"

**Scope:** ticket format, standup structure, context-gathering steps, output file paths.
Do NOT add domain-specific notes, project-specific heuristics, or session-specific
observations. Those belong in a learnings file or commit message.

**If nothing found:** Output "No self-improvements needed." and stop. Do not modify any file.

**If suggestions found:**

1. Output a numbered list. Each item must include:
   - The specific structural issue observed
   - The proposed fix
   - Rationale (why this would improve future runs, not just this one)

2. Surface the list to the user. Wait for per-item approval or rejection. The user may
   also skip the step entirely.

3. If any items are approved: spawn the self-improver sub-agent. Pass the approved items
   as an inline brief in the Agent() prompt parameter. The brief must name the target file
   (`.claude/commands/jira_and_status_update`) and describe each approved change with enough
   specificity that no further clarification is needed.

   Example brief format:
   ```
   Edit .claude/commands/jira_and_status_update: [change 1 description]. [change 2 description].
   ```

4. Wait for the sub-agent to return. Surface its full summary (Changes Made + Drift
   Warnings and Proposed Fix) to the user.

5. If the sub-agent returned Drift Warnings and the user accepts any of them: spawn one
   additional self-improver invocation per accepted warning, using the suggested brief from
   the warning as-is. These secondary invocations do not spawn further sub-agents.

---

## Hardcoded Output Constraints

These apply to all output regardless of custom_instructions:

- Never name deleted or unmerged branches
- Never name internal plan slugs (docs/ is gitignored; plan names are private)
- Never reference docs/prds/, docs/multi_phase_plans/, or docs/learnings/ paths in output
- Evaluated-but-not-adopted work: describe the feature and outcome without naming the branch
- Focus on what shipped to main; branch and workflow mechanics are internal
