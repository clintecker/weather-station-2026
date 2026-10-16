"""Power-cut tests for the node flash store.

firmware/stage0-node/App/node_store.c is compiled for the host over firmware/sim_flash.c, a RAM
model of the STM32WL flash (erased = all ones, each double-word programmed once, torn programs
read back as ECC faults, interrupted erases leave a partially erased page). firmware/test_store.c
runs a scripted workload (provision, boot epochs, counter blocks, journal appends and ACKs,
abandons, meta-log compaction, journal wrap with losses, storm scrub, WIPE) and, in the sweep,
cuts power at every flash operation index with every cut outcome, then reboots and checks the
invariants listed at the top of test_store.c. These are host-model results, not bench evidence
(the physical reset-during-write storm, tools/power_cut_test.py, stays the hardware check).
"""
import re
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from toolchain import CC_STRICT, ROOT, SAN, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import CC_STRICT, ROOT, SAN, needs_cc    # python -m unittest tests.<module>

FW = ROOT/'firmware'
APP = FW/'stage0-node'/'App'
SOURCES = [APP/'node_store.c', FW/'sim_flash.c', FW/'test_store.c', FW/'common/ws_check.c']
SMALL_JOURNAL = 3  # journal pages in the reduced-geometry build, so every-op sweeps include a wrap

# Every category the driver can report, by meaning. Anything not listed in NOTES or in a
# known-bug test below fails the sweeps, so a new kind of violation can never pass silently.
NOTES = {
    # A WIPE interrupted part way may leave acked records readable (and pending) again; the
    # operator never saw "#wipe ok" and must re-run WIPE. Not a store guarantee.
    'note_acked_back_after_interrupted_wipe',
    # A record counted lost whose page erase then failed is pending again (over-count only).
    'note_lost_back',
}
# Bugs found by this harness and fixed 2026-10-13 (each still has its regression test below).
# Nothing is tolerated any more: a sweep showing any of these categories fails.
KNOWN_CUT = set()
KNOWN_ERR = set()


# Every (build, mode, wrap) driver run the tests below read. setUpClass runs them all at once in
# parallel; a key missing here still works (run_driver runs it on first use), only slower.
RUNS = [('full', 'functional', '1'), ('small', 'functional', '1'), ('small', 'sweep', '1'),
        ('full', 'sweep', '0'), ('wide', 'sweep', '1'), ('wide', 'errsweep', '1'),
        ('wide', 'functional', '1'), ('small', 'errsweep', '1'), ('full', 'errsweep', '0')]


def parse(out):
    counts = {m[1]: int(m[2]) for m in re.finditer(r'^COUNT (\S+) (\d+)$', out, re.M)}
    summary = dict(re.findall(r'(\w+)=(\S+)', re.search(r'^SUMMARY (.*)$', out, re.M)[1]))
    return counts, summary


@needs_cc
class StorePowerCut(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        base = [*CC_STRICT, '-O1', '-g', '-I', str(FW), '-I', str(APP), '-I', str(FW/'common')]
        # 'wide': the largest slot (every catalog field), so a geometry-specific bookkeeping slip
        # cannot hide behind the default field set (one did, 2026-10-14, with 56-byte slots).
        wide = ['-DWS_NODE_FIELDS=WS_FIELDS_DEFINED', f'-DWS_JOURNAL_PAGES={SMALL_JOURNAL}U']
        builds = {'full': [], 'small': [f'-DWS_JOURNAL_PAGES={SMALL_JOURNAL}U'], 'wide': wide}
        cls.exe = {name: str(Path(cls.tmp.name)/f'test_store_{name}') for name in builds}

        def compile(name):
            cmd = base + builds[name] + [*map(str, SOURCES), '-o', cls.exe[name]]
            # ASan + UBSan when the toolchain has them (macOS clang and Linux gcc/clang do).
            if subprocess.run(cmd[:1] + SAN + cmd[1:], capture_output=True).returncode:
                subprocess.run(cmd, check=True)

        def run(key):
            try:
                return cls.drive(*key)
            except Exception as e:       # raised again by run_driver, in the test that reads this key
                return e

        with ThreadPoolExecutor(max_workers=max(len(builds), len(RUNS))) as pool:
            list(pool.map(compile, builds))          # a failed build fails setUpClass, as before
            cls.results = dict(zip(RUNS, pool.map(run, RUNS), strict=True))

    @classmethod
    def drive(cls, build, *args):
        proc = subprocess.run([cls.exe[build], *args], capture_output=True, text=True, timeout=600)
        if proc.returncode:
            raise AssertionError(f'test_store {args} exited {proc.returncode}:\n{proc.stdout[-4000:]}{proc.stderr[-4000:]}')
        return (proc.stdout, *parse(proc.stdout))

    @classmethod
    def run_driver(cls, build, *args):
        key = (build,) + args
        if key not in cls.results:
            cls.results[key] = cls.drive(build, *args)
        result = cls.results[key]
        if isinstance(result, Exception):
            raise result
        return result

    def assert_only(self, out, counts, allowed, s):
        self.assertEqual(s['check_fails'], '0', 'no WS_CHECK fails in a sweep (docs/power-of-ten.md, rule 5)')
        bad = {c: n for c, n in counts.items() if c not in allowed}
        violations = '\n'.join(line for line in out.splitlines()
                               if line.startswith('VIOLATION') and line.split()[1] in bad)
        self.assertEqual(bad, {}, violations)

    def test_functional_full_geometry(self):
        """No faults, 93 journal pages: exact bookkeeping, wrap, two meta compactions, WIPE."""
        out, counts, s = self.run_driver('full', 'functional', '1')
        self.assertEqual(counts, {}, out)
        self.assertEqual(s['guard_failures'], '0', out)
        # test_store.c checks(): three deliberate refusals of a ref outside the journal (WS_CHECK,
        # docs/power-of-ten.md rule 5), counted and recovered; the workload fails none.
        self.assertEqual(s['check_fails'], '3', out)
        meta = [int(x) for x in s['meta_erases'].split(',')]
        self.assertGreaterEqual(min(meta), 1, 'both meta pages compacted into')
        self.assertGreaterEqual(sum(meta), 3, 'at least two compactions after the first boot')
        self.assertGreaterEqual(int(s['journal0_erases']), 2, 'journal wrapped onto page 0')
        self.assertGreater(int(s['lost']), 0)
        self.assertGreater(int(s['abandoned']), 0)
        self.assertEqual(s['wipes'], '1')
        self.assertGreater(int(s['max_counter']), 3 * 256, 'counters crossed reservation blocks')

    def test_unknown_mode_rejected(self):
        """A mistyped mode must not silently run as a sweep (it used to)."""
        proc = subprocess.run([self.exe['small'], 'sweeep', '1'], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn('SUMMARY', proc.stdout)

    def test_functional_small_geometry(self):
        out, counts, s = self.run_driver('small', 'functional', '1')
        self.assertEqual(counts, {}, out)
        self.assertEqual(s['guard_failures'], '0', out)
        self.assertEqual(s['check_fails'], '3', out)
        self.assertGreaterEqual(int(s['journal0_erases']), 2)
        self.assertGreater(int(s['lost']), 0)

    def test_powercut_every_op_with_wrap(self):
        """Cut at every flash op, every outcome (3 journal pages so the sweep wraps and loses).

        Invariants after each reboot: counters and epochs only rise past every value handed out;
        no ACKed record is pending again; pending records that vanish are covered by the rise in
        the lost total; lost and abandoned totals never fall; config is the one written or
        none; the meta log survives WIPE; nothing programs a non-erased double-word."""
        out, counts, s = self.run_driver('small', 'sweep', '1')
        self.assertGreater(int(s['cut_points']), 1500)
        self.assertGreater(int(s['erase_cuts']), 50)
        self.assert_only(out, counts, NOTES | KNOWN_CUT, s)

    def test_powercut_every_op_full_geometry(self):
        """The same with the real 93-page journal (no wrap: the small build covers that)."""
        out, counts, s = self.run_driver('full', 'sweep', '0')
        self.assertGreater(int(s['cut_points']), 900)
        self.assertGreater(int(s['erase_cuts']), 400)
        self.assert_only(out, counts, NOTES | KNOWN_CUT, s)

    def test_powercut_every_op_widest_slot(self):
        """The wrap sweep and error sweep again with the largest slot the catalog allows."""
        for mode in ('sweep', 'errsweep'):
            out, counts, s = self.run_driver('wide', mode, '1')
            self.assert_only(out, counts, NOTES | (KNOWN_CUT if mode == 'sweep' else KNOWN_ERR), s)
        out, counts, s = self.run_driver('wide', 'functional', '1')
        self.assertEqual(counts, {}, out)

    def test_flash_error_every_op(self):
        """A HAL program or erase error at every op (flash unchanged, or torn / partially
        erased), the workload carries on, then the same reboot checks."""
        for build, wrap in (('small', '1'), ('full', '0')):
            out, counts, s = self.run_driver(build, 'errsweep', wrap)
            self.assert_only(out, counts, NOTES | KNOWN_ERR, s)

    # ---- regression tests for the bugs this harness found, all fixed 2026-10-13 (KNOWN_CUT and
    # KNOWN_ERR are empty). Each docstring says what went wrong and how it was fixed ----

    def test_bug_interrupted_recycle_resurrects_acked_record(self):
        """A cut during the page erase in journal_new_page (an append wrapping onto the oldest
        page) could erase a slot's ACK word but not its data; journal_init then read the acked
        record as pending, and it was sent again. Fixed by: at the end of store_journal_init, if the
        head page is full (head_slot == JOURNAL_SLOTS_PER_PAGE), finish the recycle of
        (head + 1) % WS_JOURNAL_PAGES with journal_new_page before setting journal_ready. Its
        pending records are counted lost (they would be dropped by the next append anyway)."""
        out, counts, _ = self.run_driver('small', 'sweep', '1')
        self.assertEqual(counts.get('acked_returned_recycle_erase', 0), 0)

    def test_bug_interrupted_wipe_leaves_journal_on_unprovisioned_board(self):
        """store_wipe erased the config page first, then the journal. A cut (or a failed erase)
        after the key was gone left an unprovisioned board whose journal still held pending
        records; after the next PROVISION they went out under the new station identity. Fixed by:
        erase the journal pages first and the config page last, and keep the key (return -1)
        if any journal erase failed."""
        _, cut, _ = self.run_driver('small', 'sweep', '1')
        _, err, _ = self.run_driver('small', 'errsweep', '1')
        self.assertEqual((cut.get('wipe_journal_survives', 0), err.get('wipe_journal_survives', 0)), (0, 0))

    def test_bug_failed_abandon_note_lowers_total_after_reboot(self):
        """store_note_abandoned raised abandoned_total in RAM before meta_append; if that
        program failed, STATUS and the health report (DIAG) had shown a total that the next boot
        did not restore.
        Fixed by: if (meta_append(META_ABAND, abandoned_total + 1)) return -1; then increment."""
        _, counts, _ = self.run_driver('small', 'errsweep', '1')
        self.assertEqual(counts.get('abandoned_decreased_note_failed', 0), 0)

    def test_bug_failed_lost_persist_still_erases_page(self):
        """journal_new_page ignored a failed meta_append(META_LOST) and erased the page anyway,
        so the dropped records were gone while the persisted lost total never counted them.
        Fixed by: count the pending slots first, persist lost_total + dropped, and on failure return
        -1 before clearing pending bits or erasing (the append fails; nothing is lost)."""
        _, counts, _ = self.run_driver('small', 'errsweep', '1')
        self.assertEqual(counts.get('lost_decreased_wrap_persist_failed', 0), 0)


if __name__ == '__main__':
    unittest.main()
