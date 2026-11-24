#!/bin/sh
# Rebuild the printed-parts pages and publish them to the 2389 artifact host (tailnet), index last:
#   https://artifacts.folk-fujita.ts.net/p/printed-parts/   and one printed-<part> page per printed part.
# Usage (from anywhere): sh hardware/printed-parts-pages/publish.sh [--no-publish]
# Our own CAD goes up to `everyone`. The pages in build.py's RESTRICTED list hold shapes from the radiation shield's 3MF
# (unknown licence): they go up restricted to the whoami account alone, their settings are read back after every
# publish, and a page that doesn't read back that way is deleted. Their files live only in out/ (gitignored).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/../pods-r1/sheets/env.sh"
OUT="$HERE/out"
rm -rf "$OUT" && mkdir -p "$OUT"
"$CADPY" -B "$HERE/build.py" "$OUT"
[ "$1" = "--no-publish" ] && { echo "built $OUT (not published)"; exit 0; }
"$CADPY" -B "$HERE/build.py" "$OUT" --publish
