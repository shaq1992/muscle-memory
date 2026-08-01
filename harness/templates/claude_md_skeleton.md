# CLAUDE.md skeleton (portable template)

Single source of the CLAUDE.md "slim shape". Bootstrap generates a NEW project's
root `CLAUDE.md` from this file -- it is never edited to hold a specific project's
content. CLAUDE.md lives at project root (outside `.claude/`), is gitignored, and
is project-specific, so it is never portable itself; only its SHAPE is portable.

This is the deliberate anti-`/init`: lay down a thin protective skeleton the user
then fills, rather than auto-documenting the whole filesystem.

Fill rules for the generated file:
- Keep it to ~120-150 lines. Apply the repo-recovery test to every line: a fact
  stays ONLY if it cannot be recovered by reading the repo. Mechanical detail
  (per-file maps, tool tables, function/feature inventories) is DELETED, not
  recorded -- Explore re-derives it on demand.
- Replace every `[...]` placeholder with project content. Delete sections that do
  not apply (e.g. a project with no security invariants drops that section).
- Keep the armed pointers pointing at `.claude/harness/procedures/*`,
  `.claude/preferences/*`, and `context/*` -- the paths a bootstrapped project has.
- Strip this instruction block; the generated CLAUDE.md begins at the `# CLAUDE.md`
  line below.

---

# CLAUDE.md

Guidance for Claude Code in this repository. This file is the per-turn protective
skeleton: hard rules, project state, do-not-retry ledger, security invariants, a
skeletal map, and armed pointers to fuller context. Descriptive architecture and
rationale live in `context/` (local-only); mechanical detail is not recorded
anywhere -- Explore re-derives it from the repo on demand.

## Role

[One or two lines: who Claude is acting as on this project, the domain, and who it
is helping.]

## Hard constraints (non-negotiable)

- [Project-wide behavioral rules that must never be violated -- encoding
  constraints, output-character limits, naming/forbidden-pattern rules. See
  `.claude/preferences/environment.md` for the full environment rules.]
- **No AI attribution in commit messages -- ever.** Never put a model name in a
  subject, body, or trailer; no `Co-Authored-By` AI lines, no "Generated with"
  lines. Write every commit as if authored entirely by the human developer.

## Armed pointers (read the target before acting)

- **Long-running scripts.** Before running ANY script or command expected to
  exceed ~45s, read and follow `.claude/harness/procedures/monitoring.md` (generic
  background+Monitor protocol) AND `.claude/preferences/monitoring.md` (project
  grep patterns, log locations). Non-negotiable.
- **Architecture + rationale.** For subsystem semantics and invariants, read
  `context/architecture.md`. For closed experiments, decision history, and the
  local-artifacts index, read `context/decisions.md`.
- **Explore delegation.** Use `Agent(subagent_type="Explore")` with a scoped query
  whenever you expect to touch under ~20% of a file, or need mechanical detail not
  recorded here. Never full-read a large file when a targeted excerpt suffices.
- **Prompt / scaffolding file locations.** Session prompt files and other
  file-location + venv rules live in `.claude/preferences/environment.md`.

## Project purpose

[2-4 lines: what the system does and why. Point at `context/architecture.md` for
the descriptive detail.]

## Project state

- **Architecture:** [current high-level approach in one or two bullets]
- [Other durable state bullets: data model, key components, current operating
  parameters -- only what is NOT obvious from the code.]

## Do-not-retry ledger (condensed -- full reasoning in `context/decisions.md`)

| Item | Reason (short) |
|---|---|
| [closed experiment / rejected approach] | [one-line reason it will not be retried] |

## Security hardening (do NOT regress)

[Preserve these; do not silently undo. Mechanism lives in the code -- keep the
invariant. Delete this section if the project has no such invariants.]

- [Invariant name + one line on what must stay true.]

## Skeletal directory map

Top-level orientation only (~15 lines). Explore derives per-file detail on demand.

```
[entry-point file]     -- [one line]
[top-level dir]/       -- [one line on what lives here]
[top-level dir]/       -- [one line]
docs/                  -- gitignored: prds, plans, prompts, learnings
context/               -- gitignored durable knowledge: architecture.md, decisions.md, glossary.md
.claude/               -- gitignored harness: commands, agents, hooks, harness/, preferences/
```
