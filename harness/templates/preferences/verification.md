# Preference: Project Verification Specifics

Project-specific parameters for harness/procedures/verification_cases.md

## Test suite

- Full suite command: [fill in -- e.g. `venv/bin/pytest tests/ -v`, `npm test`;
  match environment.md].
- Tests-as-deliverables policy: [fill in -- when committed tests are warranted
  vs. optional; e.g. "warranted for production code paths, optional for one-off
  experiment/measurement harnesses"].

## Application smoke-check (verification CASE A parameters)

- Application entry point.
- How to exercise it
- Key surfaces to spot-check: [fill in -- e.g. the specific endpoints, tools,
  commands, or functions that must respond].

## End-to-end verification

[Ignore for now, to be decided later]

## Browser-dependent checks

- Environment for opening artifacts: [fill in -- e.g. "WSL headless: use `wslview
  <file>` or a local `http.server`", or "desktop with a browser available"]. If a
  browser cannot be opened, state so explicitly rather than claiming success.
