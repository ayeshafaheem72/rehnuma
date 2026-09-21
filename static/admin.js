/* Rehnuma - control room.
   Analytics, the evidence feed, live configuration and observability.

   Chart colours are the truck-art hues re-stepped for a dark plotting surface and
   validated for colourblind separation, lightness band and contrast. Bars carry
   direct value labels so identity never rests on colour alone. */

const $  = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

/* validated categorical order - do not cycle, do not reorder */
const CAT = ['#E6006E', '#0090B0', '#BD8400', '#009469', '#F03A22'];
const INK_TEXT  = '#F2E9D8';
const INK_MUTED = '#A99A7C';
const GRID      = 'rgba(169,154,124,.18)';

const charts = {};
let DATA = null;
const FILTERS = { learner: '', concept: '', signal: '', since: '' };

function toast(msg, bad) {
  const t = el('div', 'toast' + (bad ? ' bad' : ''), msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), bad ? 6000 : 3000);
}

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  let data = null;
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status}).`);
  return data;
}

/* --------------------------------------------------------------- logo */

(function loadLogo() {
  const img = $('ublLogo'), fb = $('ublFallback');
  if (!img) return;
  img.addEventListener('load', () => { img.hidden = false; fb.hidden = true; });
  img.addEventListener('error', () => { img.remove(); });
})();

/* ------------------------------------------------------------ sign in */

$('signIn').addEventListener('click', signIn);
$('pw').addEventListener('keydown', (e) => { if (e.key === 'Enter') signIn(); });

async function signIn() {
  try {
    await api('/api/admin/login', {
      method: 'POST',
      body: JSON.stringify({ password: $('pw').value }),
    });
    enterAdmin();
  } catch (e) { toast(e.message, true); }
}

$('signOut').addEventListener('click', async () => {
  await api('/api/admin/logout', { method: 'POST' });
  location.reload();
});

function enterAdmin() {
  $('loginView').classList.add('hidden');
  $('adminView').classList.remove('hidden');
  $('signOut').hidden = false;
  load();
}

/* checks an existing cookie so a signed-in admin skips the form on reload */
(async function boot() {
  try {
    const cfg = await api('/api/config');
    if (cfg.is_admin) enterAdmin();
  } catch (_) {}
})();

$('refreshBtn').addEventListener('click', load);

/* --------------------------------------------------------------- load */

function filterQuery() {
  const q = new URLSearchParams();
  Object.entries(FILTERS).forEach(([k, v]) => { if (v) q.set(k, v); });
  const s = q.toString();
  return s ? '?' + s : '';
}

async function load() {
  try {
    DATA = await api('/api/dashboard' + filterQuery());
    renderFilters(DATA.filters);
    const health = await api('/health');
    renderTiles(DATA, health);
    renderCharts(DATA);
    renderEvidence(DATA);
    renderLearners(DATA);
    renderConfig(await api('/api/config'));
    renderEvents(await api('/api/events'));
    $('healthNote').textContent =
      `${health.status} · up ${Math.round(health.uptime_s)}s · ${health.model}`
      + (health.api_key_present ? '' : ' · NO API KEY');
  } catch (e) { toast(e.message, true); }
}

/* ------------------------------------------------------------ filters */

function fillSelect(id, key, options, allLabel) {
  const sel = $(id);
  if (!sel) return;
  sel.textContent = '';
  const blank = el('option', null, allLabel);
  blank.value = '';
  sel.appendChild(blank);
  options.forEach(([value, label]) => {
    const o = el('option', null, label);
    o.value = value;
    if (FILTERS[key] === value) o.selected = true;
    sel.appendChild(o);
  });
  sel.onchange = () => { FILTERS[key] = sel.value; load(); };
  const wrap = sel.closest('.filter');
  if (wrap) wrap.classList.toggle('active', !!FILTERS[key]);
}

function renderFilters(f) {
  if (!f) return;
  fillSelect('fLearner', 'learner', f.learners.map(l => [l.id, l.label]), 'All learners');
  fillSelect('fConcept', 'concept', f.concepts.map(([id, c]) => [id, `${id} — ${c.title}`]),
             'All concepts');
  fillSelect('fSignal', 'signal', f.signals.map(n => [n, n.replace(/_/g, ' ')]), 'All signals');
  fillSelect('fSince', 'since', f.windows.filter(w => w[0]), 'All time');

  const on = Object.entries(FILTERS).filter(([, v]) => v);
  $('filterNote').textContent = on.length
    ? `${on.length} filter${on.length > 1 ? 's' : ''} applied — every view below is narrowed`
    : 'Showing everything';
  $('csvBtn').href = '/api/report.csv' + (FILTERS.learner ? '?learner=' + FILTERS.learner : '');
}

$('fClear').addEventListener('click', () => {
  Object.keys(FILTERS).forEach(k => { FILTERS[k] = ''; });
  load();
});

/* -------------------------------------------------------------- tiles */

function renderTiles(d, health) {
  const box = $('tiles');
  box.textContent = '';
  const tiles = [
    ['a', d.totals.learners,        'Learners'],
    ['b', d.totals.turns,           'Guide turns'],
    ['c', d.totals.sources,         'Sources'],
    ['d', d.latency.p50 + 'ms',     'Latency p50'],
    ['a', d.latency.p95 + 'ms',     'Latency p95'],
    ['b', (d.totals.tokens_in + d.totals.tokens_out).toLocaleString(), 'Tokens used'],
  ];
  tiles.forEach(([cls, n, k]) => {
    const t = el('div', 'tile ' + cls);
    t.appendChild(el('div', 'n', String(n)));
    t.appendChild(el('div', 'k', k));
    box.appendChild(t);
  });
}

/* ------------------------------------------------------------- charts */

const baseOpts = (horizontal) => ({
  indexAxis: horizontal ? 'y' : 'x',
  responsive: true,
  maintainAspectRatio: false,
  layout: { padding: { right: 22, top: 6 } },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: '#10131A',
      titleColor: INK_TEXT,
      bodyColor: INK_TEXT,
      borderColor: INK_MUTED,
      borderWidth: 1,
      padding: 9,
      displayColors: true,
    },
  },
  scales: {
    x: {
      grid: { color: GRID, drawTicks: false },
      border: { display: false },
      ticks: { color: INK_MUTED, font: { size: 10 } },
    },
    y: {
      grid: { display: false },
      border: { display: false },
      ticks: { color: INK_TEXT, font: { size: 11 } },
    },
  },
});

/* draws the value at the end of each bar, so a reader never decodes by colour */
const endLabels = {
  id: 'endLabels',
  afterDatasetsDraw(chart, _a, opts) {
    const { ctx } = chart;
    ctx.save();
    ctx.fillStyle = INK_TEXT;
    ctx.font = '700 11px "JetBrains Mono", monospace';
    chart.data.datasets.forEach((ds, di) => {
      chart.getDatasetMeta(di).data.forEach((bar, i) => {
        const v = ds.data[i];
        if (v === 0 || v === null || v === undefined) return;
        const txt = (opts && opts.suffix) ? Math.round(v * 100) + '%' : String(v);
        if (chart.options.indexAxis === 'y') {
          ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
          ctx.fillText(txt, bar.x + 7, bar.y);
        } else {
          ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
          ctx.fillText(txt, bar.x, bar.y - 5);
        }
      });
    });
    ctx.restore();
  },
};

function draw(key, canvasId, cfg) {
  if (charts[key]) charts[key].destroy();
  charts[key] = new Chart($(canvasId), cfg);
}

function renderCharts(d) {
  /* 1. Mastery by learner - magnitude, one hue, single series so no legend */
  const ml = d.learners.slice(0, 10);
  draw('mastery', 'chartMastery', {
    type: 'bar',
    data: {
      labels: ml.map(l => l.label),
      datasets: [{
        label: 'Mastery',
        data: ml.map(l => l.overall_mastery),
        backgroundColor: CAT[3],
        borderRadius: 4,
        borderSkipped: 'start',
        barThickness: 18,
      }],
    },
    options: {
      ...baseOpts(true),
      scales: {
        ...baseOpts(true).scales,
        x: { ...baseOpts(true).scales.x, min: 0, max: 1,
             ticks: { color: INK_MUTED, font: { size: 10 },
                      callback: v => Math.round(v * 100) + '%' } },
      },
      plugins: { ...baseOpts(true).plugins, endLabels: { suffix: true } },
    },
    plugins: [endLabels],
  });

  /* 2. Understanding signals - magnitude, one hue */
  const sig = Object.entries(d.signal_counts).sort((a, b) => b[1] - a[1]);
  draw('signals', 'chartSignals', {
    type: 'bar',
    data: {
      labels: sig.map(([k]) => k.replace(/_/g, ' ')),
      datasets: [{
        label: 'Detected',
        data: sig.map(([, v]) => v),
        backgroundColor: CAT[1],
        borderRadius: 4,
        borderSkipped: 'start',
        barThickness: 18,
      }],
    },
    options: {
      ...baseOpts(true),
      scales: { ...baseOpts(true).scales,
                x: { ...baseOpts(true).scales.x, ticks: { color: INK_MUTED, precision: 0 } } },
    },
    plugins: [endLabels],
  });

  /* 3. Interaction mix - categorical identity, fixed hue order, legend + labels */
  const mix = Object.entries(d.interaction_counts);
  draw('mix', 'chartMix', {
    type: 'bar',
    data: {
      labels: mix.map(([k]) => k.replace(/_/g, ' ')),
      datasets: [{
        label: 'Turns',
        data: mix.map(([, v]) => v),
        backgroundColor: mix.map((_, i) => CAT[i % CAT.length]),
        borderRadius: 4,
        borderSkipped: 'start',
        barThickness: 28,
      }],
    },
    options: {
      ...baseOpts(false),
      scales: { ...baseOpts(false).scales,
                y: { grid: { color: GRID, drawTicks: false }, border: { display: false },
                     ticks: { color: INK_MUTED, precision: 0, font: { size: 10 } } },
                x: { grid: { display: false }, border: { display: false },
                     ticks: { color: INK_TEXT, font: { size: 11 } } } },
    },
    plugins: [endLabels],
  });
}

/* ------------------------------------------------------- evidence feed */

function renderEvidence(d) {
  const box = $('evidence');
  box.textContent = '';
  if (!d.evidence.length) {
    box.appendChild(el('p', 'small muted',
      'No evidence yet. Run a learning session and the signals behind every mastery '
      + 'change will appear here, each with the learner words that triggered it.'));
    return;
  }
  d.evidence.forEach(e => {
    const row = el('div', 'ev');
    row.appendChild(el('div', 'sig', e.signal.replace(/_/g, ' ')));
    if (e.evidence) row.appendChild(el('div', 'quote', '"' + e.evidence + '"'));
    row.appendChild(el('div', 'meta',
      `${e.learner} · ${e.concept_id} · ${new Date(e.at * 1000).toLocaleTimeString()}`));
    box.appendChild(row);
  });
}

/* ------------------------------------------------------------ learners */

function table(node, cols, rows, rowFn) {
  node.textContent = '';
  const thead = el('thead'), tr = el('tr');
  cols.forEach(c => tr.appendChild(el('th', null, c)));
  thead.appendChild(tr);
  const tbody = el('tbody');
  rows.forEach(r => tbody.appendChild(rowFn(r)));
  node.append(thead, tbody);
}

function renderLearners(d) {
  if (!d.learners.length) {
    $('learnerTable').textContent = '';
    $('learnerTable').appendChild(el('caption', 'small muted',
      'No learners yet - start a session from the learner view.'));
    return;
  }
  table($('learnerTable'),
    ['Learner', 'Turns', 'XP', 'Streak', 'Mastery', 'Mastered', 'Badges', ''],
    d.learners,
    (l) => {
      const tr = el('tr');
      tr.appendChild(el('td', null, l.label));
      tr.appendChild(el('td', 'num', String(l.turns)));
      tr.appendChild(el('td', 'num', String(l.xp)));
      tr.appendChild(el('td', 'num', String(l.streak)));
      tr.appendChild(el('td', 'num', Math.round(l.overall_mastery * 100) + '%'));
      tr.appendChild(el('td', 'num', `${l.mastered}/${l.total}`));
      tr.appendChild(el('td', 'num', String(l.badges)));
      const td = el('td');
      const b = el('button', 'btn sm blue', 'Report');
      b.type = 'button';
      b.addEventListener('click', () => showReport(l.learner_id));
      td.appendChild(b);
      tr.appendChild(td);
      return tr;
    });
}

async function showReport(id) {
  try {
    const r = await api('/api/report/' + id);
    $('reportPanel').hidden = false;
    $('reportTitle').textContent = `Outcome report — ${r.learner}`;
    table($('reportTable'),
      ['Concept', 'Before', 'Now', 'Gain', 'Exposures', 'Errors', 'Self-corrections', 'Hints', 'Status'],
      r.rows,
      (row) => {
        const tr = el('tr');
        tr.appendChild(el('td', null, row.concept));
        tr.appendChild(el('td', 'num', Math.round(row.baseline * 100) + '%'));
        tr.appendChild(el('td', 'num', Math.round(row.current * 100) + '%'));
        tr.appendChild(el('td', 'num', (row.gain >= 0 ? '+' : '') + Math.round(row.gain * 100) + '%'));
        tr.appendChild(el('td', 'num', String(row.exposures)));
        tr.appendChild(el('td', 'num', String(row.errors)));
        tr.appendChild(el('td', 'num', String(row.self_corrections)));
        tr.appendChild(el('td', 'num', String(row.hints_used)));
        const st = el('td');
        st.appendChild(el('span', 'pill ' + (row.status === 'mastered' ? 'mastered'
          : row.status === 'locked' ? 'locked' : 'progress'), row.status));
        tr.appendChild(st);
        return tr;
      });
    $('reportPanel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) { toast(e.message, true); }
}

$('closeReport').addEventListener('click', () => { $('reportPanel').hidden = true; });

/* -------------------------------------------------------------- config */

let CONFIG_SCHEMA = [];

/* what each free-text setting is for, shown until something is typed */
const TEXT_HINTS = {
  learner_profile: 'e.g. a first-time saver in their twenties, no banking background',
  constraints: 'e.g. five minutes, on a phone, in a noisy place',
  custom_rules: 'e.g. Always finish with one practical thing to try today. Never use jargon.',
};

function renderConfig(payload) {
  CONFIG_SCHEMA = payload.schema;
  const cfg = payload.config;
  const box = $('configFields');
  box.textContent = '';

  payload.schema.forEach(f => {
    const wrap = el('div', 'field');
    const lab = el('label', null, f.label);
    lab.setAttribute('for', 'cfg_' + f.key);
    wrap.appendChild(lab);

    let input;
    if (f.kind === 'select') {
      input = el('select');
      f.options.forEach(o => {
        const opt = el('option', null, o);
        opt.value = o;
        if (cfg[f.key] === o) opt.selected = true;
        input.appendChild(opt);
      });
    } else if (f.kind === 'bool') {
      input = el('select');
      [['true', 'On'], ['false', 'Off']].forEach(([v, t]) => {
        const opt = el('option', null, t);
        opt.value = v;
        if (String(!!cfg[f.key]) === v) opt.selected = true;
        input.appendChild(opt);
      });
    } else if (f.kind === 'text') {
      // free-text settings: who is learning, the operating constraint, extra rules
      input = el('textarea');
      input.rows = f.options > 200 ? 3 : 2;
      input.maxLength = f.options;
      input.value = cfg[f.key] || '';
      input.placeholder = TEXT_HINTS[f.key] || '';
      wrap.classList.add('wide');
    } else {
      input = el('input');
      input.type = 'number';
      const [min, max, step] = f.options || [0, 100, 1];
      input.min = min; input.max = max; input.step = step;
      input.value = cfg[f.key];
    }
    input.id = 'cfg_' + f.key;
    input.dataset.key = f.key;
    input.dataset.kind = f.kind;
    wrap.appendChild(input);
    box.appendChild(wrap);
  });

  const mech = $('mechanicsRow');
  mech.textContent = '';
  Object.entries(cfg.mechanics).forEach(([k, v]) => {
    const lab = el('label', 'row small');
    lab.style.gap = '6px';
    const cb = el('input');
    cb.type = 'checkbox';
    cb.checked = v;
    cb.id = 'mech_' + k;
    cb.dataset.mech = k;
    cb.style.width = 'auto';
    lab.setAttribute('for', cb.id);
    lab.append(cb, document.createTextNode(k.replace(/_/g, ' ')));
    mech.appendChild(lab);
  });
}

$('saveConfig').addEventListener('click', async () => {
  const patch = { mechanics: {} };
  $('configFields').querySelectorAll('[data-key]').forEach(inp => {
    const k = inp.dataset.key;
    if (inp.dataset.kind === 'bool')        patch[k] = inp.value === 'true';
    else if (inp.dataset.kind === 'number') patch[k] = Number(inp.value);
    else                                    patch[k] = inp.value;   // select and text
  });
  $('mechanicsRow').querySelectorAll('[data-mech]').forEach(cb => {
    patch.mechanics[cb.dataset.mech] = cb.checked;
  });
  try {
    await api('/api/config', { method: 'POST', body: JSON.stringify(patch) });
    toast('Saved. The next turn will use these settings.');
    load();
  } catch (e) { toast(e.message, true); }
});

$('resetConfig').addEventListener('click', async () => {
  try {
    await api('/api/config/reset', { method: 'POST' });
    toast('Reset to defaults.');
    load();
  } catch (e) { toast(e.message, true); }
});

/* -------------------------------------------------------------- events */

function renderEvents(payload) {
  const rows = payload.events;
  if (!rows.length) {
    $('eventTable').textContent = '';
    return;
  }
  table($('eventTable'), ['When', 'Level', 'Event', 'Detail'], rows, (e) => {
    const tr = el('tr');
    tr.appendChild(el('td', 'num', new Date(e.created_at * 1000).toLocaleTimeString()));
    const lv = el('td');
    lv.appendChild(el('span', 'pill ' + (e.level === 'error' ? 'error'
      : e.level === 'warn' ? 'warn' : 'info'), e.level));
    tr.appendChild(lv);
    tr.appendChild(el('td', null, e.message));
    tr.appendChild(el('td', 'small muted', e.meta ? JSON.stringify(e.meta).slice(0, 120) : ''));
    return tr;
  });
}
