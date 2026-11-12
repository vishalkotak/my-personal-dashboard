#!/bin/bash
# Installs (or reinstalls) the LaunchAgent that runs resign-and-install.sh 3x a day.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="local.healthsync.resign"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

sed -e "s#__SCRIPT__#$DIR/resign-and-install.sh#" \
    -e "s#__LOG__#$HOME/Library/Logs/HealthSync-resign.log#g" \
    "$DIR/resign-agent.plist.template" > "$DEST"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "Loaded $LABEL → $DEST"
