"""End-to-end check of the chain TX -> RX relay -> gateway: asks a running `ws0 serve` for the
latest observation and checks every station field (present, valid, in range) and its age.

The token comes only from the environment (WS0_API_TOKEN); this tool opens no file and no serial
port. One line a field (ok / FAIL / pending), then a summary. Exit 0: no FAIL. 1: a FAIL, a stale
or missing observation, an auth or connection error. 2: usage. Standard library only.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = 'http://127.0.0.1:8088'   # `ws0 serve` binds http_port 8088 on 127.0.0.1 by default
TIMEOUT_S = 5
# Battery, energy and rail fields of ws0/fields.py (catalog 11-17 and 26-30). The USB pair (32-33)
# and charger_pins are not in the set: the first is an optional extension, the second a pin state.
POWER = ('batt_mv', 'batt_current_ma', 'energy_in_mwh', 'energy_out_mwh', 'charge_in_mah',
         'charge_out_mah', 'soc_gauge_pct', 'load_mv', 'load_current_ma', 'charger_input_mv',
         'solar_mv', 'solar_current_ma')
RANGES = {'temperature_c': (-40, 60), 'humidity_pct': (0, 100), 'enclosure_temp_c': (-40, 60),
          'enclosure_rh_pct': (0, 100), 'pressure_hpa': (850, 1090), 'uva_raw': (0, None),
          'wind_speed_ms': (0, 75), 'rain_tips': (0, None)}
RANGES.update({name: (0, None) for name in POWER if name.startswith(('energy', 'charge_'))})
RANGES.update({'soc_gauge_pct': (0, 100), 'batt_mv': (0, None), 'load_mv': (0, None),
               'charger_input_mv': (0, None), 'solar_mv': (0, None)})


def fetch(url, token):
    """The parsed JSON of GET /v1/observations/latest; raises Failure with a one-line message."""
    request = urllib.request.Request(url.rstrip('/') + '/v1/observations/latest',
                                     headers={'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise Failure('gateway refused the token (401): check WS0_API_TOKEN') from None
        if exc.code == 404:
            raise Failure('no observation yet (404)') from None
        raise Failure(f'gateway answered HTTP {exc.code}') from None
    except (urllib.error.URLError, OSError):
        raise Failure(f'gateway not reachable at {url}') from None
    except ValueError:
        raise Failure('gateway sent a reply that is not JSON') from None


class Failure(Exception):
    pass


def check_field(name, record, power_pending):
    """(status, detail) for one field of the stored observation record."""
    if name not in record:
        return ('pending' if power_pending and name in POWER else 'FAIL'), 'absent'
    value = record[name]
    if name == 'wind_dir_deg' and value is None and record.get('wind_calm'):
        return 'ok', 'calm'
    if value is None:
        return ('pending' if power_pending and name in POWER else 'FAIL'), 'INVALID'
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 'FAIL', f'{value!r} is not a number'
    if name == 'wind_dir_deg':
        low, high = 0, 359
    elif name == 'wind_gust_ms':
        speed = record.get('wind_speed_ms')
        low, high = (speed if isinstance(speed, (int, float)) else 0), 75
    else:
        low, high = RANGES.get(name, (None, None))
    if (low is not None and value < low) or (high is not None and value > high):
        return 'FAIL', f'{value} outside {low}..{high if high is not None else "inf"}'
    return 'ok', str(value)


def check(reply, power_pending, max_age, now):
    """Report lines, and whether everything passed."""
    if not reply.get('available', True) and reply.get('reason') == 'no_observation':
        raise Failure('no observation yet')
    record = reply.get('observation')
    if not isinstance(record, dict):
        raise Failure('reply has no observation')
    lines, good = [], True
    stamp = reply.get('effective_sampled_at') or record.get('sampled_at')
    if stamp is None:
        lines.append('FAIL    age: observation has no timestamp')
        good = False
    else:
        age = now - stamp
        stale = not 0 <= age <= max_age
        good = good and not stale
        lines.append(f"{'stale' if stale else 'ok':<7} age: {age:.0f} s (max {max_age:g} s)")
    names = [*RANGES, 'wind_gust_ms', 'wind_dir_deg', *POWER]
    for name in dict.fromkeys(names):
        status, detail = check_field(name, record, power_pending)
        good = good and status != 'FAIL'
        lines.append(f'{status:<7} {name}: {detail}')
    return lines, good


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--url', default=DEFAULT_URL)
    parser.add_argument('--power-pending', action='store_true',
                        help='the power fields are expected INVALID (no INA228 rails wired yet)')
    parser.add_argument('--max-age', type=float, default=180, help='seconds (default 180)')
    args = parser.parse_args(argv)
    token = os.environ.get('WS0_API_TOKEN')
    if not token:
        print('set WS0_API_TOKEN to the gateway API token (it is read from the environment only)')
        return 2
    try:
        lines, good = check(fetch(args.url, token), args.power_pending, args.max_age, time.time())
    except Failure as exc:
        print(f'FAIL: {exc}')
        return 1
    print('\n'.join(lines))
    print('e2e: ' + ('all fields ok' if good else 'FAILED'))
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
