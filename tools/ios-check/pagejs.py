"""The scripts the checks run inside the page: hooks that record what the media element and hls.js do, and a
snapshot of the player's state. Shared by the iPhone check (check.py) and the Mac one (mac.py)."""

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
  trackEls: inner ? [].map.call(inner.querySelectorAll('track'), function (t) { return t.kind + ':' + t.track.mode + ':' + t.readyState; }) : null,
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
