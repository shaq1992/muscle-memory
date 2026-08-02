# The Workflow Harness

A portable, self-installing workflow system for Claude Code -- built for real
multi-session engineering work, by someone who runs it every day.

Claude Code out of the box is a brilliant single session. This harness makes it a
**system**: structured planning interviews that write PRDs and phased plans, compiled
phase prompts so every implementation session starts sharp, deterministic git
guardrails that make destructive operations and protected-branch pushes mechanically
impossible, and a closing sequence that carries learnings forward so session N+1 is
smarter than session N. Three properties do the heavy lifting:

- **Self-improving.** Structural friction discovered mid-session routes through a
  self-improver agent that edits the harness's own command files -- one reviewed,
  committed change at a time. The system you use next month is better than the one
  you installed.
- **Self-reconciling.** Phase closes merge learnings into a current-truth ledger and
  gate PRD/plan amendments through you -- documents stay TRUE at every session start
  instead of silently drifting from reality.
- **Self-installing.** One command, `/on_board`, takes you from clone-or-unzip to a
  verified install: prerequisites checked, hooks wired to an interpreter that exists
  on your machine, preferences elicited, and the guardrail test suite run green on
  your box.

**Version:** see `VERSION` (git tags are the releases).

## Opinionated about topology, configurable about surface details

The harness is two layers, split on exactly that line. The **law** is portable and
opinionated: `commands/`, `agents/`, `hooks/`, and `harness/` are tracked in this
repo and shipped verbatim to every recipient -- the integration-branch topology, the
PR-merged-by-you rule, the closing sequence. The **opinion** is yours and
per-project: `preferences.md` and `settings.json` are gitignored here, generated
from templates at install, and edited only by you -- your branch names, your
interpreter, your test command, your encoding rules. Upgrades pull new law and can
never touch your opinion.

## Prerequisites

- A git repository (or willingness to `git init` -- /on_board offers).
- GitHub CLI (`gh`) authenticated -- the workflow ends in PRs you merge.
- `python3` (stdlib only) for the deterministic guardrails -- /on_board can install
  it for you, with your permission.

## Install -- Path A: clone

```
git clone <this-repo-url> .claude    # at your project root
/on_board                            # in a Claude Code session at that root
```

The clone IS your version tier: full history, local commits welcome, upgrade =
`git pull` + re-run `/bootstrap_to_custom_commands`. No fork, no push -- a
recipient's harness cannot push by design. Requires read access while this repo is
private.

## Install -- Path B: zip

```
unzip harness_portable.zip           # at your project root -> .claude/ + INSTALL.md
/on_board                            # in a Claude Code session at that root
```

The no-git, no-access hand-off: same harness, no history; upgrade = re-extract +
re-run `/bootstrap_to_custom_commands`. Produced only by
`harness/scripts/make_portable_zip.sh`, so no per-project file can ride along.

## Read more

`INSTALL.md` (in `harness/`) -- both paths in detail, the owner-port recipe, and
upgrades. `harness/USER_MANUAL.md` -- the deep reference for every command,
procedure, and hook.
