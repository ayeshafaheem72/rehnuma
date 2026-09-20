/* Rehnuma - learner experience.
   Plain browser JS, no framework. Voice uses the Web Speech API, which is built into
   the browser: no server round-trip, so speaking stays instant. Text input is always
   available as a fallback, because speech recognition quality varies by browser and
   language and must never be the only way in. */

const $  = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

const S = {
  sourceId: null,
  learnerId: null,
  conceptMap: null,
  quotes: {},        // quote id -> verbatim text, for the citation chips
  cfg: null,
  busy: false,
  speak: false,
};

/* ------------------------------------------------------------ helpers */

function toast(msg, bad) {
  const t = el('div', 'toast' + (bad ? ' bad' : ''), msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), bad ? 6000 : 3200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body instanceof FormData ? {} : { 'Content-Type': 'application/json' },
    ...opts,
  });
  let data = null;
  try { data = await res.json(); } catch (_) { /* empty body */ }
  if (!res.ok) throw new Error((data && data.detail) || `Something went wrong (${res.status}).`);
  return data;
}

const isUrdu = () => S.cfg && (S.cfg.language === 'ur' || S.cfg.language === 'mixed');

function applyDirection(node, text) {
  // Urdu script present -> render right-to-left with the Nastaliq face
  if (/[؀-ۿ]/.test(text)) {
    node.classList.add('rtl', 'urdu');
    node.setAttribute('dir', 'rtl');
    node.setAttribute('lang', 'ur');
  }
}

/* --------------------------------------------------------- logo slot */

(function loadLogo() {
  const img = $('ublLogo'), fb = $('ublFallback');
  if (!img) return;
  img.addEventListener('load', () => { img.hidden = false; fb.hidden = true; });
  img.addEventListener('error', () => { img.remove(); });
})();

/* ------------------------------------------------------------- setup */

$('tabFile').addEventListener('click', () => switchTab('file'));
$('tabText').addEventListener('click', () => switchTab('text'));

function switchTab(which) {
  const f = which === 'file';
  $('tabFile').setAttribute('aria-selected', String(f));
  $('tabText').setAttribute('aria-selected', String(!f));
  $('paneFile').hidden = !f;
  $('paneText').hidden = f;
}

$('sampleBtn').addEventListener('click', () => {
  $('titleInput').value = 'How a Savings Account Actually Works';
  $('textInput').value = SAMPLE;
  toast('Sample loaded - press Build my experience.');
});

$('buildBtn').addEventListener('click', build);

async function build() {
  if (S.busy) return;
  const file = $('fileInput').files[0];
  const pasted = $('textInput').value.trim();
  const usingFile = $('tabFile').getAttribute('aria-selected') === 'true';

  if (usingFile && !file)   return toast('Choose a file first.', true);
  if (!usingFile && !pasted) return toast('Paste some content first.', true);

  S.busy = true;
  $('buildBtn').disabled = true;
  $('buildNote').textContent = 'Reading your material and mapping the ideas inside it...';

  try {
    let out;
    if (usingFile) {
      const fd = new FormData();
      fd.append('file', file);
      out = await api('/api/source/upload', { method: 'POST', body: fd });
    } else {
      out = await api('/api/source/paste', {
        method: 'POST',
        body: JSON.stringify({ title: $('titleInput').value, text: pasted }),
      });
    }
    S.sourceId = out.source_id;
    S.conceptMap = out.concept_map;
    showMap(out);
    $('buildNote').textContent = `Ready in ${(out.latency_ms / 1000).toFixed(1)}s.`;
  } catch (e) {
    toast(e.message, true);
    $('buildNote').textContent = '';
  } finally {
    S.busy = false;
    $('buildBtn').disabled = false;
  }
}

function showMap(out) {
  const list = $('mapList');
  list.textContent = '';
  const head = el('p', 'small muted');
  head.textContent = `${out.concept_map.concepts.length} concepts found in "${out.title}"`
    + (out.truncated ? ' (long document - used the opening section)' : '');
  list.appendChild(head);

  out.concept_map.concepts.forEach((c, i) => {
    const row = el('div', 'row');
    const dot = el('div', 'medallion');
    dot.style.width = dot.style.height = '38px';
    const inner = el('div', 'inner', String(i + 1));
    inner.style.width = inner.style.height = '24px';
    inner.style.fontSize = '12px';
    dot.appendChild(inner);
    const txt = el('div');
    txt.appendChild(el('div', 'stop-title', c.title));
    txt.appendChild(el('div', 'small muted', c.summary));
    row.append(dot, txt);
    list.appendChild(row);
  });

  $('mapPreview').hidden = false;
  $('mapPreview').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

$('startBtn').addEventListener('click', start);

async function start() {
  if (S.busy) return;
  S.busy = true;
  $('startBtn').disabled = true;
  $('startBtn').textContent = 'Setting the scene...';
  try {
    const out = await api('/api/session/start', {
      method: 'POST',
      body: JSON.stringify({ source_id: S.sourceId, label: $('labelInput').value || 'Learner' }),
    });
    S.learnerId = out.learner_id;
    S.conceptMap = out.concept_map;
    S.conceptMap.concepts.forEach(c => c.quotes.forEach(q => { S.quotes[q.id] = q.text; }));
    S.cfg = await api('/api/config').then(r => r.config);

    $('setupView').classList.add('hidden');
    $('learnView').classList.remove('hidden');
    $('stats').hidden = false;
    $('sourceTitle').textContent = S.conceptMap.title || 'Your journey';

    renderTurn(out);
  } catch (e) {
    toast(e.message, true);
  } finally {
    S.busy = false;
    $('startBtn').disabled = false;
    $('startBtn').textContent = 'Start learning';
  }
}

/* ------------------------------------------------------------- board */

function renderBoard(state) {
  const board = $('board');
  board.textContent = '';
  const concepts = S.conceptMap.concepts;
  const current = state._currentConcept;

  concepts.forEach((c, i) => {
    const cs = state.concepts[c.id] || { mastery: 0, unlocked: false };
    const mastered = cs.mastery >= (S.cfg ? S.cfg.mastery_mastered_at : 0.85);
    let cls = 'stop ';
    if (!cs.unlocked) cls += 'locked';
    else if (mastered) cls += 'mastered';
    else cls += 'active';
    if (c.id === current) cls += ' current';

    const stop = el('div', cls);
    stop.setAttribute('title', c.summary);

    const med = el('div', 'medallion');
    med.appendChild(el('div', 'inner', mastered ? '★' : String(i + 1)));
    const label = el('div', 'stop-label');
    label.appendChild(el('div', 'stop-title', c.title));
    const bar = el('div', 'mastery-bar');
    const fill = el('span');
    fill.style.width = Math.round(cs.mastery * 100) + '%';
    bar.appendChild(fill);
    label.appendChild(bar);

    stop.append(med, label);
    board.appendChild(stop);
  });
}

function renderStats(summary) {
  $('statXp').textContent = summary.xp;
  $('statStreak').textContent = summary.streak;
  $('statMastery').textContent = Math.round(summary.overall_mastery * 100) + '%';
  $('statLang').textContent = (S.cfg ? S.cfg.language : 'en').toUpperCase();
  $('xpBar').style.width = Math.min(100, (summary.xp % 200) / 2) + '%';

  const box = $('badges');
  if (summary.badges.length) {
    box.textContent = '';
    summary.badges.forEach(b => box.appendChild(el('span', 'badge', b.replace(/_/g, ' '))));
  }
}

/* ------------------------------------------------------ conversation */

function addBubble(who, text, cls) {
  const b = el('div', `bubble ${who}`);
  b.appendChild(el('div', 'who', cls || (who === 'guide' ? 'Rehnuma' : 'You')));
  const say = el('div', 'say');
  say.textContent = text;
  applyDirection(say, text);
  b.appendChild(say);
  $('stream').appendChild(b);
  return b;
}

function renderTurn(out) {
  const b = addBubble('guide', '');
  const say = b.querySelector('.say');

  // mechanic pill
  const pill = el('span', `mechanic ${out.interaction_type}`, out.interaction_type.replace('_', ' '));
  say.textContent = '';
  say.appendChild(pill);
  const body = el('div');
  body.textContent = out.message;
  applyDirection(say, out.message);
  say.appendChild(body);

  // off-source flag
  if (out.off_source) {
    say.appendChild(el('div', 'flag-off',
      'Heads up: that goes beyond the uploaded material. Rehnuma will not invent an answer.'));
  }

  // citations
  if (out.citations && out.citations.length) {
    const wrap = el('div', 'cites');
    out.citations.forEach(c => {
      const chip = el('button', 'cite', 'source ' + c.quote_id);
      chip.type = 'button';
      chip.title = c.claim;
      chip.addEventListener('click', () => {
        const existing = say.querySelector('.quote-pop[data-q="' + c.quote_id + '"]');
        if (existing) return existing.remove();
        const q = el('div', 'quote-pop', '"' + (S.quotes[c.quote_id] || 'quote unavailable') + '"');
        q.dataset.q = c.quote_id;
        say.appendChild(q);
      });
      wrap.appendChild(chip);
    });
    say.appendChild(wrap);
  }

  // choices
  if (out.choices && out.choices.length) {
    const wrap = el('div', 'choices');
    out.choices.forEach((c, i) => {
      const btn = el('button', 'choice');
      btn.type = 'button';
      btn.appendChild(el('span', 'key', String.fromCharCode(65 + i)));
      btn.appendChild(el('span', null, c.text));
      btn.addEventListener('click', () => {
        wrap.querySelectorAll('.choice').forEach(x => { x.disabled = true; });
        send(c.text);
      });
      wrap.appendChild(btn);
    });
    say.appendChild(wrap);
  }

  if (out.newly_unlocked && out.newly_unlocked.length) {
    const names = out.newly_unlocked
      .map(id => (S.conceptMap.concepts.find(c => c.id === id) || {}).title)
      .filter(Boolean);
    if (names.length) toast('Unlocked: ' + names.join(', '));
  }

  out.state._currentConcept = out.concept_id;
  renderBoard(out.state);
  renderStats(out.summary);
  if (out.latency_ms) $('latencyNote').textContent = (out.latency_ms / 1000).toFixed(1) + 's';

  $('stream').scrollTop = $('stream').scrollHeight;
  if (S.speak) speak(out.message);
}

/* ----------------------------------------------------------- sending */

$('sendBtn').addEventListener('click', () => send($('sayBox').value));
$('sayBox').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send($('sayBox').value); }
});

async function send(message) {
  message = (message || '').trim();
  if (!message || S.busy) return;
  S.busy = true;
  $('sendBtn').disabled = true;
  $('sayBox').value = '';
  addBubble('learner', message);

  const wait = el('div', 'bubble guide');
  const dots = el('div', 'thinking');
  dots.append(el('i'), el('i'), el('i'));
  wait.appendChild(dots);
  $('stream').appendChild(wait);
  $('stream').scrollTop = $('stream').scrollHeight;

  try {
    const out = await api(`/api/session/${S.learnerId}/turn`, {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
    wait.remove();
    S.cfg = await api('/api/config').then(r => r.config);   // pick up live config changes
    renderTurn(out);
  } catch (e) {
    wait.remove();
    addBubble('system', e.message);
    toast(e.message, true);
  } finally {
    S.busy = false;
    $('sendBtn').disabled = false;
  }
}

/* ------------------------------------------------------------- voice */

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recog = null, listening = false;

function voiceLang() {
  if (!S.cfg) return 'en-US';
  return S.cfg.language === 'ur' ? 'ur-PK' : 'en-US';
}

if (!SR) {
  $('micBtn').disabled = true;
  $('micBtn').title = 'Speech input is not supported in this browser - type instead.';
} else {
  $('micBtn').addEventListener('click', () => {
    if (listening) { recog && recog.stop(); return; }
    recog = new SR();
    recog.lang = voiceLang();
    recog.interimResults = true;
    recog.continuous = false;

    recog.onstart = () => { listening = true; $('micBtn').classList.add('listening'); };
    recog.onend   = () => { listening = false; $('micBtn').classList.remove('listening'); };
    recog.onerror = (e) => {
      listening = false;
      $('micBtn').classList.remove('listening');
      toast(e.error === 'not-allowed'
        ? 'Microphone permission was declined - you can type instead.'
        : 'Speech input did not catch that - try again, or type it.', true);
    };
    recog.onresult = (e) => {
      let text = '';
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      $('sayBox').value = text;
      if (e.results[e.results.length - 1].isFinal) send(text);
    };
    try { recog.start(); } catch (_) { /* already running */ }
  });
}

$('speakToggle').addEventListener('click', () => {
  S.speak = !S.speak;
  $('speakToggle').setAttribute('aria-pressed', String(S.speak));
  $('speakToggle').textContent = S.speak ? '🔊 Voice on' : '🔈 Voice off';
  if (!S.speak) window.speechSynthesis && window.speechSynthesis.cancel();
});

function speak(text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = voiceLang();
  const want = u.lang.split('-')[0];
  const voice = window.speechSynthesis.getVoices().find(v => v.lang.startsWith(want));
  if (voice) u.voice = voice;
  u.rate = 0.98;
  window.speechSynthesis.speak(u);
}

/* ------------------------------------------------------------ sample */

const SAMPLE = `A savings account is a deposit account held at a bank that pays interest on the
money you keep in it. Unlike a current account, which is built for frequent transactions, a
savings account rewards you for leaving money untouched.

Interest is the price a bank pays you for the use of your money. It is usually quoted as an
annual percentage rate. If you keep PKR 100,000 in an account paying 8% per year, the bank
pays you PKR 8,000 over twelve months, assuming the rate does not change.

Compounding is what makes saving powerful over time. When interest is added to your balance,
the next round of interest is calculated on the larger amount. Interest that compounds monthly
will grow faster than interest paid once a year, even at the same quoted rate.

Minimum balance requirements are a common condition. Many savings accounts require the holder
to keep a stated amount in the account. If the balance falls below that figure, the bank may
reduce the interest paid or charge a maintenance fee.

Liquidity describes how quickly an asset can be turned into cash without losing value. A
savings account is highly liquid: the money can be withdrawn on demand. A term deposit pays a
higher rate but locks the money away for a fixed period, trading liquidity for return.

Inflation is the rate at which prices rise. If an account pays 8% interest while inflation runs
at 10%, the real return is negative: the money grows in number but buys less than before. Savers
should compare the interest rate against inflation, not against zero.`;
