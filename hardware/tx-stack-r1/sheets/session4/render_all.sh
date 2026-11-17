#!/bin/sh
# Render every scene of scenes4.py, ONE per process (a multi-scene run segfaults partway and still exits 0), then
# check that every expected SVG exists. Usage: sh render_all.sh [NAME ...]
PY=${CADPY:-/private/tmp/claude-501/-Users-clint-code-electronics-weather-station-2026/68ade3da-6079-4ead-9fba-a514cb7d2eb1/scratchpad/cadx/bin/python}
cd "$(dirname "$0")"
NAMES=${*:-$($PY -B scenes4.py list)}
for n in $NAMES; do
  rm -f svg/$n.svg
  $PY -B scenes4.py $n || echo "FAILED $n"
done
miss=0
for n in $NAMES; do [ -s svg/$n.svg ] || { echo "MISSING svg/$n.svg"; miss=1; }; done
[ $miss = 0 ] && echo "all $(echo $NAMES | wc -w | tr -d ' ') scenes rendered"
