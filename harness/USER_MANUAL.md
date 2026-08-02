# Workflow Command User Manual

The `.claude/` directory is a portable-by-design, multi-session development workflow
system for Claude Code: three grilling modes, a reference-based phase compiler, a
PR-based integration-branch git strategy with a deterministic guardrail hook (every
plan ends in a pull request merged by the USER), a slim per-turn CLAUDE.md, and a
two-surface glossary. Commands plan,
implement, and track work across sessions -- most non-trivial tasks cannot finish inside
one context window.

> Location note: this manual lives at `.claude/harness/USER_MANUAL.md` (out of
> `.claude/commands/` so it never pollutes the per-turn skills listing).

## Layout

```
.claude/
  commands/       -- invocable commands ONLY (everything here shows in the skills listing)
  agents/         -- workflow agents (self-improver)
  hooks/          -- deterministic hooks: enforce_phase_closing.py, git_guardrails.py
  harness/        -- portable, read-only-in-daily-use machinery
    USER_MANUAL.md         -- this file
    INSTALL.md             -- porting/distribution guide (offline-zip + in-place install)
    harness_glossary.md    -- vocabulary owned by the command system
    procedures/            -- git_strategy, closing_sequence, monitoring,
                              verification_cases, self_improvement (portable law)
    templates/             -- prd_schema, plan_schema, claude_md_skeleton,
                              preferences_template.md (portable preferences template)
    scripts/               -- make_portable_zip.sh
    tests/                 -- stdlib-unittest suite for the hooks
                              (python3 -m unittest discover .claude/harness/tests)
  preferences.md  -- PROJECT-SPECIFIC single opinion surface (machine key block + short
                     prose sections); user-edited, out of self-improver jurisdiction;
                     consumers state a fallback when it is absent (this is what makes
                     the system portable by design)
  settings.json   -- permissions (deny rules) + hook registration
CLAUDE.md         -- per-turn protective skeleton (project root; generated from the skeleton
                     template, then filled by the user)
context/          -- durable local-only project knowledge: architecture.md, decisions.md,
                     glossary.md
.claude_archive/  -- rollback snapshot of a pre-plan .claude/ + CLAUDE.md
```

Everything above is gitignored -- AI-facing scaffolding never enters version control.

## Portable vs. per-project (the porting boundary)

- **Portable, copied verbatim:** `harness/`, `commands/`, `agents/`, `hooks/`.
- **Per-project, generated fresh (never copied from a source project):** `preferences.md`
  (a complete file generated from the portable template
  `harness/templates/preferences_template.md`), root `CLAUDE.md` (from
  `claude_md_skeleton.md`), `context/`, `docs/`.

A raw `cp -r .claude/ <new-project>` is NOT a supported port -- it drags the source
project's filled preferences.md and project-specific CLAUDE.md into the new project.
`/bootstrap_to_custom_commands` is the ONLY supported porting (and upgrade) mechanism; it
regenerates the per-project subset blank.

## Setup / upgrade a project

`/bootstrap_to_custom_commands [target_dir]` is the single install-and-upgrade lifecycle
command (there is no separate port command):

- **Install** (fresh target): copies the portable subset, generates `preferences.md` from
  the portable template (`harness/templates/preferences_template.md`), generates a root
  CLAUDE.md from the skeleton template, creates docs/ + context/, and wires the guardrail +
  phase-closing hooks and the .env deny rules.
- **Upgrade** (re-run on an existing project): refreshes the portable subset verbatim and
  leaves every per-project file untouched -- an existing preferences.md and an existing
  filled CLAUDE.md are NEVER overwritten.

After an install: fill in `CLAUDE.md` and `.claude/preferences.md`, then start a
`/grilling_session`.

For an offline hand-off to a machine that cannot see this project, the portable subset can
be shipped as a curated zip (produced by `.claude/harness/scripts/make_portable_zip.sh`,
which packs only `harness/`, `commands/`, `agents/`, `hooks/` plus `INSTALL.md`) and
installed in place: the recipient extracts it at their project root and runs
`/bootstrap_to_custom_commands` with no argument, which regenerates the per-project
scaffolding. Full recipient instructions and pre-requisites are in
`.claude/harness/INSTALL.md`.

## The workflow (typical arc)

### 1. Plan with /grilling_session

```
/grilling_session <plan_name> [functional | technical]
```

Reads the glossaries at start so established shorthand is spoken natively, then interviews
you with structured multiple-choice questions. Three modes:

- **mixed** (bare, no mode token): grills both what/why and how, then writes the PRD +
  plan in one pass. This is the regression baseline -- byte-for-byte the old behavior.
- **functional**: grills ONLY the what/why; writes `docs/prds/<plan>_prd.md` with the
  functional sections and a `## Technical Parking Lot` for any technical aside (non-binding);
  writes no plan.
- **technical**: reads the existing functional PRD, grills ONLY the how, APPENDS technical
  sections (append-only -- never rewrites functional sections; a conflict is surfaced, not
  silently edited), and writes the plan.

Mode preconditions are confirm-and-proceed (never halt, never silently adapt). Outputs:
`docs/prds/<plan>_prd.md` (schema: `harness/templates/prd_schema.md`) and, for mixed/
technical, `docs/multi_phase_plans/<plan>_plan.md` (schema: `plan_schema.md`). Each phase
is sized to fit one session.

**Stop-sequence choreography.** When you type "stop asking questions", mixed/technical run,
in this exact order: (1) slicing + behavioral-test ratification in one combined turn (1-4
tracer-bullet questions plus which phases get a `### Behavioral Tests` block and what each
tests), (2) decision log + phase table, with glossary and self-diagnosis one-liners
appended, all under your single confirmation (the final gate), (3) write documents.
Functional mode skips step 1.

### 2. Generate a session prompt with /write_prompt

```
/write_prompt <plan_name> <phase_number>
```

The phase compiler: writes a reference-based implementation prompt (~200 lines, not ~800)
to `docs/prompts/DDMMYY/`. It inlines ONLY phase-specifics -- objective, deliverables, DoD,
`### Behavioral Tests` verbatim, filtered accumulated learnings, and a resolved-parameters
block (concrete branch names, learnings path, verification case) -- and @-references
`harness/procedures/*` for all stable law. Every generated prompt therefore executes CURRENT
procedure law, never a stale copy.

### 3. Implement in a fresh session

Open a new session in "accept edits" mode and paste the generated prompt. Claude implements
the deliverables (writing any contracted behavioral tests FIRST and running them RED before
implementing to green), then runs the closing sequence
(`harness/procedures/closing_sequence.md`): self-improvement brief, phase-closing marker +
learnings file to `docs/learnings/DDMMYY/`, ledger merge + stamp
(`docs/learnings/<plan>_ledger.md`), user-gated document reconciliation, commit, and the
autonomous git close.

### 4-6. Track / audit / verify

- `/jira_and_status_update [DDMMYY]` -- Jira tickets + standup from the git log (discovers
  branches via the learnings files' `**Branch:**` lines). Output in
  `docs/jira_and_standup/DDMMYY/`.

(Some projects add optional audit/verification commands here -- e.g. a codebase-audit or an
end-to-end pipeline-verification command. These are project-specific and are not bootstrapped
into every repo; this project ships none. Add their descriptions here if and when they are
introduced.)

## Git strategy (the PR law)

Full law: `harness/procedures/git_strategy.md`; parameters: `preferences.md`'s key block.

- **Unified integration-branch strategy.** A plan cuts `integration/<plan_name>` from the
  default branch in its first phase; phase branches (`<plan_name>-phase-NN`, zero-padded)
  branch from it and merge back into it. The protected branch is never touched by Claude.
- **Autonomous phase-level git** (no confirmation): push the phase branch, merge into
  integration with git defaults and an explicit `-m "merge: ..."` message, push
  integration, delete the phase branch (remote + local, `-d`). A phase branch with zero
  commits skips push/merge/delete and reports "no tracked changes this phase".
- **Plan-end PR, merged by YOU.** At the final phase Claude pushes the integration branch
  and opens a pull request with `gh pr create` (autonomous; no AI attribution in the PR
  title/body). You merge it in-session with a `!`-prefixed command -- the keystroke is the
  approval and its output lands in the transcript:

  ```
  ! gh pr merge <n> --merge
  ```

  Merge defaults come from the `merge_style` / `retain_integration_branch` preference keys
  (merge-commit; integration branch kept -- deletion is per-plan opt-in). Post-PR review
  fixes are committed directly on the integration branch and pushed; the open PR tracks
  them.

### The guardrail hook

`.claude/hooks/git_guardrails.py` (PreToolUse on Bash, stdlib python3) deterministically
blocks: destructive ops (`git push --force`, `git reset --hard`, `git branch -D`,
`git clean -f`); every Claude-initiated path to the protected branch (`git merge` on it,
any push targeting it, `gh pr merge` -- PR merges are yours alone); and, fail-closed, any
harness-repo push whose remote does not match the `harness_push_remote` allowlist key
(key absent = all harness pushes blocked). Repo context is attributed correctly for
`git -C` and `cd`-form commands.

### Identity and auth

All GitHub auth goes through the gh CLI (`gh auth login`) -- no tokens in `.env`, no
credential-helper scripts. Multi-account setups pin each repo's identity with repo-local
git config (an inline credential helper that queries `gh auth token --user <pinned-user>`,
plus `credential.username`) so pushes never depend on gh's active-account state; see
git_strategy.md's "Identity and auth" section. `.env` read-deny rules remain in
settings.json.

## Phase-closing enforcement (Stop hook)

`.claude/hooks/enforce_phase_closing.py` mechanically enforces the "write learnings file"
obligation. The closing sequence writes `.claude/phase_closing.json` (session_id, plan,
phase, expected learnings path). On Stop: no marker (or a different session's marker) is a
no-op; a matching marker blocks the closing turn until the learnings file exists in the
required schema (`**Branch:**` first line, `## Learnings` header) and the plan ledger's
`Last merged: phase NN` stamp matches the marker's phase, then the hook self-deletes the
marker and allows. Each block reason names the specific failed check. Full mechanics:
`closing_sequence.md` steps 4-5.

## Glossaries

Two surfaces, both read at grilling-session start:

- `harness/harness_glossary.md` -- vocabulary owned by the command system (portable, travels
  with the harness).
- `context/glossary.md` -- the per-project domain glossary.

Terms are coined freely mid-session and ratified at the end-of-session glossary sweep, which
is also the only point terms are retired. Anti-rot rules: definitions not documentation (1-2
lines; longer needs a pointer), every entry earns its place, no over-seeding a term whose
meaning is guessable from its words.

## Key design principles

- **Single-source law.** Document schemas live in `harness/templates/`; procedures (git,
  closing, monitoring, verification, self-improvement) live in `harness/procedures/`.
  Commands reference them rather than restate them, so a fix lands once and every consumer
  executes current law.
- **Portable by design.** `harness/`, `commands/`, `agents/`, `hooks/` are project-agnostic;
  ALL project specifics live in `preferences.md` (with stated fallbacks). Porting is
  bootstrap, never a raw copy.
- **Slim per-turn surfaces.** CLAUDE.md is a ~120-150 line protective skeleton (repo-recovery
  test: a fact survives only if the repo cannot recover it); descriptive knowledge lives in
  local `context/`; mechanical detail is deleted and re-derived by Explore.
- **Self-improving commands.** Structural fixes discovered during sessions route through the
  self-improver sub-agent (`harness/procedures/self_improvement.md`); its jurisdiction is
  `commands/`, `agents/`, `harness/`, `hooks/` -- `preferences.md` is out of jurisdiction.
- **Everything AI-facing is gitignored.** `.claude/`, CLAUDE.md, docs/, context/, and
  `.claude_archive/` are all local-only. Only project code is committed.

## Commands reference

| Command | When to use | Key outputs |
|---------|-------------|-------------|
| /grilling_session | Planning any feature or change (mixed / functional / technical) | PRD + plan in docs/ |
| /write_prompt | Ready to implement a phase | Reference-based prompt in docs/prompts/DDMMYY/ |
| /jira_and_status_update | After work lands | Tickets + standup in docs/jira_and_standup/ |
| /bootstrap_to_custom_commands | Installing OR upgrading the harness in a project | Portable harness + fresh per-project scaffolding |
