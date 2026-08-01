---
description: Install OR upgrade the portable workflow harness in a target project. Copies the portable subset (harness/, commands/, agents/, hooks/) verbatim, generates preference files from the portable templates under harness/templates/preferences/, generates a root CLAUDE.md from the skeleton template, creates docs/ + context/, and wires settings.json (guardrail + phase-closing hooks, deny rules). Idempotent -- re-running upgrades the harness while never overwriting existing preferences or an existing CLAUDE.md.
---

## Purpose

`/bootstrap_to_custom_commands [target_dir]` is the SINGLE lifecycle command for the
harness: it installs the harness into a new project and, run again, upgrades an existing
one. There is no separate port command -- this is the only supported porting mechanism.

- **Install:** point it at a fresh project directory. It lays down the portable harness,
  generates per-project scaffolding (preference files from portable templates, CLAUDE.md,
  docs/, context/), and
  wires hooks + deny rules.
- **Upgrade:** run it again against a project that already has the harness. It refreshes the
  portable subset verbatim and leaves every per-project file (preferences, filled CLAUDE.md)
  untouched.

### Porting boundary (read before running)

The harness splits into a PORTABLE subset and a PER-PROJECT subset:

- **Portable (copied verbatim):** `.claude/harness/`, `.claude/commands/`, `.claude/agents/`,
  `.claude/hooks/`.
- **Per-project (generated fresh, NEVER copied from the source):** `.claude/preferences/`
  (complete files generated from the portable templates under
  `harness/templates/preferences/`), root `CLAUDE.md` (from the skeleton template),
  `context/`, `docs/`.

A raw `cp -r .claude/ <new-project>` is NOT a supported port: it drags the SOURCE project's
filled preference files (git parameters, environment, verification, monitoring) and its
project-specific CLAUDE.md into the new project, silently importing wrong opinion. Always
port through this command, which regenerates the per-project subset blank.

For an offline hand-off to a machine that cannot see this project, the portable subset can
instead be shipped as a curated zip and this command run in place -- see
`.claude/harness/INSTALL.md`.

## Resolve source and target

This command runs in one of two modes:

- **Cross-directory** (an argument is given): TARGET = the first argument (`target_dir`),
  an absolute or relative path to the project to install/upgrade; SOURCE = the project this
  command is invoked from. The portable subset is copied from SOURCE into TARGET, then the
  per-project scaffolding is generated in TARGET (copy-then-generate).
- **In-place / offline-zip** (NO argument): TARGET == SOURCE == the current project root.
  The portable subset already sits in the target's `.claude/` -- for example, unzipped from
  a distribution archive (see `.claude/harness/INSTALL.md`). The copy steps are a no-op
  because the files are already present; the generate steps do all the work.

Resolve the paths as follows:

- **SOURCE** = the project this command is invoked from -- specifically its `.claude/`
  directory (the one containing this file). This is where the portable harness is read from.
- **TARGET** = the first argument (`target_dir`) if given, else the current project root.
- Compute `SOURCE_CLAUDE=<source_root>/.claude` and `TARGET_CLAUDE=<target_dir>/.claude`.
- When SOURCE and TARGET resolve to the same path (the in-place / offline-zip mode), the
  copy steps become a no-op refresh and the generate steps CREATE anything missing (a fresh
  in-place install) and SKIP anything already present (an upgrade) -- the SAME code path
  serves both the first-time install and the re-run upgrade. Same-path does NOT mean
  "upgrade only".

Report the resolved SOURCE and TARGET paths before doing anything else, and state which mode
(cross-directory or in-place/offline-zip) this run is in.

## Execution steps (all idempotent -- safe to re-run)

### Step 1 -- Copy the portable subset verbatim

Create `TARGET_CLAUDE/` if absent, then copy these four trees from SOURCE_CLAUDE, verbatim,
overwriting older copies (this is the refresh/upgrade mechanism):

- `harness/`   (procedures/, templates/ incl. `claude_md_skeleton.md` and the portable
                `templates/preferences/` files, scripts/ incl. `make_portable_zip.sh`,
                `USER_MANUAL.md`, `INSTALL.md`, `harness_glossary.md`, tests/)
- `commands/`  (all invocable commands, including this bootstrap command itself so the target
                can re-bootstrap/upgrade) -- but for each `.md` file in
                `SOURCE_CLAUDE/commands/`, FIRST parse its YAML frontmatter and check for a
                `portable: false` key. If that key is present, SKIP the copy for that file
                entirely and log a `skipped-non-portable: <filename>` line in the report. All
                other command files copy verbatim.
- `agents/`    (workflow agents, e.g. self-improver)
- `hooks/`     (`git_guardrails.py`, `enforce_phase_closing.py`)

Do NOT copy `preferences/`, `settings.json`, or `context/` here -- those are
per-project (Steps 2-6). List each tree copied.

**Project-specific command opt-out:** the canonical mechanism for marking a command as
project-specific and keeping it out of bootstrapped targets is the `portable: false` key in
the command's YAML frontmatter. Files carrying that key are auto-skipped by the per-file
frontmatter check above (reported as `skipped-non-portable: <filename>`) rather than being
copied over and then flagged for the user to delete -- authors declare the opt-out once at
the source and no manual cleanup step is required in the target. Fallback: if a copied
command's description still contains the phrase "project-specific" but the file did NOT carry
the `portable: false` flag, report that file and recommend the user set `portable: false` on
it in the source so future bootstraps auto-skip it.

### Step 2 -- Generate preferences from portable templates

Preferences are generated by copying the portable template files under
`SOURCE_CLAUDE/harness/templates/preferences/`. They are NEVER derived from the source
project's own filled `preferences/` directory (that would import wrong opinion) and are NOT
hand-built `[Fill in]` one-liners -- each template is a complete, structured file the user
only edits.

- Read the manifest `SOURCE_CLAUDE/harness/templates/preferences/INDEX.md` -- it lists each
  preference file with a one-line description.
- Create `TARGET_CLAUDE/preferences/` if absent.
- For `INDEX.md` and EACH file the manifest lists (e.g. `git_parameters.md`, `environment.md`,
  `verification.md`, `monitoring.md`): if `TARGET_CLAUDE/preferences/<file>` does NOT exist,
  copy `SOURCE_CLAUDE/harness/templates/preferences/<file>` into it verbatim; if it already
  exists, leave it untouched (NEVER overwrite a filled preference file).
- `git_parameters.md` ships working defaults (not bare placeholders): the template already
  carries the machine-parseable key lines the guardrail hook reads
  (`integration_branch_prefix`, `phase_branch_pattern`, `phase_number_padding`,
  `default_branch`, `protected_branch`, `merge_style`, `retain_integration_branch`), so the
  hook works before the user customizes anything.
- Report, per file: created-from-template / already-existed-skipped.

Because these templates live under `harness/` (part of the portable subset shipped in the
offline zip), the manifest and every template are always present on the target -- this step
has NO dependency on the excluded per-project `preferences/` directory, which is what closes
the in-place / offline-zip gap.

### Step 3 -- Generate root CLAUDE.md from the skeleton template

- If `TARGET_DIR/CLAUDE.md` already exists, do NOT overwrite it. Report
  "CLAUDE.md already exists -- skipped." (This is what makes an upgrade run safe.)
- Otherwise, read `SOURCE_CLAUDE/harness/templates/claude_md_skeleton.md`, DROP the
  instruction preamble (everything above the `---` separator / the `# CLAUDE.md` marker
  line), and write the remaining skeleton body to `TARGET_DIR/CLAUDE.md`. The generated file
  is the thin protective skeleton with `[...]` placeholders the user then fills -- this is
  the deliberate anti-`/init`. Do NOT auto-fill placeholders from the target's filesystem.
- Report created-from-skeleton / skipped.

### Step 4 -- Create per-project directories

Create (idempotent) in TARGET:
```
mkdir -p <target>/docs/prds <target>/docs/multi_phase_plans <target>/docs/learnings <target>/docs/prompts
mkdir -p <target>/context
```
Report which were created and which already existed. Do NOT seed context/ files -- the domain
glossary/architecture/decisions are written by real sessions, not bootstrap.

### Step 5 -- .gitignore (all AI-facing scaffolding stays local)

Check `TARGET_DIR/.gitignore`. Ensure each of these entries is present (one per line, append
any missing, never duplicate; if the file is absent, create it):
```
.claude/
CLAUDE.md
docs/
context/
.claude_archive/
```
Report created / entries-appended / already-present.

### Step 6 -- settings.json (permissions + hook registration)

Target file: `TARGET_CLAUDE/settings.json`.

- If it does NOT exist, create it with this content (stdlib `python3`; adjust only if the
  target machine's interpreter is named differently, e.g. `python` on some hosts):
  ```json
  {
    "permissions": {
      "deny": [
        "Read(.env)",
        "Read(./.env)",
        "Read(**/.env)"
      ]
    },
    "hooks": {
      "PreToolUse": [
        { "matcher": "Bash",
          "hooks": [ { "type": "command", "command": "D=\"${CLAUDE_PROJECT_DIR:-.}\"; command -v python3 >/dev/null 2>&1 && exec python3 \"$D/.claude/hooks/git_guardrails.py\" || exit 0" } ] }
      ],
      "Stop": [
        { "hooks": [ { "type": "command", "command": "D=\"${CLAUDE_PROJECT_DIR:-.}\"; command -v python3 >/dev/null 2>&1 && exec python3 \"$D/.claude/hooks/enforce_phase_closing.py\" || exit 0" } ] }
      ]
    }
  }
  ```
- If it DOES exist, parse it as JSON and MERGE idempotently: add the two hook registrations
  only if an equivalent entry is not already present; add each `permissions.deny` rule only
  if absent. Preserve every other existing key (`allow`, `skillOverrides`, etc.) untouched.
- The `.env` deny rules are load-bearing security invariants -- they must end up present.
- Report: created-fresh / merged (list what was added) / already-complete.

### Step 7 -- Confirm

Report a summary:
- Resolved SOURCE and TARGET; whether this was an install or a self-upgrade.
- Portable trees copied (harness/, commands/, agents/, hooks/) + any command files auto-skipped
  due to `portable: false` (listed as `skipped-non-portable`).
- preferences/: which files were created-from-template vs. left untouched.
- CLAUDE.md: created-from-skeleton or skipped (already existed).
- Directories created; .gitignore result; settings.json result.
- Next step: "Fill in CLAUDE.md and the .claude/preferences/ files with this project's
  specifics, then run /grilling_session to start your first planning session."
