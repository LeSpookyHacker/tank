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

# lsof may return multiple PIDs (one per line); normalise into an array
PIDS=($PID)
echo "stopping uvicorn on port $PORT (pid=${PIDS[*]})"
kill -TERM "${PIDS[@]}"

# Wait up to 5s for graceful shutdown
for _ in 1 2 3 4 5; do
    alive=0
    for pid in "${PIDS[@]}"; do
        kill -0 "$pid" 2>/dev/null && alive=1 && break
    done
    if [[ $alive -eq 0 ]]; then
        echo "stopped"
        exit 0
    fi
    sleep 1
done

echo "process did not exit; sending SIGKILL"
kill -KILL "${PIDS[@]}" 2>/dev/null || true
