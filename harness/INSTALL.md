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
   zip -- and the generate steps do all the real work: preference files generated from the
   portable templates under `harness/templates/preferences/`, a root `CLAUDE.md` from the
   skeleton template, `docs/` + `context/` directories, `.gitignore` entries,
   `settings.json` wiring (guardrail + phase-closing hooks, deny rules), and the one-time
   credential-helper walkthrough. You never hand-create a file: every preference file (and
   CLAUDE.md) arrives complete, and you only edit placeholder values.

3. **Edit the placeholders.** The bootstrap pre-creates every file; you only fill values:
   - Fill the `[...]` placeholders in the generated root `CLAUDE.md`.
   - Edit the placeholders in each pre-created `.claude/preferences/` file
     (`git_parameters.md` already ships working defaults; the others carry `[fill in ...]`
     markers for the project-specific values).
   - Save `GIT_PAT` (and optionally `GIT_USERNAME`) into your project's own `.env` --
     see the Git credential pre-requisite below.

4. **Next step.** Fill in `CLAUDE.md` and the `.claude/preferences/` files with this
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

- **`.claude/preferences/` (filled)** -- carries the source project's opinion (git
  parameters, environment, verification, monitoring). Bootstrap regenerates these from the
  portable templates under `harness/templates/preferences/` (which DO ship in the zip) so
  the recipient gets complete, project-agnostic files to edit -- never the source's opinion.
- **`.claude/settings.json`** -- contains project-absolute allow rules and interpreter
  paths that will not match another machine. Bootstrap generates it fresh.
- **root `CLAUDE.md`** -- project-specific content, and it lives at the project root, not
  under `.claude/`. Bootstrap generates it blank from the skeleton template.
- **the user-managed approvals directory** -- created only by the user placing an
  approval marker; never shipped.
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
   Python invocation (`venv/bin/python` by default). If your project has no venv at that
   path, or uses a different interpreter, you MUST edit the two hook `command` fields in
   `.claude/settings.json` to your interpreter. Otherwise the hooks silently never fire
   and the git guardrails are not enforced.

2. **Git credential / PAT.** Pushes authenticate via the repo-local credential helper,
   which reads `GIT_PAT` from your project's own `.env` at push time. Before the
   credential step:
   - the target must be a git repo -- run `git init` first if it is not one yet;
   - `GIT_PAT` (and optionally `GIT_USERNAME`) must already be saved in that project's
     `.env`.
   Then, from the repo root, run:
   ```
   bash .claude/harness/scripts/setup_credential_helper.sh
   ```
   No session ever reads `.env`; the token never enters a transcript.

3. **Zip rooting.** The archive must expand to `.claude/...` at your project root. If it
   double-nests (e.g. `harness_portable/.claude/...`), move the `.claude/` directory up
   to the project root -- otherwise the bootstrap command will not be found and the
   generate steps have nothing to act on. Producing the zip with `make_portable_zip.sh`
   yields the correct rooting automatically.
