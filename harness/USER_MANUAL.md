# Workflow Command User Manual

The `.claude/` directory is a portable-by-design, multi-session development workflow
system for Claude Code: three grilling modes, a reference-based phase compiler, a unified
integration-branch git strategy with a deterministic guardrail hook and a user-only
approval marker, a slim per-turn CLAUDE.md, and a two-surface glossary. Commands plan,
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
                              preferences/ (portable preference templates)
    scripts/               -- setup_credential_helper.sh, git_credential_env.sh,
                              make_portable_zip.sh
    tests/                 -- local pytest for hooks/helpers (never committed)
  preferences/    -- PROJECT-SPECIFIC per-concern files + INDEX.md; user-edited, out of
                     self-improver jurisdiction; commands state a fallback when a file is
                     absent (this is what makes the system portable by design)
  approvals/      -- user-created approval markers gating integration-to-main merges
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
- **Per-project, generated fresh (never copied from a source project):** `preferences/`
  (complete files generated from the portable templates under
  `harness/templates/preferences/`), root `CLAUDE.md` (from `claude_md_skeleton.md`),
  `approvals/`, `context/`, `docs/`.

A raw `cp -r .claude/ <new-project>` is NOT a supported port -- it drags the source
project's filled preferences and project-specific CLAUDE.md into the new project.
`/bootstrap_to_custom_commands` is the ONLY supported porting (and upgrade) mechanism; it
regenerates the per-project subset blank.

## Setup / upgrade a project

`/bootstrap_to_custom_commands [target_dir]` is the single install-and-upgrade lifecycle
command (there is no separate port command):

- **Install** (fresh target): copies the portable subset, generates preference files from the
  portable templates (`harness/templates/preferences/`), generates a root CLAUDE.md from the
  skeleton template, creates docs/ + context/,
  wires the guardrail + phase-closing hooks and the .env/approvals deny rules, and walks
  through the one-time credential-helper registration.
- **Upgrade** (re-run on an existing project): refreshes the portable subset verbatim and
  leaves every per-project file untouched -- existing preferences and an existing filled
  CLAUDE.md are NEVER overwritten.

After an install: fill in `CLAUDE.md` and the `.claude/preferences/` files, then start a
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
in this exact order: (1) tracer-bullet batch (1-4 slicing questions in one turn), (2)
behavioral-test ratification (which phases get a `### Behavioral Tests` block and what it
tests), (3) decision log + your confirmation (the single final gate), (4) glossary sweep
(ratify coined terms, propose retirements), (5) self-diagnosis, (6) write documents.
Functional mode skips steps 1-2.

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
learnings file to `docs/learnings/DDMMYY/`, commit, and the autonomous git close.

### 4-6. Track / audit / verify

- `/jira_and_status_update [DDMMYY]` -- Jira tickets + standup from the git log (discovers
  branches via the learnings files' `**Branch:**` lines). Output in
  `docs/jira_and_standup/DDMMYY/`.

(Some projects add optional audit/verification commands here -- e.g. a codebase-audit or an
end-to-end pipeline-verification command. These are project-specific and are not bootstrapped
into every repo; this project ships none. Add their descriptions here if and when they are
introduced.)

## Git strategy (autonomy + the approval marker)

Full law: `harness/procedures/git_strategy.md`; parameters: `preferences/git_parameters.md`.

- **Unified integration-branch strategy.** A plan cuts `integration/<plan_name>` from `main`
  in its first phase; phase branches (`<plan_name>-phase-NN`, zero-padded) branch from it and
  merge back into it. `main` is untouched until the end.
- **Autonomous phase-level git** (no confirmation): push the phase branch, `--no-ff` merge
  into integration with an explicit `-m "merge: ..."` message, push integration, delete the
  phase branch (remote + local).
- **Permission-gated final merge** (always, even in auto mode): the single
  integration-to-main merge + push of main, once per plan.

### The guardrail hook + approval marker

`.claude/hooks/git_guardrails.py` (PreToolUse on Bash) deterministically blocks
`git push --force`, `git reset --hard`, `git branch -D`, `git clean -f`, and any `git merge`
on `main` or push targeting `main` UNLESS the approval marker exists. Claude is mechanically
unable to create the marker (settings.json deny rules + a hook backstop on the approvals
path).

To approve the final merge, YOU create the marker in-session with a `!`-prefixed command
(replace `<plan_name>`):

```
! touch .claude/approvals/<plan_name>_main_merge.json
```

The session then issues the merge and push as ONE compound command (the marker is consumed
by the merge, so they must not be split):

```
git merge --no-ff integration/<plan_name> -m "merge: ..." && git push origin main
```

The hook deletes the marker after the allowed merge (one-shot, per plan). Do NOT inspect the
approvals directory via Bash -- the hook denies any Bash command referencing it.

### PAT isolation

Pushes authenticate via the repo-local credential helper
`.claude/harness/scripts/git_credential_env.sh` (registered once by
`setup_credential_helper.sh`), which reads `GIT_PAT` from `.env` at push time. The token
never enters a command line, tool output, or transcript. No session reads `.env` (deny rules
block it); `GIT_PAT` must already be saved there.

## Phase-closing enforcement (Stop hook)

`.claude/hooks/enforce_phase_closing.py` mechanically enforces the "write learnings file"
obligation. The closing sequence writes `.claude/phase_closing.json` (session_id, plan,
phase, expected learnings path). On Stop: no marker (or a different session's marker) is a
no-op; a matching marker blocks the closing turn until the learnings file exists, then the
hook self-deletes the marker and allows. Full mechanics: `closing_sequence.md` step 4.

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
  ALL project specifics live in `preferences/` (with stated fallbacks). Porting is bootstrap,
  never a raw copy.
- **Slim per-turn surfaces.** CLAUDE.md is a ~120-150 line protective skeleton (repo-recovery
  test: a fact survives only if the repo cannot recover it); descriptive knowledge lives in
  local `context/`; mechanical detail is deleted and re-derived by Explore.
- **Self-improving commands.** Structural fixes discovered during sessions route through the
  self-improver sub-agent (`harness/procedures/self_improvement.md`); its jurisdiction is
  `commands/`, `agents/`, `harness/`, `hooks/` -- `preferences/` is out of jurisdiction.
- **Everything AI-facing is gitignored.** `.claude/`, CLAUDE.md, docs/, context/, and
  `.claude_archive/` are all local-only. Only project code is committed.

## Commands reference

| Command | When to use | Key outputs |
|---------|-------------|-------------|
| /grilling_session | Planning any feature or change (mixed / functional / technical) | PRD + plan in docs/ |
| /write_prompt | Ready to implement a phase | Reference-based prompt in docs/prompts/DDMMYY/ |
| /jira_and_status_update | After work lands | Tickets + standup in docs/jira_and_standup/ |
| /bootstrap_to_custom_commands | Installing OR upgrading the harness in a project | Portable harness + fresh per-project scaffolding |
