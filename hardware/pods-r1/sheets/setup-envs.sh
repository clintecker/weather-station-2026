#!/bin/sh
# Create or update the sheets' two interpreters at the repo root (uv: https://docs.astral.sh/uv/).
#   .venv-cad: CadQuery 2.7 + shapely (also used by box/ and shield/); .venv-pdf: reportlab + svglib on Python 3.13.
set -e
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
[ -x .venv-cad/bin/python ] || uv venv --python 3.12 .venv-cad
uv pip install --python .venv-cad/bin/python -r hardware/pods-r1/sheets/requirements-cad.txt
[ -x .venv-pdf/bin/python ] || uv venv --python 3.13 .venv-pdf
uv pip install --python .venv-pdf/bin/python -r hardware/pods-r1/sheets/requirements-pdf.txt
echo "ok: CADPY=.venv-cad/bin/python PDFPY=.venv-pdf/bin/python"
