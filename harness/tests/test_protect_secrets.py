"""Behavioral tests for hooks/protect_secrets.py (the .env secret-read guard).

Contract cases 1-11 are the brief's behavioral tests for plan
harness-improv-v7 session 02 (row E018). Every payload is a FIXTURE STRING:
the hook decides on the command / path text alone and never opens a file, so
no test here reads a real .env.

Several cases are ported from karanb192/claude-code-hooks
plugins/protect-secrets/tests/protect-secrets.test.js
(MIT License, Copyright (c) 2026 Karan Bansal); the recursive-search cases
(class 7) are new -- by its regexes the upstream guard would not catch the
recursive-grep leak (row E010).

Stdlib-only. Run with: python3 -m unittest discover .claude/harness/tests
"""

import json
import re
import subprocess
import sys
import unittest

from helpers import HARNESS_ROOT, decision_and_reason

SECRETS_HOOK = HARNESS_ROOT / "hooks" / "protect_secrets.py"
BOOTSTRAP = HARNESS_ROOT / "commands" / "bootstrap_to_custom_commands.md"


def run_secrets_hook(tool_name, tool_input, raw=None):
    payload = raw if raw is not None else json.dumps(
        {"tool_name": tool_name, "tool_input": tool_input, "cwd": "/tmp"}
    )
    return subprocess.run(
        [sys.executable, str(SECRETS_HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
    )


class SecretsEnv(unittest.TestCase):
    def verdict(self, tool_name, tool_input):
        return decision_and_reason(run_secrets_hook(tool_name, tool_input))

    def assert_denied(self, tool_name, tool_input):
        verdict, _ = self.verdict(tool_name, tool_input)
        self.assertEqual(
            "deny", verdict,
            "expected DENY for {0} {1!r}; got allow".format(tool_name, tool_input),
        )

    def assert_allowed(self, tool_name, tool_input):
        verdict, reason = self.verdict(tool_name, tool_input)
        self.assertEqual(
            "allow", verdict,
            "expected ALLOW for {0} {1!r}; denied with: {2}".format(
                tool_name, tool_input, reason),
        )

    def assert_bash_denied(self, commands):
        for command in commands:
            with self.subTest(command=command):
                self.assert_denied("Bash", {"command": command})

    def assert_bash_allowed(self, commands):
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed("Bash", {"command": command})


# ---------------------------------------------------------------------------
# 1. Read / Edit of a .env-family file is denied
# ---------------------------------------------------------------------------
class TestReadEditEnvDenied(SecretsEnv):
    PATHS = [".env", "/app/.env", ".env.local", ".env.production",
             "/path/to/.env.staging", ".envrc", "C:\\app\\.env",
             "C:\\src\\app\\.env.production"]

    def test_read_denied(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assert_denied("Read", {"file_path": path})

    def test_edit_denied(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assert_denied(
                    "Edit",
                    {"file_path": path, "old_string": "x", "new_string": "y"},
                )

    def test_deny_reason_points_at_the_example_file(self):
        _, reason = self.verdict("Read", {"file_path": "/app/.env"})
        self.assertIn(".env.example", reason)


# ---------------------------------------------------------------------------
# 2. Template names stay readable
# ---------------------------------------------------------------------------
class TestTemplatesAllowed(SecretsEnv):
    def test_templates_allowed(self):
        for path in [".env.example", ".env.sample", ".env.template",
                     ".env.schema", ".env.defaults", "/app/.env.example",
                     ".env.local.example", "C:\\src\\app\\.env.example",
                     "env.example", "example.env", "src/environment.py"]:
            with self.subTest(path=path):
                self.assert_allowed("Read", {"file_path": path})


# ---------------------------------------------------------------------------
# 3. Grep tool aimed at a .env file is denied
# ---------------------------------------------------------------------------
class TestGrepToolEnv(SecretsEnv):
    def test_grep_tool_denied(self):
        for tool_input in [
            {"pattern": "STRIPE", "path": "/app/.env"},
            {"pattern": "KEY", "glob": "**/.env"},
            {"pattern": "KEY", "include": ".env"},
            {"pattern": "KEY", "path": "/app", "glob": ".env.*"},
        ]:
            with self.subTest(tool_input=tool_input):
                self.assert_denied("Grep", tool_input)

    def test_grep_tool_allowed(self):
        for tool_input in [
            {"pattern": "STRIPE", "path": ".env.example"},
            {"pattern": "def ", "path": "src", "glob": "*.py"},
            {"pattern": "TODO"},
        ]:
            with self.subTest(tool_input=tool_input):
                self.assert_allowed("Grep", tool_input)


# ---------------------------------------------------------------------------
# 4. Bash readers of a .env file are denied
# ---------------------------------------------------------------------------
class TestBashReadersDenied(SecretsEnv):
    def test_readers_denied(self):
        self.assert_bash_denied([
            "cat .env",
            "cat /app/.env",
            "head -n 10 .env",
            "tail .env.production",
            "less .env.local",
            "grep KEY .env",
            'grep -E "STRIPE_API_VERSION|STRIPE_SECRET_KEY" /app/.env',
            "rg KEY '.env.local'",
            "awk -F= '{print $2}' .env",
            "awk -F'=' '{print $2}' .env",
            'grep KEY ./".env"',
            'grep "/tmp/.env"',
            "fgrep KEY services/billing/.env",
            "sed -n 1p .env",
            "python3 -c \"print(open('.env').read())\"",
            "while read l; do echo $l; done < .env",
            "cat foo && grep X .env",
            'bash -c "cat .env"',
            'export X="$(cat .env)"',
            "X=`cat .env` true",
            "base64 .env",
            'cat "$D/.env"',
        ])


# ---------------------------------------------------------------------------
# 5. Loading, copying or indirectly piping a .env file is denied
# ---------------------------------------------------------------------------
class TestIndirectionDenied(SecretsEnv):
    def test_indirection_denied(self):
        self.assert_bash_denied([
            "source .env",
            ". .env",
            "source /app/.env.local",
            "set -a; . ./.env; set +a",
            "cp .env .env.backup",
            "mv .env .env.old",
            "scp .env user@remote:/tmp/",
            "echo .env | xargs cat",
            'find . -name ".env" -exec cat {} \\;',
        ])


# ---------------------------------------------------------------------------
# 6. Environment dumps are denied
# ---------------------------------------------------------------------------
class TestEnvDumpsDenied(SecretsEnv):
    def test_dumps_denied(self):
        self.assert_bash_denied([
            "printenv",
            "printenv AZURE_OPENAI_KEY",
            "env",
            "cd /app && env",
            "env | sort",
            "set",
            "export",
            "export -p",
            "declare -x",
            "declare -p",
            "cat /proc/1/environ",
            "cat /proc/self/environ",
            "docker compose config",
            "docker compose -f x.yml config",
            "docker-compose config",
            "echo $API_KEY",
            'echo "${OPENAI_API_KEY}"',
            'printf %s "$DB_PASSWORD"',
        ])


# ---------------------------------------------------------------------------
# 7. Unscoped recursive search is denied (the s17 leak, row E010)
# ---------------------------------------------------------------------------
class TestRecursiveSearchDenied(SecretsEnv):
    def test_recursive_search_denied(self):
        self.assert_bash_denied([
            "command grep -rn KEY .",
            "grep -R foo /home/x/proj",
            "grep --recursive x .",
            "grep -rl secret src/ docs/",
            "egrep -r x .",
            "ugrep -r x",
            "grep -d recurse x .",
            "grep --directories=recurse x .",
            "rg --hidden x",
            "rg -uu x",
            "rg -u x .",
            "rg --no-ignore x",
            "rg --no-ignore-vcs x",
            "rg --unrestricted x",
            "rg -g '.env*' x",
            "rg --glob=.env x",
            "rg -g '.*' x",
            "ag -u x",
            "ag --hidden x",
            "ag -U x",
            "git grep --untracked x",
            "git grep --no-index x",
            "git grep --no-exclude-standard x",
            "cd /app && grep -rn API_KEY .",
            "git ls-files -o -i --exclude-standard | xargs grep KEY",
        ])

    def test_reason_names_the_scoped_alternative(self):
        _, reason = self.verdict("Bash", {"command": "grep -rn KEY ."})
        self.assertIn("git ls-files", reason)


# ---------------------------------------------------------------------------
# 8. Normal work stays allowed (row E018 reopen trigger: false blocks)
# ---------------------------------------------------------------------------
class TestNormalWorkAllowed(SecretsEnv):
    def test_allowed(self):
        self.assert_bash_allowed([
            "git ls-files | xargs grep -n foo",
            "git ls-files -z | xargs -0 grep foo",
            "git ls-files -z -- '*.md' | xargs -0 grep -n x",
            "grep -rn foo $(git ls-files)",
            "git grep foo",
            "git grep -n foo -- '*.py'",
            "rg foo",
            "rg foo src/",
            "rg -n --type py foo",
            "rg --files",
            "ag foo",
            "grep -n foo README.md",
            "grep -c x a.txt b.txt",
            "ps aux | grep python",
            "cat .env.example",
            "cat .env.example && ls",
            "grep STRIPE .env.example",
            "echo $NODE_ENV",
            "echo $CLAUDE_CODE_SESSION_ID",
            "echo $TOKENS_USED",
            "envsubst < template.yml",
            "env FOO=1 python3 app.py",
            "echo .env >> .gitignore",
            "git check-ignore -v .env",
            "git add .gitignore",
            "ls -la .env",
            "test -f .env && echo yes",
            "[ -f .env ] && echo yes",
            'git commit -m "add .env to gitignore"',
            "docker compose up -d",
            "docker compose --env-file .env up -d",
            "python3 app.py",
            "find . -name '*.py'",
            "find . -name .env",
            "export FOO=bar",
            "set -euo pipefail",
            "cat src/environment.py",
            "grep foo && echo .env",
        ])


# ---------------------------------------------------------------------------
# 9. A template name elsewhere in the command does not unlock a real .env
#    (the upstream whole-command allowlist bypass, deliberately NOT ported)
# ---------------------------------------------------------------------------
class TestTemplateDoesNotUnlock(SecretsEnv):
    def test_template_does_not_unlock(self):
        self.assert_bash_denied([
            "cat .env.example && cat .env",
            "diff .env.example .env",
        ])


# ---------------------------------------------------------------------------
# 10. Malformed payloads and unhandled tools fail open
# ---------------------------------------------------------------------------
class TestFailOpen(SecretsEnv):
    def test_malformed_payload_allows(self):
        for raw in ["", "not json", "[]", '{"tool_name": "Bash"}',
                    '{"tool_name": "Bash", "tool_input": {"command": 5}}']:
            with self.subTest(raw=raw):
                verdict, _ = decision_and_reason(run_secrets_hook(None, None, raw=raw))
                self.assertEqual("allow", verdict)

    def test_unhandled_tools_allow(self):
        self.assert_allowed("Glob", {"pattern": "**/.env"})
        self.assert_allowed("Write", {"file_path": ".env", "content": "A=1\n"})


# ---------------------------------------------------------------------------
# 11. The bootstrap Step 6 settings template registers the hook
# ---------------------------------------------------------------------------
class TestBootstrapRegistersHook(unittest.TestCase):
    def test_bootstrap_template_registers_protect_secrets(self):
        text = BOOTSTRAP.read_text(encoding="utf-8")
        step6 = text.split("### Step 6", 1)[1]
        block = re.search(r"```json\n(.*?)```", step6, re.S).group(1)
        settings = json.loads(block)
        entries = [
            e for e in settings["hooks"]["PreToolUse"]
            if "protect_secrets.py" in json.dumps(e)
        ]
        self.assertEqual(1, len(entries), "exactly one protect_secrets entry")
        tools = set(entries[0]["matcher"].split("|"))
        self.assertTrue({"Read", "Edit", "Grep", "Bash"} <= tools, tools)
        self.assertIn("python3", json.dumps(entries[0]))


if __name__ == "__main__":
    unittest.main()
