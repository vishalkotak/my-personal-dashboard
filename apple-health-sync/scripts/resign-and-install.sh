#!/bin/bash
# Keeps HealthSync alive on a FREE Apple developer account.
#
# Free ("Personal Team") signing expires after 7 days. This script runs on a schedule
# (see local.healthsync.resign.plist). When the profile installed on the phone
# is within RENEW_BEFORE_HOURS of expiring, it asks Apple for a fresh 7-day profile,
# rebuilds, and reinstalls over USB or Wi-Fi. App data on the phone is preserved.
#
# Manual run:            ./scripts/resign-and-install.sh
# Force renewal now:     FORCE_RENEW=1 ./scripts/resign-and-install.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# DEVICE_ID, DEST_UDID, APP_ID — machine-specific, kept out of git (see local.env.example).
# shellcheck source=/dev/null
source "$PROJECT_DIR/scripts/local.env"
APP="$PROJECT_DIR/build/Build/Products/Debug-iphoneos/HealthSync.app"
PROFILES="$HOME/Library/Developer/Xcode/UserData/Provisioning Profiles"
STATE="$HOME/Library/Application Support/HealthSync-resign"
RENEW_BEFORE_HOURS=60
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$STATE/old-profiles"
log()    { echo "$(date '+%F %T') $*"; }
notify() { osascript -e "display notification \"$1\" with title \"HealthSync re-sign\"" >/dev/null 2>&1 || true; }

# Expiry (epoch seconds) of a .mobileprovision file.
expiry_of() {
  local raw
  raw=$(security cms -D -i "$1" 2>/dev/null | plutil -extract ExpirationDate raw -o - -)
  TZ=UTC date -j -f '%Y-%m-%dT%H:%M:%SZ' "$raw" +%s
}

now=$(date +%s)
installed_expiry=$(cat "$STATE/installed-expiry" 2>/dev/null || echo 0)
hours_left=$(( (installed_expiry - now) / 3600 ))
log "Profile on phone expires in ${hours_left}h"

if (( hours_left >= RENEW_BEFORE_HOURS )) && [[ "${FORCE_RENEW:-0}" != 1 ]]; then
  log "Nothing to do."
  exit 0
fi

# Move this app's cached profile(s) aside so Xcode requests a brand-new 7-day one.
shopt -s nullglob
for p in "$PROFILES"/*.mobileprovision; do
  if security cms -D -i "$p" 2>/dev/null | grep -q "$APP_ID"; then
    mv "$p" "$STATE/old-profiles/"
    log "Retired cached profile $(basename "$p")"
  fi
done

log "Building…"
if ! xcodebuild -project "$PROJECT_DIR/HealthSync.xcodeproj" -scheme HealthSync \
      -destination "id=$DEST_UDID" -configuration Debug -derivedDataPath "$PROJECT_DIR/build" \
      -allowProvisioningUpdates -onlyUsePackageVersionsFromResolvedFile -quiet build; then
  # ^ unattended builds must never silently pick up new dependency versions.
  log "Build failed."; notify "Build failed — see ~/Library/Logs/HealthSync-resign.log"; exit 1
fi

new_expiry=$(expiry_of "$APP/embedded.mobileprovision")
log "New profile expires $(date -r "$new_expiry" '+%F %T')"

log "Installing…"
if ! xcrun devicectl device install app --device "$DEVICE_ID" "$APP" >/dev/null; then
  log "Install failed (is the iPhone on the same Wi-Fi / unlocked?). Will retry next run."
  notify "Couldn't reach your iPhone — will retry. App expires in ${hours_left}h."
  exit 1
fi

echo "$new_expiry" > "$STATE/installed-expiry"
log "Installed. Next renewal in ~$(( (new_expiry - now) / 3600 - RENEW_BEFORE_HOURS ))h."
