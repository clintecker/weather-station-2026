"""Bench sheets for the sensor pods (hardware/pods-r1/sheets).

Session P (the pod boards and the cable): the scenes are rendered from CadQuery models (one scene per process, in the
CAD venv), then make_session_p.py lays out the PDF (in the PDF venv), runs the label-overlap and hole-callout checks,
and writes a manifest of its pages. The build fails on any label or hole issue; this test reads the manifest.

The two interpreters are the TX sheets' (hardware/tx-stack-r1/sheets, session3/render_all.sh): CADPY (CadQuery,
OpenCascade, shapely) and PDFPY (reportlab, svglib). Both default to the paths in hardware/pods-r1/sheets/env.sh;
the test skips when either is missing (CI), or when the BOB-14021 board STEP is not on this machine.
Run from the repo root:
    .venv/bin/python -m unittest tests.test_pods_sheets -v
"""
import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEETS = ROOT / "hardware" / "pods-r1" / "sheets"
BOB_STEP = ROOT / "hardware" / "tx-stack-r1" / "render" / "models" / "BOB" / "bob14021_board.step"


def _env():
    """CADPY and PDFPY as sheets/env.sh sets them (the environment overrides it)."""
    if not (SHEETS / "env.sh").exists():
        return None, None
    out = subprocess.run(["sh", "-c", f'. "{SHEETS / "env.sh"}"; echo "$CADPY"; echo "$PDFPY"'],
                         capture_output=True, text=True)
    cad, pdf = (out.stdout.splitlines() + ["", ""])[:2]
    return cad, pdf


class SessionP(unittest.TestCase):
    def test_session_p_builds(self):
        cad, pdf = _env()
        if not cad or not pdf:
            self.fail("hardware/pods-r1/sheets/env.sh is missing: it names the CAD and PDF interpreters")
        if not Path(cad).exists() or not Path(pdf).exists():
            self.skipTest(f"CAD ({cad}) or PDF ({pdf}) interpreter not on this machine")
        if not BOB_STEP.exists():
            self.skipTest("the BOB-14021 board STEP (tx-stack-r1/render/fetch_models.py) is not on this machine")
        r = subprocess.run(["sh", str(SHEETS / "render_all.sh")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        self.assertIn("scenes rendered", r.stdout)
        r = subprocess.run(["sh", str(SHEETS / "build.sh")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        man = json.loads((SHEETS / "out" / "session-p-manifest.json").read_text())
        self.assertEqual(man["label_issues"], 0)
        self.assertEqual(man["hole_issues"], 0)
        self.assertTrue((SHEETS / "out" / "session-p-pods.pdf").exists())
        tags = {t for p in man["pages"] for t in p["tags"]}
        need = {"parts-as-supplied", "parts:bob", "parts:shunt", "parts:eeprom_24lc32", "parts:ltr390",
                "parts:bmp581", "parts:sht45", "faces", "bob-build", "cable", "cable:crimp-order",
                "cable:continuity", "cable:reversed"}
        for pod in ("TH", "BARO", "UV"):
            need |= {f"{pod}:jack-header", f"{pod}:jack", f"{pod}:eeprom", f"{pod}:wp-header", f"{pod}:strip-map",
                     f"{pod}:meter", f"{pod}:wires"}
            need |= {f"{pod}:lead"} if pod == "TH" else {f"{pod}:sensor"}
            for i in range(1, 10):
                need.add(f"{pod}:wire:w{i}")
        need |= {"BARO:header-cut", "TH:lead-sht45-end", "TH:lead-gland-order"}
        self.assertEqual(sorted(need - tags), [], "pages missing from the PDF")
        for p in man["pages"]:
            self.assertTrue(p["title"].strip(), p)
        self.assertEqual(man["page_count"], len(man["pages"]))


if __name__ == "__main__":
    unittest.main()
