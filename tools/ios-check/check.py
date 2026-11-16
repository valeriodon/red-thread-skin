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

UDID, OUT = sys.argv[1], sys.argv[2]
PAGES = [(a.split('@@') + ['play'])[:4] for a in sys.argv[3:]] or [
    ['demo', 'https://red-thread-skin.vercel.app/preview.html', 'media-container', 'full'],
]
os.makedirs(OUT, exist_ok=True)

HOOKS = r'''
if (!window.__rt) {
  window.__rt = { errors: [], events: [] };
  var stamp = function (s) { window.__rt.events.push(s + '@' + Math.round(performance.now())); };
  var spans = function (r) { var o = []; try { for (var i = 0; i < r.length; i++) o.push(r.start(i).toFixed(2) + '-' + r.end(i).toFixed(2)); } catch (x) {} return '[' + o.join(' ') + ']'; };
  addEventListener('error', function (e) { window.__rt.errors.push('error: ' + (e.message || e.type)); });
  addEventListener('unhandledrejection', function (e) { window.__rt.errors.push('rejection: ' + String(e.reason && (e.reason.message || e.reason.name) || e.reason)); });
  var m = document.querySelector('mux-video');
  ['loadstart', 'loadedmetadata', 'canplay', 'play', 'playing', 'pause', 'waiting', 'stalled', 'error', 'emptied', 'abort', 'ended'].forEach(function (t) {
    m.addEventListener(t, function () { stamp(t); });
  });
  // What the media source is fed: every append and removal, per source buffer.
  var watchBuffer = function (sb, tag) {
    if (sb.__rt) return;
    sb.__rt = true;
    ['error', 'abort'].forEach(function (n) { sb.addEventListener(n, function () { stamp(tag + ' ' + n); }); });
    sb.addEventListener('bufferedchange', function (ev) { stamp(tag + ' bufferedchange +' + spans(ev.addedRanges) + ' -' + spans(ev.removedRanges)); });
    var append = sb.appendBuffer, remove = sb.remove;
    sb.appendBuffer = function (data) { stamp(tag + ' append ' + data.byteLength); return append.apply(this, arguments); };
    sb.remove = function (a, b) { stamp(tag + ' remove ' + a + '-' + b); return remove.apply(this, arguments); };
  };
  try {
    var MS = window.ManagedMediaSource || window.MediaSource, add = MS.prototype.addSourceBuffer;
    MS.prototype.addSourceBuffer = function (type) {
      var sb = add.apply(this, arguments);
      stamp('addSourceBuffer ' + type);
      try { watchBuffer(sb, /audio/.test(type) ? 'A' : 'V'); } catch (x) {}
      return sb;
    };
  } catch (x) { window.__rt.errors.push('hook: ' + x); }
  // hls.js, as soon as the media element has made one (on a page that waits for a gesture, that is after the tap).
  setInterval(function () {
    try {
      var e = m.adapter && m.adapter.engine;
      if (!e) return;
      var ms = e.bufferController && e.bufferController.mediaSource;
      if (ms && !ms.__rt) {
        ms.__rt = true;
        ['sourceopen', 'sourceended', 'sourceclose', 'startstreaming', 'endstreaming'].forEach(function (n) { ms.addEventListener(n, function () { stamp('ms ' + n); }); });
        for (var i = 0; i < ms.sourceBuffers.length; i++) watchBuffer(ms.sourceBuffers[i], 'SB' + i);
      }
      if (e.__rt) return;
      e.__rt = true;
      stamp('engine found');
      ['hlsMediaAttached', 'hlsManifestLoading', 'hlsManifestParsed', 'hlsLevelLoaded', 'hlsAudioTrackLoaded', 'hlsBufferCodecs', 'hlsBufferCreated', 'hlsBufferEos', 'hlsBufferFlushed', 'hlsMediaDetached', 'hlsDestroying', 'hlsLevelSwitching'].forEach(function (n) {
        e.on(n, function () { stamp(n.slice(3)); });
      });
      e.on('hlsError', function (_, d) { stamp('Error ' + d.details + (d.fatal ? ' fatal' : '') + (d.error ? ' ' + String(d.error.message).slice(0, 90) : '')); });
      e.on('hlsFragLoading', function (_, d) { stamp('loading ' + d.frag.type + ' ' + d.frag.sn); });
      e.on('hlsFragBuffered', function (_, d) { stamp('buffered ' + d.frag.type + ' ' + d.frag.sn); });
      ['startLoad', 'stopLoad', 'pauseBuffering', 'resumeBuffering'].forEach(function (n) {
        var f = e[n];
        e[n] = function () { stamp(n + '(' + (e.bufferingEnabled ? 'on' : 'off') + ')'); return f.apply(this, arguments); };
      });
    } catch (x) { if (window.__rt.errors.length < 5) window.__rt.errors.push('hook: ' + x); }
  }, 5);
}
return true;
'''

STATE = r'''
var sel = arguments[0];
var p = document.querySelector('video-player'), s = p && p.store, m = document.querySelector('mux-video');
var inner = m && m.shadowRoot ? m.shadowRoot.querySelector('video') : null;
var box = document.querySelector(sel).getBoundingClientRect();
function spans(r) { var o = []; try { for (var i = 0; i < r.length; i++) o.push([+r.start(i).toFixed(2), +r.end(i).toFixed(2)]); } catch (x) { o.push(String(x)); } return o; }
var e = m && m.adapter ? m.adapter.engine : null, hls = null;
try {
  if (e) {
    var ms = e.bufferController && e.bufferController.mediaSource;
    hls = { maxLen: e.config.maxBufferLength, maxSize: e.config.maxBufferSize, buffering: e.bufferingEnabled, started: e.started, level: e.currentLevel, loadLevel: e.loadLevel, levels: e.levels ? e.levels.length : null,
      controllers: (e.networkControllers || []).map(function (c) { return c.state; }).filter(Boolean),
      ms: ms ? { kind: ms.constructor && ms.constructor.name, state: ms.readyState, streaming: ms.streaming, duration: ms.duration, active: ms.activeSourceBuffers.length,
        buffers: [].map.call(ms.sourceBuffers, function (sb) { return { updating: sb.updating, buffered: spans(sb.buffered) }; }) } : null };
  }
} catch (x) { hls = { failed: String(x) }; }
var skin = document.querySelector('media-container').getBoundingClientRect();
var cap = document.querySelector('.rt-captions'), cr = cap.getBoundingClientRect();
function rect(q) { var e = document.querySelector(q); if (!e) return null; var r = e.getBoundingClientRect(); return [Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2), Math.round(r.width), Math.round(r.height)]; }
return {
  hasStore: !!s, paused: s ? s.paused : null, t: m ? +(+m.currentTime).toFixed(2) : null, duration: s ? s.duration : null, waiting: s ? s.waiting : null,
  error: s && s.error ? String(s.error.message || s.error.code || s.error) : null,
  srcAttr: m && m.getAttribute('src') ? 'set' : 'none',
  inner: inner ? { src: String(inner.currentSrc || inner.src || '').slice(0, 12), readyState: inner.readyState, networkState: inner.networkState, paused: inner.paused, err: inner.error ? inner.error.code : null, sources: [].map.call(inner.querySelectorAll('source'), function (q) { return (q.type || '?') + ' ' + String(q.src).slice(0, 5); }), mode: inner.webkitPresentationMode || null,
    buffered: spans(inner.buffered), preload: inner.preload, noRemote: inner.disableRemotePlayback, size: [inner.videoWidth, inner.videoHeight], seeking: inner.seeking,
    decoded: [inner.webkitVideoDecodedByteCount, inner.webkitAudioDecodedByteCount], tracks: [].map.call(inner.textTracks, function (t) { return t.kind + ':' + t.mode + (t.mode === 'showing' && t.activeCues && t.activeCues.length ? ':"' + String(t.activeCues[0].text).slice(0, 30) + '"' : ''); }) } : null,
  hls: hls, preloadHost: m ? m.getAttribute('preload') : null, visible: document.visibilityState,
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
