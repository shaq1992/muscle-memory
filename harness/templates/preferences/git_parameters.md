# Preference: Git Parameters

Project-specific git parameters consumed by harness/procedures/git_strategy.md
and by hooks. Keep the `key: value` lines below machine-parseable (one per line,
no prose on the line) -- hooks read them directly. These ship as working
defaults; change a value only if your project's git conventions differ.

integration_branch_prefix: integration/
phase_branch_pattern: <plan_name>-phase-<NN>
phase_number_padding: 2
default_branch: main
protected_branch: main
approval_marker_path: .claude/approvals/<plan_name>_main_merge.json

## Notes

- Plan slugs are kebab-case (lowercase alphanumeric + hyphens), max 20 chars.
- Phase numbers are always zero-padded two-digit (`01` ... `10`).
- Merges are always `git merge --no-ff <branch> -m "merge: ..."` -- never a bare
  merge without a message.
- Under the unified strategy, phase-level pushes are autonomous and ONLY the
  integration-to-main merge + main push is permission-gated (see git_strategy.md).
- No AI attribution in any commit or merge message, ever.
