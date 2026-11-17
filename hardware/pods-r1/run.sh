#!/bin/sh
# Check everything that exists so far in hardware/pods-r1. Exits non-zero on the first failed step.
# Later tasks append their own steps (layout checks, CAD) below.
set -e
cd "$(dirname "$0")"
echo "== dimension table in README.md"
python3 sources.py --check
echo "== Perma-Proto model against sources and the .brd"
cd ../..; .venv/bin/python -m unittest tests.test_pods_permaproto; cd hardware/pods-r1
echo "== pod board layouts (TH, BARO, UV)"
cd ../..; .venv/bin/python -m unittest tests.test_pods_layout; cd hardware/pods-r1
echo "== pods-r1: every check passes"
