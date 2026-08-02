"""Validate a generated phase implementation prompt.

Usage: python3 .claude/harness/scripts/validate_prompt.py <prompt_file>
Run from the PROJECT ROOT -- @-references are resolved against the current
working directory, exactly as the prompt's reader will resolve them.

Checks (deterministic, stdlib-only; no ASCII scan by design):
  at-ref        every template-emitted @-reference resolves on disk
  placeholder   no leftover [PLACEHOLDER] / bracketed template instruction text
  sections      all 11 required template sections present
  branch-sanity resolved git parameters are coherent (integration/<slug>,
                <slug>-phase-NN zero-padded, NN <= total)

Exemptions (mirroring the write_prompt template's own rules): fenced code
blocks, inline code spans, and section 10 (verbatim-injected learnings) are
never scanned for at-refs or placeholder residue; markdown checkboxes
("[ ]" / [x]") are not residue.

Failure contract: one "FAIL <check>: <detail>" line per finding on stdout,
exit code 1. Success: "OK: all checks passed", exit code 0.
"""

import os
import re
import sys

REQUIRED_SECTIONS = {
    1: "Before You Start",
    2: "Project Overview",
    3: "Current Codebase State",
    4: "Phase Objective",
    5: "Deliverables",
    6: "Definition of Done",
    7: "Verification",
    8: "Constraints",
    9: "Resolved Parameters",
    10: "Accumulated Learnings",
    11: "End of Phase",
}

AT_REF_RE = re.compile(r"(?<![\w`])@([A-Za-z0-9_./-]+)")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
CHECKBOX_RE = re.compile(r"^\s*-\s\[( |x|X)\]\s")
SECTION_HEADER_RE = re.compile(r"^## (\d+)\.\s")

# Bracketed template-instruction residue: exact placeholder tokens the
# template uses, or bracket content opening with a template leadword.
PLACEHOLDER_TOKENS = {
    "PLACEHOLDER", "N", "NN", "bool", "plan_name", "total", "name",
    "Phase Name", "YYYY-MM-DD", "letter -- title", "selected case title",
}
INSTRUCTION_LEADS = (
    "If ", "Only if ", "OVERRIDE", "DEFAULT:", "Verbatim", "Step ",
    "The Step", "The ONE resolved", "2-3 sentences", "one-line project",
    "Final phase only", "Non-final phase", "Reference-files block",
    "Bulleted", "Checklist", "Exact commands", "Test-suite command",
)
BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")


def scannable_lines(lines):
    """Yield (line_number, text) for lines subject to residue/at-ref checks.

    Skips fenced code blocks and everything inside section 10 (the
    verbatim-injected learnings). Inline code spans are blanked out.
    """
    in_fence = False
    in_section_10 = False
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = SECTION_HEADER_RE.match(line)
        if m:
            in_section_10 = int(m.group(1)) == 10
        if in_section_10:
            continue
        yield i, INLINE_CODE_RE.sub("", line)


def check_at_refs(lines, failures):
    for lineno, text in scannable_lines(lines):
        for m in AT_REF_RE.finditer(text):
            token = m.group(1).rstrip(".,;:)]'\"")
            if not token or token.startswith("-"):
                continue
            if "/" not in token and "." not in token:
                continue
            if not os.path.exists(token):
                failures.append(
                    "FAIL at-ref: @{0} does not resolve on disk "
                    "(line {1})".format(token, lineno)
                )


def check_placeholders(lines, failures):
    for lineno, text in scannable_lines(lines):
        if CHECKBOX_RE.match(text):
            text = CHECKBOX_RE.sub("- ", text)
        for m in BRACKET_RE.finditer(text):
            content = m.group(1)
            is_residue = (
                content.strip() in PLACEHOLDER_TOKENS
                or content.startswith(INSTRUCTION_LEADS)
            )
            if is_residue:
                failures.append(
                    "FAIL placeholder: leftover template text '[{0}]' "
                    "(line {1})".format(content, lineno)
                )


def check_sections(lines, failures):
    found = {}
    for line in lines:
        m = SECTION_HEADER_RE.match(line)
        if m:
            found[int(m.group(1))] = line.strip()
    for num, title in sorted(REQUIRED_SECTIONS.items()):
        if num not in found:
            failures.append(
                "FAIL sections: missing required section '## {0}. {1} "
                "...'".format(num, title)
            )
        elif title not in found[num]:
            failures.append(
                "FAIL sections: section {0} header is {1!r}; expected it to "
                "contain '{2}'".format(num, found[num], title)
            )


def check_branch_sanity(text, failures):
    # Operate on section 9 only.
    m = re.search(r"^## 9\.[^\n]*\n(.*?)(?=^## \d+\.|\Z)", text, re.M | re.S)
    if not m:
        return  # missing section already reported by check_sections
    body = re.sub(r"\s+", " ", m.group(1))

    pm = re.search(
        r"plan_name:\s*([a-z0-9-]+)\s*--\s*phase\s*(\d+)\s*of\s*(\d+)", body
    )
    ib = re.search(r"integration branch:\s*([^\s;]+)", body)
    pb = re.search(r"phase branch:\s*([^\s;]+)", body)

    if pm is None or ib is None or pb is None:
        failures.append(
            "FAIL branch-sanity: could not parse plan_name/phase/total, "
            "integration branch, and phase branch from section 9"
        )
        return

    slug, phase_str, total_str = pm.group(1), pm.group(2), pm.group(3)
    phase, total = int(phase_str), int(total_str)

    if ib.group(1) != "integration/{0}".format(slug):
        failures.append(
            "FAIL branch-sanity: integration branch {0!r} does not match "
            "'integration/{1}'".format(ib.group(1), slug)
        )
    expected_pb = "{0}-phase-{1:02d}".format(slug, phase)
    if pb.group(1) != expected_pb:
        failures.append(
            "FAIL branch-sanity: phase branch {0!r} does not match "
            "'{1}' (zero-padded NN)".format(pb.group(1), expected_pb)
        )
    if not 1 <= phase <= total:
        failures.append(
            "FAIL branch-sanity: phase {0} is out of range for a "
            "{1}-phase plan".format(phase, total)
        )


def main(argv):
    if len(argv) != 2:
        print("Usage: python3 validate_prompt.py <prompt_file>")
        return 2
    path = argv[1]
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        print("FAIL at-ref: prompt file unreadable: {0}".format(exc))
        return 1

    lines = text.splitlines()
    failures = []
    check_at_refs(lines, failures)
    check_placeholders(lines, failures)
    check_sections(lines, failures)
    check_branch_sanity(text, failures)

    if failures:
        for line in failures:
            print(line)
        return 1
    print("OK: all checks passed ({0})".format(path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
