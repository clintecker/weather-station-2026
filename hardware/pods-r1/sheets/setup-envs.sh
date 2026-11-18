#!/bin/sh
# Create or update the sheets' two interpreters at the repo root (uv: https://docs.astral.sh/uv/).
#   .venv-cad: CadQuery 2.7 + shapely (also used by box/ and shield/); .venv-pdf: reportlab + svglib on Python 3.13.
# Then fetches the makers' STEP models (hardware/tx-stack-r1/render/fetch_models.py). The plain .venv (repo root)
# is a prerequisite of run.sh and is set up by the repo's own instructions, not here.
set -e
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
[ -x .venv-cad/bin/python ] || uv venv --python 3.12 .venv-cad
uv pip install --python .venv-cad/bin/python -r hardware/pods-r1/sheets/requirements-cad.txt
[ -x .venv-pdf/bin/python ] || uv venv --python 3.13 .venv-pdf
uv pip install --python .venv-pdf/bin/python -r hardware/pods-r1/sheets/requirements-pdf.txt
echo "ok: CADPY=.venv-cad/bin/python PDFPY=.venv-pdf/bin/python"
# The makers' STEP models the sheets draw (gitignored): the BOB-14021 board STEP is built from SparkFun's Eagle file with
# kicad-cli; the others are Adafruit / Pololu STEPs. Each download is checked against its recorded sha256 (-I: it reads
# downloaded files). It always exits 0, so check the one Session P needs.
python3 -I hardware/tx-stack-r1/render/fetch_models.py
if [ -f hardware/tx-stack-r1/render/models/BOB/bob14021_board.step ]; then
  echo "ok: BOB-14021 board STEP"
else
  echo "WARNING: the BOB-14021 board STEP was not built (is kicad-cli on PATH?); the Session P and Q sheets will skip" >&2
fi
