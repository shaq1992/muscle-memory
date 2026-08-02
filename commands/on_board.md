---
description: The single onboarding funnel for a new harness recipient -- the one command to type after cloning or unzipping the harness into a project. Verifies prerequisites (git repo, gh auth, python interpreter with a permission-gated install offer), detects the install tier (clone vs zip), invokes /bootstrap_to_custom_commands to generate the per-project scaffolding, elicits preferences.md values, offers a guided CLAUDE.md fill, gives a short tour, and ends with an install self-check reporting "harness vX.Y installed".
---

## Purpose

`/on_board` is the ONE command a recipient types after getting the portable harness
into their project (git clone or zip extract -- see `.claude/harness/INSTALL.md`).
It assumes a Claude Code NOVICE by default: explain each step in one or two plain
sentences before doing it, and offer opt-outs rather than assuming expertise. An
experienced user can decline any assist and the funnel still completes.

Run the steps in order. Every step is idempotent; re-running /on_board on an already
onboarded project skips what exists and re-verifies the rest.

## Step 1 -- Prerequisite verification

Check three prerequisites, in order. Report each as pass/fail with a one-line
explanation of why it matters.

**1a. Git repository.** The project root must be a git repo (`git rev-parse
--git-dir`). If not, explain that the harness's whole workflow ends in branches and
pull requests, and ask (AskUserQuestion) whether to run `git init` now. If declined,
stop the funnel: the harness cannot operate without git.

**1b. GitHub CLI auth.** Check `gh` is installed and `gh auth status` shows a logged-in
account. If not: explain that pushes and PRs authenticate through gh (no tokens ever
stored in files), and that `gh auth login` is INTERACTIVE -- the user must run it
themselves in their own terminal window, not through this session. Pause and ask the
user to do so, then re-check. If the user wants to proceed without it, continue with a
note that plan-end PR flows will fail until gh is authenticated (local work is
unaffected).

**1c. Python interpreter (the R11.2 flow).** Detect `python3` -> `python` -> `py`
(first `command -v` hit wins). If found, report the name and move on.

If NONE is found, do NOT silently continue:

1. Explain in UX-friendly terms WHY python is needed: it powers the harness's
   DETERMINISTIC git guardrails -- small stdlib-only scripts that mechanically block
   force pushes, hard resets, branch deletions, and any Claude-initiated merge to
   your protected branch, plus the phase-closing enforcement hook. It is NOT needed
   for the user's own project code.
2. Ask permission (AskUserQuestion) to install it, offering the ONE blessed command
   for their OS: `sudo apt install python3` (Debian/Ubuntu -- note sudo is
   interactive, so give the command for the user to run in their own terminal),
   `brew install python3` (macOS), `winget install Python.Python.3` (Windows);
   manual fallback: download from python.org.
3. If the blessed command fails, TRY OTHER PATHS before giving up: the OS's alternate
   package manager, `pyenv`, a different package name (`python` vs `python3`), or the
   python.org installer -- keep trying reasonable routes as long as the user has
   given permission.
4. **Decline behavior (one-time LOUD warning, nothing persisted):** if the user
   declines, print a clearly-marked warning block stating exactly what they lose --
   DETERMINISTIC ENFORCEMENT IS OFF: force-push/reset-hard/branch-D/clean-f blocking,
   protected-branch enforcement, and phase-closing enforcement all drop to
   prompt-law only (Claude promising to behave, with no mechanical backstop). Say it
   once, loudly, then continue the funnel; do not nag again and do not write any
   flag anywhere.

## Step 2 -- Install-tier detection (deterministic)

Check for `.claude/.git`:

- **Present -> clone tier (local-only versioning).** State the consequences: the
  clone's `.git` IS the versioning -- full upstream history plus any local commits
  (e.g. self-improver commits); upgrades are `git pull` followed by re-running
  /bootstrap_to_custom_commands; there is no push story and no fork -- recipients
  never push the harness (the push guard fails closed without the author-only
  `harness_push_remote` key).
- **Absent -> zip tier (no git).** State the consequences: no version history;
  upgrade = re-extract a newer zip over `.claude/` and re-run
  /bootstrap_to_custom_commands; the self-improver still works but reports old/new
  excerpts instead of git diffs.

There is no posture question to ask -- the install method IS the choice.

## Step 3 -- Generate the scaffolding (invoke bootstrap)

Run the steps of `/bootstrap_to_custom_commands` (its own command file is the
authoritative procedure; follow it, do not restate it). It verifies the portable
tree, writes settings.json with the Step-1c detected interpreter, generates
preferences.md from the template and CLAUDE.md from the skeleton (never overwriting
existing ones), creates the docs/ + context/ directories, and appends the .gitignore
entries. Surface its completion report to the user -- including whether an existing
preferences.md was detected and kept.

## Step 4 -- Preferences elicitation

If preferences.md was just generated from the template (not an existing kept file),
fill its machine key block FROM THE USER'S ANSWERS via AskUserQuestion -- never guess
a value. Elicit, with one line on what each key drives downstream:

- `user_name` -- how commands address you at runtime.
- `default_branch` / `protected_branch` -- confirm the shipped `main` default or take
  the project's actual branch name (the branch the guardrails will defend).
- `interpreter` -- the PROJECT code's interpreter/runtime (venv path, node, etc.) --
  distinct from the harness's own stdlib python3.
- `test_command` -- the full project test-suite command implementation phases run.
- `encoding_constraint` -- any console/encoding limits sessions must respect (offer
  "UTF-8 throughout, no constraint" as the common answer).

Batch related keys into single AskUserQuestion calls (max 4 questions per call) with
sensible defaults as the recommended options. Leave the remaining git-topology keys
at their shipped working defaults unless the user objects; edit the file with the
answers. If an existing preferences.md was kept, skip elicitation and instead flag
the per-project keys (interpreter, test_command, default/protected branch) for the
user to review -- they may carry another project's values (owner-port case).

## Step 5 -- CLAUDE.md assist (opt-in, novice-by-default)

If CLAUDE.md was just generated (placeholders present), offer to help fill it NOW,
with per-aspect opt-outs (the user can accept help for some sections and skip
others). Never silently auto-fill -- every written line is user-confirmed.

- For each skeleton section (Role, Hard constraints, Project purpose, Project state,
  security invariants, directory map), explain in ONE line the downstream value --
  e.g. "Role and Hard constraints are re-read every turn: they are what keeps
  sessions on-rails when context runs long."
- **If the project has code or docs** (a README, docs/ content, an existing
  codebase): derive grilling-session-style SUGGESTIONS from them ("From your README
  this looks like a payments API in Go -- shall I put that in Project purpose?").
  Suggestions are proposals the user confirms or edits -- never written silently.
- **If starting purely from scratch:** ask 1-line-answer questions per section,
  minimizing friction; accept "skip" freely.
- End by stating CLAUDE.md's state plainly: which sections are filled and which
  still hold `[...]` placeholders for later.

If CLAUDE.md already existed, state that and skip the assist.

## Step 6 -- Guided tour

A short (~15 line) tour, novice-appropriate:

- **The two layers, in two lines:** everything under `commands/`, `agents/`,
  `hooks/`, and `harness/` is portable LAW -- shipped verbatim, evolved upstream via
  the self-improver. `preferences.md`, `settings.json`, and your root CLAUDE.md are
  YOUR project's OPINION -- generated from templates, edited only by you.
- **The workflow arc:** `/grilling_session <plan>` interviews you and writes a PRD +
  phased plan -> `/write_prompt <plan> <N>` compiles a phase prompt -> paste it into
  a fresh session to implement -> every plan ends in a GitHub PR that YOU merge
  (Claude has no path to your protected branch -- enforced by the hooks verified in
  Step 7).
- **The quick lane:** `/grill_and_implement <slug> <task>` for tasks too small for a
  full plan.
- **Where to read more:** README.md (pitch + install paths) -> harness/INSTALL.md
  (install detail) -> harness/USER_MANUAL.md (deep reference).

## Step 7 -- Install self-check

1. Run the harness suite with the detected interpreter:
   `python3 -m unittest discover .claude/harness/tests` (substitute the detected
   name). Green = "guardrails verified working on your machine." If python was
   declined in Step 1c, state the self-check is SKIPPED and enforcement is off
   (do not re-print the full warning).
2. Read `.claude/VERSION` and close with the install report:
   "harness v<VERSION> installed" -- plus the tier (clone/zip), the interpreter
   wired into the hooks, preferences.md state (elicited / kept / placeholders),
   CLAUDE.md state, and the suggested first step: run `/grilling_session
   <plan_name>` when ready to plan your first piece of work.
