"""Power acquisition (firmware/stage0-node/App/power_acq.c) on the host.

firmware/host/power_harness.c runs the driver on the shared I2C bus in the hub profile (WS_I2C_MUX=0),
with the host bus model's INA228 and MAX17048 (firmware/host/i2c_models.c) and the board ADC and CHG edge
seams of firmware/host/sim_core.c. One build for each power profile (App/power_config.h): phase A (1),
phase B (2, four INA228 rails) and phase C (3, the BQ25798 of the TX stack, in the mux profile it ships
with, WS_I2C_MUX=1). Expected values come from the design
(docs/superpowers/specs/2026-10-29-power-telemetry-design.md sections 3, 6.1, 6.3, 9.3 to 9.5) and the
datasheets (TI SBOS904, Analog Devices MAX17048, ST DS13293, TI SLUS810, TI SLUSDV2C), not from the code
under test. Host-model results, not bench evidence."""
import ctypes
import unittest

try:
    from toolchain import ROOT, fresh_station, host_library, load_tool, needs_cc          # python -m unittest discover -s tests
except ImportError:
    from tests.toolchain import ROOT, fresh_station, host_library, load_tool, needs_cc    # python -m unittest tests.<module>

DEVK_TEST, DEVK_INA228, DEVK_MAX17048, DEVK_BQ25798 = 1, 6, 7, 10
DM_BUS_ERROR = 6
# enum power_slot (App/power_config.h)
(BATT_MV, BATT_MA, ENERGY_IN, ENERGY_OUT, CHARGE_IN, CHARGE_OUT, LOAD_MV, LOAD_MA, CHARGER_IN_MV, SOLAR_MV,
 SOLAR_MA, USB_MV, USB_MA) = range(13)
SLOTS = 13
GOOD, PARTIAL, SUSPECT, MISSING, WARMING_UP, FAULT, NOT_FITTED = range(7)
PGOOD, CHG = 0x01, 0x02                       # board_charger_pins() bits (mod_power.h)
ST_POWER_GOOD, ST_CHARGING, ST_FAULT = 0x01, 0x02, 0x04   # charger status byte (spec section 6.3)
NONE_U16, NONE_I16 = 0xFFFF, -32768
MINUTE = 60_000
TICK = 250

# Spec section 9.2: the rail addresses, and the ones an INA228 never takes.
BATTERY, LOAD, SOLAR, USB, GAUGE = 0x40, 0x41, 0x45, 0x48, 0x36
RESERVED = {0x36, 0x44, 0x46, 0x47, 0x50, 0x53, 0x70, 0x71}
SHUNT_UOHM, LSB_UA = 15_000, 10               # nominal (spec section 8.6)
SHUNT_CAL = 131072 * LSB_UA * SHUNT_UOHM // 10**7   # 1966 (SBOS904 eq. 2 in integers)
# App/power_config.h: R_ISET 1 kOhm (R9 behind the 1A jumper, record 1.4), the ISET gain of the 10k/1M
# network (record M2, nominal) and the 20k/10k divider (nominal 3); SLUS810 eq. 3 for K_ISET.
R_ISET, K_ISET, ISET_GAIN_PPM, VIN_DIVIDER = 1000, 400, 990_099, 3


def round_away(a, b):
    """a / b rounded half away from zero (the host model's rounding)."""
    q, r = divmod(abs(a), b)
    return (q + (2 * r >= b)) * (1 if a >= 0 else -1)


def ina_counts(ua):
    """The INA228 CURRENT count of a true current (uA, + VIN+ to VIN-): VSHUNT in 312.5 nV counts, then
    VSHUNT x 4096 / SHUNT_CAL (SBOS904 section 8.1.2), as the host model rounds them."""
    return round_away(round_away(ua * SHUNT_UOHM, 312_500) * 4096, SHUNT_CAL)


def half_up(a, b):
    """a / b rounded half up (ws_div_round, the firmware's rounding)."""
    return (2 * a + b) // (2 * b)


def adc_raw(volts, vdda_mv):
    """The 12-bit result for a pin voltage at this VDDA."""
    return round(volts * 1000 / vdda_mv * 4095)


def iset_pin(v_iset):
    """The PB1 pin voltage for a bq24074 ISET voltage: behind 10 kOhm over 1 MOhm (POWER_ISET_GAIN_PPM)."""
    return v_iset * ISET_GAIN_PPM / 1e6


def sources(profile, mux=0):
    fw = ROOT/'firmware'
    a = fw/'stage0-node/App'
    return [f'-DWS_I2C_MUX={mux}', f'-DWS_POWER_PROFILE={profile}', '-I', fw/'host/include', '-I', fw/'host', '-I', a,
            '-I', fw/'stage0-node/Core/Inc', '-I', fw, '-I', fw/'common', fw/'host/power_harness.c', fw/'host/sim_core.c',
            fw/'host/i2c_sim.c', fw/'host/i2c_models.c', a/'i2c_bus.c', a/'busymon.c', a/'power_acq.c', a/'charger.c', fw/'stage0.c',
            fw/'common/ws_check.c', fw/'common/power_regs.c']


class Bench:
    """A fresh harness with its parts. Window values come from latch()."""
    def __init__(self, test, library, devices, start_ms=0):
        lib = self.lib = fresh_station(test, library)
        lib.h_now_ms.restype = lib.h_window_ms.restype = ctypes.c_uint32
        lib.h_value.restype = ctypes.c_int32
        lib.h_advance.argtypes = lib.h_run.argtypes = [ctypes.c_uint32]
        lib.h_ina228_set.argtypes = [ctypes.c_int, ctypes.c_int32, ctypes.c_int32]
        lib.h_ina228_die.argtypes = [ctypes.c_int, ctypes.c_int32]
        lib.h_max17048_cell.argtypes = lib.h_max17048_rate.argtypes = [ctypes.c_int32]
        lib.h_charger_edges.argtypes = [ctypes.c_uint32]
        lib.h_power_adc.argtypes = [ctypes.c_uint16] * 4
        lib.h_advance(start_ms)
        self.dev = {addr: lib.h_add_device(kind, addr) for kind, addr in devices}
        lib.h_max17048_cell(3_900_000)
        self.adc(iset=0.0, vin=5.0 / VIN_DIVIDER)
        lib.h_charger_pins(PGOOD)
        lib.h_init()

    def adc(self, iset, vin, vdda_mv=3300, iset_raw=None, vin_raw=None):
        """A new ADC sequence: pin volts (or raw counts), VDDA as VREFINT gives it."""
        iset_raw = adc_raw(iset, vdda_mv) if iset_raw is None else iset_raw
        vin_raw = adc_raw(vin, vdda_mv) if vin_raw is None else vin_raw
        self.lib.h_power_adc(iset_raw, vin_raw, 1500, vdda_mv)

    def ina(self, addr, volts, ua):
        self.lib.h_ina228_set(self.dev[addr], round(volts * 1e6), ua)

    def minute(self, ms=MINUTE):
        self.lib.h_run(ms)
        self.lib.h_latch()

    def slot(self, s):
        return self.lib.h_value(s), self.lib.h_count(s), self.lib.h_quality(s)

    def value(self, s):
        return self.lib.h_value(s)

    def quality(self, s):
        return self.lib.h_quality(s)


PHASE_A = [(DEVK_INA228, BATTERY), (DEVK_MAX17048, GAUGE)]
PHASE_B = [(DEVK_INA228, BATTERY), (DEVK_INA228, LOAD), (DEVK_INA228, SOLAR), (DEVK_INA228, USB), (DEVK_MAX17048, GAUGE)]


@needs_cc
class PhaseA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = host_library(cls, 'power-a', *sources(1))._name

    def bench(self, devices=PHASE_A, **kw):
        return Bench(self, self.library, devices, **kw)

    def test_the_rail_table_is_the_phase_a_row(self):
        b = self.bench()
        self.assertEqual(b.lib.h_rail_count(), 1)
        self.assertEqual((b.lib.h_rail_addr(0), b.lib.h_rail_sign(0), b.lib.h_shunt_cal(0)), (BATTERY, -1, SHUNT_CAL))
        self.assertEqual(SHUNT_CAL, 1966)
        fitted = {s for s in range(SLOTS) if b.lib.h_fitted(s)}
        self.assertEqual(fitted, {BATT_MV, BATT_MA, ENERGY_IN, ENERGY_OUT, CHARGE_IN, CHARGE_OUT, LOAD_MV, CHARGER_IN_MV})

    def test_the_first_window_is_partial_and_the_profile_empty_slots_not_fitted(self):
        b = self.bench()
        b.minute()
        self.assertEqual(b.lib.h_first(), 1)
        for s in (BATT_MV, BATT_MA, LOAD_MV, CHARGER_IN_MV, CHARGE_IN):
            self.assertEqual(b.quality(s), PARTIAL, s)
        for s in (LOAD_MA, SOLAR_MV, SOLAR_MA, USB_MV, USB_MA):
            self.assertEqual(b.quality(s), NOT_FITTED, s)
        b.minute()
        self.assertEqual(b.lib.h_first(), 0)
        for s in (BATT_MV, BATT_MA, LOAD_MV, CHARGER_IN_MV, CHARGE_IN, ENERGY_IN):
            self.assertEqual(b.quality(s), GOOD, s)
        self.assertEqual(b.slot(BATT_MV)[1:], (4, GOOD))      # the gauge every 15 s
        self.assertEqual(b.slot(LOAD_MV)[1], 60)              # the rail every 1 s
        self.assertEqual(b.lib.h_window_ms(), MINUTE)

    def live(self, b):
        b.lib.h_live()
        lib = b.lib
        return {'batt_ok': lib.h_live_batt_ok(), 'ma_x100': lib.h_live_batt_ma_x100(), 'out_mv': lib.h_live_out_mv(),
                'gauge_ok': lib.h_live_gauge_ok(), 'vcell_mv': lib.h_live_vcell_mv(), 'soc_x10': lib.h_live_soc_x10(),
                'charging': lib.h_live_charging()}

    def test_the_charger_command_says_not_fitted(self):
        b = self.bench()
        b.lib.h_charger_line.restype = ctypes.c_char_p
        self.assertEqual(b.lib.h_charger_line(400).decode(), '#charger not-fitted (WS_POWER_PROFILE 3 only)')

    def test_power_live_absent_parts(self):
        b = self.bench([])                                    # no INA228, no gauge answering
        b.lib.h_charger_pins(PGOOD)
        b.lib.h_run(20_000)
        self.assertEqual(self.live(b), {'batt_ok': 0, 'ma_x100': 0, 'out_mv': 0, 'gauge_ok': 0, 'vcell_mv': 0,
                                        'soc_x10': 0, 'charging': 0})

    def test_power_live_present_parts(self):
        b = self.bench()
        b.ina(BATTERY, 4.40, -500_000)                        # +500 mA into the cell, OUT at 4.40 V
        b.lib.h_max17048_cell(3_900_000)
        b.lib.h_max17048_soc_256(0x4E66)                      # 78.398 %: 78.4 rounded to 0.1 %
        b.lib.h_charger_pins(PGOOD | CHG)
        b.lib.h_run(20_000)
        want = round(-ina_counts(-500_000) * LSB_UA / 10)     # mA x 100
        self.assertEqual(self.live(b), {'batt_ok': 1, 'ma_x100': want, 'out_mv': 4400, 'gauge_ok': 1, 'vcell_mv': 3900,
                                        'soc_x10': half_up(0x4E66 * 10, 256), 'charging': 1})
        self.assertAlmostEqual(want, 50_000, delta=10)        # the INA228 count quantises 500 mA to 500.02
        self.assertEqual(half_up(0x4E66 * 10, 256), 784)

    def test_power_live_rails_not_fitted_in_phase_a(self):
        # Phase A has no load, solar or USB-C INA228: the screen says so ("--"), never "pending".
        b = self.bench()
        b.ina(BATTERY, 4.40, -500_000)
        b.lib.h_charger_pins(PGOOD | CHG)
        b.lib.h_run(20_000)
        b.lib.h_live()
        self.assertEqual([[b.lib.h_live_rail(k, w) for w in range(4)] for k in range(3)], [[0, 0, 0, 0]] * 3)
        self.assertEqual(b.lib.h_live_charger(), 0x03)   # power good, charging (spec section 6.3)

    def test_power_live_does_not_change_the_window(self):
        def minute(with_live):
            b = self.bench()
            b.ina(BATTERY, 4.1, -300_000)
            for _ in range(MINUTE // TICK):
                b.lib.h_run(TICK)
                if with_live:
                    for _ in range(5):
                        b.lib.h_live()
            b.lib.h_latch()
            return [b.slot(s) for s in range(SLOTS)], b.lib.h_soc()
        self.assertEqual(minute(True), minute(False))

    def test_a_part_that_goes_away_reads_as_absent(self):
        b = self.bench()
        b.ina(BATTERY, 4.40, -500_000)
        b.lib.h_run(20_000)
        self.assertEqual((self.live(b)['batt_ok'], self.live(b)['gauge_ok']), (1, 1))
        b.lib.h_remove_device(b.dev[BATTERY])
        b.lib.h_remove_device(b.dev[GAUGE])
        b.lib.h_run(40_000)
        w = self.live(b)
        self.assertEqual((w['batt_ok'], w['ma_x100'], w['out_mv'], w['gauge_ok'], w['vcell_mv']), (0, 0, 0, 0, 0))

    def test_a_current_from_vin_plus_to_vin_minus_is_a_discharge(self):
        """Spec section 3.1: CELL+ on VIN+, the charger's BATT socket on VIN-, so the part's positive count is
        out of the cell; the firmware sign is -1 and the charge goes to charge out."""
        b = self.bench()
        b.ina(BATTERY, 4.0, 500_000)
        b.minute()
        b.minute()
        b.minute()
        self.assertEqual(b.slot(BATT_MA), (-500, 60, GOOD))
        self.assertEqual(b.value(CHARGE_IN), 0)
        self.assertGreaterEqual(b.value(CHARGE_OUT), 24)      # 500 mA for about 3 min: 24.6 mAh
        self.assertEqual(b.value(ENERGY_IN), 0)
        self.assertGreater(b.value(ENERGY_OUT), 0)

    def test_steady_charge_and_discharge_means(self):
        b = self.bench()
        b.ina(BATTERY, 4.2, -500_000)                         # +500 mA into the cell
        b.minute()
        b.minute()
        self.assertEqual(b.slot(BATT_MA), (round(-ina_counts(-500_000) * LSB_UA / 1000), 60, GOOD))
        self.assertEqual(b.value(BATT_MA), 500)
        b.ina(BATTERY, 4.0, 250_000)                          # -250 mA out of the cell
        b.minute()
        b.minute()
        self.assertEqual(b.slot(BATT_MA), (-250, 60, GOOD))

    def test_a_burst_between_samples_gives_the_exact_mean(self):
        """The CHARGE accumulator integrates every conversion, so a radio burst that ends between two
        1 s reads is in the mean (spec section 9.4)."""
        b = self.bench()
        base, burst = 100_000, 3_000_000                      # discharge 100 mA, then 3 A for 200 ms
        b.ina(BATTERY, 3.9, base)
        b.minute()
        b.lib.h_run(30_000)
        b.lib.h_advance(25)                                   # between two ticks: no read in it
        b.ina(BATTERY, 3.9, burst)
        b.lib.h_advance(200)
        b.ina(BATTERY, 3.9, base)
        b.lib.h_advance(25)
        b.minute(MINUTE - 30_250)
        counts_ms = ina_counts(base) * (MINUTE - 200) + ina_counts(burst) * 200
        expected = -half_up(counts_ms * LSB_UA, MINUTE * 1000)   # uA ms / ms -> uA, then mA
        self.assertEqual(b.lib.h_window_ms(), MINUTE)
        self.assertEqual(b.slot(BATT_MA), (expected, 60, GOOD))
        self.assertEqual(expected, -110)
        self.assertNotEqual(expected, -round(ina_counts(base) * LSB_UA / 1000))

    def test_a_part_reset_mid_window_gives_partial_not_wrong(self):
        b = self.bench()
        b.ina(BATTERY, 4.1, -800_000)
        b.minute()
        b.lib.h_run(20_000)
        b.lib.h_ina228_power_cycle(b.dev[BATTERY])            # SHUNT_CAL and CHARGE back to their reset values
        b.minute(40_000)
        value, count, quality = b.slot(BATT_MA)
        self.assertEqual((value, quality), (800, PARTIAL))
        self.assertLess(count, 60)
        self.assertEqual(b.quality(CHARGE_IN), PARTIAL)
        b.minute()
        self.assertEqual(b.slot(BATT_MA), (800, 60, GOOD))

    def test_a_part_reset_drops_the_live_values(self):
        # SHUNT_CAL reads back 0: the live current is from before the reset, so the screen shows NO INA228
        # until a step after the calibration again, never the old current as live (OUT is read afresh).
        b = self.bench()
        b.ina(BATTERY, 4.40, -800_000)
        b.lib.h_run(20_000)
        self.assertEqual(self.live(b)['batt_ok'], 1)
        b.lib.h_ina228_power_cycle(b.dev[BATTERY])
        b.ina(BATTERY, 4.40, -200_000)
        seen = []
        for _ in range(3_000 // TICK):
            b.lib.h_run(TICK)
            w = self.live(b)
            seen.append((w['batt_ok'], w['ma_x100'], w['out_mv']))
        oks = [ok for ok, _, _ in seen]
        self.assertIn(0, oks, seen)
        gone = oks.index(0)
        self.assertTrue(all(ok == 0 or abs(ma - 20_000) < 100 for ok, ma, _ in seen[gone:]), seen)
        self.assertEqual(seen[-1][0], 1)

    def test_out_and_the_cell_are_kept_apart(self):
        """Spec section 3.2: the battery voltage is the gauge's VCELL; the battery INA228's VBUS (on OUT)
        is the load voltage."""
        b = self.bench()
        b.ina(BATTERY, 4.40, -300_000)
        b.lib.h_max17048_cell(3_900_000)
        b.minute()
        b.minute()
        self.assertEqual(b.slot(BATT_MV), (3900, 4, GOOD))
        self.assertEqual(b.slot(LOAD_MV), (4400, 60, GOOD))

    def test_no_gauge_means_no_battery_voltage_even_with_the_ina228(self):
        b = self.bench([(DEVK_INA228, BATTERY)])
        b.ina(BATTERY, 4.40, -300_000)
        b.minute()
        b.minute()
        self.assertEqual(b.quality(BATT_MV), MISSING)
        self.assertEqual(b.slot(LOAD_MV), (4400, 60, GOOD))
        self.assertEqual((b.lib.h_soc(), b.lib.h_soc_rate()), (NONE_U16, NONE_I16))

    def test_energy_is_charge_times_the_cell_voltage(self):
        b = self.bench()
        b.ina(BATTERY, 4.40, -1_000_000)                      # 1 A into the cell; OUT 4.40 V, cell 3.90 V
        b.lib.h_max17048_cell(3_900_000)
        for _ in range(7):
            b.minute()
        charge, energy = b.value(CHARGE_IN), b.value(ENERGY_IN)
        self.assertEqual(b.quality(ENERGY_IN), GOOD)
        self.assertGreaterEqual(charge, 115)                  # about 7 min at 1 A: 116.7 mAh, less the base step
        self.assertLessEqual(abs(energy - charge * 3.9), 4)   # mWh = mAh x 3.9 V (each truncated)
        self.assertGreater(abs(energy - charge * 4.4), 50)    # not OUT x I
        self.assertEqual((b.value(ENERGY_OUT), b.value(CHARGE_OUT)), (0, 0))

    def test_energy_is_missing_when_the_cell_voltage_is_stale_while_the_charge_counts(self):
        """Spec sections 5.2 and 9.4: a step with charge and no fresh VCELL adds its charge and no energy,
        and both energy slots are missing for that window (fields 13 and 14 INVALID)."""
        b = self.bench()
        b.ina(BATTERY, 4.40, -1_000_000)
        b.minute()
        b.minute()
        self.assertEqual(b.quality(ENERGY_IN), GOOD)
        energy, charge = b.value(ENERGY_IN), b.value(CHARGE_IN)
        b.lib.h_remove_device(b.dev[GAUGE])
        for _ in range(3):
            b.minute()
            self.assertEqual((b.quality(ENERGY_IN), b.quality(ENERGY_OUT)), (MISSING, MISSING))
            self.assertEqual(b.quality(CHARGE_IN), GOOD)
            self.assertEqual(b.quality(BATT_MV), MISSING)
        self.assertGreaterEqual(b.value(CHARGE_IN), charge + 49)   # 3 min at 1 A: 50 mAh
        self.assertLessEqual(b.value(ENERGY_IN), energy + 65)      # at most the step before the removal
        b.lib.h_restore_device(b.dev[GAUGE])
        b.minute()
        b.minute()
        self.assertEqual(b.quality(ENERGY_IN), GOOD)

    def test_a_bus_fault_is_fault_and_an_absent_part_missing(self):
        b = self.bench()
        b.minute()
        b.lib.h_device_mode(b.dev[BATTERY], DM_BUS_ERROR, 0, 0)
        b.minute()
        b.minute()
        self.assertEqual(b.quality(BATT_MA), FAULT)
        self.assertEqual(b.quality(LOAD_MV), FAULT)
        b2 = self.bench([(DEVK_MAX17048, GAUGE)])
        b2.minute()
        b2.minute()
        for s in (BATT_MA, LOAD_MV, CHARGE_IN, ENERGY_IN):
            self.assertEqual(b2.quality(s), MISSING, s)
        self.assertEqual(b2.lib.h_monitor_temp(), NONE_I16)

    def test_iset_with_vdda_scaling(self):
        """SLUS810 eq. 3: I = 400 x V_ISET / R_ISET (2.5 V at 1 kOhm is 1.000 A), V_ISET the pin over the
    10k/1M gain; the pin volts scale with VDDA from VREFINT."""
        b = self.bench()
        b.lib.h_charger_pins(PGOOD | CHG)
        b.adc(iset=iset_pin(2.5), vin=5.0 / 3)
        b.minute()
        self.assertEqual(b.lib.h_chg_batt_ma(), 1000)
        self.assertEqual(b.lib.h_vdda(), 3300)
        b.adc(iset=iset_pin(2.5), vin=5.0 / 3, vdda_mv=3000)          # the same pin volts at a lower VDDA
        b.minute()
        self.assertEqual(b.lib.h_chg_batt_ma(), 1000)
        self.assertEqual(b.lib.h_vdda(), 3000)
        self.assertEqual(b.value(CHARGER_IN_MV), 5000)

    def test_iset_is_0_ma_while_pgood_is_deasserted(self):
        b = self.bench()
        b.lib.h_charger_pins(0)
        b.adc(iset=iset_pin(2.5), vin=0.0)
        b.minute()
        self.assertEqual(b.lib.h_chg_batt_ma(), 0)
        b.adc(iset=0.0, vin=0.0, iset_raw=4085)               # clipped, but no input: still 0 mA
        b.minute()
        self.assertEqual(b.lib.h_chg_batt_ma(), 0)

    def test_a_partially_clipped_result_is_out_of_range(self):
        """Spec section 9.5: with x16 oversampling an input just above full scale averages to 4090-4094,
        so a result >= 4080 is out of range: charger input INVALID, ISET none."""
        b = self.bench()
        b.lib.h_charger_pins(PGOOD | CHG)
        b.minute()
        b.adc(iset=iset_pin(2.5), vin=0.0, vin_raw=4085)
        b.minute()
        self.assertEqual(b.quality(CHARGER_IN_MV), MISSING)
        self.assertEqual(b.lib.h_chg_batt_ma(), 1000)
        b.adc(iset=0.0, vin=5.0 / 3, iset_raw=4085)
        b.minute()
        self.assertEqual(b.slot(CHARGER_IN_MV), (5000, 60, GOOD))
        self.assertEqual(b.lib.h_chg_batt_ma(), NONE_I16)
        b.adc(iset=0.0, vin=0.0, vin_raw=4079)                # just under the limit: 3 x VDDA x 4079 / 4095
        b.minute()
        self.assertEqual(b.slot(CHARGER_IN_MV), (half_up(4079 * 3300 * 1000 // 4095 * 3, 1000), 60, GOOD))

    def test_a_stalled_adc_is_missing_not_its_last_values(self):
        """Spec section 9.6: a sequence already sampled is no sample. With the ADC stalled (its interrupt
        stopped, or every start refused) board_power_adc() keeps returning its last sequence: the charger
        input is missing and VDDA and the charger's battery current are none, not the last values."""
        b = self.bench()
        b.lib.h_charger_pins(PGOOD | CHG)
        b.adc(iset=iset_pin(2.5), vin=5.0 / 3)
        b.minute()                                            # the first window is partial
        b.minute()
        self.assertEqual(b.slot(CHARGER_IN_MV), (5000, 60, GOOD))
        b.lib.h_power_adc_stall(1)
        b.minute()
        self.assertEqual((b.value(CHARGER_IN_MV), b.lib.h_count(CHARGER_IN_MV)), (0, 0))
        self.assertEqual(b.quality(CHARGER_IN_MV), MISSING)
        self.assertEqual((b.lib.h_vdda(), b.lib.h_chg_batt_ma()), (NONE_U16, NONE_I16))
        b.lib.h_power_adc_stall(0)                            # the sequences run again: good from the next one
        b.minute()
        self.assertEqual(b.slot(CHARGER_IN_MV), (5000, 60, GOOD))
        self.assertEqual((b.lib.h_vdda(), b.lib.h_chg_batt_ma()), (3300, 1000))

    def test_a_sequence_is_sampled_once(self):
        """A sequence that is still the latest at the next 1 s sample (a refused start) is not counted
        again: a window where only every other sample is new counts 30 of 60, partial."""
        b = self.bench()
        b.minute()
        for _ in range(30):
            b.lib.h_power_adc_stall(0)
            b.lib.h_run(1_000)
            b.lib.h_power_adc_stall(1)
            b.lib.h_run(1_000)
        b.lib.h_latch()
        self.assertEqual(b.lib.h_count(CHARGER_IN_MV), 30)
        self.assertEqual(b.quality(CHARGER_IN_MV), PARTIAL)

    def test_chg_steady_is_charging(self):
        b = self.bench()
        b.lib.h_charger_pins(PGOOD | CHG)
        b.minute()
        self.assertEqual(b.lib.h_status(), ST_POWER_GOOD | ST_CHARGING)
        b.lib.h_charger_pins(PGOOD)
        b.minute()
        self.assertEqual(b.lib.h_status(), ST_POWER_GOOD)

    def test_chg_flashing_is_a_fault_that_clears_after_4_s(self):
        """SLUS810 section 9.3.5.6: CHG flashes at about 2 Hz on a fault; 3 or more edges within 2 s."""
        b = self.bench()
        b.lib.h_charger_pins(PGOOD | CHG)
        b.lib.h_run(10_000)
        edges = 0
        for _ in range(20):                                   # 2 Hz: an edge every 250 ms for 5 s
            edges += 1
            b.lib.h_charger_edges(edges)
            b.lib.h_charger_pins(PGOOD | (CHG if edges % 2 else 0))
            b.lib.h_run(TICK)
        b.lib.h_latch()
        self.assertEqual(b.lib.h_status(), ST_POWER_GOOD | ST_FAULT)
        b.lib.h_charger_pins(PGOOD | CHG)
        b.lib.h_run(3_000)
        b.lib.h_latch()
        self.assertEqual(b.lib.h_status(), ST_POWER_GOOD | ST_FAULT)   # less than 4 s without an edge
        b.lib.h_run(1_500)
        b.lib.h_latch()
        self.assertEqual(b.lib.h_status(), ST_POWER_GOOD | ST_CHARGING)

    def test_two_edges_are_not_a_fault(self):
        b = self.bench()
        b.lib.h_charger_pins(PGOOD)
        b.lib.h_run(5_000)
        b.lib.h_charger_edges(2)                              # charging started and ended
        b.lib.h_run(2_000)
        b.lib.h_latch()
        self.assertEqual(b.lib.h_status(), ST_POWER_GOOD)

    def test_chg_without_pgood_is_kept(self):
        b = self.bench()
        b.lib.h_charger_pins(CHG)
        b.minute()
        self.assertEqual(b.lib.h_status(), ST_CHARGING)       # bit 1 set, bit 0 clear, stage and input 0

    def test_the_slow_gauge_and_die_values(self):
        b = self.bench()
        b.lib.h_max17048_soc_256(0x4E66)                      # 78.398 %
        b.lib.h_max17048_rate(-624)                           # -0.624 %/h
        b.lib.h_ina228_die(b.dev[BATTERY], 41_300)
        b.minute()
        self.assertEqual((b.lib.h_soc(), b.lib.h_soc_rate(), b.lib.h_monitor_temp()), (0x4E66, -6, 413))
        b.lib.h_max17048_rate(1_248)
        b.minute()
        self.assertEqual(b.lib.h_soc_rate(), 12)

    def test_the_schedule_survives_the_clock_wrap(self):
        """A warm reset leaves the board clock anywhere in its 49-day range (App/clock.h)."""
        b = self.bench(start_ms=2**32 - 70_000)
        b.ina(BATTERY, 4.0, -500_000)
        b.minute()
        b.minute()
        b.minute()
        self.assertLess(b.lib.h_now_ms(), 2**31)
        self.assertEqual(b.slot(BATT_MA), (500, 60, GOOD))
        self.assertEqual(b.slot(BATT_MV), (3900, 4, GOOD))


@needs_cc
class PhaseB(unittest.TestCase):
    """Four INA228 rails on the bq24074 (spec sections 2, 9.2, 9.3): the table needs no redesign."""
    @classmethod
    def setUpClass(cls):
        cls.library = host_library(cls, 'power-b', *sources(2))._name

    def test_the_rail_table(self):
        b = Bench(self, self.library, PHASE_B)
        lib = b.lib
        rows = [(lib.h_rail_addr(i), lib.h_rail_sign(i), lib.h_shunt_cal(i)) for i in range(lib.h_rail_count())]
        self.assertEqual(rows, [(BATTERY, -1, SHUNT_CAL), (LOAD, 1, SHUNT_CAL), (SOLAR, 1, SHUNT_CAL), (USB, 1, SHUNT_CAL)])
        addrs = [r[0] for r in rows]
        self.assertEqual(len(set(addrs)), 4)
        self.assertFalse(set(addrs) & RESERVED)
        self.assertTrue(all(lib.h_fitted(s) for s in range(SLOTS)))

    def test_power_live_rails(self):
        # The screen's load, solar and USB-C rows: each fitted rail's latest step and VBUS; the absent solar
        # part is fitted but not ok (the screen's "pending"), its values 0.
        b = Bench(self, self.library, [d for d in PHASE_B if d[1] != SOLAR])
        b.ina(LOAD, 4.38, 120_000)
        b.ina(USB, 5.05, 830_000)
        b.lib.h_charger_pins(PGOOD)
        b.lib.h_run(20_000)
        b.lib.h_live()
        rails = [[b.lib.h_live_rail(k, w) for w in range(4)] for k in range(3)]
        self.assertEqual([r[:2] for r in rails], [[1, 1], [1, 0], [1, 1]])
        self.assertAlmostEqual(rails[0][2], 12_000, delta=10)   # 120 mA in 0.01 mA
        self.assertAlmostEqual(rails[2][2], 83_000, delta=10)
        self.assertEqual((rails[0][3], rails[1][2:], rails[2][3]), (4380, [0, 0], 5050))
        self.assertEqual(b.lib.h_live_charger(), 0x01)          # power good, not charging

    def test_four_rails_and_one_absent(self):
        b = Bench(self, self.library, [d for d in PHASE_B if d[1] != SOLAR])
        b.ina(BATTERY, 4.40, -700_000)                        # its VBUS on OUT is not read in phase B
        b.ina(LOAD, 4.38, 120_000)
        b.ina(USB, 5.05, 830_000)
        for addr, mc in ((BATTERY, 30_000), (LOAD, 36_500), (USB, 33_000)):
            b.lib.h_ina228_die(b.dev[addr], mc)
        b.minute()
        b.minute()
        self.assertEqual(b.slot(BATT_MA), (700, 60, GOOD))
        self.assertEqual(b.slot(BATT_MV), (3900, 4, GOOD))
        self.assertEqual(b.slot(LOAD_MV), (4380, 60, GOOD))
        self.assertEqual(b.slot(LOAD_MA), (120, 60, GOOD))
        self.assertEqual(b.slot(USB_MV), (5050, 60, GOOD))
        self.assertEqual(b.slot(USB_MA), (830, 60, GOOD))
        self.assertEqual((b.quality(SOLAR_MV), b.quality(SOLAR_MA)), (MISSING, MISSING))
        self.assertEqual(b.lib.h_monitor_temp(), 365)         # the hottest of the fitted rails
        self.assertEqual(b.lib.h_addr_transfers(SOLAR) > 0, True)
        self.assertEqual(b.quality(ENERGY_IN), GOOD)


# The BQ25798 (TI SLUSDV2C section 7.5.1), from the datasheet: VREG REG01-02 in 10 mV (table 7-15), ICHG
# REG03-04 in 10 mA (table 7-16), CELL REG0A bits 7:6 (table 7-21), EN_CHG REG0F bit 5 (table 7-25), the
# watchdog REG10 (table 7-26: 40 s by default, WD_RST bit 3), TS REG1F bits 3:0 COLD COOL WARM HOT
# (table 7-40), TS ADC 100/1024 % a count (table 7-65). App/power_config.h: one cell, 0.9 A, 4.2 V.
CHARGER = 0x6B
VREG_CODE, ICHG_CODE, ICHG_POR = 4200 // 10, 900 // 10, 1000 // 10
ITERM_CODE, ITERM_POR = 2, 5          # REG09 bits 4:0 in 40 mA: 80 mA (nearest 90 mA) and the 200 mA default
EN_CHG = 0x20
TS_COLD, TS_COOL, TS_WARM, TS_HOT = 0x08, 0x04, 0x02, 0x01
(CH_NONE, CH_ABSENT, CH_PART, CH_CELLS, CH_READBACK, CH_TS_STALE, CH_TS_COLD, CH_TS_HOT) = range(8)   # charger.h
CHG_PRESENT, CHG_OK, CHG_CONFIGURED, CHG_HOLD, CHG_APPLIES, CHG_RESETS, CHG_FAILURES = range(7)       # h_chg()
POLL = 5_000                                  # CHARGER_PERIOD_MS
STAGE_PRECHARGE, STAGE_CC, STAGE_CV, STAGE_NOT_CHARGING = 1, 2, 3, 6   # spec section 6.3, bits 3-5
INPUT_SOLAR, INPUT_USB_C, INPUT_NONE = 1, 2, 3                       # bits 6-7
PHASE_C = [(DEVK_INA228, BATTERY), (DEVK_MAX17048, GAUGE), (DEVK_BQ25798, CHARGER)]


def status(pg=0, charging=0, fault=0, stage=0, inp=0):
    return pg | charging << 1 | fault << 2 | stage << 3 | inp << 6


@needs_cc
class PhaseC(unittest.TestCase):
    """The BQ25798 of the TX stack (hardware/tx-stack-r1, issue #34): the set-up at every start and after
    every chip reset, the charge gate, the readings in the existing slots, the CHARGER console line."""
    @classmethod
    def setUpClass(cls):
        cls.library = host_library(cls, 'power-c', *sources(3, mux=1))._name

    def bench(self, devices=PHASE_C, **kw):
        b = Bench(self, self.library, devices, **kw)
        lib = b.lib
        lib.h_bq_set.argtypes = [ctypes.c_int] + [ctypes.c_int32] * 5
        lib.h_bq_ts.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_int]
        lib.h_bq_cells.argtypes = [ctypes.c_int, ctypes.c_uint]
        lib.h_bq_status.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_int, ctypes.c_int]
        lib.h_bq_die.argtypes = [ctypes.c_int, ctypes.c_int32]
        lib.h_bq_limit_writes.restype = lib.h_bq_kicks.restype = lib.h_bq_reg_resets.restype = ctypes.c_uint32
        lib.h_charger_line.restype = ctypes.c_char_p
        lib.h_charger_line.argtypes = [ctypes.c_uint]
        b.bq = b.dev.get(CHARGER)
        return b

    def reg16(self, b, reg):
        return b.lib.h_bq_reg(b.bq, reg) << 8 | b.lib.h_bq_reg(b.bq, reg + 1)

    def en_chg(self, b):
        return bool(b.lib.h_bq_reg(b.bq, 0x0F) & EN_CHG)

    def line(self, b, length=416):
        return b.lib.h_charger_line(length).decode()

    def fields(self, b):
        return dict(kv.split('=', 1) for kv in self.line(b).split()[1:])

    def test_the_rail_table_and_the_slots_the_charger_fills(self):
        b = self.bench()
        self.assertEqual((b.lib.h_rail_count(), b.lib.h_rail_addr(0), b.lib.h_rail_sign(0)), (1, BATTERY, -1))
        fitted = {s for s in range(SLOTS) if b.lib.h_fitted(s)}
        self.assertEqual(fitted, {BATT_MV, BATT_MA, ENERGY_IN, ENERGY_OUT, CHARGE_IN, CHARGE_OUT, LOAD_MV, CHARGER_IN_MV})

    def test_the_boot_write_and_its_read_back(self):
        b = self.bench()
        self.assertEqual(self.reg16(b, 0x03), ICHG_POR)          # the 1 A default before the firmware runs
        b.lib.h_run(TICK)                                        # the first poll
        self.assertEqual(self.reg16(b, 0x01), VREG_CODE)
        self.assertEqual(self.reg16(b, 0x03), ICHG_CODE)
        self.assertEqual(b.lib.h_bq_reg(b.bq, 0x0A) >> 6, 0)     # CELL: one cell, untouched
        self.assertEqual(b.lib.h_bq_limit_writes(b.bq), 4)       # one 4-byte write, REG01 to REG04
        self.assertEqual([b.lib.h_chg(k) for k in (CHG_PRESENT, CHG_OK, CHG_CONFIGURED, CHG_APPLIES, CHG_RESETS)],
                         [1, 1, 1, 1, 0])
        # No TS reading yet: charge stays off until the first conversion is in.
        self.assertEqual(b.lib.h_chg(CHG_HOLD), CH_TS_STALE)
        self.assertFalse(self.en_chg(b))
        b.lib.h_run(POLL)
        self.assertEqual(b.lib.h_chg(CHG_HOLD), CH_NONE)
        self.assertTrue(self.en_chg(b))
        self.assertEqual(b.lib.h_bq_limit_writes(b.bq), 4)       # held: never written again

    def test_iterm_is_written_with_the_limits_and_read_back(self):
        b = self.bench()
        self.assertEqual(b.lib.h_bq_reg(b.bq, 0x09) & 0x1F, ITERM_POR)
        b.lib.h_run(TICK)
        reg09 = b.lib.h_bq_reg(b.bq, 0x09)
        self.assertEqual(reg09 & 0x1F, ITERM_CODE)
        self.assertEqual(reg09 & 0x20, 0)                        # STOP_WD_CHG kept as read
        self.assertEqual(b.lib.h_bq_reg_resets(b.bq), 0)         # REG_RST never written
        self.assertEqual(b.lib.h_chg(CHG_CONFIGURED), 1)
        self.assertEqual(self.fields(b)['iterm_ma'], '80')
        b.lib.h_run(20_000)
        b.lib.h_bq_watchdog_expire(b.bq)                         # ITERM back to 200 mA with ICHG
        self.assertEqual(b.lib.h_bq_reg(b.bq, 0x09) & 0x1F, ITERM_POR)
        b.lib.h_run(POLL)
        self.assertEqual(b.lib.h_bq_reg(b.bq, 0x09) & 0x1F, ITERM_CODE)
        self.assertEqual((b.lib.h_chg(CHG_APPLIES), b.lib.h_chg(CHG_RESETS)), (2, 1))
        self.assertEqual(b.lib.h_bq_reg_resets(b.bq), 0)

    def test_the_iterm_code_rounds_to_40_ma_steps_and_clamps(self):
        b = self.bench()
        code = b.lib.bq25798_iterm_code
        code.argtypes, code.restype = [ctypes.c_uint16], ctypes.c_uint8
        self.assertEqual([code(ma) for ma in (0, 40, 59, 60, 90, 99, 100, 1000, 5000)], [1, 1, 1, 2, 2, 2, 3, 25, 25])

    def test_the_watchdog_is_kept_and_the_set_up_holds(self):
        b = self.bench()
        b.lib.h_run(120_000)                                     # three 40 s watchdog periods
        self.assertGreaterEqual(b.lib.h_bq_kicks(b.bq), 120_000 // POLL - 1)
        self.assertFalse(b.lib.h_bq_reg(b.bq, 0x1B) & 0x20)      # WD_STAT: still host mode
        self.assertEqual(self.reg16(b, 0x03), ICHG_CODE)
        self.assertEqual((b.lib.h_chg(CHG_APPLIES), b.lib.h_chg(CHG_RESETS)), (1, 0))

    def test_a_chip_reset_is_seen_and_the_set_up_applied_again(self):
        b = self.bench()
        b.lib.h_run(20_000)
        b.lib.h_bq_watchdog_expire(b.bq)                         # ICHG back to 1 A, EN_CHG to 1
        self.assertEqual(self.reg16(b, 0x03), ICHG_POR)
        b.lib.h_run(POLL)
        self.assertEqual(self.reg16(b, 0x03), ICHG_CODE)
        self.assertEqual((b.lib.h_chg(CHG_APPLIES), b.lib.h_chg(CHG_RESETS)), (2, 1))
        b.lib.h_bq_power_cycle(b.bq)                             # a power-on reset: every register
        b.lib.h_run(POLL)
        self.assertEqual((self.reg16(b, 0x01), self.reg16(b, 0x03)), (VREG_CODE, ICHG_CODE))
        self.assertEqual((b.lib.h_chg(CHG_APPLIES), b.lib.h_chg(CHG_RESETS)), (3, 2))
        self.assertTrue(self.en_chg(b))                          # the TS reading from before is 5 s old: fresh

    def test_ts_out_of_band_keeps_charge_disabled(self):
        for bits, hold in ((TS_COLD, CH_TS_COLD), (TS_HOT, CH_TS_HOT)):
            with self.subTest(bits=bits):
                b = self.bench()
                b.lib.h_bq_status(b.bq, 1, 0, 3, 0, 0)           # USB in, the chip would charge in CC
                b.lib.h_bq_ts(b.bq, 800 if bits == TS_COLD else 150, bits)
                b.lib.h_run(30_000)
                self.assertEqual(b.lib.h_chg(CHG_HOLD), hold)
                self.assertFalse(self.en_chg(b))
                st = b.lib.h_chg_status_byte()
                self.assertEqual(st & 0x3F, status(pg=1, stage=STAGE_NOT_CHARGING))   # no fault: a temperature
                f = self.fields(b)
                self.assertEqual((f['ts'], f['en_chg'], f['hold']), ('COLD' if bits == TS_COLD else 'HOT', '0',
                                                                     'ts-cold' if bits == TS_COLD else 'ts-hot'))
                b.lib.h_bq_ts(b.bq, 520, 0)                      # back to normal: charge on at the next poll
                b.lib.h_run(2 * POLL)
                self.assertEqual(b.lib.h_chg(CHG_HOLD), CH_NONE)
                self.assertTrue(self.en_chg(b))

    def test_cool_and_warm_still_charge(self):
        for bits in (TS_COOL, TS_WARM):
            with self.subTest(bits=bits):
                b = self.bench()
                b.lib.h_bq_ts(b.bq, 600, bits)
                b.lib.h_run(15_000)
                self.assertEqual(b.lib.h_chg(CHG_HOLD), CH_NONE)
                self.assertTrue(self.en_chg(b))

    def test_no_ts_reading_keeps_charge_disabled(self):
        b = self.bench()
        b.lib.h_bq_set(b.bq, 0, 0, 0, 0, 0)                      # no VBUS, no VBAT: the ADC never converts
        b.lib.h_run(30_000)
        self.assertEqual(b.lib.h_chg(CHG_HOLD), CH_TS_STALE)
        self.assertFalse(self.en_chg(b))
        self.assertEqual(self.fields(b)['ts_pct'], 'none')

    def test_another_cell_count_or_a_bad_read_back_is_a_fault_and_no_charge(self):
        b = self.bench()
        b.lib.h_bq_cells(b.bq, 2)
        b.lib.h_bq_power_cycle(b.bq)                             # the PROG strap says two cells
        b.lib.h_run(15_000)
        self.assertEqual(b.lib.h_chg(CHG_HOLD), CH_CELLS)
        self.assertFalse(self.en_chg(b))
        self.assertTrue(b.lib.h_chg_status_byte() & ST_FAULT)
        b = self.bench()
        b.lib.h_bq_ignore_limits(b.bq, 1)                        # the writes never land
        b.lib.h_run(15_000)
        self.assertEqual((b.lib.h_chg(CHG_HOLD), b.lib.h_chg(CHG_CONFIGURED)), (CH_READBACK, 0))
        self.assertFalse(self.en_chg(b))
        self.assertTrue(b.lib.h_chg_status_byte() & ST_FAULT)

    def test_an_absent_charger_has_no_status(self):
        b = self.bench(PHASE_A)
        b.minute()
        self.assertEqual(b.lib.h_status(), 0xFF)
        self.assertEqual(b.lib.h_chg(CHG_HOLD), CH_ABSENT)
        self.assertEqual((b.lib.h_chg_input_mv(), b.lib.h_chg_batt_ma(), b.lib.h_chg_temp()), (NONE_U16, NONE_I16, NONE_I16))
        self.assertEqual(b.quality(CHARGER_IN_MV), MISSING)
        self.assertEqual(self.fields(b)['present'], '0')

    def test_the_readings_fill_the_existing_slots(self):
        b = self.bench()
        b.lib.h_bq_set(b.bq, 5050, 640, 3950, 850, 4010)         # USB in, 850 mA into the pack
        b.lib.h_bq_die(b.bq, 415)
        b.lib.h_bq_status(b.bq, 1, 0, 3, 0, 0)                   # VAC1 (USB-C, J6), fast charge
        b.minute()
        b.minute()
        self.assertEqual(b.slot(CHARGER_IN_MV), (5050, 12, GOOD))   # VBUS, one read a poll
        self.assertEqual(b.slot(LOAD_MV), (4010, 12, GOOD))         # VSYS: the load rail
        self.assertEqual((b.lib.h_chg_batt_ma(), b.lib.h_chg_input_mv(), b.lib.h_chg_input_ma(), b.lib.h_chg_batt_mv()),
                         (850, 5050, 640, 3950))
        self.assertEqual(b.lib.h_chg_temp(), 415)                   # 0.5 degC counts, in 0.1 degC
        self.assertEqual(b.lib.h_status(), status(pg=1, charging=1, stage=STAGE_CC, inp=INPUT_USB_C))
        b.lib.h_bq_status(b.bq, 0, 1, 4, 0, 0)                   # solar only, CV
        b.minute()
        self.assertEqual(b.lib.h_status(), status(pg=1, charging=1, stage=STAGE_CV, inp=INPUT_SOLAR))
        b.lib.h_bq_status(b.bq, 1, 0, 3, 0x40, 0)                # VBUS_OVP (REG20 bit 6)
        b.minute()
        self.assertTrue(b.lib.h_status() & ST_FAULT)

    def test_the_console_line(self):
        b = self.bench()
        b.lib.h_bq_status(b.bq, 1, 0, 3, 0, 0)
        b.lib.h_run(2 * POLL + TICK)                             # charge on at the second poll, seen at the third
        line = self.line(b)
        self.assertTrue(line.startswith('#charger '))
        f = self.fields(b)
        want = {'present': '1', 'ok': '1', 'reg48': '0x19', 'reg0a': '0x23', 'cells': '1', 'reg01_02': '0x01a4',
                'vreg_mv': '4200', 'reg03_04': '0x005a', 'ichg_ma': '900', 'ts': 'NORMAL', 'chg_stat': '3',
                'stage': 'cc', 'en_chg': '1', 'hold': 'none', 'pg': '1', 'wd': '0', 'fault0': '0x00', 'fault1': '0x00',
                'vbus_mv': '5000', 'vsys_mv': '3600', 'applies': '1', 'resets': '0', 'failures': '0'}
        self.assertEqual({k: f.get(k) for k in want}, want)
        # TS 52.0 %: the model's 520 permille is ADC count 532, which is 51.95 %, rounded to 0.1 %.
        self.assertEqual(f['ts_pct'], '52.0')
        self.assertLess(len(line), 400)
        self.assertEqual(len(self.line(b, 20)), 19)              # truncated to the buffer, terminated

    def test_the_charger_part_number_is_checked(self):
        # Another part at 0x6B: the test device's REG48 reads 0x48, PN 1 (not 3).
        b = self.bench([(DEVK_INA228, BATTERY), (DEVK_MAX17048, GAUGE), (DEVK_TEST, CHARGER)])
        b.lib.h_run(15_000)
        self.assertEqual((b.lib.h_chg(CHG_PRESENT), b.lib.h_chg(CHG_HOLD)), (0, CH_PART))
        self.assertEqual(b.lib.h_chg_status_byte(), 0xFF)


@needs_cc
class KnownAnswers(unittest.TestCase):
    """One table of reference values, checked against the shared C conversions (firmware/common/
    power_regs.c), the node's driver (power_acq.c) and the bench logger (tools/benchlink_log.py), so the
    node, the bench tool and the logger read a part the same way (spec section 14)."""
    # (name, raw, expected): raws from the datasheets' register scales.
    VCELL = (49_920, 3_900_000)          # MAX17048 VCELL, 78.125 uV a count
    SOC = (0x4E66, 78_398)               # 1/256 %: 78.398 %
    CRATE = (0xFFFD, -624)               # 0.208 %/h a count
    DIETEMP = (3085, 24_101)             # INA228, 7.8125 m degC a count
    ISET = (2_500_000, 1_000_000)        # V_ISET (uV) -> charge current (uA) at R_ISET 1000 ohm
    ISHUNT = (24_000 << 4, 500_000)      # INA228 VSHUNT register image (24,000 counts at 15 mOhm) -> uA

    @classmethod
    def setUpClass(cls):
        cls.library = host_library(cls, 'power-kat', *sources(1))._name
        cls.log = load_tool('benchlink_log')

    def test_the_c_conversions(self):
        lib = ctypes.CDLL(self.library)
        lib.max17048_vcell_uv.argtypes = lib.max17048_soc_mpct.argtypes = lib.max17048_crate_mpct_h.argtypes = [ctypes.c_uint16]
        lib.ina228_dietemp_mc.argtypes = [ctypes.c_uint16]
        lib.iset_charge_ua.argtypes = [ctypes.c_int32, ctypes.c_uint32]
        lib.ina228_current_ua.argtypes = [ctypes.c_uint32, ctypes.c_int32]
        lib.adc_pin_uv.argtypes = [ctypes.c_uint16, ctypes.c_uint32]
        self.assertEqual(lib.max17048_vcell_uv(self.VCELL[0]), self.VCELL[1])
        self.assertEqual(lib.max17048_soc_mpct(self.SOC[0]), self.SOC[1])
        self.assertEqual(lib.max17048_crate_mpct_h(self.CRATE[0]), self.CRATE[1])
        self.assertEqual(lib.ina228_dietemp_mc(self.DIETEMP[0]), self.DIETEMP[1])
        self.assertEqual(lib.iset_charge_ua(self.ISET[0], R_ISET), self.ISET[1])
        self.assertEqual(lib.ina228_current_ua(self.ISHUNT[0], SHUNT_UOHM), self.ISHUNT[1])
        self.assertEqual(lib.adc_pin_uv(4095, 3000), 3_000_000)   # full scale is VDDA at the pin

    def test_the_bench_logger(self):
        pb1 = round(iset_pin(self.ISET[0] / 1e6) * 1e6)   # version 4 carries the PB1 node (bl_pkt.h:19)
        p = dict(version=self.log.BL_VERSION, flags=0x01 | 0x02 | 0x20, seq=1, uptime_s=1, samples=1, misses=0,
                 vout_uv=4_400_000,
                 ishunt_ua=self.ISHUNT[1], iset_uv=pb1, iset_min_uv=pb1, iset_max_uv=pb1,
                 ina_die_mc=self.DIETEMP[1], vcell_uv=self.VCELL[1], soc_mpct=self.SOC[1], crate_mpct_h=self.CRATE[1],
                 sht_t_mc=0, sht_rh_mpct=0, vin_uv=None)
        r = self.log.row(p, -40, 9, 0, cal=self.log.Cal(r_iset_ohm=R_ISET, k_iset=K_ISET))
        self.assertEqual(r['charge_ma'], self.ISET[1] / 1000)
        self.assertEqual(r['battery_ma'], -self.ISHUNT[1] / 1000)   # + into the cell: the sign turns once
        self.assertEqual(r['vcell_v'], self.VCELL[1] / 1e6)
        self.assertEqual(r['soc_pct'], self.SOC[1] / 1000)
        self.assertEqual(r['rate_pct_h'], self.CRATE[1] / 1000)
        self.assertEqual(r['ina_die_c'], self.DIETEMP[1] / 1000)

    def test_the_node_driver(self):
        b = Bench(self, self.library, PHASE_A)
        b.lib.h_charger_pins(PGOOD | CHG)
        b.lib.h_max17048_cell(self.VCELL[1])
        b.lib.h_max17048_soc_256(self.SOC[0])
        b.lib.h_max17048_rate(self.CRATE[1])
        b.lib.h_ina228_die(b.dev[BATTERY], self.DIETEMP[1])
        b.ina(BATTERY, 4.40, self.ISHUNT[1])
        b.adc(iset=iset_pin(self.ISET[0] / 1e6), vin=5.0 / 3)   # the node unscales the 10k/1M gain
        b.minute()
        b.minute()
        self.assertEqual(b.value(BATT_MV), self.VCELL[1] // 1000)
        self.assertEqual(b.value(BATT_MA), -self.ISHUNT[1] // 1000)
        self.assertEqual(b.lib.h_chg_batt_ma(), self.ISET[1] // 1000)
        self.assertEqual(b.lib.h_soc(), self.SOC[0])
        self.assertEqual(b.lib.h_soc_rate(), round(self.CRATE[1] / 100))
        self.assertEqual(b.lib.h_monitor_temp(), round(self.DIETEMP[1] / 100))


if __name__ == '__main__':
    unittest.main()
