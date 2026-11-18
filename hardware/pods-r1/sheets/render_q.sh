#!/bin/sh
# Render every scene of scenes_q.py (Session Q: boxes, shield, install), ONE per process (a multi-scene run segfaults
# partway and still exits 0), several at a time. A scene is re-rendered when its SVG is missing or older than any of
# its sources; FORCE=1 re-renders all. Then checks every SVG exists. The shield scenes come from the shield's meshes
# (licence unknown): svg/ is gitignored and stays on this machine.
# Usage: sh render_q.sh [NAME ...]        (JOBS=n sets how many run at once, default 6)
cd "$(dirname "$0")"
. ./env.sh
mkdir -p svg
NAMES=${*:-$("$CADPY" -B scenes_q.py list)}
[ -n "$NAMES" ] || { echo "scenes_q.py list failed"; exit 1; }
SRC="scenes_q.py models_q.py mrender.py scenes_p.py models_p.py ../box/podbox.py ../shield/remix.py ../shield/assemble.py
     ../layout/pods.py ../layout/permaproto.py ../sources.py"
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
  echo $TODO | tr ' ' '\n' | xargs -P "${JOBS:-6}" -I{} sh -c '"$0" -B scenes_q.py {} > svg/{}.log 2>&1 || echo "FAILED {}: $(tail -3 svg/{}.log)"' "$CADPY"
fi
miss=0
for n in $NAMES; do [ -s svg/$n.svg ] || { echo "MISSING svg/$n.svg: $(tail -3 svg/$n.log 2>/dev/null)"; miss=1; }; done
[ $miss = 0 ] || exit 1
"$CADPY" -B scenes_q.py facts > svg/q_facts.log 2>&1 || { echo "FAILED facts: $(tail -3 svg/q_facts.log)"; exit 1; }
echo "all $(echo $NAMES | wc -w | tr -d ' ') scenes rendered"
