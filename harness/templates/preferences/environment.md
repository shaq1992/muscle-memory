# Preference: Environment and Invocation

Project-specific environment rules. Edit the placeholders below for this project;
leave the structure intact.

## Interpreter / invocation

- Interpreter invocation for this project: [fill in -- e.g. `venv/bin/python
  script.py`, `python3 script.py`, `node script.js`; state whether a bare
  interpreter is on PATH or a project-local one must be used].
- Test/tooling invocation: [fill in -- e.g. `venv/bin/pytest tests/ -v`, `npm
  test`; match what verification.md expects].
- Hooks registered in `.claude/settings.json` use this same interpreter -- keep
  the hook `command` fields consistent with the invocation above.

## Encoding constraint

- Source-file / console encoding constraint for this project: [fill in -- e.g.
  "ASCII-only: the target console is cp1252 and cannot render em dashes, arrows,
  `>=` symbols, superscripts; use ASCII equivalents", or "UTF-8 throughout, no
  constraint"].
- Always pass `encoding="utf-8"` explicitly to file-open calls when content might
  be non-ASCII (language-appropriate equivalent if not Python).

## File-location rules

- Session prompt files (grill-me inputs, implementation prompts) go in
  `docs/prompts/DDMMYY/` (dated subdirs). `docs/` is entirely gitignored.
- AI-facing scaffolding never enters version control: `.claude/`, `CLAUDE.md`,
  `docs/`, `context/`, `.claude_archive/` are all gitignored.
- Any additional project-specific location rules: [fill in, or delete this line].
