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
echo "== pod electrical checks P1-P7"
cd ../..; .venv/bin/python -m unittest tests.test_pods_checks; cd hardware/pods-r1
../../.venv/bin/python layout/pod_checks.py
echo "== assembled shield and SHT45 fit (only when the shield 3MF is on this machine)"
if ../../.venv/bin/python -c "import sys; sys.path.insert(0, '.'); import sources; sys.exit(0 if sources.shield_path().exists() else 1)" \
   && [ -x ../../.venv-cad/bin/python ]; then
  cd ../..; .venv-cad/bin/python -m unittest tests.test_pods_shield; cd hardware/pods-r1
  ../../.venv-cad/bin/python shield/assemble.py
else
  echo "skipped: the shield 3MF (sources.shield_3mf) or .venv-cad is not on this machine"
fi
echo "== pod boxes (TH, BARO, UV): STLs, then the fit, openings, seal and window checks"
if [ -x ../../.venv-cad/bin/python ]; then
  ../../.venv-cad/bin/python box/podbox.py
  cd ../..; .venv-cad/bin/python -m unittest tests.test_pods_box; cd hardware/pods-r1
else
  echo "skipped: .venv-cad (CadQuery) is not on this machine"
fi
echo "== shield remix: cap bosses (UV), arm faces (TH, BARO), TH lead (only when the shield 3MF is on this machine)"
if ../../.venv/bin/python -c "import sys; sys.path.insert(0, '.'); import sources; sys.exit(0 if sources.shield_path().exists() else 1)" \
   && [ -x ../../.venv-cad/bin/python ]; then
  cd ../..; .venv-cad/bin/python -m unittest tests.test_pods_remix; cd hardware/pods-r1
  ../../.venv-cad/bin/python shield/remix.py
else
  echo "skipped: the shield 3MF (sources.shield_3mf) or .venv-cad is not on this machine"
fi
echo "== Session P + Q bench sheets: render the scenes, build the PDFs, label and hole checks (CADPY/PDFPY from sheets/env.sh)"
. sheets/env.sh
SHEETS_SKIPPED=""
if [ -z "$_PODS_MISSING" ]; then
  cd ../..; .venv/bin/python -m unittest tests.test_pods_sheets; cd hardware/pods-r1
  if ! ../../.venv/bin/python -c "import sys; sys.path.insert(0, '.'); import sources as S; from pathlib import Path; o = Path(S.val('shield_out')).expanduser(); \
sys.exit(0 if S.shield_path().exists() and (o / 'cap_remixed.stl').exists() and (o / 'arm_remixed.stl').exists() else 1)"; then
    SHEETS_SKIPPED=1
    echo "################################################################################"
    echo "WARNING: Session Q sheets NOT BUILT: the shield 3MF (sources.shield_3mf) or the remixed STLs"
    echo "  (sources.shield_out: run .venv-cad/bin/python hardware/pods-r1/shield/remix.py) are not on this machine"
    echo "################################################################################"
  fi
else
  SHEETS_SKIPPED=1
  echo "################################################################################"
  echo "WARNING: Session P sheets SKIPPED: missing or incomplete:$_PODS_MISSING"
  echo "  set up: sh hardware/pods-r1/sheets/setup-envs.sh   (or set CADPY / PDFPY)"
  echo "################################################################################"
fi
if [ -n "$SHEETS_SKIPPED" ]; then
  echo "== pods-r1: every check that ran passes; WARNING: some bench sheets were SKIPPED (see above)"
else
  echo "== pods-r1: every check passes"
fi
