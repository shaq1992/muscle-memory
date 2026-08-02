# Preferences

Single project-opinion surface, generated at `.claude/preferences.md` by
/bootstrap and filled in by the user (or by /on-board elicitation). The
contiguous `key: value` block below is machine-parseable (one key per line, no
prose on the line) -- hooks and commands read it directly; inline defaults
apply when the file is absent. The self-improver never edits this file.

Keys ship as working defaults; change a value only if your project's
conventions differ. Bracketed values are placeholders to fill in.

user_name: [your name -- commands address you with it at runtime]
default_branch: main
protected_branch: main
integration_branch_prefix: integration/
phase_branch_pattern: <plan_name>-phase-<NN>
phase_number_padding: 2
merge_style: merge-commit
retain_integration_branch: true
interpreter: [project-code interpreter -- e.g. venv/bin/python, python3, node]
test_command: [full project test-suite command -- e.g. venv/bin/pytest tests/ -v, npm test]
encoding_constraint: [e.g. "ASCII-only source and output (cp1252 console)", or "UTF-8 throughout, no constraint"]

`harness_push_remote` is deliberately NOT set here: it is the fail-closed
allowlist for pushes made from inside the harness repo at `.claude/`. Only the
harness AUTHOR's machine sets it; without the key the guardrail hook blocks
ALL harness-repo pushes, which is the correct posture for recipients.

## Verification

- Harness hooks/scripts/tests always run on stdlib bare `python3`
  (suite: `python3 -m unittest discover .claude/harness/tests`) -- independent
  of `interpreter`, which governs project code only.
- Tests-as-deliverables policy: [when committed tests are warranted vs.
  optional -- e.g. "warranted for production code paths, optional for one-off
  probe scripts"].
- Artifact-opening environment: [e.g. "WSL headless: use `wslview <file>` or a
  local `http.server`", or "desktop browser available"]. If an artifact cannot
  be opened, say so explicitly rather than claiming success.
- Session prompt files go in `docs/prompts/DDMMYY/`; `.claude/`, `CLAUDE.md`,
  `docs/`, `context/` stay gitignored in the project repo.

## Monitoring

- Any command expected to exceed ~45s runs `run_in_background: true` per
  harness/procedures/monitoring.md; one Monitor at a time; TaskStop when done.
- Grep filters: always `[ERROR]|[FATAL]|[DONE]`; add `[RESULT]|[PROGRESS]`
  when progress visibility is needed.
- Project-specific long-running commands, progress markers, and log locations:
  [fill in as scripts appear, or "none yet"].
