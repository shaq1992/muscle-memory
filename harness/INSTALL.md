# INSTALL.md -- Porting and Distribution Guide

How to install the portable workflow harness into another project. The harness is
portable by design: a small set of trees copy verbatim, and everything project-specific
is generated fresh at install time. This guide is project-agnostic -- nothing here is
tied to any particular codebase.

## Two porting modes

There are exactly two supported ways to get the harness into a project. Both end by
running `/bootstrap_to_custom_commands`, the single install/upgrade command.

- **(a) Cross-directory bootstrap.** You already have a project that carries the harness,
  and you can see the target directory from the same machine/session. Run
  `/bootstrap_to_custom_commands <target_dir>` from the source project. It copies the
  portable subset into the target and generates the per-project scaffolding there. Use
  this when both projects live on one machine.

- **(b) Offline zip / in-place install.** The target is on a different machine (or is a
  brand-new project that has nothing yet), so the portable files must reach it first as a
  curated zip. You extract the zip at the project root, then run
  `/bootstrap_to_custom_commands` with NO argument -- an in-place install where SOURCE ==
  TARGET == the current project. This document focuses on mode (b).

Because `.claude/` is gitignored, a fresh clone or a new machine has none of the harness
until the zip is extracted -- mode (b) is the intended offline hand-off.

## Offline zip flow -- recipient steps

1. **Extract the zip at your project root.** It must expand so the trees land at
   `.claude/harness/`, `.claude/commands/`, `.claude/agents/`, and `.claude/hooks/`
   under your project root, with `INSTALL.md` (this file) at the root as well. See the
   "Zip rooting" pre-requisite below if the archive double-nests.

2. **Run the bootstrap in place.** In a Claude Code session opened at the project root,
   run:
   ```
   /bootstrap_to_custom_commands
   ```
   With no argument, SOURCE and TARGET resolve to the same path (your current project).
   The copy steps are a no-op -- the four portable trees are already present from the
   zip -- and the generate steps do all the real work: `.claude/preferences.md` generated
   from the portable template `harness/templates/preferences_template.md`, a root
   `CLAUDE.md` from the skeleton template, `docs/` + `context/` directories, `.gitignore`
   entries, and `settings.json` wiring (guardrail + phase-closing hooks, deny rules). You
   never hand-create a file: the preferences file (and CLAUDE.md) arrives complete, and
   you only edit placeholder values.

3. **Edit the placeholders.** The bootstrap pre-creates every file; you only fill values:
   - Fill the `[...]` placeholders in the generated root `CLAUDE.md`.
   - Edit the placeholders in the pre-created `.claude/preferences.md` (the git keys
     already ship working defaults; the bracketed values are the project-specific
     placeholders to fill).

4. **Next step.** Fill in `CLAUDE.md` and `.claude/preferences.md` with this
   project's specifics, then run `/grilling_session` to start your first planning
   session. (This is the same next-step the bootstrap reports on completion.)

## What the zip contains vs. must NOT contain

**IN the zip (the four portable trees only):**

- `.claude/harness/`  -- procedures, templates, scripts, USER_MANUAL, glossary, tests.
- `.claude/commands/` -- the invocable commands (including bootstrap itself).
- `.claude/agents/`   -- workflow agents.
- `.claude/hooks/`    -- the guardrail and phase-closing hooks.
- `INSTALL.md` at the archive root, for immediate reading on extraction.

**OUT of the zip (and why):**

- **`.claude/preferences.md` (filled)** -- carries the source project's opinion (git
  parameters, environment, verification, monitoring). Bootstrap regenerates it from the
  portable template `harness/templates/preferences_template.md` (which DOES ship in the
  zip) so the recipient gets a complete, project-agnostic file to edit -- never the
  source's opinion.
- **`.claude/settings.json`** -- contains project-absolute allow rules and interpreter
  paths that will not match another machine. Bootstrap generates it fresh.
- **root `CLAUDE.md`** -- project-specific content, and it lives at the project root, not
  under `.claude/`. Bootstrap generates it blank from the skeleton template.
- **`.claude/phase_closing.json`** -- transient per-session state.
- **`.claude/projects/`** -- the auto-memory store, machine-local.
- **`context/`** and **`docs/`** -- durable/working project knowledge, project-specific.
- **`.env`** -- secrets, never distributed.
- **`.claude_archive/`** -- rollback snapshots, machine-local.

To make this curation mechanical instead of manual, produce the zip with
`.claude/harness/scripts/make_portable_zip.sh`. It copies ONLY the four portable trees by
an explicit include list -- it never names or touches any of the excluded paths -- so the
"don't ship your filled `.claude/`" and correct-rooting footguns are handled for you.

## Pre-Requisites (you handle these on your own)

A short checklist to clear BEFORE or DURING install. Each is a flag for you to act on --
not something the tooling does for you.

1. **Hook interpreter (most likely "it didn't work" surprise -- check this first).** The
   generated `settings.json` registers the guardrail and phase-closing hooks with a
   stdlib `python3` invocation (no venv, no third-party packages). If `python3` is not
   on PATH under a different name (e.g. `python` on some hosts), you MUST edit the two
   hook `command` fields in `.claude/settings.json` to your interpreter. Otherwise the
   hooks silently never fire and the git guardrails are not enforced.

2. **Git + GitHub auth.** The target must be a git repo -- run `git init` first if it is
   not one yet. Pushes and PR operations authenticate through the GitHub CLI: install
   `gh` and run `gh auth login` yourself in your own terminal (it is interactive). No
   tokens are stored in `.env` and no session ever reads your credentials.

3. **Zip rooting.** The archive must expand to `.claude/...` at your project root. If it
   double-nests (e.g. `harness_portable/.claude/...`), move the `.claude/` directory up
   to the project root -- otherwise the bootstrap command will not be found and the
   generate steps have nothing to act on. Producing the zip with `make_portable_zip.sh`
   yields the correct rooting automatically.
