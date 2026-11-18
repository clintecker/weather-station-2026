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
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEETS = ROOT / "hardware" / "pods-r1" / "sheets"
PAGES = 33      # 2 cover, faces, jack breakouts, BMP581 cut, headers, 8 (TH) + 7 (BARO) + 7 (UV), 2 cable pages
BOB_STEP = ROOT / "hardware" / "tx-stack-r1" / "render" / "models" / "BOB" / "bob14021_board.step"


def _env():
    """CADPY, PDFPY and what is missing, as sheets/env.sh sets them (the environment overrides it)."""
    if not (SHEETS / "env.sh").exists():
        return None, None, None
    out = subprocess.run(["sh", "-c", f'. "{SHEETS / "env.sh"}"; echo "$CADPY"; echo "$PDFPY"; echo "$_PODS_MISSING"'],
                         capture_output=True, text=True, cwd=ROOT)
    cad, pdf, missing = (out.stdout.splitlines() + ["", "", ""])[:3]
    return cad, pdf, missing.strip()


def pdf_page_count(path):
    """Page objects in the PDF itself (reportlab writes page dictionaries uncompressed), not the manifest's word."""
    return len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", Path(path).read_bytes()))


class SessionP(unittest.TestCase):
    def test_session_p_builds(self):
        cad, pdf, missing = _env()
        if not cad or not pdf:
            self.fail("hardware/pods-r1/sheets/env.sh is missing: it names the CAD and PDF interpreters")
        if missing:
            self.skipTest(f"WARNING: sheet interpreters missing or incomplete ({missing}); "
                          "set up with: sh hardware/pods-r1/sheets/setup-envs.sh")
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
        need |= {"BARO:header-cut", "TH:lead-sht45-end", "TH:lead-gland-order", "cable:per-pod"}
        self.assertEqual(sorted(need - tags), [], "pages missing from the PDF")
        for p in man["pages"]:
            self.assertTrue(p["title"].strip(), p)
        self.assertEqual(len(man["pages"]), PAGES)
        self.assertEqual(man["page_count"], PAGES)
        self.assertEqual(pdf_page_count(SHEETS / "out" / "session-p-pods.pdf"), PAGES, "the PDF's own page objects")
        self.assertEqual([p["page"] for p in man["pages"]], list(range(1, PAGES + 1)))


if __name__ == "__main__":
    unittest.main()
