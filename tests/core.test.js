// 單元測試：從 index.html 抽出 Core（==CORE-BEGIN== … ==CORE-END==）在 Node 執行
// 執行：node tests/core.test.js
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const m = html.match(/\/\/ ==CORE-BEGIN==([\s\S]*?)\/\/ ==CORE-END==/);
assert(m, 'Core block not found');
const Core = new Function(m[1] + '\nreturn Core;')();
const legacy = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures-v1.json'), 'utf8'));
const legacy2 = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures-v2.json'), 'utf8'));
const legacy3 = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures-v3.json'), 'utf8'));

let passed = 0;
function test(name, fn) { try { fn(); passed++; console.log('  ok  ' + name); } catch (e) { console.error('  FAIL ' + name + '\n', e); process.exitCode = 1; } }
const stats = (arr) => { const s = arr.slice().sort((a, b) => a - b); return { min: s[0], median: s[s.length >> 1], p95: s[Math.floor(s.length * 0.95)], max: s[s.length - 1] }; };
const hashLen = (enc) => enc.length + 3;   // "#c=" + data

function fakeHandDrawn(rand) {
  const strokes = [];
  const nStrokes = 3 + Math.floor(rand() * 6);
  for (let k = 0; k < nStrokes; k++) {
    const raw = [];
    const type = rand();
    if (type < 0.1) { raw.push([rand() - 0.5, rand() - 0.5]); }
    else if (type < 0.25) {
      const r = 0.2 + rand() * 0.6, a0 = rand() * 6, span = 1 + rand() * 4;
      for (let i = 0; i <= 80; i++) { const a = a0 + span * i / 80; raw.push([r * Math.cos(a) + (rand() - 0.5) * 0.006, r * Math.sin(a) + (rand() - 0.5) * 0.006]); }
    } else {
      let x = (rand() - 0.5) * 0.4, y = (rand() - 0.5) * 0.4, a = rand() * 6.28;
      const n = 30 + Math.floor(rand() * 90);
      for (let i = 0; i < n; i++) { a += (rand() - 0.5) * 0.25; x += Math.cos(a) * 0.012; y += Math.sin(a) * 0.012; raw.push([x + (rand() - 0.5) * 0.004, y + (rand() - 0.5) * 0.004]); }
    }
    strokes.push(Core.makeStroke(raw, Math.floor(rand() * 3)));
    Core.fitStrokes(strokes, 220);
  }
  if (rand() < 0.3) {                         // 有時在隨機結晶上再加手繪
    const base = Core.randomFlake(rand);
    strokes.push(...base); Core.fitStrokes(strokes, 220);
  }
  return strokes;
}
const cardOf = (strokes, rand) => ({ strokes: strokes.map(s => ({ w: s.w, m: s.m, q: s.q })), beautify: rand() < 0.5 });
const same = (a, b) => {
  assert.strictEqual(b.beautify, a.beautify);
  assert.strictEqual(b.strokes.length, a.strokes.length);
  a.strokes.forEach((s, i) => { assert.strictEqual(b.strokes[i].w, s.w); assert.strictEqual(b.strokes[i].m, s.m !== false); assert.deepStrictEqual(b.strokes[i].q, s.q); });
};

console.log('Core tests (format v' + Core.VERSION + ')');
test('fold maps all 12 symmetric copies to the same wedge point', () => {
  const p = [0.5, 0.2];
  const f0 = Core.fold(p[0], p[1]);
  for (let k = 0; k < 6; k++) for (const mm of [1, -1]) {
    const a = k * Math.PI / 3, x = p[0], y = p[1] * mm;
    const q = Core.fold(x * Math.cos(a) - y * Math.sin(a), x * Math.sin(a) + y * Math.cos(a));
    assert(Math.abs(q[0] - f0[0]) < 1e-9 && Math.abs(q[1] - f0[1]) < 1e-9);
  }
  assert(f0[1] >= 0 && Math.atan2(f0[1], f0[0]) <= Math.PI / 6 + 1e-9);
});

test('random crystals: round trip x1000, per-type length stats, budget & stroke caps', () => {
  const rand = Core.mulberry32(12345);
  const lens = {}, all = [];
  for (let i = 0; i < 1000; i++) {
    const strokes = Core.randomFlake(rand);
    const total = strokes.reduce((n, s) => n + s.q.length, 0);
    assert(total <= 220 && strokes.length <= Core.MAX_STROKES, 'caps ' + total + ' ' + strokes.length);
    assert(strokes.every(s => s.m === true));
    const card = cardOf(strokes, rand);
    const enc = Core.encode(card);
    same(card, Core.decode(enc));
    assert(!/[^A-Za-z0-9_-]/.test(enc));
    (lens[strokes.type] = lens[strokes.type] || []).push(hashLen(enc)); all.push(hashLen(enc));
  }
  for (const t of Object.keys(lens)) console.log('      ' + t.padEnd(13) + ' #c= length', JSON.stringify(stats(lens[t])));
  console.log('      all crystals  #c= length', JSON.stringify(stats(all)));
});

test('crystal geometry is realistic: inside 30° wedge, straight lines at multiples of 30°, 6-fold', () => {
  let segs = 0, maxOff = 0;
  for (const type of Core.CRYSTAL_TYPES) for (let k = 0; k < 150; k++) {
    const strokes = Core.randomFlake(Core.mulberry32(k * 7 + 3), type);
    assert.strictEqual(strokes.type, type);
    for (const s of Core.toFloat(strokes, 3)) {
      for (const p of s.pts) {
        const beyond = p[1] * Math.cos(Math.PI / 6) - p[0] * Math.sin(Math.PI / 6);   // 超出 30° 鏡射線的距離
        assert(p[1] >= 0 && beyond <= 0.006, type + ' point outside wedge ' + p);
        assert(Math.hypot(p[0], p[1]) <= 1.0001);
      }
      for (let i = 1; i < s.pts.length; i++) {
        const dx = s.pts[i][0] - s.pts[i - 1][0], dy = s.pts[i][1] - s.pts[i - 1][1], L = Math.hypot(dx, dy);
        if (L < 0.06) continue;                                     // 很短的線段受量化影響較大
        let a = ((Math.atan2(dy, dx) * 180 / Math.PI) % 30 + 30) % 30; a = Math.min(a, 30 - a);
        const tol = Math.atan(0.0042 / L) * 180 / Math.PI + 0.3;          // 量化誤差（約 1/255）造成的角度偏差上限
        assert(a < tol, type + ' segment angle off by ' + a.toFixed(2) + '° (L=' + L.toFixed(3) + ')');
        maxOff = Math.max(maxOff, L > 0.2 ? a : 0);
        segs++;
      }
    }
  }
  console.log('      checked ' + segs + ' crystal segments: all at multiples of 30° within quantization; max deviation on segments >0.2 long: ' + maxOff.toFixed(2) + '°');
});

/* ---------- 手繪引導 ---------- */
const wobble = (rand, f, n, amp) => Array.from({ length: n || 50 }, (_, i) => {
  const t = i / ((n || 50) - 1), p = f(t), a = amp == null ? 0.012 : amp;
  return [p[0] + (rand() - 0.5) * a + Math.sin(t * 19) * a * 0.7, p[1] + (rand() - 0.5) * a + Math.cos(t * 13) * a * 0.5];
});
const ang = (u) => Math.atan2(u[1], u[0]);
const lineAngleDeg = (a, b) => { let d = Math.abs(a - b) * 180 / Math.PI % 180; return Math.min(d, 180 - d); };
/* 驗證一個引導出的元素：直線／六角形、角度是 30° 倍數、分枝貼在母線上且夾 60° */
function checkElem(el, before) {
  assert(el.t === 's' || el.t === 'h', 'element type');
  assert(Number.isInteger(el.d) && el.d >= 0 && el.d < 12, 'direction is a multiple of 30°');
  const line = Core.elemLine(el);
  if (el.t === 'h') { assert.strictEqual(line.pts.length, 7); return; }
  assert.strictEqual(line.pts.length, 2, 'one straight segment, never a polyline');
  const [a, b] = line.pts;
  assert(Math.hypot(b[0], b[1]) <= 0.975 && Math.hypot(a[0], a[1]) <= 0.975, 'inside circle ' + el.rule + ' ' + JSON.stringify([a, b]));
  assert(el.l >= Math.round(Core.MIN_LEN * 64), 'minimum length');
  if (el.rule === 'arm' || el.rule === 'axis') {
    assert(el.d % 2 === 0, 'arms lie on the 6 arm axes');
    if (el.rule === 'arm') assert(Math.hypot(a[0], a[1]) < 0.003, 'arm starts at the center');
    else assert(Math.abs(a[0] * Math.sin(el.d * Math.PI / 6) - a[1] * Math.cos(el.d * Math.PI / 6)) < 0.003, 'axis segment lies on an arm axis');
  }
  if (el.rule === 'branch' || el.rule === 'extend') {
    const segs = Core.expandSegs(before).filter(g => !g.hex);
    let best = null;
    for (const g of segs) {
      const dx = g.b[0] - g.a[0], dy = g.b[1] - g.a[1], L2 = dx * dx + dy * dy;
      const t = Math.max(0, Math.min(1, ((a[0] - g.a[0]) * dx + (a[1] - g.a[1]) * dy) / L2));
      const d = Math.hypot(a[0] - g.a[0] - dx * t, a[1] - g.a[1] - dy * t);
      if (!best || d < best.d - 1e-9) best = { d, g };
    }
    assert(best && best.d < 0.006, el.rule + ' starts on an existing line (off by ' + (best && best.d.toFixed(4)) + ')');
    const pa = lineAngleDeg(ang([best.g.b[0] - best.g.a[0], best.g.b[1] - best.g.a[1]]), el.d * Math.PI / 6);
    // 母線若也是 30° 倍數，分枝夾角應恰為 60°（延長則 0°）；找出所有貼著的母線中最符合的那條
    const ok = segs.some(g => {
      const dx = g.b[0] - g.a[0], dy = g.b[1] - g.a[1], L2 = dx * dx + dy * dy;
      const t = Math.max(0, Math.min(1, ((a[0] - g.a[0]) * dx + (a[1] - g.a[1]) * dy) / L2));
      if (Math.hypot(a[0] - g.a[0] - dx * t, a[1] - g.a[1] - dy * t) > 0.006) return false;
      const snapped = Math.round(ang([dx, dy]) / (Math.PI / 6)) * Math.PI / 6;     // 母線本身的方向（對齊到 30° 格，結晶線段有量化誤差）
      const x = lineAngleDeg(snapped, el.d * Math.PI / 6);
      return el.rule === 'branch' ? Math.abs(x - 60) < 1e-6 : x < 1e-6;
    });
    assert(ok, el.rule + ' angle to parent ' + pa.toFixed(1));
    const out = (b[0] - a[0]) * a[0] + (b[1] - a[1]) * a[1];
    assert(out > -1e-6, 'branch points outward');
  }
}
function guided(strokes, raws, w) {
  const out = [];
  for (const raw of raws) {
    const before = Core.toFloat(strokes, 4);
    const el = Core.interpret(raw, before, w == null ? 1 : w);
    out.push(el);
    if (el) { checkElem(el, before); delete el.rule; strokes.push(el); }
  }
  return out;
}

test('guided drawing: wobbly/curved strokes become straight crystal segments', () => {
  const rand = Core.mulberry32(11), st = [];
  const [arm, br1, br2] = guided(st, [
    wobble(rand, t => [0.03 + 0.86 * t, 0.12 * Math.sin(t * 3.5)]),             // 彎彎的主枝
    wobble(rand, t => [0.42 + 0.22 * t, 0.02 + 0.3 * t + 0.06 * Math.sin(t * 7)]),  // 抖動的分枝
    wobble(rand, t => [0.6 + 0.14 * t, -0.03 - 0.22 * t])                         // 另一側分枝
  ]);
  const bp = Core.elemLine(st[1]).pts, bm = [bp[0][0] + (bp[1][0] - bp[0][0]) * 0.55, bp[0][1] + (bp[1][1] - bp[0][1]) * 0.55];
  const [sub, plate, tip, tap, winding] = guided(st, [
    wobble(rand, t => [bm[0] + 0.15 * t, bm[1] + 0.01 * t]),                     // 從分枝上再分枝
    wobble(rand, t => [0.28 + 0.03 * Math.sin(t * 6), -0.16 + 0.32 * t]),         // 橫越主枝 → 六角板
    wobble(rand, t => [0.84, -0.06 + 0.12 * t], 20, 0.006),                        // 橫越尖端 → 六角小板
    [[0.3, 0.7]],                                                                 // 空白處點一下 → 忽略
    wobble(rand, t => [-0.1 - 0.75 * t, 0.15 * Math.sin(t * Math.PI * 3)], 120, 0.03)  // 長而彎曲 → 仍只有一條直線
  ]);
  assert.strictEqual(arm.rule, undefined); // rule 已在 guided() 裡移除
  const kinds = st.map(e => e.t + e.d);
  assert(st[0].t === 's' && st[0].d === 0 && Math.abs(st[0].l / 64 - 0.86) < 0.06, 'arm length = projected length ' + st[0].l / 64);
  assert(br1 && br1.d === 2, 'branch at +60°'); assert(br2 && br2.d === 10, 'branch at -60°');
  assert(sub && (sub.d === 0 || sub.d === 4), 'sub-branch off a branch at ±60° to it (got ' + (sub && sub.d) + ')');
  assert(plate && plate.t === 'h' && Math.abs(plate.x - 255) <= 0 && plate.d % 2 === 1, 'across main arm → centered hexagonal plate');
  assert(tip && tip.t === 'h' && tip.d === 0 && tip.x > 255, 'across arm tip → small hexagon tip');
  assert.strictEqual(tap, null, 'tap in empty space ignored');
  assert(winding && winding.t === 's', 'long winding stroke → single straight segment');
  const enc = Core.encode({ strokes: st, beautify: false });
  const d = Core.decode(enc);
  assert.strictEqual(d.v, 4);
  assert.deepStrictEqual(d.strokes.map(x => JSON.stringify(x, Object.keys(x).sort())), st.map(x => JSON.stringify(x, Object.keys(x).sort())));
  console.log('      guided flake of ' + st.length + ' elements (' + kinds.join(' ') + ') -> #c= length ' + hashLen(enc));
});

test('guided drawing fuzz: 3000 random wobbly strokes always give valid crystal geometry', () => {
  const rand = Core.mulberry32(2024);
  let made = 0, nulls = 0; const rules = {}; const lens = [];
  for (let k = 0; k < 150; k++) {
    const st = rand() < 0.3 ? Core.randomFlake(rand) : [];
    for (let i = 0; i < 20; i++) {
      const s = [(rand() - 0.5) * 1.8, (rand() - 0.5) * 1.8], a = rand() * 6.28, L = rand() * 0.8, bend = (rand() - 0.5) * 3;
      const raw = wobble(rand, t => [s[0] + Math.cos(a + bend * t) * L * t, s[1] + Math.sin(a + bend * t) * L * t], 10 + Math.floor(rand() * 80), rand() * 0.04);
      if (rand() < 0.25 && st.length) { const ls = Core.toFloat(st, 4).filter(l => !l.hex); const l = ls[Math.floor(rand() * ls.length)]; const q = l.pts[0]; raw[0] = [q[0], q[1]]; }
      const before = Core.toFloat(st, 4);
      const el = Core.interpret(raw, before, Math.floor(rand() * 3));
      if (!el) { nulls++; continue; }
      checkElem(el, before);
      rules[el.rule] = (rules[el.rule] || 0) + 1; delete el.rule;
      st.push(el); made++;
    }
    if (st.length) { const enc = Core.encode({ strokes: st, beautify: rand() < 0.5 }); Core.decode(enc); lens.push(hashLen(enc)); }
  }
  console.log('      ' + made + ' elements valid, ' + nulls + ' ignored; rules ' + JSON.stringify(rules));
});

test('beautify (v4) on guided arms: parallel ±60° side branches + hex tip', () => {
  const st = [{ t: 's', w: 1, x: 255, y: 255, d: 0, l: 56 }];
  const g = Core.decorate(Core.toFloat(st, 4), true, 4);
  const extra = g.lines.filter(l => !(l.pts.length === 2 && l.pts[0][0] === 0 && l.pts[0][1] === 0));
  const branches = extra.filter(l => l.pts.length === 2), hexes = extra.filter(l => l.pts.length === 7);
  assert(branches.length === 4, 'two branch pairs');
  const dirs = branches.map(l => Math.atan2(l.pts[1][1] - l.pts[0][1], l.pts[1][0] - l.pts[0][0]) * 180 / Math.PI);
  assert(dirs.every(d => Math.abs(Math.abs(d) - 60) < 1e-6), 'all side branches at ±60° (parallel per side): ' + dirs);
  assert(hexes.length === 2, 'hex tip + center hex');
  const g2 = Core.decorate(Core.toFloat(st.concat([{ t: 's', w: 1, x: 357, y: 255, d: 2, l: 15 }]), 4), true, 4);
  assert(g2.lines.length === g.lines.length + 1, 'short branches are not decorated further');
});

test('hand-drawn-like snowflakes: round trip x500, budget respected', () => {
  const rand = Core.mulberry32(999);
  const lens = [];
  for (let i = 0; i < 500; i++) {
    const strokes = fakeHandDrawn(rand);
    const total = strokes.reduce((n, s) => n + s.q.length, 0);
    assert(total <= 220, 'budget ' + total);
    strokes.forEach(s => assert(s.q.length <= Core.MAX_PTS_STROKE));
    const card = cardOf(strokes, rand);
    const enc = Core.encode(card);
    same(card, Core.decode(enc));
    lens.push(hashLen(enc));
  }
  console.log('      hand-drawn    #c= length', JSON.stringify(stats(lens)));
});

test('typical card (6 hand-drawn curves) is short', () => {
  const rand = Core.mulberry32(7);
  const strokes = [];
  for (let k = 0; k < 6; k++) {
    const raw = []; let x = 0.05 + rand() * 0.1, y = 0, a = rand() * 0.5;
    for (let i = 0; i < 70; i++) { a += (rand() - 0.5) * 0.2; x += Math.cos(a) * 0.011; y += Math.sin(a) * 0.011; raw.push([x, y]); }
    strokes.push(Core.makeStroke(raw, 1));
  }
  Core.fitStrokes(strokes, 220);
  const enc = Core.encode({ strokes, beautify: true });
  console.log('      typical 6-curve card #c= length', hashLen(enc), ' points', strokes.reduce((n, s) => n + s.q.length, 0));
  assert(hashLen(enc) < 200);
});

test('worst case: 63 long strokes still encodes, budget holds', () => {
  const rand = Core.mulberry32(42);
  const strokes = [];
  for (let k = 0; k < 63; k++) {
    const raw = []; let x = rand() - 0.5, y = rand() - 0.5, a = rand() * 6;
    for (let i = 0; i < 300; i++) { a += (rand() - 0.5) * 0.9; x += Math.cos(a) * 0.01; y += Math.sin(a) * 0.01; raw.push([x, y]); }
    strokes.push(Core.makeStroke(raw, 2));
  }
  const r = Core.fitStrokes(strokes, 220);
  assert(r.total <= 220, 'total ' + r.total);
  const card = { strokes: strokes.map(s => ({ w: s.w, m: s.m, q: s.q })), beautify: false };
  const enc = Core.encode(card);
  same(card, Core.decode(enc));
  console.log('      worst-case    #c= length', hashLen(enc));
});

test('new links contain no text fields; extra card properties are ignored', () => {
  const s = Core.randomFlake(Core.mulberry32(1));
  const a = Core.encode({ strokes: s, beautify: true });
  const b = Core.encode({ strokes: s, beautify: true, to: '媽媽', msg: '聖誕快樂', from: '小明' });
  assert.strictEqual(a, b);
  const d = Core.decode(a);
  assert.deepStrictEqual(Object.keys(d).sort(), ['beautify', 'strokes', 'v']);
  assert.strictEqual(d.v, 4);
});

test('legacy v1, v2 and v3 links decode and render exactly as before', () => {
  const close = (a, b) => Math.abs(a - b) < 1e-12;
  for (const f of legacy.concat(legacy2, legacy3)) {
    const d = Core.decode(f.hash);
    assert.strictEqual(d.v, f.v);
    assert.strictEqual(d.beautify, f.beautify);
    assert.deepStrictEqual(d.strokes.map(s => ({ w: s.w, q: s.q })), f.strokes.map(s => ({ w: s.w, q: s.q })));
    if (f.v < 3) assert(d.strokes.every(s => s.m === true), 'v1/v2 strokes are mirrored');
    const g = Core.decorate(Core.toFloat(d.strokes, d.v), d.beautify, d.v);
    assert.strictEqual(g.lines.length, f.geo.lines.length);
    g.lines.forEach((l, i) => {
      const o = f.geo.lines[i];
      assert(close(l.lw, o.lw) && l.m === (o.m === undefined ? true : o.m) && l.pts.length === o.pts.length, 'line ' + i);
      l.pts.forEach((p, j) => assert(close(p[0], o.pts[j][0]) && close(p[1], o.pts[j][1]), 'pt'));
    });
    assert.strictEqual(g.tips.length, f.geo.tips.length);
    g.tips.forEach((t, i) => { const o = f.geo.tips[i], op = o.p || o; assert(close(t.p[0], op[0]) && close(t.p[1], op[1])); });
    console.log('      legacy v' + f.v + ' ' + String(f.hash.length + 3).padStart(3) + ' chars: identical geometry (' + g.lines.length + ' lines)  ->  re-encoded v3 ' + (Core.encode(d).length + 3) + ' chars');
  }
});

test('encode rejects empty snowflake', () => {
  assert.throws(() => Core.encode({ strokes: [] }));
});

test('corrupt / truncated / garbage inputs throw (never return junk)', () => {
  const rand = Core.mulberry32(5);
  const goods = [Core.encode(cardOf(Core.randomFlake(rand), rand)), legacy[1].hash, legacy2[4].hash, legacy3[0].hash, Core.encode({ strokes: [{ t: 's', w: 1, x: 255, y: 255, d: 0, l: 50 }, { t: 's', w: 0, x: 350, y: 255, d: 2, l: 20 }, { t: 'h', w: 0, x: 255, y: 255, r: 40, d: 1 }] }), (() => { const h = Core.makeStroke(Array.from({ length: 30 }, (_, i) => [Math.cos(i / 5) * 0.6, Math.sin(i / 5) * 0.6]), 1); Core.fitStrokes([h], 220); return Core.encode({ strokes: [h] }); })()];
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  const bad = ['', 'abc', '!!!!', 'A'.repeat(5000), '%E5%A5%BD'];
  for (const good of goods) {
    bad.push(good.slice(0, -1), good.slice(0, -5), good.slice(0, good.length >> 1), good + 'A', good + 'AAAA');
    for (let i = 0; i < 200; i++) {
      const pos = Math.floor(rand() * good.length), ch = alphabet[Math.floor(rand() * 64)];
      if (ch !== good[pos]) bad.push(good.slice(0, pos) + ch + good.slice(pos + 1));
    }
  }
  let detected = 0;
  for (const b of bad) { try { const d = Core.decode(b); assert(d.strokes.length >= 1); } catch (e) { detected++; } }
  console.log('      corrupt inputs rejected: ' + detected + '/' + bad.length + ' (any others still decode to a valid snowflake)');
  assert(detected >= bad.length * 0.97);
  for (const b of ['', 'abc', '!!!!', goods[0].slice(0, -1), goods[0] + 'A', 'A'.repeat(5000)]) assert.throws(() => Core.decode(b));
});

test('decorate (beautify) adds side branches and tips', () => {
  const fl = Core.toFloat(Core.randomFlake(Core.mulberry32(3), 'dendrite'), 3);
  const a = Core.decorate(fl, false, 3), b = Core.decorate(fl, true, 3);
  assert(b.lines.length > a.lines.length);
  assert(b.tips.length > a.tips.length);
});

console.log(passed + ' tests passed' + (process.exitCode ? ' (with failures)' : ''));
