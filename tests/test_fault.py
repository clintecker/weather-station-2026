"""The crash record and the boot counter (firmware/stage0-node/App/fault.c) on the host.

fault.c is compiled unchanged against a small stand-in for the chip (written below): the TAMP
backup registers BKP0R-BKP19R as a plain array that a power loss clears, the SCB fault status
registers, NVIC_SystemReset (which returns to the test through longjmp) and APP_PRINTF (captured).
Power telemetry design, sections 6.2 and 9.8: with no crash the last crash PC is 0, DR12 counts one
boot per fault_boot_note(), saturates at 0xFFFF and restarts on a power-on; fault_boot_note() is the
only DR12 writer and each role calls it exactly once a boot, before fault_report()."""
import ctypes
import re
import tempfile
import unittest
from pathlib import Path

try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>

APP = ROOT/'firmware/stage0-node/App'

CHIP_STUB = r'''
#ifndef STM32WLXX_H
#define STM32WLXX_H
#include <stdint.h>
typedef struct { volatile uint32_t BKP0R, BKP1R, BKP2R, BKP3R, BKP4R, BKP5R, BKP6R, BKP7R, BKP8R, BKP9R,
                 BKP10R, BKP11R, BKP12R, BKP13R, BKP14R, BKP15R, BKP16R, BKP17R, BKP18R, BKP19R; } TAMP_TypeDef;
extern TAMP_TypeDef stub_tamp;
#define TAMP (&stub_tamp)
typedef struct { volatile uint32_t CFSR, HFSR, BFAR; } SCB_Type;
extern SCB_Type stub_scb;
#define SCB (&stub_scb)
/* The RAM fault_record trusts a stacked frame in: here a host array (its address's low 32 bits). */
extern uint32_t stub_ram[64];
#define SRAM1_BASE ((uint32_t)(uintptr_t)stub_ram)
#define SRAM2_BASE SRAM1_BASE
#define SRAM2_SIZE ((uint32_t)sizeof stub_ram)
void NVIC_SystemReset(void) __attribute__((noreturn));
#endif
'''

SYS_APP_STUB = r'''
#ifndef SYS_APP_H
#define SYS_APP_H
#include <stdint.h>
int stub_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
#define APP_PRINTF(...) ((void)stub_printf(__VA_ARGS__))
void HAL_Delay(uint32_t ms);
#endif
'''

STUB_C = r'''
#include <setjmp.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include "fault.h"
#include "stm32wlxx.h"
#include "sys_app.h"

TAMP_TypeDef stub_tamp;
SCB_Type stub_scb;
uint32_t stub_ram[64];
static jmp_buf reset_jump;
static int resets;
static char out[4096];
static size_t out_len;

void NVIC_SystemReset(void) { resets++; longjmp(reset_jump, 1); }
void HAL_Delay(uint32_t ms) { (void)ms; }
int stub_printf(const char *fmt, ...)
{
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(out + out_len, sizeof out - out_len, fmt, ap);
  va_end(ap);
  if (n > 0) out_len += (size_t)n < sizeof out - out_len ? (size_t)n : sizeof out - out_len - 1U;
  return n;
}

uint32_t stub_bkp(int n) { return (&stub_tamp.BKP0R)[n]; }
void stub_set_bkp(int n, uint32_t v) { (&stub_tamp.BKP0R)[n] = v; }
void stub_power_loss(void) { memset((void *)&stub_tamp, 0, sizeof stub_tamp); resets = 0; out_len = 0; out[0] = 0; }
int stub_resets(void) { return resets; }
const char *stub_out(void) { return out; }
/* 1: the RAM array's 32-bit addresses do not wrap, so a frame in it is "in RAM" to fault_record. */
int stub_ram_usable(void) { return SRAM1_BASE <= UINT32_MAX - SRAM2_SIZE; }

/* A crash with the frame at stub_ram[at] (in RAM) or, when at < 0, at a NULL frame (not in RAM). */
void stub_crash(int at, uint32_t pc, uint32_t lr, uint32_t kind)
{
  uint32_t *frame = at < 0 ? NULL : &stub_ram[at];
  if (frame) { frame[5] = lr; frame[6] = pc; }
  stub_scb.CFSR = 0x8200U; stub_scb.HFSR = 0x40000000U; stub_scb.BFAR = 0x20040000U;
  if (setjmp(reset_jump) == 0) fault_record(frame, 0xFFFFFFF9U, kind);
}
'''

POWER_ON, NOT_POWER_ON = 1, 0
DR_PC, DR_COUNT, DR_BOOTS = 6, 11, 12


@needs_cc
class FaultRecord(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        inc = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(inc.cleanup)
        (Path(inc.name)/'stm32wlxx.h').write_text(CHIP_STUB)
        (Path(inc.name)/'sys_app.h').write_text(SYS_APP_STUB)
        # fault_record casts the frame pointer to the chip's 32-bit address: harmless on the host,
        # where the stub RAM's low 32 bits stand in for it.
        cls.lib = host_library(cls, 'fault', '-Wno-pointer-to-int-cast', '-I', inc.name, '-I', APP,
                               APP/'fault.c', files={'stub.c': STUB_C})
        lib = cls.lib
        for name in ('fault_count', 'fault_last_pc', 'fault_boots', 'stub_bkp'):
            getattr(lib, name).restype = ctypes.c_uint32
        lib.stub_set_bkp.argtypes = (ctypes.c_int, ctypes.c_uint32)
        lib.stub_crash.argtypes = (ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32)
        lib.stub_out.restype = ctypes.c_char_p

    def setUp(self):
        self.lib.stub_power_loss()

    def registers(self):
        return [self.lib.stub_bkp(n) for n in range(20)]

    def test_no_crash_gives_pc_zero(self):
        self.assertEqual((self.lib.fault_count(), self.lib.fault_last_pc()), (0, 0))
        self.lib.stub_set_bkp(DR_PC, 0x08001234)   # a stale PC is not reported while the count is 0
        self.assertEqual(self.lib.fault_last_pc(), 0)

    def test_the_last_pc_outlives_the_report(self):
        if not self.lib.stub_ram_usable():
            self.skipTest('the stub RAM address wraps in 32 bits')
        self.lib.stub_crash(0, 0x08001235, 0x08000F01, 1)
        self.lib.stub_crash(8, 0x08002469, 0x08000F01, 2)
        self.assertEqual((self.lib.stub_resets(), self.lib.fault_count(), self.lib.fault_last_pc()), (2, 2, 0x08002469))
        self.lib.fault_report()
        self.assertIn('#fault kind=nmi pc=08002469', self.lib.stub_out().decode())
        self.assertEqual(self.lib.fault_last_pc(), 0x08002469)   # fault_report clears only the magic
        self.lib.fault_boot_note(POWER_ON)
        self.assertEqual(self.lib.fault_last_pc(), 0x08002469)   # the boot counter leaves the record alone

    def test_an_untrusted_frame_reads_as_all_ones(self):
        self.lib.stub_crash(-1, 0, 0, 1)
        self.assertEqual((self.lib.fault_count(), self.lib.fault_last_pc()), (1, 0xFFFFFFFF))

    def test_one_increment_per_boot(self):
        self.lib.fault_boot_note(POWER_ON)
        self.assertEqual(self.lib.fault_boots(), 1)
        for boots in range(2, 6):
            self.lib.fault_boot_note(NOT_POWER_ON)
            self.assertEqual((self.lib.fault_boots(), self.lib.stub_bkp(DR_BOOTS)), (boots, boots))

    def test_a_power_on_restarts_the_count(self):
        self.lib.stub_set_bkp(DR_BOOTS, 41)   # a power-on that did not clear the backup domain (a brown-out)
        self.lib.fault_boot_note(POWER_ON)
        self.assertEqual(self.lib.fault_boots(), 1)

    def test_the_count_saturates_at_0xffff(self):
        self.lib.stub_set_bkp(DR_BOOTS, 0xFFFE)
        for _ in range(3):
            self.lib.fault_boot_note(NOT_POWER_ON)
        self.assertEqual(self.lib.fault_boots(), 0xFFFF)
        self.lib.fault_boot_note(POWER_ON)
        self.assertEqual(self.lib.fault_boots(), 1)

    def test_the_boot_note_writes_only_dr12(self):
        for n in range(20):
            self.lib.stub_set_bkp(n, 0x5A5A0000 + n)
        self.lib.stub_set_bkp(DR_BOOTS, 7)
        before = self.registers()
        self.lib.fault_boot_note(NOT_POWER_ON)
        after = self.registers()
        self.assertEqual([n for n in range(20) if before[n] != after[n]], [DR_BOOTS])
        self.assertEqual(after[DR_BOOTS], 8)


def code(path):
    """The C text of firmware file `path` without its comments."""
    return re.sub(r'/\*.*?\*/|//[^\n]*', ' ', (ROOT/path).read_text(errors='replace'), flags=re.S)


class BootNoteCallers(unittest.TestCase):
    """fault_boot_note() is DR12's only writer and runs once a boot, before fault_report(), in each role."""
    CALLERS = ('firmware/stage0-node/App/app_tx.c', 'firmware/stage0-node/App/app_rx.c',
               'firmware/benchlink/App/bl_guard.c')

    def test_each_role_notes_one_boot_before_the_report(self):
        for path in self.CALLERS:
            with self.subTest(path=path):
                text = code(path)
                self.assertEqual(len(re.findall(r'\bfault_boot_note\(', text)), 1)
                self.assertLess(text.index('fault_boot_note('), text.index('fault_report();'))

    def test_no_other_firmware_writes_dr12_or_calls_the_note(self):
        allowed = {*self.CALLERS, 'firmware/stage0-node/App/fault.c', 'firmware/stage0-node/App/fault.h',
                   'firmware/host/sim_core.c'}
        found = []
        for path in sorted((ROOT/'firmware').rglob('*.[ch]')):
            rel = path.relative_to(ROOT).as_posix()
            if rel in allowed or '/vendor/' in f'/{rel}':
                continue
            text = code(rel)
            if re.search(r'\bfault_boot_note\(|BKP12R|RTC_BKP_DR12|BKP\(\s*12\s*\)|BKP_BOOTS', text):
                found.append(rel)
        self.assertEqual(found, [])


if __name__ == '__main__':
    unittest.main()
