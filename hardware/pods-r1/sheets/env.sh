# The two interpreters the pod sheets use (sourced by render_all.sh, build.sh and tests/test_pods_sheets.py).
# Same environments as the TX sheets (hardware/tx-stack-r1/sheets/session3/render_all.sh): set CADPY / PDFPY to override.
#   CADPY: CadQuery 2.7 + OpenCascade + shapely (the repo's .venv-cad lacks shapely; the TX sessions' cadx venv has it)
#   PDFPY: reportlab + svglib, pinned in hardware/tx-stack-r1/sheets/requirements-pdf.txt (.venv-cad lacks reportlab)
_SP=/private/tmp/claude-501/-Users-clint-code-electronics-weather-station-2026/68ade3da-6079-4ead-9fba-a514cb7d2eb1/scratchpad
CADPY=${CADPY:-$_SP/cadx/bin/python}
PDFPY=${PDFPY:-$_SP/pdfenv/bin/python}
