"""The sensor pods' dimension table (hardware/pods-r1/sources.py): keys, citations, and what stays out of git."""
import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PODS = ROOT / "hardware" / "pods-r1"


def load():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("pods_sources", PODS / "sources.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PodsSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = load()

    def test_keys_present(self):
        s = self.s
        for k in ("permaproto_q", "permaproto_q_cols", "permaproto_q_rows", "permaproto_q_rails"):
            self.assertIn(k, s.D)
        for b in ("sht45", "bmp581", "ltr390", "eeprom_24lc32"):
            for suffix in ("", "_pins", "_pullup_k", "_addr"):
                self.assertIn(b + suffix, s.D, b + suffix)
        self.assertIn("eeprom_24lc32_wp", s.D)
        self.assertEqual(s.val("pg7_seal"), (3.0, 4.3))
        self.assertEqual(s.val("cable_max_m"), 2.0)
        self.assertIn("cable_pf_per_m", s.D)
        self.assertTrue(s.tbd("cable_pf_per_m"))
        self.assertEqual(s.val("i2c_sink_ma"), 3.0)
        self.assertEqual(s.val("rise_ns_max"), 1000)
        self.assertEqual(s.val("sht45_addr"), "0x44")
        self.assertEqual(s.val("bmp581_addr"), "0x47")
        self.assertEqual(s.val("ltr390_addr"), "0x53")
        self.assertEqual(s.val("eeprom_24lc32_addr"), "0x50")
        self.assertEqual(s.val("permaproto_q"), (43.18, 50.8))

    def test_shared_tx_values_are_read_not_copied(self):
        s = self.s
        self.assertEqual(s.val("bob_w"), s.TX.val("bob_w"))
        self.assertEqual(s.val("jack_w"), s.TX.val("jack_w"))
        self.assertNotIn("bob_w", s.D)

    def test_permaproto_grid_is_the_files(self):
        holes = self.s.permaproto_q_holes()
        self.assertEqual(len(holes), 210)
        self.assertEqual(len({(x, y) for x, y, _ in holes}), 210)
        self.assertEqual(len({st for _, _, st in holes}), 34)       # 30 five-hole strips + 4 rails

    def test_every_row_is_wellformed(self):
        for k, row in self.s.D.items():
            self.assertEqual(len(row), 4, k)
            self.assertIn(row[3], ("sourced", "derived", "TBD"), k)

    def test_every_sourced_row_cites(self):
        for k, (v, what, src, st) in self.s.D.items():
            if st == "sourced":
                self.assertTrue(re.search(r"https?://|[\w.-]+/[\w./-]*\.[A-Za-z0-9]{2,4}\b", src), f"{k}: no URL or path in the source")

    def test_readme_table_in_step(self):
        self.assertTrue(self.s.sync_readme(check=True))

    def test_shield_row(self):
        path, sha = self.s.val("shield_3mf")
        self.assertTrue(path.endswith("Stevenson_screen_NFS.3mf"))
        self.assertRegex(sha, r"^[0-9a-f]{64}$")
        self.assertEqual(self.s.D["shield_3mf"][3], "sourced")

    def test_label_units(self):
        self.assertEqual(self.s.label("sht45_addr"), "0x44")
        self.assertEqual(self.s.label("cable_max_m"), "2 mm")
        self.assertTrue(self.s.label("cable_pf_per_m").endswith("[TBD-MEASURE]"))

    def test_table_has_no_home_path(self):
        self.assertNotIn(str(Path.home()), self.s.table())
        self.assertTrue(self.s.val("shield_3mf")[0].startswith("~/"))

    def test_shield_not_in_git(self):
        files = subprocess.run(["git", "ls-files", "hardware/pods-r1"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        for f in files:
            self.assertFalse(f.lower().endswith(".3mf"), f)
            self.assertNotIn("stevenson", f.lower(), f)
            self.assertNotIn("object_70", f.lower(), f)
            self.assertNotIn("object_72", f.lower(), f)


if __name__ == "__main__":
    unittest.main()
