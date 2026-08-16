# Procedure: Instruction Precedence

One ladder for every layer that injects rules into a session -- an
orchestrator, a dispatched orchestrated session, or a canonical phase alike.
Before this file, precedence existed only as fragments scattered through the
corpus (each cited below as an instance of the general rule). This file
generalises them; it does not retire them -- each rule still lives with the
actor who can violate it, and this file is the map that shows they agree.

## The ladder -- outermost first

When two layers genuinely conflict about what a session must DO, the outer
layer binds. "Outer" means harder to change and broader in scope, not louder
or more recent.

1. **Deterministic hooks.** A registered hook's deny/block is final for the
   turn in which it fires. No document and no instruction un-fires a hook;
   changing what a hook enforces means changing the hook (red-first, per the
   lockstep-test law), never talking past it. A session executes under the
   hooks that are LIVE, which may lag the corpus being edited.
2. **The user's live word.** An explicit instruction given in conversation
   overrides every document below this rung -- and is written through to the
   governing document (a state row, a CLAUDE.md edit, a preferences value) so
   the override has exactly one durable author. A live word cannot un-fire a
   hook; it can direct that the hook be changed.
3. **Host-project hard law (CLAUDE.md).** The host project's non-negotiables:
   encoding rules, budget law, legal/permitted-use boundaries, the ambiguity
   protocol. Portable harness law never overrides host hard law -- the harness
   is a guest in the project.
4. **State rows.** The governing plan's `## Established` table
   (`harness/templates/state_schema.md`): pinned invariants, gates, settled
   decisions. Rows bind every session of their plan. At handback ingest the
   fragment "where it conflicts with state, STATE WINS" (orchestrator.md
   Step 9) is this rung: an ADVISORY handback section never outranks a row.
5. **Session prompt.** The dispatched prompt or generated phase prompt. It is
   a VIEW of the layers above -- verbatim rows, resolved parameters -- never a
   second store: a fact in a prompt and absent from state is a bug in the
   prompt. Where a prompt and a state row disagree, the row wins and the
   disagreement is surfaced.
6. **Command and procedure law.** The portable corpus: `commands/`,
   `agents/`, `harness/procedures/`, `harness/templates/`, hook SOURCE text.
   This rung owns BEHAVIOR and TOPOLOGY (see the split below).
7. **preferences.md defaults.** The per-project parameter key block:
   interpreter, branch patterns, remotes, thresholds. The bottom rung by
   design -- every layer above may specialise a parameter; preferences supply
   the value when nothing above speaks.

## The generalised insight: parameters vs behavior

**PARAMETERS flow from the more specific layer.** A parameter is a VALUE -- a
branch name, a path, a repo location, a threshold, an interpreter. The layer
closest to the work supplies it: a plan's own git-strategy section beats the
key-block pattern on branch NAMES and repo location; a dispatch prompt names
the concrete deliverable paths; preferences fill in whatever nothing above
named. (Fragment: "the plan wins on branch NAMES and repo location" --
commands/write_prompt.md.)

**BEHAVIOR and TOPOLOGY always follow law.** How the machinery works -- the
per-work-unit flow, autonomous close, the plan-end PR merged by the USER, the
one-writer rule, marker/handback mechanics -- comes from rung 6 and is never
overridden by a name-level layer. A plan that needs different BEHAVIOR does
not assert it: it goes through the law's own explicit carve-out (e.g. the
removal-direction no-PR opt-out in `harness/procedures/git_strategy.md`,
which must be QUOTED, never inferred) or the user changes the law itself.
(Fragment: "BEHAVIOR always follows git_strategy.md" -- commands/write_prompt.md.)

## Bounded tiebreakers within the ladder

- **LIVE CODE WINS -- descriptive claims only.** When live code diverges from
  a prior specification document, the code wins for DESCRIPTIVE claims (what
  the system does, what a value resolved to) and NEVER for PRESCRIPTIVE
  constraints (hard rules, security, legal, budget, encoding) -- those are
  rungs 1-4 material, and violating code is a bug to surface. Divergences are
  recorded, not absorbed. (Fragment: harness/templates/plan_schema.md,
  commands/write_prompt.md section 8.)
- **The temporal rule.** A session executes the law it READ AT START. An
  amendment made mid-flight -- to a command, a schema, a procedure -- reaches
  the NEXT dispatch, never the running session. No layer hot-reloads.
  (Fragment: commands/orchestrator.md, "never hot-reloads law".)
- **Lockstep ownership.** A contract held in more than one file has exactly
  ONE owner file; the others mirror it, and every edit updates all holders in
  lockstep. Within rung 6, the owner file wins a mirror drift. (Fragments:
  the ownership clauses in orchestrator.md, handback_schema.md,
  state_schema.md, grill_and_implement.md.)

## The backstop

A GENUINE collision -- two layers commanding incompatible things and the
rules above not resolving it -- triggers the ambiguity protocol: STOP,
surface the collision with a recommendation and the alternatives, and gate on
an explicit user decision. The ladder exists to make that rare, not to make
it unnecessary.

## Where the pieces slot

Every harness deliverable sits on a named rung: registered hook binaries at
rung 1; state files (via their schema) at rung 4; dispatch/phase prompts at
rung 5; commands, agents, procedures, templates, schemas and harness scripts
at rung 6; the preferences key block at rung 7. A new deliverable that does
not obviously slot into one rung is a design smell to resolve before
shipping it.
