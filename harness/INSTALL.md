# INSTALL.md -- Recipient Install Guide

How to get the portable workflow harness into your project. Two install paths, one
onboarding command. This guide is project-agnostic; the deep reference is
`harness/USER_MANUAL.md`, and the landing-page overview is the repo's `README.md`.

## Prerequisites

- A **git repository** at your project root (`git init` if new -- /on_board offers
  to do this).
- The **GitHub CLI** (`gh`), authenticated via `gh auth login` (interactive -- run it
  yourself in a terminal). Needed for the PR-based workflow, not for local work.
- **python3** (stdlib only, no packages). Powers the deterministic git guardrails.
  If it is missing, /on_board explains, asks permission, and installs it for you.

## Path A -- Clone install (recommended when you have repo access)

1. At your project root:
   ```
   git clone <harness-repo-url> .claude
   ```
2. Open a Claude Code session at the project root and run:
   ```
   /on_board
   ```

That is the whole install. The clone's `.git` IS your versioning tier: full upstream
history, local commits (e.g. self-improver improvements) accumulate on your clone,
and upgrading is `git pull` in `.claude/` followed by re-running
`/bootstrap_to_custom_commands` (idempotent -- picks up any new wiring, overwrites
nothing of yours). There is no fork and no push story: a recipient's harness cannot
push (the push guard fails closed without the author-only `harness_push_remote` key).

While the harness repo is private, cloning needs per-person read access -- the zip
below is the no-access hand-off.

## Path B -- Zip install (no git, no repo access needed)

1. Get the curated archive (produced by `harness/scripts/make_portable_zip.sh`) and
   extract it at your project root. It must expand so the trees land at
   `.claude/harness/`, `.claude/commands/`, `.claude/agents/`, `.claude/hooks/`,
   with `INSTALL.md` (this file) at the archive root. If it double-nests
   (e.g. `harness_portable/.claude/...`), move `.claude/` up to the project root.
2. Open a Claude Code session at the project root and run:
   ```
   /on_board
   ```

The zip tier has no git inside `.claude/`: no history, and upgrading is re-extract a
newer zip over `.claude/` + re-run `/bootstrap_to_custom_commands`. The self-improver
still works, reporting old/new excerpts instead of git diffs.

## What /on_board does

The single funnel after either path: verifies the prerequisites above (with a
permission-gated python install offer if needed), detects your install tier
(`.claude/.git` present = clone, absent = zip) and states its consequences, invokes
`/bootstrap_to_custom_commands` to generate the per-project scaffolding, elicits your
`preferences.md` values, offers a guided (opt-in, never silent) CLAUDE.md fill,
gives a short tour, and ends with a self-check run of the guardrail test suite plus
"harness vX.Y installed".

## What you get vs. what you fill in

The harness is two layers, and the install respects the boundary:

- **You GET the portable law** -- `commands/`, `agents/`, `hooks/`, `harness/`
  (procedures, templates, scripts, tests). Tracked in the harness repo, shipped
  verbatim to every recipient, evolved upstream via the self-improver. You never
  need to edit these.
- **You FILL IN the per-project opinion** -- `.claude/preferences.md` and
  `.claude/settings.json` (generated from templates at install), plus your root
  `CLAUDE.md`. These are gitignored inside the harness repo, so they never travel
  with it and a `git pull` upgrade can never clobber them. They are edited only by
  you (with /on_board's help), never by the self-improvement loop.

## Same-machine porting and the owner-port recipe

Moving the harness to another project on a machine that already has it is just a
local git clone -- git itself preserves the capability, zero special tooling:

```
git clone /path/to/other-project/.claude .claude
```

Then run `/on_board` as usual.

**Owner-port recipe** (you are the harness owner carrying YOUR opinions to a new
project -- no /on_board needed):

1. `git clone /path/to/other-project/.claude .claude` at the new project root.
2. Manually copy your filled `preferences.md` into the new `.claude/` -- it is
   gitignored, so it never travels via git.
3. Run `/bootstrap_to_custom_commands`. It is idempotent: it detects your copied
   preferences.md and keeps it (the completion report says so), generating only the
   rest of the scaffolding.
4. Review the per-project keys in the copied file -- `interpreter`, `test_command`,
   `default_branch` / `protected_branch` -- they carry the OLD project's values and
   usually need updating.

## Upgrading

- **Clone tier:** `cd .claude && git pull`, then re-run
  `/bootstrap_to_custom_commands` (idempotent) to pick up any new wiring. Your
  preferences.md, settings.json, and CLAUDE.md are never overwritten.
- **Zip tier:** re-extract a newer zip over `.claude/`, then re-run
  `/bootstrap_to_custom_commands`.

## What the zip contains vs. must NOT contain

**IN the zip:** the four portable trees under `.claude/` (`harness/`, `commands/`,
`agents/`, `hooks/`), plus `README.md` and `VERSION` at `.claude/`, plus `INSTALL.md`
at the archive root for immediate reading.

**OUT of the zip (and why):** `.claude/.git/` (the zip tier is the no-git tier); any
filled `preferences.md` or `settings.json` (another project's opinion and
machine-specific wiring -- bootstrap regenerates both); root `CLAUDE.md`, `docs/`,
`context/` (project-specific); `phase_closing.json`, `projects/`, `__pycache__`
(transient/local state); `.env` (secrets, never distributed).

Always produce the zip with `harness/scripts/make_portable_zip.sh` -- it stages an
explicit include list (it cannot leak per-project files), prunes transient state,
and roots the archive correctly.
