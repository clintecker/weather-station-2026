#!/bin/sh
# Shape checks for our C (CI host job; run locally the same way): every function stays small and
# nothing is copied. Vendor code, ST-generated board files and the host test programs
# (firmware/test_*.c) are out of scope; the host harnesses under firmware/host are in.
#   lizard: cyclomatic complexity <= 10 and <= 60 lines per function (warnings fail)
#   jscpd:  no clone of 5+ lines / 40+ tokens (any duplication fails)
# Needs lizard (requirements-dev.txt) and Node.js for npx.
set -eu
cd "$(dirname "$0")/.."
PATHS="firmware/stage0-node/App firmware/common firmware/stage0.c firmware/host"
lizard -C 10 -L 60 -w $PATHS
npx --yes jscpd@4.0.5 --min-lines 5 --min-tokens 40 --format c --threshold 0 --silent $PATHS
echo "code shape: OK (lizard CCN <= 10, <= 60 lines; no duplication)"
