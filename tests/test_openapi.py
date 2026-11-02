"""docs/openapi.json against the gateway (power telemetry design sections 5, 6.1 and 10.2): the
Observation schema has exactly the catalog fields (fields.MEASURED), the base keys, wind_calm and
qualifiers, each catalog field with its unit and decoded range; the HealthReport schema has exactly
the keys service.receive_diagnostic stores; and the records, reports, history and status that a
live gateway serves match their schemas."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

try:                                        # first: sets WS0_UNSAFE_FAST_FSYNC before ws0 is imported
    from toolchain import StationTest
except ImportError:
    from tests.toolchain import StationTest
import gateway
from ws0 import fields, web
from ws0.protocol import CHARGER_INPUTS, CHARGER_STAGES, pack_diag
from ws0.service import HEALTH_ENTITIES, HEALTH_KEYS, Gateway

ROOT = Path(__file__).resolve().parent.parent
SPEC = json.loads((ROOT / 'docs' / 'openapi.json').read_text())
SCHEMAS = SPEC['components']['schemas']
V5_KEYS = dict(epoch=7, uptime=900, pending=0, lost=0, torn=0, abandoned=0, no_ack=0, rejects=0, reset_cause=1,
               link=0, build=0x5eed0001, rssi=-80, snr=9, crashes=0, energy=1)


def resolve(schema):
    """A schema with its $ref followed."""
    while '$ref' in schema:
        schema = SCHEMAS[schema['$ref'].rsplit('/', 1)[1]]
    return schema


def properties(schema):
    """Every property a schema names, through $ref and allOf."""
    schema = resolve(schema)
    out = dict(schema.get('properties', {}))
    for part in schema.get('allOf', ()):
        out |= properties(part)
    return out


def type_ok(value, kind):
    checks = {'null': value is None, 'boolean': isinstance(value, bool), 'string': isinstance(value, str),
              'integer': isinstance(value, int) and not isinstance(value, bool),
              'number': isinstance(value, (int, float)) and not isinstance(value, bool),
              'object': isinstance(value, dict), 'array': isinstance(value, list)}
    return checks[kind]


def problems(value, schema, where='$'):
    """The ways a value breaks a schema: the subset of JSON Schema this file uses (type, enum,
    const, minimum, maximum, required, properties, items, allOf, oneOf, $ref)."""
    schema = resolve(schema)
    out = []
    for part in schema.get('allOf', ()):
        out += problems(value, part, where)
    if 'oneOf' in schema and sum(not problems(value, s, where) for s in schema['oneOf']) != 1:
        out.append(f'{where}: not exactly one of oneOf')
    kinds = schema.get('type')
    if kinds and not any(type_ok(value, k) for k in ([kinds] if isinstance(kinds, str) else kinds)):
        return out + [f'{where}: {value!r} is not {kinds}']
    if 'enum' in schema and value not in schema['enum']:
        out.append(f'{where}: {value!r} not in {schema["enum"]}')
    if 'const' in schema and value != schema['const']:
        out.append(f'{where}: {value!r} != {schema["const"]}')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get('minimum', value) or value > schema.get('maximum', value):
            out.append(f'{where}: {value!r} outside {schema.get("minimum")}..{schema.get("maximum")}')
    if isinstance(value, dict):
        out += [f'{where}: missing {k}' for k in schema.get('required', ()) if k not in value]
        for k, sub in schema.get('properties', {}).items():
            if k in value:
                out += problems(value[k], sub, f'{where}.{k}')
    if isinstance(value, list) and 'items' in schema:
        for i, item in enumerate(value):
            out += problems(item, schema['items'], f'{where}[{i}]')
    return out


def stored_health_keys():
    """The keys receive_diagnostic hands the store for a report built with pack_diag."""
    stored = []
    stub = SimpleNamespace(check_counter=lambda *a: None, cfg={'station': 'station-01'},
                           store=SimpleNamespace(diagnostic=lambda station, report, now: stored.append(report)),
                           telemetry=SimpleNamespace(diagnostic=lambda report, now: None))
    Gateway.receive_diagnostic(stub, b'', pack_diag(**V5_KEYS), 0)
    return set(stored[0])


class SchemaShape(unittest.TestCase):
    def test_version_bumped_for_protocol_6(self):
        major, minor, _ = (int(n) for n in SPEC['info']['version'].split('.'))
        self.assertGreaterEqual((major, minor), (0, 4))

    def test_every_ref_resolves(self):
        text = json.dumps(SPEC)
        for name in {part.split('"')[0] for part in text.split('"#/components/schemas/')[1:]}:
            self.assertIn(name, SCHEMAS)

    def test_observation_properties_are_the_catalog_and_base_keys(self):
        expected = set(fields.MEASURED) | gateway.BASE_KEYS | {'wind_calm', 'qualifiers'}
        self.assertEqual(set(SCHEMAS['Observation']['properties']), expected)
        self.assertEqual(set(SCHEMAS['Observation']['required']), gateway.BASE_KEYS)

    def test_each_catalog_field_has_its_unit_range_and_null(self):
        props = SCHEMAS['Observation']['properties']
        for f in fields.FIELDS:
            if f.name == 'qualifiers':
                continue
            with self.subTest(field=f.name):
                p = props[f.name]
                self.assertIn('null', p['type'])     # null = INVALID
                self.assertIn('integer' if f.scale == 1 else 'number', p['type'])
                self.assertEqual((p['minimum'], p['maximum']), (f.value(0), f.value(f.max)))
                self.assertEqual(p.get('x-unit', ''), f.unit)
                self.assertEqual(p['x-field-index'], f.index)
                self.assertEqual(p.get('x-counter', False), f.counter)
                self.assertEqual(p.get('x-diagnostic', False), f.name in fields.DIAGNOSTIC_FIELDS)
                self.assertEqual(p['title'], fields.LABELS[f.name])

    def test_battery_current_is_signed(self):
        p = SCHEMAS['Observation']['properties']['batt_current_ma']
        self.assertEqual((p['minimum'], p['maximum']), (-32768, 32766))
        self.assertIn('+ into the cell (charging)', p['description'])
        self.assertIn('absent = not measured in this build', SCHEMAS['Observation']['description'].lower())
        self.assertIn('null = invalid', SCHEMAS['Observation']['description'].lower())

    def test_retired_fields_are_deprecated(self):
        props = SCHEMAS['Observation']['properties']
        self.assertEqual({n for n, p in props.items() if p.get('deprecated')}, {'soc_gauge_pct', 'charger_pins'})

    def test_health_report_properties_are_the_stored_keys(self):
        keys = stored_health_keys()
        self.assertEqual(keys, set(HEALTH_KEYS))
        self.assertEqual(set(SCHEMAS['HealthReport']['properties']), keys)
        self.assertEqual(set(SCHEMAS['HealthReport']['required']), keys)
        self.assertFalse(keys & set(fields.MEASURED))

    def test_charger_enums_follow_the_protocol(self):
        props = SCHEMAS['HealthReport']['properties']
        self.assertEqual(props['charger_stage']['enum'], [*(s for s in CHARGER_STAGES if s), None])
        self.assertEqual(props['charger_active_input']['enum'], [*(s for s in CHARGER_INPUTS if s), None])
        self.assertEqual(props['last_crash_pc']['pattern'], '^[0-9a-f]{8}$')

    def test_gateway_docs_name_every_key(self):
        readme = (ROOT / 'ws0' / 'README.md').read_text()
        runbook = (ROOT / 'docs' / 'runbook-home-assistant.md').read_text()
        dashboard = (ROOT / 'docs' / 'web-dashboard.md').read_text()
        for key in HEALTH_KEYS:
            self.assertIn(f'`{key}`', readme, key)
        for key in HEALTH_ENTITIES:
            self.assertIn(f'`{key}`', runbook, key)
        for name in ('batt_mv', 'batt_current_ma', 'load_mv', 'load_current_ma', 'charger_input_mv', 'solar_mv',
                     'solar_current_ma', 'usb_mv', 'usb_current_ma'):
            self.assertIn(f'`{name}`', dashboard, name)
            self.assertIn(f'`{name}`', runbook, name)

    def test_checker_catches_a_wrong_value(self):     # the checker below is not vacuous
        self.assertTrue(problems({'batt_current_ma': -40000}, SCHEMAS['Observation']))
        self.assertTrue(problems({'charger_stage': 'bulk'}, SCHEMAS['HealthReport']))


class ServedShapes(StationTest):
    """What a gateway serves, against its schema."""
    def setUp(self):
        super().setUp()
        self.record = self.node.sample(1_700_000_000)
        self.node.acknowledge(self.gateway.receive(self.node.packet(self.record), 1_700_000_001))
        self.gateway.receive(self.node.diagnostic(1_700_000_010), 1_700_000_010)

    def check(self, value, name):
        self.assertEqual(problems(value, {'$ref': f'#/components/schemas/{name}'}), [])

    def test_observation_row(self):
        rows = self.gateway.store.history(self.cfg['station'])
        self.assertEqual(len(rows), 1)
        self.assertLessEqual(set(rows[0]), set(properties({'$ref': '#/components/schemas/ObservationRow'})))
        self.check(rows[0], 'ObservationRow')

    def test_latest_and_status(self):
        status = self.gateway.status()
        self.assertEqual(set(status), set(SCHEMAS['Status']['properties']))
        self.assertLessEqual(set(status['latest']), set(SCHEMAS['LatestObservation']['properties']))
        self.check(status, 'Status')

    def test_diagnostic_row(self):
        row = self.gateway.store.latest_diagnostic(self.cfg['station'])
        self.assertEqual(set(row), set(properties({'$ref': '#/components/schemas/DiagnosticRow'})))
        self.check(row, 'DiagnosticRow')

    def test_history(self):
        h = web.history(self.gateway, 1_699_999_000, 1_700_001_000)
        self.assertEqual(set(h), set(SCHEMAS['History']['properties']))
        for key, name in (('observations', 'ObservationSeries'), ('radio', 'RadioSeries'),
                          ('receiver', 'ReceiverSeries')):
            self.assertEqual(set(h[key]), set(SCHEMAS[name]['properties']), key)
        self.check(h, 'History')


if __name__ == '__main__':
    unittest.main()
