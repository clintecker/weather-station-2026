"""The gateway's descriptor sets (docs/module-protocol.md section 11.2, WSMP-E5 to E7), the current
set by the newest reading's generation, the two-station serial alarm and the module identities it
publishes (sensor module ports design, section 6.7). Sets are written byte by byte with
tests/test_wsmp_set.py's helpers."""
import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path

try:
    from toolchain import StationTest                       # python -m unittest discover -s tests
    import test_wsmp_set as T
except ImportError:
    from tests.toolchain import StationTest                 # python -m unittest tests.<module>
    from tests import test_wsmp_set as T

from ws0 import wsmp_registry
from ws0.descsets import DescriptorSets, module_discovery, modules_payload, station_key


def air(generation=1, serial=T.RECORD_SERIAL, id_flags=0x01, crc=0xDEADBEEF):
    return T.header(generation, 1, T.entry(1, 1, 2, serial, id_flags, crc, T.AIR_TH))


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'sets.sqlite3'
        self.sets = DescriptorSets(self.path)

    def tearDown(self):
        self.sets.close()
        self.tmp.cleanup()

    def test_an_accepted_set_survives_a_restart_with_its_registry_version(self):
        self.assertEqual(self.sets.accept('st', T.bench_set(7), 100)['outcome'], 'accepted')
        self.sets.close()
        self.sets = DescriptorSets(self.path)
        self.assertEqual([m.port for m in self.sets.set_of('st', 7).modules], [1, 2, 6])
        self.assertIsNone(self.sets.set_of('st', 8))
        self.assertEqual(self.sets.db.execute('SELECT registry_version FROM sets').fetchall(),
                         [(wsmp_registry.REGISTRY_VERSION,)])                      # WSMP-G4

    def test_the_current_set_is_the_newest_frames_generation_not_the_newest_arrival(self):
        self.sets.accept('st', air(1), 100)
        self.assertIsNone(self.sets.current('st'))                     # no frame has named a generation
        self.sets.note_generation('st', 1, counter=10)
        self.assertEqual(self.sets.current('st').generation, 1)
        self.sets.accept('st', air(2, crc=0x55), 200)                  # e.g. a late answer to a describe request
        self.assertEqual(self.sets.current('st').generation, 1)        # arrival does not make it current
        self.sets.note_generation('st', 2, counter=9)                  # an older frame: ignored
        self.assertEqual(self.sets.current('st').generation, 1)
        self.sets.note_generation('st', 2, counter=11)
        self.assertEqual(self.sets.current('st').generation, 2)
        self.sets.note_generation('st', 3, counter=12)                 # a generation not held (WSMP-E8 asks)
        self.assertIsNone(self.sets.current('st'))
        self.assertEqual(self.sets.current_generation('st'), 3)

    def test_a_health_report_names_the_generation_by_its_counter_too(self):
        # readings and health reports share one counter space; a health report has no sequence
        self.sets.accept('st', air(1), 100)
        self.sets.accept('st', air(2, crc=0x55), 100)
        self.sets.note_generation('st', 1, counter=20)                 # a reading
        self.sets.note_generation('st', 2, counter=21)                 # a health report after it
        self.assertEqual(self.sets.current('st').generation, 2)
        self.sets.note_generation('st', 1, counter=19)                 # a delayed reading from before
        self.assertEqual(self.sets.current('st').generation, 2)

    def test_the_same_set_again_is_a_duplicate(self):
        self.sets.accept('st', air(), 100)
        self.assertEqual(self.sets.accept('st', air(), 101)['outcome'], 'duplicate')
        self.assertEqual(self.sets.alarms('st'), [])

    def test_wsmp_e5_a_bad_set_is_kept_for_diagnosis_not_used(self):
        bad = air()[:-1]
        r = self.sets.accept('st', bad, 100)
        self.assertEqual((r['outcome'], r['detail'].split(':')[0]), ('invalid', 'WSMP_ELEN'))
        self.assertEqual(self.sets.db.execute('SELECT reason, raw FROM refused').fetchall(), [('invalid', bad)])

    def test_wsmp_e6_a_different_set_under_a_held_generation_is_an_alarm_and_the_first_stays(self):
        self.sets.accept('st', air(), 100)
        self.assertEqual(self.sets.accept('st', air(crc=0x1234), 101)['outcome'], 'conflict')
        self.sets.note_generation('st', 1, 1)
        self.assertEqual(self.sets.current('st').modules[0].record_crc, 0xDEADBEEF)
        self.assertEqual([a['reason'] for a in self.sets.alarms('st')], ['conflict'])

    def test_wsmp_e7_a_failed_check_is_stored_with_an_alarm_and_not_used(self):
        cases = {'registry': T.header(2, 1, T.entry(1, 1, 2, T.RECORD_SERIAL, 0x01, 0, T.AIR_TH[6:] + T.AIR_TH[:6])),
                 'namespace': air(3, serial=T.PORT_SERIAL),                      # a port serial, source record
                 'type twice': T.header(4, 2, T.entry(1, 1, 2, T.RECORD_SERIAL, 0x01, 0, T.AIR_TH)
                                        + T.entry(4, 1, 2, T.RECORD_SERIAL + 1, 0x01, 0, T.AIR_TH))}
        for name, raw in cases.items():
            with self.subTest(name):
                r = self.sets.accept('st', raw, 100)
                self.assertEqual(r['outcome'], 'registry')
                self.assertIsNone(self.sets.set_of('st', r['generation']))
        self.assertEqual([a['reason'] for a in self.sets.alarms('st')], ['registry'] * 3)

    def test_reads_do_not_wait_for_the_writer_lock(self):
        self.sets.accept('st', air(), 100)
        self.sets.note_generation('st', 1, 1)
        got = []
        with self.sets.lock:                                    # a write in progress on another thread
            t = threading.Thread(target=lambda: got.append(self.sets.current('st').generation))
            t.start()
            t.join(5)
        self.assertEqual(got, [1])

    def test_one_serial_in_two_live_stations_for_over_10_minutes_is_an_alarm(self):
        for st in ('a', 'b'):
            self.sets.accept(st, air(), 0)
            self.sets.note_generation(st, 1, 1)
        self.assertEqual(self.sets.serial_alarms({'a': 0, 'b': 0}, 0), [])
        self.assertEqual(self.sets.serial_alarms({'a': 590, 'b': 590}, 600), [])     # exactly 10 min: not yet
        self.assertEqual(self.sets.serial_alarms({'a': 595, 'b': 595}, 601),
                         [{'serial': T.RECORD_SERIAL, 'stations': ['a', 'b'], 'since': 0}])
        self.assertEqual(self.sets.serial_alarms({'a': 1300, 'b': 601}, 1300), [])   # b not heard: forgotten
        self.assertEqual(self.sets.serial_alarms({'a': 1300, 'b': 1300}, 1300), [])  # it starts again

    def test_namespace_0_serials_repeat_across_stations_by_design(self):
        for st in ('a', 'b'):
            self.sets.accept(st, air(serial=T.PORT_SERIAL, id_flags=0x00, crc=0), 0)
            self.sets.note_generation(st, 1, 1)
        self.sets.serial_alarms({'a': 0, 'b': 0}, 0)
        self.assertEqual(self.sets.serial_alarms({'a': 700, 'b': 700}, 700), [])


class Publish(unittest.TestCase):
    def test_the_modules_payload_is_by_type_id_with_source_status_and_crc(self):
        s = T.wsmp_set.unpack(T.bench_set())
        self.assertEqual(modules_payload(s), {
            'air_th': {'port': 1, 'type': 1, 'serial': '0123456789abcdef', 'serial_source': 'record',
                       'record_status': 'applied', 'no_record': False, 'record_crc': 'deadbeef'},
            'pressure': {'port': 2, 'type': 2, 'serial': '020001000badcafe', 'serial_source': 'sensor',
                         'record_status': 'BLANK', 'no_record': True, 'record_crc': '00000000'},
            'wind': {'port': 6, 'type': 6, 'serial': f'{T.PORT_SERIAL:016x}', 'serial_source': 'port',
                     'record_status': 'none', 'no_record': False, 'record_crc': '00000000'}})   # a meter: no record
        self.assertIsNone(modules_payload(None))                               # no current set
        self.assertEqual(modules_payload(T.wsmp_set.unpack(T.header(1, 0, b''))), {})   # an empty set

    def test_discovery_is_one_diagnostic_sensor_per_type_id_with_safe_templates(self):
        cfg = {'station': 'sim', 'mode': 'simulation'}
        (topic, e), = module_discovery(cfg, ['air_th'], 'weatherstation/v1/sim').items()
        self.assertEqual(topic, 'homeassistant/sensor/sim_module_air_th/config')
        self.assertEqual((e['unique_id'], e['entity_category'], e['state_topic']),
                         ('sim_module_air_th', 'diagnostic', 'weatherstation/v1/sim/modules'))
        self.assertEqual(e['value_template'], "{{ value_json.get('air_th', {}).get('record_status') }}")
        self.assertEqual(e['json_attributes_template'], "{{ value_json.get('air_th', {}) | tojson }}")
        self.assertIn("'air_th' in value_json", e['availability'][1]['value_template'])

    def test_the_station_key_is_the_id_and_a_key_fingerprint(self):
        self.assertEqual(station_key(9, bytes(16)), '9:d3e9825756bd4e64')   # SHA-256(b'ws0-station-key\0' + key)
        self.assertNotEqual(station_key(9, bytes(16)), station_key(9, b'\1' * 16))   # a re-key: new space


class Gateway(StationTest):
    def mqtt(self):
        try:
            from test_stage0 import fake_mqtt
        except ImportError:
            from tests.test_stage0 import fake_mqtt
        return fake_mqtt(self.gateway)

    def published(self, mqtt, suffix):
        return [json.loads(a[1]) for a, _ in mqtt.client.messages if a[0].endswith(suffix)]

    def test_the_gateway_publishes_the_current_sets_modules(self):
        mqtt = self.mqtt()
        self.assertEqual(self.gateway.receive_descriptor_set(T.bench_set(3), 100)['outcome'], 'accepted')
        mqtt.publish_modules()
        self.assertEqual(mqtt.client.messages, [])                     # no reading has named generation 3
        self.gateway.note_generation(3, counter=1)
        mqtt.publish_modules()
        topics = [a[0] for a, _ in mqtt.client.messages]
        self.assertEqual(sum(t.startswith('homeassistant/sensor/') for t in topics), 3)
        self.assertEqual(self.published(mqtt, '/modules')[-1]['pressure']['record_status'], 'BLANK')
        n = len(mqtt.client.messages)
        mqtt.publish_modules()                                          # unchanged: nothing sent
        self.assertEqual(len(mqtt.client.messages), n)

    def test_an_empty_current_set_replaces_a_stale_retained_payload(self):
        mqtt = self.mqtt()
        self.gateway.receive_descriptor_set(T.bench_set(3), 100)
        self.gateway.note_generation(3, counter=1)
        mqtt.publish_modules()
        self.gateway.receive_descriptor_set(T.header(4, 0, b''), 200)   # every module left
        self.gateway.note_generation(4, counter=2)
        mqtt.publish_modules()
        self.assertEqual(self.published(mqtt, '/modules')[-1], {})

    def test_no_current_set_clears_the_retained_payload_once(self):
        from ws0.service import MODULES_UNPUBLISHED
        mqtt = self.mqtt()
        mqtt.published_modules = MODULES_UNPUBLISHED                     # a fresh connection
        mqtt.publish_modules()
        mqtt.publish_modules()
        self.assertEqual([(a[0], a[1], kw.get('retain')) for a, kw in mqtt.client.messages],
                         [('weatherstation/v1/simulation-01/modules', '', True)])   # an empty retained clears
        self.gateway.receive_descriptor_set(T.bench_set(3), 100)
        self.gateway.note_generation(3, counter=1)
        mqtt.publish_modules()
        self.gateway.note_generation(9, counter=2)                       # a generation not held: no current set
        mqtt.publish_modules()
        self.assertEqual(mqtt.client.messages[-1][0], ('weatherstation/v1/simulation-01/modules', ''))

    def test_e6_and_e7_alarms_reach_stderr_and_the_diagnostics_topic(self):
        self.gateway.receive_descriptor_set(air(1), 100)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.gateway.receive_descriptor_set(air(1, crc=0x77), 101)                   # E6
            self.gateway.receive_descriptor_set(air(2, serial=T.PORT_SERIAL), 102)       # E7
        self.assertIn('#gateway alarm descriptor set conflict', err.getvalue())
        self.assertIn('#gateway alarm descriptor set registry', err.getvalue())
        mqtt = self.mqtt()
        mqtt.tick()
        diag = self.published(mqtt, '/diagnostics')[-1]
        self.assertEqual([a['reason'] for a in diag['descriptor_set_alarms']], ['registry', 'conflict'])


if __name__ == '__main__':
    unittest.main()
