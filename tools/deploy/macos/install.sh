#!/bin/sh
# Install or remove the gateway LaunchAgent for the current user.
#
#   tools/deploy/macos/install.sh install [state-dir] [rx-stlink-serial]
#   tools/deploy/macos/install.sh uninstall
#   tools/deploy/macos/install.sh status
#
# The agent runs `python -m ws0 serve --serial-number <RX>`, restarts if it exits, and logs to
# <state-dir>/serve.out. The 24-hour delivery test (H01) also needs the Mac to stay awake
# (System Settings > Battery/Energy).
set -eu
label=com.clintecker.weatherstation.gateway
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
plist="$HOME/Library/LaunchAgents/$label.plist"
domain="gui/$(id -u)"

case "${1:-}" in
  install)
    state=$(CDPATH= cd -- "${2:-$repo/run-hw}" && pwd)
    rx=${3:-0016001E4142500E20353451}
    [ -f "$state/gateway.json" ] || { echo "no gateway.json in $state" >&2; exit 1; }
    mkdir -p "$HOME/Library/LaunchAgents"
    sed -e "s|@REPO@|$repo|g" -e "s|@STATE@|$state|g" -e "s|@RX_SERIAL@|$rx|g" \
      "$repo/tools/deploy/macos/$label.plist.in" > "$plist"
    plutil -lint "$plist"
    launchctl bootout "$domain/$label" 2>/dev/null || true
    launchctl bootstrap "$domain" "$plist"
    echo "installed $plist"
    ;;
  uninstall)
    launchctl bootout "$domain/$label" 2>/dev/null || true
    rm -f "$plist"
    echo "removed $label"
    ;;
  status)
    launchctl print "$domain/$label" | grep -E "state =|pid =|last exit code|runs =" || echo "not loaded"
    ;;
  *)
    echo "usage: $0 install [state-dir] [rx-stlink-serial] | uninstall | status" >&2
    exit 2
    ;;
esac
