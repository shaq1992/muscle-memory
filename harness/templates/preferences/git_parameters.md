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
merge_style: merge-commit
retain_integration_branch: true

## Notes

- Plan slugs are kebab-case (lowercase alphanumeric + hyphens), max 20 chars.
- Phase numbers are always zero-padded two-digit (`01` ... `10`).
- Phase merges use git defaults, always with an explicit message
  (`git merge <branch> -m "merge: ..."` -- never a bare merge without one).
- Phase-level pushes are autonomous; the protected branch is reached ONLY via
  a pull request merged by the USER (`! gh pr merge`) -- see git_strategy.md.
- `merge_style` / `retain_integration_branch` are the plan-end PR merge
  defaults (`gh pr merge --merge`; integration branch kept). Deletion is
  per-plan opt-in.
- `harness_push_remote` (deliberately NOT set here): the fail-closed allowlist
  for pushes made from inside the harness repo at `.claude/`. Only the harness
  AUTHOR's own machine sets it; without the key the guardrail hook blocks ALL
  harness-repo pushes, which is the correct posture for recipients.
- No AI attribution in any commit or merge message, ever.
