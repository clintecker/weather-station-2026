#!/bin/sh
# Lay out Session Q (the boxes, the shield and the installation) from the rendered scenes: writes
# out/session-q-install.pdf and out/session-q-manifest.json, and exits non-zero on any label-overlap or hole-callout
# issue. Render first: sh render_q.sh. Both stay in the gitignored out/ (the shield pictures come from its meshes).
cd "$(dirname "$0")"
. ./env.sh
mkdir -p out
exec "$PDFPY" -B make_session_q.py out
