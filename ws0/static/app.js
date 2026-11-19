/* Weather station dashboard (docs/web-dashboard.md). Plain JS, no libraries, no build step.
 *
 * Security: the API token lives only in sessionStorage and in Authorization headers. Text from
 * the device, the logs or the API is only ever inserted with textContent / setAttribute, never
 * as HTML.
 *
 * Real time: one fetch() stream of Server-Sent Events from GET /v1/events (EventSource cannot
 * send an Authorization header). On reconnect the last event id goes back as Last-Event-ID; the
 * gateway replays what was missed, or sends `resync`, and then the page reloads its snapshot.
 *
 * Rendering: events only change state and mark parts dirty; one animation frame redraws each
 * dirty part once, however many events arrived (a reconnect replay is one redraw, not N). The
 * 1 s tick rewrites age texts in place and rebuilds nothing unless a state flips with time.
 * Field names, labels and their order come from the gateway's catalog (/v1/history), not from
 * a table in this file. The exceptions are the power view's rail table (RAILS: which voltage and
 * current fields form one rail, docs/superpowers/specs/2026-10-29-power-telemetry-design.md
 * section 10.1) and the health-report keys it charts (section 6.1); which fields are station
 * rather than weather values still comes from the gateway (observations.diagnostic).
 */
'use strict';
(() => {
  const TOKEN_KEY = 'ws0.token';
  const THEME_KEY = 'ws0.theme';
  const STALE_S = 180;          // gateway's freshness limit for a reading (gateway.py latest())
  const RX_SILENT_S = 180;      // three missed 60 s #alive reports
  const DIAG_OVERDUE_S = 1900;  // two 15-minute health reports plus slack
  const WATCHDOG_MS = 45000;    // no byte (heartbeats included) for this long: reconnect
  const MAX_FRAMES = 40;
  const MAX_EVENTS = 60;
  const HISTORY_TIMEOUT_MS = 30000;   // a history request that has not answered by then is abandoned
  const SLIDE_S = 60;                 // the following window slides (full redraw) this often
  const GROUPS = ['sensors', 'power', 'charger', 'link', 'node', 'rx'];   // chart groups, redrawn independently
  // The power view: one entry per rail, voltage and current paired (design sections 3.2 and 10.1).
  // A slot whose field no record in the range carries is "not measured in this build"; a present
  // field with INVALID values is a sensor fault, drawn as on every other chart.
  const RAILS = [
    { name: 'Battery', v: 'batt_mv', i: 'batt_current_ma', signed: true },
    { name: 'Load (system)', v: 'load_mv', i: 'load_current_ma' },
    { name: 'Charger input (source not identified)', v: 'charger_input_mv' },
    { name: 'Solar input', v: 'solar_mv', i: 'solar_current_ma' },
    { name: 'USB-C input', v: 'usb_mv', i: 'usb_current_ma' },
    { name: 'Battery energy and charge since boot', v: 'energy_in_mwh', i: 'energy_out_mwh', counters: ['charge_in_mah', 'charge_out_mah'] },
  ];
  const POWER_FIELDS = new Set(RAILS.flatMap((r) => [r.v, r.i, ...(r.counters || [])].filter(Boolean)));
  const NOT_MEASURED = 'not measured in this build';
  const SIGNED = { above: 'charging', below: 'discharging' };

  const S = {
    token: null, running: false, lastId: null, skew: 0, conn: 'off', status: null,
    frames: [], events: [], hist: null, range: { span: 86400 }, abort: null, epoch: 0,
    labels: {},       // field name -> display label, from the gateway catalog (history responses)
    diagnostic: null, // Set of station (not weather) field names, from the gateway catalog; null until known
    histSeq: 0,       // request sequence: only the newest history request may land
    histLoadedAt: 0,  // Date.now() of the last history request (bucketed reloads are spaced from it)
    histPending: false, histError: null, histBackoff: 2000,
    snapshotOk: false, snapshotBackoff: 2000,   // a resumed stream reloads the snapshot until one has loaded
    // S.range is the range last asked for; S.hist.range the one the data on screen belongs to.
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
  // Change a text in place: reuse the existing text node, touch the DOM only when it differs.
  function setText(node, s) {
    const f = node.firstChild;
    if (f && f.nodeType === 3 && !f.nextSibling) { if (f.data !== s) f.data = s; } else if (node.textContent !== s) node.textContent = s;
  }

  // ---------------------------------------------------------------- formatting
  const now = () => Date.now() / 1000 + S.skew;
  function fmtDuration(s) {
    if (s === null || s === undefined || !isFinite(s)) return '—';
    s = Number(s);
    if (s < 120) return `${Math.round(s)} s`;
    if (s < 7200) return `${Math.round(s / 60)} min`;
    if (s < 172800) return `${(s / 3600).toFixed(1)} h`;
    return `${(s / 86400).toFixed(1)} d`;
  }
  function fmtAge(s) {
    if (s === null || s === undefined || !isFinite(s)) return '—';
    return s < 0 ? 'in the future' : `${fmtDuration(s)} ago`;
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
  // History responses and the latest reading both carry the catalog labels.
  const label = (name) => S.labels[name] || ((S.status && S.status.latest && S.status.latest.labels) || {})[name] || name;

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
  // Charts take every colour from CSS variables, so a theme change needs no redraw.
  $('theme').addEventListener('click', () => {
    const order = ['auto', 'light', 'dark'];
    const next = order[(order.indexOf(getItem('local', THEME_KEY) || 'auto') + 1) % 3];
    setItem('local', THEME_KEY, next);
    applyTheme(next);
  });
  applyTheme(getItem('local', THEME_KEY) || 'auto');

  // ---------------------------------------------------------------- API
  class Unauthorized extends Error {}
  async function api(path, timeoutMs) {
    const ctrl = timeoutMs ? new AbortController() : null;
    const timer = ctrl ? setTimeout(() => ctrl.abort(), timeoutMs) : null;
    try {
      const r = await fetch(path, { headers: { Authorization: `Bearer ${S.token}` }, cache: 'no-store', signal: ctrl ? ctrl.signal : undefined });
      if (r.status === 401) throw new Unauthorized('token rejected');
      if (!r.ok) throw new Error(`HTTP ${r.status} for ${path.split('?')[0]}`);
      return await r.json();
    } catch (e) {
      if (e && e.name === 'AbortError' && ctrl && ctrl.signal.aborted) throw new Error(`no answer within ${timeoutMs / 1000} s`);
      throw e;
    } finally {
      clearTimeout(timer);
    }
  }
  const iso = (t) => new Date(t * 1000).toISOString();

  // ---------------------------------------------------------------- render scheduling
  // Parts: live, frames, events. Marked dirty by events, drawn once in the next animation frame.
  const dirty = new Set();
  let frameRequest = 0;
  function invalidate(...parts) {
    for (const p of parts) dirty.add(p);
    if (!frameRequest) frameRequest = requestAnimationFrame(flush);
  }
  function flush() {
    frameRequest = 0;
    const parts = new Set(dirty);
    dirty.clear();
    if (parts.has('live')) renderLive();
    if (parts.has('frames')) renderFrames();
    if (parts.has('events')) renderEvents();
  }

  // ---------------------------------------------------------------- sign in / out
  function showLogin(message) {
    $('login').hidden = false; $('app').hidden = true; $('signout').hidden = true;
    $('login-error').textContent = message || '';
    $('token').focus();
  }
  function signOut(message) {
    S.running = false; S.token = null; S.lastId = null; S.epoch += 1;
    histReplay = null; S.histPending = false; clearTimeout(retryTimer); clearTimeout(snapshotTimer);
    S.snapshotOk = false; S.snapshotBackoff = 2000;
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
    invalidate('live');   // the Gateway card shows the stream state
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
      if (id !== null) S.lastId = id;  // even when handling threw: the event is skipped on resume, not replayed forever
    }
    return true;
  }

  function dispatch(type, d) {
    switch (type) {
      case 'hello':
        S.skew = d.server_time - Date.now() / 1000;
        setConn('live');
        if (d.resumed && S.snapshotOk) refreshStatus(); else loadSnapshot();
        break;
      case 'resync':
        loadSnapshot();
        break;
      case 'observation':
        if (S.status) { S.status.latest = d.latest; invalidate('live'); }
        toHistory(addObservation, d.record, d.latest);
        break;
      case 'diagnostic':
        toHistory(addDiagnostic, d);
        refreshStatusSoon();
        break;
      case 'radio':
        addFrame(d);
        if (d.outcome === 'rejected' || d.outcome === 'nack' || d.outcome === 'commit_failed') refreshStatusSoon();
        break;
      case 'rx':
        addAlive(d);
        break;
      case 'rx_fault':   // a bad reception: only the trailing-hour count is shown (rows: /v1/radio/faults)
        if (S.status) { S.status.rx_faults = d.summary; invalidate('live'); }
        break;
      case 'rx_fault_summary':   // the same count, changed as time passed (old ones left the hour)
        if (S.status) { S.status.rx_faults = d.summary; invalidate('live'); }
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
  // A failed snapshot is shown and retried with backoff (and by the next hello, resumed or not).
  let snapshotBusy = null, snapshotTimer = null;
  async function loadSnapshot() {
    if (snapshotBusy) return snapshotBusy;
    clearTimeout(snapshotTimer); snapshotTimer = null;
    const epoch = S.epoch;
    snapshotBusy = (async () => {
      try {
        const [status, frames, events] = await Promise.all([
          api('/v1/status'), api('/v1/radio?order=desc&limit=' + MAX_FRAMES), api('/v1/gateway/events?order=desc&limit=' + MAX_EVENTS),
        ]);
        S.status = status;
        S.frames = frames.rows;
        S.events = events.rows;
        invalidate('live', 'frames', 'events');
        S.snapshotOk = true; S.snapshotBackoff = 2000;
        await loadHistory();   // retries its own failures
      } catch (e) {
        if (epoch !== S.epoch) return;
        if (e instanceof Unauthorized) { signOut('The gateway rejected the token.'); return; }
        console.warn('snapshot:', e.message);
        S.snapshotOk = false;
        if (!S.hist) $('hist-note').textContent = `Could not load the dashboard: ${e.message} (retrying)`;
        const delay = S.snapshotBackoff;
        S.snapshotBackoff = Math.min(S.snapshotBackoff * 2, 60000);
        snapshotTimer = setTimeout(() => { if (S.running && epoch === S.epoch) loadSnapshot(); }, delay);
      } finally {
        snapshotBusy = null;
      }
    })();
    return snapshotBusy;
  }
  async function refreshStatus() {
    try { S.status = await api('/v1/status'); invalidate('live'); } catch (e) {
      if (e instanceof Unauthorized) signOut('The gateway rejected the token.');
    }
  }
  let statusTimer = null;
  function refreshStatusSoon() {
    clearTimeout(statusTimer);
    statusTimer = setTimeout(refreshStatus, 400);
  }

  // ---------------------------------------------------------------- live panel
  // Texts that count up with time register here; the 1 s tick rewrites them in place.
  let ages = [];   // [node, at (unix s), format(age s) -> text]
  function ageText(node, at, format) {
    const f = format || fmtAge;
    setText(node, f(now() - at));
    ages.push([node, at, f]);
    return node;
  }
  // The states that flip with time alone; when one does, the tick redraws the live panel.
  function timeSignature() {
    const st = S.status;
    if (!st) return '';
    const l = st.latest;
    const age = l && l.effective_sampled_at !== null && l.effective_sampled_at !== undefined ? now() - l.effective_sampled_at : null;
    const rx = st.receiver;
    return `${age === null || age >= STALE_S}|${!!rx && (!rx.alive || now() - rx.last_seen > RX_SILENT_S)}`;
  }
  let liveSignature = '';

  // Status chips: one fixed slot each. A chip's level and text (what the live region announces)
  // change only with the state; its detail (ages, clock offset) is visual only and outside the
  // live region, so a screen reader hears a state change once, not every second.
  // The visible chips are the readable state; the sr-only live region only carries changes (not
  // the first state) and is emptied again after SAID_HOLD_MS, so reading the page in browse mode
  // meets each chip once, not twice. Emptying is a removal, which a polite region does not announce.
  const ICON = { good: '✓', warning: '!', critical: '✕', neutral: '•' };
  const CHIP_SLOTS = ['alarm', 'reading', 'quality', 'receiver', 'clock', 'link', 'energy', 'overdue'];
  const SAID_HOLD_MS = 10000;
  const chips = {};   // slot -> { box, icon, text, detail, said, key }
  let saidTimer = null;
  function announce(c, s) {
    setText(c.said, s);
    clearTimeout(saidTimer);
    saidTimer = setTimeout(() => { for (const x of Object.values(chips)) setText(x.said, ''); }, SAID_HOLD_MS);
  }

  function readingChip(latest) {
    if (!latest || latest.reason === 'no_observation') return ['neutral', 'No readings yet'];
    const age = latest.effective_sampled_at === null ? null : now() - latest.effective_sampled_at;
    if (latest.reason === 'unknown_clock') return ['warning', 'Latest reading has no time yet'];
    if (latest.reason === 'future_clock_at_receipt') return ['critical', 'Latest reading is time-stamped in the future'];
    if (latest.reason === 'time_uncertain') return ['warning', 'Latest reading time is too uncertain'];
    if (age !== null && age >= STALE_S) return ['warning', 'Reading stale', `(${fmtAge(age)})`];
    if (latest.reason === 'sensor_fault') return ['critical', 'Sensor fault: no valid field'];
    return ['good', 'Reading fresh', `(${fmtAge(age)})`];
  }
  function chipSpecs(st) {
    const c = {};
    c.alarm = st.alarm ? ['critical', `Alarm: ${st.alarm}`] : ['good', 'No key-reuse alarm'];
    c.reading = readingChip(st.latest);
    const obs = st.latest && st.latest.observation;
    if (obs) {
      const q = obs.quality;
      c.quality = [q === 'valid' ? 'good' : q === 'partial' ? 'warning' : 'critical',
        q === 'valid' ? 'All sensors valid' : q === 'partial' ? 'Some sensors faulty' : 'All sensors faulty'];
    }
    const rx = st.receiver;
    if (!rx) c.receiver = ['neutral', 'Receiver: no report yet'];
    else {
      const age = now() - rx.last_seen;
      c.receiver = !rx.alive || age > RX_SILENT_S ? ['critical', 'Receiver silent', `(last report ${fmtAge(age)})`] : ['good', 'Receiver alive'];
    }
    const hc = st.host_clock;
    c.clock = !hc ? ['neutral', 'Host clock: not checked (demo)']
      : [hc.state === 'ok' ? 'good' : hc.state === 'bad' ? 'critical' : 'warning', `Host clock ${hc.state}`,
        hc.offset_s !== null && hc.offset_s !== undefined ? `(${hc.offset_s >= 0 ? '+' : ''}${hc.offset_s.toFixed(3)} s)` : ''];
    const dg = st.node_diagnostics;
    if (!dg) c.link = ['neutral', 'Node: no health report yet'];
    else {
      c.link = [dg.link === 'linked' ? 'good' : 'warning', `Node link ${dg.link}`];
      c.energy = [dg.energy_state === 'critical' ? 'critical' : dg.energy_state === 'conserve' ? 'warning' : 'good', `Energy ${dg.energy_state}`];
      const age = now() - dg.received_at;
      if (age > DIAG_OVERDUE_S) c.overdue = ['warning', 'Node health report overdue', `(${fmtAge(age)})`];
    }
    return c;
  }
  function renderChips() {
    const st = S.status;
    if (!st) return;
    const specs = chipSpecs(st);
    for (const slot of CHIP_SLOTS) {
      let c = chips[slot];
      if (!c) {
        c = chips[slot] = {
          icon: el('span', { class: 'icon', 'aria-hidden': 'true' }), text: el('span'), detail: el('span', { class: 'detail' }),
          said: el('span'), key: null,
        };
        c.box = el('span', { class: 'chip', hidden: true }, c.icon, c.text, c.detail);
        $('chips').append(c.box);
        $('chips-live').append(c.said);
      }
      const [level, text, detail] = specs[slot] || [];
      const key = level ? `${level}|${text}` : '';
      if (key !== c.key) {
        const first = c.key === null;   // the first state is not announced, only changes are
        c.key = key;
        c.box.hidden = !level;
        if (level) { c.box.dataset.level = level; setText(c.icon, ICON[level]); setText(c.text, text); }
        if (!first) { if (level) announce(c, `${text}. `); else setText(c.said, ''); }
      }
      setText(c.detail, detail || '');
    }
  }

  // Weather tiles and station/power tiles: the gateway's DIAGNOSTIC_FIELDS (observations.diagnostic
  // of a history response) say which is which; until one has loaded, every tile is in the first box.
  function renderReadings() {
    const box = $('readings'), station = $('readings-station');
    clear(box); clear(station);
    $('readings-station-head').hidden = true;
    const latest = S.status && S.status.latest;
    const meta = $('reading-meta');
    if (!latest || !latest.observation) { meta.textContent = 'No observation stored yet.'; return; }
    const obs = latest.observation;
    const at = latest.effective_sampled_at;
    const age = at === null ? null : now() - at;
    const stale = age === null || age >= STALE_S;
    for (const name of Object.keys(latest.fields_available || {})) {   // catalog order (gateway)
      const isStation = !!S.diagnostic && S.diagnostic.has(name);
      (isStation ? station : box).append(readingTile(name, obs, latest.units || {}, at, stale));
      if (isStation) $('readings-station-head').hidden = false;
    }
    meta.textContent = `Sample ${fmtTime(at, true)} · epoch ${obs.session} · sequence ${obs.sequence} · ` +
      `time ${latest.time_basis}${latest.time_uncertainty_s ? ` (±${fmtNum(latest.time_uncertainty_s, 1)} s)` : ''} · ` +
      `quality ${obs.quality} · energy ${obs.energy_state} · received ${fmtTime(latest.received_at, true)}`;
  }

  function readingTile(name, obs, units, at, stale) {
    let value = obs[name];
    let state = 'ok', flag = '';
    if (name === 'wind_dir_deg' && obs.wind_calm) value = 'calm';
    if (value === null) { state = 'fault'; flag = 'sensor fault'; }   // present and INVALID
    else if (stale) { state = 'stale'; flag = 'stale'; }
    const qual = obs.qualifiers && obs.qualifiers[name];
    const sub = el('div', { class: 'sub' });
    if (at === null) sub.textContent = '—'; else ageText(sub, at);
    return el('div', { class: 'tile', 'data-state': state },
      el('div', { class: 'label', text: label(name) }),
      el('div', { class: 'value' }, value === null ? '—' : fmtNum(value), units[name] && value !== null && value !== 'calm' ? el('span', { class: 'unit', text: units[name] }) : null),
      sub,
      flag ? el('div', { class: 'flag', text: flag }) : null,
      qual ? el('div', { class: 'flag', text: qual.replace(/_/g, ' ') }) : null);
  }

  function kv(target, rows) {
    clear(target);
    for (const [k, v, level] of rows) {
      const dd = el('dd', { 'data-level': level || null });
      if (v && typeof v === 'object') dd.append(v); else dd.textContent = v === null || v === undefined ? '—' : String(v);
      target.append(el('dt', { text: k }), dd);
    }
  }
  const sinceText = (s) => `· ${fmtAge(s)}`;

  function renderNode() {
    const d = S.status && S.status.node_diagnostics;
    if (d) ageText($('node-age'), d.received_at, sinceText); else setText($('node-age'), '');
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
      ...healthRows(d),
    ]);
  }
  // Version 6 health-report keys (design section 6.1). A report from older firmware lacks them
  // (undefined: '—'). A key the node sent as its none code is null; the report's fitted byte, as
  // power_sensor_faults and power_not_measured, says why: a fitted source failed ('sensor fault') or
  // this build has no source ('not measured in this build'). Without the lists: 'not measured'.
  const isFault = (d, key) => (d.power_sensor_faults || []).includes(key);
  function nullText(d, key) {
    if (isFault(d, key)) return 'sensor fault';
    if ((d.power_not_measured || []).includes(key)) return NOT_MEASURED;
    return 'not measured';
  }
  function healthValue(d, key, unit, digits) {
    const v = d[key];
    if (v === undefined) return '—';
    if (v === null) return nullText(d, key);
    return `${fmtNum(v, digits)}${unit ? ` ${unit}` : ''}`;
  }
  // A health-table row: label, value, and 'warning' for a sensor fault.
  const healthRow = (label, d, key, unit, digits) => [label, healthValue(d, key, unit, digits), isFault(d, key) ? 'warning' : null];
  // A named health key (charger stage, active input) as text, for the node table and a state band:
  // `older` when an older report lacks it, its name, or why it is null (the fitted byte: 'sensor fault'
  // or 'not measured in this build'; a null without either list is 'not reported').
  function stateText(d, key, names, older) {
    const v = d[key];
    if (v === undefined) return older;
    if (v !== null) return names[v] || String(v);
    return isFault(d, key) || (d.power_not_measured || []).includes(key) ? nullText(d, key) : 'not reported';
  }
  // no_input: the charger reports that neither input powers it (phase C at night; design section 6.3).
  const INPUTS = { solar: 'solar', usb_c: 'USB-C', no_input: 'no input' };
  const STAGES = { precharge: 'pre-charge', cc: 'constant current', cv: 'constant voltage', topoff: 'top-off',
    terminated: 'terminated', not_charging: 'not charging' };
  const inputText = (d) => stateText(d, 'charger_active_input', INPUTS, '—');
  function chargerText(d) {
    if (d.charger_input_power_ok === undefined) return '—';
    if (d.charger_input_power_ok === null) return stateText(d, 'charger_input_power_ok', {}, '—');
    const parts = [d.charger_input_power_ok ? 'input power good' : 'no input power', d.charger_charging ? 'charging' : 'not charging'];
    if (d.charger_fault) parts.push('fault');
    if (d.charger_stage) parts.push(`stage ${STAGES[d.charger_stage] || d.charger_stage}`);
    return parts.join(', ');
  }
  // last_crash_pc: null = no crash since power-up; 'ffffffff' (protocol.CRASH_PC_UNTRUSTED) = a crash whose
  // stacked frame was not in RAM, so no PC was recorded (docs/protocol.md section 4, fault.c).
  const CRASH_PC_UNTRUSTED = 'ffffffff';
  function crashPcText(pc) {
    if (pc === undefined) return '—';
    if (pc === null) return 'none';
    return pc === CRASH_PC_UNTRUSTED ? 'crash, frame not trusted (no PC)' : `0x${pc}`;
  }
  function healthRows(d) {
    const count = (k) => [healthValue(d, k, '', 0), d[k] > 0 ? 'warning' : null];
    return [
      ['Last crash PC', crashPcText(d.last_crash_pc), d.last_crash_pc ? 'warning' : null],
      ['Boots since power-up', healthValue(d, 'boots_since_power_up', '', 0)],
      ['Radio TX timeouts since boot', ...count('tx_timeouts_since_boot')],
      ['I2C bus recoveries since boot', ...count('i2c_recoveries_since_boot')],
      healthRow('MCU supply (VDDA)', d, 'mcu_supply_mv', 'mV', 0),
      healthRow('Power monitor die temperature', d, 'power_monitor_temp_c', '°C', 1),
      healthRow('Battery state of charge (gauge)', d, 'battery_soc_pct', '%', 1),
      healthRow('State of charge rate (+ charging)', d, 'battery_soc_rate_pct_h', '%/h', 1),
      ['Charger status', chargerText(d), d.charger_fault ? 'critical' : isFault(d, 'charger_charging') ? 'warning' : null],
      ['Charger active input', inputText(d)],
      ['Charger-reported input', healthPair(d, 'charger_reported_input_mv', 'charger_reported_input_ma')],
      ['Charger-reported battery', healthPair(d, 'charger_reported_battery_mv', 'charger_reported_battery_ma')],
      healthRow('Charger die temperature', d, 'charger_temp_c', '°C', 1),
      healthRow('Pack temperature', d, 'pack_temp_c', '°C', 1),
    ];
  }
  const healthPair = (d, mv, ma) => (d[mv] === undefined && d[ma] === undefined ? '—' : `${healthValue(d, mv, 'mV', 0)} · ${healthValue(d, ma, 'mA', 0)}`);

  function renderRx() {
    const rx = S.status && S.status.receiver;
    if (rx) ageText($('rx-age'), rx.last_seen, sinceText); else setText($('rx-age'), '');
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
      ['Bad receptions (last hour)', badReceptions(S.status.rx_faults), badLevel(S.status.rx_faults)],
      ['CRC / header errors since boot', rx.crc_errors === undefined ? null : `${rx.crc_errors} / ${rx.hdr_errors}`],
      ['Bad receptions not captured (overrun)', rx.fault_overruns, Number(rx.fault_overruns) > 0 ? 'warning' : null],
      ['Longest task (µs)', peak(rx.task_peak_us, rx.task_peak)],
      ['Longest interrupt (µs)', peak(rx.isr_peak_us, rx.isr_peak)],
      ['Trace drops', rx.trace_drops, Number(rx.trace_drops) > 0 ? 'warning' : null],
    ]);
  }
  // Bad receptions (#rx crc / #rx hdr) are normal at a few an hour (ambient 915 MHz traffic); the
  // gateway's threshold (warn_per_hour) marks an abnormal rate. The ones the gateway's rate limit
  // dropped in the same trailing hour (throttled) are counted apart.
  function badReceptions(f) {
    if (!f) return null;
    const text = `${f.crc} CRC · ${f.hdr} header`;
    return f.throttled ? `${text} (${f.throttled} more dropped by the rate limit in the last hour)` : text;
  }
  function badLevel(f) { return f && (f.crc + f.hdr > f.warn_per_hour || f.throttled > 0) ? 'warning' : null; }
  function peak(us, word) { return us === undefined || us === null ? null : word ? `${us} (${word})` : String(us); }

  function renderGateway() {
    const st = S.status;
    if (!st) return;
    $('station').textContent = `${st.station} · ${st.mode}`;
    const nc = st.node_counter || {};
    const hc = st.host_clock;
    let clock = 'not checked (demo)';
    if (hc) clock = hc.checked_at ? el('span', {}, `${hc.state}, checked `, ageText(el('span'), hc.checked_at)) : hc.state;
    kv($('gw'), [
      ['Station', st.station],
      ['Mode', st.mode],
      ['Accepted (this run)', fmtNum(st.accepted_this_process)],
      ['Rejected (this run)', fmtNum(st.rejected_this_process), st.rejected_this_process > 0 ? 'warning' : null],
      ['NACKed (this run)', fmtNum(st.nacked_this_process), st.nacked_this_process > 0 ? 'warning' : null],
      ['Node counter mark', fmtNum(nc.max_node_counter, 0)],
      ['Counter regressions', fmtNum(nc.counter_regression, 0), nc.counter_regression ? 'critical' : null],
      ['Host clock', clock, hc && hc.state === 'bad' ? 'critical' : null],
      ['Event stream', S.conn],
    ]);
  }

  function renderLive() {
    ages = [];
    liveSignature = timeSignature();
    renderChips(); renderReadings(); renderNode(); renderRx(); renderGateway();
  }
  // Every second: ages count up in place; a state that flips with time (stale reading, silent
  // receiver) redraws the panel once.
  function tick() {
    if (!S.running || !S.status) return;
    if (timeSignature() !== liveSignature) { invalidate('live'); return; }
    renderChips();
    const t = now();
    for (const [node, at, format] of ages) setText(node, format(t - at));
  }

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
  const following = () => !!S.hist && S.hist.range.span !== undefined;   // the data on screen follows live

  // Live data for the history charts. While a history request is in flight, each addition is
  // also queued and applied again to the response, so an event that raced the request is not
  // lost (the add functions ignore what is already there).
  let histReplay = null;
  function toHistory(add, ...args) {
    if (histReplay) histReplay.push([add, args]);   // for the pending response (bounded by its timeout)
    if (following()) add(...args);                  // for the data on screen
  }
  // A bucketed series (bucket_s > 0) holds averages, counts or last values per bucket: a raw
  // point does not belong in it. Reload the history instead, at most once per bucket.
  let reloadTimer = null, reloadDue = 0;
  function reloadHistorySoon(bucket) {
    const due = S.histLoadedAt + bucket * 1000;
    if (reloadTimer && reloadDue <= due) return;
    clearTimeout(reloadTimer);
    reloadDue = due;
    reloadTimer = setTimeout(() => {
      reloadTimer = null;
      if (S.running && following()) loadHistory();
    }, Math.max(0, due - Date.now()));
  }

  function addObservation(r, latest) {
    const o = S.hist.observations;
    const t = r.effective_sampled_at;
    if (t === null || t === undefined) return;
    if (o.bucket_s) { reloadHistorySoon(o.bucket_s); return; }
    // A field the loaded range has never seen: its label and catalog place come with a reload
    // (spaced like a 60 s bucket, so a record outside the reloaded window cannot loop).
    if (Object.keys((latest && latest.fields_available) || {}).some((n) => n in r && !o.fields.includes(n))) reloadHistorySoon(60);
    const at = insertionPoint(o.t, t);
    for (let i = at - 1; i >= 0 && o.t[i] === t; i--) if (o.session[i] === r.session) return;  // already loaded
    o.t.splice(at, 0, t);
    o.basis.splice(at, 0, r.time_basis);
    o.quality.splice(at, 0, r.quality);
    o.session.splice(at, 0, r.session);
    for (const name of o.fields) o.values[name].splice(at, 0, name in r ? r[name] : null);
    scheduleHistory('sensors', 'power');
  }
  function addFrame(f) {
    if (S.frames.some((x) => x.id === f.id)) return;
    S.frames.unshift(f);
    S.frames.length = Math.min(S.frames.length, MAX_FRAMES);
    invalidate('frames');
    toHistory(addRadioPoint, f);
  }
  function addRadioPoint(f) {
    const r = S.hist.radio;
    if (r.bucket_s) { reloadHistorySoon(r.bucket_s); return; }
    if (r.t.length && r.t[r.t.length - 1] >= f.received_at) return;
    r.t.push(f.received_at); r.rssi_dbm.push(f.rssi_dbm); r.snr_db.push(f.snr_db); r.rssi_min.push(f.rssi_dbm);
    r.frames.push(1); r.kind.push(f.kind); r.outcome.push(f.outcome); r.counter.push(f.counter);
    scheduleHistory('link');
  }
  function addAlive(a) {
    if (S.status) {
      const rx = S.status.receiver || {};
      S.status.receiver = Object.assign({}, rx, {
        alive: true, last_seen: a.received_at, uptime: a.uptime_s, forwarded: a.forwarded, dropped: a.dropped,
        acks: a.acks, diag: a.diag, listening: String(a.listening), relistens: a.relistens, uart_errors: a.uart_errors,
        stack_peak: a.stack_peak, crc_errors: a.crc_errors, hdr_errors: a.hdr_errors, fault_overruns: a.fault_overruns,
        task_peak_us: a.task_peak_us,
        task_peak: a.task_peak, isr_peak_us: a.isr_peak_us, isr_peak: a.isr_peak, trace_drops: a.trace_drops,
      });
      invalidate('live');
    }
    toHistory(addAlivePoint, a);
  }
  const ALIVE_KEYS = ['uptime_s', 'forwarded', 'dropped', 'acks', 'diag', 'listening', 'relistens', 'uart_errors', 'stack_peak',
    'crc_errors', 'hdr_errors', 'fault_overruns', 'task_peak_us', 'task_peak', 'isr_peak_us', 'isr_peak', 'trace_drops'];   // web.ALIVE_FIELDS
  function addAlivePoint(a) {
    const h = S.hist.receiver;
    if (h.bucket_s) { reloadHistorySoon(h.bucket_s); return; }
    if (h.t.length && h.t[h.t.length - 1] >= a.received_at) return;
    h.t.push(a.received_at);
    for (const k of ALIVE_KEYS) if (h[k]) h[k].push(a[k]);
    scheduleHistory('rx');
  }
  function addDiagnostic(d) {
    const list = S.hist.diagnostics;
    if (list.some((x) => x.epoch === d.epoch && x.uptime_s === d.uptime_s)) return;
    list.push(d);
    list.sort((a, b) => a.received_at - b.received_at);
    scheduleHistory('link', 'node', 'charger');
  }
  function addEvent(e) {
    if (S.events.some((x) => x.id === e.id)) return;
    S.events.unshift(e);
    S.events.length = Math.min(S.events.length, MAX_EVENTS);
    invalidate('events');
    toHistory(addHistoryEvent, e);
  }
  function addHistoryEvent(e) {
    if (S.hist.events.some((x) => x.id === e.id)) return;
    S.hist.events.push(e);
    scheduleHistory();   // only markers may change: renderHistory redraws the groups whose markers did
  }

  // ---------------------------------------------------------------- history
  function rangeBounds() {
    if (S.range.span !== undefined) { const to = now(); return [to - S.range.span, to]; }
    return [S.range.from, S.range.to];
  }
  // On screen: the bounds of the data shown, following live or fixed.
  function histBounds() {
    const r = S.hist.range;
    if (r.span !== undefined) { const to = now(); return [to - r.span, to]; }
    return [S.hist.from, S.hist.to];
  }
  // One history request at a time is current (S.histSeq); an older one that lands is dropped.
  // A failure keeps the previous data with its own range, shows the error and retries with backoff.
  let retryTimer = null;
  async function loadHistory() {
    const seq = ++S.histSeq, epoch = S.epoch, range = S.range;
    clearTimeout(reloadTimer); reloadTimer = null;   // this request is the reload
    clearTimeout(retryTimer); retryTimer = null;
    S.histLoadedAt = Date.now();
    S.histPending = true;
    histReplay = range.span !== undefined ? histReplay || [] : null;
    const [from, to] = rangeBounds();
    const width = Math.max(320, Math.min(2400, document.documentElement.clientWidth));
    const points = Math.max(300, Math.min(3000, Math.round(width * 1.5)));
    $('hist-note').textContent = S.histError ? `${historyNote()} · loading…` : 'Loading…';
    let h;
    try {
      h = await api(`/v1/history?from=${encodeURIComponent(iso(from))}&to=${encodeURIComponent(iso(to))}&max_points=${points}`, HISTORY_TIMEOUT_MS);
    } catch (e) {
      if (seq !== S.histSeq || epoch !== S.epoch) return;   // superseded: the newer request reports
      S.histPending = false;
      histReplay = null;
      if (e instanceof Unauthorized) { signOut('The gateway rejected the token.'); return; }
      S.histError = e.message;
      renderHistory();   // the previous data, if any, under the error note
      if (!S.hist) $('hist-note').textContent = historyNote();
      const delay = S.histBackoff;
      S.histBackoff = Math.min(S.histBackoff * 2, 60000);
      retryTimer = setTimeout(() => { if (S.running && epoch === S.epoch && seq === S.histSeq) loadHistory(); }, delay);
      return;
    }
    if (seq !== S.histSeq || epoch !== S.epoch) return;     // a newer range was asked for meanwhile
    S.histPending = false; S.histError = null; S.histBackoff = 2000;
    h.range = range;
    S.hist = h;
    const queued = histReplay || [];
    histReplay = null;
    for (const [add, args] of queued) toHistory(add, ...args);
    const labels = h.observations.labels || {};
    if (Object.keys(labels).some((n) => S.labels[n] !== labels[n])) { Object.assign(S.labels, labels); invalidate('live'); }
    const diagnostic = h.observations.diagnostic;
    if (diagnostic && (!S.diagnostic || diagnostic.length !== S.diagnostic.size || diagnostic.some((n) => !S.diagnostic.has(n)))) {
      S.diagnostic = new Set(diagnostic); invalidate('live');   // the tiles move to their box
    }
    clearTimeout(histTimer); histTimer = null; histDirty.clear();
    renderHistory();
  }
  const historyNote = () => (S.histError ? `Could not load history: ${S.histError} (retrying)` : '');

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
    loadHistory();
  }));
  $('custom').addEventListener('submit', (ev) => {
    ev.preventDefault();
    const from = new Date($('c-from').value).getTime() / 1000;
    const to = new Date($('c-to').value).getTime() / 1000;
    if (!isFinite(from) || !isFinite(to) || from >= to) { $('custom-error').textContent = 'Choose a start before the end.'; return; }
    $('custom-error').textContent = '';
    S.range = { from, to };
    loadHistory();
  });

  // Live additions are batched: one redraw of the touched chart groups per 500 ms at most.
  let histTimer = null;
  const histDirty = new Set();
  function scheduleHistory(...groups) {
    for (const g of groups) histDirty.add(g);
    if (histTimer) return;
    histTimer = setTimeout(() => {
      histTimer = null;
      trimHistory();
      const only = new Set(histDirty);
      histDirty.clear();
      renderHistory(only, SLIDE_S);
    }, 500);
  }
  // While following live, points older than the window are dropped, so a page left open for days
  // keeps a bounded history instead of growing forever.
  function trimHistory() {
    if (!following()) return;
    const cutoff = now() - S.hist.range.span;
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
      else if (e.kind === 'serial-reopen') m.push({ t: e.at, label: 'serial reopen', group: 'rx' });
      else if (e.kind === 'receiver-silent') m.push({ t: e.at, label: 'RX silent', group: 'rx' });
    }
    return m.sort((a, b) => a.t - b.t);
  }
  const MARKER_GROUPS = { sensors: ['node', 'gateway'], power: ['node', 'gateway'], charger: ['node', 'gateway'], link: ['node', 'rx'], node: ['node', 'gateway'], rx: ['rx', 'gateway'] };
  let drawn = null;   // what is on screen: { from, to, width, markers: {group: key} }

  // Draw the chart groups in `only` (all of them when omitted). A group is redrawn anyway when
  // its markers changed, and every group is when the time axis moved since the last full redraw
  // by a pixel or more, or by `slack` seconds if that is more (live batches pass the slide
  // period: between slides only the touched groups redraw, the slide moves every axis).
  // Nothing is drawn while a history request is pending: its response redraws everything.
  function renderHistory(only, slack) {
    const h = S.hist;
    if (!h || S.histPending) return;
    const [from, to] = histBounds();
    const width = chartWidth();
    const all = markersFor(h);
    const markers = {}, keys = {};
    for (const g of GROUPS) {
      markers[g] = all.filter((m) => MARKER_GROUPS[g].includes(m.group));
      keys[g] = markers[g].map((m) => `${m.t}:${m.label}`).join('|');
    }
    const drift = Math.max((to - from) / (width - M.l - M.r), slack || 0);
    const redrawAll = !only || !drawn || drawn.width !== width || Math.abs(to - drawn.to) >= drift || Math.abs(from - drawn.from) >= drift;
    const groups = GROUPS.filter((g) => redrawAll || only.has(g) || drawn.markers[g] !== keys[g]);
    // the axis drift is measured from the last full redraw, so partial redraws cannot accumulate it
    drawn = redrawAll ? { from, to, width, markers: keys } : Object.assign(drawn, { markers: keys });

    const o = h.observations;
    const notes = [`${fmtTime(from, true)} – ${fmtTime(to, true)}`];
    if (S.histError) notes.unshift(historyNote());
    if (o.bucket_s) notes.push(`sensor values averaged over ${fmtDuration(o.bucket_s)} (counters: last value)`);
    if (h.radio.bucket_s) notes.push(`radio averaged over ${fmtDuration(h.radio.bucket_s)}`);
    if (o.unknown_time_count) notes.push(`${o.unknown_time_count} reading(s) with no time yet are not plotted`);
    if (following()) notes.push('following live');
    $('hist-note').textContent = notes.join(' · ');

    const stepChart = (title, unit, t, v, gap, m, extra) => chart(Object.assign({
      title, unit, from, to, markers: m, integer: true, series: [{ name: title, cls: 'c1', t, v, gap, step: true }],
    }, extra));
    const diag = h.diagnostics;
    const dt = diag.map((d) => d.received_at);
    // One health-report value over time (version 6 keys: older reports lack them).
    const diagChart = (title, unit, key, m, zero) => chart({
      title, unit, from, to, markers: m, zero, empty: diagEmpty(diag, key),
      series: [{ name: title, cls: 'c1', t: dt, v: diag.map((d) => d[key]), gap: 2000, dots: true }],
    });
    const draw = {
      sensors(box) {
        if (!o.fields.length) box.append(el('p', { class: 'muted small', text: 'No observations with a known time in this range.' }));
        const gap = o.bucket_s ? o.bucket_s * 1.5 : 110;
        for (const name of o.fields) {
          if (POWER_FIELDS.has(name)) continue;   // drawn in the power group
          const title = label(name);   // S.labels already holds this response's labels
          box.append(chart({
            title, unit: o.units[name], from, to, markers: markers.sensors,
            series: [{ name: title, cls: 'c1', t: o.t, v: o.values[name], basis: o.basis, gap, dots: name === 'wind_dir_deg', faults: true }],
          }));
        }
      },
      link(box) {
        const r = h.radio;
        const gap = r.bucket_s ? r.bucket_s * 1.5 : 0;
        box.append(chart({
          title: 'Signal strength (RSSI)', unit: 'dBm', from, to, markers: markers.link,
          series: [
            { name: 'Uplink (RX hears node)', cls: 'c1', t: r.t, v: r.rssi_dbm, gap, dots: !r.bucket_s },
            { name: 'Downlink ACK (node hears gateway)', cls: 'c2', t: dt, v: diag.map((d) => d.ack_rssi_dbm), gap: 2000, dots: true },
          ],
        }));
        box.append(chart({
          title: 'Signal-to-noise ratio (SNR)', unit: 'dB', from, to, markers: markers.link,
          series: [
            { name: 'Uplink (RX hears node)', cls: 'c1', t: r.t, v: r.snr_db, gap, dots: !r.bucket_s },
            { name: 'Downlink ACK (node hears gateway)', cls: 'c2', t: dt, v: diag.map((d) => d.ack_snr_db), gap: 2000, dots: true },
          ],
        }));
        const fine = ['ack', 'diag', 'duplicate'];
        const bad = r.outcome.map((out) => (typeof out === 'object' && out
          ? Object.entries(out).reduce((s, [k, c]) => s + (fine.includes(k) ? 0 : c), 0)
          : (fine.includes(out) ? 0 : 1)));
        const problem = { name: 'NACKed, rejected or dropped', cls: r.bucket_s ? 'c2' : 'c1', t: r.t, v: bad, gap, dots: true, skipZero: true };
        box.append(chart(r.bucket_s ? {
          title: `Frames per ${fmtDuration(r.bucket_s)}`, unit: 'count', from, to, markers: markers.link, integer: true,
          series: [{ name: 'All frames', cls: 'c1', t: r.t, v: r.frames, gap }, problem],
        } : {
          title: 'Problem frames (NACK, rejected, dropped by RX)', unit: 'count', from, to, markers: markers.link, integer: true,
          empty: r.t.length ? 'None in this range' : 'No frames in this range', series: [problem],
        }));
      },
      node(box) {
        if (!diag.length) { box.append(el('p', { class: 'muted small', text: 'No node health reports in this range (one every 15 minutes).' })); return; }
        const m = markers.node;
        box.append(stateChart('Energy state', from, to, dt, diag.map((d) => d.energy_state),
          { surplus: 'st-s3', normal: 'st-s1', conserve: 'st-warning', critical: 'st-critical' }, m));
        box.append(stateChart('Link state', from, to, dt, diag.map((d) => d.link), { linked: 'st-good', probing: 'st-warning' }, m));
        for (const [title, key, unit] of [
          ['Journal pending', 'journal_pending', 'records'], ['Journal lost (total)', 'journal_lost_total', 'records'],
          ['Missed ACKs since boot', 'missed_acks_since_boot', 'count'], ['Crashes since power-up', 'crashes_since_power_up', 'count'],
          ['Boot epoch', 'epoch', ''], ['Abandoned records (total)', 'abandoned_total', 'records'],
          ['Boots since power-up', 'boots_since_power_up', 'count'], ['Radio TX timeouts since boot', 'tx_timeouts_since_boot', 'count'],
          ['I2C bus recoveries since boot', 'i2c_recoveries_since_boot', 'count'], ['MCU supply (VDDA)', 'mcu_supply_mv', 'mV'],
        ]) box.append(stepChart(title, unit, dt, diag.map((d) => d[key]), 2000, m, { empty: diagEmpty(diag, key) }));
        box.append(diagChart('Power monitor die temperature', '°C', 'power_monitor_temp_c', m));
      },
      power(box) { drawPower(box, { o, diag, from, to, m: markers.power }); },
      charger(box) { drawCharger(box, { diag, dt, from, to, m: markers.charger, diagChart }); },
      rx(box) {
        const a = h.receiver;
        if (!a.t.length) { box.append(el('p', { class: 'muted small', text: 'No RX reports in this range (one a minute while the gateway serves a receiver).' })); return; }
        const gap = a.bucket_s ? a.bucket_s * 1.5 : 150;
        for (const [title, key, unit] of [
          ['Frames forwarded', 'forwarded', 'count'], ['Frames dropped by RX', 'dropped', 'count'], ['Re-listens', 'relistens', 'count'],
          ['UART errors', 'uart_errors', 'count'], ['Stack peak', 'stack_peak', 'bytes'], ['RX uptime', 'uptime_s', 's'],
          ['CRC errors (bad receptions)', 'crc_errors', 'count'], ['Header errors (bad receptions)', 'hdr_errors', 'count'],
          ['Longest task', 'task_peak_us', 'µs'], ['Longest interrupt', 'isr_peak_us', 'µs'],
        ]) if (a[key]) box.append(stepChart(title, unit, a.t, a[key], gap, markers.rx));
      },
    };
    const BOX = { sensors: 'c-sensors', power: 'c-power', charger: 'c-charger', link: 'c-link', node: 'c-node', rx: 'c-rx' };
    for (const g of groups) {
      const box = $(BOX[g]);
      clear(box);
      draw[g](box);
    }
  }

  // ---------------------------------------------------------------- power view
  // What an empty health-report chart says: a key no report in the range carries comes from older
  // firmware; a key every report sends as its none code is a sensor fault when the reports list it in
  // power_sensor_faults (its source is fitted), and otherwise not measured by this build.
  function diagEmpty(diag, key) {
    if (!diag.length) return 'No health reports in this range';
    if (diag.every((d) => d[key] === undefined)) return 'Not in these health reports (older firmware)';
    if (!diag.every((d) => d[key] === null || d[key] === undefined)) return undefined;
    if (diag.some((d) => isFault(d, key))) return 'Sensor fault (no value in these health reports)';
    return 'Not measured in this build';
  }
  function absentSlot(title) {
    return el('figure', { class: 'chart absent', 'data-absent': 'true' },
      el('figcaption', {}, el('span', { class: 'ct', text: title })), el('p', { class: 'muted small', text: NOT_MEASURED }));
  }
  function railCharts(rail, a) {
    const { o, from, to, m } = a;
    const gap = o.bucket_s ? o.bucket_s * 1.5 : 110;
    const slots = [rail.v, rail.i, ...(rail.counters || [])].filter(Boolean);
    if (!slots.some((n) => o.fields.includes(n))) {   // the whole rail: one line, not empty charts
      return el('p', { class: 'muted small absent-rail', text: `${rail.name}: ${NOT_MEASURED}` });
    }
    const div = el('div', { class: 'rail' }, el('h4', { text: rail.name }));
    for (const name of slots) {
      const title = label(name);
      if (!o.fields.includes(name)) { div.append(absentSlot(title)); continue; }
      div.append(chart({
        title, unit: o.units[name], from, to, markers: m, zero: rail.signed && name === rail.i ? SIGNED : null,
        series: [{ name: title, cls: 'c1', t: o.t, v: o.values[name], basis: o.basis, gap, faults: true }],
      }));
    }
    return div;
  }
  // Charger status from the health reports' three booleans, as one state per report.
  function chargerState(d) {
    if (d.charger_input_power_ok === undefined) return 'not in report';
    if (d.charger_input_power_ok === null) return isFault(d, 'charger_input_power_ok') ? 'sensor fault' : 'not reported';
    if (d.charger_fault) return 'fault';
    if (d.charger_charging) return 'charging';
    return d.charger_input_power_ok ? 'input power, not charging' : 'no input power';
  }
  const CHARGER_CLASSES = { fault: 'st-critical', charging: 'st-s1', 'input power, not charging': 'st-s3', 'no input power': 'st-s2' };
  // The stage and active-input bands (phase C fills them; phases A and B show 'not measured in this build').
  const STAGE_CLASSES = { 'pre-charge': 'st-s2', 'constant current': 'st-s1', 'constant voltage': 'st-s3', 'top-off': 'st-good',
    terminated: 'st-s4', 'sensor fault': 'st-warning' };
  const INPUT_CLASSES = { solar: 'st-s3', 'USB-C': 'st-s1', 'no input': 'st-s2', 'sensor fault': 'st-warning' };
  // Every-minute rails (observations): redrawn with the sensors.
  function drawPower(box, a) {
    if (!a.o.t.length) box.append(el('p', { class: 'muted small', text: 'No observations with a known time in this range.' }));
    for (const rail of RAILS) box.append(railCharts(rail, a));
  }
  // Every-15-minute power values (health reports): redrawn with the node charts.
  function drawCharger(box, a) {
    const { diag, dt, from, to, m, diagChart } = a;
    const soc = el('div', { class: 'rail' }, el('h4', { text: 'Battery state of charge (fuel gauge, health reports)' }));
    soc.append(diagChart('State of charge', '%', 'battery_soc_pct', m), diagChart('State of charge rate', '%/h', 'battery_soc_rate_pct_h', m, SIGNED));
    box.append(soc);
    const chg = el('div', { class: 'rail' }, el('h4', { text: 'Charger (health reports)' }));
    if (diag.length) {
      chg.append(stateChart('Charger status', from, to, dt, diag.map(chargerState), CHARGER_CLASSES, m));
      chg.append(stateChart('Charger stage', from, to, dt,
        diag.map((d) => stateText(d, 'charger_stage', STAGES, 'not in report')), STAGE_CLASSES, m));
      chg.append(stateChart('Charger active input', from, to, dt,
        diag.map((d) => stateText(d, 'charger_active_input', INPUTS, 'not in report')), INPUT_CLASSES, m));
    }
    for (const [title, unit, key] of [
      ['Charger-reported input voltage', 'mV', 'charger_reported_input_mv'], ['Charger-reported input current', 'mA', 'charger_reported_input_ma'],
      ['Charger-reported battery voltage', 'mV', 'charger_reported_battery_mv'], ['Charger-reported charge current', 'mA', 'charger_reported_battery_ma'],
      ['Charger die temperature', '°C', 'charger_temp_c'], ['Pack temperature', '°C', 'pack_temp_c'],
    ]) chg.append(diagChart(title, unit, key, m));
    box.append(chg);
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
    let lo = Infinity, hi = -Infinity, fault = false, reconstructed = false;
    for (const s of series) for (let i = 0; i < s.t.length; i++) {
      if (s.t[i] < from || s.t[i] > to) continue;
      const v = s.v[i];
      if (s.basis && s.basis[i] === 'reconstructed') reconstructed = true;
      if (v === null || v === undefined) { if (s.faults && v === null) fault = true; continue; }
      if (s.skipZero && v === 0) continue;
      if (v < lo) lo = v; if (v > hi) hi = v;
    }
    if (spec.zero && lo !== Infinity) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }   // the zero line is always in view
    const legend = series.length > 1 ? series.map((s) => [s.cls, s.name]) : [];
    if (spec.zero) legend.push(['zero', `above 0: ${spec.zero.above} · below 0: ${spec.zero.below}`]);
    if (fault) legend.push(['fault', 'sensor fault', true]);
    if (reconstructed) legend.push(['c1 dash', 'dashed: reconstructed time']);
    const fig = frame(spec, legend);
    const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `${spec.title} chart` });
    fig.append(svg);
    const plotBottom = H - M.b;
    if (lo === Infinity) {
      // A present field whose every reading is INVALID is a sensor fault, not missing data.
      const text = fault ? 'Sensor fault: no valid reading in this range' : spec.empty || 'No data in this range';
      svg.append(sv('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', class: 'empty' }, text));
      drawTimeAxis(svg, from, to, x, W, plotBottom, H - 6);
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
    drawTimeAxis(svg, from, to, x, W, plotBottom, H - 6);
    drawMarkers(svg, spec.markers || [], from, to, x, M.t - 4, plotBottom, true);
    if (spec.zero) {
      svg.append(sv('line', { x1: M.l, x2: W - M.r, y1: y(0), y2: y(0), class: 'zeroline' }));
      svg.append(sv('text', { x: W - M.r - 2, y: y(0) - 4, 'text-anchor': 'end', class: 'zero-label' }, spec.zero.above));
      svg.append(sv('text', { x: W - M.r - 2, y: y(0) + 11, 'text-anchor': 'end', class: 'zero-label' }, spec.zero.below));
    }

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
      // Dots: one path of zero-length segments with round caps, over a wider surface-coloured
      // path for the outline ring. Two nodes per series instead of one circle per point.
      // Never give these paths a dash class: Chrome drops zero-length subpaths when dashed.
      let pts = '';
      for (const i of lonely) {
        if (s.t[i] < from || s.t[i] > to) continue;
        pts += `M${x(s.t[i]).toFixed(1)},${y(s.v[i]).toFixed(1)}h0`;
      }
      if (pts) {
        const size = s.dots ? ' sm' : '';
        svg.append(sv('path', { d: pts, class: `pts-ring${size}` }));
        svg.append(sv('path', { d: pts, class: `pts${size} ${s.cls}` }));
      }
    }
    hover(fig, svg, spec, series, x, y, W);
    return fig;
  }

  function drawTimeAxis(svg, from, to, x, W, baseY, labelY) {
    svg.append(sv('line', { x1: M.l, x2: W - M.r, y1: baseY, y2: baseY, class: 'baseline' }));
    const [ticks, step] = timeTicks(from, to, Math.max(2, Math.floor((W - M.l - M.r) / 90)));
    for (const t of ticks) svg.append(sv('text', { x: x(t), y: labelY, 'text-anchor': 'middle', class: 'tick' }, timeLabel(t, step)));
  }
  // Event markers: dashed vertical lines from top to bottom; labelled (where they do not
  // collide) or with the label as a tooltip only.
  function drawMarkers(svg, markers, from, to, x, top, bottom, labelled) {
    let lastX = -Infinity;
    for (const m of markers) {
      if (m.t < from || m.t > to) continue;
      const mx = x(m.t);
      const line = sv('line', { x1: mx, x2: mx, y1: top, y2: bottom, class: 'marker' });
      const tip = sv('title', {}, `${m.label} · ${fmtTime(m.t, true)}`);
      svg.append(line);
      if (!labelled) { line.append(tip); continue; }
      const right = mx > x(to) - 90;   // near the right edge: label on the left of the line
      const text = sv('text', { x: right ? mx - 3 : mx + 3, y: top, 'text-anchor': right ? 'end' : 'start', class: 'marker-label' },
        mx - lastX > 70 ? m.label : '');
      text.append(tip);
      svg.append(text);
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

  // Crosshair and tooltip: at most one update per animation frame; layout is read once, before
  // anything is written, and the tooltip is anchored by its left or right edge (no width read).
  let pointer = null;   // { title, x }: where the pointer rests, so a redrawn chart keeps its tooltip
  function hover(fig, svg, spec, series, x, y, W) {
    const cross = sv('line', { y1: M.t, y2: H - M.b, class: 'cross', visibility: 'hidden' });
    svg.append(cross);
    const dots = series.map((s) => { const c = sv('circle', { r: 4, class: `hover-dot ${s.cls}`, visibility: 'hidden' }); svg.append(c); return c; });
    const tip = el('div', { class: 'tip', hidden: true });
    fig.append(tip);
    const hit = sv('rect', { x: M.l, y: 0, width: W - M.l - M.r, height: H, fill: 'transparent' });
    svg.append(hit);
    let pending = 0, lastX = 0;
    const hide = () => {
      cancelAnimationFrame(pending); pending = 0;
      if (pointer && pointer.title === spec.title) pointer = null;
      cross.setAttribute('visibility', 'hidden'); dots.forEach((d) => d.setAttribute('visibility', 'hidden')); tip.hidden = true;
    };
    hit.addEventListener('pointerleave', hide);
    hit.addEventListener('pointermove', (ev) => {
      lastX = ev.clientX;
      pointer = { title: spec.title, x: lastX };
      if (!pending) pending = requestAnimationFrame(update);
    });
    if (pointer && pointer.title === spec.title) { lastX = pointer.x; pending = requestAnimationFrame(update); }
    function update() {
      pending = 0;
      const box = svg.getBoundingClientRect();
      const figBox = fig.getBoundingClientRect();
      const px = (lastX - box.left) * W / box.width;
      const t = spec.from + (px - M.l) / (W - M.l - M.r) * (spec.to - spec.from);
      let best = null;
      series.forEach((s, k) => {
        const i = nearest(t, s.t);
        dots[k].setAttribute('visibility', 'hidden');
        if (i < 0) return;
        const dist = Math.abs(s.t[i] - t);
        if (!best || dist < best.dist) best = { dist, t: s.t[i] };
      });
      if (!best || Math.abs(x(best.t) - px) > 40) {
        pending = 0; cross.setAttribute('visibility', 'hidden'); tip.hidden = true;   // pointer still here: keep it
        return;
      }
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
      const at = lastX - figBox.left;
      if (at > figBox.width / 2) { tip.style.left = 'auto'; tip.style.right = `${figBox.width - at + 12}px`; }
      else { tip.style.right = 'auto'; tip.style.left = `${at + 12}px`; }
      tip.style.top = `${box.top - figBox.top + 8}px`;
    }
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
    drawTimeAxis(svg, from, to, x, W, 40, h - 8);
    drawMarkers(svg, markers, from, to, x, 8, 40, false);
    return fig;
  }

  // ---------------------------------------------------------------- timers and start
  setInterval(tick, 1000);   // ages tick locally; no polling
  // Slide the window: the drift rule redraws everything only once the axis moved a pixel.
  setInterval(() => { if (S.running && following()) { trimHistory(); renderHistory(new Set(), 0); } }, SLIDE_S * 1000);
  let resizeTimer = null;
  window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => renderHistory(), 250); });

  S.token = getItem('session', TOKEN_KEY);
  if (S.token) start(); else showLogin('');
})();
