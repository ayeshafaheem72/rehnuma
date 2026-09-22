/* Rehnuma - learner experience.
   Plain browser JS, no framework. Voice uses the Web Speech API, which is built into the
   browser: no server round-trip, so speaking stays instant. Text input is always available
   as a fallback, because speech recognition and voices vary by browser, device and language
   and must never be the only way in. */
'use strict';

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
  quotes: {},         // quote id -> verbatim text, for the citation chips
  cfg: null,          // the public settings
  eff: null,          // what this learner is actually taught under (admin defaults + their own choices)
  busy: false,
  speak: false,
  talk: false,        // hands-free: the guide speaks, then listens
  mode: 'challenge',  // story | challenge | tour | deep - chosen on the setup screen
  story: null,
  storyCtl: null,
  opening: null,      // the first beat, fetched while the story plays
  openingP: null,
  touched: {},        // setup choices the learner made themselves - only these are sent, so
                      // an admin's later change to a default is never overruled by a stale copy
  lastAdapt: null,
};

const LANG_NAME = { en: 'English', ur: 'Urdu', mixed: 'English and Urdu', roman: 'Roman Urdu' };

/* ------------------------------------------------------------ helpers */

function toast(msg, bad) {
  const t = el('div', 'toast' + (bad ? ' bad' : ''), msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), bad ? 6500 : 3400);
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

const isUrdu = () => S.eff && (S.eff.language === 'ur' || S.eff.language === 'mixed');
/* Roman Urdu is spoken Urdu written in Latin letters: the learner may still talk to the microphone in Urdu */
const speaksUrdu = () => S.eff && ['ur', 'mixed', 'roman'].includes(S.eff.language);
const hasArabicScript = (t) => /[؀-ۿ]/.test(t || '');

/* Read the preference live rather than once at load: a learner may change it mid-demo,
   and every motion path below is expected to answer to it immediately. */
const REDUCED = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
const calmMotion = () => !!(REDUCED && REDUCED.matches);

/* Follows the foot of the stream while a reply grows. A distance test is no good
   here: the text itself pushes the foot away, so the only reliable signal that the
   learner has scrolled up to re-read is the position moving when we did not move it. */
function bottomPin(stream) {
  let on = true, wrote = -1;
  return () => {
    if (!stream || !on) return;
    if (wrote >= 0 && Math.abs(stream.scrollTop - wrote) > 8) { on = false; return; }
    stream.scrollTop = stream.scrollHeight;
    wrote = stream.scrollTop;
  };
}

function applyDirection(node, text) {
  // Urdu script present -> render right-to-left with the Nastaliq face
  if (hasArabicScript(text)) {
    node.classList.add('rtl', 'urdu');
    node.setAttribute('dir', 'rtl');
    node.setAttribute('lang', 'ur');
  }
}

/* A group of buttons that behaves as one radio group: arrow keys move the choice. */
function radioGroup(root, attr, onChange) {
  const btns = Array.from(root.querySelectorAll('[role="radio"]'));
  function set(value, silent) {
    let hit = false;
    btns.forEach(b => {
      const on = b.dataset[attr] === value;
      hit = hit || on;
      b.setAttribute('aria-checked', String(on));
      b.tabIndex = on ? 0 : -1;
    });
    if (!hit && btns[0]) btns[0].tabIndex = 0;
    if (!silent && onChange) onChange(value);
  }
  btns.forEach((b, i) => {
    b.addEventListener('click', () => set(b.dataset[attr]));
    b.addEventListener('keydown', (e) => {
      const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1
                 : e.key === 'ArrowLeft'  || e.key === 'ArrowUp'   ? -1 : 0;
      if (!step) return;
      e.preventDefault();
      const next = btns[(i + step + btns.length) % btns.length];
      set(next.dataset[attr]);
      next.focus();
    });
  });
  return { set, get: () => { const on = btns.find(b => b.getAttribute('aria-checked') === 'true'); return on ? on.dataset[attr] : ''; } };
}

/* --------------------------------------------------------- logo slot */

(function loadLogo() {
  const img = $('ublLogo'), fb = $('ublFallback');
  if (!img) return;
  img.addEventListener('load', () => { img.hidden = false; fb.hidden = true; });
  img.addEventListener('error', () => { img.remove(); });
})();

/* ------------------------------------------------------------- setup */

const TABS = ['File', 'Url', 'Text'];
TABS.forEach(t => $('tab' + t).addEventListener('click', () => switchTab(t)));
function switchTab(which) {
  TABS.forEach(t => {
    const on = t === which;
    $('tab' + t).setAttribute('aria-selected', String(on));
    $('pane' + t).hidden = !on;
  });
}
const activeTab = () => TABS.find(t => $('tab' + t).getAttribute('aria-selected') === 'true');

$('sampleBtn').addEventListener('click', () => {
  $('titleInput').value = 'How a Savings Account Actually Works';
  $('textInput').value = SAMPLE;
  toast('Sample loaded - press Build my experience.');
});

/* who is learning: language, level and any limit. Whatever the learner touches is sent with
   the session; whatever they leave alone stays on the admin's current defaults. */
const langPick = radioGroup($('langPick'), 'lang', (v) => { S.touched.language = v; warmStory(); });
$('levelPick').addEventListener('change', () => { S.touched.learner_level = $('levelPick').value; warmStory(); });
$('constraintInput').addEventListener('change', () => {
  const v = $('constraintInput').value.trim();
  if (v) S.touched.constraints = v; else delete S.touched.constraints;
  warmStory();
});
$('constraintInput').addEventListener('input', () => {
  const v = $('constraintInput').value.trim();
  if (v) S.touched.constraints = v; else delete S.touched.constraints;
});

/* The story takes as long to write as a reply does, and it starts as soon as the map exists.
   If the learner changes language, level or limit after that, start writing the right one now
   so it is waiting when they press Start rather than making them wait for it. */
let warmTimer = 0;
function warmStory() {
  if (!S.sourceId || S.learnerId) return;
  clearTimeout(warmTimer);
  warmTimer = setTimeout(() => {
    fetch(`/api/source/${S.sourceId}/prefetch`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(S.touched),
    }).catch(() => { /* an optimisation; start still works without it */ });
  }, 500);
}

async function loadDefaults() {
  try {
    const r = await api('/api/config');
    S.cfg = r.config;
    if (!S.touched.language) langPick.set(S.cfg.language, true);
    if (!S.touched.learner_level) $('levelPick').value = S.cfg.learner_level;
  } catch (_) { /* the page still works on the last settings it saw */ }
}
loadDefaults();
document.addEventListener('visibilitychange', () => { if (!document.hidden && !S.learnerId) loadDefaults(); });

$('buildBtn').addEventListener('click', build);

async function build() {
  if (S.busy) return;
  const tab = activeTab();
  const file = $('fileInput').files[0];
  const pasted = $('textInput').value.trim();
  const url = $('urlInput').value.trim();

  if (tab === 'File' && !file)   return toast('Choose a file first.', true);
  if (tab === 'Url'  && !url)    return toast('Paste a web address first.', true);
  if (tab === 'Text' && !pasted) return toast('Paste some content first.', true);

  S.busy = true;
  $('buildBtn').disabled = true;
  $('buildNote').textContent = 'Reading your material and mapping the ideas inside it...';

  try {
    let out;
    if (tab === 'File') {
      const fd = new FormData();
      fd.append('file', file);
      Object.entries(S.touched).forEach(([k, v]) => fd.append(k, v));
      out = await api('/api/source/upload', { method: 'POST', body: fd });
    } else if (tab === 'Url') {
      out = await api('/api/source/url', { method: 'POST', body: JSON.stringify(Object.assign({ url }, S.touched)) });
    } else {
      out = await api('/api/source/paste', {
        method: 'POST',
        body: JSON.stringify(Object.assign({ title: $('titleInput').value, text: pasted }, S.touched)),
      });
    }
    S.sourceId = out.source_id;
    S.conceptMap = out.concept_map;
    engineBanner(out.engine);
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

  // the proof that the map says only what the document says
  const g = out.grounding, note = $('groundNote');
  if (g && g.quotes_total) {
    const ok = g.verbatim + g.repaired;
    note.textContent = '';
    note.append(el('b', null, 'GROUNDED'),
      el('span', null, ` ${ok} of ${g.quotes_total} source quotes checked against your document`
        + (g.repaired ? ` (${g.repaired} corrected to the exact wording)` : '')
        + (g.dropped ? `; ${g.dropped} that could not be found were dropped` : '')
        + '. Every claim the guide makes points back to one of them.'));
    note.hidden = false;
  } else note.hidden = true;

  out.concept_map.concepts.forEach((c, i) => {
    const row = el('div', 'map-row');
    const dot = el('div', 'medallion');
    dot.style.width = dot.style.height = '38px';
    const inner = el('div', 'inner', String(i + 1));
    inner.style.width = inner.style.height = '24px';
    inner.style.fontSize = '12px';
    dot.appendChild(inner);
    const txt = el('div');
    const title = el('div', 'stop-title', c.title), summ = el('div', 'summary', c.summary);
    applyDirection(title, c.title); applyDirection(summ, c.summary);
    txt.appendChild(title);
    txt.appendChild(summ);
    row.append(dot, txt);
    list.appendChild(row);
  });

  $('startBtn').textContent = (S.cfg && S.cfg.story_intro === false) ? 'Start learning' : 'Start the story';
  $('mapPreview').hidden = false;
  $('mapPreview').scrollIntoView({ behavior: calmMotion() ? 'auto' : 'smooth', block: 'nearest' });
}

/* ------------------------------------------------------- learning mode */

/* The cards behave as one radio group: arrow keys move the choice, so the panel can
   be driven from the keyboard as well as the mouse. */
(function modePicker() {
  const group = $('modePick');
  if (!group) return;
  const cards = Array.from(group.querySelectorAll('.mode'));

  function choose(card, focus) {
    S.mode = card.dataset.mode;
    cards.forEach(c => {
      const on = c === card;
      c.setAttribute('aria-checked', String(on));
      c.classList.toggle('on', on);
      c.tabIndex = on ? 0 : -1;
    });
    if (focus) card.focus();
  }

  cards.forEach((card, i) => {
    card.addEventListener('click', () => choose(card));
    card.addEventListener('keydown', (e) => {
      const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1
                 : e.key === 'ArrowLeft'  || e.key === 'ArrowUp'   ? -1 : 0;
      if (!step) return;
      e.preventDefault();
      choose(cards[(i + step + cards.length) % cards.length], true);
    });
  });

  const initial = cards.find(c => c.dataset.mode === S.mode) || cards[0];
  if (initial) choose(initial);
})();

/* ------------------------------------------------------------- start */

$('startBtn').addEventListener('click', start);

async function start() {
  if (S.busy) return;
  S.busy = true;
  $('startBtn').disabled = true;
  await loadDefaults();                       // a default the admin changed a moment ago
  const wantStory = !!(S.cfg && S.cfg.story_intro);
  // The story may still be being written. These lines describe what is happening in that
  // time; they are not a progress bar, because nothing here can honestly report progress.
  const DRAWING = { story: 'Drawing the road...', challenge: 'Setting the field...', tour: 'Charting the route...', deep: 'Setting up the bench...' };
  const lines = wantStory
    ? ['Choosing who the story is about...', DRAWING[S.mode] || DRAWING.story, 'Writing the scenes...', 'Choosing the pictures...']
    : ['Setting the scene...'];
  let li = 0;
  $('startBtn').textContent = lines[0];
  const rotate = setInterval(() => { li = (li + 1) % lines.length; $('startBtn').textContent = lines[li]; }, 2600);
  try {
    const out = await api('/api/session/start', {
      method: 'POST',
      body: JSON.stringify(Object.assign({
        source_id: S.sourceId,
        label: $('labelInput').value || 'Learner',
        mode: S.mode,
        defer_opening: wantStory,
      }, S.touched)),
    });
    S.learnerId = out.learner_id;
    S.conceptMap = out.concept_map;
    S.conceptMap.concepts.forEach(c => c.quotes.forEach(q => { S.quotes[q.id] = q.text; }));
    S.eff = out.effective;
    S.story = out.story || null;
    S.mode = out.mode || S.mode;
    $('sourceTitle').textContent = S.conceptMap.title || 'Your journey';
    syncPrefs();

    if (S.story) playStory(false);
    else enterLearn(wantStory ? await fetchOpening() : out);
  } catch (e) {
    toast(e.message, true);
  } finally {
    clearInterval(rotate);
    S.busy = false;
    $('startBtn').disabled = false;
    $('startBtn').textContent = (S.cfg && S.cfg.story_intro === false) ? 'Start learning' : 'Start the story';
  }
}

const fetchOpening = () => api(`/api/session/${S.learnerId}/opening`, { method: 'POST' });

/* the state of the board before anything has been said */
function blankState() {
  const concepts = {};
  S.conceptMap.concepts.forEach(c => { concepts[c.id] = { mastery: 0, unlocked: !(c.prerequisites || []).length, exposures: 0 }; });
  return { concepts, _currentConcept: S.conceptMap.concepts[0] && S.conceptMap.concepts[0].id };
}

function enterLearn(out) {
  $('setupView').classList.add('hidden');
  $('storyView').classList.add('hidden');
  $('givingBack').classList.add('hidden');
  $('learnView').classList.remove('hidden');
  $('stats').hidden = false;
  $('replayStory').hidden = !S.story;
  window.scrollTo({ top: 0, behavior: 'auto' });
  if (out) { renderTurn(out); return; }
  renderBoard(blankState());
  addBubble('system', 'The guide could not open the first scene. Say hello and it will begin.');
}

/* ------------------------------------------------------------- story */

function postEvent(type, extra) {
  if (!S.learnerId) return;
  fetch(`/api/session/${S.learnerId}/event`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign({ type }, extra || {})),
  }).catch(() => { /* engagement is best-effort */ });
}

/* the story reads through the same voice as everything else */
const storyVoice = () => ({
  enabled: () => S.speak,
  toggle: () => { setSpeak(!S.speak); return S.speak; },
  speak: (text) => Voice.say(text),
  stop: () => Voice.stop(),
});

function playStory(replay) {
  $('setupView').classList.add('hidden');
  $('learnView').classList.add('hidden');
  $('givingBack').classList.add('hidden');
  $('stats').hidden = true;
  const mount = $('storyView');
  mount.classList.remove('hidden');
  window.scrollTo({ top: 0, behavior: 'auto' });

  if (!replay) {
    // the first beat is written while the story plays, so it is ready when the story ends
    S.opening = null;
    S.openingP = fetchOpening().then(o => { S.opening = o; }).catch(() => { S.opening = null; });
  }
  let reported = 0;
  S.storyCtl = RehnumaStory.play({
    mount, story: S.story, quotes: S.quotes, voice: storyVoice(), theme: S.mode,
    onProgress: (v) => { if (!replay && v > reported) { reported = v; postEvent('story_progress', { viewed: v }); } },
    onDone: () => afterStory(false, replay),
    onSkip: () => afterStory(true, replay),
  });
  if (S.storyCtl) {
    if (replay) S.storyCtl.setReady(true);
    else S.openingP.then(() => S.storyCtl && S.storyCtl.setReady(true));
  }
}

async function afterStory(skipped, replay) {
  Voice.stop();
  $('storyView').classList.add('hidden');
  if (replay) {
    $('learnView').classList.remove('hidden');
    $('stats').hidden = false;
    return;
  }
  postEvent(skipped ? 'story_skipped' : 'story_done');
  $('stats').hidden = false;
  if (!S.opening) {
    toast('Getting your first mission ready...');
    await S.openingP;
    if (!S.opening) { try { S.opening = await fetchOpening(); } catch (_) { S.opening = null; } }
  }
  enterLearn(S.opening);
}

$('replayStory').addEventListener('click', () => { if (S.story) playStory(true); });

/* ------------------------------------------------------------- board */

/* Which concepts were already mastered last time the board was drawn. The board is
   rebuilt from scratch each turn, so crossing the threshold can only be spotted by
   comparing against the previous draw - and never on the very first one, or a
   resumed session would celebrate work the learner did earlier. */
const MASTERED = new Set();
let boardDrawn = false;

function renderBoard(state) {
  const board = $('board');
  board.textContent = '';
  const concepts = S.conceptMap.concepts;
  const current = state._currentConcept;
  const justUnlocked = state._newly_unlocked || [];
  const masteredAt = S.cfg && S.cfg.mastery_mastered_at ? S.cfg.mastery_mastered_at : 0.85;

  concepts.forEach((c, i) => {
    const cs = state.concepts[c.id] || { mastery: 0, unlocked: false };
    const mastered = cs.mastery >= masteredAt;
    const justMastered = mastered && boardDrawn && !MASTERED.has(c.id);
    if (mastered) MASTERED.add(c.id); else MASTERED.delete(c.id);

    let cls = 'stop ';
    if (!cs.unlocked) cls += 'locked';
    else if (mastered) cls += 'mastered';
    else cls += 'active';
    if (c.id === current) cls += ' current';
    if (justUnlocked.includes(c.id)) cls += ' just-unlocked';
    if (justMastered) cls += ' just-mastered';

    const stop = el('div', cls);
    stop.setAttribute('title', c.summary);

    const med = el('div', 'medallion');
    med.appendChild(el('div', 'inner', mastered ? '★' : String(i + 1)));
    const label = el('div', 'stop-label');
    const t = el('div', 'stop-title', c.title);
    applyDirection(t, c.title);
    label.appendChild(t);
    const bar = el('div', 'mastery-bar');
    const fill = el('span');
    fill.style.width = Math.round(cs.mastery * 100) + '%';
    bar.appendChild(fill);
    label.appendChild(bar);

    stop.append(med, label);
    board.appendChild(stop);
  });

  boardDrawn = true;

  // keep the concept being taught in view as the journey moves down the board
  const active = board.querySelector('.stop.current');
  if (active && !calmMotion()) active.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

const LAST = {};
function bump(id, value) {
  const node = $(id);
  if (!node) return;
  const chip = node.closest('.stat');
  if (chip && LAST[id] !== undefined && LAST[id] !== value) {
    chip.classList.remove('bump');
    void chip.offsetWidth;            // restart the animation
    chip.classList.add('bump');
  }
  LAST[id] = value;
  node.textContent = value;
}

/* Float the gained XP off the chip it came from, so the reward is attached to the
   thing that changed rather than announced somewhere else on the page. */
function floatXp(gain) {
  if (calmMotion() || gain <= 0) return;
  const chip = $('statXp') && $('statXp').closest('.stat');
  if (!chip) return;
  const r = chip.getBoundingClientRect();
  const f = el('div', 'xp-float', '+' + gain);
  f.style.left = (r.left + r.width / 2) + 'px';
  // launched from under the chip: the bar sits at the top of the window, so a float
  // starting level with it would rise straight off the screen
  f.style.top  = (r.bottom + 2) + 'px';
  document.body.appendChild(f);
  f.addEventListener('animationend', () => f.remove());
  setTimeout(() => f.remove(), 1600);   // belt and braces if the animation never fires
}

const BADGE_LABEL = {
  first_steps: 'First steps', first_unlock: 'First unlock', on_a_roll: 'On a roll',
  own_words: 'Own words', mastered_one: 'Mastered one', boss_slayer: 'Boss slayer',
  curious: 'Curious', storyteller: 'Storyteller',
};

function renderStats(summary) {
  const hadXp = LAST.statXp;
  if (hadXp !== undefined && summary.xp > hadXp) floatXp(summary.xp - hadXp);
  bump('statXp', summary.xp);
  bump('statStreak', summary.streak);
  bump('statMastery', Math.round(summary.overall_mastery * 100) + '%');
  bump('statLang', (S.eff ? S.eff.language : 'en').toUpperCase());
  $('xpBar').style.width = Math.min(100, (summary.xp % 200) / 2) + '%';

  const box = $('badges');
  if (summary.badges.length) {
    box.textContent = '';
    summary.badges.forEach(b => box.appendChild(el('span', 'badge', BADGE_LABEL[b] || b.replace(/_/g, ' '))));
  }
}

/* --------------------------------------------- how it is adapting (measured) */

const SUPPORT = {
  high: 'Step by step, with a worked example first',
  normal: 'Explain, then ask',
  low: 'You lead, the guide steps back',
};

function renderAdaptation(ad) {
  if (!ad) return;
  const prev = S.lastAdapt || {};
  const set = (id, text, changed) => {
    const n = $(id);
    n.textContent = text;
    if (changed) { n.classList.remove('changed'); void n.offsetWidth; n.classList.add('changed'); }
  };
  const dots = el('span', 'dots5');
  for (let i = 1; i <= 5; i++) dots.appendChild(el('i', i <= ad.difficulty_target ? 'on' : ''));
  const diff = $('adDiff');
  diff.textContent = '';
  diff.append(dots);
  diff.setAttribute('aria-label', `Difficulty ${ad.difficulty_target} of 5`);
  if (prev.difficulty_target !== undefined && prev.difficulty_target !== ad.difficulty_target) {
    diff.classList.remove('changed'); void diff.offsetWidth; diff.classList.add('changed');
  }
  set('adSupport', SUPPORT[ad.scaffolding] || ad.scaffolding, prev.scaffolding !== undefined && prev.scaffolding !== ad.scaffolding);
  set('adPace', ad.pace.charAt(0).toUpperCase() + ad.pace.slice(1), prev.pace !== undefined && prev.pace !== ad.pace);
  set('adFocus', ad.focus_title || 'Everything open is mastered', prev.focus_concept !== undefined && prev.focus_concept !== ad.focus_concept);
  $('adFocus').className = 'v' + (hasArabicScript(ad.focus_title) ? ' urdu' : '');
  const why = $('adWhy');
  why.textContent = '';
  (ad.why || []).forEach(w => why.appendChild(el('li', null, w)));
  S.lastAdapt = ad;
}

/* ------------------------------------------------ the learner's own settings */

const prefLang = radioGroup($('prefLang'), 'lang', (v) => savePref({ language: v }));
$('prefLevel').addEventListener('change', () => savePref({ learner_level: $('prefLevel').value }));
$('prefPace').addEventListener('change', () => savePref({ pace: $('prefPace').value }));
$('prefTone').addEventListener('change', () => savePref({ tone: $('prefTone').value }));
$('prefConstraint').addEventListener('change', () => savePref({ constraints: $('prefConstraint').value.trim() }));

function syncPrefs() {
  const e = S.eff || {};
  prefLang.set(e.language || 'en', true);
  $('prefLevel').value = e.learner_level || 'beginner';
  $('prefPace').value = e.pace || 'normal';
  $('prefTone').value = e.tone || 'friendly';
  if (document.activeElement !== $('prefConstraint')) $('prefConstraint').value = e.constraints || '';
  if (S.eff) bump('statLang', S.eff.language.toUpperCase());
  // the microphone listens in the language the learner is being taught in
  if (!S.micChosen) micLang.set(speaksUrdu() ? 'ur-PK' : 'en-PK', true);
  document.documentElement.lang = e.language === 'ur' ? 'ur' : 'en';
}

async function savePref(patch) {
  if (!S.learnerId) return;
  try {
    const r = await api(`/api/session/${S.learnerId}/prefs`, { method: 'POST', body: JSON.stringify(patch) });
    S.eff = r.effective;
    syncPrefs();
    renderAdaptation(r.adaptation);
    toast(patch.language
      ? `Saved - the next reply will be in ${LANG_NAME[patch.language]}.`
      : 'Saved - the next reply will use this.');
  } catch (e) { toast(e.message, true); syncPrefs(); }
}

$('eraseBtn').addEventListener('click', async () => {
  if (!S.learnerId) return;
  if (!window.confirm('Delete this session and everything you said in it? This cannot be undone.')) return;
  try {
    await api(`/api/session/${S.learnerId}`, { method: 'DELETE' });
    location.reload();
  } catch (e) { toast(e.message, true); }
});

/* ------------------------------------------------------ conversation */

function addBubble(who, text, cls) {
  const b = el('div', `bubble ${who} enter`);
  b.appendChild(el('div', 'who', cls || (who === 'guide' ? 'Rehnuma' : who === 'system' ? 'Note' : 'You')));
  const say = el('div', 'say');
  say.textContent = text;
  applyDirection(say, text);
  b.appendChild(say);
  $('stream').appendChild(b);
  return b;
}

/* Split into small word groups, keeping the whitespace between them, so blank lines
   and Urdu spacing survive the reveal exactly as they were written. */
function wordGroups(text, per) {
  const parts = text.split(/(\s+)/);
  const groups = [];
  let buf = '', words = 0;
  for (const p of parts) {
    buf += p;
    if (p.trim()) words++;
    if (words >= per) { groups.push(buf); buf = ''; words = 0; }
  }
  if (buf) groups.push(buf);
  return groups;
}

/* Reveal the reply a few words at a time, so a long wait ends in something that reads
   as the guide speaking rather than a finished wall of text. Whatever belongs after
   the words - citations, choices, the off-source flag - is held in `then` and run
   exactly once, when the reveal stops or the learner skips it. Used when a reply arrives
   whole (a fallback); streamed replies are already being written as they come. */
function revealSpeech(bubble, node, text, then) {
  if (bubble.dataset.revealed === '1') return;   // a message already spoken never repeats
  bubble.dataset.revealed = '1';

  const pin = bottomPin($('stream'));
  let timer = null, over = false;
  const finish = () => {
    if (over) return;
    over = true;
    clearTimeout(timer);
    node.textContent = text;
    bubble.classList.remove('revealing');
    bubble.removeAttribute('aria-busy');
    bubble.removeAttribute('title');
    bubble.removeEventListener('click', finish);
    const hint = bubble.querySelector('.skip-hint');
    if (hint) hint.remove();
    then();
    pin();
  };

  if (calmMotion() || !text.trim()) { finish(); return; }

  const groups = wordGroups(text, 3);
  bubble.classList.add('revealing');
  // hold the live region until the reply is whole, or a screen reader hears it in pieces
  bubble.setAttribute('aria-busy', 'true');
  bubble.title = 'Click to show the whole reply';
  bubble.addEventListener('click', finish);
  node.parentNode.appendChild(el('div', 'skip-hint', 'Click to skip'));

  let i = 0;
  const step = () => {
    node.textContent += groups[i];
    i += 1;
    if (i >= groups.length) { finish(); return; }
    pin();
    // a longer beat after a full stop, English or Urdu - speech has punctuation in it
    const pause = /[.!?۔]["')\]]?\s*$/.test(groups[i - 1]) ? 150 : 0;
    timer = setTimeout(step, 26 + Math.random() * 16 + pause);
  };
  timer = setTimeout(step, 80);
}

/* When the AI service is unavailable (billing, an outage, a rate limit) the journey carries on
   with the offline engine. Say so plainly: it is simpler and template-based, and a learner or a
   panel should never mistake it for the real thing. */
function engineBanner(engine) {
  const n = $('engineNote');
  if (!n) return;
  if (engine === 'offline') {
    n.textContent = 'The AI service is not answering right now, so this is the offline engine: simpler, '
      + 'template-based replies, still built only from your document. It switches back by itself when the service returns.';
    n.hidden = false;
  } else if (engine === 'live') n.hidden = true;
}

function feedbackRow(out) {
  const row = el('div', 'fb');
  row.appendChild(el('span', null, 'Was that helpful?'));
  const mk = (glyph, rating, label) => {
    const b = el('button', null, glyph);
    b.type = 'button';
    b.setAttribute('aria-label', label);
    b.addEventListener('click', async () => {
      row.querySelectorAll('button').forEach(x => { x.disabled = true; });
      try {
        await api(`/api/session/${S.learnerId}/feedback`, {
          method: 'POST', body: JSON.stringify({ rating, concept_id: out.concept_id || '' }),
        });
        row.appendChild(el('span', 'thanks', 'Thanks'));
      } catch (_) { row.querySelectorAll('button').forEach(x => { x.disabled = false; }); }
    });
    return b;
  };
  row.append(mk('👍', 1, 'Helpful'), mk('👎', -1, 'Not helpful'));
  return row;
}

/* Draw a guide turn. With `live`, the words are already on screen (they were streamed in);
   otherwise the bubble is made here and the words are revealed. */
function renderTurn(out, live) {
  const b = live ? live.bubble : addBubble('guide', '');
  if (out.interaction_type === 'teach') b.classList.add('teach-beat');
  const say = b.querySelector('.say');

  // mechanic pill
  const pill = el('span', `mechanic ${out.interaction_type}`, out.interaction_type.replace('_', ' '));
  let body;
  if (live) {
    body = live.body;
    say.insertBefore(pill, body);
  } else {
    say.textContent = '';
    say.appendChild(pill);
    body = el('div', 'said');
    say.appendChild(body);
  }
  applyDirection(say, out.message);

  // Held back until the words finish: a learner should read the reply before being
  // asked to act on it, and a citation chip means nothing next to half a sentence.
  const afterSpeech = () => {
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
          applyDirection(q, S.quotes[c.quote_id] || '');
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
        const label = el('span', null, c.text);
        applyDirection(label, c.text);
        btn.appendChild(label);
        btn.addEventListener('click', () => {
          wrap.querySelectorAll('.choice').forEach(x => { x.disabled = true; });
          send(c.text);
        });
        wrap.appendChild(btn);
      });
      say.appendChild(wrap);
    }

    say.appendChild(feedbackRow(out));
    const pin = bottomPin($('stream'));
    pin();
  };

  if (live) { body.textContent = out.message; b.dataset.revealed = '1'; afterSpeech(); }
  else revealSpeech(b, body, out.message, afterSpeech);

  if (out.newly_unlocked && out.newly_unlocked.length) {
    const names = out.newly_unlocked
      .map(id => (S.conceptMap.concepts.find(c => c.id === id) || {}).title)
      .filter(Boolean);
    if (names.length) toast('Unlocked: ' + names.join(', '));
  }

  if (out.effective) { S.eff = out.effective; syncPrefs(); }
  engineBanner(out.engine);
  out.state._currentConcept = (out.adaptation && out.adaptation.focus_concept) || out.concept_id;
  renderBoard(out.state);
  renderStats(out.summary);
  renderAdaptation(out.adaptation);
  if (out.latency_ms) {
    $('latencyNote').textContent = live && live.first
      ? `first words ${(live.first / 1000).toFixed(1)}s · full reply ${(out.latency_ms / 1000).toFixed(1)}s`
      : (out.latency_ms / 1000).toFixed(1) + 's';
  }

  const stream = $('stream');
  stream.scrollTo({ top: stream.scrollHeight, behavior: calmMotion() ? 'auto' : 'smooth' });
  return b;
}

/* ----------------------------------------------------------- waiting */

/* A reply takes a moment to begin. These lines describe what is actually happening in
   that time - they are not a progress bar, because nothing here can honestly report
   progress, and a bank's panel will notice the difference. */
const WAIT_LINES = [
  'Reading what you said',
  'Looking back through your material',
  'Finding the lines that support an answer',
  'Deciding what comes next in your journey',
  'Putting it into words',
];

function waiting() {
  const node = el('div', 'bubble guide');
  const box = el('div', 'thinking');
  const line = el('span', 'line', WAIT_LINES[0]);
  box.append(el('span', 'pip'), line);
  node.appendChild(box);
  $('stream').appendChild(node);
  $('stream').scrollTop = $('stream').scrollHeight;

  let i = 0;
  const timer = setInterval(() => {
    i = (i + 1) % WAIT_LINES.length;
    line.textContent = WAIT_LINES[i];
    line.classList.remove('in');
    void line.offsetWidth;                 // restart the fade for the new line
    line.classList.add('in');
  }, 2300);

  return { node, stop: () => { clearInterval(timer); node.remove(); } };
}

/* ----------------------------------------------------------- sending */

$('sendBtn').addEventListener('click', () => send($('sayBox').value));
$('sayBox').addEventListener('keydown', (e) => {
  // accept both key names - some environments report "Return" rather than "Enter"
  const enter = e.key === 'Enter' || e.key === 'Return' || e.keyCode === 13;
  if (enter && !e.shiftKey) { e.preventDefault(); send($('sayBox').value); }
});

/* One turn, read as it is written. `on.token` gets each piece of the reply; the promise
   resolves with the final payload (citations, choices, mastery, the board). */
async function streamTurn(message, on) {
  const res = await fetch(`/api/session/${S.learnerId}/turn/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    let d = null;
    try { d = await res.json(); } catch (_) { /* not JSON */ }
    const err = new Error((d && d.detail) || `Something went wrong (${res.status}).`);
    err.http = true;
    throw err;
  }
  const reader = res.body.getReader(), dec = new TextDecoder();
  let buf = '', final = null, failure = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let cut;
    while ((cut = buf.indexOf('\n\n')) >= 0) {
      const frame = buf.slice(0, cut);
      buf = buf.slice(cut + 2);
      let ev = 'message', data = '';
      frame.split('\n').forEach(line => {
        if (line.startsWith('event:')) ev = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      });
      if (!data) continue;                       // a keep-alive comment
      const obj = JSON.parse(data);
      if (ev === 'token') on.token(obj.t);
      else if (ev === 'final') final = obj;
      else if (ev === 'error') failure = new Error(obj.detail);
    }
  }
  if (failure) { failure.http = true; throw failure; }
  if (!final) throw new Error('That response did not come through. Please try again.');
  return final;
}

async function send(message) {
  message = (message || '').trim();
  if (!message || S.busy) return;
  S.busy = true;
  $('sendBtn').disabled = true;
  $('sayBox').value = '';
  Voice.stop();
  addBubble('learner', message);

  const wait = waiting();
  const live = { bubble: null, say: null, body: null, text: '', t0: performance.now(), first: 0, pin: null,
                 speech: S.speak ? Voice.stream() : null };

  const beginLive = () => {
    if (live.bubble) return;
    wait.stop();
    live.bubble = addBubble('guide', '');
    live.bubble.classList.add('streaming');
    live.say = live.bubble.querySelector('.say');
    live.body = el('div', 'said');
    live.say.appendChild(live.body);
    live.first = performance.now() - live.t0;
    live.pin = bottomPin($('stream'));
  };

  try {
    let out;
    try {
      out = await streamTurn(message, { token: (t) => {
        beginLive();
        live.text += t;
        live.body.textContent = live.text;
        applyDirection(live.say, live.text);
        live.pin();
        if (live.speech) live.speech.push(t);
      } });
    } catch (e) {
      // A refusal from the server is shown as it is. Only a stream that could not be
      // opened at all (a proxy that buffers or drops it) falls back to the blocking reply.
      if (e.http || live.bubble) throw e;
      out = await api(`/api/session/${S.learnerId}/turn`, { method: 'POST', body: JSON.stringify({ message }) });
      if (live.speech) { live.speech.cancel(); live.speech = null; }
    }
    wait.stop();
    if (live.bubble) live.bubble.classList.remove('streaming');
    renderTurn(out, live.bubble ? live : null);

    // when the guide has finished speaking, hands-free mode listens for the answer
    let spoken = Promise.resolve();
    if (S.speak) spoken = live.speech ? live.speech.end() : Voice.say(out.message);
    spoken.then(() => { if (S.talk && !S.busy) startListening(); });
  } catch (e) {
    wait.stop();
    if (live.speech) live.speech.cancel();
    if (live.bubble) { live.bubble.classList.remove('streaming'); live.bubble.remove(); }
    addBubble('system', e.message);
    toast(e.message, true);
    if (S.talk) setTalk(false);
  } finally {
    S.busy = false;
    $('sendBtn').disabled = false;
  }
}

/* ------------------------------------------------------------- voice */

/* Speaking. The browser's own voices, chosen per stretch of script: Urdu script goes to an
   Urdu voice and Latin script to an English one, so a mixed sentence is read the way a person
   would read it instead of an English voice butchering Urdu. Where no Urdu voice exists the
   reply stays on screen as text and the learner is told why, once. */
const Voice = (() => {
  const synth = window.speechSynthesis || null;
  let voices = [], gen = 0, warned = false;
  const refresh = () => { voices = synth ? synth.getVoices() : []; };
  if (synth) { refresh(); if (synth.addEventListener) synth.addEventListener('voiceschanged', refresh); }

  const score = (v) => (/natural|online|neural/i.test(v.name) ? 4 : 0) + (/google/i.test(v.name) ? 2 : 0) + (v.localService ? 0 : 1);
  function pick(lang) {
    const want = lang === 'ur' ? ['ur-pk', 'ur'] : ['en-pk', 'en-in', 'en-gb', 'en-us', 'en'];
    for (const p of want) {
      const pool = voices.filter(v => (v.lang || '').toLowerCase().replace('_', '-').startsWith(p))
                         .sort((a, b) => score(b) - score(a));
      if (pool.length) return pool[0];
    }
    return null;
  }

  /* runs of Urdu script and runs of everything else, so each can go to the right voice */
  function runs(text) {
    const out = [];
    const re = /([؀-ۿ][؀-ۿ\s،۔؟.,!?'"()\-0-9]*)|([^؀-ۿ]+)/g;
    let m;
    while ((m = re.exec(text))) {
      const t = (m[0] || '').trim();
      if (t && /[\p{L}\p{N}]/u.test(t)) out.push({ t, lang: m[1] ? 'ur' : 'en' });
    }
    return out;
  }

  function warn() {
    if (warned) return;
    warned = true;
    note('This device has no Urdu voice, so Urdu replies stay on screen as text. '
       + 'Microsoft Edge includes natural Urdu voices, and so do Android phones; typing always works.', true);
  }

  function speakRun(r, my) {
    return new Promise(done => {
      if (!synth || my !== gen) return done();
      if (r.lang === 'ur' && !pick('ur')) { warn(); return done(); }
      const u = new SpeechSynthesisUtterance(r.t);
      const v = pick(r.lang);
      u.lang = v ? v.lang : (r.lang === 'ur' ? 'ur-PK' : 'en-PK');
      if (v) u.voice = v;
      u.rate = 0.97;
      u.onend = u.onerror = () => done();
      synth.speak(u);
    });
  }

  const sentences = (t) => String(t).split(/(?<=[.!?۔\n])\s+/).filter(x => x.trim());

  function say(text) {
    if (!synth) return Promise.resolve();
    const my = ++gen;
    synth.cancel();
    const all = [];
    sentences(text).forEach(s => runs(s).forEach(r => all.push(speakRun(r, my))));
    return Promise.all(all).then(() => {});
  }

  /* speak a reply while it is still being written, a sentence at a time */
  function stream() {
    if (!synth) return { push() {}, end: () => Promise.resolve(), cancel() {} };
    const my = ++gen;
    synth.cancel();
    let buf = '';
    const all = [];
    const flush = (final) => {
      const re = /[^.!?۔\n]+[.!?۔\n]+["')\]]*\s*/g;
      let m, used = 0;
      while ((m = re.exec(buf))) { used = re.lastIndex; runs(m[0]).forEach(r => all.push(speakRun(r, my))); }
      buf = buf.slice(used);
      if (final && buf.trim()) { runs(buf).forEach(r => all.push(speakRun(r, my))); buf = ''; }
    };
    return {
      push(t) { buf += t; flush(false); },
      end() { flush(true); return Promise.all(all).then(() => {}); },
      cancel() { if (my === gen) { gen++; synth.cancel(); } },
    };
  }

  function stop() { gen++; if (synth) synth.cancel(); }
  return { say, stream, stop, supported: !!synth, hasUrdu: () => !!pick('ur') };
})();

function note(msg, warn) {
  const n = $('voiceNote');
  if (!msg) { n.hidden = true; return; }
  n.textContent = msg;
  n.classList.toggle('warn', !!warn);
  n.hidden = false;
}

function setSpeak(on) {
  S.speak = on && Voice.supported;
  $('speakToggle').setAttribute('aria-pressed', String(S.speak));
  $('speakToggle').textContent = S.speak ? '🔊 Voice on' : '🔈 Voice off';
  if (!S.speak) { Voice.stop(); if (S.talk) setTalk(false); }
  else if (isUrdu() && !Voice.hasUrdu()) {
    // voices load asynchronously, so give the list a moment before judging it empty
    setTimeout(() => { if (S.speak && isUrdu() && !Voice.hasUrdu()) note('This device has no Urdu voice, so Urdu replies stay on screen as text. Microsoft Edge includes natural Urdu voices, and so do Android phones; typing always works.', true); }, 600);
  }
}

$('speakToggle').addEventListener('click', () => setSpeak(!S.speak));
if (!Voice.supported) {
  $('speakToggle').disabled = true;
  $('speakToggle').title = 'Spoken replies are not supported in this browser - the text is always shown.';
  $('talkToggle').disabled = true;
}

/* Listening. Web Speech recognition is the browser's own; the audio goes to the browser's
   speech service and Rehnuma only ever receives the resulting text. */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recog = null, listening = false, quiet = 0;

const micLang = radioGroup($('micLang'), 'l', () => { S.micChosen = true; });
micLang.set('en-PK', true);

function startListening() {
  if (!SR || listening || S.busy) return;
  Voice.stop();
  recog = new SR();
  recog.lang = micLang.get() || 'en-PK';
  recog.interimResults = true;
  recog.continuous = false;
  let heard = false;

  recog.onstart = () => { listening = true; $('micBtn').classList.add('listening'); $('sayBox').classList.add('listening'); };
  recog.onend = () => {
    listening = false;
    $('micBtn').classList.remove('listening');
    $('sayBox').classList.remove('listening');
    // in hands-free mode a silence is retried once, then handed back to the learner
    if (S.talk && !heard && !S.busy) {
      if (++quiet < 2) startListening();
      else { setTalk(false); note('Talk mode paused - press the microphone when you are ready.'); }
    }
  };
  recog.onerror = (e) => {
    listening = false;
    $('micBtn').classList.remove('listening');
    if (e.error === 'no-speech' || e.error === 'aborted') return;
    const msg = e.error === 'not-allowed' || e.error === 'service-not-allowed'
      ? 'Microphone permission was declined - you can type instead.'
      : e.error === 'language-not-supported'
        ? 'This browser cannot recognise that language - type instead, or switch the microphone language.'
        : e.error === 'network'
          ? 'Speech recognition needs an internet connection - type instead.'
          : 'Speech input did not catch that - try again, or type it.';
    toast(msg, true);
    if (S.talk) setTalk(false);
  };
  recog.onresult = (e) => {
    let text = '';
    for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
    $('sayBox').value = text;
    if (e.results[e.results.length - 1].isFinal) { heard = true; quiet = 0; send(text); }
  };
  try { recog.start(); } catch (_) { /* already running */ }
}

if (!SR) {
  $('micBtn').disabled = true;
  $('micBtn').title = 'Speech input is not supported in this browser - type instead. Chrome and Edge support it.';
  $('talkToggle').disabled = true;
  $('micLang').hidden = true;
  note('Voice input works in Chrome and Edge. Typing works everywhere.');
} else {
  $('micBtn').addEventListener('click', () => {
    if (listening) { recog && recog.stop(); return; }
    note('Your browser’s speech service hears the audio; Rehnuma receives only the text.');
    startListening();
  });
}

function setTalk(on) {
  S.talk = on && !!SR && Voice.supported;
  quiet = 0;
  $('talkToggle').setAttribute('aria-pressed', String(S.talk));
  if (S.talk) {
    if (!S.speak) setSpeak(true);
    if (!S.busy) startListening();
  } else if (listening && recog) { recog.stop(); }
}
$('talkToggle').addEventListener('click', () => setTalk(!S.talk));

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
