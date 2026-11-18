#!/bin/sh
# Lay out Session P (the pod boards and the cable) from the rendered scenes: writes out/session-p-pods.pdf and
# out/session-p-manifest.json, and exits non-zero on any label-overlap or hole-callout issue. Render first: sh render_all.sh
cd "$(dirname "$0")"
. ./env.sh
mkdir -p out
exec "$PDFPY" -B make_session_p.py out
