#!/usr/bin/env bash
# One-time setup (run by the USER or by bootstrap, from the target repo):
# registers the repo-local git credential helper that reads GIT_PAT from the
# repo's .env at push time. Assumes GIT_PAT is already saved in .env; this
# script NEVER reads .env itself and never prints any credential.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$SCRIPT_DIR/git_credential_env.sh"

if [ ! -f "$HELPER" ]; then
    echo "[FATAL] credential helper not found: $HELPER" >&2
    exit 1
fi
chmod +x "$HELPER"

if ! git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
    echo "[FATAL] not inside a git repository -- run from the repo root" >&2
    exit 1
fi

# Repo-local config (.git/config -- never committed, never global).
git config --local credential.helper "!$HELPER"

echo "[DONE] repo-local credential helper registered: $HELPER"
echo "Pushes now authenticate via GIT_PAT from .env; the token never enters a transcript."
