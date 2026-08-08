# Procedure: Unified Git Strategy (PR law)

Portable law for all multi-phase plans. Project-specific parameters are read
from the key block of `.claude/preferences.md`; if that file is absent, the
defaults stated inline below apply.

The core invariant: Claude has NO path to the protected branch. Every plan
ends in a reviewable GitHub pull request that the USER merges. There is no
side-channel approval mechanism, no Claude-run merge to the protected branch,
and no exempt plan type -- every plan follows the same topology.

**Removal-direction carve-out.** A plan whose OWN git-strategy section states an
explicit no-PR exception -- no PR opened, NOTHING merged to the protected branch
at any point, the integration branch retained as the plan's durable artifact --
may skip the plan-end PR flow. That direction REMOVES a Claude path to the
protected branch rather than creating one, so the core invariant is
strengthened, not weakened. "No exempt plan type" stands unchanged for anything
that would ADD a path: no standby/manual-merge handover, no Claude-run merge or
push to the protected branch, no side-channel approval, ever. The opt-out is
NEVER inferred from silence -- it must be quoted from the plan's own
git-strategy section; absent that explicit statement, the standard PR flow
applies.

## Branch model

- **Integration branch:** `integration/<plan_name>`, created from the default
  branch during the plan's first phase. All phase work funnels into it. It is
  the plan's single accumulation point; the protected branch is never touched
  by Claude at any point.
- **Phase branches:** `<plan_name>-phase-<NN>`, created from the integration
  branch. Naming convention:
  - the plan slug is kebab-case (lowercase alphanumeric + hyphens);
  - the phase number is ALWAYS zero-padded to two digits (`01`, `02`, ... `10`);
  - separators are hyphens throughout -- no underscores.
  Example: `example-plan-phase-04`.

## The two booleans

Every generated phase prompt resolves exactly two boolean parameters:

- **`is_first_phase`** -- if true, create `integration/<plan_name>` from the
  default branch (and push it) BEFORE cutting the phase branch.
- **`is_final_phase`** -- if true, after this phase's branch merges into the
  integration branch, the plan-end PR flow fires (see below).

Single-phase plans set both booleans true.

## Per-phase flow (autonomous, no confirmation)

1. If `is_first_phase`: from the default branch, create and push
   `integration/<plan_name>`.
2. Create `<plan_name>-phase-<NN>` from the integration branch.
3. Implement; commit on the phase branch (commit rules per
   closing_sequence.md).
4. Autonomous close: push the phase branch -> merge it into the integration
   branch with git defaults and an explicit message
   (`git merge <phase-branch> -m "merge: ..."`) -> push integration ->
   delete the phase branch, remote and local (`git branch -d`, never `-D`).

**Zero-commit rule:** a phase whose branch ends with zero commits skips
push/merge/delete entirely and reports "no tracked changes this phase"
plainly, naming why (e.g. all deliverables were config-only or gitignored).

## Plan-end PR flow

At the final phase, after the last phase branch has merged into integration:

1. **Autonomous:** push the integration branch, then open the PR with
   `gh pr create` (title/body convention below).
2. **User-gated:** the USER merges the PR with a `!`-prefixed
   `gh pr merge <n> --merge` -- the keystroke IS the approval, and its output
   lands in the transcript. Claude NEVER runs `gh pr merge` (the guardrail
   hook flat-blocks it). If the user withholds the merge, the plan ends with
   the integration branch and the open PR as the durable artifacts.
3. **Merge defaults** (preference keys): `merge_style: merge-commit`
   (`gh pr merge --merge`) and `retain_integration_branch: true` -- the
   integration branch is kept after the merge; deletion is per-plan opt-in.

**Plan-level opt-out (removal direction only).** If the plan's own git-strategy
section explicitly states a no-PR exception (e.g. "PLAN-SPECIFIC EXCEPTION to
the standard plan-end PR flow. No pull request is opened and NOTHING is merged
to `main` at any point"), steps 1-3 above do NOT run: no `gh pr create`, no
user-run `gh pr merge`, nothing reaches the protected branch, and the retained
integration branch IS the plan's durable artifact. Everything else in this
procedure -- branch model, the two booleans, the per-phase flow, the zero-commit
rule, commit authorship, the hook enforcement -- is unchanged. This opt-out is
never inferred from silence and never assumed from a plan's tone or scope: it
must be quoted from the plan text. It permits only the removal direction; a plan
may NOT use it to substitute a standby/manual-merge handover or any other
Claude-run path to the protected branch.

**PR title/body convention:** the no-AI-attribution law extends verbatim to PR
titles and bodies. Fixed body shape: the plan one-liner; a bulleted phase list
(drawn from the per-phase `feat:` commits -- under git-default merges a phase
merge FAST-FORWARDS whenever the integration branch has not moved since the
phase branch was cut, so per-phase merge commits may not exist); a pointer note
that detailed history lives in the per-phase commits.

**Post-PR fixes:** review changes requested on an open plan PR are committed
directly on the integration branch and pushed; the open PR tracks them -- no
fix-phase ceremony.

## Interactive commands (TTY rule)

TTY-interactive commands (auth prompts, `gh auth login`, sudo) cannot run
through the Bash tool OR a `!`-prefixed line -- no terminal is attached. They
run BY THE USER in a separate terminal window. `!`-prefixed lines are for
NON-interactive user-run commands whose output must land in the transcript
(e.g. `! gh pr merge 7 --merge`).

## Identity and auth (gh)

All GitHub auth goes through the gh CLI (`gh auth login`); there is no token
in any env file and no credential-helper script. With multiple github.com
identities, each repo pins its own, WITHOUT relying on gh's active-account
state -- gh's built-in credential helper serves only the active account, so
plain `credential.username` pinning alone fails for the non-active repo. The
working per-repo config is:

1. an empty `credential.helper` entry (resets the global helper chain), then
2. an INLINE helper that asks gh for the pinned user's token:
   `!f() { test "$1" = get && echo "password=$(gh auth token --user <pinned-user>)"; }; f`
3. plus `credential.username <pinned-user>`.

This is repo-local git config (environment, not corpus). `gh api` / `gh pr`
commands still follow gh's ACTIVE account -- only git pushes are
active-agnostic -- so keep the account that owns the harness repo active when
running gh operations against it.

## Commit authorship

No AI attribution anywhere in any commit, merge, or PR message, ever: no
model names, no `Co-Authored-By` AI trailers, no "Generated with" lines.
Unchanged, permanent rule.

## Enforcement (deterministic layer)

`.claude/hooks/git_guardrails.py`, a PreToolUse hook on Bash registered in
`.claude/settings.json` (stdlib python3). Deterministic pattern matching,
never model judgement. Parameters from `.claude/preferences.md`'s key block.

- **Destructive ops, always blocked:** `git push --force` / `-f` (any
  `--force*` variant), `git reset --hard`, `git branch -D`, `git clean -f`.
- **Protected branch, flat-blocked -- no exceptions:** `git merge` while on
  the protected branch; any push targeting it (including the
  `origin main:main` refspec form); `gh pr merge` (user-only, see above).
- **Push-remote allowlist (fail-closed):** a `git push` attributed to the
  harness repo at `.claude/` (attribution covers `git -C` and `cd` forms) is
  allowed only when the resolved remote URL matches the
  `harness_push_remote` parameter. Key absent = ALL harness pushes blocked.
  Recipients never set the key; a recipient's harness cannot push.
