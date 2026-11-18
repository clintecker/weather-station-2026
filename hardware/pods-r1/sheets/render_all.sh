#!/bin/sh
# Render every scene of scenes_p.py, ONE per process (a multi-scene run segfaults partway and still exits 0, as in the TX
# sheets), several at a time. A scene is re-rendered when its SVG is missing or older than any of its sources
# (scenes_p.py, models_p.py, the layout and sources.py); FORCE=1 re-renders all. Then checks every SVG exists.
# Usage: sh render_all.sh [NAME ...]        (JOBS=n sets how many run at once, default 6)
cd "$(dirname "$0")"
. ./env.sh
mkdir -p svg
NAMES=${*:-$("$CADPY" -B scenes_p.py list)}
[ -n "$NAMES" ] || { echo "scenes_p.py list failed"; exit 1; }
SRC="scenes_p.py models_p.py ../layout/pods.py ../layout/permaproto.py ../layout/pod_checks.py ../sources.py"
TODO=""
for n in $NAMES; do
  stale=0
  [ -s svg/$n.svg ] || stale=1
  [ "${FORCE:-0}" = 1 ] && stale=1
  if [ $stale = 0 ]; then
    for f in $SRC; do [ "$f" -nt svg/$n.svg ] && stale=1; done
  fi
  [ $stale = 1 ] && { rm -f svg/$n.svg svg/$n.json; TODO="$TODO $n"; }
done
if [ -n "$TODO" ]; then
  echo "rendering:$TODO"
  echo $TODO | tr ' ' '\n' | xargs -P "${JOBS:-6}" -I{} sh -c '"$0" -B scenes_p.py {} > svg/{}.log 2>&1 || echo "FAILED {}: $(tail -3 svg/{}.log)"' "$CADPY"
fi
miss=0
for n in $NAMES; do [ -s svg/$n.svg ] || { echo "MISSING svg/$n.svg: $(tail -3 svg/$n.log 2>/dev/null)"; miss=1; }; done
[ $miss = 0 ] || exit 1
echo "all $(echo $NAMES | wc -w | tr -d ' ') scenes rendered"
