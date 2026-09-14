"""UserPromptSubmit hook: deterministic ARMING of the handback marker.

Companion to enforce_handback.py, which enforces the orchestrated-session
handback obligation at Stop time but is a structural no-op unless
.claude/handback_session.json exists with a matching session_id. Before this
hook, that marker was written only by the dispatched session itself
(commands/grill_and_implement.md Step 0a item 2) -- model obedience, not
mechanism. A session that skipped Step 0a was never armed, and the Stop hook
silently allowed a free-form handback to close (observed: plan
peer-route-advantage session 40, 2026-09-03). This hook makes the arming
deterministic: the marker is written the moment the dispatched prompt is
SUBMITTED, before the model has read a word of it.

Trigger: the submitted prompt carries a "## Orchestration" block with a
"- **Handback:**" field. That is the SAME presence signal
commands/grill_and_implement.md keys its orchestrated mode on. The block's
shape is owned by commands/orchestrator.md Step 7 and produced by
harness/scripts/assemble_dispatch.py (orchestration_block()); this hook is a
third consumer of it, so a change to the heading or the bolded field names
there must update the regexes here in lockstep.

The text scanned is the literal submitted prompt PLUS the contents of every
prompt file it references. Dispatched prompts are routinely handed over as a
FILE REFERENCE -- the submitted text is just
"/grill_and_implement @docs/prompts/<date>/<plan>_session_<NN>_prompt.md" --
and while Claude Code expands that @-mention into the model's context, the
UserPromptSubmit payload's "prompt" is the literal text, so a hook that
scanned only the literal text saw a path, found no block, and exited 0
silently, leaving the session un-armed (observed: plan ai-mirror-demo
session 01, 2026-09-15; the Step 0a fallback wrote the marker that time,
which is exactly the model obedience this hook exists to replace). A
reference is (a) an "@"-prefixed path token, plain (@docs/prompts/x.md) or
quoted (@"path with spaces.md"), or (b) any bare token ending in ".md" that
resolves to an existing file. Relative paths resolve against
CLAUDE_PROJECT_DIR when set, else the payload's "cwd" when present, else the
parent of this .claude/ directory. Each file is read as UTF-8 (undecodable
bytes replaced) and capped at REF_FILE_MAX_BYTES; missing, unreadable,
non-file or oversized-beyond-cap references are skipped silently. Segments
are scanned in order -- the literal prompt first, then each referenced file
in order of first mention -- and the FIRST segment yielding a usable block
(heading plus Handback field) wins; any later block is ignored.

On trigger, the hook writes .claude/handback_session.json with EXACTLY the
key names and value shapes that grill_and_implement.md Step 0a item 2
specifies and enforce_handback.py reads:

    {
      "session_id":     <the UserPromptSubmit event's session_id>,
      "plan_name":      <plan name>,
      "session_number": <NN, as the string from the block>,
      "handback_path":  <verbatim value of the block's Handback: field>
    }

plan_name and session_number are parsed from the "- **Branch:**" field's
value, "<plan_name>-session-<NN>" (the value is the text on the field's own
line only -- the "(cut from ...)" continuation line is annotation, never part
of it); if the Branch field is absent or unparseable, they are derived from
the conventional handback path docs/orchestration/<plan>/handbacks/<NN>.md,
and failing that are written as null, which enforce_handback.py already
treats as manifest-underivable (its receipt check degrades to a structural
no-op while the handback obligation itself still fires).

The session-side write in grill_and_implement.md Step 0a item 2 remains in
place as a FALLBACK for projects whose settings.json predates this hook's
registration; re-writing the same marker is idempotent and harmless.

No "## Orchestration" block, no Handback field, or no usable session_id ->
exit 0 silently, writing nothing. FAIL SOFT everywhere: this hook must never
block or delay a prompt, so every parse oddity and every write failure exits
0 with no output. (On UserPromptSubmit, exit 2 blocks the prompt and stdout
is injected as context; this hook deliberately does neither.) The marker is
written atomically (temp file + os.replace) so a half-written file can never
trip enforce_orchestrator_isolation.py-style corruption handling downstream.

Stdlib-only, ASCII-only, like every hook in this corpus.
"""

import json
import os
import re
import sys
import tempfile

HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(HOOK_DIR)
MARKER_PATH = os.path.join(CLAUDE_DIR, "handback_session.json")

# The block heading, exactly as commands/orchestrator.md Step 7 fixes it and
# commands/grill_and_implement.md detects it.
BLOCK_HEADING_RE = re.compile(r"^## Orchestration[ \t]*$", re.MULTILINE)
# The next H2 heading ends the block's scope (by construction the block is
# appended last, so this is usually end-of-prompt).
NEXT_HEADING_RE = re.compile(r"^## ", re.MULTILINE)

# The bolded field lines per assemble_dispatch.py orchestration_block().
HANDBACK_FIELD_RE = re.compile(
    r"^-[ \t]*\*\*Handback:\*\*[ \t]*(\S+)[ \t]*$", re.MULTILINE
)
BRANCH_FIELD_RE = re.compile(
    r"^-[ \t]*\*\*Branch:\*\*[ \t]*(\S+)[ \t]*$", re.MULTILINE
)

# <plan_name>-session-<NN>, per orchestrator.md Step 7.
BRANCH_VALUE_RE = re.compile(r"^(.+)-session-(\d+)$")
# Conventional handback path fallback: .../docs/orchestration/<plan>/
# handbacks/<NN>.md.
HANDBACK_PATH_RE = re.compile(
    r"(?:^|/)docs/orchestration/([^/]+)/handbacks/([^/]+)\.md$"
)

# Prompt-file references embedded in the submitted text (see the docstring's
# Trigger paragraph). Quoted forms first so a path with spaces is captured
# whole; the plain form takes the run of non-whitespace after the "@".
AT_REF_QUOTED_RE = re.compile(r"@\"([^\"]+)\"|@'([^']+)'")
AT_REF_PLAIN_RE = re.compile(r"(?<![\w@])@([^\s\"'@]+)")
# Trailing punctuation a path token may carry in prose ("see @x.md," etc.).
REF_STRIP_CHARS = "\"'`<>()[]{},;:!?"
# Per-file read cap for referenced prompt files (~1 MB).
REF_FILE_MAX_BYTES = 1000000


def _project_dir(payload):
    """Base directory for relative references: CLAUDE_PROJECT_DIR when set,
    else the payload's cwd when present, else the parent of .claude/."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if isinstance(env_dir, str) and env_dir.strip():
        return env_dir
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd
    return os.path.dirname(CLAUDE_DIR)


def _referenced_paths(prompt):
    """Candidate prompt-file references in order of first mention, deduped:
    "@"-prefixed tokens (quoted or plain) and bare tokens ending in ".md".
    Existence is NOT checked here; _read_referenced_files skips misses."""
    if not isinstance(prompt, str):
        return []
    found = []
    seen = set()

    def add(candidate):
        candidate = candidate.strip().strip(REF_STRIP_CHARS)
        if candidate and candidate not in seen:
            seen.add(candidate)
            found.append(candidate)

    # Position-ordered so "first block found" is well defined across forms.
    hits = []
    for m in AT_REF_QUOTED_RE.finditer(prompt):
        hits.append((m.start(), m.group(1) or m.group(2)))
    # Blank out the quoted spans so the plain form cannot re-match the
    # leading word of a quoted path.
    unquoted = AT_REF_QUOTED_RE.sub(lambda m: " " * len(m.group(0)), prompt)
    for m in AT_REF_PLAIN_RE.finditer(unquoted):
        hits.append((m.start(), m.group(1)))
    for m in re.finditer(r"\S+", unquoted):
        token = m.group(0).strip(REF_STRIP_CHARS)
        if token.startswith("@"):
            continue
        if token.lower().endswith(".md"):
            hits.append((m.start(), token))
    for _, candidate in sorted(hits, key=lambda h: h[0]):
        add(candidate)
    return found


def _read_referenced_files(prompt, base_dir):
    """Contents of each referenced file that resolves to a readable regular
    file, in reference order. Every failure is skipped silently."""
    texts = []
    for ref in _referenced_paths(prompt):
        try:
            path = ref if os.path.isabs(ref) else os.path.join(base_dir, ref)
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                data = f.read(REF_FILE_MAX_BYTES)
            texts.append(data.decode("utf-8", errors="replace"))
        except Exception:
            continue
    return texts


def _parse_orchestration(prompt):
    """(handback_path, plan_name, session_number) from the prompt's
    "## Orchestration" block, or None when the prompt carries no block or
    the block has no Handback field. plan_name/session_number are None when
    underivable -- the caller still arms on the handback path alone."""
    if not isinstance(prompt, str):
        return None
    heading = BLOCK_HEADING_RE.search(prompt)
    if heading is None:
        return None
    block = prompt[heading.end():]
    nxt = NEXT_HEADING_RE.search(block)
    if nxt is not None:
        block = block[:nxt.start()]

    handback_match = HANDBACK_FIELD_RE.search(block)
    if handback_match is None:
        return None
    handback_path = handback_match.group(1)

    plan_name = None
    session_number = None
    branch_match = BRANCH_FIELD_RE.search(block)
    if branch_match is not None:
        value_match = BRANCH_VALUE_RE.match(branch_match.group(1))
        if value_match is not None:
            plan_name = value_match.group(1)
            session_number = value_match.group(2)
    if plan_name is None:
        path_match = HANDBACK_PATH_RE.search(handback_path)
        if path_match is not None:
            plan_name = path_match.group(1)
            session_number = path_match.group(2)
    return handback_path, plan_name, session_number


def _write_marker_atomically(marker):
    """Write MARKER_PATH via temp file + os.replace; exceptions propagate
    to main()'s fail-soft catch."""
    fd, tmp_path = tempfile.mkstemp(
        prefix=".handback_session.", suffix=".tmp", dir=CLAUDE_DIR
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(marker, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, MARKER_PATH)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    if not isinstance(payload, dict):
        sys.exit(0)

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        # A marker without a real session_id can never legitimately match
        # a Stop event; arming with one would be noise, not enforcement.
        sys.exit(0)

    prompt = payload.get("prompt")
    # Literal prompt first, then each referenced prompt file in order of
    # first mention; the first segment with a usable block wins.
    parsed = _parse_orchestration(prompt)
    if parsed is None:
        for text in _read_referenced_files(prompt, _project_dir(payload)):
            parsed = _parse_orchestration(text)
            if parsed is not None:
                break
    if parsed is None:
        sys.exit(0)

    handback_path, plan_name, session_number = parsed
    _write_marker_atomically(
        {
            "session_id": session_id,
            "plan_name": plan_name,
            "session_number": session_number,
            "handback_path": handback_path,
        }
    )
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # Fail SOFT: an arming hook must never block or delay a prompt.
        sys.exit(0)
