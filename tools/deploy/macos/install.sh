#!/bin/sh
# Install or remove the gateway as a LaunchAgent (default) or a LaunchDaemon (--daemon).
#
#   tools/deploy/macos/install.sh [--daemon] install [state-dir] [rx-stlink-serial]
#   tools/deploy/macos/install.sh [--daemon] uninstall
#   tools/deploy/macos/install.sh [--daemon] status
#
# Both run `python -m ws0 serve --serial-number <RX>`, restart it if it exits, and log to
# <state-dir>/serve.out.
#   LaunchAgent (~/Library/LaunchAgents, domain gui/<uid>): starts when you log in, stops when you
#     log out. No sudo.
#   LaunchDaemon (/Library/LaunchDaemons, domain system): starts at boot with nobody logged in, after
#     a power cut too. It runs as you (UserName), never as root, so the state directory and its
#     mqtt-password keep their owner. Installing it needs sudo (asked for by this script).
# Only one may be loaded: two gateways can't share the RX board's serial port. Installing the
# daemon removes the agent; installing the agent refuses while the daemon is installed.
# The 24-hour delivery test (H01) also needs the Mac to stay awake (System Settings > Battery/Energy).
set -eu
label=com.clintecker.weatherstation.gateway
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
agent_plist="$HOME/Library/LaunchAgents/$label.plist"
daemon_plist="/Library/LaunchDaemons/$label.plist"
agent_domain="gui/$(id -u)"

daemon=0
if [ "${1:-}" = --daemon ]; then daemon=1; shift; fi
if [ "$daemon" = 1 ]; then
  plist=$daemon_plist domain=system sudo=sudo
else
  plist=$agent_plist domain=$agent_domain sudo=
fi

render() {   # render <state> <rx> <output>: the plist from the template
  user_keys=
  if [ "$daemon" = 1 ]; then
    user_keys="<key>UserName</key><string>$(id -un)</string><key>GroupName</key><string>$(id -gn)</string>"
    user_keys="$user_keys<key>EnvironmentVariables</key><dict><key>HOME</key><string>$HOME</string></dict>"
  fi
  sed -e "s|@REPO@|$repo|g" -e "s|@STATE@|$1|g" -e "s|@RX_SERIAL@|$2|g" -e "s|<!-- @DAEMON_KEYS@ -->|$user_keys|" \
    "$repo/tools/deploy/macos/$label.plist.in" > "$3"
  plutil -lint "$3"
}

case "${1:-}" in
  install)
    state=$(CDPATH= cd -- "${2:-$repo/run-hw}" && pwd)
    rx=${3:-0016001E4142500E20353451}
    [ -f "$state/gateway.json" ] || { echo "no gateway.json in $state" >&2; exit 1; }
    if [ "$daemon" = 1 ]; then
      tmp=$(mktemp)
      render "$state" "$rx" "$tmp"
      launchctl bootout "$agent_domain/$label" 2>/dev/null || true   # never both
      rm -f "$agent_plist"
      sudo install -m 644 -o root -g wheel "$tmp" "$daemon_plist"
      rm -f "$tmp"
    else
      if [ -f "$daemon_plist" ]; then
        echo "the LaunchDaemon is installed; remove it first: $0 --daemon uninstall" >&2
        exit 1
      fi
      mkdir -p "$HOME/Library/LaunchAgents"
      render "$state" "$rx" "$plist"
    fi
    $sudo launchctl bootout "$domain/$label" 2>/dev/null || true
    $sudo launchctl bootstrap "$domain" "$plist"
    echo "installed $plist"
    ;;
  uninstall)
    $sudo launchctl bootout "$domain/$label" 2>/dev/null || true
    $sudo rm -f "$plist"
    echo "removed $label ($domain)"
    ;;
  status)
    $sudo launchctl print "$domain/$label" | grep -E "state =|pid =|last exit code|runs =" || echo "not loaded"
    ;;
  *)
    echo "usage: $0 [--daemon] install [state-dir] [rx-stlink-serial] | uninstall | status" >&2
    exit 2
    ;;
esac
