#!/usr/bin/env python3
"""Red Thread in Safari on an iPhone simulator, with real touches (Appium, XCUITest driver).

For each page: tap the picture and report whether the film plays; with the mode "full" also the tap that only
brings the controls back, captions and fullscreen.
Usage: check.py <simulator udid> <output dir> [name@@url@@selector-of-the-player[@@mode] ...]
Modes: play (default), full, and four for a page that hands the media its address at the first gesture
(mux-video with data-src): auto and metadata set that preload value before the tap; early and early-none set the
address five seconds before it, with preload metadata or none; native asks for the browser's own HLS instead of
hls.js. Pages on 127.0.0.1 are served by lab.py.
Writes results.json and screenshots to the output dir, and prints a summary.
"""
import json, os, subprocess, sys, time

from appium import webdriver
from appium.options.ios import XCUITestOptions

from pagejs import HOOKS, STATE

UDID, OUT = sys.argv[1], sys.argv[2]
PAGES = [(a.split('@@') + ['play'])[:4] for a in sys.argv[3:]] or [
    ['demo', 'https://red-thread-skin.vercel.app/preview.html', 'media-container', 'full'],
]
os.makedirs(OUT, exist_ok=True)

CAL_START = r'''
window.__cal = null;
var o = document.createElement('div');
o.id = '__cal';
o.style.cssText = 'position:fixed;left:0;top:0;right:0;bottom:0;width:100vw;height:100vh;z-index:2147483647;background:transparent;touch-action:none';
var rec = function (ev) { var p = ev.touches && ev.touches.length ? ev.touches[0] : ev; if (!window.__cal) window.__cal = { x: p.clientX, y: p.clientY }; ev.preventDefault(); ev.stopPropagation(); };
o.addEventListener('touchstart', rec, { passive: false, capture: true });
o.addEventListener('pointerdown', rec, true);
['touchend', 'pointerup', 'mousedown', 'mouseup', 'click'].forEach(function (t) { o.addEventListener(t, function (e) { e.preventDefault(); e.stopPropagation(); }, true); });
document.documentElement.appendChild(o);
return true;
'''
CAL_READ = "var o = document.getElementById('__cal'); if (o) o.remove(); return window.__cal;"


def log(*a):
    print(*a, flush=True)


o = XCUITestOptions()
o.platform_name = 'iOS'
o.set_capability('browserName', 'Safari')
o.udid = UDID
o.set_capability('appium:nativeWebTap', False)
o.set_capability('appium:wdaLaunchTimeout', 900000)
o.set_capability('appium:wdaConnectionTimeout', 900000)
o.set_capability('appium:newCommandTimeout', 900)
o.set_capability('appium:safariInitialUrl', 'about:blank')
o.set_capability('appium:webviewConnectTimeout', 120000)
o.set_capability('appium:webviewConnectRetries', 20)
d = None
for attempt in range(3):  # Safari's web inspector is sometimes not up yet on a fresh simulator
    try:
        d = webdriver.Remote('http://127.0.0.1:4723', options=o)
        break
    except Exception as e:
        log('session attempt %d failed: %s' % (attempt + 1, str(e)[:200]))
        time.sleep(20)
if d is None:
    sys.exit('no Safari session')
d.set_script_timeout(30)
d.set_page_load_timeout(90)
W, H = d.execute_script('return [screen.width, screen.height]')
log('screen (points)', W, H)

results = {}


def shot(name):
    subprocess.run(['xcrun', 'simctl', 'io', UDID, 'screenshot', '--type=png', os.path.join(OUT, name + '.png')], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Page:
    def __init__(self, name, url, sel, mode):
        self.name, self.url, self.sel, self.mode, self.cal = name, url, sel, mode, None
        self.steps = []

    def state(self, label):
        s = d.execute_script(STATE, self.sel)
        s['step'] = label
        self.steps.append(s)
        log('  [%s] %s: paused=%s t=%s waiting=%s bar=%s subtitles=%s fullscreen=%s skin=%s view=%sx%s caption=%s err=%s inner=%s hls=%s events=%s errors=%s' % (
            self.name, label, s['paused'], s['t'], s['waiting'], s['topVisible'], s['subtitles'], s['isFullscreen'], s['skin'], s['view']['iw'], s['view']['ih'],
            json.dumps(s['caption']), s['error'], json.dumps(s['inner']), json.dumps(s['hls']), s['events'], s['errors']))
        return s

    def calibrate(self):
        for attempt in range(4):
            d.execute_script(CAL_START)
            time.sleep(0.6 + attempt)
            sx, sy = W / 2, H * (0.45 + 0.05 * attempt)
            d.execute_script('mobile: tap', {'x': float(sx), 'y': float(sy)})
            time.sleep(0.8)
            c = d.execute_script(CAL_READ)
            if c:
                self.cal = (sx - c['x'], sy - c['y'])
                log('  [%s] page origin on screen = %.1f, %.1f' % (self.name, self.cal[0], self.cal[1]))
                return
        raise RuntimeError('calibration tap not received')

    def tap(self, x, y):
        """A real touch at page (client) coordinates."""
        d.execute_script('mobile: tap', {'x': float(self.cal[0] + x), 'y': float(self.cal[1] + y)})

    def tap_picture(self, s):
        b = s['skin']
        self.tap(b[0] + b[2] / 2, b[1] + b[3] * 0.35)

    def run(self):
        log('== %s: %s' % (self.name, self.url))
        d.get(self.url)
        for _ in range(40):
            time.sleep(0.5)
            if d.execute_script("var p = document.querySelector('video-player'); return !!(p && p.store && document.querySelector('red-thread canvas'));"):
                break
        d.execute_script("document.querySelector(arguments[0]).scrollIntoView({ block: 'center' }); return true;", self.sel)
        time.sleep(1.5)
        d.execute_script(HOOKS)
        self.calibrate()
        if self.mode == 'native':
            d.execute_script("document.querySelector('mux-video').source = { preferPlayback: 'native' }; return true;")
        elif self.mode in ('auto', 'metadata'):
            d.execute_script("document.querySelector('mux-video').setAttribute('preload', arguments[0]); return true;", self.mode)
        elif self.mode in ('early', 'early-none'):
            d.execute_script("var m = document.querySelector('mux-video'); m.setAttribute('preload', arguments[0]); m.setAttribute('src', m.dataset.src); return true;",
                             'metadata' if self.mode == 'early' else 'none')
            time.sleep(5)
        s = self.state('loaded')
        shot(self.name + '-1-loaded')

        # 1. tap the picture: the film must start and keep going
        self.tap_picture(s)
        for wait, label in ((1.5, 'tap +1.5s'), (3.0, 'tap +4.5s'), (4.0, 'tap +8.5s')):
            time.sleep(wait)
            s = self.state(label)
        shot(self.name + '-2-after-tap')
        self.playing = (s['paused'] is False) and (s['t'] or 0) > 1.0
        if not self.playing or self.mode != 'full':
            return

        # 2. with the bar away, a tap only brings it back: the film keeps playing
        try:
            for _ in range(8):
                if not s['topVisible']:
                    break
                time.sleep(1.0)
                s = self.state('waiting for the bar to go')
            self.tap_picture(s)
            time.sleep(0.5)
            s = self.state('tap with the bar away (expected: still playing)')
        except Exception as e:
            log('  reveal step failed:', type(e).__name__, str(e)[:200])

        # 3. captions, switched on through the real button's click handler (a touch on it is checked in the lab)
        try:
            d.execute_script("document.querySelector('.rt-captions-button').click(); document.querySelector('video-player').store.seek(28.3); return true;")
            time.sleep(2.5)
            s = self.state('captions on')
            shot(self.name + '-3-captions')
            time.sleep(2.5)
            s = self.state('captions on, bar away')
            shot(self.name + '-4-captions-bar-away')
        except Exception as e:
            log('  captions step failed:', type(e).__name__, str(e)[:200])

        # 4. fullscreen, paused so the bar stays: the skin should fill the window with no handover to Apple's player
        try:
            d.execute_script("document.querySelector('video-player').store.pause(); return true;")
            time.sleep(1.2)
            s = self.state('paused for fullscreen')
            if s['fs']:
                self.tap(s['fs'][0], s['fs'][1])
                time.sleep(3.5)
                s = self.state('after fullscreen tap (expected: skin = window)')
                shot(self.name + '-5-fullscreen')
                if s['fs']:
                    self.tap(s['fs'][0], s['fs'][1])
                    time.sleep(3.5)
                    self.state('after second fullscreen tap (expected: skin back)')
                    shot(self.name + '-6-back')
            d.execute_script("document.querySelector('video-player').store.play(); return true;")
            time.sleep(2.0)
            self.state('playing again')
        except Exception as e:
            log('  fullscreen step failed:', type(e).__name__, str(e)[:200])


code = 0
for name, url, sel, mode in PAGES:
    page = Page(name, url, sel, mode)
    page.playing = False
    try:
        page.run()
    except Exception as e:
        log('  FAILED:', type(e).__name__, str(e)[:300])
        shot(name + '-error')
    results[name] = {'url': url, 'playing': page.playing, 'steps': page.steps}
    if not page.playing:
        code = 1
json.dump(results, open(os.path.join(OUT, 'results.json'), 'w'), indent=1)
log('SUMMARY ' + json.dumps({k: v['playing'] for k, v in results.items()}))
try:
    d.quit()
except Exception:
    pass
sys.exit(code)
