"""MQTT credentials and connection diagnostics, portable across macOS, Linux and Windows."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ws0.protocol import CHG_CHARGING, CHG_POWER_GOOD, pack_diag
from ws0.service import (HEALTH_ENTITIES, HEALTH_KEYS, HEALTH_MAX_AGE_S, MQTT, discovery, health_discovery, health_fresh,
                         health_report, mqtt_password)


class PasswordSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_in_run_directory(self):
        (self.dir / 'mqtt-password').write_text('s3cret\n')
        (self.dir / 'mqtt-password').chmod(0o600)   # else the permission warning reaches real stderr
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('WS_MQTT_PASSWORD', None)
            self.assertEqual(mqtt_password(self.dir), 's3cret')   # trailing newline stripped

    def test_environment_wins(self):
        (self.dir / 'mqtt-password').write_text('from-file')
        with patch.dict(os.environ, {'WS_MQTT_PASSWORD': 'from-env'}):
            self.assertEqual(mqtt_password(self.dir), 'from-env')

    def test_none_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('WS_MQTT_PASSWORD', None)
            self.assertIsNone(mqtt_password(self.dir))

    @unittest.skipIf(sys.platform == 'win32', 'POSIX permission bits')
    def test_warns_when_readable_by_others(self):
        path = self.dir / 'mqtt-password'
        path.write_text('x')
        path.chmod(0o644)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), patch.dict(os.environ, {}, clear=False):
            os.environ.pop('WS_MQTT_PASSWORD', None)
            mqtt_password(self.dir)
        self.assertIn('readable by other users', err.getvalue())
        path.chmod(0o600)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            mqtt_password(self.dir)
        self.assertEqual(err.getvalue(), '')


class ConnectDiagnostics(unittest.TestCase):
    def test_refused_connection_is_logged(self):
        class Reason:
            is_failure = True
            def __str__(self): return 'Not authorized'
        publisher = object.__new__(MQTT)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            publisher.on_connect(None, None, None, Reason(), None)
        self.assertIn('mqtt connect refused: Not authorized', err.getvalue())


class StartAndClose(unittest.TestCase):
    def test_username_without_password_fails_at_start(self):
        """Refuse to start rather than connect with no password and fail vaguely later."""
        with tempfile.TemporaryDirectory() as tmp:
            gateway = type('G', (), {'directory': tmp,
                                     'cfg': {'station': 's', 'mqtt': {'username': 'weatherstation'}}})()
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop('WS_MQTT_PASSWORD', None)
                with self.assertRaises(ValueError) as exc:
                    MQTT(gateway)
            self.assertIn('mqtt-password', str(exc.exception))

    def test_close_survives_a_failed_final_publish(self):
        """wait_for_publish raises if the link drops; close must still stop the client."""
        calls = []
        class Info:
            def wait_for_publish(self, timeout=None):
                raise RuntimeError('The client is not currently connected.')
        class Client:
            def is_connected(self): return True
            def publish(self, *a, **k): return Info()
            def disconnect(self): calls.append('disconnect')
            def loop_stop(self): calls.append('loop_stop')
        publisher = object.__new__(MQTT)
        publisher.client, publisher.root = Client(), 'weatherstation/v1/s'
        publisher.close()
        self.assertEqual(calls, ['disconnect', 'loop_stop'])


class HealthDiscovery(unittest.TestCase):
    """Home Assistant entities for the health report's power keys (power telemetry design section 10.2)."""
    cfg = {'station': 's1', 'mode': 'simulation'}
    root = 'weatherstation/v1/s1'

    def test_own_namespace_on_the_diagnostics_topic(self):
        entries = health_discovery(self.cfg)
        self.assertEqual(len(entries), 15)
        for key, (component, _name, unit, ha_class) in HEALTH_ENTITIES.items():
            entry = entries[f'homeassistant/{component}/s1_diag_{key}/config']
            self.assertEqual((entry['unique_id'], entry['state_topic'], entry['entity_category']),
                             (f's1_diag_{key}', self.root + '/diagnostics', 'diagnostic'))
            self.assertIn(key, entry['value_template'])
            self.assertEqual(entry['availability_mode'], 'all')
            self.assertEqual(entry['availability'][0], {'topic': self.root + '/gateway_availability'})
            self.assertEqual(entry['availability'][1], {'topic': self.root + '/diagnostics/availability'})
            self.assertEqual(entry['availability'][2]['topic'], self.root + '/diagnostics')
            self.assertIn(f"value_json.get('{key}') is not none", entry['availability'][2]['value_template'])
            self.assertEqual((entry.get('unit_of_measurement'), entry.get('device_class')), (unit, ha_class))

    def test_components_and_classes(self):
        entries = {e['unique_id'].removeprefix('s1_diag_'): (topic.split('/')[1], e) for topic, e in
                   health_discovery(self.cfg).items()}
        binary = {k: e['device_class'] for k, (c, e) in entries.items() if c == 'binary_sensor'}
        self.assertEqual(binary, {'charger_charging': 'battery_charging', 'charger_input_power_ok': 'power',
                                  'charger_fault': 'problem'})
        for key in binary:
            self.assertNotIn('unit_of_measurement', entries[key][1])
            self.assertIn("'ON' if", entries[key][1]['value_template'])
        self.assertEqual(entries['charger_stage'][1]['options'],
                         ['precharge', 'cc', 'cv', 'topoff', 'terminated', 'not_charging'])
        self.assertEqual(entries['charger_active_input'][1]['options'], ['solar', 'usb_c', 'no_input'])
        self.assertEqual((entries['battery_soc_pct'][1]['device_class'], entries['battery_soc_rate_pct_h'][1]['unit_of_measurement']),
                         ('battery', '%/h'))
        self.assertEqual({k for k, (_c, e) in entries.items() if e.get('device_class') == 'temperature'},
                         {'power_monitor_temp_c', 'charger_temp_c', 'pack_temp_c'})

    def test_station_counters_stay_json_only(self):
        self.assertTrue(set(HEALTH_ENTITIES) < set(HEALTH_KEYS))
        for key in ('boots_since_power_up', 'tx_timeouts_since_boot', 'i2c_recoveries_since_boot', 'last_crash_pc',
                    'crashes_since_power_up', 'journal_pending', 'epoch'):
            self.assertNotIn(key, HEALTH_ENTITIES)
        self.assertEqual(health_discovery(self.cfg, ['epoch', 'boots_since_power_up']), {})

    def test_no_discovery_config_topic_is_generated_twice(self):
        """Every observation field and every health entity at once: no config topic and no unique_id
        repeats, so a health entity can never overwrite an observation entity (charger_input_mv)."""
        from ws0.fields import DERIVED, MEASURED
        observation = discovery(self.cfg, [*MEASURED, *DERIVED])
        health = health_discovery(self.cfg)
        topics = [*observation, *health]
        self.assertEqual(len(topics), len(set(topics)))
        uids = [e['unique_id'] for e in (*observation.values(), *health.values())]
        self.assertEqual(len(uids), len(set(uids)))
        self.assertIn('homeassistant/sensor/s1_charger_input_mv/config', observation)
        self.assertIn('homeassistant/sensor/s1_diag_charger_reported_input_mv/config', health)



def phase_a_report(**values):
    """A phase A health report as the gateway stores it: fitted 0x2F (VDDA, the INA228 die, the gauge,
    the CHG/PGOOD pins and ISET; design section 6.1)."""
    base = dict(epoch=1, uptime=600, pending=0, lost=0, torn=0, abandoned=0, no_ack=0, rejects=0, reset_cause=1,
                link=0, build=0, rssi=-60, snr=7, crashes=0, energy=1, fitted=0x2F, vdda_mv=3300, monitor_temp=250,
                soc=12800, soc_rate=10, charger_status=CHG_POWER_GOOD | CHG_CHARGING, chg_batt_ma=800)
    return health_report(pack_diag(**(base | values)))[0]


class HealthFreshness(unittest.TestCase):
    """Health-report entities go unavailable when the node stops sending (design section 10.2): a
    report is due every 15 minutes, so the newest one older than HEALTH_MAX_AGE_S is stale."""
    cfg = {'station': 's1', 'mode': 'simulation', 'mqtt': {}}
    root = 'weatherstation/v1/s1'

    def test_fresh_until_two_periods_and_slack(self):
        self.assertEqual(HEALTH_MAX_AGE_S, 1900)
        report = {'received_at': 10_000.0}
        self.assertTrue(health_fresh(report, 10_000.0))
        self.assertTrue(health_fresh(report, 10_000.0 + HEALTH_MAX_AGE_S - 1))
        self.assertFalse(health_fresh(report, 10_000.0 + HEALTH_MAX_AGE_S))
        self.assertFalse(health_fresh(report, 9_000.0))          # from the future: not trusted
        self.assertFalse(health_fresh(None, 10_000.0))
        self.assertFalse(health_fresh({'epoch': 1}, 10_000.0))

    def publisher(self, diag):
        published = []
        class Client:
            def is_connected(self): return True
            def publish(self, topic, payload, qos=0, retain=False): published.append((topic, payload, retain))
        class Store:
            def latest(self, station): return {'available': False}
            def latest_diagnostic(self, station): return diag
        gateway = type('G', (), {'cfg': self.cfg, 'store': Store(), 'counter_alarm': lambda self: {'alarm': False},
                                 'descriptor_set_alarms': lambda self: [], 'modules': lambda self: None})()
        mqtt = object.__new__(MQTT)
        mqtt.gateway, mqtt.client, mqtt.root = gateway, Client(), self.root
        mqtt.published, mqtt.published_at, mqtt.published_modules = None, 0.0, None
        mqtt.advertised, mqtt.advertised_types, mqtt.advertised_health = set(), set(), set()
        return mqtt, published

    def availability(self, published):
        return [p for t, p, retain in published if t == self.root + '/diagnostics/availability' and retain]

    def test_a_stale_report_publishes_offline(self):
        """The node browns out with the pack at 40 % and CHG asserted: the gateway stays up, the retained
        report stays, but its entities go unavailable once it is HEALTH_MAX_AGE_S old."""
        import time
        report = phase_a_report(soc=40 * 256) | {'received_at': time.time() - HEALTH_MAX_AGE_S - 5}
        mqtt, published = self.publisher(report)
        mqtt.tick()
        self.assertEqual(self.availability(published), ['offline'])
        report['received_at'] = time.time()
        published.clear()
        mqtt.tick()
        self.assertEqual(self.availability(published), ['online'])

    def test_phase_a_advertises_only_what_it_measures(self):
        """Phase A (fitted 0x2F) creates no entity for the slots it has no source for: the charger
        registers (stage, active input, reported input and battery voltage, die temperature) and the
        pack temperature. A fitted key that faults (a dead gauge) keeps its entity, unavailable."""
        mqtt, published = self.publisher(None)
        mqtt.advertise_health(phase_a_report(soc=0xFFFF, soc_rate=-0x8000))
        advertised = {t.split('/')[2].removeprefix('s1_diag_') for t, _p, _r in published}
        self.assertEqual(advertised, {'battery_soc_pct', 'battery_soc_rate_pct_h', 'charger_charging',
                                      'charger_input_power_ok', 'charger_fault', 'power_monitor_temp_c',
                                      'mcu_supply_mv', 'charger_reported_battery_ma'})


class HealthNoneReasons(unittest.TestCase):
    """The fitted byte tells a slot this build does not measure from a fitted source that failed
    (design section 6.1); the gateway lists the None keys by reason."""

    def test_phase_a_with_a_dead_gauge(self):
        r = phase_a_report(soc=0xFFFF, soc_rate=-0x8000)
        self.assertEqual(r['power_sensor_faults'], ['battery_soc_pct', 'battery_soc_rate_pct_h'])
        self.assertEqual(r['power_not_measured'], sorted(['charger_stage', 'charger_active_input',
                                                          'charger_reported_input_mv', 'charger_reported_input_ma',
                                                          'charger_reported_battery_mv', 'charger_temp_c',
                                                          'pack_temp_c']))

    def test_a_healthy_phase_a_report_has_no_fault(self):
        r = phase_a_report()
        self.assertEqual(r['power_sensor_faults'], [])
        self.assertNotIn('battery_soc_pct', r['power_not_measured'])

    def test_no_charger_status_with_the_pins_fitted_is_a_fault(self):
        r = phase_a_report(charger_status=0xFF, vdda_mv=0xFFFF)
        self.assertEqual(r['power_sensor_faults'], ['charger_charging', 'charger_fault', 'charger_input_power_ok',
                                                    'mcu_supply_mv'])

    def test_nothing_fitted_is_nothing_measured(self):
        r = health_report(pack_diag(epoch=1, uptime=1, pending=0, lost=0, torn=0, abandoned=0, no_ack=0, rejects=0,
                                    reset_cause=1, link=0, build=0, rssi=-60, snr=7, crashes=0, energy=1))[0]
        self.assertEqual(r['power_sensor_faults'], [])
        self.assertEqual(len(r['power_not_measured']), 15)
        self.assertEqual(set(r['power_not_measured']), set(HEALTH_ENTITIES))


if __name__ == '__main__':
    unittest.main()
