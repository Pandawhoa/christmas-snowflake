"""End-to-end 測試（Playwright + Chromium，模擬手機觸控）
執行：python3 tests/e2e.py
會在 screenshots/ 產生截圖。
"""
import http.server, threading, functools, os, sys, math, time, json
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, 'screenshots')
os.makedirs(SHOTS, exist_ok=True)
LEGACY = json.load(open(os.path.join(ROOT, 'tests', 'fixtures-v1.json')))

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d/index.html' % srv.server_address[1]

failures = []
def check(cond, msg):
    print(('  ok   ' if cond else '  FAIL ') + msg)
    if not cond: failures.append(msg)

def watch(page, bag):
    page.on('console', lambda m: bag.append('console.%s: %s' % (m.type, m.text)) if m.type in ('error', 'warning') else None)
    page.on('pageerror', lambda e: bag.append('pageerror: %s' % e))

def touch_stroke(cdp, pts, delay=0.008):
    tp = lambda p: [{'x': p[0], 'y': p[1], 'id': 1, 'radiusX': 4, 'radiusY': 4, 'force': 1}]
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': tp(pts[0])})
    for p in pts[1:]:
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': tp(p)})
        time.sleep(delay)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})

def pad_center(page):
    b = page.locator('#pad').bounding_box()
    return b['x'] + b['width'] / 2, b['y'] + b['height'] / 2, b['width'] / 2 * 0.93

UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Safari Line/13.20.0'
MOBILE = dict(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True, user_agent=UA, locale='zh-TW')

def layout_check(pg, label):
    """雪花（含光暈與跳躍最高點）不得碰到標題；也不得壓到小木屋（水平重疊時）或地面"""
    d = pg.evaluate('window.__snowflake.Scene.debug()')
    tb = pg.evaluate("(() => { const r = document.getElementById('xmasTitle').getBoundingClientRect(); return r.bottom - 10 * 0; })()")
    # 標題 fade 動畫結束後 transform 為 none，用 offset 量測較準
    tb2 = pg.evaluate("(() => { const e = document.getElementById('xmasTitle'); return e.offsetTop + e.offsetHeight; })()")
    peak_top = d['cy'] - d['up'] * d['R']
    ok_title = peak_top >= max(tb, tb2) + 1
    horiz_overlap = d['cx'] + d['down'] * d['R'] > d['cabinLeft']
    limit = d['cabinTop'] if horiz_overlap else d['groundY']
    bottom = d['cy'] + d['down'] * d['R']
    check(ok_title, '%s: flake peak top %.0f below title bottom %.0f' % (label, peak_top, max(tb, tb2)))
    check(bottom <= limit, '%s: flake bottom %.0f above %s %.0f' % (label, bottom, 'cabin top' if horiz_overlap else 'ground', limit))
    space_mid = (max(tb, tb2) + limit) / 2
    print('       %s: viewport %dx%d  R=%.0f  center y=%.0f  (mid of free space %.0f)' % (label, d['W'], d['H'], d['R'], d['cy'], space_mid))
    return d

def peak_shot(pg, name):
    pg.evaluate('window.__snowflake.Scene.freezeFlake(0.8)')     # 跳躍最高點
    pg.wait_for_timeout(250)
    pg.screenshot(path=os.path.join(SHOTS, name))
    pg.evaluate('window.__snowflake.Scene.freezeFlake(null)')

with sync_playwright() as p:
    browser = p.chromium.launch(args=['--autoplay-policy=user-gesture-required'])
    ctx = browser.new_context(**MOBILE)
    page = ctx.new_page()
    errs = []
    watch(page, errs)

    print('[1] 設計模式載入')
    page.goto(BASE)
    page.wait_for_timeout(900)
    check(page.locator('#designer').is_visible(), 'designer visible')
    check(page.locator('#card').is_hidden(), 'card hidden')
    check(page.locator('#inTo').count() == 0 and page.locator('#inMsg').count() == 0 and page.locator('.chip').count() == 0, 'message form removed')
    check(page.locator('#greet').count() == 0, 'greeting panel removed')

    print('[2] 手繪引導：故意抖動、彎曲的筆畫 → 對齊成直線冰晶（每一筆 6 份旋轉，不鏡射）')
    cdp = ctx.new_cdp_session(page)
    cx, cy, R = pad_center(page)
    import random
    rng = random.Random(7)
    def W(f, n=36, amp=0.02):
        out = []
        for i in range(n):
            t = i / (n - 1); x, y = f(t)
            out.append((cx + R * (x + (rng.random() - 0.5) * amp + math.sin(t * 17) * amp * 0.6), cy - R * (y + (rng.random() - 0.5) * amp)))
        return out
    strokes = [
        W(lambda t: (0.03 + 0.86 * t, 0.12 * math.sin(t * 3.4))),                    # 彎彎曲曲的主枝
        W(lambda t: (0.36 + 0.2 * t, 0.02 + 0.3 * t + 0.05 * math.sin(t * 8))),       # 抖動的分枝（上）
        W(lambda t: (0.6 + 0.16 * t, -0.02 - 0.22 * t + 0.03 * math.sin(t * 9))),     # 分枝（下）
        W(lambda t: (0.22 + 0.02 * math.sin(t * 7), -0.13 + 0.26 * t), 24),           # 橫越主枝 → 六角板
        W(lambda t: (0.85 + 0.01 * math.sin(t * 5), -0.06 + 0.12 * t), 16, 0.008),    # 橫越尖端 → 六角小板
    ]
    for st in strokes:
        touch_stroke(cdp, st)
        page.wait_for_timeout(120)
    # 從上面那條分枝的中間再長出次分枝，畫到一半時截圖（淡淡筆跡＋金色對齊預覽）
    br = page.evaluate('''() => { const s = window.__snowflake.D.strokes[1]; const p = window.__snowflake.Core.elemLine(s).pts; return [(p[0][0] + p[1][0]) / 2, (p[0][1] + p[1][1]) / 2]; }''')
    mid_raw = [(cx + R * (br[0] + 0.2 * t + 0.02 * math.sin(t * 9)), cy + R * (br[1] - 0.01 * t + 0.055 * math.sin(t * 10))) for t in [i / 30 for i in range(31)]]
    tp = lambda p: [{'x': p[0], 'y': p[1], 'id': 1, 'radiusX': 4, 'radiusY': 4, 'force': 1}]
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': tp(mid_raw[0])})
    for pnt in mid_raw[1:22]:
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': tp(pnt)}); time.sleep(0.01)
    page.wait_for_timeout(120)
    page.screenshot(path=os.path.join(SHOTS, 'designer-drawing.png'))
    for pnt in mid_raw[22:]:
        cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': tp(pnt)}); time.sleep(0.01)
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
    page.wait_for_timeout(700)
    n = page.evaluate('window.__snowflake.D.strokes.length')
    check(n == 6, 'six guided elements committed (got %s)' % n)
    info = page.evaluate('''() => {
      const { Core, D } = window.__snowflake; const res = [];
      D.strokes.forEach((el, i) => {
        const line = Core.elemLine(el), before = Core.toFloat(D.strokes.slice(0, i), 4);
        const segs = Core.expandSegs(before).filter(g => !g.hex);
        const a = line.pts[0];
        let attach = null, angle = null;
        for (const g of segs) {
          const dx = g.b[0] - g.a[0], dy = g.b[1] - g.a[1], L2 = dx * dx + dy * dy;
          const t = Math.max(0, Math.min(1, ((a[0] - g.a[0]) * dx + (a[1] - g.a[1]) * dy) / L2));
          const d = Math.hypot(a[0] - g.a[0] - dx * t, a[1] - g.a[1] - dy * t);
          if (attach === null || d < attach) { attach = d; let x = Math.abs(Math.atan2(dy, dx) - el.d * Math.PI / 6) * 180 / Math.PI % 180; angle = Math.min(x, 180 - x); }
        }
        res.push({ t: el.t, d: el.d, pts: line.pts.length, r0: Math.hypot(a[0], a[1]), attach, angle });
      });
      return res; }''')
    print('       elements: ' + ', '.join('%s d=%d%s' % (e['t'], e['d'] * 30, (' on parent, %.0f°' % e['angle']) if e['t'] == 's' and e['r0'] > 0.01 else '') for e in info))
    check(all(e['t'] in ('s', 'h') for e in info), 'only straight segments / hexagons (no freeform polylines)')
    check(all(e['pts'] == 2 for e in info if e['t'] == 's'), 'each segment is exactly one straight line')
    check(info[0]['t'] == 's' and info[0]['d'] % 2 == 0 and info[0]['r0'] < 0.003, 'wobbly stroke from center → straight arm on an arm axis')
    check(info[1]['t'] == 's' and info[1]['attach'] < 0.006 and abs(info[1]['angle'] - 60) < 1e-6, 'wobbly branch starts on the arm at exactly 60°')
    check(info[2]['t'] == 's' and info[2]['attach'] < 0.006 and abs(info[2]['angle'] - 60) < 1e-6, 'second branch starts on the arm at exactly 60°')
    check(info[3]['t'] == 'h', 'stroke across the arm → hexagonal plate')
    check(info[4]['t'] == 'h', 'stroke across the arm tip → small hexagon tip')
    check(info[5]['t'] == 's' and info[5]['attach'] < 0.006 and abs(info[5]['angle'] - 60) < 1e-6, 'sub-branch starts on the branch at exactly 60°')
    check(page.evaluate('window.scrollY') == 0, 'page did not scroll while drawing')
    page.evaluate('window.scrollTo(0,0)'); page.wait_for_timeout(2600)
    page.screenshot(path=os.path.join(SHOTS, 'designer.png'))
    hand_card = page.evaluate('''() => { const D = window.__snowflake.D; return window.__snowflake.Core.encode({ strokes: D.strokes, beautify: false }); }''')
    print('       guided hand-drawn flake (6 elements) hash length: %d' % (len(hand_card) + 3))
    touch_stroke(cdp, [(cx + R * 0.5, cy - R * 0.62), (cx + R * 0.51, cy - R * 0.62)])     # 空白處點一下 → 忽略
    page.wait_for_timeout(150)
    check(page.evaluate('window.__snowflake.D.strokes.length') == 6, 'tap in empty space is ignored')

    print('[2b] 隨機生成：各種真實冰晶型態')
    pb = page.locator('.pad-wrap').bounding_box()
    gen_types = ['dendrite', 'fern', 'sectored', 'stellarPlate', 'hexPlate', 'dendrite']
    gen_lens = []
    page.evaluate('''() => { const C = window.__snowflake.Core; C.__orig = C.__orig || C.randomFlake; }''')
    for i, t in enumerate(gen_types):
        page.evaluate('''([t, seed]) => { const C = window.__snowflake.Core; C.randomFlake = () => C.__orig(C.mulberry32(seed), t); }''', [t, 31 + i * 17])
        page.click('#btnRandom'); page.wait_for_timeout(150)
        if i == 5:
            page.click('#btnBeautify'); page.wait_for_timeout(150)
        page.evaluate('window.scrollTo(0,0)'); page.wait_for_timeout(300)
        page.screenshot(path=os.path.join(SHOTS, 'gen-%d.png' % (i + 1)), clip={'x': 0, 'y': pb['y'] - 6, 'width': 390, 'height': pb['height'] + 12})
        enc = page.evaluate('''() => { const D = window.__snowflake.D; return window.__snowflake.Core.encode({ strokes: D.strokes.map(s => s.t ? s : ({ w: s.w, m: s.m, q: s.q })), beautify: D.beautify }); }''')
        gen_lens.append((t + (' +美化' if i == 5 else ''), len(enc) + 3))
        check(page.evaluate('window.__snowflake.D.strokes.every(s => s.m === true)'), 'generated %s strokes are mirrored crystal strokes' % t)
        if i == 5:
            gen_card = enc
            page.click('#btnBeautify'); page.wait_for_timeout(100)
    page.evaluate('''() => { const C = window.__snowflake.Core; C.randomFlake = C.__orig; }''')
    print('       generated hash lengths: %s' % gen_lens)
    for _ in range(8): page.click('#btnUndo')   # 6 次生成 + 2 次美化切換
    page.wait_for_timeout(150)
    check(page.evaluate('window.__snowflake.D.strokes.length') == 6 and page.evaluate('window.__snowflake.D.strokes.every(s => s.t)'), 'undo back to the hand-guided flake')

    print('[3] 復原 / 隨機 / 美化 / 清除')
    page.click('#btnUndo'); page.wait_for_timeout(100)
    check(page.evaluate('window.__snowflake.D.strokes.length') == 5, 'undo removes last element')
    touch_stroke(cdp, mid_raw); page.wait_for_timeout(150)
    check(page.evaluate('window.__snowflake.D.strokes.length') == 6, 'redraw sub-branch')
    page.click('#btnBeautify'); page.wait_for_timeout(100)
    check(page.get_attribute('#btnBeautify', 'aria-pressed') == 'true', 'beautify toggled on')
    page.click('#btnClear'); page.wait_for_timeout(100)
    check(page.evaluate('window.__snowflake.D.strokes.length') == 0, 'clear empties')

    print('[4] 沒有雪花時不能送出；只需雪花即可送出')
    page.click('#btnMake'); page.wait_for_timeout(200)
    check(page.locator('#sheet').is_hidden() and '雪花' in page.inner_text('#toast'), 'make blocked without snowflake')
    page.click('#btnUndo'); page.wait_for_timeout(100)
    check(page.evaluate('window.__snowflake.D.strokes.length') == 6, 'undo restores after clear')
    page.click('#btnRandom'); page.wait_for_timeout(100)
    check(page.evaluate('window.__snowflake.D.strokes.length') > 0, 'random generates strokes')
    page.click('#btnUndo'); page.wait_for_timeout(100)
    check(page.evaluate('window.__snowflake.D.strokes.length') == 6, 'undo reverts random')
    page.evaluate('window.scrollTo(0,0)'); page.wait_for_timeout(600)
    page.screenshot(path=os.path.join(SHOTS, 'designer-beautified.png'))

    print('[5] 預覽與返回')
    page.click('#btnPreview'); page.wait_for_timeout(2500)
    check(page.locator('#card').is_visible() and page.locator('#backEdit').is_visible() and page.locator('#makeOwn').is_hidden(), 'preview shows card + 返回編輯')
    page.click('#backEdit'); page.wait_for_timeout(300)
    check(page.locator('#designer').is_visible() and page.evaluate('window.__snowflake.D.strokes.length') == 6, 'back to designer, state kept')

    print('[6] 產生連結')
    page.click('#btnMake'); page.wait_for_timeout(300)
    check(page.locator('#sheet').is_visible(), 'share sheet visible with only a snowflake')
    link = page.input_value('#linkOut')
    check('#c=' in link, 'link has #c=')
    print('       guided flake (6 elements, beautified) link hash length: %d' % (len(link.split('#', 1)[1]) + 1))
    check(link.split('#c=')[1][:1] in 'QRST', 'new links use format v4')
    check(page.get_attribute('#btnLine', 'href').startswith('https://line.me/R/share?text='), 'LINE share href')
    page.click('#btnCopy'); page.wait_for_timeout(300)
    check(('已複製' in page.inner_text('#toast')) or ('手動複製' in page.inner_text('#toast')), 'copy gives feedback')
    page.screenshot(path=os.path.join(SHOTS, 'share-sheet.png'))
    page.click('#btnCloseSheet')
    rl = []
    for i in range(5):
        page.click('#btnRandom'); page.click('#btnMake'); page.wait_for_timeout(120)
        rl.append(len(page.input_value('#linkOut').split('#', 1)[1]) + 1)
        page.click('#btnCloseSheet')
    print('       random-flake link hash lengths: %s' % rl)
    check(not errs, 'designer: no console errors ' + json.dumps(errs, ensure_ascii=False))

    print('[7] 收件人開啟卡片 (390x844)')
    ctx2 = browser.new_context(**MOBILE)
    pg = ctx2.new_page(); errs2 = []; watch(pg, errs2)
    pg.goto(link)
    pg.wait_for_timeout(600)
    check(pg.locator('#card').is_visible() and pg.locator('#designer').is_hidden(), 'card mode on link')
    pg.wait_for_timeout(2600)
    layout_check(pg, 'iPhone 390x844')
    pg.screenshot(path=os.path.join(SHOTS, 'card.png'))
    peak_shot(pg, 'card-peak.png')
    check('idle' in pg.get_attribute('#sound', 'class'), 'speaker idle before touch')
    pg.touchscreen.tap(200, 760)
    pg.wait_for_timeout(500)
    st = pg.evaluate('window.__snowflake.Music.state'); cs = pg.evaluate('window.__snowflake.Music.ctxState')
    print('       music state after tap: %s, AudioContext: %s' % (st, cs))
    check(st == 'playing', 'music playing after first tap')
    pg.click('#sound'); pg.wait_for_timeout(300)
    check(pg.evaluate('window.__snowflake.Music.state') == 'muted', 'speaker mutes')
    pg.click('#sound'); pg.wait_for_timeout(300)
    check(pg.evaluate('window.__snowflake.Music.state') == 'playing', 'speaker unmutes')
    cdp2 = ctx2.new_cdp_session(pg)
    touch_stroke(cdp2, [(40 + i * 15, 300 + i * 4) for i in range(22)], 0.016)
    pg.wait_for_timeout(300)
    # 雪橇經過月亮時截圖；兩個時間點的麋鹿腿部應不同（奔跑動畫）
    d = pg.evaluate('window.__snowflake.Scene.debug()')
    wait = (d['sleighMoonAt'] - d['sinceCard']) * 1000
    if wait > 0: pg.wait_for_timeout(int(wait))
    pg.screenshot(path=os.path.join(SHOTS, 'card-sleigh.png'))
    mo = d['moon']
    clip = {'x': max(0, mo['x'] - 150), 'y': max(0, mo['y'] - 70), 'width': min(300, d['W'] - max(0, mo['x'] - 150)), 'height': 140}
    a = pg.screenshot(clip=clip); pg.wait_for_timeout(110); b = pg.screenshot(clip=clip)
    open(os.path.join(SHOTS, 'sleigh-frame-a.png'), 'wb').write(a); open(os.path.join(SHOTS, 'sleigh-frame-b.png'), 'wb').write(b)
    check(a != b, 'sleigh crop changes between frames (gallop animation)')
    check(not errs2, 'card: no console errors ' + json.dumps(errs2, ensure_ascii=False))
    pg.click('#makeOwn'); pg.wait_for_timeout(800)
    check(pg.locator('#designer').is_visible() and '#c=' not in pg.url, '我也做一片送人 → designer')

    pgc = ctx2.new_page(); errsc = []; watch(pgc, errsc)
    pgc.goto(BASE + '#c=' + gen_card); pgc.wait_for_timeout(3200)
    pgc.screenshot(path=os.path.join(SHOTS, 'card-crystal.png'))
    check(not errsc, 'crystal card: no console errors')

    print('[8] 舊版連結（v1 含文字、v2）仍可開啟，畫面與以前相同')
    LEGACY.extend(json.load(open(os.path.join(ROOT, 'tests', 'fixtures-v2.json'))))
    LEGACY.extend(json.load(open(os.path.join(ROOT, 'tests', 'fixtures-v3.json'))))
    pg2 = ctx2.new_page(); errs3 = []; watch(pg2, errs3)
    for i, f in enumerate(LEGACY):
        pg2.goto(BASE + '#c=' + f['hash']); pg2.wait_for_timeout(500)
        q = pg2.evaluate('window.__snowflake.Scene.debug().R')
        check(pg2.locator('#card').is_visible() and pg2.locator('#errorBox').is_hidden(), 'legacy v%d link %d opens as card' % (f['v'], i))
        check('媽媽' not in pg2.inner_text('body'), 'legacy link %d shows no greeting text' % i)
    pg2.goto(BASE + '#c=' + LEGACY[-1]['hash']); pg2.wait_for_timeout(2800)
    pg2.screenshot(path=os.path.join(SHOTS, 'card-legacy.png'))

    print('[9] 毀損連結 / ?c= / 短碼未設定')
    pg2.goto(link[:-6]); pg2.wait_for_timeout(500)
    check(pg2.locator('#errorBox').is_visible() and '打不開' in pg2.inner_text('#errorBox'), 'truncated link → friendly zh-TW error')
    pg2.screenshot(path=os.path.join(SHOTS, 'error.png'))
    pg2.click('#errorMake'); pg2.wait_for_timeout(600)
    check(pg2.locator('#designer').is_visible(), 'error → make own')
    pg2.goto(BASE + '?c=' + link.split('#c=')[1]); pg2.wait_for_timeout(500)
    check(pg2.locator('#card').is_visible(), '?c= query accepted')
    pg2.goto(BASE + '#s=abc'); pg2.wait_for_timeout(400)
    check(pg2.locator('#errorBox').is_visible(), '#s= without storage → friendly error')
    pg2.goto(BASE + '#c=%%%'); pg2.wait_for_timeout(400)
    check(pg2.locator('#errorBox').is_visible(), 'garbage → friendly error')
    check(not errs3, 'legacy/error pages: no console errors ' + json.dumps(errs3, ensure_ascii=False))

    print('[10] 其他尺寸：iPhone SE、橫向、桌面')
    for label, opts, name in [
        ('iPhone SE 375x667', dict(MOBILE, viewport={'width': 375, 'height': 667}), 'card-se'),
        ('landscape 844x390', dict(MOBILE, viewport={'width': 844, 'height': 390}), 'card-landscape'),
        ('desktop 1280x800', dict(viewport={'width': 1280, 'height': 800}, locale='zh-TW'), 'card-desktop'),
        ('small Android 360x640', dict(MOBILE, viewport={'width': 360, 'height': 640}), 'card-360'),
        ('tablet 820x1180', dict(MOBILE, viewport={'width': 820, 'height': 1180}), 'card-tablet'),
    ]:
        c3 = browser.new_context(**opts); p3 = c3.new_page(); e3 = []; watch(p3, e3)
        p3.goto(link); p3.wait_for_timeout(3200)
        layout_check(p3, label)
        p3.screenshot(path=os.path.join(SHOTS, name + '.png'))
        peak_shot(p3, name + '-peak.png')
        check(not e3, label + ': no console errors ' + json.dumps(e3, ensure_ascii=False))
        c3.close()

    print('[11] 旋轉畫面後重新排版')
    c4 = browser.new_context(**MOBILE); p4 = c4.new_page(); e4 = []; watch(p4, e4)
    p4.goto(link); p4.wait_for_timeout(1500)
    p4.set_viewport_size({'width': 844, 'height': 390}); p4.wait_for_timeout(800)
    layout_check(p4, 'rotated to landscape')
    p4.set_viewport_size({'width': 390, 'height': 844}); p4.wait_for_timeout(800)
    layout_check(p4, 'rotated back to portrait')
    check(not e4, 'rotate: no console errors ' + json.dumps(e4, ensure_ascii=False))

    print('[12] 效能（CPU 降速 4 倍模擬舊手機）')
    cdp4 = c4.new_cdp_session(p4)
    cdp4.send('Emulation.setCPUThrottlingRate', {'rate': 4})
    fps = p4.evaluate('''() => new Promise(r => { let n = 0; const t0 = performance.now(); function f() { n++; if (performance.now() - t0 < 3000) requestAnimationFrame(f); else r(n / ((performance.now() - t0) / 1000)); } requestAnimationFrame(f); })''')
    dbg = p4.evaluate('window.__snowflake.Scene.debug()')
    print('       fps at 4x CPU throttle: %.1f, frame work median %.1fms p95 %.1fms (throttled)' % (fps, dbg['frameMedian'], dbg['frameP95']))
    cdp4.send('Emulation.setCPUThrottlingRate', {'rate': 1})
    t0 = time.time(); p4.reload(); p4.wait_for_function('window.__snowflake && window.__snowflake.Scene.isRunning()');
    print('       page load to running scene: %.2fs' % (time.time() - t0))

    print('[13] 桌面滑鼠作畫 / 離線')
    c5 = browser.new_context(viewport={'width': 1280, 'height': 800}, locale='zh-TW'); p5 = c5.new_page(); e5 = []; watch(p5, e5)
    p5.goto(BASE); p5.wait_for_timeout(400)
    b = p5.locator('#pad').bounding_box()
    p5.mouse.move(b['x'] + b['width'] * 0.55, b['y'] + b['height'] * 0.5); p5.mouse.down()
    for i in range(30): p5.mouse.move(b['x'] + b['width'] * (0.55 + i * 0.012), b['y'] + b['height'] * (0.5 - i * 0.006))
    p5.mouse.up()
    check(p5.evaluate('window.__snowflake.D.strokes.length') >= 1, 'mouse drawing works on desktop')
    check(not e5, 'desktop designer: no console errors')
    ctx.set_offline(True)
    page.click('#btnRandom'); page.click('#btnMake'); page.wait_for_timeout(200)
    check(page.locator('#sheet').is_visible(), 'works offline after load')
    ctx.set_offline(False)
    check(not errs, 'final: no console errors ' + json.dumps(errs, ensure_ascii=False))
    print('SAMPLE_LINK_HASH ' + link.split('#', 1)[1])
    browser.close()

srv.shutdown()
print('\n%s' % ('ALL PASSED' if not failures else 'FAILURES: %d' % len(failures)))
sys.exit(1 if failures else 0)
