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
                                 'descriptor_set_alarms': lambda self: [], 'modules': lambda self: None,
                                 'receiver_silent': lambda self, now=None: None})()
        mqtt = object.__new__(MQTT)
        mqtt.gateway, mqtt.client, mqtt.root = gateway, Client(), self.root
        mqtt.published, mqtt.published_at, mqtt.published_modules = None, 0.0, None
        mqtt.advertised, mqtt.advertised_types, mqtt.advertised_health, mqtt.advertised_alerts = set(), set(), set(), set()
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
                                                          'pack_temp_c', 'charger_cold_hold']))

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
        self.assertEqual(len(r['power_not_measured']), 16)
        # Every entity key, and charger_cold_hold (an alert, from the pack temperature).
        self.assertEqual(set(r['power_not_measured']), set(HEALTH_ENTITIES) | {'charger_cold_hold'})


if __name__ == '__main__':
    unittest.main()


def render(template, payload):
    """Evaluate the Jinja subset the discovery templates use ({{ a if b is not none else c }}) as Python,
    with value_json the decoded payload: Jinja calls a dict's .get exactly as Python does. A missing key
    read as value_json.key raises here (AttributeError), as it is an undefined-variable error in HA."""
    expression = template.strip().removeprefix('{{').removesuffix('}}').replace('is not none', 'is not None')
    class Json(dict):
        def __getattr__(self, name):
            if name not in self:
                raise AttributeError(name)
            return self[name]
    return eval(expression, {}, {'value_json': Json(payload)})   # noqa: S307 - our own templates only


class ObservationEntities(unittest.TestCase):
    """Discovery for the weather topic: missing pods, rain in mm, the UV index, wind direction."""
    cfg = {'station': 's1', 'mode': 'hardware', 'mqtt': {}}

    def entry(self, field):
        return discovery(self.cfg, [field])[f'homeassistant/sensor/s1_{field}/config']

    def test_a_missing_field_key_makes_the_entity_unavailable(self):
        """A pod unplugged (or a build without the sensor) leaves the key out of the weather payload: the
        entity must go unavailable, not raise a template error. null (a faulted sensor) does the same."""
        template = self.entry('pressure_hpa')['availability'][2]['value_template']
        self.assertIn("value_json.get('pressure_hpa')", template)
        self.assertEqual(render(template, {'temperature_c': 20.5}), 'offline')   # key absent
        self.assertEqual(render(template, {'pressure_hpa': None}), 'offline')    # sensor fault
        self.assertEqual(render(template, {'pressure_hpa': 1001.3}), 'online')
        self.assertIsNone(render(self.entry('pressure_hpa')['value_template'], {'temperature_c': 20.5}))
        from ws0.fields import DERIVED, MEASURED
        for field in (*MEASURED, *DERIVED):
            entry = self.entry(field)
            self.assertEqual(render(entry['availability'][2]['value_template'], {}), 'offline', field)
            self.assertIsNone(render(entry['value_template'], {}), field)

    def test_rain_in_mm_from_the_sen15901_tip_size(self):
        from ws0.fields import RAIN_MM_PER_TIP, derived, rain_mm
        self.assertEqual(RAIN_MM_PER_TIP, 0.2794)               # 0.011 in, SparkFun SEN-15901
        self.assertEqual((rain_mm(0), rain_mm(10), rain_mm(None)), (0.0, 2.794, None))
        self.assertEqual(derived({'rain_tips': 3})['rain_mm'], 0.8382)
        rain = self.entry('rain_mm')
        self.assertEqual((rain['unit_of_measurement'], rain['device_class'], rain['state_class']),
                         ('mm', 'precipitation', 'total_increasing'))
        self.assertNotIn('entity_category', rain)
        tips = self.entry('rain_tips')                           # the raw count stays, as a diagnostic
        self.assertEqual((tips['entity_category'], tips['state_class']), ('diagnostic', 'total_increasing'))

    def test_uv_index_from_ltr390_counts(self):
        """Datasheet: 2300 counts per UVI at gain 18, 20 bit. The node runs gain 3, 18 bit: 95.83 per UVI."""
        from ws0.fields import LTR390_COUNTS_PER_UVI, LTR390_WINDOW_FACTOR, derived, uv_index
        self.assertAlmostEqual(LTR390_COUNTS_PER_UVI, 2300 * 3 / 18 / 4)
        self.assertEqual(LTR390_WINDOW_FACTOR, 1.0)              # uncalibrated until the PTFE window is measured
        self.assertEqual((uv_index(0), uv_index(958), uv_index(None)), (0.0, 10.0, None))
        self.assertEqual(derived({'uva_raw': 479})['uv_index_est'], 5.0)
        uv = self.entry('uv_index_est')
        self.assertEqual((uv['unit_of_measurement'], uv['state_class']), ('UV index', 'measurement'))
        self.assertNotIn('entity_category', uv)
        self.assertEqual(self.entry('uva_raw')['entity_category'], 'diagnostic')   # raw counts stay diagnostic

    def test_wind_direction_is_an_angle(self):
        wind = self.entry('wind_dir_deg')
        self.assertEqual((wind['unit_of_measurement'], wind['device_class'], wind['state_class']),
                         ('°', 'wind_direction', 'measurement_angle'))


class Alerts(unittest.TestCase):
    """The gateway's alert binary sensors (…/alerts): on = problem, null = not known (unavailable)."""
    cfg = {'station': 's1', 'mode': 'hardware', 'mqtt': {}}
    now = 100_000.0

    def latest(self, age=30, reason='fresh', energy='normal'):
        return {'available': reason == 'fresh', 'reason': reason, 'age_seconds': age,
                'observation': {'energy_state': energy}}

    def report(self, **values):
        return phase_a_report(**values) | {'received_at': self.now - 60}

    def test_all_quiet(self):
        from ws0.service import alerts
        self.assertEqual(alerts(self.latest(), self.report(soc=80 * 256), False, self.now),
                         {'station_stale': False, 'battery_low': False, 'charger_fault': False,
                          'charger_cold_hold': None, 'receiver_silent': False})

    def test_station_stale(self):
        from ws0.service import alerts
        self.assertTrue(alerts(self.latest(age=181, reason='stale_or_clock_step'), None, False, self.now)['station_stale'])
        self.assertTrue(alerts({'available': False, 'reason': 'no_observation'}, None, False, self.now)['station_stale'])
        self.assertTrue(alerts(self.latest(age=None, reason='unknown_clock'), None, False, self.now)['station_stale'])
        # A fresh reading with a faulted sensor: the station is talking, so not stale.
        self.assertFalse(alerts(self.latest(reason='sensor_fault'), None, False, self.now)['station_stale'])

    def test_battery_low_from_soc_or_energy_state(self):
        from ws0.service import BATTERY_LOW_SOC_PCT, alerts
        low = lambda latest, report: alerts(latest, report, None, self.now)['battery_low']
        self.assertEqual(BATTERY_LOW_SOC_PCT, 20)
        self.assertTrue(low(self.latest(), self.report(soc=19 * 256)))
        self.assertFalse(low(self.latest(), self.report(soc=20 * 256)))
        self.assertTrue(low(self.latest(energy='conserve'), self.report(soc=60 * 256)))
        self.assertTrue(low(self.latest(energy='critical'), None))
        # Stale reading: its energy state no longer counts; the fresh health report's does.
        self.assertTrue(low(self.latest(age=900, reason='stale_or_clock_step', energy='normal'),
                            self.report(soc=0xFFFF, energy=3)))
        self.assertIsNone(low(self.latest(age=900, reason='stale_or_clock_step'), None))
        stale_report = phase_a_report(soc=5 * 256) | {'received_at': self.now - HEALTH_MAX_AGE_S - 1}
        self.assertFalse(low(self.latest(), stale_report))       # an old report's SOC is not used

    def test_charger_fault_and_cold_hold(self):
        from ws0.protocol import CHG_FAULT
        from ws0.service import alerts
        report = self.report(charger_status=CHG_POWER_GOOD | CHG_FAULT)
        self.assertTrue(alerts(self.latest(), report, False, self.now)['charger_fault'])
        self.assertTrue(alerts(self.latest(), report | {'charger_cold_hold': True}, False, self.now)['charger_cold_hold'])
        self.assertIsNone(alerts(self.latest(), self.report(charger_status=0xFF), False, self.now)['charger_fault'])

    def phase_c_report(self, pack_dc, stage=6, status=CHG_POWER_GOOD):
        """A phase C (TX stack) report: fitted 0x7F, the pack temperature from the charger's TS pin."""
        from ws0.protocol import CHG_STAGE_SHIFT
        return self.report(fitted=0x7F, pack_temp=pack_dc, charger_status=status | stage << CHG_STAGE_SHIFT,
                           chg_input_mv=6900, chg_input_ma=0, chg_batt_mv=3800, chg_temp=250)

    def test_cold_hold_end_to_end_from_a_phase_c_report(self):
        """The node reports a TS cold hold as power good, no fault, stage not_charging (6) with the pack
        temperature (App/charger.c): the gateway decodes it to charger_cold_hold, the alert goes on and
        its entity is advertised."""
        from ws0.protocol import CHG_FAULT
        from ws0.service import COLD_HOLD_BELOW_C, alerts
        self.assertEqual(COLD_HOLD_BELOW_C, 6.3)                   # VT1 falling, B 3950 on the EVM divider
        cold = self.phase_c_report(20)                               # 2.0 degC, not charging
        self.assertIs(cold['charger_cold_hold'], True)
        self.assertNotIn('charger_cold_hold', cold['power_not_measured'] + cold['power_sensor_faults'])
        self.assertTrue(alerts(self.latest(), cold, False, self.now)['charger_cold_hold'])
        self.assertIs(self.phase_c_report(250)['charger_cold_hold'], False)        # warm enough
        self.assertIs(self.phase_c_report(20, stage=2, status=CHG_POWER_GOOD | CHG_CHARGING)['charger_cold_hold'],
                      False)                                         # still charging: no hold
        self.assertIs(self.phase_c_report(20, stage=5)['charger_cold_hold'], False)  # terminated: a full pack
        self.assertIs(self.phase_c_report(20, status=CHG_POWER_GOOD | CHG_FAULT)['charger_cold_hold'], False)
        self.assertIs(self.phase_c_report(20, status=0)['charger_cold_hold'], False)  # no input: nothing to hold
        # An open thermistor: no pack temperature, so not known, and a sensor fault under the fitted bit.
        open_ntc = self.phase_c_report(-32768)
        self.assertIsNone(open_ntc['charger_cold_hold'])
        self.assertIn('charger_cold_hold', open_ntc['power_sensor_faults'])
        # Phase A has no pack temperature: not measured, and the alert is never advertised.
        self.assertIsNone(self.report()['charger_cold_hold'])
        self.assertIn('charger_cold_hold', self.report()['power_not_measured'])
        mqtt, published = HealthFreshness.publisher(HealthFreshness(), None)
        mqtt.advertise_alerts(self.report())
        self.assertNotIn('homeassistant/binary_sensor/s1_alert_charger_cold_hold/config', [t for t, _p, _r in published])
        mqtt.advertise_alerts(cold)
        self.assertIn('homeassistant/binary_sensor/s1_alert_charger_cold_hold/config', [t for t, _p, _r in published])

    def test_discovery_is_independent_of_station_availability(self):
        from ws0.service import ALERTS_ALWAYS, alert_discovery
        entries = alert_discovery(self.cfg)
        self.assertEqual(sorted(entries), sorted(f'homeassistant/binary_sensor/s1_alert_{k}/config' for k in ALERTS_ALWAYS))
        for key in ALERTS_ALWAYS:
            entry = entries[f'homeassistant/binary_sensor/s1_alert_{key}/config']
            self.assertEqual((entry['device_class'], entry['state_topic']), ('problem', 'weatherstation/v1/s1/alerts'))
            self.assertNotIn('entity_category', entry)
            topics = [a['topic'] for a in entry['availability']]
            self.assertEqual(topics, ['weatherstation/v1/s1/gateway_availability', 'weatherstation/v1/s1/alerts'])
            self.assertEqual(render(entry['value_template'], {key: True}), 'ON')
            self.assertEqual(render(entry['availability'][1]['value_template'], {key: None}), 'offline')
            self.assertEqual(render(entry['availability'][1]['value_template'], {}), 'offline')

    def test_cold_hold_is_advertised_once_a_report_carries_it(self):
        mqtt, published = HealthFreshness.publisher(HealthFreshness(), None)
        mqtt.advertise_alerts(self.report())
        self.assertNotIn('charger_cold_hold', {t.split('/')[2].removeprefix('s1_alert_') for t, _p, _r in published})
        published.clear()
        mqtt.advertise_alerts(self.report() | {'charger_cold_hold': False})
        self.assertEqual([t for t, _p, _r in published], ['homeassistant/binary_sensor/s1_alert_charger_cold_hold/config'])

    def test_tick_publishes_retained_alerts(self):
        import json
        mqtt, published = HealthFreshness.publisher(HealthFreshness(), None)
        mqtt.tick()
        alert = [json.loads(p) for t, p, retain in published if t == 'weatherstation/v1/s1/alerts' and retain]
        self.assertEqual(alert, [{'station_stale': True, 'battery_low': None, 'charger_fault': None,
                                  'charger_cold_hold': None, 'receiver_silent': None}])


class ReceiverSilent(unittest.TestCase):
    def gateway(self):
        from ws0.service import Gateway
        gateway = object.__new__(Gateway)
        gateway.receiver, gateway.expects_receiver, gateway.started = None, False, 1000.0
        return gateway

    def test_states(self):
        from ws0.service import RECEIVER_SILENT_S
        gateway = self.gateway()
        self.assertIsNone(gateway.receiver_silent(5000))                       # demo or not serving: not known
        gateway.expects_receiver = True
        self.assertFalse(gateway.receiver_silent(1000 + RECEIVER_SILENT_S))     # grace after start
        self.assertTrue(gateway.receiver_silent(1001 + RECEIVER_SILENT_S))      # never reported
        gateway.receiver = {'alive': True, 'last_seen': 2000.0}
        self.assertFalse(gateway.receiver_silent(2000 + RECEIVER_SILENT_S))
        self.assertTrue(gateway.receiver_silent(2001 + RECEIVER_SILENT_S))      # before the serial loop marks it
        gateway.receiver['alive'] = False
        self.assertTrue(gateway.receiver_silent(2001))
