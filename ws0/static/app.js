/* Weather station dashboard (docs/web-dashboard.md). Plain JS, no libraries, no build step.
 *
 * Security: the API token lives only in sessionStorage and in Authorization headers. Text from
 * the device, the logs or the API is only ever inserted with textContent / setAttribute, never
 * as HTML.
 *
 * Real time: one fetch() stream of Server-Sent Events from GET /v1/events (EventSource cannot
 * send an Authorization header). On reconnect the last event id goes back as Last-Event-ID; the
 * gateway replays what was missed, or sends `resync`, and then the page reloads its snapshot.
 */
'use strict';
(() => {
  const TOKEN_KEY = 'ws0.token';
  const THEME_KEY = 'ws0.theme';
  const STALE_S = 180;          // gateway's freshness limit for a reading (gateway.py latest())
  const RX_SILENT_S = 180;      // three missed 60 s #alive reports
  const DIAG_OVERDUE_S = 1900;  // two 15-minute health reports plus slack
  const WATCHDOG_MS = 45000;    // no byte (heartbeats included) for this long: reconnect
  const FIELDS = [
    ['temperature_c', 'Temperature'], ['humidity_pct', 'Humidity'], ['pressure_hpa', 'Pressure'],
    ['wind_speed_ms', 'Wind speed'], ['wind_gust_ms', 'Wind gust'], ['wind_dir_deg', 'Wind direction'],
    ['rain_tips', 'Rain tips (since boot)'], ['uv_index', 'UV index'], ['irradiance_wm2', 'Irradiance'],
    ['uva_raw', 'UVA (raw)'], ['batt_mv', 'Battery voltage'], ['batt_current_ma', 'Battery current'],
    ['energy_in_mwh', 'Energy in (since boot)'], ['energy_out_mwh', 'Energy out (since boot)'],
    ['charge_in_mah', 'Charge in (since boot)'], ['charge_out_mah', 'Charge out (since boot)'],
    ['soc_gauge_pct', 'State of charge'], ['charger_pins', 'Charger pins'],
    ['enclosure_temp_c', 'Enclosure temperature'], ['enclosure_rh_pct', 'Enclosure humidity'],
  ];
  const LABEL = Object.fromEntries(FIELDS);
  const MAX_FRAMES = 40;
  const MAX_EVENTS = 60;

  const S = {
    token: null, running: false, lastId: null, skew: 0, conn: 'off', status: null,
    frames: [], events: [], hist: null, range: { span: 86400 }, abort: null, epoch: 0,
  };

  // ---------------------------------------------------------------- DOM helpers (text only)
  const $ = (id) => document.getElementById(id);
  function el(tag, props, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'text') e.textContent = String(v);
      else if (k === 'class') e.className = v;
      else e.setAttribute(k, String(v));
    }
    for (const kid of kids) if (kid !== null && kid !== undefined) e.append(kid);  // strings become text nodes
    return e;
  }
  const NS = 'http://www.w3.org/2000/svg';
  function sv(tag, attrs, text) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) e.setAttribute(k, String(v));
    if (text !== undefined) e.textContent = String(text);
    return e;
  }
  const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); };

  // ---------------------------------------------------------------- formatting
  const now = () => Date.now() / 1000 + S.skew;
  function fmtAge(s) {
    if (s === null || s === undefined || !isFinite(s)) return '—';
    if (s < 0) return 'in the future';
    if (s < 90) return `${Math.round(s)} s ago`;
    if (s < 5400) return `${Math.round(s / 60)} min ago`;
    if (s < 172800) return `${(s / 3600).toFixed(1)} h ago`;
    return `${(s / 86400).toFixed(1)} d ago`;
  }
  function fmtTime(t, withDate) {
    if (t === null || t === undefined) return '—';
    const d = new Date(t * 1000);
    const opts = { hour: '2-digit', minute: '2-digit', second: '2-digit' };
    if (withDate) Object.assign(opts, { month: 'short', day: 'numeric' });
    return d.toLocaleString(undefined, opts);
  }
  function fmtNum(v, digits) {
    if (v === null || v === undefined) return '—';
    if (typeof v !== 'number') return String(v);
    return v.toLocaleString(undefined, { maximumFractionDigits: digits === undefined ? 2 : digits });
  }
  function fmtDuration(s) {
    if (s === null || s === undefined) return '—';
    s = Number(s);
    if (s < 120) return `${s} s`;
    if (s < 7200) return `${Math.round(s / 60)} min`;
    if (s < 172800) return `${(s / 3600).toFixed(1)} h`;
    return `${(s / 86400).toFixed(1)} d`;
  }

  // ---------------------------------------------------------------- theme (per-viewer convenience)
  function storage(kind) { try { return kind === 'session' ? window.sessionStorage : window.localStorage; } catch (e) { return null; } }
  function getItem(kind, k) { try { const s = storage(kind); return s ? s.getItem(k) : null; } catch (e) { return null; } }
  function setItem(kind, k, v) { try { const s = storage(kind); if (s) s.setItem(k, v); } catch (e) { /* private mode */ } }
  function removeItem(kind, k) { try { const s = storage(kind); if (s) s.removeItem(k); } catch (e) { /* ignore */ } }
  function applyTheme(mode) {
    if (mode === 'light' || mode === 'dark') document.documentElement.dataset.theme = mode;
    else delete document.documentElement.dataset.theme;
    $('theme').textContent = `Theme: ${mode}`;
  }
  $('theme').addEventListener('click', () => {
    const order = ['auto', 'light', 'dark'];
    const next = order[(order.indexOf(getItem('local', THEME_KEY) || 'auto') + 1) % 3];
    setItem('local', THEME_KEY, next);
    applyTheme(next);
    renderHistory();
  });
  applyTheme(getItem('local', THEME_KEY) || 'auto');

  // ---------------------------------------------------------------- API
  class Unauthorized extends Error {}
  async function api(path) {
    const r = await fetch(path, { headers: { Authorization: `Bearer ${S.token}` }, cache: 'no-store' });
    if (r.status === 401) throw new Unauthorized('token rejected');
    if (!r.ok) throw new Error(`HTTP ${r.status} for ${path.split('?')[0]}`);
    return r.json();
  }
  const iso = (t) => new Date(t * 1000).toISOString();

  // ---------------------------------------------------------------- sign in / out
  function showLogin(message) {
    $('login').hidden = false; $('app').hidden = true; $('signout').hidden = true;
    $('login-error').textContent = message || '';
    $('token').focus();
  }
  function signOut(message) {
    S.running = false; S.token = null; S.lastId = null; S.epoch += 1;
    removeItem('session', TOKEN_KEY);
    if (S.abort) S.abort.abort();
    setConn('off');
    showLogin(message);
  }
  $('signout').addEventListener('click', () => signOut(''));
  $('login-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const value = $('token').value.trim();
    $('token').value = '';
    S.token = value;
    try {
      await api('/v1/status');
    } catch (e) {
      S.token = null;
      $('login-error').textContent = e instanceof Unauthorized ? 'That token was not accepted.' : `Gateway not reachable: ${e.message}`;
      return;
    }
    setItem('session', TOKEN_KEY, value);
    start();
  });

  function start() {
    $('login').hidden = true; $('app').hidden = false; $('signout').hidden = false;
    S.running = true; S.epoch += 1;
    streamLoop(S.epoch);
  }

  // ---------------------------------------------------------------- event stream
  function setConn(state) {
    S.conn = state;
    const pill = $('conn');
    pill.dataset.state = state;
    pill.textContent = { live: 'live', connecting: 'connecting…', reconnecting: 'reconnecting…', off: 'offline' }[state] || state;
  }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function streamLoop(epoch) {
    let backoff = 1000;
    setConn('connecting');
    while (S.running && epoch === S.epoch) {
      const ctrl = new AbortController();
      S.abort = ctrl;
      let watchdog = null;
      const arm = () => { clearTimeout(watchdog); watchdog = setTimeout(() => ctrl.abort(), WATCHDOG_MS); };
      try {
        const headers = { Authorization: `Bearer ${S.token}`, Accept: 'text/event-stream' };
        if (S.lastId) headers['Last-Event-ID'] = S.lastId;
        arm();
        const res = await fetch('/v1/events', { headers, signal: ctrl.signal, cache: 'no-store' });
        if (res.status === 401) { clearTimeout(watchdog); signOut('The gateway rejected the token.'); return; }
        if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          arm();
          buf += decoder.decode(value, { stream: true }).replace(/\r\n?/g, '\n');
          let cut;
          while ((cut = buf.indexOf('\n\n')) >= 0) {
            const block = buf.slice(0, cut);
            buf = buf.slice(cut + 2);
            if (handleBlock(block)) backoff = 1000;
          }
        }
      } catch (e) {
        if (!(e && e.name === 'AbortError')) console.warn('event stream:', e && e.message);
      } finally {
        clearTimeout(watchdog);
      }
      if (!S.running || epoch !== S.epoch) return;
      setConn('reconnecting');
      await sleep(backoff + Math.random() * 500);
      backoff = Math.min(backoff * 2, 15000);
    }
  }

  // One SSE block: `id:`, `event:`, `data:` lines; lines starting with ':' are comments (heartbeats).
  function handleBlock(block) {
    let id = null, type = 'message';
    const data = [];
    for (const line of block.split('\n')) {
      if (!line || line[0] === ':') continue;
      const colon = line.indexOf(':');
      const field = colon < 0 ? line : line.slice(0, colon);
      let value = colon < 0 ? '' : line.slice(colon + 1);
      if (value[0] === ' ') value = value.slice(1);
      if (field === 'id') id = value;
      else if (field === 'event') type = value;
      else if (field === 'data') data.push(value);
    }
    if (!data.length) return false;
    let payload;
    try { payload = JSON.parse(data.join('\n')); } catch (e) { console.warn('bad event data'); return false; }
    try {
      dispatch(type, payload);
    } finally {
      if (id !== null) S.lastId = id;  // after handling: a crash mid-event replays it
    }
    return true;
  }

  function dispatch(type, d) {
    switch (type) {
      case 'hello':
        S.skew = d.server_time - Date.now() / 1000;
        setConn('live');
        if (d.resumed) refreshStatus(); else loadSnapshot();
        break;
      case 'resync':
        loadSnapshot();
        break;
      case 'observation':
        if (S.status) { S.status.latest = d.latest; }
        addObservation(d.record);
        renderLive();
        break;
      case 'diagnostic':
        addDiagnostic(d);
        refreshStatusSoon();
        break;
      case 'radio':
        addFrame(d);
        if (d.outcome === 'rejected' || d.outcome === 'nack' || d.outcome === 'commit_failed') refreshStatusSoon();
        break;
      case 'rx':
        addAlive(d);
        break;
      case 'gateway':
        addEvent(d);
        refreshStatusSoon();
        break;
      default:
        break;
    }
  }

  // ---------------------------------------------------------------- snapshot loading
  let snapshotBusy = null;
  async function loadSnapshot() {
    if (snapshotBusy) return snapshotBusy;
    snapshotBusy = (async () => {
      try {
        const [status, frames, events] = await Promise.all([
          api('/v1/status'), api('/v1/radio?order=desc&limit=' + MAX_FRAMES), api('/v1/gateway/events?order=desc&limit=' + MAX_EVENTS),
        ]);
        S.status = status;
        S.frames = frames.rows;
        S.events = events.rows;
        renderLive(); renderFrames(); renderEvents();
        await loadHistory();
      } catch (e) {
        if (e instanceof Unauthorized) signOut('The gateway rejected the token.');
        else console.warn('snapshot:', e.message);
      } finally {
        snapshotBusy = null;
      }
    })();
    return snapshotBusy;
  }
  async function refreshStatus() {
    try { S.status = await api('/v1/status'); renderLive(); } catch (e) {
      if (e instanceof Unauthorized) signOut('The gateway rejected the token.');
    }
  }
  let statusTimer = null;
  function refreshStatusSoon() {
    clearTimeout(statusTimer);
    statusTimer = setTimeout(refreshStatus, 400);
  }

  // ---------------------------------------------------------------- live panel
  function chip(level, icon, text) {
    return el('span', { class: 'chip', 'data-level': level }, el('span', { class: 'icon', 'aria-hidden': 'true', text: icon }), text);
  }
  const ICON = { good: '✓', warning: '!', critical: '✕', neutral: '•' };

  function readingState(latest) {
    if (!latest || latest.reason === 'no_observation') return ['neutral', 'No readings yet'];
    const age = latest.effective_sampled_at === null ? null : now() - latest.effective_sampled_at;
    if (latest.reason === 'unknown_clock') return ['warning', 'Latest reading has no time yet'];
    if (latest.reason === 'future_clock_at_receipt') return ['critical', 'Latest reading is time-stamped in the future'];
    if (latest.reason === 'time_uncertain') return ['warning', 'Latest reading time is too uncertain'];
    if (age !== null && age >= STALE_S) return ['warning', `Reading stale (${fmtAge(age)})`];
    if (latest.reason === 'sensor_fault') return ['critical', 'Sensor fault: no valid field'];
    return ['good', `Reading fresh (${fmtAge(age)})`];
  }

  function renderChips() {
    const st = S.status;
    const box = $('chips');
    clear(box);
    if (!st) return;
    const add = (level, text) => box.append(chip(level, ICON[level], text));
    add(...(st.alarm ? ['critical', `Alarm: ${st.alarm}`] : ['good', 'No key-reuse alarm']));
    add(...readingState(st.latest));
    const obs = st.latest && st.latest.observation;
    if (obs) {
      const q = obs.quality;
      add(q === 'valid' ? 'good' : q === 'partial' ? 'warning' : 'critical',
        q === 'valid' ? 'All sensors valid' : q === 'partial' ? 'Some sensors faulty' : 'All sensors faulty');
    }
    const rx = st.receiver;
    if (!rx) add('neutral', 'Receiver: no report yet');
    else {
      const age = now() - rx.last_seen;
      if (!rx.alive || age > RX_SILENT_S) add('critical', `Receiver silent (last report ${fmtAge(age)})`);
      else add('good', 'Receiver alive');
    }
    const hc = st.host_clock;
    if (!hc) add('neutral', 'Host clock: not checked (demo)');
    else add(hc.state === 'ok' ? 'good' : hc.state === 'bad' ? 'critical' : 'warning',
      `Host clock ${hc.state}${hc.offset_s !== null && hc.offset_s !== undefined ? ` (${hc.offset_s >= 0 ? '+' : ''}${hc.offset_s.toFixed(3)} s)` : ''}`);
    const dg = st.node_diagnostics;
    if (!dg) add('neutral', 'Node: no health report yet');
    else {
      add(dg.link === 'linked' ? 'good' : 'warning', `Node link ${dg.link}`);
      add(dg.energy_state === 'critical' ? 'critical' : dg.energy_state === 'conserve' ? 'warning' : 'good', `Energy ${dg.energy_state}`);
      const age = now() - dg.received_at;
      if (age > DIAG_OVERDUE_S) add('warning', `Node health report overdue (${fmtAge(age)})`);
    }
  }

  function renderReadings() {
    const box = $('readings');
    clear(box);
    const latest = S.status && S.status.latest;
    const meta = $('reading-meta');
    if (!latest || !latest.observation) { meta.textContent = 'No observation stored yet.'; return; }
    const obs = latest.observation;
    const units = latest.units || {};
    const age = latest.effective_sampled_at === null ? null : now() - latest.effective_sampled_at;
    const stale = age === null || age >= STALE_S;
    for (const [name, label] of FIELDS) {
      if (!(name in obs)) continue;
      let value = obs[name];
      let state = 'ok', flag = '';
      if (name === 'wind_dir_deg' && obs.wind_calm) value = 'calm';
      if (value === null) { state = 'fault'; flag = 'sensor fault'; }
      else if (stale) { state = 'stale'; flag = 'stale'; }
      const qual = obs.qualifiers && obs.qualifiers[name];
      box.append(el('div', { class: 'tile', 'data-state': state },
        el('div', { class: 'label', text: label }),
        el('div', { class: 'value' }, value === null ? '—' : fmtNum(value), units[name] && value !== null && value !== 'calm' ? el('span', { class: 'unit', text: units[name] }) : null),
        el('div', { class: 'sub', text: fmtAge(age) }),
        flag ? el('div', { class: 'flag', text: flag }) : null,
        qual ? el('div', { class: 'flag', text: qual.replace(/_/g, ' ') }) : null));
    }
    meta.textContent = `Sample ${fmtTime(latest.effective_sampled_at, true)} · epoch ${obs.session} · sequence ${obs.sequence} · ` +
      `time ${latest.time_basis}${latest.time_uncertainty_s ? ` (±${fmtNum(latest.time_uncertainty_s, 1)} s)` : ''} · ` +
      `quality ${obs.quality} · energy ${obs.energy_state} · received ${fmtTime(latest.received_at, true)}`;
  }

  function kv(target, rows) {
    clear(target);
    for (const [k, v, level] of rows) {
      target.append(el('dt', { text: k }), el('dd', { text: v === null || v === undefined ? '—' : v, 'data-level': level || null }));
    }
  }

  function renderNode() {
    const d = S.status && S.status.node_diagnostics;
    $('node-age').textContent = d ? `· ${fmtAge(now() - d.received_at)}` : '';
    if (!d) { kv($('node'), [['Health report', 'none received yet']]); return; }
    kv($('node'), [
      ['Firmware build', d.firmware_build],
      ['Boot epoch', d.epoch],
      ['Uptime', fmtDuration(d.uptime_s)],
      ['Reset cause', d.reset_cause, d.reset_cause === 'watchdog' || d.reset_cause === 'brownout' ? 'warning' : null],
      ['Link state', d.link, d.link === 'linked' ? null : 'warning'],
      ['Energy state', d.energy_state, d.energy_state === 'critical' ? 'critical' : d.energy_state === 'conserve' ? 'warning' : null],
      ['Journal pending', fmtNum(d.journal_pending), d.journal_pending > 0 ? 'warning' : null],
      ['Journal lost (total)', fmtNum(d.journal_lost_total), d.journal_lost_total > 0 ? 'critical' : null],
      ['Torn slots', fmtNum(d.journal_torn_slots)],
      ['Abandoned (NACKed)', fmtNum(d.abandoned_total), d.abandoned_total > 0 ? 'warning' : null],
      ['Missed ACKs since boot', fmtNum(d.missed_acks_since_boot)],
      ['Rejected replies since boot', fmtNum(d.rejected_replies_since_boot)],
      ['Crashes since power-up', fmtNum(d.crashes_since_power_up), d.crashes_since_power_up > 0 ? 'warning' : null],
      ['ACK as heard by node', d.ack_rssi_dbm === null ? 'none yet' : `${d.ack_rssi_dbm} dBm, SNR ${d.ack_snr_db} dB`],
    ]);
  }

  function renderRx() {
    const rx = S.status && S.status.receiver;
    $('rx-age').textContent = rx ? `· ${fmtAge(now() - rx.last_seen)}` : '';
    if (!rx) { kv($('rx'), [['Reports', 'none received yet']]); return; }
    const silent = !rx.alive || now() - rx.last_seen > RX_SILENT_S;
    kv($('rx'), [
      ['State', silent ? 'silent' : 'alive', silent ? 'critical' : null],
      ['Last report', fmtTime(rx.last_seen, true)],
      ['Uptime', rx.uptime === undefined ? null : fmtDuration(rx.uptime)],
      ['Firmware', rx.fw],
      ['Forwarded', rx.forwarded],
      ['Dropped', rx.dropped, Number(rx.dropped) > 0 ? 'warning' : null],
      ['ACKs sent', rx.acks],
      ['Health reports', rx.diag],
      ['Listening', rx.listening === undefined ? null : rx.listening === '1' ? 'yes' : 'no', rx.listening === '0' ? 'warning' : null],
      ['Re-listens', rx.relistens, Number(rx.relistens) > 0 ? 'warning' : null],
      ['UART errors', rx.uart_errors, Number(rx.uart_errors) > 0 ? 'warning' : null],
      ['Stack peak (bytes)', rx.stack_peak],
    ]);
  }

  function renderGateway() {
    const st = S.status;
    if (!st) return;
    $('station').textContent = `${st.station} · ${st.mode}`;
    const nc = st.node_counter || {};
    const hc = st.host_clock;
    kv($('gw'), [
      ['Station', st.station],
      ['Mode', st.mode],
      ['Accepted (this run)', fmtNum(st.accepted_this_process)],
      ['Rejected (this run)', fmtNum(st.rejected_this_process), st.rejected_this_process > 0 ? 'warning' : null],
      ['NACKed (this run)', fmtNum(st.nacked_this_process), st.nacked_this_process > 0 ? 'warning' : null],
      ['Node counter mark', fmtNum(nc.max_node_counter, 0)],
      ['Counter regressions', fmtNum(nc.counter_regression, 0), nc.counter_regression ? 'critical' : null],
      ['Host clock', hc ? `${hc.state}${hc.checked_at ? `, checked ${fmtAge(Date.now() / 1000 - hc.checked_at)}` : ''}` : 'not checked (demo)', hc && hc.state === 'bad' ? 'critical' : null],
      ['Event stream', S.conn],
    ]);
  }

  function renderLive() { renderChips(); renderReadings(); renderNode(); renderRx(); renderGateway(); }

  const OUTCOME_LEVEL = { nack: 'warning', duplicate: null, rejected: 'critical', commit_failed: 'critical', dropped_by_rx: 'warning', unparsed: 'warning' };
  function renderFrames() {
    const body = $('frames').tBodies[0];
    clear(body);
    if (!S.frames.length) { body.append(el('tr', {}, el('td', { colspan: 6, class: 'muted', text: 'No frames recorded yet.' }))); return; }
    for (const f of S.frames) {
      let outcome = f.outcome || '—';
      if (f.delivered === 0) outcome += ' (reply not delivered)';
      body.append(el('tr', {},
        el('td', { text: fmtTime(f.received_at) }),
        el('td', { text: f.kind || '—' }),
        el('td', { class: 'num', text: f.counter === null || f.counter === undefined ? '—' : f.counter }),
        el('td', { text: outcome, 'data-level': OUTCOME_LEVEL[f.outcome] || null, title: f.detail || null }),
        el('td', { class: 'num', text: f.rssi_dbm === null || f.rssi_dbm === undefined ? '—' : f.rssi_dbm }),
        el('td', { class: 'num', text: f.snr_db === null || f.snr_db === undefined ? '—' : f.snr_db })));
    }
  }
  function renderEvents() {
    const list = $('events');
    clear(list);
    if (!S.events.length) { list.append(el('li', { class: 'muted', text: 'No events recorded yet.' })); return; }
    for (const e of S.events) {
      list.append(el('li', {},
        el('time', { datetime: iso(e.at), text: fmtTime(e.at, true) }),
        el('span', { class: 'lvl', 'data-level': e.level, text: e.level }),
        el('span', { class: 'txt', text: e.source === 'gateway' ? e.text.replace(/^#gateway /, 'gateway: ') : `RX: ${e.text}` })));
    }
  }

  // ---------------------------------------------------------------- live additions
  function insertionPoint(keyArr, t) {
    // index at which t keeps keyArr sorted (binary search)
    let lo = 0, hi = keyArr.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (keyArr[mid] <= t) lo = mid + 1; else hi = mid; }
    return lo;
  }
  const following = () => S.hist && S.range.span !== undefined;

  function addObservation(r) {
    const h = S.hist;
    if (!following() || r.effective_sampled_at === null || r.effective_sampled_at === undefined) return;
    const o = h.observations;
    const t = r.effective_sampled_at;
    for (let i = 0; i < o.t.length; i++) if (o.t[i] === t && o.session[i] === r.session) return;  // already loaded
    for (const [name] of FIELDS) {
      if (name in r && !o.fields.includes(name)) {
        o.fields.push(name);
        o.values[name] = o.t.map(() => null);
        o.fields.sort((a, b) => FIELDS.findIndex((f) => f[0] === a) - FIELDS.findIndex((f) => f[0] === b));
      }
    }
    const at = insertionPoint(o.t, t);
    o.t.splice(at, 0, t);
    o.basis.splice(at, 0, r.time_basis);
    o.quality.splice(at, 0, r.quality);
    o.session.splice(at, 0, r.session);
    for (const name of o.fields) o.values[name].splice(at, 0, name in r ? r[name] : null);
    scheduleHistory();
  }
  function addFrame(f) {
    if (S.frames.some((x) => x.id === f.id)) return;
    S.frames.unshift(f);
    S.frames.length = Math.min(S.frames.length, MAX_FRAMES);
    renderFrames();
    if (!following()) return;
    const r = S.hist.radio;
    if (r.t.length && r.t[r.t.length - 1] >= f.received_at) return;
    r.t.push(f.received_at); r.rssi_dbm.push(f.rssi_dbm); r.snr_db.push(f.snr_db); r.rssi_min.push(f.rssi_dbm);
    r.frames.push(1); r.kind.push(f.kind); r.outcome.push(f.outcome); r.counter.push(f.counter);
    scheduleHistory();
  }
  function addAlive(a) {
    if (S.status) {
      const rx = S.status.receiver || {};
      S.status.receiver = Object.assign({}, rx, {
        alive: true, last_seen: a.received_at, uptime: a.uptime_s, forwarded: a.forwarded, dropped: a.dropped,
        acks: a.acks, diag: a.diag, listening: String(a.listening), relistens: a.relistens, uart_errors: a.uart_errors,
        stack_peak: a.stack_peak,
      });
      renderLive();
    }
    if (!following()) return;
    const h = S.hist.receiver;
    if (h.t.length && h.t[h.t.length - 1] >= a.received_at) return;
    h.t.push(a.received_at);
    for (const k of ['uptime_s', 'forwarded', 'dropped', 'acks', 'diag', 'listening', 'relistens', 'uart_errors', 'stack_peak']) h[k].push(a[k]);
    scheduleHistory();
  }
  function addDiagnostic(d) {
    if (!following()) return;
    const list = S.hist.diagnostics;
    if (list.some((x) => x.epoch === d.epoch && x.uptime_s === d.uptime_s)) return;
    list.push(d);
    list.sort((a, b) => a.received_at - b.received_at);
    scheduleHistory();
  }
  function addEvent(e) {
    if (S.events.some((x) => x.id === e.id)) return;
    S.events.unshift(e);
    S.events.length = Math.min(S.events.length, MAX_EVENTS);
    renderEvents();
    if (following() && !S.hist.events.some((x) => x.id === e.id)) { S.hist.events.push(e); scheduleHistory(); }
  }

  // ---------------------------------------------------------------- history
  function rangeBounds() {
    if (S.range.span !== undefined) { const to = now(); return [to - S.range.span, to]; }
    return [S.range.from, S.range.to];
  }
  async function loadHistory() {
    const [from, to] = rangeBounds();
    const width = Math.max(320, Math.min(2400, document.documentElement.clientWidth));
    const points = Math.max(300, Math.min(3000, Math.round(width * 1.5)));
    $('hist-note').textContent = 'Loading…';
    const h = await api(`/v1/history?from=${encodeURIComponent(iso(from))}&to=${encodeURIComponent(iso(to))}&max_points=${points}`);
    S.hist = h;
    renderHistory();
  }

  document.querySelectorAll('.ranges button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('.ranges button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    if (b.dataset.range === 'custom') {
      $('custom').hidden = false;
      const [from, to] = rangeBounds();
      const local = (t) => { const d = new Date(t * 1000 - new Date(t * 1000).getTimezoneOffset() * 60000); return d.toISOString().slice(0, 16); };
      if (!$('c-from').value) $('c-from').value = local(from);
      if (!$('c-to').value) $('c-to').value = local(to);
      return;
    }
    $('custom').hidden = true;
    S.range = { span: Number(b.dataset.range) };
    loadHistory().catch((e) => { $('hist-note').textContent = `Could not load history: ${e.message}`; });
  }));
  $('custom').addEventListener('submit', (ev) => {
    ev.preventDefault();
    const from = new Date($('c-from').value).getTime() / 1000;
    const to = new Date($('c-to').value).getTime() / 1000;
    if (!isFinite(from) || !isFinite(to) || from >= to) { $('custom-error').textContent = 'Choose a start before the end.'; return; }
    $('custom-error').textContent = '';
    S.range = { from, to };
    loadHistory().catch((e) => { $('hist-note').textContent = `Could not load history: ${e.message}`; });
  });

  let histTimer = null;
  function scheduleHistory() {
    if (histTimer) return;
    histTimer = setTimeout(() => { histTimer = null; trimHistory(); renderHistory(); }, 500);
  }
  // While following live, points older than the window are dropped, so a page left open for days
  // keeps a bounded history instead of growing forever (gateway review GW11).
  function trimHistory() {
    if (!following()) return;
    const cutoff = now() - S.range.span;
    const h = S.hist;
    const dropColumns = (series, names) => {
      const n = insertionPoint(series.t, cutoff - 1e-9);
      if (n) for (const k of names) series[k].splice(0, n);
      return n;
    };
    const o = h.observations;
    const n = dropColumns(o, ['t', 'basis', 'quality', 'session']);
    if (n) for (const name of o.fields) o.values[name].splice(0, n);
    dropColumns(h.radio, Object.keys(h.radio).filter((k) => Array.isArray(h.radio[k])));
    dropColumns(h.receiver, Object.keys(h.receiver).filter((k) => Array.isArray(h.receiver[k])));
    h.diagnostics = h.diagnostics.filter((d) => d.received_at >= cutoff);
    h.events = h.events.filter((e) => e.at >= cutoff);
  }

  function markersFor(h) {
    const m = [];
    let prev = null;
    for (const d of h.diagnostics) {
      if (prev && d.epoch !== prev.epoch) m.push({ t: d.received_at, label: `node boot (${d.reset_cause})`, group: 'node' });
      if (prev && d.firmware_build !== prev.firmware_build) m.push({ t: d.received_at, label: `firmware ${d.firmware_build}`, group: 'node' });
      prev = d;
    }
    const o = h.observations;
    for (let i = 1; i < o.t.length; i++) {
      if (o.session[i] !== o.session[i - 1] && !m.some((x) => x.group === 'node' && Math.abs(x.t - o.t[i]) < 1800)) {
        m.push({ t: o.t[i], label: `node epoch ${o.session[i]}`, group: 'node' });
      }
    }
    for (const e of h.events) {
      if (e.kind === 'rx_boot') m.push({ t: e.at, label: 'RX boot', group: 'rx' });
      else if (e.kind === 'start') m.push({ t: e.at, label: 'gateway start', group: 'gateway' });
      else if (e.kind === 'serial-lost') m.push({ t: e.at, label: 'serial lost', group: 'rx' });
      else if (e.kind === 'receiver-silent') m.push({ t: e.at, label: 'RX silent', group: 'rx' });
    }
    return m.sort((a, b) => a.t - b.t);
  }

  function renderHistory() {
    const h = S.hist;
    if (!h) return;
    const [from, to] = S.range.span !== undefined ? rangeBounds() : [h.from, h.to];
    const o = h.observations;
    const markers = markersFor(h);
    const pick = (...groups) => markers.filter((m) => groups.includes(m.group));
    const notes = [`${fmtTime(from, true)} – ${fmtTime(to, true)}`];
    if (o.bucket_s) notes.push(`sensor values averaged over ${fmtDuration(o.bucket_s)} (counters: last value)`);
    if (h.radio.bucket_s) notes.push(`radio averaged over ${fmtDuration(h.radio.bucket_s)}`);
    if (o.unknown_time_count) notes.push(`${o.unknown_time_count} reading(s) with no time yet are not plotted`);
    if (S.range.span !== undefined) notes.push('following live');
    $('hist-note').textContent = notes.join(' · ');

    const obsGap = o.bucket_s ? o.bucket_s * 1.5 : 110;
    const sensors = $('c-sensors');
    clear(sensors);
    if (!o.fields.length) sensors.append(el('p', { class: 'muted small', text: 'No observations with a known time in this range.' }));
    for (const name of o.fields) {
      sensors.append(chart({
        title: LABEL[name] || name, unit: o.units[name], from, to, markers: pick('node', 'gateway'),
        series: [{ name: LABEL[name] || name, cls: 'c1', t: o.t, v: o.values[name], basis: o.basis, gap: obsGap, dots: name === 'wind_dir_deg', faults: true }],
      }));
    }

    const r = h.radio;
    const diag = h.diagnostics;
    const dt = diag.map((d) => d.received_at);
    const radioGap = r.bucket_s ? r.bucket_s * 1.5 : 0;
    const link = $('c-link');
    clear(link);
    link.append(chart({
      title: 'Signal strength (RSSI)', unit: 'dBm', from, to, markers: pick('node', 'rx'),
      series: [
        { name: 'Uplink (RX hears node)', cls: 'c1', t: r.t, v: r.rssi_dbm, gap: radioGap, dots: !r.bucket_s },
        { name: 'Downlink ACK (node hears gateway)', cls: 'c2', t: dt, v: diag.map((d) => d.ack_rssi_dbm), gap: 2000, dots: true },
      ],
    }));
    link.append(chart({
      title: 'Signal-to-noise ratio (SNR)', unit: 'dB', from, to, markers: pick('node', 'rx'),
      series: [
        { name: 'Uplink (RX hears node)', cls: 'c1', t: r.t, v: r.snr_db, gap: radioGap, dots: !r.bucket_s },
        { name: 'Downlink ACK (node hears gateway)', cls: 'c2', t: dt, v: diag.map((d) => d.ack_snr_db), gap: 2000, dots: true },
      ],
    }));
    const bad = { t: [], v: [] };
    for (let i = 0; i < r.t.length; i++) {
      const out = r.outcome[i];
      const n = typeof out === 'object' && out ? Object.entries(out).filter(([k]) => !['ack', 'diag', 'duplicate'].includes(k)).reduce((s, [, c]) => s + c, 0)
        : (['ack', 'diag', 'duplicate'].includes(out) ? 0 : 1);
      bad.t.push(r.t[i]); bad.v.push(n);
    }
    const problem = { name: 'NACKed, rejected or dropped', cls: r.bucket_s ? 'c2' : 'c1', t: bad.t, v: bad.v, gap: radioGap, dots: true, skipZero: true };
    link.append(chart(r.bucket_s ? {
      title: `Frames per ${fmtDuration(r.bucket_s)}`, unit: 'count', from, to, markers: pick('node', 'rx'), integer: true,
      series: [{ name: 'All frames', cls: 'c1', t: r.t, v: r.frames, gap: radioGap }, problem],
    } : {
      title: 'Problem frames (NACK, rejected, dropped by RX)', unit: 'count', from, to, markers: pick('node', 'rx'), integer: true,
      empty: r.t.length ? 'None in this range' : 'No frames in this range', series: [problem],
    }));

    const node = $('c-node');
    clear(node);
    const nodeMarkers = pick('node', 'gateway');
    const nodeSeries = (title, key, unit) => chart({
      title, unit, from, to, markers: nodeMarkers, integer: true,
      series: [{ name: title, cls: 'c1', t: dt, v: diag.map((d) => d[key]), gap: 2000, step: true }],
    });
    if (!diag.length) node.append(el('p', { class: 'muted small', text: 'No node health reports in this range (one every 15 minutes).' }));
    else {
      node.append(stateChart('Energy state', from, to, dt, diag.map((d) => d.energy_state),
        { surplus: 'st-s3', normal: 'st-s1', conserve: 'st-warning', critical: 'st-critical' }, nodeMarkers));
      node.append(stateChart('Link state', from, to, dt, diag.map((d) => d.link), { linked: 'st-good', probing: 'st-warning' }, nodeMarkers));
      node.append(nodeSeries('Journal pending', 'journal_pending', 'records'));
      node.append(nodeSeries('Journal lost (total)', 'journal_lost_total', 'records'));
      node.append(nodeSeries('Missed ACKs since boot', 'missed_acks_since_boot', 'count'));
      node.append(nodeSeries('Crashes since power-up', 'crashes_since_power_up', 'count'));
      node.append(nodeSeries('Boot epoch', 'epoch', ''));
      node.append(nodeSeries('Abandoned records (total)', 'abandoned_total', 'records'));
    }

    const a = h.receiver;
    const rx = $('c-rx');
    clear(rx);
    const rxGap = a.bucket_s ? a.bucket_s * 1.5 : 150;
    const rxSeries = (title, key, unit) => chart({
      title, unit, from, to, markers: pick('rx', 'gateway'), integer: true,
      series: [{ name: title, cls: 'c1', t: a.t, v: a[key], gap: rxGap, step: true }],
    });
    if (!a.t.length) rx.append(el('p', { class: 'muted small', text: 'No RX reports in this range (one a minute while the gateway serves a receiver).' }));
    else {
      rx.append(rxSeries('Frames forwarded', 'forwarded', 'count'));
      rx.append(rxSeries('Frames dropped by RX', 'dropped', 'count'));
      rx.append(rxSeries('Re-listens', 'relistens', 'count'));
      rx.append(rxSeries('UART errors', 'uart_errors', 'count'));
      rx.append(rxSeries('Stack peak', 'stack_peak', 'bytes'));
      rx.append(rxSeries('RX uptime', 'uptime_s', 's'));
    }
  }

  // ---------------------------------------------------------------- charts (SVG, no library)
  const H = 150, M = { l: 48, r: 12, t: 14, b: 22 };

  function niceTicks(lo, hi, count, integer) {
    if (lo === hi) { lo -= 1; hi += 1; }
    const raw = (hi - lo) / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    let step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || 10 * mag;
    if (integer) step = Math.max(1, Math.round(step));
    const start = Math.floor(lo / step) * step;
    const ticks = [];
    for (let v = start; v <= hi + step * 0.5; v += step) ticks.push(Number(v.toFixed(10)));
    return ticks;
  }
  const STEPS = [60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800, 2592000];
  function timeTicks(from, to, maxTicks) {
    const span = to - from;
    const step = STEPS.find((s) => span / s <= maxTicks) || STEPS[STEPS.length - 1];
    const tz = new Date(from * 1000).getTimezoneOffset() * 60;
    const first = Math.ceil((from - tz) / step) * step + tz;
    const out = [];
    for (let t = first; t <= to; t += step) out.push(t);
    return [out, step];
  }
  function timeLabel(t, step) {
    const d = new Date(t * 1000);
    if (step >= 86400) return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    const hm = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    return d.getHours() === 0 && d.getMinutes() === 0 ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : hm;
  }

  function frame(spec, legendItems) {
    const fig = el('figure', { class: 'chart' });
    const cap = el('figcaption', {}, el('span', { class: 'ct', text: spec.title }), spec.unit ? el('span', { class: 'cu', text: spec.unit }) : null);
    if (legendItems.length) {
      const lg = el('span', { class: 'legend' });
      for (const [cls, name, box] of legendItems) lg.append(el('span', {}, el('span', { class: `sw ${box ? 'box ' : ''}${cls}` }), name));
      cap.append(lg);
    }
    fig.append(cap);
    return fig;
  }
  function chartWidth() {
    const w = document.documentElement.clientWidth;
    return Math.max(260, Math.min(w - 64, w > 960 ? (Math.min(w, 1400) - 60) / 2 - 30 : w - 64));
  }

  function chart(spec) {
    const W = chartWidth();
    const { from, to } = spec;
    const x = (t) => M.l + (t - from) / (to - from) * (W - M.l - M.r);
    const series = spec.series;
    const legend = series.length > 1 ? series.map((s) => [s.cls, s.name]) : [];
    if (series.some((s) => s.faults && s.v.some((v, i) => v === null && s.t[i] >= from && s.t[i] <= to))) legend.push(['fault', 'sensor fault', true]);
    if (series.some((s) => s.basis && s.basis.some((b, i) => b === 'reconstructed' && s.t[i] >= from && s.t[i] <= to))) legend.push(['c1', 'dashed: reconstructed time']);
    const fig = frame(spec, legend);
    let lo = Infinity, hi = -Infinity;
    for (const s of series) for (let i = 0; i < s.t.length; i++) {
      const v = s.v[i];
      if (v === null || v === undefined || s.t[i] < from || s.t[i] > to || (s.skipZero && v === 0)) continue;
      if (v < lo) lo = v; if (v > hi) hi = v;
    }
    const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${spec.title} chart` });
    fig.append(svg);
    const plotBottom = H - M.b;
    if (lo === Infinity) {
      svg.append(sv('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', class: 'empty' }, spec.empty || 'No data in this range'));
      drawTimeAxis(svg, from, to, x, W);
      return fig;
    }
    const pad = (hi - lo) * 0.08 || (spec.integer ? 1 : Math.abs(hi) * 0.05 || 1);
    const ticks = niceTicks(lo - (lo === hi ? pad : 0), hi + (lo === hi ? pad : 0), 4, spec.integer);
    const ylo = Math.min(ticks[0], lo), yhi = Math.max(ticks[ticks.length - 1], hi);
    const y = (v) => plotBottom - (v - ylo) / (yhi - ylo || 1) * (plotBottom - M.t);
    for (const tv of ticks) {
      if (tv < ylo || tv > yhi) continue;
      svg.append(sv('line', { x1: M.l, x2: W - M.r, y1: y(tv), y2: y(tv), class: 'gridline' }));
      svg.append(sv('text', { x: M.l - 6, y: y(tv) + 3.5, 'text-anchor': 'end', class: 'tick' }, fmtNum(tv, 2)));
    }
    drawTimeAxis(svg, from, to, x, W);
    drawMarkers(svg, spec.markers || [], from, to, x);

    for (const s of series) {
      if (s.faults) {
        const g = s.gap ? s.gap / 1.5 : 60;
        for (let i = 0; i < s.t.length; i++) {
          if (s.v[i] !== null || s.t[i] < from - g || s.t[i] > to + g) continue;
          let j = i;
          while (j + 1 < s.t.length && s.v[j + 1] === null && s.t[j + 1] - s.t[j] <= s.gap) j++;
          const x0 = Math.max(M.l, x(s.t[i] - g / 2)), x1 = Math.min(W - M.r, x(s.t[j] + g / 2));
          svg.append(sv('rect', { x: x0, y: M.t, width: Math.max(2, x1 - x0), height: plotBottom - M.t, class: 'fault' }));
          i = j;
        }
      }
    }
    for (const s of series) {
      let solid = '', dashed = '';
      const lonely = [];
      let prev = -1, prevJoined = false;
      for (let i = 0; i < s.t.length; i++) {
        const v = s.v[i];
        if (v === null || v === undefined || (s.skipZero && v === 0)) { if (prev >= 0 && !prevJoined) lonely.push(prev); prev = -1; continue; }
        if (s.t[i] < from - (s.gap || 0) || s.t[i] > to + (s.gap || 0)) continue;
        if (s.dots) { lonely.push(i); continue; }
        if (prev >= 0 && s.t[i] - s.t[prev] <= s.gap) {
          const seg = s.step
            ? `M${x(s.t[prev]).toFixed(1)},${y(s.v[prev]).toFixed(1)}H${x(s.t[i]).toFixed(1)}V${y(v).toFixed(1)}`
            : `M${x(s.t[prev]).toFixed(1)},${y(s.v[prev]).toFixed(1)}L${x(s.t[i]).toFixed(1)},${y(v).toFixed(1)}`;
          if (s.basis && (s.basis[i] === 'reconstructed' || s.basis[prev] === 'reconstructed')) dashed += seg; else solid += seg;
          prevJoined = true;
        } else {
          if (prev >= 0 && !prevJoined) lonely.push(prev);
          prevJoined = false;
        }
        prev = i;
      }
      if (prev >= 0 && !prevJoined && !s.dots) lonely.push(prev);
      if (s.step && prev >= 0 && !s.dots) {  // a step line holds its last value until "now" or the next gap
        const end = Math.min(to, s.t[prev] + s.gap);
        if (end > s.t[prev]) solid += `M${x(s.t[prev]).toFixed(1)},${y(s.v[prev]).toFixed(1)}H${x(end).toFixed(1)}`;
      }
      if (solid) svg.append(sv('path', { d: solid, class: `line ${s.cls}` }));
      if (dashed) svg.append(sv('path', { d: dashed, class: `line dash ${s.cls}` }));
      const r = s.dots ? 2.6 : 3;
      for (const i of lonely) {
        if (s.t[i] < from || s.t[i] > to) continue;
        svg.append(sv('circle', { cx: x(s.t[i]).toFixed(1), cy: y(s.v[i]).toFixed(1), r, class: `dot ${s.cls}` }));
      }
    }
    hover(fig, svg, spec, series, x, y, W);
    return fig;
  }

  function drawTimeAxis(svg, from, to, x, W) {
    const plotBottom = H - M.b;
    svg.append(sv('line', { x1: M.l, x2: W - M.r, y1: plotBottom, y2: plotBottom, class: 'baseline' }));
    const [ticks, step] = timeTicks(from, to, Math.max(2, Math.floor((W - M.l - M.r) / 90)));
    for (const t of ticks) svg.append(sv('text', { x: x(t), y: H - 6, 'text-anchor': 'middle', class: 'tick' }, timeLabel(t, step)));
  }
  function drawMarkers(svg, markers, from, to, x) {
    let lastX = -Infinity;
    for (const m of markers) {
      if (m.t < from || m.t > to) continue;
      const mx = x(m.t);
      svg.append(sv('line', { x1: mx, x2: mx, y1: M.t - 4, y2: H - M.b, class: 'marker' }));
      const right = mx > x(to) - 90;   // near the right edge: label on the left of the line
      const label = sv('text', { x: right ? mx - 3 : mx + 3, y: M.t - 4, 'text-anchor': right ? 'end' : 'start', class: 'marker-label' },
        mx - lastX > 70 ? m.label : '');
      label.append(sv('title', {}, `${m.label} · ${fmtTime(m.t, true)}`));
      svg.append(label);
      if (mx - lastX > 70) lastX = mx;
    }
  }

  function nearest(t, arr) {
    let lo = 0, hi = arr.length - 1;
    if (hi < 0) return -1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] < t) lo = mid + 1; else hi = mid; }
    if (lo > 0 && Math.abs(arr[lo - 1] - t) < Math.abs(arr[lo] - t)) lo -= 1;
    return lo;
  }

  function hover(fig, svg, spec, series, x, y, W) {
    const cross = sv('line', { y1: M.t, y2: H - M.b, class: 'cross', visibility: 'hidden' });
    svg.append(cross);
    const dots = series.map((s) => { const c = sv('circle', { r: 4, class: `hover-dot ${s.cls}`, visibility: 'hidden' }); svg.append(c); return c; });
    const tip = el('div', { class: 'tip', hidden: true });
    fig.append(tip);
    const hit = sv('rect', { x: M.l, y: 0, width: W - M.l - M.r, height: H, fill: 'transparent' });
    svg.append(hit);
    const hide = () => { cross.setAttribute('visibility', 'hidden'); dots.forEach((d) => d.setAttribute('visibility', 'hidden')); tip.hidden = true; };
    hit.addEventListener('pointerleave', hide);
    hit.addEventListener('pointermove', (ev) => {
      const box = svg.getBoundingClientRect();
      const px = (ev.clientX - box.left) * W / box.width;
      const t = spec.from + (px - M.l) / (W - M.l - M.r) * (spec.to - spec.from);
      let best = null;
      series.forEach((s, k) => {
        const i = nearest(t, s.t);
        dots[k].setAttribute('visibility', 'hidden');
        if (i < 0) return;
        const dist = Math.abs(s.t[i] - t);
        if (!best || dist < best.dist) best = { dist, t: s.t[i] };
      });
      if (!best || Math.abs(x(best.t) - px) > 40) { hide(); return; }
      clear(tip);
      tip.append(el('div', { class: 'tt', text: fmtTime(best.t, true) }));
      series.forEach((s, k) => {
        const i = nearest(best.t, s.t);
        if (i < 0 || Math.abs(s.t[i] - best.t) > Math.max(s.gap || 0, 60)) return;
        const v = s.v[i];
        let text = v === null || v === undefined ? (s.faults ? 'sensor fault' : 'no value') : `${fmtNum(v)}${spec.unit && spec.unit !== 'count' ? ` ${spec.unit}` : ''}`;
        if (s.basis && s.basis[i] === 'reconstructed') text += ' (reconstructed time)';
        tip.append(el('div', {}, el('span', { class: `sw ${s.cls}` }), `${series.length > 1 ? `${s.name}: ` : ''}${text}`));
        if (v !== null && v !== undefined) {
          dots[k].setAttribute('cx', x(s.t[i])); dots[k].setAttribute('cy', y(v)); dots[k].setAttribute('visibility', 'visible');
        }
      });
      cross.setAttribute('x1', x(best.t)); cross.setAttribute('x2', x(best.t)); cross.setAttribute('visibility', 'visible');
      tip.hidden = false;
      const figBox = fig.getBoundingClientRect();
      const left = ev.clientX - figBox.left + 12;
      tip.style.left = `${Math.min(left, figBox.width - tip.offsetWidth - 4)}px`;
      tip.style.top = `${box.top - figBox.top + 8}px`;
    });
  }

  // Category over time (energy state, link state): a band per report interval, labelled in the legend.
  function stateChart(title, from, to, t, values, classes, markers) {
    const W = chartWidth();
    const h = 64;
    const x = (v) => M.l + (v - from) / (to - from) * (W - M.l - M.r);
    const seen = [...new Set(values)];
    const fig = frame({ title }, seen.map((v) => [classes[v] || 'st-unknown', v, true]));
    const svg = sv('svg', { viewBox: `0 0 ${W} ${h}`, role: 'img', 'aria-label': `${title} over time` });
    fig.append(svg);
    for (let i = 0; i < t.length; i++) {
      const end = Math.min(i + 1 < t.length ? t[i + 1] : to, t[i] + 2000, to);
      if (end < from || t[i] > to) continue;
      const x0 = x(Math.max(from, t[i])), x1 = x(end);
      const r = sv('rect', { x: x0, y: 14, width: Math.max(1.5, x1 - x0), height: 22, class: classes[values[i]] || 'st-unknown' });
      r.append(sv('title', {}, `${values[i]} · ${fmtTime(t[i], true)}`));
      svg.append(r);
    }
    svg.append(sv('line', { x1: M.l, x2: W - M.r, y1: 40, y2: 40, class: 'baseline' }));
    const [ticks, step] = timeTicks(from, to, Math.max(2, Math.floor((W - M.l - M.r) / 90)));
    for (const tt of ticks) svg.append(sv('text', { x: x(tt), y: h - 8, 'text-anchor': 'middle', class: 'tick' }, timeLabel(tt, step)));
    for (const m of markers) {
      if (m.t < from || m.t > to) continue;
      const mx = x(m.t);
      const line = sv('line', { x1: mx, x2: mx, y1: 8, y2: 40, class: 'marker' });
      line.append(sv('title', {}, `${m.label} · ${fmtTime(m.t, true)}`));
      svg.append(line);
    }
    return fig;
  }

  // ---------------------------------------------------------------- timers and start
  setInterval(() => { if (S.running) renderLive(); }, 1000);          // ages tick locally; no polling
  setInterval(() => { if (S.running && S.range.span !== undefined) renderHistory(); }, 60000);  // slide the window
  let resizeTimer = null;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderHistory, 250); });

  S.token = getItem('session', TOKEN_KEY);
  if (S.token) start(); else showLogin('');
})();
