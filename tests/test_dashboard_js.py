"""Browser dashboard (ws0/static/app.js) under node with a stub DOM, fake timers and a scripted
gateway: rendering cost, the screen-reader live region, bucketed live appends and the history
request race. Skipped when node is not installed (CI images without it still run tests.test_web)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The harness: `node harness.js <app.js>` prints one JSON object of measurements.
HARNESS = r'''
// Node harness for ws0/static/app.js: a stub DOM, fake timers, a fake clock and a scripted gateway.
// Usage: node harness.js <path to app.js>   -> prints one JSON object of measurements and checks.
'use strict';
const fs = require('fs');
const vm = require('vm');

const APP = fs.readFileSync(process.argv[2], 'utf8');
const T0 = 1760400000;   // fake "now" (unix seconds)

function makeWorld() {
  const W = { created: 0, liveMutations: 0, fetches: [], historyQueue: null, clock: T0 * 1000 };
  // ---------------------------------------------------------------- stub DOM
  class Node {
    constructor(tag) { this.tagName = tag; this.childNodes = []; this.parentNode = null; this.attrs = {}; this.dataset = {}; this.style = {}; this.listeners = {}; this._text = ''; this.hidden = false; }
    get nodeType() { return this.tagName === '#text' ? 3 : 1; }
    get firstChild() { return this.childNodes[0] || null; }
    get children() { return this.childNodes.filter((c) => c.tagName !== '#text'); }
    _mut() { for (let n = this; n; n = n.parentNode) if (n.attrs['aria-live']) { W.liveMutations++; return; } }
    _adopt(k) {
      if (typeof k === 'string' || typeof k === 'number') { const t = new Node('#text'); t._text = String(k); W.created++; k = t; }
      if (k.tagName === '#fragment') { const kids = k.childNodes.slice(); k.childNodes = []; return kids.map((c) => this._adopt(c)); }
      if (k.parentNode) k.parentNode.removeChild(k);
      k.parentNode = this; return [k];
    }
    append(...kids) { for (const k of kids) this.childNodes.push(...this._adopt(k)); this._mut(); }
    appendChild(k) { this.append(k); return k; }
    prepend(...kids) { const add = []; for (const k of kids) add.push(...this._adopt(k)); this.childNodes.unshift(...add); this._mut(); }
    insertBefore(k, ref) { const add = this._adopt(k); const i = ref ? this.childNodes.indexOf(ref) : this.childNodes.length; this.childNodes.splice(i < 0 ? this.childNodes.length : i, 0, ...add); this._mut(); return k; }
    replaceChildren(...kids) { for (const c of this.childNodes) c.parentNode = null; this.childNodes = []; this.append(...kids); }
    removeChild(k) { const i = this.childNodes.indexOf(k); if (i >= 0) { this.childNodes.splice(i, 1); k.parentNode = null; this._mut(); } return k; }
    remove() { if (this.parentNode) this.parentNode.removeChild(this); }
    get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
    get nextSibling() { const p = this.parentNode; if (!p) return null; return p.childNodes[p.childNodes.indexOf(this) + 1] || null; }
    get textContent() { return this.tagName === '#text' ? this._text : this.childNodes.map((c) => c.textContent).join(''); }
    set textContent(v) { for (const c of this.childNodes) c.parentNode = null; this.childNodes = []; if (this.tagName === '#text') this._text = String(v); else if (String(v) !== '') { const t = new Node('#text'); t._text = String(v); t.parentNode = this; this.childNodes.push(t); } this._mut(); }
    get data() { return this._text; } set data(v) { this._text = String(v); this._mut(); }
    get nodeValue() { return this._text; } set nodeValue(v) { this._text = String(v); this._mut(); }
    setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'class') this.className = String(v); this._mut(); }
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
    hasAttribute(k) { return k in this.attrs; }
    removeAttribute(k) { delete this.attrs[k]; this._mut(); }
    set className(v) { this.attrs.class = v; } get className() { return this.attrs.class || ''; }
    get classList() { const n = this; return { contains: (c) => n.className.split(/\s+/).includes(c), add: (c) => { if (!this.contains(c)) n.className = `${n.className} ${c}`.trim(); }, remove: (c) => { n.className = n.className.split(/\s+/).filter((x) => x !== c).join(' '); }, toggle: (c, on) => { const has = n.className.split(/\s+/).includes(c); const want = on === undefined ? !has : on; n.className = want ? (has ? n.className : `${n.className} ${c}`.trim()) : n.className.split(/\s+/).filter((x) => x !== c).join(' '); return want; } }; }
    addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
    removeEventListener(t, f) { this.listeners[t] = (this.listeners[t] || []).filter((x) => x !== f); }
    fire(t, ev) { for (const f of this.listeners[t] || []) f(Object.assign({ preventDefault() {}, type: t }, ev)); }
    click() { this.fire('click'); }
    focus() {}
    getBoundingClientRect() { return { left: 0, top: 0, width: 600, height: 150 }; }
    get offsetWidth() { return 100; }
    get tBodies() { return this.childNodes.filter((c) => c.tagName === 'tbody'); }
    closest() { return null; }
    querySelector() { return null; }
  }
  const make = (tag) => { W.created++; return new Node(tag); };
  const byId = {};
  const body = new Node('body');
  const getEl = (id) => {
    if (!byId[id]) {
      const n = new Node(id === 'frames' ? 'table' : 'div');
      n.attrs.id = id;
      if (id === 'frames') n.append(new Node('tbody'));
      if (id === 'chips') n.attrs['aria-live'] = 'polite';   // as index.html (old layout)
      body.append(n);
      byId[id] = n;
    }
    return byId[id];
  };
  // ids that index.html marks aria-live: read from the real page next to app.js
  const html = fs.readFileSync(require('path').join(require('path').dirname(process.argv[2]), 'index.html'), 'utf8');
  const liveIds = [...html.matchAll(/id="([^"]+)"[^>]*aria-live=/g)].map((m) => m[1]);
  const ranges = ['3600', '86400', '604800', 'custom'].map((r) => { const b = new Node('button'); b.dataset.range = r; return b; });
  const document = {
    getElementById: (id) => { const n = getEl(id); if (liveIds.includes(id)) n.attrs['aria-live'] = 'polite'; else if (id === 'chips' && !liveIds.includes('chips')) delete n.attrs['aria-live']; return n; },
    createElement: make, createElementNS: (ns, tag) => make(tag),
    createTextNode: (t) => { W.created++; const n = new Node('#text'); n._text = String(t); return n; },
    createDocumentFragment: () => new Node('#fragment'),
    querySelectorAll: (sel) => (sel === '.ranges button' ? ranges : []),
    documentElement: { clientWidth: 1280, dataset: {} },
    body,
  };
  const store = () => { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }; };
  const session = store(); session.setItem('ws0.token', 'x'.repeat(43));
  const winListeners = {};
  const window = { sessionStorage: session, localStorage: store(), addEventListener: (t, f) => { (winListeners[t] = winListeners[t] || []).push(f); } };

  // ---------------------------------------------------------------- fake timers and clock
  let timers = [], nextId = 1, rafs = [];
  const setTimeout_ = (fn, ms) => { const id = nextId++; timers.push({ id, due: W.clock + (ms || 0), fn }); return id; };
  const setInterval_ = (fn, ms) => { const id = nextId++; timers.push({ id, due: W.clock + ms, fn, every: ms }); return id; };
  const clearTimeout_ = (id) => { timers = timers.filter((t) => t.id !== id); };
  const RealDate = Date;
  class FakeDate extends RealDate { constructor(...a) { if (a.length) super(...a); else super(W.clock); } static now() { return W.clock; } }
  W.rafCalls = 0;
  const raf = (fn) => { W.rafCalls++; const id = nextId++; rafs.push({ id, fn }); return id; };
  const caf = (id) => { rafs = rafs.filter((r) => r.id !== id); };

  // ---------------------------------------------------------------- scripted gateway
  let reads = [], chunks = [];
  const enc = new TextEncoder();
  W.push = (text) => { chunks.push(enc.encode(text)); while (reads.length && chunks.length) reads.shift()({ value: chunks.shift(), done: false }); };
  W.sse = (type, data, id) => W.push(`${id ? `id: ${id}\n` : ''}event: ${type}\ndata: ${JSON.stringify(data)}\n\n`);
  W.responses = {};
  const json = (v) => ({ status: 200, ok: true, json: async () => JSON.parse(JSON.stringify(v)) });
  const fetch = (url, opts) => {
    W.fetches.push({ url, at: W.clock, auth: opts && opts.headers && opts.headers.Authorization });
    if (url === '/v1/events') {
      return Promise.resolve({ status: 200, ok: true, body: { getReader: () => ({ read: () => new Promise((r) => { if (chunks.length) r({ value: chunks.shift(), done: false }); else reads.push(r); }) }) } });
    }
    const path = url.split('?')[0];
    if (path === '/v1/history') {
      if (W.historyQueue) return new Promise((resolve) => W.historyQueue.push({ url, resolve: (v) => resolve(json(v)) }));
      return Promise.resolve(json(W.responses.history(url)));
    }
    return Promise.resolve(json(W.responses[path]));
  };

  const ctx = {
    window, document, fetch, console: { warn() {}, log: console.log, error: console.error },
    setTimeout: setTimeout_, setInterval: setInterval_, clearTimeout: clearTimeout_, clearInterval: clearTimeout_,
    requestAnimationFrame: raf, cancelAnimationFrame: caf, Date: FakeDate,
    TextDecoder, TextEncoder, AbortController, Promise, Math, JSON, Object, Array, Number, String, Set, Map, Error, isFinite, encodeURIComponent,
  };
  W.flushRaf = () => { let n = 0; while (rafs.length && n++ < 20) { const r = rafs; rafs = []; for (const x of r) x.fn(W.clock); } };
  W.settle = async () => { for (let i = 0; i < 30; i++) await new Promise((r) => setImmediate(r)); };
  W.advance = async (ms) => {
    const end = W.clock + ms;
    for (;;) {
      await W.settle();
      timers.sort((a, b) => a.due - b.due);
      const t = timers[0];
      if (!t || t.due > end) break;
      W.clock = t.due;
      if (t.every) t.due += t.every; else timers.shift();
      t.fn();
      W.flushRaf();
    }
    W.clock = end;
    await W.settle();
    W.flushRaf();
    await W.settle();
  };
  W.resize = () => { for (const f of winListeners.resize || []) f(); };
  W.byId = getEl;
  W.find = (root, pred, out = []) => { if (pred(root)) out.push(root); for (const c of root.childNodes) W.find(c, pred, out); return out; };
  W.ranges = ranges;
  W.start = () => { vm.createContext(ctx); vm.runInContext(APP, ctx, { filename: 'app.js' }); };
  return W;
}

// ---------------------------------------------------------------- fixtures
const FIELDS = ['temperature_c', 'humidity_pct', 'pressure_hpa', 'wind_speed_ms', 'wind_gust_ms', 'wind_dir_deg', 'rain_tips', 'batt_mv'];
const LABELS = { temperature_c: 'Temperature', humidity_pct: 'Humidity', pressure_hpa: 'Pressure', wind_speed_ms: 'Wind speed', wind_gust_ms: 'Wind gust', wind_dir_deg: 'Wind direction', rain_tips: 'Rain tips', batt_mv: 'Battery voltage', th_samples: 'T/RH samples per minute' };
const UNITS = { temperature_c: '°C', humidity_pct: '%', pressure_hpa: 'hPa', wind_speed_ms: 'm/s', wind_gust_ms: 'm/s', wind_dir_deg: '°', rain_tips: null, batt_mv: 'mV', th_samples: null };
const value = (name, i) => (name === 'wind_dir_deg' ? (i * 37) % 360 : name === 'rain_tips' ? Math.floor(i / 10) : 10 + Math.sin(i / 50) * 5);
function history(from, to, opts = {}) {
  const fields = opts.fields || FIELDS;
  const step = opts.step || 60;
  const ts = [];
  for (let t = Math.ceil(from / step) * step; t < to; t += step) ts.push(t);
  const obs = { bucket_s: opts.obsBucket || 0, fields, units: Object.fromEntries(fields.map((f) => [f, UNITS[f]])), labels: Object.fromEntries(fields.map((f) => [f, LABELS[f]])), unknown_time_count: 0, t: ts.slice(), basis: ts.map(() => 'synchronized'), quality: ts.map(() => 'valid'), session: ts.map(() => 7), values: Object.fromEntries(fields.map((f) => [f, ts.map((_, i) => value(f, i))])) };
  const rb = opts.radioBucket || 0;
  const radio = { bucket_s: rb, t: ts.slice(), rssi_dbm: ts.map(() => -80), snr_db: ts.map(() => 9), rssi_min: ts.map(() => -80), frames: ts.map(() => (rb ? 5 : 1)), kind: ts.map(() => (rb ? null : 'obs')), outcome: ts.map(() => (rb ? { ack: 5 } : 'ack')), counter: ts.map((_, i) => (rb ? null : i)) };
  const receiver = { bucket_s: 0, t: ts.slice(), uptime_s: ts.map((_, i) => i * 60), forwarded: ts.map((_, i) => i), dropped: ts.map(() => 0), acks: ts.map((_, i) => i), diag: ts.map(() => 0), listening: ts.map(() => 1), relistens: ts.map(() => 0), uart_errors: ts.map(() => 0), stack_peak: ts.map(() => 900) };
  const diagnostics = ts.filter((_, i) => i % 15 === 0).map((t, i) => ({ received_at: t, epoch: 7, firmware_build: 'b1', reset_cause: 'power', uptime_s: i * 900, link: 'linked', energy_state: 'normal', journal_pending: 0, journal_lost_total: 0, missed_acks_since_boot: 0, crashes_since_power_up: 0, abandoned_total: 0, ack_rssi_dbm: -70, ack_snr_db: 8 }));
  return { from, to, server_time: to, observations: obs, diagnostics, radio, receiver, events: [{ id: 1, at: from + 60, source: 'gateway', kind: 'start', level: 'info', text: '#gateway start demo' }] };
}
function statusAt(t) {
  const obs = Object.fromEntries(FIELDS.map((f) => [f, value(f, 3)]));
  Object.assign(obs, { session: 7, sequence: 99, quality: 'valid', energy_state: 'normal', wind_calm: false });
  return {
    station: 'ws-test', mode: 'demo', alarm: null, node_counter: { max_node_counter: 5, counter_regression: 0 }, accepted_this_process: 3, rejected_this_process: 0, nacked_this_process: 0, host_clock: null,
    node_diagnostics: { received_at: t - 30, epoch: 7, firmware_build: 'b1', uptime_s: 1000, reset_cause: 'power', link: 'linked', energy_state: 'normal', journal_pending: 0, journal_lost_total: 0, journal_torn_slots: 0, abandoned_total: 0, missed_acks_since_boot: 0, rejected_replies_since_boot: 0, crashes_since_power_up: 0, ack_rssi_dbm: -70, ack_snr_db: 8 },
    receiver: { alive: true, last_seen: t - 5, uptime: 100, fw: 'rx1', forwarded: 1, dropped: 0, acks: 1, diag: 0, listening: '1', relistens: 0, uart_errors: 0, stack_peak: 900 },
    latest: { available: true, reason: 'fresh', fields_available: Object.fromEntries(FIELDS.map((f) => [f, true])), age_seconds: 10, received_at: t - 10, observation: obs, derived: {}, effective_sampled_at: t - 10, time_basis: 'synchronized', time_uncertainty_s: 0.5, units: Object.fromEntries(FIELDS.filter((f) => UNITS[f]).map((f) => [f, UNITS[f]])) },
  };
}
function parseRange(url) {
  const q = new URLSearchParams(url.split('?')[1]);
  return [Date.parse(q.get('from')) / 1000, Date.parse(q.get('to')) / 1000];
}
async function boot(W, histFn) {
  W.responses['/v1/status'] = statusAt(T0);
  W.responses['/v1/radio'] = { rows: [] };
  W.responses['/v1/gateway/events'] = { rows: [] };
  W.responses.history = histFn || ((url) => { const [f, t] = parseRange(url); return history(f, t); });
  W.start();
  await W.settle();
  W.sse('hello', { server_time: W.clock / 1000, resumed: false });
  await W.advance(1000);
}
const sensorTitles = (W) => W.find(W.byId('c-sensors'), (n) => n.className === 'ct').map((n) => n.textContent);
const chartBy = (W, box, title) => W.find(W.byId(box), (n) => n.tagName === 'figure').find((f) => W.find(f, (n) => n.className === 'ct')[0].textContent.startsWith(title));

async function main() {
  const out = {};
  // ---- 1/2: rendering cost
  {
    const W = makeWorld();
    await boot(W);
    out.charts = W.find(W.byId('c-sensors'), (n) => n.tagName === 'figure').length;
    let c = W.created; W.resize(); await W.advance(400); out.nodes_per_renderHistory = W.created - c;
    out.circles_after_render = W.find(W.byId('c-link'), (n) => n.tagName === 'circle').length + W.find(W.byId('c-sensors'), (n) => n.tagName === 'circle').length;
    c = W.created; W.byId('theme').click(); await W.advance(10); out.nodes_per_theme_toggle = W.created - c;
    // idle ticks: 10 s, no events
    c = W.created; let live = W.liveMutations; await W.advance(10000);
    out.nodes_per_idle_second = (W.created - c) / 10; out.live_region_mutations_per_idle_second = (W.liveMutations - live) / 10;
    // replay burst of N events (frames, gateway events, observations) in one chunk, as after a reconnect
    const N = 50;
    let text = '';
    for (let i = 0; i < N; i++) {
      const t = W.clock / 1000 - N + i;
      text += `id: r${i}\nevent: radio\ndata: ${JSON.stringify({ id: 1000 + i, received_at: t, kind: 'obs', counter: 500 + i, outcome: 'ack', rssi_dbm: -81, snr_db: 9, delivered: 1 })}\n\n`;
      text += `id: g${i}\nevent: gateway\ndata: ${JSON.stringify({ id: 1000 + i, at: t, source: 'rx', kind: 'relisten', level: 'warn', text: '#relisten' })}\n\n`;
      const rec = Object.assign(Object.fromEntries(FIELDS.map((f) => [f, 12])), { session: 7, sequence: 1000 + i, quality: 'valid', energy_state: 'normal', effective_sampled_at: t, time_basis: 'synchronized', received_at: t });
      const st = statusAt(t).latest;
      text += `id: o${i}\nevent: observation\ndata: ${JSON.stringify({ record: rec, latest: st })}\n\n`;
    }
    c = W.created; W.push(text); await W.settle(); W.flushRaf();
    out.replay_events = 3 * N;
    out.nodes_during_replay_before_timers = W.created - c;
    await W.advance(1000);
    out.nodes_for_replay_total = W.created - c;
    out.nodes_per_replayed_event = +(out.nodes_for_replay_total / (3 * N)).toFixed(1);
    out.history_fetches = W.fetches.filter((f) => f.url.startsWith('/v1/history')).length;
    // ages count up in place; a reading going stale is announced once
    const sub = () => W.find(W.byId('readings'), (n) => n.className === 'sub').map((n) => n.textContent)[0];
    const ageBefore = sub();
    live = W.liveMutations;
    await W.advance(200000);
    out.age_text = [ageBefore, sub()];
    out.live_region_mutations_on_stale = W.liveMutations - live;
    out.live_region_text = W.byId('chips-live').textContent;
    out.tile_labels = W.find(W.byId('readings'), (n) => n.className === 'label').map((n) => n.textContent);
    out.token_in_url = W.fetches.some((f) => /x{43}/.test(f.url));
  }
  // ---- 3(a): bucketed radio series must not get raw points
  {
    const W = makeWorld();
    await boot(W, (url) => { const [f, t] = parseRange(url); return history(f, t, { radioBucket: 60 }); });
    const pts = () => { const p = W.find(chartBy(W, 'c-link', 'Frames per'), (n) => n.tagName === 'path' && /\bc1\b/.test(n.className))[0]; return p ? (p.attrs.d.match(/[ML]/g) || []).length : 0; };
    const ys = () => { const p = W.find(chartBy(W, 'c-link', 'Frames per'), (n) => n.tagName === 'path' && /\bc1\b/.test(n.className))[0]; return new Set((p.attrs.d.match(/,(-?[\d.]+)/g) || [])).size; };
    const before = pts();
    const hist0 = W.fetches.filter((f) => f.url.startsWith('/v1/history')).length;
    for (let i = 0; i < 5; i++) {
      W.sse('radio', { id: 5000 + i, received_at: W.clock / 1000, kind: 'obs', counter: 9000 + i, outcome: 'ack', rssi_dbm: -81, snr_db: 9, delivered: 1 });
      await W.advance(10000);   // 5 frames over 50 s
    }
    const mid = W.fetches.filter((f) => f.url.startsWith('/v1/history')).length - hist0;
    await W.advance(30000);
    out.bucketed = { points_before: before, distinct_y_after: ys(), history_reloads_within_50s: mid, history_reloads_within_80s: W.fetches.filter((f) => f.url.startsWith('/v1/history')).length - hist0 };
  }
  // ---- 3(b): a slow earlier range must not overwrite a later one
  {
    const W = makeWorld();
    await boot(W);
    W.historyQueue = [];
    W.ranges[0].click();   // 1 h: temperature only
    W.ranges[2].click();   // 7 d: pressure only
    await W.settle();
    const [a, b] = W.historyQueue;
    W.historyQueue = null;
    const [bf, bt] = parseRange(b.url);
    b.resolve(history(bf, bt, { fields: ['pressure_hpa', 'th_samples'], step: 3600 }));
    await W.advance(10);
    const [af, at] = parseRange(a.url);
    a.resolve(history(af, at, { fields: ['temperature_c'] }));
    await W.advance(10);
    out.race = { sensor_titles: sensorTitles(W) };
  }
  console.log(JSON.stringify(out));
}
main().catch((e) => { console.error(e && e.stack || e); process.exit(1); });
'''


class DashboardScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node = shutil.which('node')
        if not node:
            raise unittest.SkipTest('node not installed')
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / 'harness.js'
            script.write_text(HARNESS)
            result = subprocess.run([node, str(script), str(ROOT / 'ws0' / 'static' / 'app.js')],
                                    capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise AssertionError(f'harness failed:\n{result.stderr}')
        cls.out = json.loads(result.stdout)

    def test_history_render_draws_dots_as_paths_not_one_circle_each(self):
        # 24 h at one point a minute, 8 sensor charts: was ~5,500 nodes with ~4,500 circles
        self.assertLess(self.out['nodes_per_renderHistory'], 2000)
        self.assertLessEqual(self.out['circles_after_render'], 20)   # hover dots only, one per series

    def test_theme_toggle_does_not_redraw(self):
        self.assertEqual(self.out['nodes_per_theme_toggle'], 0)

    def test_idle_tick_updates_ages_in_place(self):
        self.assertEqual(self.out['nodes_per_idle_second'], 0)
        self.assertEqual(self.out['live_region_mutations_per_idle_second'], 0)
        before, after = self.out['age_text']
        self.assertNotEqual(before, after)

    def test_state_change_is_announced_once(self):
        # the reading goes stale and the receiver silent: two announcements, not one per second
        self.assertLessEqual(self.out['live_region_mutations_on_stale'], 4)
        self.assertIn('Reading stale', self.out['live_region_text'])
        self.assertNotIn('ago', self.out['live_region_text'])

    def test_replay_burst_redraws_once(self):
        self.assertLess(self.out['nodes_per_replayed_event'], 20)   # was ~176

    def test_labels_come_from_the_gateway_catalog(self):
        self.assertIn('Rain tips', self.out['tile_labels'])
        self.assertEqual(self.out['race']['sensor_titles'], ['Pressure', 'T/RH samples per minute'])

    def test_bucketed_series_gets_no_raw_points_and_reloads_once_per_bucket(self):
        b = self.out['bucketed']
        self.assertEqual(b['distinct_y_after'], 1)   # every bucket still shows 5 frames
        self.assertEqual(b['history_reloads_within_50s'], 0)
        self.assertEqual(b['history_reloads_within_80s'], 1)

    def test_token_never_in_a_url(self):
        self.assertFalse(self.out['token_in_url'])


if __name__ == '__main__':
    unittest.main()
