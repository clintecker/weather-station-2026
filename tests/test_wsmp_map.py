"""The interim map from WSMP snapshots to today's catalog (App/wsmp_catalog_map.c, spec section 5).

The real modules, station host and map run on the host bus model; each reading is encoded by
firmware/common/ws_obs.c and decoded by the gateway's own decoder (ws0/fields.py), so the round trip
checks both ends. Expected values come from the spec's table and the parts' datasheets."""
import ctypes
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from toolchain import ROOT, host_library, needs_cc          # python -m unittest discover -s tests
    from test_modules import module_sources
    import wsmp_wind_ref as wind_ref
except ImportError:
    from tests.toolchain import ROOT, host_library, needs_cc    # python -m unittest tests.<module>
    from tests.test_modules import module_sources
    from tests import wsmp_wind_ref as wind_ref
from ws0 import fields

DEVK_SHT45, DEVK_SHTC3, DEVK_BMP581, DEVK_LTR390, DEVK_INA228, DEVK_MAX17048 = 2, 3, 4, 5, 6, 7
ADDR = {DEVK_SHT45: 0x44, DEVK_SHTC3: 0x70, DEVK_BMP581: 0x47, DEVK_LTR390: 0x53, DEVK_INA228: 0x40, DEVK_MAX17048: 0x36}
ALL = list(ADDR)
MINUTE = 60_000
PGOOD, CHG = 1, 2
F = {f.name: f.index for f in fields.FIELDS}


@needs_cc
class CatalogMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = ROOT/'firmware/stage0-node/App'
        cls.library = host_library(cls, 'wsmpmap', '-DWSMP_HOST', '-DWSMP_MAP', *module_sources(), app/'wsmp_host.c',
                                   app/'wsmp_catalog_map.c', ROOT/'firmware/common/ws_obs.c')._name
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.count = 0

    def station(self, kinds, vane=None, rain=True):
        vane = wind_ref.vane_mv(4) if vane is None else vane
        type(self).count += 1
        path = Path(self.tmp.name)/f'map{self.count}.so'
        shutil.copy(self.library, path)
        lib = ctypes.CDLL(str(path))
        devs = {k: lib.h_add_device(k, ADDR[k]) for k in kinds}
        lib.h_init(7)
        if DEVK_BMP581 in devs:
            lib.h_bmp581_set(devs[DEVK_BMP581], 101_325 * 64)
        if DEVK_LTR390 in devs:
            lib.h_ltr390_set(devs[DEVK_LTR390], 123_456)
        if DEVK_INA228 in devs:
            lib.h_ina228_set(devs[DEVK_INA228], 4_000_000, 500_000)
        if DEVK_MAX17048 in devs:
            lib.h_max17048_set(devs[DEVK_MAX17048], 87)
        lib.h_vane_mv(vane)
        lib.h_rain_enable(1 if rain else 0)
        lib.h_charger_pins(PGOOD | CHG)
        lib.h_host_init()
        self.addCleanup(lambda: self.assertEqual((lib.h_pin_errors(), lib.ws_check_count()), (0, 0)))
        return lib, devs

    def minute(self, lib, pulses_per_tick=0):
        """One minute as app_tx.c runs it: module ticks, the latch, then the minute's reading."""
        for _ in range(MINUTE // 250):
            lib.h_pulses_add(pulses_per_tick)
            lib.h_host_run(250)
        lib.h_host_latch(1_792_000_000)
        return self.reading(lib)

    def reading(self, lib):
        buf = (ctypes.c_uint8 * 100)()
        n = lib.h_map_reading(buf, 100)
        self.assertGreater(n, 0, 'the reading encodes')
        head, codes = fields.decode(bytes(buf[:n]))
        return codes, fields.values(codes)

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
        self.assertEqual(v['batt_mv'], 4000)
        self.assertEqual(v['soc_gauge_pct'], 87)
        self.assertEqual(codes[F['charger_pins']], PGOOD | CHG)    # charging: both pins asserted
        self.assertGreater(v['charge_in_mah'], 0)
        self.assertNotIn(F['batt_current_ma'], codes)              # left out: 1 mAh counters are too coarse
        for name in ('temperature_min_c', 'temperature_max_c', 'humidity_min_pct', 'humidity_max_pct'):
            self.assertNotIn(F[name], codes)                       # the gateway derives extremes (WSMP rule 6)

    def test_bitmap_follows_active_modules(self):
        # Review Focus 4: modules come and go; each reading carries exactly the modules active at its latch.
        lib, devs = self.station([DEVK_SHT45, DEVK_BMP581], vane=3_300, rain=False)
        codes, _ = self.minute(lib)
        self.assertEqual(set(codes), {F['temperature_c'], F['humidity_pct'], F['th_samples'], F['pressure_hpa']})
        lib.h_remove_device(devs[DEVK_BMP581])
        codes, v = self.minute(lib)
        self.assertIn(F['pressure_hpa'], codes)                    # suspect: still in the layout ...
        self.assertIsNone(v['pressure_hpa'])                       # ... and INVALID, not a stale value
        self.minute(lib)
        codes, _ = self.minute(lib)
        self.assertEqual(set(codes), {F['temperature_c'], F['humidity_pct'], F['th_samples']})   # removed

    def test_no_module_still_sends_the_air_fields_invalid(self):
        # As today's firmware: a minute without any module sends temperature and humidity INVALID,
        # never an empty reading (the catalog refuses an empty field bitmap).
        lib, _ = self.station([], vane=3_300, rain=False)
        codes, v = self.minute(lib)
        self.assertEqual(set(codes), {F['temperature_c'], F['humidity_pct'], F['th_samples']})
        self.assertEqual((v['temperature_c'], v['humidity_pct'], v['th_samples']), (None, None, 0))

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

    def test_a_fault_or_unknown_quality_goes_invalid(self):
        # WSMP section 9: quality 5 (fault) and unknown codes are "missing" on the radio.
        for q in (5, 9):
            with self.subTest(quality=q):
                lib, _ = self.station([DEVK_SHT45, DEVK_INA228])
                self.minute(lib)
                self.minute(lib)
                lib.h_host_force_quality(1, q)                     # the air module's slots
                lib.h_host_force_quality(5, q)                     # the power module's slots
                _, v = self.reading(lib)
                self.assertIsNone(v['temperature_c'])
                self.assertIsNone(v['energy_in_mwh'])

    def test_calm_direction(self):
        lib, _ = self.station([DEVK_SHT45])
        self.minute(lib)
        _, v = self.minute(lib)
        self.assertEqual(v['wind_speed_ms'], 0.0)
        self.assertTrue(v.get('wind_calm'))                        # CALM below 0.5 m/s

    def test_a_gauge_above_100_percent_still_encodes(self):
        # The MAX17048 reports 101 % and more near full charge. The reading must still encode
        # (field 17 tops at 100), or every minute fails and the watchdog reboots the board.
        for soc in (101, 255):
            with self.subTest(soc=soc):
                lib, devs = self.station([DEVK_INA228, DEVK_MAX17048])
                lib.h_max17048_set(devs[DEVK_MAX17048], soc)
                self.minute(lib)
                _, v = self.minute(lib)
                self.assertEqual(v['soc_gauge_pct'], 100)

    def test_a_code_out_of_its_field_range_goes_invalid(self):
        # Any value the catalog cannot hold becomes INVALID, never a reading that fails to encode:
        # here a battery voltage above the field's 65.534 V.
        lib, devs = self.station([DEVK_INA228])
        lib.h_ina228_set(devs[DEVK_INA228], 70_000_000, 0)
        self.minute(lib)
        _, v = self.minute(lib)
        self.assertIsNone(v['batt_mv'])

    def test_no_stale_mean_after_a_quarantine(self):
        # A flapping module is quarantined for an hour while it keeps sampling. The first reading
        # after it rejoins must not report that hour-long window as the minute's value (WSMP-T3:
        # a long window is not a minute), and the next minute is normal again.
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
        self.assertIsNone(v['temperature_c'], 'the first reading after the quarantine is not a minute mean')
        _, v = self.minute(lib)
        self.assertEqual(v['temperature_c'], 42.5)

    def test_first_reading_after_a_warm_reset_is_a_minute(self):
        # The board's clock keeps counting across a warm reset (PROVISION, WIPE, a reflash), so the
        # modules start at a large clock_ms(). Their first window is the time since they started,
        # not since 0: the first reading has its temperature (found on the bench, 2026-10-19).
        type(self).count += 1
        path = Path(self.tmp.name)/f'map{self.count}.so'
        shutil.copy(self.library, path)
        lib = ctypes.CDLL(str(path))
        lib.h_advance(5_000_000)   # the clock before the modules start
        lib.h_add_device(DEVK_SHT45, ADDR[DEVK_SHT45])
        lib.h_init(7)
        lib.h_vane_mv(3_300)
        lib.h_host_init()
        _, v = self.minute(lib)
        self.assertEqual(v['temperature_c'], 42.5)

    def test_charger_states_map_to_pins(self):
        for pins, state_pins in ((0, 0), (PGOOD, PGOOD), (PGOOD | CHG, PGOOD | CHG)):
            with self.subTest(pins=pins):
                lib, _ = self.station([DEVK_INA228])
                lib.h_charger_pins(pins)
                self.minute(lib)
                codes, _ = self.minute(lib)
                self.assertEqual(codes[F['charger_pins']], state_pins)


if __name__ == '__main__':
    unittest.main()
