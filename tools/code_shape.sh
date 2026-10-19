#!/bin/sh
# Shape checks for our C (CI host job; run locally the same way): every function stays small and
# nothing is copied. Vendor code, ST-generated board files and the host test programs
# (firmware/test_*.c) are out of scope; the host harnesses under firmware/host are in.
#   lizard: cyclomatic complexity <= 10 and <= 60 lines per function (warnings fail)
#   jscpd:  no clone of 5+ lines / 40+ tokens (any duplication fails)
#   tools/tangle.py --check: every generated file (node_store.c) is what its .lit.md document tangles
#           to, so the checks below judge the code the document holds
#   tools/wsmp_registry.py --check: the generated WSMP registry (C and Python) matches its TOML, and
#           no code was removed or renamed (append-only, docs/module-protocol.md WSMP-G1)
#   tools/loop_bounds.py: every firmware loop is a counting loop or has a "bound:" comment (Power of
#           Ten rule 2, docs/power-of-ten.md); the host harnesses are not checked
# Needs lizard (requirements-dev.txt) and Node.js for npx.
set -eu
cd "$(dirname "$0")/.."
PATHS="firmware/stage0-node/App firmware/common firmware/stage0.c firmware/host"
python3 tools/tangle.py --check
python3 tools/wsmp_registry.py --check
lizard -C 10 -L 60 -w $PATHS
npx --yes jscpd@4.0.5 --min-lines 5 --min-tokens 40 --format c --threshold 0 --silent $PATHS
python3 tools/loop_bounds.py
echo "code shape: OK (generated C matches its document and the WSMP registry; lizard CCN <= 10, <= 60 lines; no duplication; every loop bounded)"
