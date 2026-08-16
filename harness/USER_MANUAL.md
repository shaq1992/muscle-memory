# Workflow Harness User Manual

The `.claude/` directory is a portable-by-design, multi-session development workflow
system for Claude Code: three grilling modes, a reference-based phase compiler, an
orchestrator for plans that cannot be specified up front, a PR-based
integration-branch git strategy with a deterministic guardrail hook (every plan ends
in a pull request merged by the USER), a rolling per-plan learnings ledger, a slim
per-turn CLAUDE.md, and a two-surface glossary. Commands plan, implement, and track
work across sessions -- most non-trivial tasks cannot finish inside one context
window.

This is the deep-reference tier of the documentation: `README.md` (harness repo root)
is the landing page, `harness/INSTALL.md` is the recipient install guide, and this
manual explains the whole system.

> Location note: this manual lives at `.claude/harness/USER_MANUAL.md` (out of
> `.claude/commands/` so it never pollutes the per-turn skills listing).

## The two layers: law vs opinion

The harness splits cleanly into two layers, and almost every question about "can I
edit this?" or "will an upgrade overwrite that?" is answered by knowing which layer a
file belongs to.

**Portable LAW** -- the machinery itself. Tracked in the harness git repo, shipped
verbatim to every recipient, identical in every project, and evolved only through the
self-improver flow (or upstream releases):

```
.claude/
  commands/       -- invocable commands ONLY (everything here shows in the skills listing)
  agents/         -- workflow agents (self-improver, investigator, experimenter,
                     garbage_collector)
  hooks/          -- deterministic hooks: git_guardrails.py, enforce_phase_closing.py,
                     enforce_handback.py, enforce_orchestrator_isolation.py
  harness/        -- read-only-in-daily-use machinery
    USER_MANUAL.md         -- this file
    INSTALL.md             -- recipient install guide (clone or zip, then /on_board)
    harness_glossary.md    -- vocabulary owned by the command system
    procedures/            -- git_strategy, closing_sequence, monitoring,
                              verification_cases, self_improvement, precedence,
                              comms (portable law)
    templates/             -- prd_schema, plan_schema, claude_md_skeleton,
                              state_schema, handback_schema,
                              preferences_template.md
    scripts/               -- validate_prompt.py, make_portable_zip.sh
    tests/                 -- stdlib-unittest suite for the hooks
                              (python3 -m unittest discover .claude/harness/tests)
  README.md       -- harness repo landing page
  VERSION         -- one-line harness version (see Versioning)
```

**Per-project OPINION** -- your choices about your project. Gitignored INSIDE the
harness repo (so pulls and upgrades can never clobber them), generated fresh from the
portable templates at install time, edited only by you, and permanently out of
self-improver jurisdiction:

```
.claude/
  preferences.md  -- the single opinion surface: a machine-parseable key block
                     (branches, merge style, interpreter, test command, encoding,
                     user_name, harness_push_remote) + short Verification and
                     Monitoring prose sections; consumers state a fallback when it
                     is absent (this is what makes the system portable by design)
  settings.json   -- permissions (deny rules) + hook registration, written with the
                     interpreter detected on YOUR machine
CLAUDE.md         -- per-turn protective skeleton (project root; generated from the
                     skeleton template, then filled by the user)
docs/             -- prds/, multi_phase_plans/, prompts/, learnings/, quick/,
                     orchestration/ outputs, plus the append-only observations.md
context/          -- durable local-only project knowledge: architecture.md,
                     decisions.md, glossary.md
```

In short: the law layer is opinionated about TOPOLOGY (how plans, branches, PRs, and
closing sequences work) and travels verbatim; the opinion layer is configurable about
SURFACE DETAILS (branch names, interpreters, test commands, your name) and never
travels. In the PROJECT repo, everything AI-facing (`.claude/`, CLAUDE.md, docs/,
context/) is gitignored -- only project code is committed there. The harness's own
version control is the nested repo at `.claude/` (clone tier) or nothing (zip tier).

## Install tiers, upgrades, versioning

Install = get the portable tree to `.claude/` (clone or zip), then run `/on_board` --
the single onboarding funnel. The install METHOD is the version-control choice:

- **Clone tier:** `.claude/.git` exists. The clone IS the versioning -- full upstream
  history plus your local commits (self-improver commits accumulate here). Upgrade =
  `git pull` in `.claude/`, then re-run `/bootstrap_to_custom_commands`. Local-only:
  no fork, no push story (a recipient's harness cannot push -- see the push-remote
  allowlist below).
- **Zip tier:** no git at all. Upgrade = re-extract the new zip, then re-run
  `/bootstrap_to_custom_commands`.

`/on_board` verifies prerequisites (git repo, gh auth, a python interpreter -- with a
permission-gated install offer and a one-time loud warning if declined, since the
deterministic guardrails need it), detects the tier (`.claude/.git` present = clone,
absent = zip), invokes `/bootstrap_to_custom_commands` to generate the per-project
scaffolding (preferences.md from the template, root CLAUDE.md from the skeleton,
docs/ + docs/quick/ + docs/comms/ + context/, .gitignore entries, settings.json with
the detected interpreter), elicits preferences values, offers an opt-in never-silent CLAUDE.md
assist, gives a short tour, and ends with a self-check that runs the unittest suite
and reports "harness vX.Y installed".

`/bootstrap_to_custom_commands` on its own is the in-place scaffolding step: re-run
it after any upgrade -- idempotent, never overwrites an existing preferences.md or
CLAUDE.md. Full recipient instructions, the owner-port recipe (same-machine local
clone + manual preferences.md copy + /bootstrap), and prerequisites are in
`.claude/harness/INSTALL.md`.

**Versioning:** the one-line `VERSION` file at `.claude/VERSION` is bumped in the
same commit as a matching git tag on the harness repo; releases are tags. `/on_board`
reports the installed version; README states the current one.

## The workflow (typical arc)

### 1. Plan with /grilling_session

```
/grilling_session <plan_name> [functional | technical]
```

Reads the glossaries at start so established shorthand is spoken natively, opens with
a 3-line controls legend (stop phrase, `linger`, asides), then interviews you with
structured multiple-choice questions -- up to 3 per turn when genuinely independent.
Three modes:

- **mixed** (bare, no mode token): grills both what/why and how, then writes the PRD +
  plan in one pass.
- **functional**: grills ONLY the what/why; writes `docs/prds/<plan>_prd.md` with the
  functional sections and a `## Technical Parking Lot` for any technical aside
  (non-binding); writes no plan.
- **technical**: reads the existing functional PRD, grills ONLY the how, APPENDS
  technical sections (append-only -- never rewrites functional sections; a conflict is
  surfaced, not silently edited), and writes the plan.

Mode preconditions are confirm-and-proceed (never halt, never silently adapt).
Outputs: `docs/prds/<plan>_prd.md` (schema: `harness/templates/prd_schema.md`) and,
for mixed/technical, `docs/multi_phase_plans/<plan>_plan.md` (schema:
`plan_schema.md`). Each phase is sized to fit one session.

**Stop-sequence choreography.** When you type "stop asking questions", mixed/technical
run, in this exact order: (1) slicing + behavioral-test ratification in one combined
turn (1-4 tracer-bullet questions plus which phases get a `### Behavioral Tests`
block and what each tests), (2) decision log + phase table, with glossary and
self-diagnosis one-liners appended, all under your single confirmation (the final
gate), (3) write documents. Functional mode skips step 1.

### 2. Generate a session prompt with /write_prompt

```
/write_prompt <plan_name> <phase_number>
```

The phase compiler: writes a reference-based implementation prompt (~200 lines, not
~800) to `docs/prompts/DDMMYY/`. It inlines ONLY phase-specifics -- objective,
deliverables, DoD, `### Behavioral Tests` verbatim, learnings filtered from the plan
ledger, and a resolved-parameters block (concrete branch names, learnings path,
verification case) -- and @-references `harness/procedures/*` for all stable law.
Every generated prompt therefore executes CURRENT procedure law, never a stale copy.
Before reporting done it runs `harness/scripts/validate_prompt.py` (at-refs resolve,
no placeholder residue, required sections present, branch-name sanity) and fixes to
green.

### 3. Implement in a fresh session

Open a new session in "accept edits" mode and paste the generated prompt. Claude
implements the deliverables (writing any contracted behavioral tests FIRST and
running them RED before implementing to green), then runs the closing sequence
(`harness/procedures/closing_sequence.md`): self-improvement brief, phase-closing
marker + learnings file to `docs/learnings/DDMMYY/`, ledger merge + stamp, user-gated
document reconciliation, commit, and the autonomous git close.

### 4. Track with /jira_and_status_update

`/jira_and_status_update [DDMMYY]` -- Jira tickets + standup from the git log
(discovers branches via the learnings files' `**Branch:**` lines). Output in
`docs/jira_and_standup/DDMMYY/`.

### Long-running plans: /orchestrator

```
/orchestrator <plan_name> [additional text]
```

The third lane, for plans whose later steps are NOT knowable in advance. It replaces
steps 1-2 above with a single durable state file and dispatches one session at a time
-- see "The orchestrated lane" below. It does not replace the canonical arc: a plan
that can genuinely be specified up front should still be run as a PRD plus a phased
plan, which is the only path that produces a stakeholder-readable spec.

### Small tasks: /grill_and_implement

```
/grill_and_implement <slug> <task>
```

The lightweight sibling for tasks too small for a full plan: a mixed-style grilling
hard-capped at 8 questions (it recommends a full /grilling_session if that ceiling
is insufficient), a short brief written to `docs/quick/<slug>_brief.md` (carrying a
`## Behavioral tests` section when the work changes behavior), a go/no-go
gate, then in-session implementation on a `quick/<slug>` branch cut from the default
branch, push + `gh pr create` -- you merge the PR. The brief doubles as the PR body.
No PRD, no plan, no ledger, no phase apparatus; the no-Claude-path-to-protected-
branch invariant holds identically. It is also the command that RECEIVES an
orchestrated session prompt: handed a prompt carrying an `## Orchestration` block it
switches lanes automatically (see below). Absent that block it behaves exactly as
described here.

## The orchestrated lane

`/orchestrator <plan_name>` drives a plan from ONE document:
`docs/orchestration/<plan_name>_state.md`. For a plan run this way that file REPLACES
the PRD, the multi-phase plan, the learnings ledger and the per-phase learnings files
entirely. The canonical arc and its ledger enforcement are untouched and keep serving
canonical plans exactly as before.

Why a file rather than the conversation: context is a cache, and a cache can be
silently dropped by compaction. Every decision is written THROUGH to state before the
orchestrator replies, so a fresh session with zero history resumes from the file alone.
Schemas: `harness/templates/state_schema.md` (state) and
`harness/templates/handback_schema.md` (handback).

**The loop, as you actually run it:**

1. **`/orchestrator <plan_name>`** -- the same invocation initialises or resumes; the
   file's existence on disk is the only signal, so you never have to remember which
   mode you are in. Init is a grilling capped at FIVE questions covering the objective,
   its acceptance criteria, known invariants and gates, and the first committed session.
2. **You say "dispatch"** -- the orchestrator never dispatches on its own initiative.
   It authors the task body (stamped with a one-line TDD posture, warranted or
   optional, per your preferences.md task-type rule), selects the state rows the
   session must obey, and the
   dispatch script (`harness/scripts/assemble_dispatch.py`) writes the session prompt
   to `docs/prompts/DDMMYY/<plan_name>_session_<NN>_prompt.md` -- carrying a fixed
   `## Orchestration` block with the rows copied verbatim -- plus a dispatch manifest
   at `docs/orchestration/<plan_name>/dispatches/<NN>.json` (row IDs + the prompt
   file's SHA-256). The orchestrator records the expectation in the state file's
   `## Dispatched` BEFORE the session runs, and reports the path only -- never the
   prompt body. One tree-holding session at a time: while a session is outstanding, a
   second dispatch is refused by name rather than queued.
3. **You paste that prompt into a fresh session.** `/grill_and_implement` detects the
   `## Orchestration` block and runs as an orchestrated session: it writes a handback
   STUB at `docs/orchestration/<plan_name>/handbacks/<NN>.md` in minute one -- whose
   read receipt (row-ID list + prompt hash) is verified against the dispatch manifest
   by the closing hook -- works on
   `<plan_name>-session-<NN>` cut from `integration/<plan_name>`, merges back into
   integration, and opens NO PR of its own.
4. **You tell the orchestrator the session came back.** Ingest is mechanical: the
   handback's `## Delta` rows arrive pre-formatted in the state file's own table shape,
   and the ingest script (`harness/scripts/ingest_handback.py`, the orchestrator's pen)
   applies them verbatim -- nobody re-authors a row, and the orchestrator reads only the
   script's short summary. That is what keeps an ingest nearly free in context, which is
   what lets a plan run for months. The summary's last line reports `## Established`
   against the GC threshold (80 rows OR 45 KB); when it trips, the orchestrator offers
   at most ONE line suggesting a garbage-collection pass. GC never auto-runs: on your
   word the propose-only `garbage_collector` sub-agent returns retire / condense /
   promote batches, the orchestrator snapshots state to a dated archive FIRST, and you
   gate every batch -- promotion of a row into CLAUDE.md most explicitly of all.
5. **You declare the plan done.** Only then does the plan-end PR flow fire -- push
   integration, `gh pr create`, and you merge. Nothing else in this lane ever reaches
   the protected branch.

**The three legible end states** come from writing the handback stub early: a stub still
at `Status: OPEN` is positive evidence the session DIED, `PARTIAL` / `ABANDONED` is an
honest early exit, `COMPLETE` is a real close, and no file at all means the session was
never run. The abandon path deliberately costs about three lines -- a status field and
one sentence -- because an expensive escape hatch produces silent abandonment, not
better reports.

**Enforcement.** `.claude/hooks/enforce_handback.py` (Stop) blocks a dispatched
session's closing turn until a schema-valid handback exists at the path its marker names;
it and `enforce_phase_closing.py` are mutually exclusive by construction, reading
different marker files. `.claude/hooks/enforce_orchestrator_isolation.py` (PreToolUse on
Edit/Write/NotebookEdit) keeps an orchestrator session out of the implementation work --
an anti-drift guardrail, not a sandbox: a Bash heredoc bypasses it entirely, and it is
documented that way on purpose. Orchestrator markers are PER-PLAN
(`.claude/orchestrator_<plan_name>_session.json`), so orchestrators on different plans
run concurrently; a second orchestrator on the SAME plan is refused with the marker
path named -- deleting a dead orchestrator's marker is always your call, never a
heuristic's. The hook scans all per-plan markers, matches on session_id, and is
FAIL-CLOSED on a corrupt marker file: guarded writes are denied, for every session,
until you delete the named file.

**Structural observations.** Sessions report defects in the WORKFLOW MACHINERY (not in
your project's logic) under a closed tag vocabulary; they accumulate in one append-only
`docs/observations.md`, written by handback ingestion and by standalone
`/grill_and_implement` closes alike. When a tag reaches two occurrences anywhere in that
file, the orchestrator emits ONE line saying so. `/orchestrator improve` then runs in a
FRESH session with zero plan context and hands the approved items to the existing
self-improver flow unchanged -- sessions report, the orchestrator counts, execution
happens out of process.

**Delegation.** Long reads and corpus searches go to the `investigator` sub-agent, whose
isolation law (read-only outside the scratchpad, named do-not-touch paths, a hard output
budget, never the state file) lives in `agents/investigator.md` so it binds whether or
not the caller restated it. Research questions that reading alone cannot answer -- a
probe that must be written and RUN, or evidence fetched from the web -- go to its
sibling, the `experimenter`, which duplicates that discipline in
`agents/experimenter.md` and adds a write-and-run lane confined to the session
scratchpad (throwaway venv allowed inside it; no servers, no system-state changes).
Caller-side routing lives in `commands/orchestrator.md`'s "Delegating to sub-agents".

## Git strategy (the PR law)

Full law: `harness/procedures/git_strategy.md`; parameters: `preferences.md`'s key
block.

- **Unified integration-branch strategy.** A plan cuts `integration/<plan_name>` from
  the default branch in its first WORK UNIT; work-unit branches branch from it and
  merge back into it -- `<plan_name>-phase-NN` for a canonical phase,
  `<plan_name>-session-NN` for an orchestrated session, zero-padded either way. The
  protected branch is never touched by Claude.
- **Autonomous phase-level git** (no confirmation): push the phase branch, merge into
  integration with git defaults and an explicit `-m "merge: ..."` message, push
  integration, delete the phase branch (remote + local, `-d`). A phase branch with
  zero commits skips push/merge/delete and reports "no tracked changes this phase".
- **Plan-end PR, merged by YOU.** At the final phase Claude pushes the integration
  branch and opens a pull request with `gh pr create` (autonomous; no AI attribution
  in the PR title/body). You merge it in-session with a `!`-prefixed command -- the
  keystroke is the approval and its output lands in the transcript:

  ```
  ! gh pr merge <n> --merge
  ```

  Merge defaults come from the `merge_style` / `retain_integration_branch` preference
  keys (merge-commit; integration branch kept -- deletion is per-plan opt-in).
  Post-PR review fixes are committed directly on the integration branch and pushed;
  the open PR tracks them.

### The guardrail hook

`.claude/hooks/git_guardrails.py` (PreToolUse on Bash, stdlib python3)
deterministically blocks: destructive ops (`git push --force`, `git reset --hard`,
`git branch -D`, `git clean -f`); every Claude-initiated path to the protected branch
(`git merge` on it, any push targeting it, `gh pr merge` -- PR merges are yours
alone); and, fail-closed, any harness-repo push whose remote does not match the
`harness_push_remote` allowlist key (key absent = ALL harness pushes blocked, which
is exactly the recipient posture -- recipients never set the key). Repo context is
attributed correctly for `git -C` and `cd`-form commands.

### Identity and auth

All GitHub auth goes through the gh CLI (`gh auth login`) -- no tokens in `.env`, no
credential-helper scripts. Multi-account setups pin each repo's identity with
repo-local git config (an inline credential helper that queries
`gh auth token --user <pinned-user>`, plus `credential.username`) so pushes never
depend on gh's active-account state; see git_strategy.md's "Identity and auth"
section. `.env` read-deny rules remain in settings.json.

## Learnings: per-phase files + the ledger

Two surfaces with distinct jobs:

- **Per-phase learnings files** (`docs/learnings/DDMMYY/<plan>_phase_<NN>_learnings.md`)
  are immutable history: `**Branch:**` as the first line, one `## Learnings` header,
  then bullets. Learnings are carry-forward BY DEFINITION -- a learning not worth
  carrying forward is not a learning.
- **The plan ledger** (`docs/learnings/<plan>_ledger.md`) is current-truth-only: the
  ONE file /write_prompt reads for accumulated learnings. Bullets are grouped under
  theme headers, each stamped with its origin phase `(PN)`. At every phase close the
  session merges the new bullets in -- add, supersede (delete old + write new), delete
  stale -- and rewrites the mandatory `Last merged: phase NN` freshness stamp. The
  ledger may never hold two contradicting bullets; ambiguous supersessions are
  surfaced to you, never silently resolved.

An ORCHESTRATED plan has neither surface: its state file subsumes both, and a
dispatched session's handback replaces the per-phase learnings file and the ledger
merge outright.

## Phase-closing enforcement (Stop hook)

`.claude/hooks/enforce_phase_closing.py` mechanically enforces the "write learnings"
obligation. The closing sequence writes `.claude/phase_closing.json` (session_id,
plan, phase, expected learnings path). On Stop: no marker (or a different session's
marker) is a no-op; a matching marker blocks the closing turn until the learnings
file exists in the required schema (`**Branch:**` first line, `## Learnings` header)
and the plan ledger's `Last merged: phase NN` stamp matches the marker's phase, then
the hook self-deletes the marker and allows. Each block reason names the specific
failed check. Full mechanics: `closing_sequence.md` steps 4-5.

This hook serves CANONICAL phases only. Its orchestrated counterpart is
`enforce_handback.py`, which enforces the handback obligation instead; the two are
mutually exclusive by construction because they read different marker files
(`phase_closing.json` vs `handback_session.json`) and neither honors the other's. A
session writes one marker or the other, never both.

## Glossaries

Two surfaces, both read at grilling-session start:

- `harness/harness_glossary.md` -- vocabulary owned by the command system (portable,
  travels with the harness).
- `context/glossary.md` -- the per-project domain glossary.

Terms are coined freely mid-session and ratified at the end-of-session glossary
review inside the decision-log turn, which is also the only point terms are retired.
Anti-rot rules: definitions not documentation (1-2 lines; longer needs a pointer),
every entry earns its place, no over-seeding a term whose meaning is guessable from
its words.

## Key design principles

- **Single-source law.** Document schemas live in `harness/templates/`; procedures
  (git, closing, monitoring, verification, self-improvement) live in
  `harness/procedures/`. Commands reference them rather than restate them, so a fix
  lands once and every consumer executes current law.
- **Portable by design.** `harness/`, `commands/`, `agents/`, `hooks/` are
  project-agnostic; ALL project specifics live in `preferences.md` (with stated
  fallbacks). Porting is a clone (or zip) plus bootstrap, never a raw copy -- a raw
  `cp -r .claude/` would drag the source project's opinion layer along.
- **Deterministic where it matters.** Git safety and closing enforcement are stdlib
  python hooks with a unittest suite, not prompt-law -- they hold even when the model
  is having a bad day. Everything else is instructions.
- **Slim per-turn surfaces.** CLAUDE.md is a protective skeleton (repo-recovery test:
  a fact survives only if the repo cannot recover it); descriptive knowledge lives in
  local `context/`; mechanical detail is re-derived on demand.
- **Self-improving commands.** Structural fixes discovered during sessions route
  through the self-improver sub-agent (`harness/procedures/self_improvement.md`),
  which commits each accepted change in the harness repo; its jurisdiction is
  `commands/`, `agents/`, `harness/`, `hooks/` -- `preferences.md` is out of
  jurisdiction.

## Commands reference

| Command | When to use | Key outputs |
|---------|-------------|-------------|
| /grilling_session | Planning any feature or change (mixed / functional / technical) | PRD + plan in docs/ |
| /write_prompt | Ready to implement a phase | Validated reference-based prompt in docs/prompts/DDMMYY/ |
| /orchestrator | A plan whose later steps are not knowable up front (init, resume, dispatch, ingest) | State file in docs/orchestration/ + session prompts in docs/prompts/DDMMYY/ |
| /grill_and_implement | Task too small for a plan -- and the receiver of an orchestrated session prompt | Brief in docs/quick/ + a quick/<slug> PR you merge (orchestrated: a handback, no PR) |
| /jira_and_status_update | After work lands | Tickets + standup in docs/jira_and_standup/ |
| /on_board | First-time onboarding after clone-or-unzip | Verified install: scaffolding, preferences, tour, self-check |
| /bootstrap_to_custom_commands | In-place scaffolding generation / post-upgrade re-run | Fresh per-project scaffolding (never overwrites yours) |
