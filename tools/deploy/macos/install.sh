#!/bin/sh
# Install or remove the gateway as a LaunchAgent (default) or a LaunchDaemon (--daemon).
#
#   tools/deploy/macos/install.sh [--daemon] install [state-dir] [rx-stlink-serial]
#   tools/deploy/macos/install.sh [--daemon] uninstall
#   tools/deploy/macos/install.sh status
#   tools/deploy/macos/install.sh [--daemon] render [state-dir] [rx-stlink-serial]
#
# status shows both the agent and the daemon. render prints the plist install would write, and
# installs nothing.
#
# Both run `python -m ws0 serve --serial-number <RX>`, restart it if it exits, and log to
# <state-dir>/serve.out.
#   LaunchAgent (~/Library/LaunchAgents, domain gui/<uid>): starts when you log in, stops when you
#     log out. No sudo.
#   LaunchDaemon (/Library/LaunchDaemons, domain system): starts at boot with nobody logged in, after
#     a power cut too. It runs as you (UserName), never as root, so the state directory and its
#     mqtt-password keep their owner. Installing it needs sudo (asked for by this script), so run the
#     script as yourself, not with sudo: it refuses to install the daemon as root.
# Only one may be loaded: two gateways can't share the RX board's serial port. Installing the
# daemon removes the agent; installing the agent refuses while the daemon is installed.
# The 24-hour delivery test (H01) also needs the Mac to stay awake (System Settings > Battery/Energy).
# FileVault: with it on, a Mac that restarts after a power cut waits at the unlock screen, before any
# LaunchDaemon starts. The gateway stays down until someone unlocks the disk (logs in) at the Mac.
set -eu
label=com.clintecker.weatherstation.gateway
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
agent_plist="$HOME/Library/LaunchAgents/$label.plist"
daemon_plist="/Library/LaunchDaemons/$label.plist"
agent_domain="gui/$(id -u)"
default_rx=0016001E4142500E20353451

daemon=0
if [ "${1:-}" = --daemon ]; then daemon=1; shift; fi
if [ "$daemon" = 1 ] && [ "$(id -u)" = 0 ]; then
  echo "don't run this as root: the daemon runs as the user who installs it (id -un, \$HOME)." >&2
  echo "run it as yourself; it asks for sudo where it needs it." >&2
  exit 1
fi
if [ "$daemon" = 1 ]; then
  plist=$daemon_plist domain=system sudo=sudo
else
  plist=$agent_plist domain=$agent_domain sudo=
fi

python=$repo/.venv/bin/python
[ -x "$python" ] || python=python3

render() {   # render <state> <rx> <output, - for stdout>: the plist from the template
  # Python fills the template, so a path with &, |, \ or < goes in as XML text, not as sed syntax.
  "$python" - "$repo/tools/deploy/macos/$label.plist.in" "$3" "$daemon" "$repo" "$1" "$2" \
      "$(id -un)" "$(id -gn)" "$HOME" <<'EOF'
import re, sys
from xml.sax.saxutils import escape
template, out, daemon, repo, state, rx, user, group, home = sys.argv[1:]
with open(template, encoding='utf-8') as f:
    text = f.read()
keys = ''
if daemon == '1':
    keys = (f'<key>UserName</key><string>{escape(user)}</string><key>GroupName</key><string>{escape(group)}</string>'
            f'<key>EnvironmentVariables</key><dict><key>HOME</key><string>{escape(home)}</string></dict>')
text = text.replace('<!-- @DAEMON_KEYS@ -->', keys)
values = {'REPO': repo, 'STATE': state, 'RX_SERIAL': rx}
text = re.sub(r'@(REPO|STATE|RX_SERIAL)@', lambda m: escape(values[m.group(1)]), text)
if out == '-':
    sys.stdout.write(text)
else:
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text)
EOF
  if [ "$3" != - ] && command -v plutil >/dev/null 2>&1; then plutil -lint "$3"; fi
}

show() {   # show <name> <domain> <plist>: installed or not, and launchd's view of it
  if [ -f "$3" ]; then echo "$1: $3"; else echo "$1: not installed"; fi
  launchctl print "$2/$label" 2>/dev/null | grep -E "state =|pid =|last exit code|runs =" || echo "  not loaded ($2)"
}

case "${1:-}" in
  install)
    state=$(CDPATH= cd -- "${2:-$repo/run-hw}" && pwd)
    rx=${3:-$default_rx}
    [ -f "$state/gateway.json" ] || { echo "no gateway.json in $state" >&2; exit 1; }
    if [ "$daemon" = 1 ]; then
      tmp=$(mktemp)
      trap 'rm -f "$tmp"' EXIT
      trap 'rm -f "$tmp"; exit 1' HUP INT TERM
      render "$state" "$rx" "$tmp"
      launchctl bootout "$agent_domain/$label" 2>/dev/null || true   # never both
      rm -f "$agent_plist"
      sudo install -m 644 -o root -g wheel "$tmp" "$daemon_plist"
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
    show agent "$agent_domain" "$agent_plist"
    show daemon system "$daemon_plist"
    ;;
  render)
    state=$(CDPATH= cd -- "${2:-$repo/run-hw}" && pwd)
    render "$state" "${3:-$default_rx}" -
    ;;
  *)
    echo "usage: $0 [--daemon] install [state-dir] [rx-stlink-serial] | uninstall | status | render [state-dir] [rx]" >&2
    exit 2
    ;;
esac
