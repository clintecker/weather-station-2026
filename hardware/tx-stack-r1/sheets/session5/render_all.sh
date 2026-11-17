#!/bin/sh
# Render every Session 5 scene, ONE per process (a multi-scene run segfaults partway and still exits 0),
# then check every expected SVG exists. Usage: sh render_all.sh [NAME ...]
CAD=${CAD:-/private/tmp/claude-501/-Users-clint-code-electronics-weather-station-2026/68ade3da-6079-4ead-9fba-a514cb7d2eb1/scratchpad/cadx/bin/python}
cd "$(dirname "$0")"
NAMES=${*:-$($CAD -B scenes5.py list)}
for n in $NAMES; do
  rm -f "svg/$n.svg"
  $CAD -B scenes5.py "$n" 2>&1 | tail -1
done
missing=0
for n in $NAMES; do
  [ -s "svg/$n.svg" ] || { echo "MISSING svg/$n.svg"; missing=1; }
done
[ $missing = 0 ] && echo "all $(echo $NAMES | wc -w | tr -d ' ') scenes rendered"
exit $missing
