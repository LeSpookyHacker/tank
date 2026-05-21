#!/usr/bin/env bash
# scripts/stop.sh — graceful shutdown of a backgrounded Tank uvicorn.
# Useful only if you launched start.sh with nohup/disown/screen.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

[[ -f .env ]] && { set -a; source .env; set +a; }
PORT="${TANK_BIND_PORT:-8000}"

PID=$(lsof -ti:"$PORT" -sTCP:LISTEN 2>/dev/null || true)

if [[ -z "$PID" ]]; then
    echo "no process listening on port $PORT"
    exit 0
fi

echo "stopping uvicorn on port $PORT (pid=$PID)"
kill -TERM "$PID"

# Wait up to 5s for graceful shutdown
for _ in 1 2 3 4 5; do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "stopped"
        exit 0
    fi
    sleep 1
done

echo "process did not exit; sending SIGKILL"
kill -KILL "$PID" 2>/dev/null || true
