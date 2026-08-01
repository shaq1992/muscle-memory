# Preferences Index

Project-specific per-concern preference files. Commands and procedures read
these for project parameters; each states its fallback when a file is absent.
The self-improver never edits this directory -- project opinion is user-edited.

- `git_parameters.md` -- machine-parseable git parameters (integration prefix,
  phase-branch pattern, protected branch, merge defaults, push-remote
  allowlist); read by hooks. Ships with working defaults.
- `environment.md` -- interpreter/invocation rules, source encoding constraint,
  gitignored-scaffolding file-location rules.
- `verification.md` -- test-suite invocation, application smoke-check specifics,
  browser/headless fallbacks.
- `monitoring.md` -- long-running-command list + background rules, project grep
  patterns, log locations.
