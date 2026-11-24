#!/bin/sh
# Rebuild the printed-parts pages and publish them to the 2389 artifact host (tailnet), index last:
#   https://artifacts.folk-fujita.ts.net/p/printed-parts/   and one printed-<part> page per printed part.
# Usage (from anywhere): sh hardware/printed-parts-pages/publish.sh [--no-publish]
# Source: hardware/PRINTED-PARTS.md and the committed STLs (the retention bar is exported into out/ only).
# Only our own CAD goes in: nothing from the radiation shield's 3MF (unknown licence) or remix.py, ever.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../pods-r1/sheets/env.sh"
OUT="$HERE/out"
rm -rf "$OUT" && mkdir -p "$OUT"
"$CADPY" -B "$HERE/build.py" "$OUT"
# nothing shield-derived: no remix/shield/arm/cap file names, and no mesh outside our own STLs
if find "$OUT" -type f | grep -i -E 'shield|remix|arm|cap|3mf'; then echo "refusing: a shield-like file name in $OUT" >&2; exit 1; fi
[ "$1" = "--no-publish" ] && { echo "built $OUT (not published)"; exit 0; }
URLS="$OUT/urls.json"
echo '{}' > "$URLS"
put() {   # slug dir
  COPYFILE_DISABLE=1 tar -czf "$OUT/$1.tgz" -C "$2" .
  curl -sS -f -m 180 -X PUT "https://artifacts.folk-fujita.ts.net/api/v1/artifacts/$1" \
    -H 'Content-Type: application/gzip' --data-binary @"$OUT/$1.tgz" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); u=json.load(open(sys.argv[1])); u[sys.argv[2]]=d["url"]; json.dump(u,open(sys.argv[1],"w"),indent=1); print("published v%s %s (%s)" % (d["version"], d["url"], d["visibility"]))' "$URLS" "$1"
  rm -f "$OUT/$1.tgz"
}
for d in "$OUT"/printed-*/; do
  slug=$(basename "$d")
  [ "$slug" = printed-parts ] || put "$slug" "$d"
done
"$CADPY" -B "$HERE/build.py" "$OUT" --index-only --urls "$URLS"
put printed-parts "$OUT/printed-parts"
