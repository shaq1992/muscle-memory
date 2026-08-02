#!/usr/bin/env bash
# Produce a curated distribution archive of the portable harness subset.
#
# Ships ONLY the four portable trees rooted at .claude/, plus the harness repo's
# README.md and VERSION at .claude/, plus INSTALL.md at the archive root. The
# harness repo's .git/ and every internally-gitignored per-project file (filled
# preferences, settings.json, phase_closing.json, projects/, caches) are
# excluded -- the zip is the NO-GIT install tier, and per-project scaffolding is
# regenerated in the target by /bootstrap_to_custom_commands (via /on_board).
#
# Usage: bash .claude/harness/scripts/make_portable_zip.sh [output_zip_path]
#   default output: ./harness_portable.zip
#
# The archive extracts to <target>/.claude/{harness,commands,agents,hooks},
# <target>/.claude/{README.md,VERSION}, plus <target>/INSTALL.md. Never prints
# secrets.
set -euo pipefail

# --- Resolve repo root (git first, fall back to script location) -------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    # If we resolved the nested harness repo itself, step up to the project root.
    case "$REPO_ROOT" in
        */.claude) REPO_ROOT="${REPO_ROOT%/.claude}" ;;
    esac
else
    # scripts/ -> harness/ -> .claude/ -> repo root
    REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
fi

CLAUDE_DIR="$REPO_ROOT/.claude"
if [ ! -d "$CLAUDE_DIR" ]; then
    echo "[FATAL] no .claude/ directory at repo root: $REPO_ROOT" >&2
    exit 1
fi

# --- Resolve output path (absolute) ------------------------------------------
OUT_ARG="${1:-$REPO_ROOT/harness_portable.zip}"
case "$OUT_ARG" in
    /*) OUT_ZIP="$OUT_ARG" ;;
    *)  OUT_ZIP="$(pwd)/$OUT_ARG" ;;
esac

# --- Explicit INCLUDE list -- the ONLY content copied -------------------------
# Never a "copy .claude then delete" approach: an include-only copy cannot leak
# per-project files, and it means this script never stages an excluded path.
PORTABLE_TREES="harness commands agents hooks"
PORTABLE_ROOT_FILES="README.md VERSION"

# --- Stage into a temp dir ---------------------------------------------------
STAGING="$(mktemp -d)"
cleanup() { rm -rf "$STAGING"; }
trap cleanup EXIT

STAGED_CLAUDE="$STAGING/.claude"
mkdir -p "$STAGED_CLAUDE"

for tree in $PORTABLE_TREES; do
    src="$CLAUDE_DIR/$tree"
    if [ ! -d "$src" ]; then
        echo "[FATAL] portable tree missing from source: .claude/$tree" >&2
        exit 1
    fi
    cp -R "$src" "$STAGED_CLAUDE/$tree"
done

for f in $PORTABLE_ROOT_FILES; do
    src="$CLAUDE_DIR/$f"
    if [ ! -f "$src" ]; then
        echo "[FATAL] portable root file missing from source: .claude/$f" >&2
        exit 1
    fi
    cp "$src" "$STAGED_CLAUDE/$f"
done

# Prune anything transient or internally-gitignored from the staging tree:
# compiled bytecode, pytest caches, and any nested git metadata. The include
# list already skips .claude/.git; the prune is defense in depth.
find "$STAGED_CLAUDE" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$STAGED_CLAUDE" -name '.pytest_cache' -type d -prune -exec rm -rf {} +
find "$STAGED_CLAUDE" -name '*.pyc' -type f -delete
find "$STAGED_CLAUDE" -name '.git' -prune -exec rm -rf {} +

# INSTALL.md also goes to the staging ROOT so the recipient sees it immediately.
INSTALL_SRC="$CLAUDE_DIR/harness/INSTALL.md"
if [ ! -f "$INSTALL_SRC" ]; then
    echo "[FATAL] INSTALL.md not found: .claude/harness/INSTALL.md" >&2
    exit 1
fi
cp "$INSTALL_SRC" "$STAGING/INSTALL.md"

# --- Safety guard: defense in depth ------------------------------------------
# Fail loudly if any per-project / secret file slipped into the staging tree
# (everything the harness repo's internal .gitignore keeps untracked).
LEAKED="$(find "$STAGING" \( -name '.env' -o -name 'settings.json' \
    -o -name 'settings.local.json' -o -name 'phase_closing.json' \
    -o -name '.git' \
    -o \( -path "$STAGED_CLAUDE/preferences.md" \) \
    -o \( -type d -name 'projects' -path "$STAGED_CLAUDE/projects" \) \) -print)"
if [ -n "$LEAKED" ]; then
    echo "[FATAL] refusing to emit zip -- excluded file(s) found in staging:" >&2
    # Print paths relative to staging so no absolute host paths leak.
    echo "$LEAKED" | sed "s#^$STAGING/##" >&2
    exit 1
fi

# --- Create the zip from inside staging so paths root correctly --------------
rm -f "$OUT_ZIP"
( cd "$STAGING" && zip -r -q "$OUT_ZIP" .claude INSTALL.md )

# --- Summary -----------------------------------------------------------------
echo "[DONE] curated portable harness archive written:"
echo "  output: $OUT_ZIP"
echo "  trees included (under .claude/): $PORTABLE_TREES"
echo "  root files included (under .claude/): $PORTABLE_ROOT_FILES"
echo "  plus INSTALL.md at the archive root"
echo "Note: .git/, preferences.md, settings.json, phase_closing.json, and root"
echo "CLAUDE.md are intentionally excluded -- per-project scaffolding is"
echo "regenerated in the target by /on_board (via /bootstrap_to_custom_commands)."
