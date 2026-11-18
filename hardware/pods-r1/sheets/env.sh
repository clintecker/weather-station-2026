# The two interpreters the pod sheets use (sourced by render_all.sh, build.sh, run.sh and tests/test_pods_sheets.py).
#   CADPY: CadQuery 2.7 + OpenCascade + shapely   (hardware/pods-r1/sheets/requirements-cad.txt)
#   PDFPY: reportlab + svglib, Python 3.13        (hardware/pods-r1/sheets/requirements-pdf.txt, the TX sheets' pins)
# Order: CADPY / PDFPY from the environment if set; else the repo-local venvs (.venv-cad, .venv-pdf at the repo root);
# else nothing, with a WARNING. One-command setup (repo root): sh hardware/pods-r1/sheets/setup-envs.sh
_PODS_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo .)
CADPY=${CADPY:-$_PODS_ROOT/.venv-cad/bin/python}
PDFPY=${PDFPY:-$_PODS_ROOT/.venv-pdf/bin/python}
_PODS_MISSING=""
[ -x "$CADPY" ] && "$CADPY" -c "import cadquery, shapely" 2>/dev/null || _PODS_MISSING="$_PODS_MISSING CADPY=$CADPY"
[ -x "$PDFPY" ] && "$PDFPY" -c "import reportlab, svglib" 2>/dev/null || _PODS_MISSING="$_PODS_MISSING PDFPY=$PDFPY"
if [ -n "$_PODS_MISSING" ]; then
  {
    echo "################################################################################"
    echo "WARNING: pods-r1 Session P sheets: interpreter missing or incomplete:"
    for _m in $_PODS_MISSING; do echo "  $_m"; done
    echo "The sheets cannot be rendered or built. Set up the repo-local venvs from the repo root:"
    echo "  sh hardware/pods-r1/sheets/setup-envs.sh"
    echo "or point CADPY / PDFPY at interpreters that have them."
    echo "################################################################################"
  } >&2
fi
