---
description: Lightweight grill-then-build for tasks too small for a full plan. Runs a mixed-style grilling capped at 8 questions, writes a short brief to docs/quick/<slug>_brief.md, gates go/no-go via AskUserQuestion, then implements in-session on a quick/<slug> branch ending in a PR the user merges. No PRD, no plan, no ledger, no phase apparatus.
argument-hint: <slug> <task> (slug = short kebab-case slug max 20 chars; then describe the task + @file references)
---

Run a compressed grill-and-implement loop for the task described in $ARGUMENTS. This is
the lightweight sibling of `/grilling_session` for work that fits in one session and does
not warrant a PRD, a multi-phase plan, a ledger, or the phase-closing apparatus -- NONE of
those are produced here.

## Parse arguments

1. **slug** -- the FIRST token of $ARGUMENTS. Auto-normalize to a valid kebab-case slug
   (lowercase alphanumeric + hyphens, max 20 chars: lowercase, replace underscores/spaces
   with hyphens, strip invalid characters, truncate) and state the normalized slug in a
   one-line notice. If no slug is given, derive one from the task and state it.
2. **task** -- everything remaining. Read any @file references in full before your first
   question.

## Step 1 -- Grill (capped at 8 questions)

Mixed-style grilling (what/why AND how), HARD-CAPPED at 8 questions total. Follow the
grilling question format and rules from `/grilling_session` -- markdown multiple-choice
with 3-4 options plus "Other (describe)", recommendation after the options, batching of
up to 3 genuinely independent questions per turn, `linger` and asides handled the same
way -- but scaled down:

- Before any question that proposes file locations or git behavior, read `.gitignore` and
  `.claude/preferences.md` and answer from them instead of asking.
- Stop grilling as soon as the task is unambiguous -- the cap is a ceiling, not a quota.
  The user can also end grilling early with "stop asking questions".
- If 8 questions are not enough to pin the task down, say so plainly and recommend a full
  `/grilling_session` instead of guessing.

## Step 2 -- Write the brief

Write `docs/quick/<slug>_brief.md` (create `docs/quick/` if absent), SHORT by design:

```
# Quick Brief: <slug>

## Scope
[2-4 sentences: what is being built/changed and what is explicitly out]

## Decisions
[One bullet per grilling decision, with the user's elaborations captured verbatim
where they went beyond picking an option]

## Implementation outline
[Numbered steps: files to touch, changes per file, how it will be verified]
```

The brief is the ONLY document this command produces, and it doubles as the PR body
(Step 4) -- write it to stand alone for a PR reviewer.

## Step 3 -- Go/no-go gate

Gate through AskUserQuestion: proceed with the implementation as briefed / revise the
brief (free-text what to change) / abandon. Do not start implementing before the gate
clears. On revise, update the brief and re-gate.

## Step 4 -- Implement in-session

Git parameters come from `.claude/preferences.md`'s key block; the no-Claude-path-to-the-
protected-branch invariant of `harness/procedures/git_strategy.md` holds identically here.

1. Cut ONE short-lived branch `quick/<slug>` from the default branch.
2. Implement the brief in-session; commit on that branch (conventional messages, no AI
   attribution -- ever). Verify per the brief's outline and report results plainly.
3. Push the branch and open the PR with `gh pr create`, using the brief as the PR body
   source (title from the brief's scope line; no AI attribution in title or body).
4. The USER merges with a `!`-prefixed `gh pr merge <n> --merge` -- the keystroke is the
   approval. Claude never runs `gh pr merge`. If the merge is withheld, the branch and
   open PR are the durable artifacts.

No phase-closing marker, no learnings file, no ledger entry, no document reconciliation
-- the brief and the PR are the whole paper trail.
