# Procedure: Verification CASE Patterns

The five human-verification patterns for phase implementation prompts. The
prompt writer selects exactly ONE case per phase and emits its resolved text.
Project specifics (server entry point, tool names, smoke-test commands, browser
fallbacks) come from `.claude/preferences/verification.md`; if that file is
absent, fall back to the generic placeholders and the plan's own verification
text.

## CASE A -- Phase modifies live server/tool behaviour

(For this project: live server/service/tool paths -- see preferences/verification.md
for the server entry point and tool list.) Title: "Human (live tool spot-check)".

After tests pass, start the server per the project's dev command and call the
tools implemented in this phase with parameters relevant to the changes.
Confirm the response is correct before declaring the phase complete.

If no browser/interactive inspector is available in the session, call the
registered tool functions directly in-process instead (import the server module
and invoke the tool function as a plain function, where the framework permits --
see preferences/verification.md for whether this holds). This exercises the
same code path the inspector would and is an acceptable substitute for the
interactive check, not a reason to skip verification. Prefer the interactive
inspector when a browser is available.

## CASE B -- Non-server code with a specific smoke-test command

Title: "Human (<script-name> smoke-test)". Describe the exact command and what
output confirms success. State what constitutes a valid "no crash" result if
live data (model files, upstream API connection) may be unavailable. If the
smoke-test requires opening a browser or interactive UI, include the project's
open command (see preferences/verification.md) and append: "If you cannot open
a browser (headless environment), state so explicitly rather than claiming
success."

## CASE C -- No live-runtime verification needed

(Experiment branches, analysis-only phases.) Replace the human subsection with
a single line: "Note: This phase has no interactive runtime verification step.
Automated checks in the Automated section above are sufficient."

## CASE D -- Phase builds or modifies a harness mechanism itself

(Hooks, closing-sequence enforcement, marker files, and similar meta-tooling,
where the plan says the check happens live during the plan's own execution.)
Title: "Human (live mechanism sanity check)". Write:
- The specific condition to create (e.g. an intentionally incomplete artifact,
  a missing precondition) that should cause the mechanism to trigger.
- What observing correct behavior looks like (it blocks/fires/no-ops as
  designed), then what confirms the corrected state (it allows/clears once
  fixed).
- The instruction: "If this live check cannot be performed in this session,
  state so explicitly rather than claiming success -- do not declare the phase
  complete without it."

## CASE E -- Fully automated phase with a manual review action

(A script or session writes a report/document; the plan's verification includes
a manual read; no server or interactive app to spot-check.) Title:
"Human (report review)". Write:
- The manual-review bullet(s) VERBATIM from the plan's phase-specific
  Verification section.
- Plainly what the reviewer needs to confirm is present or correct in the
  output artifact -- name the artifact path and the specific content to check.
- The note: "No live app or service interaction is needed for this phase -- this is
  a document/report review only."
