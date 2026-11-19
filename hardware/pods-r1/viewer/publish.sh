#!/bin/sh
# Rebuild the UV crown 3D view and publish it to the 2389 artifact host (tailnet):
#   https://artifacts.folk-fujita.ts.net/p/uv-dome-crown/
# Usage (from anywhere): sh hardware/pods-r1/viewer/publish.sh [--no-publish]
# Only our own CAD goes in (podbox.py + the Session Q models); the shield's mesh never does (unknown licence).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../sheets/env.sh"
OUT="$HERE/out"
rm -rf "$OUT" && mkdir -p "$OUT"
"$CADPY" -B "$HERE/export_crown.py" "$OUT"
cp "$HERE/index.html" "$OUT/index.html"
[ "$1" = "--no-publish" ] && { echo "built $OUT (not published)"; exit 0; }
COPYFILE_DISABLE=1 tar -czf "$OUT.tgz" -C "$OUT" .
curl -sS -f -m 180 -X PUT 'https://artifacts.folk-fujita.ts.net/api/v1/artifacts/uv-dome-crown' \
  -H 'Content-Type: application/gzip' --data-binary @"$OUT.tgz" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("published v%s %s (%s)" % (d["version"], d["url"], d["visibility"]))'
rm -f "$OUT.tgz"
