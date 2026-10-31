"""The interim map from WSMP snapshots to the catalog (App/wsmp_catalog_map.c; WSMP bench design section
5, power telemetry design docs/superpowers/specs/2026-10-29-power-telemetry-design.md sections 3.2, 5.2,
5.3 and 9.7).

The real modules, station host and map run on the host bus model; each reading is encoded by
firmware/common/ws_obs.c and decoded by the gateway's own decoder (ws0/fields.py), so the round trip
checks both ends. Expected values come from the specs' tables and the parts' datasheets.

The descriptor-set fuzz seed firmware/fuzz/corpus/set/bench.bin is this station's own set (every module
in the layout: 8 modules, 24 channels). WS_WRITE_SEEDS=1 python -m unittest tests.test_wsmp_map rewrites
it; without it the test checks that the seed still matches."""
import ctypes
import os
import unittest

try:
    from toolchain import ROOT, fresh_station, host_library, needs_cc, wsmp_sources          # python -m unittest discover -s tests
    import wsmp_wind_ref as wind_ref
except ImportError:
    from tests.toolchain import ROOT, fresh_station, host_library, needs_cc, wsmp_sources    # python -m unittest tests.<module>
    from tests import wsmp_wind_ref as wind_ref
from ws0 import fields, wsmp_set

DEVK_SHT45, DEVK_SHTC3, DEVK_BMP581, DEVK_LTR390, DEVK_INA228, DEVK_MAX17048 = 2, 3, 4, 5, 6, 7
ADDR = {DEVK_SHT45: 0x44, DEVK_SHTC3: 0x70, DEVK_BMP581: 0x47, DEVK_LTR390: 0x53, DEVK_INA228: 0x40, DEVK_MAX17048: 0x36}
ALL = list(ADDR)
MINUTE = 60_000
PGOOD, CHG = 1, 2
F = {f.name: f.index for f in fields.FIELDS}
P_BATTERY, P_RAILS = 5, 8
MISSING, FAULT, NOT_FITTED = 3, 5, 6
LOAD, SOLAR, USB = 0x41, 0x45, 0x48             # the phase B INA228s (App/power_config.h)
VDDA = 3300
OUT_UV, CELL_UV = 4_400_000, 3_900_000          # the charger OUT (INA228 VBUS) and the cell (gauge VCELL)
SET_SEED = ROOT/'firmware/fuzz/corpus/set/bench.bin'

# The power fields (design section 3.2): the battery module's, then the rails module's.
BATTERY_FIELDS = [F[n] for n in ('batt_mv', 'batt_current_ma', 'energy_in_mwh', 'energy_out_mwh', 'charge_in_mah',
                                 'charge_out_mah')]
RAIL_FIELDS = [F[n] for n in ('load_mv', 'load_current_ma', 'charger_input_mv', 'solar_mv', 'solar_current_ma', 'usb_mv',
                              'usb_current_ma')]
POWER_FIELDS = set(BATTERY_FIELDS + RAIL_FIELDS)
RETIRED = {F['soc_gauge_pct'], F['charger_pins']}
PHASE_A = set(BATTERY_FIELDS) | {F['load_mv'], F['charger_input_mv']}   # present in phase A
PHASE_A_ABSENT = POWER_FIELDS - PHASE_A | RETIRED                         # 27, 29, 30, 32, 33, 17, 18

# Test only: overwrite one slot of a port's stored snapshot (value as two's complement, and quality),
# as a module that reported it would, to reach codes the bus models cannot (a 32 A current).
SHIM = r'''
#include <stdint.h>
#include "wsmp_host.h"
void t_force_slot(int port, int i, int32_t value, int quality)
{
  wsmp_snapshot *s = (wsmp_snapshot *)(uintptr_t)wsmp_host_snapshot((enum wsmp_port)port);
  if (s) { s->slot[i].value = (uint32_t)value; s->slot[i].quality = (uint8_t)quality; }
}
'''


def pin_mv(raw, ratio=3):
    """power_regs.c: the pin voltage of a 12-bit result at VDDA, times the divider ratio, mV half up."""
    return (raw * VDDA * 1000 // 4095 * ratio + 500) // 1000


def vin_raw(mv):
    """The PA10 result of a charger input of mv through the 3:1 divider."""
    return round(mv / 3 * 4095 / VDDA)


@needs_cc
class CatalogMap(unittest.TestCase):
    PROFILE = 1

    @classmethod
    def setUpClass(cls):
        app = ROOT/'firmware/stage0-node/App'
        cls.library = host_library(cls, f'wsmpmap{cls.PROFILE}', '-DWSMP_HOST', '-DWSMP_MAP',
                                   f'-DWS_POWER_PROFILE={cls.PROFILE}', *wsmp_sources(), app/'wsmp_host.c',
                                   app/'wsmp_catalog_map.c', ROOT/'firmware/common/ws_obs.c', files={'shim.c': SHIM})._name

    def station(self, kinds, vane=None, rain=True, vin_mv=5_000, adc=True):
        vane = wind_ref.vane_mv(4) if vane is None else vane
        lib = fresh_station(self, self.library)
        lib.h_power_adc.argtypes = [ctypes.c_uint16] * 4
        devs = {k: lib.h_add_device(k, ADDR[k]) for k in kinds}
        lib.h_init(7)
        if DEVK_BMP581 in devs:
            lib.h_bmp581_set(devs[DEVK_BMP581], 101_325 * 64)
        if DEVK_LTR390 in devs:
            lib.h_ltr390_set(devs[DEVK_LTR390], 123_456)
        if DEVK_INA228 in devs:
            lib.h_ina228_set(devs[DEVK_INA228], OUT_UV, 500_000)     # VIN+ -> VIN-: 500 mA out of the cell
        if DEVK_MAX17048 in devs:
            lib.h_max17048_set(devs[DEVK_MAX17048], 87)
            lib.h_max17048_cell(CELL_UV)
        if adc:
            lib.h_power_adc(0, vin_raw(vin_mv), 1500, VDDA)          # ISET 0, the charger input, VDDA 3.3 V
        lib.h_vane_mv(vane)
        lib.h_rain_enable(1 if rain else 0)
        lib.h_charger_pins(PGOOD | CHG)
        lib.h_host_init()
        return lib, devs

    def minute(self, lib, pulses_per_tick=0):
        """One minute as app_tx.c runs it: module ticks, the latch, then the minute's reading."""
        for _ in range(MINUTE // 250):
            lib.h_pulses_add(pulses_per_tick)
            lib.h_host_run(250)
        lib.h_host_latch(1_792_000_000)
        return self.reading(lib)

    def plain(self, lib):
        buf = (ctypes.c_uint8 * 100)()
        n = lib.h_map_reading(buf, 100)
        self.assertGreater(n, 0, 'the reading encodes')
        return bytes(buf[:n])

    def reading(self, lib):
        head, codes = fields.decode(self.plain(lib))
        return codes, fields.values(codes)


def name_of(index):
    return next(f.name for f in fields.FIELDS if f.index == index)


class PhaseA(CatalogMap):
    """Profile A (the default build): the bq24074, the battery INA228 at 0x40 with its VBUS on OUT, the
    MAX17048 on the cell and the PA10 charger-input divider."""

    def test_map_round_trip_through_the_gateway_decoder(self):
        lib, _ = self.station(ALL)
        for _ in range(3):
            lib.h_rain_tip(); lib.h_advance(200)
        self.minute(lib, 5)
        codes, v = self.minute(lib, 5)
        self.assertEqual(v['temperature_c'], 42.5)                 # SHT45 words 0x8000
        self.assertEqual(v['humidity_pct'], 56.5)
        self.assertEqual(v['th_samples'], 4)
        self.assertEqual(v['pressure_hpa'], 1013.3)                # 101,325 Pa
        self.assertEqual(v['uva_raw'], 123_456)
        self.assertEqual(v['enclosure_temp_c'], 42.5)              # SHTC3 words 0x8000
        self.assertEqual(v['enclosure_rh_pct'], 50.0)
        self.assertEqual(v['wind_speed_ms'], 13.3)                 # 1,200 pulses in 60 s = 20 Hz x 0.66698
        self.assertEqual(v['wind_gust_ms'], 13.3)
        self.assertEqual(v['wind_dir_deg'], 90)                    # vane position 4: east
        self.assertEqual(v['rain_tips'], 3)
        self.assertEqual(v['batt_mv'], 3900)                       # the cell (gauge VCELL), never OUT
        self.assertEqual(v['batt_current_ma'], -500)               # 500 mA out of the cell: negative
        self.assertEqual(v['load_mv'], 4400)                       # the battery INA228's VBUS on OUT
        self.assertEqual(v['charger_input_mv'], pin_mv(vin_raw(5_000)))
        self.assertGreater(v['charge_out_mah'], 0)
        self.assertEqual(v['charge_in_mah'], 0)
        self.assertEqual(set(codes) & PHASE_A_ABSENT, set())       # not fitted, and the retired 17 and 18
        for name in ('temperature_min_c', 'temperature_max_c', 'humidity_min_pct', 'humidity_max_pct'):
            self.assertNotIn(F[name], codes)                       # the gateway derives extremes (WSMP rule 6)

    def test_the_widest_phase_a_record_is_65_bytes(self):
        # Design section 5.4: the v5 bench set (61 B) less fields 17 and 18 plus 12, 26 and 28.
        lib, _ = self.station(ALL)
        self.minute(lib, 5)
        self.minute(lib, 5)
        plain = self.plain(lib)
        self.assertEqual(len(plain), 65)
        self.assertEqual(int.from_bytes(plain[18:22], 'big') >> 31, 0)   # no extension word

    def test_bitmap_follows_active_modules(self):
        # Review Focus 4: modules come and go; each reading carries exactly the modules active at its latch.
        # The battery and rails modules are base-board modules, in every layout (design section 8.5).
        lib, devs = self.station([DEVK_SHT45, DEVK_BMP581], vane=3_300, rain=False)
        codes, _ = self.minute(lib)
        self.assertEqual(set(codes), {F['temperature_c'], F['humidity_pct'], F['th_samples'], F['pressure_hpa']} | PHASE_A)
        lib.h_remove_device(devs[DEVK_BMP581])
        codes, v = self.minute(lib)
        self.assertIn(F['pressure_hpa'], codes)                    # suspect: still in the layout ...
        self.assertIsNone(v['pressure_hpa'])                       # ... and INVALID, not a stale value
        self.minute(lib)
        codes, _ = self.minute(lib)
        self.assertEqual(set(codes), {F['temperature_c'], F['humidity_pct'], F['th_samples']} | PHASE_A)   # removed

    def test_no_port_module_still_sends_the_power_fields(self):
        # Without any port module the power modules are still in the layout, so the reading is never
        # empty: it carries the phase A power fields (here with their parts dead: INVALID).
        lib, _ = self.station([], vane=3_300, rain=False, adc=False)
        codes, v = self.minute(lib)
        self.assertEqual(set(codes), PHASE_A)
        self.assertEqual([v[name_of(i)] for i in sorted(PHASE_A)], [None] * len(PHASE_A))

    def test_first_minute_has_no_wind_speed(self):
        lib, _ = self.station([DEVK_SHT45])
        _, v = self.minute(lib, 5)
        self.assertIsNone(v['wind_speed_ms'])                      # no earlier counter to take the increment from
        self.assertIsNone(v['wind_dir_deg'])
        self.assertFalse(v['wind_calm'])

    def test_wind_speed_returns_one_minute_after_a_long_window(self):
        # A long window (a skipped latch) has no speed, but its pulse counter is still good: the next
        # minute takes its increment from it (WSMP-T3 drops rates, not counters).
        lib, _ = self.station([DEVK_SHT45])
        self.minute(lib)
        lib.h_host_run(2 * MINUTE)                                 # no latch: the next window is long
        _, v = self.minute(lib)
        self.assertIsNone(v['wind_speed_ms'])
        _, v = self.minute(lib, 5)
        self.assertIsNotNone(v['wind_speed_ms'])

    def test_a_long_window_drops_the_power_means_and_keeps_the_counters(self):
        # Design section 9.7: means over more than a minute are INVALID (WSMP-T3); counters stay.
        lib, _ = self.station([DEVK_INA228, DEVK_MAX17048])
        self.minute(lib)
        lib.h_host_run(2 * MINUTE)                                 # no latch: the next window is long
        codes, v = self.minute(lib)
        self.assertEqual(set(codes) & POWER_FIELDS, PHASE_A)       # nothing goes absent
        for name in ('batt_mv', 'batt_current_ma', 'load_mv', 'charger_input_mv'):
            self.assertIsNone(v[name], name)
        for name in ('energy_out_mwh', 'charge_out_mah'):
            self.assertGreater(v[name], 0, name)                   # 3 minutes at 500 mA out
        for name in ('energy_in_mwh', 'charge_in_mah'):
            self.assertEqual(v[name], 0, name)

    def test_a_fault_or_unknown_quality_goes_invalid(self):
        # WSMP section 9: quality 5 (fault) and unknown codes are "missing" on the radio.
        for q in (5, 9):
            with self.subTest(quality=q):
                lib, _ = self.station([DEVK_SHT45, DEVK_INA228])
                self.minute(lib)
                self.minute(lib)
                lib.h_host_force_quality(1, q)                     # the air module's slots
                lib.h_host_force_quality(P_BATTERY, q)             # the battery module's slots
                lib.h_host_force_quality(P_RAILS, q)               # the rails module's slots, not fitted ones too
                codes, v = self.reading(lib)
                self.assertIsNone(v['temperature_c'])
                self.assertEqual(set(codes) & POWER_FIELDS, POWER_FIELDS)   # a forced fault is not "not fitted"
                self.assertEqual({v[name_of(i)] for i in POWER_FIELDS}, {None})

    def test_a_missing_humidity_leaves_the_temperature(self):
        # Each channel has its own count (section 6.9): RH of -6 % is suspect on every sample, so the
        # RH slot is missing and goes INVALID, while the temperature of the same samples is sent.
        lib, devs = self.station([DEVK_SHT45])
        lib.h_sht45_set(devs[DEVK_SHT45], 0x8000, 0, 0)
        self.minute(lib)
        _, v = self.minute(lib)
        self.assertEqual((v['temperature_c'], v['humidity_pct'], v['th_samples']), (42.5, None, 4))

    def test_pressure_outside_the_field_goes_invalid(self):
        # Field 2 holds 300.0 to 1100.0 hPa: below and above it the reading is INVALID, never clamped.
        for pa, expected in ((29_990, None), (30_000, 300.0), (110_000, 1100.0), (110_010, None)):
            with self.subTest(pa=pa):
                lib, devs = self.station([DEVK_SHT45, DEVK_BMP581])
                lib.h_bmp581_set(devs[DEVK_BMP581], pa * 64)
                self.minute(lib)
                _, v = self.minute(lib)
                self.assertEqual(v['pressure_hpa'], expected)

    def test_calm_direction(self):
        lib, _ = self.station([DEVK_SHT45])
        self.minute(lib)
        _, v = self.minute(lib)
        self.assertEqual(v['wind_speed_ms'], 0.0)
        self.assertTrue(v.get('wind_calm'))                        # CALM below 0.5 m/s

    def test_the_gauge_soc_and_the_charger_pins_are_not_in_the_observation(self):
        # Fields 17 and 18 are retired (design section 5.2): the health report carries SOC and the
        # charger status. A gauge above 100 % (the MAX17048 reports 101 % and more near full) cannot
        # break the reading any more.
        for soc in (87, 101, 255):
            with self.subTest(soc=soc):
                lib, devs = self.station([DEVK_INA228, DEVK_MAX17048])
                lib.h_max17048_set(devs[DEVK_MAX17048], soc)
                self.minute(lib)
                codes, _ = self.minute(lib)
                self.assertEqual(set(codes) & RETIRED, set())

    def test_a_code_out_of_its_field_range_goes_invalid(self):
        # Any value the catalog cannot hold becomes INVALID, never a reading that fails to encode:
        # here a load voltage above the field's 65.534 V.
        lib, devs = self.station([DEVK_INA228])
        lib.h_ina228_set(devs[DEVK_INA228], 70_000_000, 0)
        self.minute(lib)
        codes, v = self.minute(lib)
        self.assertIn(F['load_mv'], codes)
        self.assertIsNone(v['load_mv'])

    def test_the_battery_current_sign_and_its_edges(self):
        # Design sections 3.1 and 5.2: + into the cell; code = mA + 32768; the codec's own range check
        # decides: -32768 and +32766 mA encode, -32769 and +32767 (code 65535, INVALID) do not.
        lib, devs = self.station([DEVK_INA228, DEVK_MAX17048])
        lib.h_ina228_set(devs[DEVK_INA228], OUT_UV, -1_000_000)  # VIN- -> VIN+: 1 A into the cell
        self.minute(lib)
        codes, v = self.minute(lib)
        self.assertEqual((v['batt_current_ma'], codes[F['batt_current_ma']]), (1000, 33768))
        for ma, code in ((-32768, 0), (-1, 32767), (0, 32768), (32766, 65534), (-32769, 0xFFFF), (32767, 0xFFFF),
                         (-(1 << 31), 0xFFFF), ((1 << 31) - 1, 0xFFFF)):
            with self.subTest(ma=ma):
                lib.t_force_slot(P_BATTERY, 1, ma, 0)
                codes, v = self.reading(lib)
                self.assertEqual(codes[F['batt_current_ma']], code)
                self.assertEqual(v['batt_current_ma'], None if code == 0xFFFF else ma)

    def test_each_rail_maps_to_its_field_with_its_invalid_case(self):
        # The rails module's slots in registry order (type 9) to fields 26-30, 32 and 33: a good slot
        # carries its value, a missing or faulted one is INVALID, a not fitted one is left out.
        lib, _ = self.station([DEVK_INA228, DEVK_MAX17048])
        self.minute(lib)
        self.minute(lib)
        values = (4400, 250, 5000, 6100, -3, 5100, 32766)
        for slot, (field, value) in enumerate(zip(RAIL_FIELDS, values, strict=True)):
            with self.subTest(field=name_of(field)):
                lib.t_force_slot(P_RAILS, slot, value, 0)
                codes, v = self.reading(lib)
                self.assertEqual(v[name_of(field)], value)
                for q in (MISSING, FAULT):
                    lib.t_force_slot(P_RAILS, slot, value, q)
                    codes, v = self.reading(lib)
                    self.assertIn(field, codes)
                    self.assertIsNone(v[name_of(field)])
                lib.t_force_slot(P_RAILS, slot, value, NOT_FITTED)
                codes, _ = self.reading(lib)
                self.assertNotIn(field, codes)

    def test_a_voltage_slot_out_of_its_field_goes_invalid(self):
        # A negative or too large voltage (two's complement in the slot) never encodes as a value.
        lib, _ = self.station([DEVK_INA228, DEVK_MAX17048])
        self.minute(lib)
        self.minute(lib)
        for mv in (-1, 65_535, 1 << 20):
            with self.subTest(mv=mv):
                lib.t_force_slot(P_RAILS, 2, mv, 0)
                lib.t_force_slot(P_BATTERY, 0, mv, 0)
                _, v = self.reading(lib)
                self.assertEqual((v['charger_input_mv'], v['batt_mv']), (None, None))

    def test_energy_missing_drops_fields_13_and_14_only(self):
        # Design section 9.4: a step with charge and no fresh cell voltage marks both energy slots
        # missing; fields 13 and 14 are INVALID that minute, the charge counters 15 and 16 are not.
        lib, _ = self.station([DEVK_INA228, DEVK_MAX17048])
        self.minute(lib)
        self.minute(lib)
        for slot in (2, 3):
            lib.t_force_slot(P_BATTERY, slot, 12, MISSING)
        codes, v = self.reading(lib)
        self.assertEqual((v['energy_in_mwh'], v['energy_out_mwh']), (None, None))
        self.assertIsNotNone(v['charge_in_mah'])
        self.assertGreater(v['charge_out_mah'], 0)
        self.assertEqual((v['batt_mv'], v['batt_current_ma']), (3900, -500))

    def test_a_missing_gauge_drops_the_cell_voltage_and_the_energy(self):
        # The real path of the same rule: no gauge, no cell voltage, so field 11 and the energy go
        # INVALID; the INA228's current, charge counters and load voltage stay (design sections 3.2, 9.4).
        lib, _ = self.station([DEVK_INA228])
        self.minute(lib)
        codes, v = self.minute(lib)
        self.assertEqual(set(codes) & POWER_FIELDS, PHASE_A)
        self.assertEqual([v[n] for n in ('batt_mv', 'energy_in_mwh', 'energy_out_mwh')], [None] * 3)
        self.assertEqual((v['batt_current_ma'], v['load_mv'], v['charge_in_mah']), (-500, 4400, 0))
        self.assertGreater(v['charge_out_mah'], 0)

    def test_every_power_part_dead_is_invalid_not_absent(self):
        # Design sections 5.3 and 8.5: no INA228, no gauge, no ADC sequence: fields 11-16 and the phase A
        # rails (26, 28) are present and INVALID ("sensor fault"), never absent ("not in this build").
        lib, _ = self.station([DEVK_SHT45], adc=False)
        self.minute(lib)
        codes, v = self.minute(lib)
        self.assertEqual(set(codes) & (POWER_FIELDS | RETIRED), PHASE_A)
        self.assertEqual({v[name_of(i)] for i in PHASE_A}, {None})

    def test_phase_matrix(self):
        # Design section 3.2: what phase A puts in each slot, per charger state and per input source.
        # The bq24074 has one input, so USB-C (bench, backup) and solar (never at the same time) look the
        # same: only the charger input voltage (28), and the map never infers the source from it.
        states = {                      # name: (pins, INA228 VIN+ -> VIN- uA, battery mA)
            'off': (0, 150_000, -150),
            'charging': (PGOOD | CHG, -1_000_000, 1000),
            'done': (PGOOD, 0, 0),
        }
        sources = {'usb-c': 5_000, 'solar': 4_500, 'none': 0}   # solar under load sits low (VIN-DPM with EN2 low, or pulled down with EN2 high)
        for state, (pins, ua, ma) in states.items():
            for source, mv in sources.items():
                if (state == 'off') != (source == 'none'):
                    continue            # the charger is off exactly when it has no input
                with self.subTest(state=state, source=source):
                    lib, devs = self.station([DEVK_INA228, DEVK_MAX17048], vin_mv=mv)
                    lib.h_charger_pins(pins)
                    lib.h_ina228_set(devs[DEVK_INA228], OUT_UV, ua)
                    self.minute(lib)
                    codes, v = self.minute(lib)
                    self.assertEqual(set(codes) & (POWER_FIELDS | RETIRED), PHASE_A)   # present; the rest absent
                    self.assertEqual((v['batt_mv'], v['batt_current_ma'], v['load_mv']), (3900, ma, 4400))
                    self.assertEqual(v['charger_input_mv'], pin_mv(vin_raw(mv)))
                    self.assertEqual({v[name_of(i)] is None for i in PHASE_A}, {False})
        with self.subTest(case='a missing part'):
            lib, _ = self.station([DEVK_MAX17048], adc=False)  # the INA228 and the ADC are dead
            self.minute(lib)
            codes, v = self.minute(lib)
            self.assertEqual(set(codes) & (POWER_FIELDS | RETIRED), PHASE_A)
            self.assertEqual(v['batt_mv'], 3900)
            self.assertEqual({v[name_of(i)] for i in PHASE_A - {F['batt_mv']}}, {None})

    def test_the_set_fuzz_seed_is_this_stations_set(self):
        # PT-077: firmware/fuzz/corpus/set/bench.bin is byte 0 (0: keep the digest) and the descriptor
        # set of this station with every module in the layout: 8 modules, 24 channels (design 8.4).
        lib, _ = self.station(ALL)
        self.minute(lib, 5)
        self.minute(lib, 5)
        out = (ctypes.c_uint8 * 296)()
        n = lib.h_host_set(out)
        raw = bytes(out)[:n]
        s = wsmp_set.unpack(raw)
        self.assertEqual((len(s.modules), sum(len(m.descriptors) for m in s.modules)), (8, 24))
        self.assertEqual([m.port for m in s.modules], [1, 2, 3, 4, 5, 6, 7, 8])
        if os.environ.get('WS_WRITE_SEEDS') == '1':
            SET_SEED.write_bytes(b'\x00' + raw)
        self.assertEqual(SET_SEED.read_bytes(), b'\x00' + raw, 'regenerate: WS_WRITE_SEEDS=1 python -m unittest tests.test_wsmp_map')

    def test_no_stale_mean_after_a_quarantine(self):
        # A flapping module is quarantined for an hour while it keeps sampling. The first reading
        # after it rejoins must not report that hour-long window as the minute's value (WSMP-T3): the
        # driver's window starts afresh at the admission (the bind, ports design section 6.7), so the
        # first reading holds only the samples since then, and the next minute is normal again.
        lib, devs = self.station([DEVK_SHT45], vane=3_300, rain=False)
        dev = devs[DEVK_SHT45]
        for _ in range(3):                                     # join, leave: the 5th change quarantines
            self.minute(lib)
            lib.h_remove_device(dev)
            for _ in range(3):
                self.minute(lib)
            lib.h_restore_device(dev)
        for _ in range(3):
            self.minute(lib)                                   # the module leaves the layout: quarantined
        self.assertEqual(lib.h_host_state(1), 6)               # the air module is quarantined
        for _ in range(70):                                    # the hour, with the sensor sampling
            codes, v = self.minute(lib)
            if lib.h_host_state(1) == 4:                       # active again: this reading is its first
                break
        self.assertEqual(lib.h_host_state(1), 4, 'the module is active again after the hour')
        self.assertEqual(v['temperature_c'], 42.5)
        self.assertLess(v['th_samples'], 4, 'the first reading after the quarantine holds only the samples since the bind')
        _, v = self.minute(lib)
        self.assertEqual(v['temperature_c'], 42.5)

    def test_first_reading_after_a_warm_reset_is_a_minute(self):
        # The board's clock keeps counting across a warm reset (PROVISION, WIPE, a reflash), so the
        # modules start at a large clock_ms(). Their first window is the time since they started,
        # not since 0: the first reading has its temperature (found on the bench, 2026-10-19).
        lib = fresh_station(self, self.library)                   # with the invariants every station keeps
        lib.h_advance(5_000_000)   # the clock before the modules start
        lib.h_add_device(DEVK_SHT45, ADDR[DEVK_SHT45])
        lib.h_init(7)
        lib.h_vane_mv(3_300)
        lib.h_host_init()
        _, v = self.minute(lib)
        self.assertEqual(v['temperature_c'], 42.5)

class PhaseB(CatalogMap):
    """Profile B (WS_POWER_PROFILE=2): one INA228 per rail besides the battery's, upstream of where the
    sources join (load 0x41, solar 0x45, USB-C 0x48). The same map and field set as phase A."""
    PROFILE = 2

    def rails(self, lib, load_ma=300, solar=(0, 0), usb=(5_100, 800)):
        """Adds the three rail monitors: (VBUS mV, current mA) each, + into the load or the station."""
        devs = {}
        for addr, (mv, ma) in ((LOAD, (OUT_UV // 1000, load_ma)), (SOLAR, solar), (USB, usb)):
            devs[addr] = lib.h_add_device(DEVK_INA228, addr)
            lib.h_ina228_set(devs[addr], mv * 1000, ma * 1000)    # VIN+ at the source: + is into the station
        return devs

    def test_the_build_is_profile_b(self):
        lib, _ = self.station([])
        self.assertEqual(lib.h_power_profile(), 2)

    def test_every_rail_with_the_extension_word(self):
        # Design sections 5.1 and 5.4: every module and every rail, 77 bytes, EXT (bit 31) set and the
        # extension bitmap for fields 32 and 33. USB-C charging, solar disconnected (never both).
        lib, _ = self.station(ALL)
        self.rails(lib)
        self.minute(lib, 5)
        self.minute(lib, 5)
        plain = self.plain(lib)
        self.assertEqual(len(plain), 77)
        self.assertEqual(int.from_bytes(plain[18:22], 'big') >> 31, 1)
        self.assertEqual(int.from_bytes(plain[22:24], 'big'), 0b11)          # fields 32 and 33
        codes, v = self.reading(lib)
        self.assertEqual(set(codes) & (POWER_FIELDS | RETIRED), POWER_FIELDS)
        self.assertEqual((v['batt_mv'], v['batt_current_ma']), (3900, -500))
        self.assertEqual((v['load_mv'], v['load_current_ma']), (4400, 300))
        self.assertEqual(v['charger_input_mv'], pin_mv(vin_raw(5_000)))
        self.assertEqual((v['solar_mv'], v['solar_current_ma']), (0, 0))
        self.assertEqual((v['usb_mv'], v['usb_current_ma']), (5100, 800))

    def test_solar_or_usb_c_each_on_its_own_rail(self):
        for name, solar, usb in (('solar', (6_100, 700), (0, 0)), ('usb-c', (0, 0), (5_100, 900))):
            with self.subTest(source=name):
                lib, _ = self.station([DEVK_INA228, DEVK_MAX17048])
                self.rails(lib, solar=solar, usb=usb)
                self.minute(lib)
                _, v = self.minute(lib)
                self.assertEqual(((v['solar_mv'], v['solar_current_ma']), (v['usb_mv'], v['usb_current_ma'])), (solar, usb))

    def test_every_power_part_dead_is_invalid_not_absent(self):
        lib, _ = self.station([DEVK_SHT45], adc=False)
        self.minute(lib)
        codes, v = self.minute(lib)
        self.assertEqual(set(codes) & (POWER_FIELDS | RETIRED), POWER_FIELDS)
        self.assertEqual({v[name_of(i)] for i in POWER_FIELDS}, {None})

    def test_a_dead_rail_monitor_is_invalid_and_the_others_stay(self):
        lib, _ = self.station([DEVK_INA228, DEVK_MAX17048])
        devs = self.rails(lib)
        lib.h_remove_device(devs[SOLAR])
        self.minute(lib)
        codes, v = self.minute(lib)
        self.assertEqual(set(codes) & POWER_FIELDS, POWER_FIELDS)
        self.assertEqual((v['solar_mv'], v['solar_current_ma']), (None, None))
        self.assertEqual((v['usb_mv'], v['usb_current_ma'], v['load_current_ma']), (5100, 800, 300))


if __name__ == '__main__':
    unittest.main()
