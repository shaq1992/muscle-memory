#!/usr/bin/env bash
# Git credential helper: emits GIT_PAT from the current repo's .env on 'get'.
# Invoked BY GIT at push time (registered via setup_credential_helper.sh).
# The token flows only over git's private helper pipe -- it never appears in
# a command line, tool output, or transcript. No Claude session runs this
# directly or reads .env.
set -euo pipefail

action="${1:-}"
if [ "$action" != "get" ]; then
    # store/erase are no-ops for an env-file-backed helper
    exit 0
fi

# Drain the credential request from stdin (protocol requirement).
while IFS= read -r line; do
    [ -z "$line" ] && break
done || true

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
env_file="$root/.env"
if [ ! -f "$env_file" ]; then
    exit 0
fi

pat="$(grep -E '^GIT_PAT=' "$env_file" | tail -n 1 | cut -d '=' -f 2-)"
# strip optional surrounding quotes
pat="${pat%\"}"; pat="${pat#\"}"
pat="${pat%\'}"; pat="${pat#\'}"
if [ -z "$pat" ]; then
    exit 0
fi

username="$(grep -E '^GIT_USERNAME=' "$env_file" | tail -n 1 | cut -d '=' -f 2- || true)"
if [ -z "$username" ]; then
    username="x-access-token"
fi

printf 'username=%s\n' "$username"
printf 'password=%s\n' "$pat"
