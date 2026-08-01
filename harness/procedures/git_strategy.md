# Procedure: Unified Git Strategy

Portable law for all multi-phase plans. Project-specific parameters are read
from `.claude/preferences/git_parameters.md`; if that file is absent, the defaults
stated inline below apply.

## Branch model

- **Integration branch:** `integration/<plan_name>`, created from `main` during the
  plan's first phase. All phase work funnels into it. It is the plan's single
  accumulation point; `main` is never touched mid-plan.
- **Phase branches:** `<plan_name>-phase-<NN>`, created from the integration branch.
  Naming convention:
  - the plan slug is kebab-case (lowercase alphanumeric + hyphens);
  - the phase number is ALWAYS zero-padded to two digits (`01`, `02`, ... `10`);
  - separators are hyphens throughout -- no underscores.
  Example: `harness-improv-v3-phase-04`.

## The two booleans

Every generated phase prompt resolves exactly two boolean parameters. They replace
the old branch-type taxonomy entirely:

- **`is_first_phase`** -- if true, create `integration/<plan_name>` from `main`
  (and push it) BEFORE cutting the phase branch.
- **`is_final_phase`** -- if true, after this phase's branch merges into the
  integration branch, the integration-to-main merge fires -- permission-gated
  (see below).

Single-phase plans set both booleans true. Gate-fail or never-merge experiment
plans are simply "final merge permission withheld" -- the integration branch
remains as the durable artifact; nothing special is needed.

## Autonomous operations (no confirmation required)

At phase close, the session performs these git operations autonomously -- no
user confirmation, no surfacing of commands for manual execution:

1. Push the phase branch to the remote.
2. Merge the phase branch into `integration/<plan_name>` with
   `git merge --no-ff <phase_branch> -m "merge: <message>"` (always `--no-ff`,
   always with an explicit merge message).
3. Push the integration branch.
4. Delete the phase branch, remote AND local.

## Permission-gated operation (always, even in auto mode)

The single **integration-to-main merge + push of main** -- once per plan, at the
final phase -- ALWAYS requires explicit user permission, even if the session is
running in an auto-accept mode. Permission is never inferred, assumed, or carried
over from earlier approvals. If permission is withheld, the plan ends with the
integration branch intact and main untouched.

## Per-phase flow (summary)

1. If `is_first_phase`: from `main`, create and push `integration/<plan_name>`.
2. Create `<plan_name>-phase-<NN>` from the integration branch.
3. Implement; commit on the phase branch (commit rules per closing_sequence.md).
4. Autonomous close: push phase branch -> no-ff merge into integration -> push
   integration -> delete phase branch (remote + local).
5. If `is_final_phase`: request explicit user permission for the
   integration-to-main merge; only after approval, merge into `main` and push.

## Local-only plans

A plan whose deliverables are ALL gitignored/local-only (e.g. harness work under
`.claude/`, `context/`, `docs/`) has nothing to commit: no integration branch, no
phase branches. Work happens directly on `main` with nothing staged. Any
exceptional tracked edit (e.g. a `.gitignore` line) is committed directly to main
per that plan's explicit instruction.

## Commit authorship

No AI attribution anywhere in any commit or merge message, ever: no model names,
no `Co-Authored-By` AI trailers, no "Generated with" lines. Unchanged, permanent
rule.

## Enforcement (deterministic layer)

- **Guardrail hook:** `.claude/hooks/git_guardrails.py`, a PreToolUse hook on
  Bash registered in `.claude/settings.json`. Deterministic pattern matching,
  never model judgement. Always blocks `git push --force` / `-f` (any
  `--force*` variant), `git reset --hard`, `git branch -D`, `git clean -f`.
  Blocks `git merge` while on the protected branch and any push targeting it
  (including the `origin main:main` refspec form) unless the approval marker
  exists. Reads its parameters from `preferences/git_parameters.md`.
- **Approval marker:** `.claude/approvals/<plan_name>_main_merge.json` (path
  template in `git_parameters.md`). Only the USER can create it -- Claude is
  write-denied on the approvals path (settings.json deny rules on Write/Edit/
  Bash, plus a hook backstop denying any Bash command referencing the
  approvals directory). One-shot: the hook deletes the marker when it allows
  the gated merge.
- **Single-command final merge:** because the marker is consumed by the merge,
  issue the integration-to-main merge AND the main push as ONE compound Bash
  command, e.g.
  `git merge --no-ff integration/<plan_name> -m "merge: ..." && git push origin main`.
- **Credential isolation:** pushes authenticate via the repo-local credential
  helper `.claude/harness/scripts/git_credential_env.sh` (registered once by
  `.claude/harness/scripts/setup_credential_helper.sh`), which reads `GIT_PAT`
  from `.env` at push time. No session ever reads `.env`; settings.json deny
  rules block it.
