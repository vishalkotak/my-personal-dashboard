#!/usr/bin/env bash
# Builds "Health Dashboard.app" and installs it in ~/Applications.
#
#   ./dashboard/desktop/build.sh
#
# Re-run it after pulling changes to the dashboard. Needs Xcode, XcodeGen (brew install xcodegen),
# Python 3.11+ and Node 20.19+. The app reads your settings from dashboard/.env, like start.sh.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASH="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$DASH/.." && pwd)"
DEST="${DEST:-$HOME/Applications}"

command -v xcodegen >/dev/null || { echo "XcodeGen is required: brew install xcodegen"; exit 1; }

# ---------------------------------------------------------------- backend environment
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] || { echo "Python 3.11+ is required (brew install python@3.12)."; exit 1; }
if [ ! -x "$DASH/backend/.venv/bin/python" ]; then
  echo "• Setting up the Python environment…"
  "$PY" -m venv "$DASH/backend/.venv"
fi
if [ ! -f "$DASH/backend/.venv/.installed" ] || [ "$DASH/backend/requirements.txt" -nt "$DASH/backend/.venv/.installed" ]; then
  "$DASH/backend/.venv/bin/pip" install --quiet --disable-pip-version-check -r "$DASH/backend/requirements.txt"
  touch "$DASH/backend/.venv/.installed"
fi

# ---------------------------------------------------------------- web page
command -v npm >/dev/null || { echo "Node.js 20.19+ is required (brew install node)."; exit 1; }
echo "• Building the web page…"
(cd "$DASH/frontend" && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent)

# ---------------------------------------------------------------- icon (from the iPhone app's icon)
ICONSET="$HERE/Assets.xcassets/AppIcon.appiconset"
mkdir -p "$ICONSET"
printf '{ "info" : { "author" : "xcode", "version" : 1 } }\n' > "$HERE/Assets.xcassets/Contents.json"
SRC_ICON="$REPO/apple-health-sync/HealthSync/Assets.xcassets/AppIcon.appiconset/AppIcon.png"
if [ ! -f "$ICONSET/icon_512x512@2x.png" ] || [ "$SRC_ICON" -nt "$ICONSET/icon_512x512@2x.png" ]; then
  echo "• Rendering the app icon…"
  swift "$HERE/scripts/make-icon.swift" "$SRC_ICON" "$ICONSET/icon_512x512@2x.png"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$ICONSET/icon_512x512@2x.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    d=$((s * 2))
    [ "$s" = 512 ] || sips -z $d $d "$ICONSET/icon_512x512@2x.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
  done
fi
{
  echo '{ "images" : ['
  first=1
  for s in 16 32 128 256 512; do
    for scale in 1 2; do
      suffix=""; if [ $scale = 2 ]; then suffix="@2x"; fi
      name="icon_${s}x${s}${suffix}.png"
      [ $first = 1 ] || echo ','
      first=0
      printf '  { "idiom" : "mac", "size" : "%sx%s", "scale" : "%sx", "filename" : "%s" }' $s $s $scale "$name"
    done
  done
  echo ''
  echo '], "info" : { "author" : "xcode", "version" : 1 } }'
} > "$ICONSET/Contents.json"

# ---------------------------------------------------------------- app
echo "• Building the app…"
cd "$HERE"
xcodegen generate --quiet
xcodebuild -project HealthDashboard.xcodeproj -scheme HealthDashboard -configuration Release \
  -destination "platform=macOS,arch=$(uname -m)" -derivedDataPath build -quiet build
mkdir -p "$DEST"
rm -rf "$DEST/Health Dashboard.app"
cp -R "build/Build/Products/Release/Health Dashboard.app" "$DEST/"
echo
echo "Installed: $DEST/Health Dashboard.app"
echo "Open it from Launchpad or Spotlight (\"Health Dashboard\"), or: open \"$DEST/Health Dashboard.app\""
