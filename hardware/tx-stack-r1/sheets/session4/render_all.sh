#!/bin/sh
# Render every scene of scenes4.py, ONE per process (a multi-scene run segfaults partway and still exits 0), then
# check that every expected SVG exists. Usage: sh render_all.sh [NAME ...]
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${CADPY:-$HERE/../../../../.venv-cad/bin/python}   # repo-local venv (hardware/pods-r1/sheets/setup-envs.sh)
cd "$(dirname "$0")"
NAMES=${*:-$($PY -B scenes4.py list)}
for n in $NAMES; do
  rm -f svg/$n.svg
  $PY -B scenes4.py $n || echo "FAILED $n"
done
miss=0
for n in $NAMES; do [ -s svg/$n.svg ] || { echo "MISSING svg/$n.svg"; miss=1; }; done
[ $miss = 0 ] && echo "all $(echo $NAMES | wc -w | tr -d ' ') scenes rendered"
