#!/usr/bin/env bash
# scripts/start.sh — boot Tank from a fresh clone.
#
# Idempotent: re-running never re-installs deps unless requirements.txt changed.
# Friendly errors: missing ANTHROPIC_API_KEY explains how to fix it.
# First-run banner points to /onboarding; subsequent runs show KB counts.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors (TTY only)
if [[ -t 1 ]]; then
    BOLD='\033[1m'; DIM='\033[2m'; RED='\033[31m'; GRN='\033[32m'
    YEL='\033[33m'; CYN='\033[36m'; RST='\033[0m'
else
    BOLD=''; DIM=''; RED=''; GRN=''; YEL=''; CYN=''; RST=''
fi

say()  { printf '%b\n' "$*"; }
fail() { printf '%b\n' "${RED}error:${RST} $*" >&2; exit 1; }

# sqlite3 CLI availability (used for banner stats; not required to run)
_SQLITE3_OK=0
if command -v sqlite3 >/dev/null 2>&1; then
    _SQLITE3_OK=1
else
    say "${DIM}▸ sqlite3 CLI not found — KB stats will be skipped in the banner.${RST}"
    say "${DIM}  Install with: sudo apt install sqlite3   # or brew install sqlite3${RST}"
fi

# 1. Python version check (>=3.11)
if ! command -v python3 >/dev/null 2>&1; then
    fail "python3 not found. Install Python 3.11+ from https://www.python.org/ or via Homebrew."
fi

PY_MAJ=$(python3 -c 'import sys; print(sys.version_info[0])')
PY_MIN=$(python3 -c 'import sys; print(sys.version_info[1])')
if [[ "$PY_MAJ" -lt 3 ]] || { [[ "$PY_MAJ" -eq 3 ]] && [[ "$PY_MIN" -lt 11 ]]; }; then
    fail "Python ${PY_MAJ}.${PY_MIN} found, need 3.11+."
fi

# 2. Virtualenv
if [[ ! -d .venv ]]; then
    say "${CYN}▸${RST} creating virtualenv at .venv"
    python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 3. Deps (hash-cached so reruns are instant)
REQ_HASH_FILE=".venv/.req.hash"
REQ_HASH_NOW=$(sha256sum requirements.txt 2>/dev/null | awk '{print $1}' \
    || shasum -a 256 requirements.txt | awk '{print $1}')
REQ_HASH_CACHED=""
[[ -f "$REQ_HASH_FILE" ]] && REQ_HASH_CACHED=$(cat "$REQ_HASH_FILE")

if [[ "$REQ_HASH_NOW" != "$REQ_HASH_CACHED" ]]; then
    say "${CYN}▸${RST} installing dependencies (requirements.txt changed)"
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements.txt
    echo "$REQ_HASH_NOW" > "$REQ_HASH_FILE"
else
    say "${DIM}▸ dependencies up to date${RST}"
fi

# 4. Optional spaCy model
if [[ "${TANK_ENABLE_PERSON_REDACTION:-}" == "1" ]]; then
    if ! python -c "import spacy; spacy.load('en_core_web_sm')" >/dev/null 2>&1; then
        say "${CYN}▸${RST} downloading spaCy en_core_web_sm for person-name redaction"
        python -m spacy download en_core_web_sm
    fi
fi

# 5. .env check
if [[ ! -f .env ]]; then
    fail "no .env found. Run: cp .env.example .env  and paste your ANTHROPIC_API_KEY."
fi

# Safe .env loading — parse only, do not execute
while IFS='=' read -r _key _val; do
    # Skip comments and empty lines
    case "$_key" in
        ''|\#*) continue ;;
    esac
    # Only export keys that are valid shell identifiers
    if printf '%s' "$_key" | grep -qE '^[A-Za-z_][A-Za-z0-9_]*$'; then
        export "${_key}=${_val}"
    fi
done < .env

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    say "${RED}error:${RST} ANTHROPIC_API_KEY is empty in .env."
    say "       Edit .env and paste your key from https://console.anthropic.com/settings/keys"
    exit 1
fi

# 6. Banner
DB_PATH="${TANK_DB_PATH:-$HOME/.tank/db.sqlite}"
mkdir -p "$(dirname "$DB_PATH")"

# Detect first-run by checking app_state. If DB doesn't exist or table is empty,
# we're in first-run mode. FastAPI's startup event creates the schema.
FIRST_RUN=1
if [[ -f "$DB_PATH" ]]; then
    if [[ "$_SQLITE3_OK" -eq 1 ]]; then
        COUNT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM app_state WHERE id = 1;" 2>/dev/null || echo "0")
        [[ "$COUNT" == "1" ]] && FIRST_RUN=0
    fi
fi

BIND_HOST="${TANK_BIND_HOST:-127.0.0.1}"
BIND_PORT="${TANK_BIND_PORT:-8000}"

say ""
say "${BOLD}${GRN}Tank${RST} — Security Engineer Onboarding Partner"
say ""
if [[ "$FIRST_RUN" -eq 1 ]]; then
    say "${YEL}▸ first run detected.${RST}"
    say "  Once the server is up, open ${BOLD}http://${BIND_HOST}:${BIND_PORT}${RST}"
    say "  Tank will walk you through onboarding (~7 min)."
    say "  ${DIM}Nothing has been sent anywhere yet.${RST}"
else
    if [[ "$_SQLITE3_OK" -eq 1 ]]; then
        DOCS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM documents;" 2>/dev/null || echo "0")
        ENT=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM entities;" 2>/dev/null || echo "0")
        REDACTIONS=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM redaction_map;" 2>/dev/null || echo "0")
        LAST=$(sqlite3 "$DB_PATH" \
            "SELECT datetime(updated_at, 'unixepoch', 'localtime') FROM conversations ORDER BY updated_at DESC LIMIT 1;" \
            2>/dev/null || echo "")
        say "${DIM}▸ welcome back.${RST}"
        say "  documents:  ${BOLD}${DOCS}${RST}     entities: ${BOLD}${ENT}${RST}     redactions: ${BOLD}${REDACTIONS}${RST}"
        [[ -n "$LAST" ]] && say "  last chat:  ${DIM}${LAST}${RST}"
    else
        say "${DIM}▸ welcome back.${RST}"
        say "  ${DIM}(install sqlite3 CLI to see KB stats)${RST}"
    fi
    say "  open ${BOLD}http://${BIND_HOST}:${BIND_PORT}${RST}"
fi
say ""

# 7. Run uvicorn
UVI_FLAGS=("--host" "$BIND_HOST" "--port" "$BIND_PORT")
if [[ "${TANK_ENV:-dev}" != "prod" ]]; then
    UVI_FLAGS+=("--reload")
fi

exec python -m uvicorn app.main:app "${UVI_FLAGS[@]}"
