#!/usr/bin/env bash
# Install Tank as a systemd --user service.
#
# Idempotent — re-running just refreshes the unit file and restarts.
# Linux only. macOS users should write a launchd plist instead.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="$PROJECT_ROOT/scripts/tank.service"
UNIT_DST="$HOME/.config/systemd/user/tank.service"

if [[ ! -d /run/systemd/system ]]; then
    echo "error: systemd is not the active init system on this host." >&2
    echo "       (no /run/systemd/system). Use launchd / nohup instead." >&2
    exit 2
fi

if [[ ! -f "$UNIT_SRC" ]]; then
    echo "error: $UNIT_SRC not found." >&2
    exit 1
fi

mkdir -p "$(dirname "$UNIT_DST")"

# Substitute the project root into the unit so it works without
# editing-by-hand for the common case where the repo is at $HOME/projects/tank.
sed "s|%h/projects/tank|$PROJECT_ROOT|g" "$UNIT_SRC" > "$UNIT_DST"

systemctl --user daemon-reload
systemctl --user enable tank
systemctl --user restart tank

# Persist user services across logout / SSH disconnects.
if command -v loginctl >/dev/null 2>&1; then
    if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
        echo "▸ enabling linger so Tank survives SSH disconnect…"
        sudo loginctl enable-linger "$USER" || \
            echo "  (loginctl enable-linger failed — Tank will still run while you're logged in)"
    fi
fi

echo
echo "✓ tank.service installed and started"
echo
echo "  status:  systemctl --user status tank"
echo "  logs:    journalctl --user -u tank -f"
echo "  stop:    systemctl --user stop tank"
echo "  disable: systemctl --user disable tank"
