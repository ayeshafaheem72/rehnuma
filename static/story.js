/* Rehnuma - the illustrated story.

   A row of scene posters set along a winding road. The camera does what a Prezi does: it
   pulls back to show the whole road, then flies in on the next stop while a truck drives
   there. Each poster is drawn here, in the browser, from a small vocabulary the model can
   only *name* (a layout, an icon, an accent, a few labelled items) - it never supplies
   markup - so a hostile document has no way to put anything on the page through the story.

   Drawing follows the diagram rules: each scene draws the mechanism its idea is about,
   labels sit on the marks (not in a legend to decode), fills use the validated categorical
   palette in fixed order, and every drawing carries a text alternative. */
(function () {
  'use strict';

  const NS = 'http://www.w3.org/2000/svg';
  const INK = '#081426', CREAM = '#F2E9D8', CREAM_2 = '#E2D4B7', MUTED = '#5C5240';

  const ACCENT = {
    pink:   { main: '#E6006E', lt: '#FFB3D6', deep: '#A8004F', on: '#fff' },
    yellow: { main: '#FFC402', lt: '#FFE58A', deep: '#7A5C00', on: INK },
    green:  { main: '#00A878', lt: '#A6E9D2', deep: '#00694B', on: '#fff' },
    blue:   { main: '#0070B8', lt: '#B0D9F5', deep: '#004E80', on: '#fff' },
    red:    { main: '#FF4530', lt: '#FFC0B7', deep: '#B32210', on: '#fff' },
  };
  /* Categorical order for charts. Run through the palette validator against the cream board:
     colour-blind separation dE 9.3 (target >= 8), every mark >= 3:1 against the board. */
  const CHART = ['#E6006E', '#0090B0', '#A87300', '#009469', '#F03A22'];

  /* dawn -> morning -> noon -> dusk -> night, spread across the story - one sky per theme,
     since the "world" each mode plays out in has its own time of day */
  const SKY_STORY = [
    { top: '#3A1C6E', bot: '#FF8A5B', hill: '#7A3B8C' },
    { top: '#1F7AC0', bot: '#9ADBFF', hill: '#2C8F7A' },
    { top: '#1E90E6', bot: '#D4F1FF', hill: '#2FA36B' },
    { top: '#6A2C91', bot: '#FF7A8A', hill: '#5B2A7A' },
    { top: '#0A1636', bot: '#2E4C9A', hill: '#152A5C' },
  ];
  const SKY_CHALLENGE = [        // an afternoon match running into floodlit evening
    { top: '#1E63A8', bot: '#8FC7E8', hill: '#1E6B46' },
    { top: '#1B7FC2', bot: '#BEE6FF', hill: '#237A4C' },
    { top: '#2E93D6', bot: '#DFF4FF', hill: '#2C8F5A' },
    { top: '#5B3A8C', bot: '#F0965B', hill: '#1E5A3C' },
    { top: '#0B1830', bot: '#274E86', hill: '#123322' },
  ];
  const SKY_TOUR = [              // above the clouds, atlas blues throughout
    { top: '#1657A0', bot: '#BFE3FF', hill: '#3E6E8C' },
    { top: '#1B6FC0', bot: '#D6EFFF', hill: '#48789A' },
    { top: '#1E86D6', bot: '#EAF7FF', hill: '#5286A6' },
    { top: '#2E4C8C', bot: '#8FB6E0', hill: '#3A5E82' },
    { top: '#0A1C3E', bot: '#26407A', hill: '#1C3456' },
  ];
  const SKY_DEEP = [               // a garage interior, warm work-light through the session
    { top: '#4A3420', bot: '#B9793A', hill: '#3A3226' },
    { top: '#553C22', bot: '#D89A4E', hill: '#443A2C' },
    { top: '#5C4526', bot: '#F0B25E', hill: '#4A4030' },
    { top: '#3A2A22', bot: '#9A5A32', hill: '#332C22' },
    { top: '#1C140E', bot: '#4A3420', hill: '#201A14' },
  ];

  const REDUCED = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
  const calm = () => !!(REDUCED && REDUCED.matches);

  /* ------------------------------------------------------------ helpers */

  function s(tag, attrs) {
    const n = document.createElementNS(NS, tag);
    if (attrs) for (const k in attrs) if (attrs[k] !== null && attrs[k] !== undefined) n.setAttribute(k, attrs[k]);
    for (let i = 2; i < arguments.length; i++) {
      const kid = arguments[i];
      if (Array.isArray(kid)) kid.forEach(k => k && n.append(k)); else if (kid !== null && kid !== undefined) n.append(kid);
    }
    return n;
  }
  function h(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const RTL_RE = /[؀-ۿ]/;
  const isRtl = (t) => RTL_RE.test(t || '');

  function mix(a, b, t) {
    const pa = a.replace('#', ''), pb = b.replace('#', '');
    let out = '#';
    for (let i = 0; i < 3; i++) {
      const x = parseInt(pa.substr(i * 2, 2), 16), y = parseInt(pb.substr(i * 2, 2), 16);
      out += Math.round(x + (y - x) * t).toString(16).padStart(2, '0');
    }
    return out;
  }
  function rng(seed) {                       // small deterministic generator: same scene, same picture
    let x = (seed * 9301 + 49297) % 233280;
    return () => { x = (x * 9301 + 49297) % 233280; return x / 233280; };
  }
  function wrap(text, max, maxLines) {
    const words = String(text || '').trim().split(/\s+/).filter(Boolean);
    const lines = [];
    let cur = '';
    words.forEach(w => {
      if (cur && (cur + ' ' + w).length > max) { lines.push(cur); cur = w; }
      else cur = cur ? cur + ' ' + w : w;
    });
    if (cur) lines.push(cur);
    if (lines.length > maxLines) {
      lines.length = maxLines;
      lines[maxLines - 1] = lines[maxLines - 1].replace(/[\s,.;:]*$/, '') + '…';
    }
    return lines.length ? lines : [''];
  }
  /* text with wrapping; `v: true` centres the block vertically on y */
  function txt(x, y, str, o) {
    o = o || {};
    const size = o.size || 16, lh = (o.lh || 1.2) * size, rtl = o.rtl === undefined ? isRtl(str) : o.rtl;
    const lines = wrap(str, o.max || 24, o.maxLines || 3);
    const y0 = o.v ? y - ((lines.length - 1) * lh) / 2 + size * 0.34 : y;
    // anchors are given as they look (start = left edge, end = right edge); SVG reads them
    // the other way round once the text runs right-to-left
    const vis = o.anchor || 'middle';
    const t = s('text', {
      x, y: y0, 'font-size': size, 'font-weight': o.weight || 600,
      'text-anchor': rtl ? { start: 'end', end: 'start', middle: 'middle' }[vis] : vis, fill: o.fill || INK,
      class: 't ' + (o.font || 'body') + (rtl ? ' urdu' : ''),
      direction: rtl ? 'rtl' : null,
    });
    lines.forEach((ln, k) => t.append(s('tspan', { x, dy: k === 0 ? 0 : lh }, ln)));
    if (o.pop !== undefined) { t.classList.add('pop'); t.style.setProperty('--i', o.pop); }
    return t;
  }
  function pop(node, i) { node.classList.add('pop'); node.style.setProperty('--i', i); return node; }
  const fmtNum = (n) => Number.isFinite(n) ? n.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '';
  const numOf = (it) => {
    if (typeof it.n === 'number') return it.n;
    const m = String(it.value || '').replace(/,/g, '').match(/\d+(\.\d+)?/);
    return m ? parseFloat(m[0]) : NaN;
  };

  /* -------------------------------------------------------------- icons */

  const C = (cx, cy, r, filled) => ['circle', filled ? { cx, cy, r, fill: 'currentColor', stroke: 'none' } : { cx, cy, r }];
  const R = (x, y, w, hh, rx) => ['rect', { x, y, width: w, height: hh, rx: rx || 0 }];
  const P = (d) => ['path', { d }];

  const ICONS = {
    coin:     [C(12, 12, 9), P('M12 7v10'), P('M15 9.6c-.5-1-1.6-1.6-3-1.6-1.7 0-3 .9-3 2.1s1.2 1.7 3 2.1 3 .9 3 2.1-1.3 2.1-3 2.1c-1.4 0-2.5-.6-3-1.6')],
    bank:     [P('M3 9.5 12 4l9 5.5'), P('M4 9.5h16'), P('M6 12v6M10 12v6M14 12v6M18 12v6'), P('M3 20.5h18')],
    chart:    [R(3.5, 11, 4, 9, 1), R(10, 5, 4, 15, 1), R(16.5, 8, 4, 12, 1)],
    wallet:   [R(3, 6.5, 18, 13, 3), P('M3 10.5h18'), C(16.5, 14.5, 1.2, true)],
    shield:   [P('M12 3l8 3v6c0 4.6-3.3 7.6-8 9-4.7-1.4-8-4.4-8-9V6z'), P('M8.5 12l2.4 2.4 4.7-4.8')],
    lock:     [R(5, 11, 14, 10, 2.5), P('M8 11V8a4 4 0 0 1 8 0v3'), C(12, 16, 1.3, true)],
    key:      [C(8, 15, 4), P('M11 12l9-9'), P('M16 7l3 3'), P('M13.5 9.5l2 2')],
    book:     [P('M12 6.5C10 5 7 4.5 4 4.5v13c3 0 6 .5 8 2 2-1.5 5-2 8-2v-13c-3 0-6 .5-8 2z'), P('M12 6.5v13')],
    bulb:     [P('M9 18h6'), P('M10 21h4'), P('M12 3a6 6 0 0 0-3.6 10.8c.6.5 1.1 1.2 1.1 2V16h5v-.2c0-.8.5-1.5 1.1-2A6 6 0 0 0 12 3z')],
    clock:    [C(12, 12, 9), P('M12 7v5.2l3.4 2')],
    calendar: [R(4, 5, 16, 15, 2.5), P('M4 10h16'), P('M8 3v4M16 3v4')],
    phone:    [R(7, 2.5, 10, 19, 2.5), P('M11 18.5h2')],
    laptop:   [R(4.5, 5.5, 15, 10, 1.5), P('M2.5 19.5h19')],
    person:   [C(12, 8, 4), P('M4.5 21c0-4.2 3.4-7 7.5-7s7.5 2.8 7.5 7')],
    people:   [C(9, 9, 3.4), P('M2.8 20c0-3.6 2.8-6 6.2-6s6.2 2.4 6.2 6'), C(17, 8, 2.6), P('M17 13.2c2.8 0 4.6 1.8 4.6 4.6')],
    heart:    [P('M12 20s-8-4.7-8-10.3A4.4 4.4 0 0 1 12 7a4.4 4.4 0 0 1 8 2.7C20 15.3 12 20 12 20z')],
    leaf:     [P('M5 19c0-8 5-14 15-14 0 10-6 15-14 15'), P('M5 19l8-8')],
    sun:      [C(12, 12, 4), P('M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1')],
    drop:     [P('M12 3s6 6.4 6 11a6 6 0 0 1-12 0c0-4.6 6-11 6-11z')],
    flame:    [P('M12 3c.8 4 5 5.4 5 10a5 5 0 0 1-10 0c0-2 1-3.2 2-4.2.3 1.4 1 2.2 2 2.4C10.5 8 11.4 5.6 12 3z')],
    gear:     [C(12, 12, 3), ['circle', { cx: 12, cy: 12, r: 7.6, 'stroke-dasharray': '2.6 2.1' }], C(12, 12, 5.6)],
    target:   [C(12, 12, 9), C(12, 12, 5), C(12, 12, 1.2, true)],
    flag:     [P('M5 21V4'), P('M5 4h11l-2.2 4L16 12H5')],
    star:     [P('M12 3l2.7 5.5 6 .9-4.4 4.2 1 6L12 16.8 6.7 19.6l1-6L3.3 9.4l6-.9z')],
    home:     [P('M3 11.5 12 4l9 7.5'), P('M5.5 10v10h13V10'), P('M10 20v-5.5h4V20')],
    truck:    [R(1.5, 7, 12, 9.5, 1), P('M13.5 10h4.2l3 3.2v3.3h-7.2'), C(6.2, 18, 2), C(17, 18, 2)],
    pin:      [P('M12 21s7-6.2 7-11.5a7 7 0 0 0-14 0C5 14.8 12 21 12 21z'), C(12, 9.5, 2.5)],
    scale:    [P('M12 4v16'), P('M6 20h12'), P('M5 8h14'), P('M5 8l-3 6.5h6z'), P('M19 8l-3 6.5h6z')],
    warning:  [P('M12 3.5 22 20.5H2z'), P('M12 10v5'), C(12, 17.8, .9, true)],
    check:    [C(12, 12, 9), P('M7.8 12.4l3 3 5.4-6')],
    chat:     [P('M4 5h16v11H10l-5 4v-4H4z')],
    megaphone:[P('M3 10v4h4l8 4V6L7 10z'), P('M18.5 9a4 4 0 0 1 0 6')],
    search:   [C(10.5, 10.5, 6.5), P('M15.5 15.5 21 21')],
    gift:     [R(3, 9, 18, 4, 1), R(5, 13, 14, 8, 1), P('M12 9v12'), P('M12 9C10 4.5 6 5.5 7 8.5c.3.5 1 .5 5 .5zM12 9c2-4.5 6-3.5 5-.5-.3.5-1 .5-5 .5z')],
    cap:      [P('M2 9l10-5 10 5-10 5z'), P('M6 11.5V16c0 1.6 2.7 3 6 3s6-1.4 6-3v-4.5'), P('M22 9v6')],
    globe:    [C(12, 12, 9), P('M3 12h18'), P('M12 3c3.2 3 3.2 15 0 18M12 3c-3.2 3-3.2 15 0 18')],
    sprout:   [P('M12 21v-9'), P('M12 12c0-4-3-6-7.5-6 0 4 3 6 7.5 6z'), P('M12 14.5c0-3.2 2.6-5.5 6.5-5.5 0 3.7-2.6 5.5-6.5 5.5z')],
    medal:    [C(12, 15, 5.5), P('M8 3l4 7 4-7'), P('M12 12.5v5')],
    percent:  [P('M19 5 5 19'), C(7, 7, 2.3), C(17, 17, 2.3)],
    doc:      [P('M6 3h8.5L19 7.5V21H6z'), P('M14 3v5h5'), P('M9 13h7M9 17h7')],
    mail:     [R(3, 5, 18, 14, 2.5), P('M3.5 7l8.5 6 8.5-6')],
    eye:      [P('M2 12s3.8-7 10-7 10 7 10 7-3.8 7-10 7S2 12 2 12z'), C(12, 12, 3)],
    mountain: [P('M2 20l7-12 4.2 7 2.8-4 6 9z')],
  };

  /* the icon as a <g> centred on (cx, cy) at `size` px, stroked in `color` */
  function icon(name, cx, cy, size, color, sw) {
    const g = s('g', {
      transform: `translate(${cx - size / 2} ${cy - size / 2}) scale(${size / 24})`,
      fill: 'none', stroke: color || INK, 'stroke-width': sw || 1.8,
      'stroke-linecap': 'round', 'stroke-linejoin': 'round', color: color || INK,
    });
    (ICONS[name] || ICONS.star).forEach(([tag, attrs]) => g.append(s(tag, attrs)));
    return g;
  }

  /* Truck-art rosette: a ring of petals around a cream disc, the way it is painted on a panel. */
  function rosette(cx, cy, r, c1, c2, spin) {
    const g = s('g', { class: spin ? 'spin-slow' : null });
    const petals = 12;
    for (let i = 0; i < petals; i++) {
      const a = (i / petals) * Math.PI * 2;
      g.append(s('circle', {
        cx: cx + Math.cos(a) * r * 0.8, cy: cy + Math.sin(a) * r * 0.8, r: r * 0.2,
        fill: i % 2 ? c2 : c1, stroke: INK, 'stroke-width': 2,
      }));
    }
    g.append(s('circle', { cx, cy, r: r * 0.76, fill: CREAM, stroke: INK, 'stroke-width': 3 }));
    return g;
  }
  function medallion(cx, cy, r, ac, spin) {
    const g = s('g');
    g.append(rosette(cx, cy, r, ac.main, CHART[1], spin));
    g.append(s('circle', { cx, cy, r: r * 0.6, fill: ac.lt, stroke: INK, 'stroke-width': 2 }));
    return g;
  }

  /* ----------------------------------------------------------- backdrop */

  function hillPath(seed, base, amp, w, h) {
    const r = rng(seed), f1 = 0.008 + r() * 0.006, f2 = 0.021 + r() * 0.01, p1 = r() * 6, p2 = r() * 6;
    let d = `M0 ${h} L0 ${base}`;
    for (let x = 0; x <= w + 20; x += 20) {
      const y = base - amp * (0.55 + 0.3 * Math.sin(x * f1 + p1) + 0.15 * Math.sin(x * f2 + p2));
      d += ` L${x} ${y.toFixed(1)}`;
    }
    return d + ` L${w} ${h} Z`;
  }

  function backdrop(i, n, ac, uid, skyTable) {
    const t = n > 1 ? i / (n - 1) : 0, phase = Math.round(t * 4), sky = (skyTable || SKY_STORY)[phase], r = rng(i + 3);
    const g = s('g');
    const gid = 'sky' + uid;
    g.append(s('defs', null, s('linearGradient', { id: gid, x1: 0, y1: 0, x2: 0, y2: 1 },
      s('stop', { offset: '0', 'stop-color': sky.top }), s('stop', { offset: '1', 'stop-color': sky.bot }))));
    g.append(s('rect', { width: 640, height: 360, fill: `url(#${gid})` }));

    if (phase >= 3) {                       // stars come out towards the end of the story
      for (let k = 0; k < 26; k++) {
        const st = s('circle', { cx: r() * 640, cy: r() * 200, r: 0.8 + r() * 1.6, fill: '#fff', opacity: 0.5 + r() * 0.5 });
        st.classList.add('twinkle'); st.style.animationDelay = (r() * 3).toFixed(2) + 's';
        g.append(st);
      }
    }
    // sun crosses the sky; at night it is the moon
    const sx = [70, 190, 320, 470, 560][phase], sy = [235, 120, 62, 150, 70][phase];
    if (phase === 4) {
      g.append(s('circle', { cx: sx, cy: sy, r: 26, fill: '#F6F1D8' }));
      g.append(s('circle', { cx: sx + 11, cy: sy - 6, r: 24, fill: sky.top }));
    } else {
      const rays = s('g', { class: 'spin-slow' });
      for (let k = 0; k < 12; k++) {
        const a = (k / 12) * Math.PI * 2;
        rays.append(s('line', { x1: sx + Math.cos(a) * 34, y1: sy + Math.sin(a) * 34, x2: sx + Math.cos(a) * 46, y2: sy + Math.sin(a) * 46, stroke: '#FFE58A', 'stroke-width': 4, 'stroke-linecap': 'round' }));
      }
      g.append(rays, s('circle', { cx: sx, cy: sy, r: 27, fill: '#FFD23F', stroke: INK, 'stroke-width': 3 }));
    }
    if (phase < 4) {                        // a couple of clouds drift across
      for (let k = 0; k < 3; k++) {
        const cx = 90 + k * 210 + r() * 40, cy = 40 + r() * 70, w = 46 + r() * 30;
        const cloud = s('g', { class: 'drift', opacity: 0.92 },
          s('ellipse', { cx, cy, rx: w, ry: 13, fill: '#fff' }), s('ellipse', { cx: cx - w * 0.35, cy: cy - 9, rx: w * 0.5, ry: 12, fill: '#fff' }),
          s('ellipse', { cx: cx + w * 0.3, cy: cy - 7, rx: w * 0.42, ry: 10, fill: '#fff' }));
        cloud.style.animationDelay = (-k * 3.5) + 's';
        g.append(cloud);
      }
    }
    g.append(s('path', { d: hillPath(i * 7 + 1, 300, 84, 640, 360), fill: mix(sky.hill, sky.bot, 0.3) }));
    g.append(s('path', { d: hillPath(i * 11 + 5, 328, 50, 640, 360), fill: mix(sky.hill, INK, 0.35) }));
    g.append(s('rect', { y: 338, width: 640, height: 22, fill: mix(sky.hill, INK, 0.6) }));
    return g;
  }

  /* --------------------------------------------------------- the layouts */

  const BOARD = { x: 36, y: 28, w: 568, h: 294 };
  const TITLE_H = 66;
  const AREA = { x: BOARD.x + 16, y: BOARD.y + TITLE_H, w: BOARD.w - 32, h: BOARD.h - TITLE_H - 14 };

  function marker(id, color) {
    return s('marker', { id, viewBox: '0 0 10 10', refX: 8, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' },
      s('path', { d: 'M1 1 L9 5 L1 9 z', fill: color }));
  }

  function layHero(items, A, c) {
    const g = s('g'), cx = A.x + 104, cy = A.y + A.h / 2;
    const left = c.rtl ? A.x + A.w - 104 : cx;
    g.append(medallion(left, cy, 84, c.ac, true), icon(c.icon, left, cy, 82, INK, 1.7));
    if (!items.length) return g;
    const x0 = c.rtl ? A.x + A.w - 232 : A.x + 232, anchor = c.rtl ? 'end' : 'start';
    const wide = A.w - 232;
    let y = A.y + 8, k = 0;
    const big = items.find(it => /\d/.test(it.value || ''));
    if (big) {
      // digits stay in the Latin face even beside Urdu: Nastaliq numerals are tiny
      g.append(txt(x0, y + 50, big.value, { size: 52, weight: 800, font: 'display', anchor, fill: c.ac.deep, rtl: false, pop: k++ }));
      y += 66;
    }
    items.filter(it => it !== big).slice(0, 3).forEach(it => {
      const lines = wrap(it.label, 28, 2), hh = 22 + lines.length * 19;
      const bx = c.rtl ? x0 - wide : x0;
      const st = s('g');
      st.append(s('rect', { x: bx + 4, y: y + 4, width: wide, height: hh, rx: 8, fill: INK }));
      st.append(s('rect', { x: bx, y, width: wide, height: hh, rx: 8, fill: c.ac.lt, stroke: INK, 'stroke-width': 3 }));
      st.append(s('rect', { x: c.rtl ? bx + wide - 10 : bx, y, width: 10, height: hh, fill: c.ac.main, stroke: INK, 'stroke-width': 3 }));
      st.append(txt(c.rtl ? x0 - 20 : x0 + 22, y + hh / 2, it.label,
        { size: 17, weight: 700, anchor, max: 28, maxLines: 2, lh: 1.15, rtl: c.rtl, v: true }));
      g.append(pop(st, k++));
      y += hh + 12;
    });
    return g;
  }

  function layVersus(items, A, c) {
    const g = s('g'), gap = 66, w = (A.w - gap) / 2, hh = A.h - 4;
    (c.rtl ? [1, 0] : [0, 1]).forEach((which, k) => {
      const it = items[which] || { label: '', value: '' };
      const x = A.x + k * (w + gap), col = CHART[which], grp = s('g');
      grp.append(s('rect', { x: x + 5, y: A.y + 9, width: w, height: hh - 5, rx: 12, fill: INK }));
      grp.append(s('rect', { x, y: A.y + 4, width: w, height: hh - 5, rx: 12, fill: '#fff', stroke: INK, 'stroke-width': 3 }));
      grp.append(s('path', { d: `M${x} ${A.y + 56} V${A.y + 16} a12 12 0 0 1 12 -12 H${x + w - 12} a12 12 0 0 1 12 12 V${A.y + 56} Z`, fill: col, stroke: INK, 'stroke-width': 3 }));
      grp.append(txt(x + w / 2, A.y + 31, it.label, { size: 20, weight: 800, font: 'display', fill: '#fff', max: Math.floor(w / 11.5), maxLines: 2, v: true, lh: 1.08 }));
      grp.append(txt(x + w / 2, A.y + 60 + (hh - 66) / 2, it.value || '', { size: 17, weight: 600, max: Math.floor(w / 9), maxLines: 4, v: true, lh: 1.25 }));
      g.append(pop(grp, which));
    });
    const vs = s('g');
    vs.append(s('circle', { cx: A.x + w + gap / 2, cy: A.y + A.h / 2, r: 26, fill: INK }));
    vs.append(s('circle', { cx: A.x + w + gap / 2, cy: A.y + A.h / 2, r: 21, fill: c.ac.main, stroke: CREAM, 'stroke-width': 2 }));
    vs.append(txt(A.x + w + gap / 2, A.y + A.h / 2 + 6, 'VS', { size: 17, weight: 800, font: 'mono', fill: c.ac.on, rtl: false }));
    g.append(pop(vs, 2));
    return g;
  }

  function laySteps(items, A, c) {
    const g = s('g'), n = items.length, uid = c.uid;
    const mx = (x) => c.rtl ? 2 * A.x + A.w - x : x;
    const xs = items.map((_, k) => mx(A.x + 44 + (k * (A.w - 88)) / Math.max(1, n - 1)));
    const ys = items.map((_, k) => A.y + A.h / 2 + (k % 2 ? 22 : -22));
    let d = `M${xs[0]} ${ys[0]}`;
    for (let k = 1; k < n; k++) { const mx = (xs[k - 1] + xs[k]) / 2; d += ` C${mx} ${ys[k - 1]} ${mx} ${ys[k]} ${xs[k]} ${ys[k]}`; }
    g.append(s('path', { d, fill: 'none', stroke: INK, 'stroke-width': 14, 'stroke-linecap': 'round' }));
    g.append(s('path', { d, fill: 'none', stroke: '#35496A', 'stroke-width': 9, 'stroke-linecap': 'round' }));
    const dash = s('path', { d, fill: 'none', stroke: c.ac.lt, 'stroke-width': 2.5, 'stroke-dasharray': '7 7', class: 'flow' });
    g.append(dash);
    items.forEach((it, k) => {
      const up = k % 2 === 0, node = s('g');
      node.append(s('circle', { cx: xs[k] + 3, cy: ys[k] + 3, r: 21, fill: INK }));
      node.append(s('circle', { cx: xs[k], cy: ys[k], r: 21, fill: c.ac.main, stroke: INK, 'stroke-width': 3 }));
      node.append(txt(xs[k], ys[k] + 6.5, String(k + 1), { size: 19, weight: 800, font: 'mono', fill: c.ac.on, rtl: false }));
      const ly = up ? ys[k] - 42 - (wrap(it.label, 16, 2).length - 1) * 16 : ys[k] + 44;
      node.append(txt(xs[k], ly, it.label, { size: 15.5, weight: 700, max: 17, maxLines: 2, lh: 1.15 }));
      if (it.value) {
        const vy = up ? ys[k] + 44 : ys[k] - 34;
        node.append(s('rect', { x: xs[k] - 34, y: vy - 14, width: 68, height: 20, rx: 10, fill: c.ac.lt, stroke: INK, 'stroke-width': 2 }));
        node.append(txt(xs[k], vy, it.value, { size: 12.5, weight: 700, font: 'mono', max: 10, maxLines: 1, rtl: false }));
      }
      g.append(pop(node, k));
    });
    return g;
  }

  function layGrowth(items, A, c) {
    const g = s('g'), n = items.length;
    const vals = items.map(numOf), max = Math.max.apply(null, vals) || 1;
    const base = A.y + A.h - 36, top = A.y + 22, bw = Math.min(64, ((A.w - 40) / n) * 0.62);
    const step = (A.w - 40) / n;
    g.append(s('line', { x1: A.x + 6, x2: A.x + A.w - 6, y1: base, y2: base, stroke: INK, 'stroke-width': 3, 'stroke-linecap': 'round' }));
    items.forEach((it, k) => {
      const v = vals[k], hh = Math.max(6, ((base - top) * v) / max), x = A.x + 20 + step * k + (step - bw) / 2, y = base - hh, r = 7;
      const bar = s('g');
      const d = `M${x} ${base} V${y + r} a${r} ${r} 0 0 1 ${r} ${-r} H${x + bw - r} a${r} ${r} 0 0 1 ${r} ${r} V${base} Z`;
      bar.append(s('path', { d, fill: c.ac.main, stroke: INK, 'stroke-width': 3, class: 'bar' }, s('title', null, `${it.label}: ${fmtNum(v)}`)));
      bar.append(txt(x + bw / 2, y - 8, fmtNum(v), { size: 15, weight: 800, font: 'mono', rtl: false }));
      bar.append(txt(x + bw / 2, base + 19, it.label, { size: 13, weight: 600, max: 13, maxLines: 2, lh: 1.1 }));
      g.append(pop(bar, k));
    });
    return g;
  }

  function layPie(items, A, c) {
    const g = s('g'), cx = c.rtl ? A.x + A.w - 104 : A.x + 104, cy = A.y + A.h / 2, R = 90, r = 46, rm = (R + r) / 2, sw = R - r;
    const vals = items.map(numOf), total = vals.reduce((a, b) => a + b, 0) || 1, circ = 2 * Math.PI * rm;
    g.append(s('circle', { cx, cy, r: R + 1.5, fill: CREAM_2, stroke: INK, 'stroke-width': 3 }));
    let acc = 0;
    items.forEach((it, k) => {
      const len = (vals[k] / total) * circ, gap = items.length > 1 ? 3 : 0;
      const seg = s('circle', {
        cx, cy, r: rm, fill: 'none', stroke: CHART[k % CHART.length], 'stroke-width': sw,
        'stroke-dasharray': `${Math.max(0, len - gap)} ${circ}`, 'stroke-dashoffset': -acc,
        transform: `rotate(-90 ${cx} ${cy})`, class: 'seg',
      }, s('title', null, `${it.label}: ${fmtNum(vals[k])}%`));
      seg.style.setProperty('--i', k);
      g.append(seg);
      acc += len;
    });
    g.append(s('circle', { cx, cy, r: r - 1.5, fill: CREAM, stroke: INK, 'stroke-width': 3 }));
    g.append(icon(c.icon, cx, cy, 44, INK, 1.8));
    const lx = c.rtl ? A.x + A.w - 232 : A.x + 232;
    items.forEach((it, k) => {
      const y = A.y + 12 + k * 40, row = s('g');
      row.append(s('rect', { x: c.rtl ? lx - 22 : lx, y: y - 4, width: 22, height: 22, rx: 4, fill: CHART[k % CHART.length], stroke: INK, 'stroke-width': 2.5 }));
      row.append(txt(c.rtl ? lx - 32 : lx + 34, y + 13, it.label, { size: 17, weight: 700, anchor: c.rtl ? 'end' : 'start', max: 22, maxLines: 1, rtl: c.rtl }));
      row.append(txt(c.rtl ? A.x + 8 : A.x + A.w - 8, y + 14, fmtNum(vals[k]) + '%', { size: 16, weight: 800, font: 'mono', anchor: c.rtl ? 'start' : 'end', rtl: false }));
      g.append(pop(row, k));
    });
    return g;
  }

  function layCycle(items, A, c) {
    const g = s('g'), n = items.length, cx = A.x + A.w / 2, cy = A.y + A.h / 2, rx = A.w * 0.3, ry = A.h * 0.33, uid = c.uid;
    const mid = 'ar' + uid;
    g.append(s('defs', null, marker(mid, INK)));
    const ang = (k) => -Math.PI / 2 + (k / n) * Math.PI * 2;
    const pt = (k, ex) => [cx + Math.cos(ang(k)) * (rx + (ex || 0)), cy + Math.sin(ang(k)) * (ry + (ex || 0) * 0.6)];
    const nodes = items.map((_, k) => pt(k));
    // arrows follow the ellipse from each node to the next, leaving room for the boxes
    items.forEach((it, k) => {
      const a0 = ang(k) + 0.42, a1 = ang(k + 1) - 0.42, x0 = cx + Math.cos(a0) * rx, y0 = cy + Math.sin(a0) * ry, x1 = cx + Math.cos(a1) * rx, y1 = cy + Math.sin(a1) * ry;
      const path = s('path', { d: `M${x0} ${y0} A${rx} ${ry} 0 0 1 ${x1} ${y1}`, fill: 'none', stroke: INK, 'stroke-width': 3.5, 'marker-end': `url(#${mid})`, 'stroke-linecap': 'round', class: 'flow-arrow' });
      g.append(path);
      if (it.value) {
        const am = (a0 + a1) / 2;
        g.append(txt(cx + Math.cos(am) * (rx + 26), cy + Math.sin(am) * (ry + 20), it.value, { size: 12.5, weight: 700, font: 'mono', max: 12, maxLines: 1, rtl: false }));
      }
    });
    g.append(s('circle', { cx, cy, r: 36, fill: c.ac.lt, stroke: INK, 'stroke-width': 3 }));
    g.append(icon(c.icon, cx, cy, 40, INK, 1.8));
    items.forEach((it, k) => {
      const lines = wrap(it.label, 22, 3), bw = 176, bh = 22 + lines.length * 17, [x, y] = nodes[k], node = s('g');
      node.append(s('rect', { x: x - bw / 2 + 4, y: y - bh / 2 + 4, width: bw, height: bh, rx: 12, fill: INK }));
      node.append(s('rect', { x: x - bw / 2, y: y - bh / 2, width: bw, height: bh, rx: 12, fill: CREAM, stroke: INK, 'stroke-width': 3 }));
      node.append(s('rect', { x: x - bw / 2, y: y - bh / 2, width: bw, height: 8, rx: 4, fill: CHART[k % CHART.length], stroke: INK, 'stroke-width': 2 }));
      node.append(txt(x, y + 4, it.label, { size: 14.5, weight: 700, max: 22, maxLines: 3, v: true, lh: 1.12 }));
      g.append(pop(node, k));
    });
    return g;
  }

  function shieldPath(cx, cy, w, hh) {
    const x = cx - w / 2, y = cy - hh / 2;
    return `M${cx} ${y} L${x + w} ${y + hh * 0.16} V${y + hh * 0.52} C${x + w} ${y + hh * 0.8} ${cx + w * 0.2} ${y + hh * 0.94} ${cx} ${y + hh} C${cx - w * 0.2} ${y + hh * 0.94} ${x} ${y + hh * 0.8} ${x} ${y + hh * 0.52} V${y + hh * 0.16} Z`;
  }

  function layShield(items, A, c) {
    const g = s('g'), cx = A.x + A.w / 2, cy = A.y + A.h / 2, uid = c.uid, mid = 'sh' + uid;
    g.append(s('defs', null, marker(mid, '#B32210')));
    const slots = [[A.x + 92, A.y + 34], [A.x + A.w - 92, A.y + 34], [A.x + 92, A.y + A.h - 34], [A.x + A.w - 92, A.y + A.h - 34]];
    items.slice(0, 4).forEach((it, k) => {
      const [x, y] = slots[k], lines = wrap(it.label, 20, 2), bw = 170, bh = 20 + lines.length * 17, node = s('g');
      const towards = [x < cx ? 1 : -1, y < cy ? 1 : -1];
      const ax = x + towards[0] * (bw / 2 + 2), ay = y + towards[1] * (bh / 2 - 2);
      const tx = cx - towards[0] * 44, ty = cy - towards[1] * 26;
      node.append(s('path', { d: `M${ax} ${ay} L${tx} ${ty}`, stroke: '#B32210', 'stroke-width': 3.5, 'stroke-dasharray': '6 5', 'marker-end': `url(#${mid})`, class: 'flow-arrow', fill: 'none' }));
      node.append(s('rect', { x: x - bw / 2 + 4, y: y - bh / 2 + 4, width: bw, height: bh, rx: 10, fill: INK }));
      node.append(s('rect', { x: x - bw / 2, y: y - bh / 2, width: bw, height: bh, rx: 10, fill: '#fff', stroke: INK, 'stroke-width': 3 }));
      const bx = x - bw / 2 + 4, by = y - bh / 2 + 4;
      node.append(s('circle', { cx: bx, cy: by, r: 11, fill: '#FF4530', stroke: INK, 'stroke-width': 2.5 }));
      node.append(s('path', { d: `M${bx - 4} ${by - 4} l8 8 M${bx + 4} ${by - 4} l-8 8`, stroke: '#fff', 'stroke-width': 2.5, 'stroke-linecap': 'round', fill: 'none' }));
      node.append(txt(x + 6, y + 1, it.label, { size: 14.5, weight: 700, max: 20, maxLines: 2, v: true, lh: 1.12 }));
      g.append(pop(node, k));
    });
    const core = s('g', { class: 'breathe' });
    core.append(s('path', { d: shieldPath(cx + 4, cy + 4, 118, 140), fill: INK }));
    core.append(s('path', { d: shieldPath(cx, cy, 118, 140), fill: c.ac.main, stroke: INK, 'stroke-width': 4 }));
    core.append(s('path', { d: shieldPath(cx, cy, 92, 112), fill: 'none', stroke: c.ac.lt, 'stroke-width': 3 }));
    core.append(icon(c.icon, cx, cy, 58, c.ac.on === '#fff' ? '#fff' : INK, 1.8));
    g.append(core);
    return g;
  }

  function layChecklist(items, A, c) {
    const g = s('g'), n = items.length, cols = n > 4 ? 2 : 1, per = Math.ceil(n / cols), rh = Math.min(62, (A.h - 6) / per);
    const cw = cols === 2 ? A.w / 2 - 8 : A.w, top = A.y + Math.max(4, (A.h - per * rh) / 2);
    items.forEach((it, k) => {
      const col = Math.floor(k / per), row = k % per, y = top + row * rh;
      const x = A.x + col * (cw + 16), row_ = s('g');
      const bx = c.rtl ? x + cw - 34 : x;
      row_.append(s('rect', { x: bx + 3, y: y + 3, width: 32, height: 32, rx: 7, fill: INK }));
      row_.append(s('rect', { x: bx, y, width: 32, height: 32, rx: 7, fill: '#fff', stroke: INK, 'stroke-width': 3 }));
      const tick = s('path', { d: `M${bx + 7} ${y + 17} l7 7 l12 -14`, fill: 'none', stroke: '#00694B', 'stroke-width': 5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', class: 'tick' });
      tick.style.setProperty('--i', k);
      row_.append(tick);
      row_.append(txt(c.rtl ? bx - 12 : bx + 46, y + 16, it.label, { size: cols === 2 ? 17 : 19, weight: 700, anchor: c.rtl ? 'end' : 'start', max: cols === 2 ? 26 : 44, maxLines: 2, lh: 1.15, rtl: c.rtl, v: true }));
      g.append(pop(row_, k));
    });
    return g;
  }

  function layTimeline(items, A, c) {
    const g = s('g'), n = items.length, y = A.y + A.h / 2, mid = 'tl' + c.uid;
    g.append(s('defs', null, marker(mid, INK)));
    g.append(s('line', c.rtl ? { x1: A.x + A.w - 6, y1: y, x2: A.x + 4, y2: y, stroke: INK, 'stroke-width': 5, 'stroke-linecap': 'round', 'marker-end': `url(#${mid})` }
                             : { x1: A.x + 6, y1: y, x2: A.x + A.w - 4, y2: y, stroke: INK, 'stroke-width': 5, 'stroke-linecap': 'round', 'marker-end': `url(#${mid})` }));
    items.forEach((it, k) => {
      const x0 = A.x + 84 + (k * (A.w - 168)) / Math.max(1, n - 1), x = c.rtl ? 2 * A.x + A.w - x0 : x0, up = k % 2 === 0, node = s('g');
      node.append(s('line', { x1: x, y1: y, x2: x, y2: up ? y - 30 : y + 30, stroke: INK, 'stroke-width': 3 }));
      node.append(s('circle', { cx: x, cy: y, r: 11, fill: c.ac.main, stroke: INK, 'stroke-width': 3.5 }));
      const lines = wrap(it.label, 17, 2), ly = up ? y - 36 - (lines.length - 1) * 16 : y + 50;
      node.append(txt(x, ly, it.label, { size: 15.5, weight: 700, max: 17, maxLines: 2, lh: 1.15 }));
      if (it.value) {
        const vy = up ? y + 42 : y - 30;
        node.append(s('rect', { x: x - 38, y: vy - 15, width: 76, height: 22, rx: 11, fill: c.ac.lt, stroke: INK, 'stroke-width': 2 }));
        node.append(txt(x, vy, it.value, { size: 12.5, weight: 700, font: 'mono', max: 11, maxLines: 1, rtl: false }));
      }
      g.append(pop(node, k));
    });
    return g;
  }

  const LAYOUTS = { hero: layHero, versus: layVersus, steps: laySteps, growth: layGrowth, pie: layPie,
                    cycle: layCycle, shield: layShield, checklist: layChecklist, timeline: layTimeline };

  /* what a screen reader is told instead of the picture */
  function altText(sc) {
    const parts = (sc.items || []).map(it => it.value ? `${it.label}, ${it.value}` : it.label);
    return `${sc.title}. ${sc.layout} diagram: ${parts.join('; ')}.`;
  }

  /* One scene poster, drawn as a single SVG. */
  function drawScene(sc, i, n, uid, sky) {
    const ac = ACCENT[sc.accent] || ACCENT.pink;
    const rtl = isRtl(sc.title) || isRtl((sc.items[0] || {}).label);
    const svg = s('svg', { viewBox: '0 0 640 360', role: 'img', 'aria-label': altText(sc), preserveAspectRatio: 'xMidYMid slice', class: 'art' });
    svg.append(backdrop(i, n, ac, uid, sky));
    // the board: a cream panel with a hard shadow, like the painted panels on a truck
    svg.append(s('rect', { x: BOARD.x + 7, y: BOARD.y + 7, width: BOARD.w, height: BOARD.h, fill: INK, opacity: 0.55 }));
    svg.append(s('rect', { x: BOARD.x, y: BOARD.y, width: BOARD.w, height: BOARD.h, fill: CREAM, stroke: INK, 'stroke-width': 4 }));
    // the chevron strip that edges every panel in this design: slanted colour blocks
    const chev = s('g');
    const y0 = BOARD.y + 4, y1 = BOARD.y + 12;
    for (let k = 0; k < 29; k++) {
      const x = BOARD.x + 4 + k * 20;
      chev.append(s('polygon', { points: `${x + 6},${y0} ${x + 16},${y0} ${x + 10},${y1} ${x},${y1}`, fill: CHART[k % 4] }));
    }
    svg.append(chev);

    svg.append(txt(rtl ? BOARD.x + BOARD.w - 22 : BOARD.x + 22, BOARD.y + 42, sc.title, {
      size: 25, weight: 800, font: rtl ? 'body' : 'display', anchor: rtl ? 'end' : 'start', max: 32, maxLines: 2, lh: 1.08, rtl }));
    const tagX = rtl ? BOARD.x + BOARD.w - 88 : BOARD.x + 14;
    svg.append(s('rect', { x: tagX, y: BOARD.y - 12, width: 74, height: 22, fill: ac.main, stroke: INK, 'stroke-width': 3 }));
    svg.append(txt(tagX + 37, BOARD.y + 4, `${i + 1} / ${n}`, { size: 13, weight: 800, font: 'mono', fill: ac.on, rtl: false }));

    const ctx = { ac, icon: sc.icon, rtl, uid };
    const layout = LAYOUTS[sc.layout] || layHero;
    let diagram;
    try { diagram = layout(sc.items || [], AREA, ctx); }
    catch (e) { diagram = layHero([], AREA, ctx); }        // a bad drawing degrades to the hero, not a blank
    svg.append(diagram);

    const medX = rtl ? BOARD.x + 30 : BOARD.x + BOARD.w - 30;
    svg.append(medallion(medX, BOARD.y + 27, 40, ac, true));
    svg.append(icon(sc.icon, medX, BOARD.y + 27, 34, INK, 1.9));
    return svg;
  }

  /* Narrow screens: the diagram's labels would be 8px tall, so the poster keeps the picture
     (sky, medallion) and the items become real, wrapping, tappable-size text below it. */
  function drawCompact(sc, i, n, uid, sky) {
    const ac = ACCENT[sc.accent] || ACCENT.pink;
    const wrap_ = h('div', 'compact-card');
    const svg = s('svg', { viewBox: '0 0 640 250', class: 'art', preserveAspectRatio: 'xMidYMid slice', 'aria-hidden': 'true' });
    svg.append(backdrop(i, n, ac, uid, sky));
    svg.append(medallion(320, 128, 74, ac, true), icon(sc.icon, 320, 128, 84, INK, 1.8));
    wrap_.append(svg);
    const body = h('div', 'compact-body');
    body.append(h('div', 'compact-title' + (isRtl(sc.title) ? ' urdu rtl' : ''), sc.title));
    const ul = h('ul', 'compact-items');
    (sc.items || []).forEach(it => {
      const li = h('li', isRtl(it.label) ? 'urdu rtl' : '', it.value ? `${it.label} — ${it.value}` : it.label);
      ul.append(li);
    });
    body.append(ul);
    wrap_.append(body);
    return wrap_;
  }

  /* --------------------------------------------------------- the truck */

  function truck() {
    const g = s('g');
    g.append(s('rect', { x: 0, y: 10, width: 50, height: 26, rx: 3, fill: '#E6006E', stroke: INK, 'stroke-width': 3.5 }));
    g.append(s('rect', { x: 4, y: 15, width: 42, height: 5, fill: '#FFC402' }));
    g.append(s('rect', { x: 50, y: 17, width: 20, height: 19, rx: 3, fill: '#FFC402', stroke: INK, 'stroke-width': 3.5 }));
    g.append(s('path', { d: 'M54 20h11l4 7H54z', fill: '#9ADBFF', stroke: INK, 'stroke-width': 2.5 }));
    g.append(s('circle', { cx: 25, cy: 27, r: 6.5, fill: '#00A878', stroke: INK, 'stroke-width': 2.5 }));
    g.append(s('circle', { cx: 25, cy: 27, r: 2.4, fill: '#FFC402' }));
    g.append(s('path', { d: 'M2 10 L8 2 L16 10 M22 10 L28 2 L36 10', fill: 'none', stroke: INK, 'stroke-width': 2.5 }));
    // the outer group places the wheel; the inner one spins, so the two transforms never fight
    [[14, 41], [58, 41]].forEach(([cx, cy]) => {
      const place = s('g', { transform: `translate(${cx} ${cy})` });
      const w = s('g', { class: 'wheel' });
      w.append(s('circle', { r: 8, fill: INK }), s('circle', { r: 3.4, fill: CREAM }));
      place.append(w);
      g.append(place);
    });
    return g;
  }

  function flagSvg(color) {
    return s('g', null, s('line', { x1: 0, y1: 0, x2: 0, y2: -46, stroke: INK, 'stroke-width': 4, 'stroke-linecap': 'round' }),
      s('path', { d: 'M2 -46 H30 L24 -37 L30 -28 H2 Z', fill: color, stroke: INK, 'stroke-width': 3 }));
  }

  /* the other three movers - same 72x50 box as the truck, so the positioning and
     rotation math in setTruck()/drive() never has to know which one it is placing */
  function cricketBall() {
    const g = s('g');
    g.append(s('circle', { cx: 36, cy: 25, r: 20, fill: '#B32210', stroke: INK, 'stroke-width': 3.5 }));
    g.append(s('path', { d: 'M22 9c8 6 8 26 0 32', fill: 'none', stroke: CREAM, 'stroke-width': 2.2, 'stroke-linecap': 'round' }));
    g.append(s('path', { d: 'M50 9c-8 6-8 26 0 32', fill: 'none', stroke: CREAM, 'stroke-width': 2.2, 'stroke-linecap': 'round' }));
    return g;
  }
  function paperPlane() {
    const g = s('g');
    g.append(s('path', { d: 'M4 26 L64 6 L34 46 L28 30 Z', fill: CREAM, stroke: INK, 'stroke-width': 3.5, 'stroke-linejoin': 'round' }));
    g.append(s('path', { d: 'M4 26 L28 30 L34 46', fill: 'none', stroke: INK, 'stroke-width': 2.2, 'stroke-linejoin': 'round' }));
    g.append(s('path', { d: 'M28 30 L64 6', fill: 'none', stroke: '#B0D9F5', 'stroke-width': 2, 'stroke-dasharray': '1 5', 'stroke-linecap': 'round' }));
    return g;
  }
  function toolTrolley() {
    const g = s('g');
    g.append(s('rect', { x: 22, y: 2, width: 28, height: 8, rx: 2, fill: INK }));
    g.append(s('rect', { x: 10, y: 8, width: 52, height: 24, rx: 3, fill: '#5C5240', stroke: INK, 'stroke-width': 3.5 }));
    g.append(s('rect', { x: 10, y: 8, width: 52, height: 7, rx: 3, fill: '#FFC402', stroke: INK, 'stroke-width': 3 }));
    g.append(icon('gear', 36, 25, 20, INK, 2));
    [[22, 39], [50, 39]].forEach(([cx, cy]) => {
      const place = s('g', { transform: `translate(${cx} ${cy})` });
      const w = s('g', { class: 'wheel' });
      w.append(s('circle', { r: 8, fill: INK }), s('circle', { r: 3.4, fill: CREAM }));
      place.append(w);
      g.append(place);
    });
    return g;
  }

  /* ---------------------------------------------------------- theme chrome */

  /* Everything below tells the world it is a road, a cricket ground, a flight path or a
     workshop bench: route colours, what stands beside it, the badge at each stop, the
     start/end markers, the thing that moves, and the words the HUD uses for a "scene".
     The camera, the poster content and the state machine never look at this - a theme is
     purely the stage dressing. */
  const THEMES = {
    story: {
      sky: SKY_STORY,
      route: { fill: '#2C4165', dash: '#FFC402', progress: '#FFE58A' },
      badge: { fill: '#FFC402', text: INK },
      startColor: '#00A878', endColor: '#E6006E',
      decor(rsvg, x, y, sz) {
        rsvg.append(s('g', { transform: `translate(${x} ${y}) scale(${sz})` },
          s('rect', { x: -3, y: -8, width: 6, height: 16, fill: '#4A3A2A' }),
          s('path', { d: 'M0 -46 L15 -6 H-15 Z', fill: mix('#00A878', INK, 0.35), stroke: INK, 'stroke-width': 2 })));
      },
      vehicle: truck,
      nouns: { unit: 'Scene', endMeta: 'The end of the road', endEyebrow: 'The road ahead' },
    },
    challenge: {
      sky: SKY_CHALLENGE,
      route: { fill: '#1E6B46', dash: '#F2E9D8', progress: '#FF9A86' },
      badge: { fill: '#B32210', text: CREAM },
      startColor: '#00A878', endColor: '#B32210',
      decor(rsvg, x, y, sz) {
        rsvg.append(s('g', { transform: `translate(${x} ${y}) scale(${sz})` },
          s('rect', { x: -7, y: -18, width: 3, height: 18, fill: '#D9B173', stroke: INK, 'stroke-width': 1.5 }),
          s('rect', { x: -1.5, y: -18, width: 3, height: 18, fill: '#D9B173', stroke: INK, 'stroke-width': 1.5 }),
          s('rect', { x: 4, y: -18, width: 3, height: 18, fill: '#D9B173', stroke: INK, 'stroke-width': 1.5 }),
          s('rect', { x: -8, y: -21, width: 16, height: 3, fill: INK })));
      },
      vehicle: cricketBall,
      nouns: { unit: 'Over', endMeta: 'The end of the last over', endEyebrow: 'Last over' },
    },
    tour: {
      sky: SKY_TOUR,
      route: { fill: '#123A66', dash: '#F2E9D8', progress: '#9ADBFF' },
      badge: { fill: '#0070B8', text: CREAM },
      startColor: '#0070B8', endColor: '#00B4D8',
      decor(rsvg, x, y, sz) { rsvg.append(icon('pin', x, y - 16 * sz, 30 * sz, '#E6006E', 2)); },
      vehicle: paperPlane,
      nouns: { unit: 'Stop', endMeta: 'The end of the journey', endEyebrow: 'Journey complete' },
    },
    deep: {
      sky: SKY_DEEP,
      route: { fill: '#4A4030', dash: '#FFC402', progress: '#FFE58A' },
      badge: { fill: '#8A8064', text: INK },
      startColor: '#FFC402', endColor: '#FF4530',
      decor(rsvg, x, y, sz) {
        rsvg.append(s('g', { transform: `translate(${x} ${y}) scale(${sz})` },
          s('circle', { r: 7, fill: '#8A8064', stroke: INK, 'stroke-width': 2 }),
          s('line', { x1: -3.5, y1: 0, x2: 3.5, y2: 0, stroke: INK, 'stroke-width': 1.5 })));
      },
      vehicle: toolTrolley,
      nouns: { unit: 'Station', endMeta: 'The end of the bench', endEyebrow: 'Bench cleared' },
    },
  };

  /* ------------------------------------------------------------- the stage */

  function play(opts) {
    const story = opts.story, mount = opts.mount, scenes = story.scenes || [];
    const n = scenes.length;
    if (!n) { if (opts.onDone) opts.onDone(); return null; }
    const THEME = THEMES[opts.theme] || THEMES.story;

    mount.textContent = '';
    mount.classList.remove('hidden');
    const compact = (mount.clientWidth || window.innerWidth) < 700;

    const frame = h('div', 'story-frame');
    const top = h('div', 'story-top');
    const titleBox = h('div');
    titleBox.append(h('div', 'eyebrow', 'Your story'));
    const titleEl = h('h2', 'story-title' + (isRtl(story.title) ? ' urdu rtl' : ''), story.title || 'Your story');
    titleBox.append(titleEl);
    top.append(titleBox, h('div', 'spacer'));
    const voiceBtn = h('button', 'btn sm ghost', opts.voice && opts.voice.enabled() ? '🔊 Voice on' : '🔈 Voice off');
    voiceBtn.type = 'button';
    const skipBtn = h('button', 'btn sm ghost', 'Skip story ▸▸');
    skipBtn.type = 'button';
    top.append(voiceBtn, skipBtn);

    const stage = h('div', 'story-stage');
    stage.tabIndex = 0;
    stage.setAttribute('role', 'group');
    stage.setAttribute('aria-roledescription', 'story');
    stage.setAttribute('aria-label', 'Illustrated story. Use the arrow keys to move between scenes.');
    const far = h('div', 'story-far'), near = h('div', 'story-near');
    const world = h('div', 'story-world');
    stage.append(far, near, world);

    const hud = h('div', 'story-hud');
    const speaker = h('div', 'speaker');
    const avatar = h('div', 'avatar');
    const who = (story.character || '').trim();
    avatar.textContent = who ? who[0].toUpperCase() : 'R';
    const say = h('div', 'say-col');
    const meta = h('div', 'eyebrow');
    const line = h('div', 'narration');
    line.setAttribute('aria-live', 'polite');
    say.append(meta, line);
    speaker.append(avatar, say);

    const controls = h('div', 'story-controls');
    const back = h('button', 'btn sm ghost', '◀ Back'); back.type = 'button';
    const next = h('button', 'btn sm pink', 'Next ▶'); next.type = 'button';
    const auto = h('button', 'btn sm ghost', '⏸ Pause'); auto.type = 'button';
    const dots = h('div', 'dots', '');
    dots.setAttribute('role', 'group');
    dots.setAttribute('aria-label', THEME.nouns.unit + 's');
    scenes.forEach((_, k) => {
      const d = h('button', 'dot'); d.type = 'button';
      d.setAttribute('aria-label', `Go to ${THEME.nouns.unit.toLowerCase()} ${k + 1}`);
      d.addEventListener('click', () => goto(k));
      dots.append(d);
    });
    controls.append(back, dots, auto, next);
    hud.append(speaker, controls);
    frame.append(top, stage, hud);
    mount.append(frame);

    /* ---- geometry: sized from the stage, so the poster is always readable at full zoom */
    let W = 0, H = 0, cw = 0, ch = 0, geo = [], roadPath = null, pathLen = 0, truckEl = null, truckSvg = null;
    let cams = [];
    const posters = [];

    function measure() { W = stage.clientWidth; H = stage.clientHeight; }

    function build() {
      measure();
      world.textContent = '';
      posters.length = 0;
      if (compact) { cw = clamp(W - 24, 250, 520); ch = clamp(H - 118, 270, 560); }
      else { ch = clamp(H - 128, 200, 560); cw = Math.round(ch * (640 / 360)); if (cw > W * 0.9) { cw = Math.round(W * 0.9); ch = Math.round(cw * (360 / 640)); } }
      const gx = Math.round(cw * 0.5), amp = Math.round(ch * 0.2), padX = Math.round(W * 0.5), padY = 90;
      const worldW = padX * 2 + n * cw + (n - 1) * gx, worldH = ch + amp * 2 + padY * 2 + 60;
      world.style.width = worldW + 'px'; world.style.height = worldH + 'px';
      geo = scenes.map((_, k) => {
        const x = padX + k * (cw + gx), y = padY + amp + (k % 2 ? amp : -amp * 0.2) ;
        return { x, y, cx: x + cw / 2, cy: y + ch / 2, road: { x: x + cw / 2, y: y + ch + 34 } };
      });

      // the route, drawn under the posters - a road, a pitch, a flight path or a bench,
      // depending on the theme; the bezier through the stop points never changes
      const rsvg = s('svg', { class: 'road', width: worldW, height: worldH, viewBox: `0 0 ${worldW} ${worldH}`, 'aria-hidden': 'true' });
      const pts = [{ x: geo[0].road.x - cw * 0.9, y: geo[0].road.y + 6 }].concat(geo.map(g => g.road), [{ x: geo[n - 1].road.x + cw * 0.9, y: geo[n - 1].road.y - 6 }]);
      let d = `M${pts[0].x} ${pts[0].y}`;
      for (let k = 1; k < pts.length; k++) { const mx = (pts[k - 1].x + pts[k].x) / 2; d += ` C${mx} ${pts[k - 1].y} ${mx} ${pts[k].y} ${pts[k].x} ${pts[k].y}`; }
      const layers = [['road-edge', 46, INK], ['road-fill', 36, THEME.route.fill], ['road-dash', 3, THEME.route.dash]];
      layers.forEach(([cls, w, col]) => rsvg.append(s('path', { d, class: cls, stroke: col, 'stroke-width': w, fill: 'none', 'stroke-linecap': 'round' })));
      roadPath = s('path', { d, fill: 'none', stroke: 'none' });
      rsvg.append(roadPath);
      pathLen = roadPath.getTotalLength();
      // decorations along the verge: cheap, and they make the route feel like a place
      const r = rng(9);
      for (let k = 0; k < Math.round(pathLen / 260); k++) {
        const at = roadPath.getPointAtLength((k + 0.5) * (pathLen / Math.round(pathLen / 260)));
        const side = k % 2 ? 1 : -1, off = 46 + r() * 20, x = at.x, y = at.y + side * off, sz = 0.8 + r() * 0.7;
        THEME.decor(rsvg, x, y, sz);
      }
      geo.forEach((g, k) => {            // a badge at every stop, numbered
        const stop = s('g', { transform: `translate(${g.road.x} ${g.road.y + 40})`, class: 'stop-tyre', 'data-k': k });
        stop.append(s('circle', { r: 20, fill: INK }), s('circle', { r: 14, fill: THEME.badge.fill, stroke: INK, 'stroke-width': 3 }));
        stop.append(s('text', { 'text-anchor': 'middle', y: 5.5, 'font-size': 16, 'font-weight': 800, fill: THEME.badge.text, class: 't mono' }, String(k + 1)));
        rsvg.append(stop);
      });
      const startFlag = flagSvg(THEME.startColor); startFlag.setAttribute('transform', `translate(${pts[0].x + 40} ${pts[0].y - 22})`);
      const endFlag = flagSvg(THEME.endColor); endFlag.setAttribute('transform', `translate(${pts[pts.length - 1].x - 30} ${pts[pts.length - 1].y - 22})`);
      rsvg.append(startFlag, endFlag);
      // the part of the route already travelled lights up
      progress = s('path', { d, class: 'road-progress', stroke: THEME.route.progress, fill: 'none', 'stroke-linecap': 'round', 'stroke-width': 8 });
      progress.style.strokeDasharray = pathLen; progress.style.strokeDashoffset = pathLen;
      rsvg.append(progress);
      world.append(rsvg);

      // the thing that moves along it
      truckSvg = s('svg', { class: 'truck', width: 86, height: 56, viewBox: '0 0 72 50', 'aria-hidden': 'true' });
      truckSvg.append(THEME.vehicle());
      truckEl = h('div', 'truck-wrap'); truckEl.append(truckSvg);

      scenes.forEach((sc, k) => {
        const uid = `${Date.now().toString(36)}${k}`;
        const card = h('section', 'scene' + (compact ? ' compact' : ''));
        card.style.left = geo[k].x + 'px'; card.style.top = geo[k].y + 'px';
        card.style.width = cw + 'px'; card.style.height = ch + 'px';
        card.setAttribute('aria-label', `${THEME.nouns.unit} ${k + 1} of ${n}: ${sc.title}`);
        let art;
        try { art = compact ? drawCompact(sc, k, n, uid, THEME.sky) : drawScene(sc, k, n, uid, THEME.sky); }
        catch (e) { art = drawCompact(sc, k, n, uid, THEME.sky); }
        card.append(art);
        // the source line this scene rests on: the story is grounded like everything else
        const q = opts.quotes && opts.quotes[sc.quote_id];
        if (q) {
          const chip = h('button', 'src-chip', 'source ' + sc.quote_id); chip.type = 'button';
          chip.title = 'The line in your material this scene rests on';
          chip.addEventListener('click', (e) => {
            e.stopPropagation();
            const open = card.querySelector('.src-pop');
            if (open) { open.remove(); return; }
            const pop_ = h('div', 'src-pop', '“' + q + '”');
            card.append(pop_);
          });
          card.append(chip);
        }
        world.append(card);
        posters.push(card);
      });
      world.append(truckEl);
      cams = geo.map(g => camAt(g.cx, g.cy + 22, 1));
      cams.overview = camAt(worldW / 2, worldH / 2, Math.min(W / worldW, H / worldH) * 0.94);
      placeTruck(idx < 0 ? 0 : Math.min(idx, n - 1), true);
    }
    let progress = null;

    function camAt(cx, cy, sc) { return { x: W / 2 - cx * sc, y: H / 2 - cy * sc, s: sc }; }
    function applyCam(c, ms, ease) {
      world.style.transition = ms && !calm() ? `transform ${ms}ms ${ease || 'cubic-bezier(.45,0,.2,1)'}` : 'none';
      world.style.transform = `translate(${c.x}px, ${c.y}px) scale(${c.s})`;
      const px = -c.x;
      far.style.transition = near.style.transition = ms && !calm() ? `background-position ${ms}ms ${ease || 'ease'}` : 'none';
      far.style.backgroundPosition = `${-px * 0.08}px 0`;
      near.style.backgroundPosition = `${-px * 0.2}px bottom`;
    }

    /* the truck's place on the road at a stop, and the drive between two stops */
    function roadLenAt(k) {
      // nearest point on the path to the stop's road point: search along the path
      let best = 0, bd = Infinity;
      const tx = geo[k].road.x, ty = geo[k].road.y;
      for (let l = 0; l <= pathLen; l += 12) { const p = roadPath.getPointAtLength(l), dd = (p.x - tx) ** 2 + (p.y - ty) ** 2; if (dd < bd) { bd = dd; best = l; } }
      return best;
    }
    let stopLens = [];
    function placeTruck(k, instant) {
      if (!stopLens.length || instant) stopLens = geo.map((_, j) => roadLenAt(j));
      const l = stopLens[k];
      setTruck(l);
      progress.style.strokeDashoffset = pathLen - l;
      truckLen = l;
    }
    let truckLen = 0, driveRaf = 0;
    function setTruck(l) {
      const p = roadPath.getPointAtLength(l), q = roadPath.getPointAtLength(Math.min(pathLen, l + 4));
      const ang = Math.atan2(q.y - p.y, q.x - p.x) * 180 / Math.PI;
      truckEl.style.transform = `translate(${p.x - 43}px, ${p.y - 46}px) rotate(${ang}deg)`;
    }
    function drive(toLen, ms, cb) {
      cancelAnimationFrame(driveRaf);
      const from = truckLen, t0 = performance.now();
      truckSvg.classList.add('moving');
      const step = (now) => {
        const t = clamp((now - t0) / ms, 0, 1), e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        truckLen = from + (toLen - from) * e;
        setTruck(truckLen);
        progress.style.strokeDashoffset = pathLen - Math.max(truckLen, from);
        if (t < 1) driveRaf = requestAnimationFrame(step);
        else { truckSvg.classList.remove('moving'); if (cb) cb(); }
      };
      if (calm() || !ms) { truckLen = toLen; setTruck(toLen); progress.style.strokeDashoffset = pathLen - toLen; truckSvg.classList.remove('moving'); if (cb) cb(); return; }
      driveRaf = requestAnimationFrame(step);
    }

    /* ---- state machine */
    let idx = -1, viewed = 0, timers = [], revealTimer = 0, dwellTimer = 0, autoOn = opts.autoplay !== false && !calm(), ended = false, ready = false, gone = false, speaking = false;
    const clearTimers = () => { timers.forEach(clearTimeout); timers = []; clearTimeout(revealTimer); clearTimeout(dwellTimer); };

    function words(text) { return text.split(/(\s+)/); }
    function narrate(text, then) {
      clearTimeout(revealTimer);
      line.textContent = '';
      line.classList.toggle('urdu', isRtl(text)); line.classList.toggle('rtl', isRtl(text));
      line.setAttribute('dir', isRtl(text) ? 'rtl' : 'ltr');
      if (isRtl(text)) line.setAttribute('lang', 'ur'); else line.removeAttribute('lang');
      if (calm()) { line.textContent = text; then(); return; }
      const parts = words(text);
      let i = 0, buf = '', done = false;
      const finish = () => { if (done) return; done = true; clearTimeout(revealTimer); line.textContent = text; line.classList.remove('revealing'); line.removeEventListener('click', finish); then(); };
      line.classList.add('revealing');
      line.addEventListener('click', finish);
      const step = () => {
        if (done) return;
        let w = 0;
        while (i < parts.length && w < 2) { buf += parts[i]; if (parts[i].trim()) w++; i++; }
        line.textContent = buf;
        if (i >= parts.length) { finish(); return; }
        revealTimer = setTimeout(step, 70 + (/[.!?۔]\s*$/.test(buf) ? 170 : 0));
      };
      revealTimer = setTimeout(step, 60);
    }

    function scheduleNext(text) {
      clearTimeout(dwellTimer);
      if (!autoOn || ended || gone) return;
      const dwell = Math.max(4200, text.trim().split(/\s+/).length * 330 + 1400);
      dwellTimer = setTimeout(() => { if (autoOn && !gone && !ended) next.click(); }, dwell);
    }

    function updateHud() {
      dots.querySelectorAll('.dot').forEach((d, k) => { d.classList.toggle('on', !ended && k === idx); d.classList.toggle('done', ended || k < idx); d.setAttribute('aria-current', String(!ended && k === idx)); });
      back.disabled = idx <= 0;
      const last = idx >= n - 1;
      next.textContent = ended ? 'Replay ↺' : (last ? 'Finish ▶' : 'Next ▶');
      auto.textContent = autoOn ? '⏸ Pause' : '▶ Auto-play';
    }

    function goto(k, o) {
      o = o || {};
      if (gone) return;
      k = clamp(k, 0, n - 1);
      const from = idx;
      idx = k; ended = false;
      endCard.classList.remove('on');
      clearTimers();
      if (opts.voice) opts.voice.stop();
      const sc = scenes[k];
      viewed = Math.max(viewed, k + 1);
      if (opts.onProgress) opts.onProgress(viewed);
      posters.forEach((p, j) => p.classList.toggle('on', j === k));
      meta.textContent = `${who ? who + ' · ' : ''}${THEME.nouns.unit} ${k + 1} of ${n}`;
      updateHud();
      const arrive = () => {
        narrate(sc.narration, () => {
          if (opts.voice && opts.voice.enabled()) {
            speaking = true;
            Promise.resolve(opts.voice.speak(sc.narration)).catch(() => {}).then(() => { speaking = false; scheduleNext(sc.narration); });
          } else scheduleNext(sc.narration);
        });
      };
      if (from < 0 || o.instant) {
        // opening move: start pulled all the way back and fly in
        applyCam(cams.overview, 0);
        placeTruck(k, true);
        requestAnimationFrame(() => requestAnimationFrame(() => { if (idx === k && !gone) applyCam(cams[k], calm() ? 0 : 1500, 'cubic-bezier(.3,.8,.2,1)'); }));
        timers.push(setTimeout(arrive, calm() ? 0 : 900));
        return;
      }
      // Prezi move: pull back, then fly to the next stop while the truck drives there
      const a = geo[from], b = geo[k];
      const spanW = Math.abs(a.cx - b.cx) + cw * 1.5, spanH = Math.abs(a.cy - b.cy) + ch * 1.6;
      const sm = clamp(Math.min(W / spanW, H / spanH), 0.16, 0.6);
      const mid = camAt((a.cx + b.cx) / 2, (a.cy + b.cy) / 2 + 20, sm);
      if (calm()) { applyCam(cams[k], 0); placeTruck(k, false); arrive(); return; }
      applyCam(mid, 640, 'cubic-bezier(.5,0,.3,1)');
      timers.push(setTimeout(() => {
        applyCam(cams[k], 1050, 'cubic-bezier(.25,.85,.2,1)');
        drive(stopLens[k], 1400);
      }, 560));
      timers.push(setTimeout(arrive, 1500));
    }

    /* the end of the road: pull all the way back, then offer the way in */
    const endCard = h('div', 'story-end');
    const endBox = h('div', 'end-box');
    endBox.append(h('div', 'eyebrow', THEME.nouns.endEyebrow));
    const endLine = h('p', 'end-line' + (isRtl(story.closing) ? ' urdu rtl' : ''), story.closing || 'Now put it to use.');
    const go = h('button', 'btn pink', 'Start the first mission ▶'); go.type = 'button';
    const wait = h('span', 'small', 'Getting your first mission ready…');
    const replay = h('button', 'btn sm ghost', 'Replay the story ↺'); replay.type = 'button';
    const endBtns = h('div', 'row');
    endBtns.append(go, replay);
    endBox.append(endLine, endBtns, wait);
    endCard.append(endBox);
    stage.append(endCard);

    function showEnd() {
      ended = true;
      clearTimers();
      if (opts.voice) opts.voice.stop();
      posters.forEach(p => p.classList.remove('on'));
      meta.textContent = `${who ? who + ' · ' : ''}${THEME.nouns.endMeta}`;
      line.textContent = story.closing || '';
      line.classList.toggle('urdu', isRtl(story.closing)); line.classList.toggle('rtl', isRtl(story.closing));
      line.setAttribute('dir', isRtl(story.closing) ? 'rtl' : 'ltr');
      dots.querySelectorAll('.dot').forEach(d => { d.classList.remove('on'); d.classList.add('done'); });
      updateHud();
      applyCam(cams.overview, 1300, 'cubic-bezier(.4,0,.2,1)');
      drive(pathLen * 0.985, 1300);
      endCard.classList.add('on');
      refreshGo();
      if (opts.onProgress) opts.onProgress(n);
      go.focus({ preventScroll: true });
    }
    function refreshGo() { go.disabled = !ready; wait.hidden = ready; }

    /* ---- controls */
    function advance() {
      if (ended) { goto(0, { instant: true }); return; }
      if (idx >= n - 1) { showEnd(); return; }
      goto(idx + 1);
    }
    next.addEventListener('click', advance);
    back.addEventListener('click', () => { if (ended) goto(n - 1); else if (idx > 0) goto(idx - 1); });
    auto.addEventListener('click', () => { autoOn = !autoOn; updateHud(); if (autoOn) scheduleNext(scenes[Math.max(0, idx)].narration); else clearTimeout(dwellTimer); });
    replay.addEventListener('click', () => goto(0, { instant: true }));
    go.addEventListener('click', () => { if (!ready) return; finish(false); });
    skipBtn.addEventListener('click', () => finish(true));
    voiceBtn.addEventListener('click', () => {
      if (!opts.voice) return;
      const on = opts.voice.toggle();
      voiceBtn.textContent = on ? '🔊 Voice on' : '🔈 Voice off';
      if (on && idx >= 0 && !ended) opts.voice.speak(scenes[idx].narration);
    });
    function onKey(e) {
      if (gone || mount.classList.contains('hidden')) return;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target.tagName || '').toUpperCase())) return;
      if (e.key === 'ArrowRight' || e.key === ' ' && e.target === stage) { e.preventDefault(); advance(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); back.click(); }
      else if (e.key === 'Escape') { finish(true); }
    }
    document.addEventListener('keydown', onKey);

    let resizeTimer = 0;
    function onResize() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => { if (gone) return; const k = Math.max(0, idx); build(); posters.forEach((p, j) => p.classList.toggle('on', j === k && !ended)); applyCam(ended ? cams.overview : cams[k], 0); }, 160);
    }
    window.addEventListener('resize', onResize);

    function finish(skipped) {
      if (gone) return;
      gone = true;
      clearTimers(); cancelAnimationFrame(driveRaf);
      if (opts.voice) opts.voice.stop();
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', onResize);
      mount.classList.add('hidden');
      mount.textContent = '';
      if (skipped) { if (opts.onSkip) opts.onSkip(); } else if (opts.onDone) opts.onDone();
    }

    /* ---- go */
    build();
    goto(0, { instant: true });
    stage.focus({ preventScroll: true });

    return {
      setReady(v) { ready = !!v; refreshGo(); },
      goto(k) { if (k >= n) showEnd(); else goto(k); },
      overview() { applyCam(cams.overview, 0); },
      destroy() { finish(true); },
      isOpen() { return !gone; },
    };
  }

  window.RehnumaStory = { play, ICONS: Object.keys(ICONS) };
})();
