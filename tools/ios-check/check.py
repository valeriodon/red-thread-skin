#!/usr/bin/env python3
"""Red Thread in Safari on an iPhone simulator, with real touches (Appium, XCUITest driver).

For each page: tap the picture and report whether the film plays; then captions and fullscreen.
Usage: check.py <simulator udid> <output dir> [name=url=selector-of-the-player ...]
Writes results.json and screenshots to the output dir, and prints a summary.
"""
import json, os, subprocess, sys, time

from appium import webdriver
from appium.options.ios import XCUITestOptions

UDID, OUT = sys.argv[1], sys.argv[2]
PAGES = [a.split('=', 2) for a in sys.argv[3:]] or [
    ['demo', 'https://red-thread-skin.vercel.app/preview.html', 'media-container'],
]
os.makedirs(OUT, exist_ok=True)

HOOKS = r'''
if (!window.__rt) {
  window.__rt = { errors: [], events: [] };
  addEventListener('error', function (e) { window.__rt.errors.push('error: ' + (e.message || e.type)); });
  addEventListener('unhandledrejection', function (e) { window.__rt.errors.push('rejection: ' + String(e.reason && (e.reason.message || e.reason.name) || e.reason)); });
  var m = document.querySelector('mux-video');
  ['loadstart', 'loadedmetadata', 'canplay', 'play', 'playing', 'pause', 'waiting', 'stalled', 'error', 'emptied', 'abort', 'ended'].forEach(function (t) {
    m.addEventListener(t, function () { window.__rt.events.push(t + '@' + Math.round(performance.now())); });
  });
}
return true;
'''

STATE = r'''
var sel = arguments[0];
var p = document.querySelector('video-player'), s = p && p.store, m = document.querySelector('mux-video');
var inner = m && m.shadowRoot ? m.shadowRoot.querySelector('video') : null;
var box = document.querySelector(sel).getBoundingClientRect();
var skin = document.querySelector('media-container').getBoundingClientRect();
var cap = document.querySelector('.rt-captions'), cr = cap.getBoundingClientRect();
function rect(q) { var e = document.querySelector(q); if (!e) return null; var r = e.getBoundingClientRect(); return [Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2), Math.round(r.width), Math.round(r.height)]; }
return {
  hasStore: !!s, paused: s ? s.paused : null, t: m ? +(+m.currentTime).toFixed(2) : null, duration: s ? s.duration : null, waiting: s ? s.waiting : null,
  error: s && s.error ? String(s.error.message || s.error.code || s.error) : null,
  srcAttr: m && m.getAttribute('src') ? 'set' : 'none',
  inner: inner ? { src: String(inner.currentSrc || inner.src || '').slice(0, 12), readyState: inner.readyState, networkState: inner.networkState, paused: inner.paused, err: inner.error ? inner.error.code : null, sources: inner.querySelectorAll('source').length, mode: inner.webkitPresentationMode || null } : null,
  mse: 'MediaSource' in window, mms: 'ManagedMediaSource' in window, fullscreenEnabled: !!(document.fullscreenEnabled || document.webkitFullscreenEnabled), isFullscreen: s ? s.isFullscreen : null,
  volumeAvailability: s ? s.volumeAvailability : null, subtitles: s ? s.subtitlesShowing : null, topVisible: !!document.querySelector('.rt-top[data-visible]'),
  box: [Math.round(box.left), Math.round(box.top), Math.round(box.width), Math.round(box.height)], skin: [Math.round(skin.left), Math.round(skin.top), Math.round(skin.width), Math.round(skin.height)],
  cc: rect('.rt-captions-button'), fs: rect('.rt-fullscreen-button'),
  caption: cap.hidden ? null : { text: cap.textContent.slice(0, 40), top: Math.round(cr.top - skin.top), bottom: Math.round(cr.bottom - skin.top), opacity: getComputedStyle(cap).opacity },
  view: { iw: innerWidth, ih: innerHeight, vl: visualViewport.offsetLeft, vt: visualViewport.offsetTop, scale: visualViewport.scale, sy: Math.round(scrollY) },
  events: window.__rt ? window.__rt.events.splice(0) : [], errors: window.__rt ? window.__rt.errors.splice(0) : [], ua: navigator.userAgent.slice(-60)
};
'''

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
d = webdriver.Remote('http://127.0.0.1:4723', options=o)
d.set_script_timeout(30)
d.set_page_load_timeout(90)
W, H = d.execute_script('return [screen.width, screen.height]')
log('screen (points)', W, H)

results = {}


def shot(name):
    subprocess.run(['xcrun', 'simctl', 'io', UDID, 'screenshot', '--type=png', os.path.join(OUT, name + '.png')], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Page:
    def __init__(self, name, url, sel):
        self.name, self.url, self.sel, self.cal = name, url, sel, None
        self.steps = []

    def state(self, label):
        s = d.execute_script(STATE, self.sel)
        s['step'] = label
        self.steps.append(s)
        log('  [%s] %s: paused=%s t=%s dur=%s waiting=%s err=%s inner=%s events=%s errors=%s' % (
            self.name, label, s['paused'], s['t'], s['duration'], s['waiting'], s['error'], json.dumps(s['inner']), s['events'], s['errors']))
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
        s = self.state('loaded')
        shot(self.name + '-1-loaded')

        # 1. tap the picture: the film must start
        self.tap_picture(s)
        for wait, label in ((1.0, 'tap +1s'), (2.5, 'tap +3.5s'), (4.0, 'tap +7.5s')):
            time.sleep(wait)
            s = self.state(label)
        shot(self.name + '-2-after-tap')
        playing = (s['paused'] is False) and (s['t'] or 0) > 0.5
        if not playing:
            # a second tap tells whether only the first gesture is lost
            if s['paused'] is False:
                self.tap_picture(s)  # pause
                time.sleep(1.0)
                s = self.state('tap 2 (pause)')
            self.tap_picture(s)
            for wait, label in ((1.5, 'second play +1.5s'), (5.0, 'second play +6.5s')):
                time.sleep(wait)
                s = self.state(label)
            shot(self.name + '-3-second-tap')
            playing = (s['paused'] is False) and (s['t'] or 0) > 0.5
        self.playing = playing
        if not playing:
            return

        # 2. captions: pause (the bar shows), tap the captions button, play, look at where the line sits
        try:
            self.tap_picture(s)
            time.sleep(1.2)
            s = self.state('paused for captions')
            if s['cc']:
                self.tap(s['cc'][0], s['cc'][1])
                time.sleep(0.8)
            d.execute_script("document.querySelector('video-player').store.seek(28.3); return true;")
            time.sleep(0.8)
            s = self.state('captions on, paused')
            self.tap_picture(s)
            time.sleep(1.2)
            s = self.state('captions, bar showing')
            shot(self.name + '-4-captions-bar')
            d.execute_script("document.querySelector('video-player').store.seek(28.3); return true;")
            time.sleep(4.2)
            s = self.state('captions, bar away')
            shot(self.name + '-5-captions-top')
        except Exception as e:
            log('  captions step failed:', type(e).__name__, str(e)[:200])

        # 3. fullscreen: the skin should fill the window, with no handover to the native player
        try:
            self.tap_picture(s)
            time.sleep(1.2)
            s = self.state('paused for fullscreen')
            if s['fs']:
                self.tap(s['fs'][0], s['fs'][1])
                time.sleep(2.5)
                s = self.state('after fullscreen tap')
                shot(self.name + '-6-fullscreen')
                if s['fs']:
                    self.tap(s['fs'][0], s['fs'][1])
                    time.sleep(2.5)
                    self.state('after second fullscreen tap')
                    shot(self.name + '-7-back')
        except Exception as e:
            log('  fullscreen step failed:', type(e).__name__, str(e)[:200])


code = 0
for name, url, sel in PAGES:
    page = Page(name, url, sel)
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
