"""PreToolUse guard for Read / Edit / Grep / Bash: deterministic secret-read denial.

Deterministic pattern matching, never model judgement. It DENIES:

  1. Read / Edit of a .env-family file (.env, .env.<anything>, .envrc), and a
     Grep tool call whose path or glob names one. Template names -- a final
     suffix of example / sample / template / schema / defaults, e.g.
     .env.example -- stay readable: they are how a session learns the keys.
  2. Bash that reads, loads, copies or pipes a .env-family file: any command
     given one as an operand or as `< file` input, unless the command only
     handles the NAME (echo, ls, test, touch, chmod, find without -exec,
     git check-ignore / ls-files / rm / status, docker other than
     `compose config`). Command substitutions, `bash -c` strings, heredocs
     fed to a shell and interpreter `-c` / `-e` code are checked too; xargs
     anywhere in a command that names a .env file is denied.
  3. Environment dumps: printenv, bare env / set / export / declare -x|-p,
     /proc/*/environ, `docker compose config` (prints .env values
     interpolated), and echo / printf of a secret-named variable
     ($API_KEY, ${DB_PASSWORD}, ...).
  4. Unscoped recursive search, which opens gitignored .env files without
     naming them (the s17 leak): grep-family -r / -R / --recursive /
     -d recurse, rg / ag flags that search hidden or ignored files, rg globs
     aimed at dotfiles, and git grep --untracked / --no-index /
     --no-exclude-standard. Scoped search stays allowed:
     `git ls-files | xargs grep`, `grep -r ... $(git ls-files)`, plain
     `git grep`, and plain rg / ag (they skip hidden and gitignored files).

Write is not handled: creating a .env does not expose one.

Allow = exit 0 with no stdout (the normal permission flow continues).
Deny  = PreToolUse JSON decision on stdout, exit 0.
Fail-open on malformed payloads, like git_guardrails.py. The hook never opens
a file; it decides on the tool input text alone.

Pattern families and test cases adapted from karanb192/claude-code-hooks,
plugins/protect-secrets/protect-secrets.js and its test file:

  MIT License
  Copyright (c) 2026 Karan Bansal
  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to
  deal in the Software without restriction, including without limitation the
  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
  sell copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions: The above
  copyright notice and this permission notice shall be included in all copies
  or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS",
  WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.

Deliberately NOT ported: upstream allows a whole Bash command when ANY
template name appears in it, so `cat .env.example && cat .env` passes; here
every operand is judged on its own.
"""

import json
import os
import re
import shlex
import sys

ENV_NAME_RE = re.compile(r"^\.env(?:rc)?(?:[.*?\[][^/\\]*)?$")
TEMPLATE_SUFFIX_RE = re.compile(
    r"\.(?:example|sample|template|schema|defaults)$", re.IGNORECASE
)
# A .env name inside free text (interpreter code, heredoc bodies).
ENV_IN_TEXT_RE = re.compile(r"(?<![\w.-])\.env(?:rc)?(?:\.[A-Za-z0-9_.-]*)?(?![\w])")
PROC_ENVIRON_RE = re.compile(r"/proc/[^/\s]+/environ")
SECRET_VAR_RE = re.compile(r"\$\{?!?([A-Z][A-Z0-9_]*)\}?")
SECRET_WORDS = {
    "SECRET", "SECRETS", "KEY", "KEYS", "TOKEN", "PASSWORD", "PASSWD", "PASS",
    "PASSPHRASE", "CREDENTIAL", "CREDENTIALS", "APIKEY", "PAT",
}
SECRET_LAST_WORDS = {"AUTH", "PRIVATE"}

_SHELL_OPERATORS = {"&&", "||", ";", ";;", "|", "|&", "&", "(", ")"}
_WRAPPERS = {"command", "nohup", "time", "sudo", "exec", "nice", "builtin"}
_KEYWORDS = {"do", "then", "else", "elif", "if", "while", "until", "!", "{", "}"}
_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
_INTERPRETERS = {"python", "python3", "node", "ruby", "perl", "php"}

# Commands that only handle a file's NAME, so a .env operand is harmless.
_NAME_ONLY = {
    "echo", "printf", "ls", "stat", "test", "[", "[[", "]", "]]", "touch",
    "chmod", "chown", "file", "realpath", "basename", "dirname", "readlink",
}
_GIT_NAME_ONLY = {"check-ignore", "ls-files", "rm", "status"}
_FIND_EXEC = {"-exec", "-execdir", "-ok", "-okdir"}

_GREP_FAMILY = {"grep", "egrep", "fgrep", "ugrep", "ug", "zgrep"}
_RG_HIDDEN_LONG = ("--hidden", "--unrestricted", "--no-ignore")
_AG_HIDDEN_LONG = ("--hidden", "--unrestricted", "--skip-vcs-ignores")
_GIT_GREP_UNSCOPED = {"--untracked", "--no-index", "--no-exclude-standard"}
_XARGS_VALUE_OPTS = {"-n", "-I", "-P", "-d", "-L", "-s", "-E", "-a"}
_DOCKER_VALUE_OPTS = {
    "-f", "--file", "-p", "--project-name", "--env-file", "--profile",
    "--project-directory", "--ansi", "--parallel", "-c", "--context", "-H",
    "--host", "--log-level", "--config",
}

SUBST_TOKEN = "__PROTECT_SECRETS_SUBST_{0}__"
SUBST_TOKEN_RE = re.compile(r"__PROTECT_SECRETS_SUBST_(\d+)__")

ENV_REASON = (
    "protect_secrets: {0!r} is a .env secret file -- never read, load, copy or "
    "search it, by any tool. Use .env.example (same keys, placeholder values) "
    "for its structure."
)
DUMP_REASON = (
    "protect_secrets: {0} prints the process environment or a secret "
    "variable, which can hold credentials. Use .env.example for key names; "
    "echo only non-secret variables."
)
COMPOSE_REASON = (
    "protect_secrets: `docker compose config` prints the compose file with "
    ".env values interpolated. Read the compose file itself instead."
)
RECURSIVE_REASON = (
    "protect_secrets: {0} can open gitignored .env files without naming them "
    "(the recursive-grep leak). Scope the search to tracked files: "
    "`git ls-files -z | xargs -0 grep -n PATTERN`, `git grep PATTERN`, or "
    "plain `rg PATTERN` (it skips hidden and gitignored files)."
)


class Denied(Exception):
    pass


def _allow():
    sys.exit(0)


def _deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


# ---------------------------------------------------------------------------
# Path checks (Read / Edit / Grep and Bash operands)
# ---------------------------------------------------------------------------
def is_env_path(path):
    if not isinstance(path, str) or not path:
        return False
    base = re.split(r"[/\\]", path.rstrip("/\\"))[-1]
    return bool(ENV_NAME_RE.match(base)) and not TEMPLATE_SUFFIX_RE.search(base)


def env_names_in_text(text):
    return [m.group(0) for m in ENV_IN_TEXT_RE.finditer(text)
            if not TEMPLATE_SUFFIX_RE.search(m.group(0))]


def _operand_candidates(token):
    yield token
    if "=" in token:
        yield token.split("=", 1)[1]


def _env_operand(token):
    for cand in _operand_candidates(token):
        if is_env_path(cand):
            return cand
    return None


# ---------------------------------------------------------------------------
# Bash parsing
# ---------------------------------------------------------------------------
def _strip_heredocs(command, check):
    """Drop heredoc bodies; a body fed to a shell or interpreter is checked."""
    lines = command.split("\n")
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        m = re.search(r"(?<!<)<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line)
        if not m:
            continue
        delim = m.group(2)
        body = []
        while i < len(lines) and lines[i].strip() != delim:
            body.append(lines[i])
            i += 1
        i += 1  # the delimiter line
        prefix = re.split(r"[;&|(]", line[:m.start()])[-1].split()
        words = [w for w in prefix if w not in _WRAPPERS
                 and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w)]
        cmd = os.path.basename(words[0]) if words else ""
        text = "\n".join(body)
        if cmd in _SHELLS:
            check(text)
        elif cmd in _INTERPRETERS or re.match(r"^python3?(\.\d+)?$", cmd):
            names = env_names_in_text(text)
            if names:
                raise Denied(ENV_REASON.format(names[0]))
    return "\n".join(out)


def _extract_substitutions(command, check):
    """Replace $(...), <(...) and `...` with placeholder tokens.

    Each inner command is checked recursively; returns the rewritten command
    and the list of inner texts (indexed by placeholder number).
    """
    inners = []
    out = []
    i = 0
    n = len(command)
    in_single = False
    while i < n:
        c = command[i]
        if c == "'" and not in_single:
            # single-quoted text is literal: copy through to the closing quote
            j = command.find("'", i + 1)
            if j == -1:
                out.append(command[i:])
                break
            out.append(command[i:j + 1])
            i = j + 1
            continue
        if c in "$<" and i + 1 < n and command[i + 1] == "(" and not (
            c == "$" and i + 2 < n and command[i + 2] == "("
        ):
            depth = 1
            j = i + 2
            while j < n and depth:
                if command[j] == "(":
                    depth += 1
                elif command[j] == ")":
                    depth -= 1
                j += 1
            inner = command[i + 2:j - 1] if depth == 0 else command[i + 2:]
            check(inner)
            out.append(" " + SUBST_TOKEN.format(len(inners)) + " ")
            inners.append(inner)
            i = j
            continue
        if c == "`":
            j = command.find("`", i + 1)
            if j == -1:
                j = n
            inner = command[i + 1:j]
            check(inner)
            out.append(" " + SUBST_TOKEN.format(len(inners)) + " ")
            inners.append(inner)
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out), inners


def _newlines_to_separators(command):
    """Turn unquoted newlines into ';' so one shlex pass respects quotes."""
    out = []
    quote = None
    i = 0
    while i < len(command):
        c = command[i]
        if quote:
            if c == "\\" and quote == '"' and i + 1 < len(command):
                out.append(command[i:i + 2])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "\\" and i + 1 < len(command):
            out.append(command[i:i + 2])
            i += 2
            continue
        elif c == "\n":
            out.append(" ; ")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _split_segments(command):
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        tokens = command.split()
    segments = []
    current = []
    for tok in tokens:
        if tok in _SHELL_OPERATORS:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(tok)
    if current:
        segments.append(current)
    return segments


def _command_start(tokens):
    """Skip keywords, env assignments and wrappers; return (index, env_seen)."""
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t in _KEYWORDS or t in _WRAPPERS:
            i += 1
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
            continue
        if t == "env":
            # env's own options, then assignments, then the real command
            i += 1
            while i < n and tokens[i].startswith("-"):
                i += 2 if tokens[i] in ("-u", "--unset", "-C", "--chdir") else 1
            if i >= n or all(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t)
                             for t in tokens[i:]):
                raise Denied(DUMP_REASON.format("bare `env`"))
            continue
        break
    return i


def _short_cluster(tok):
    return tok.startswith("-") and not tok.startswith("--") and len(tok) > 1


def _check_grep_family(cmd, args, inners):
    if cmd == "rgrep":
        raise Denied(RECURSIVE_REASON.format("`rgrep`"))
    recursive = None
    for k, a in enumerate(args):
        if a in ("--recursive", "--dereference-recursive") or a.startswith(
            "--directories=recurse"
        ) or (a in ("-d", "--directories") and k + 1 < len(args)
              and args[k + 1] == "recurse") or (
            _short_cluster(a) and re.search(r"[rR]", a[1:])
        ):
            recursive = a
            break
    if recursive is None:
        return
    scoped = any(
        SUBST_TOKEN_RE.fullmatch(a)
        and re.match(r"\s*git\s+ls-files\b", inners[int(SUBST_TOKEN_RE.fullmatch(a).group(1))])
        for a in args
    )
    if not scoped:
        raise Denied(RECURSIVE_REASON.format("`{0} {1}`".format(cmd, recursive)))


def _glob_hits_dotfiles(value):
    v = value.strip("'\"")
    if v.startswith("!"):
        return False
    return v.startswith(".") or "/." in v or ".env" in v


def _check_rg(args):
    for k, a in enumerate(args):
        if a.startswith(_RG_HIDDEN_LONG) or a == "-.":
            raise Denied(RECURSIVE_REASON.format("`rg {0}`".format(a)))
        if _short_cluster(a) and not a.startswith(("-g", "-e", "-t", "-T")) and (
            "u" in a[1:] or "." in a[1:]
        ):
            raise Denied(RECURSIVE_REASON.format("`rg {0}`".format(a)))
        value = None
        if a in ("-g", "--glob", "--iglob") and k + 1 < len(args):
            value = args[k + 1]
        elif a.startswith(("--glob=", "--iglob=")):
            value = a.split("=", 1)[1]
        elif a.startswith("-g") and len(a) > 2:
            value = a[2:]
        if value is not None and _glob_hits_dotfiles(value):
            raise Denied(RECURSIVE_REASON.format("`rg` with glob {0!r}".format(value)))


def _check_ag(args):
    for a in args:
        if a.startswith(_AG_HIDDEN_LONG) or (
            _short_cluster(a) and re.search(r"[uU]", a[1:])
        ):
            raise Denied(RECURSIVE_REASON.format("`ag {0}`".format(a)))


def _check_git(args, all_segments):
    sub_i = 0
    while sub_i < len(args) and args[sub_i].startswith("-"):
        sub_i += 2 if args[sub_i] in ("-C", "-c", "--git-dir", "--work-tree") else 1
    if sub_i >= len(args):
        return
    sub = args[sub_i]
    rest = args[sub_i + 1:]
    if sub == "grep":
        for a in rest:
            if a in _GIT_GREP_UNSCOPED:
                raise Denied(RECURSIVE_REASON.format("`git grep {0}`".format(a)))
    if sub == "ls-files":
        flags = "".join(a[1:] for a in rest if _short_cluster(a))
        others = "--others" in rest or "o" in flags
        ignored = "--ignored" in rest or "i" in flags
        piped = any(_command_name(s) == "xargs" for s in all_segments)
        if others and ignored and piped:
            raise Denied(RECURSIVE_REASON.format(
                "`git ls-files --others --ignored` piped to xargs"))
    if sub not in _GIT_NAME_ONLY:
        for a in rest:
            hit = _env_operand(a)
            if hit:
                raise Denied(ENV_REASON.format(hit))


def _command_name(tokens):
    try:
        i = _command_start(tokens)
    except Denied:
        return "env"
    return os.path.basename(tokens[i]) if i < len(tokens) else ""


def _check_docker(cmd, args):
    positionals = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in _DOCKER_VALUE_OPTS:
            skip = True
            continue
        if a.startswith("-"):
            continue
        positionals.append(a)
    if cmd == "docker-compose":
        positionals = ["compose"] + positionals
    if positionals[:1] == ["compose"] and "config" in positionals[1:2]:
        raise Denied(COMPOSE_REASON)


def _check_secret_echo(cmd, args):
    for a in args:
        for m in SECRET_VAR_RE.finditer(a):
            parts = m.group(1).split("_")
            if SECRET_WORDS & set(parts) or parts[-1] in SECRET_LAST_WORDS:
                raise Denied(DUMP_REASON.format("`{0} ${1}`".format(cmd, m.group(1))))


def _check_segment(tokens, all_segments, inners, check):
    for t in tokens:
        if PROC_ENVIRON_RE.search(t):
            raise Denied(DUMP_REASON.format("reading /proc/*/environ"))
    # `< file` feeds the file to whatever command this is; `>` targets are writes.
    for k, t in enumerate(tokens):
        if t == "<" and k + 1 < len(tokens) and is_env_path(tokens[k + 1]):
            raise Denied(ENV_REASON.format(tokens[k + 1]))

    i = _command_start(tokens)
    if i >= len(tokens):
        return
    cmd = os.path.basename(tokens[i])
    args = []
    skip = False
    for t in tokens[i + 1:]:
        if skip:
            skip = False
            continue
        if t in (">", ">>", ">|", "&>", "&>>", "2>", "<", "<<", "<<<"):
            skip = True
            continue
        args.append(t)

    if cmd == "xargs":
        k = 0
        while k < len(args) and args[k].startswith("-"):
            k += 2 if args[k] in _XARGS_VALUE_OPTS else 1
        if k < len(args):
            _check_segment(args[k:], all_segments, inners, check)
        return

    if cmd == "printenv":
        raise Denied(DUMP_REASON.format("`printenv`"))
    if cmd == "set" and not args:
        raise Denied(DUMP_REASON.format("bare `set`"))
    if cmd == "export" and all(a == "-p" for a in args):
        raise Denied(DUMP_REASON.format("bare `export`"))
    if cmd in ("declare", "typeset") and args and all(
        _short_cluster(a) and re.search(r"[xp]", a) for a in args
    ):
        raise Denied(DUMP_REASON.format("`{0} {1}`".format(cmd, " ".join(args))))
    if cmd in ("echo", "printf"):
        _check_secret_echo(cmd, args)

    if cmd in _SHELLS and "-c" in args:
        k = args.index("-c")
        if k + 1 < len(args):
            check(args[k + 1])
        return
    if cmd == "eval":
        check(" ".join(args))
        return
    if cmd in _INTERPRETERS or re.match(r"^python3?(\.\d+)?$", cmd):
        for a in args:
            names = env_names_in_text(a)
            if names:
                raise Denied(ENV_REASON.format(names[0]))

    if cmd in _GREP_FAMILY or cmd == "rgrep":
        _check_grep_family(cmd, args, inners)
    elif cmd == "rg":
        _check_rg(args)
    elif cmd == "ag":
        _check_ag(args)
    elif cmd == "git":
        _check_git(args, all_segments)
        return
    elif cmd in ("docker", "docker-compose"):
        _check_docker(cmd, args)
        return
    elif cmd == "find":
        if not any(a in _FIND_EXEC for a in args):
            return

    if cmd in _NAME_ONLY:
        return
    for a in args:
        hit = _env_operand(a)
        if hit:
            raise Denied(ENV_REASON.format(hit))


def check_bash(command):
    """Raise Denied if the command exposes a secret; return None otherwise."""
    command = re.sub(r"\\\r?\n", " ", command)
    command = _strip_heredocs(command, check_bash)
    command, inners = _extract_substitutions(command, check_bash)
    command = _newlines_to_separators(command)
    segments = _split_segments(command)
    names = [_command_name(s) for s in segments]
    if "xargs" in names and any(
        _env_operand(t) for s in segments for t in s
    ):
        raise Denied(ENV_REASON.format(".env (piped to xargs)"))
    for tokens in segments:
        _check_segment(tokens, segments, inners, check_bash)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def check(tool_name, tool_input):
    if tool_name in ("Read", "Edit"):
        path = tool_input.get("file_path")
        if isinstance(path, str) and is_env_path(path.replace("\\", "/")):
            raise Denied(ENV_REASON.format(path))
    elif tool_name == "Grep":
        path = tool_input.get("path")
        path = path.replace("\\", "/") if isinstance(path, str) else ""
        filters = [v.replace("\\", "/") for v in
                   (tool_input.get("glob"), tool_input.get("include"))
                   if isinstance(v, str) and v]
        for cand in [path] + filters + [path.rstrip("/") + "/" + f for f in filters]:
            if is_env_path(cand):
                raise Denied(ENV_REASON.format(cand))
    elif tool_name == "Bash":
        command = tool_input.get("command")
        if isinstance(command, str) and command.strip():
            check_bash(command)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        _allow()
        return
    if not isinstance(payload, dict):
        _allow()
        return
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        _allow()
        return
    try:
        check(payload.get("tool_name"), tool_input)
    except Denied as exc:
        _deny(str(exc))
        return
    except Exception:  # fail open on any parser surprise, like git_guardrails
        _allow()
        return
    _allow()


if __name__ == "__main__":
    main()
