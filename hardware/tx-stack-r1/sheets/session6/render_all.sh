#!/bin/sh
# Render every Session 6 scene, ONE per process (a multi-scene run segfaults partway and still exits 0),
# JOBS at a time (default 4), then check every expected SVG exists. Usage: sh render_all.sh [NAME ...]
HERE=$(cd "$(dirname "$0")" && pwd)
CAD=${CAD:-$HERE/../../../../.venv-cad/bin/python}   # repo-local venv (hardware/pods-r1/sheets/setup-envs.sh)
cd "$HERE"
NAMES=${*:-$($CAD -B scenes6.py list)}
for n in $NAMES; do rm -f "svg/$n.svg"; done
echo $NAMES | tr ' ' '\n' | xargs -P "${JOBS:-4}" -I{} sh -c "$CAD -B scenes6.py {} 2>&1 | tail -1"
missing=0
for n in $NAMES; do
  [ -s "svg/$n.svg" ] || { echo "MISSING svg/$n.svg"; missing=1; }
done
[ $missing = 0 ] && echo "all $(echo $NAMES | wc -w | tr -d ' ') scenes rendered"
exit $missing
