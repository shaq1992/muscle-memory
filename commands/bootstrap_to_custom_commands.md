---
description: In-place install/upgrade step for the portable workflow harness. Generates the per-project scaffolding around the portable tree already present at .claude/ (from a git clone or an extracted zip): .claude/preferences.md from the single template, a root CLAUDE.md from the skeleton template, docs/ + context/ directories, .gitignore entries, and settings.json wired with the DETECTED python interpreter. Idempotent -- re-running refreshes wiring and NEVER overwrites an existing preferences.md or an existing CLAUDE.md. Recipients normally reach this through /on_board, which wraps it.
---

## Purpose

`/bootstrap_to_custom_commands` is the harness's install-only scaffolding step. It runs
IN PLACE, with no arguments: the portable harness trees are already sitting at the
project's `.claude/` -- put there by a `git clone` of the harness repo or by extracting
the curated distribution zip (see `.claude/harness/INSTALL.md`). Bootstrap's ONE job is
to generate the per-project scaffolding around that portable tree.

- **Install** (fresh project): generates every per-project file and directory listed
  below.
- **Upgrade** (re-run on a project that already has them): creates anything missing,
  skips anything present. The SAME steps serve both; every step is idempotent.

There is no cross-directory copy mode. Moving the harness between projects or machines
is done by git clone or by the zip -- see INSTALL.md's install paths and owner-port
recipe -- never by this command copying files across directories.

### The two-layer split (context for what this generates)

- **Portable law** (already present, NOT touched by bootstrap): `.claude/harness/`,
  `.claude/commands/`, `.claude/agents/`, `.claude/hooks/` -- tracked in the harness
  repo, shipped verbatim.
- **Per-project opinion** (what bootstrap GENERATES): `.claude/preferences.md`, root
  `CLAUDE.md`, `docs/` + `context/` directories, project `.gitignore` entries,
  `.claude/settings.json`. Gitignored inside the harness repo; edited only by the user.

## Execution steps (all idempotent -- safe to re-run)

### Step 0 -- Verify the portable tree is present

Confirm all four portable trees exist: `.claude/harness/`, `.claude/commands/`,
`.claude/agents/`, `.claude/hooks/`. If any is missing, STOP and report which -- the
harness has not been cloned/extracted at the project root correctly (see INSTALL.md's
"Zip rooting" note). Do not generate scaffolding around a partial tree.

### Step 1 -- Detect the python interpreter

Detect the interpreter that will run the deterministic hooks, in this order:
`python3` -> `python` -> `py` (first hit of `command -v <name>` wins). Record the
detected name for Step 6.

If NONE is found: report it loudly -- the generated hooks will not fire until a python
interpreter exists (the hook commands fail open by design). Do NOT offer an install
here; the interpreter install flow (permission ask, per-OS blessed command, decline
warning) lives in /on_board, which runs its prerequisite step BEFORE invoking this
command. Continue scaffolding with `python3` as the written default so a later install
needs no rewiring.

### Step 2 -- Generate preferences.md from the single template

- If `.claude/preferences.md` does NOT exist, copy
  `.claude/harness/templates/preferences_template.md` to `.claude/preferences.md`
  verbatim.
- If it already exists, leave it byte-for-byte untouched -- NEVER overwrite a
  preferences file -- and the completion report MUST state:
  "existing preferences.md detected -- kept". (This is what makes the owner-port
  recipe in INSTALL.md safe: clone, copy your preferences.md in, run /bootstrap.)
- The template ships working git defaults (the machine-parseable key lines the
  guardrail hook reads), so the hook works before the user customizes anything.
  `harness_push_remote` is deliberately absent -- recipients never set it.
- Report: created-from-template / existing-detected-and-kept.

### Step 3 -- Generate root CLAUDE.md from the skeleton template

- If `<project root>/CLAUDE.md` already exists, do NOT overwrite it. Report
  "CLAUDE.md already exists -- skipped."
- Otherwise, read `.claude/harness/templates/claude_md_skeleton.md`, DROP the
  instruction preamble (everything above the `---` separator / the `# CLAUDE.md`
  marker line), and write the remaining skeleton body to `<project root>/CLAUDE.md`.
  The generated file is the thin protective skeleton with `[...]` placeholders the
  user then fills -- the deliberate anti-`/init`. Do NOT auto-fill placeholders from
  the filesystem (guided, user-confirmed filling is /on_board's CLAUDE.md assist).
- Report created-from-skeleton / skipped.

### Step 4 -- Create per-project directories

Create (idempotent) at the project root:
```
mkdir -p docs/prds docs/multi_phase_plans docs/learnings docs/prompts docs/quick
mkdir -p docs/comms/incoming docs/comms/outgoing
mkdir -p context
```
Report which were created and which already existed. Do NOT seed context/ files -- the
domain glossary/architecture/decisions are written by real sessions, not bootstrap.

### Step 5 -- .gitignore (all AI-facing scaffolding stays local)

Check `<project root>/.gitignore`. Ensure each of these entries is present (one per
line, append any missing, never duplicate; if the file is absent, create it):
```
.claude/
CLAUDE.md
docs/
context/
```
Report created / entries-appended / already-present.

### Step 6 -- settings.json (permissions + hook registration)

Target file: `.claude/settings.json`. Substitute the Step 1 detected interpreter for
BOTH `python3` occurrences in each hook command below (the `command -v` guard and the
`exec`) so registered hooks always invoke an interpreter that exists on this machine.

- If it does NOT exist, create it with this content (shown with the `python3` default):
  ```json
  {
    "permissions": {
      "allow": [
        "Bash(git push origin --delete:*)"
      ],
      "deny": [
        "Read(.env)",
        "Read(./.env)",
        "Read(**/.env)"
      ]
    },
    "hooks": {
      "PreToolUse": [
        { "matcher": "Bash",
          "hooks": [ { "type": "command", "command": "D=\"${CLAUDE_PROJECT_DIR:-.}\"; command -v python3 >/dev/null 2>&1 && exec python3 \"$D/.claude/hooks/git_guardrails.py\" || exit 0" } ] },
        { "matcher": "Edit|Write|NotebookEdit",
          "hooks": [ { "type": "command", "command": "D=\"${CLAUDE_PROJECT_DIR:-.}\"; command -v python3 >/dev/null 2>&1 && exec python3 \"$D/.claude/hooks/enforce_orchestrator_isolation.py\" || exit 0" } ] }
      ],
      "Stop": [
        { "hooks": [ { "type": "command", "command": "D=\"${CLAUDE_PROJECT_DIR:-.}\"; command -v python3 >/dev/null 2>&1 && exec python3 \"$D/.claude/hooks/enforce_phase_closing.py\" || exit 0" } ] },
        { "hooks": [ { "type": "command", "command": "D=\"${CLAUDE_PROJECT_DIR:-.}\"; command -v python3 >/dev/null 2>&1 && exec python3 \"$D/.claude/hooks/enforce_handback.py\" || exit 0" } ] }
      ]
    }
  }
  ```
- If it DOES exist, parse it as JSON and MERGE idempotently: add the four hook
  registrations only if an equivalent entry is not already present; add each
  `permissions.deny` and `permissions.allow` rule only if absent (create the `allow`
  list if the file has none). Preserve every other existing key and every
  user-added entry (`skillOverrides`, extra allow/deny rules, etc.) untouched. Do
  not rewrite an existing hook command's interpreter -- an already-wired project
  keeps its wiring.
- The `.env` deny rules are load-bearing security invariants -- they must end up
  present.
- The `git push origin --delete` allow rule exists so the orchestrated per-work-unit
  close (git_strategy.md step 4: delete the work-unit branch, remote and local) can
  complete autonomously -- the auto-mode permission classifier otherwise flags the
  remote delete as destructive and blocks it. It is safe because the
  `git_guardrails.py` PreToolUse hook independently denies every push form that
  deletes the protected branch (`--delete main`, `-d`, `:main`, `refs/heads/main`),
  so the allowlist can never open a path to deleting main.
- Report: created-fresh (naming the interpreter written) / merged (list what was
  added) / already-complete.

### Step 7 -- Completion report

Report a summary:
- Whether this was a fresh install or an upgrade/no-op re-run.
- Detected interpreter (or "none found -- hooks inert until python is installed").
- preferences.md: created-from-template, or "existing preferences.md detected -- kept".
- CLAUDE.md: created-from-skeleton or skipped (already existed).
- Directories created; .gitignore result; settings.json result.
- Next step: "Run /on_board for the guided setup (preferences elicitation, CLAUDE.md
  assist, tour, self-check) -- or, if you have already onboarded, fill in CLAUDE.md
  and .claude/preferences.md, then run /grilling_session to start your first planning
  session."
