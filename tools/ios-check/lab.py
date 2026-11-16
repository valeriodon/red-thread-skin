#!/usr/bin/env python3
"""A small local site for the iPhone check, to tell apart what a page does from what the skin's build does.

    /lab/static      the embed build (dist-embed/) on a bare page, the media address in the markup
    /lab/late        the same, but the address is handed over at the first gesture (as a page that asks nothing of
                     the video host until the visitor reaches for the player)
    /lab/js          the same, but the player is made by a script once the module has loaded
                     (late and js take ?engine=native, startpos or pad0: see ENGINES; late also takes
                     ?fix=defer, defer-up, reseek or pauseplay: see FIXES)
    /lab/raw/<kind>  no skin: a bare video, hls.js alone, the media element alone or inside a player (see RAW_KINDS)
    /embed/...       dist-embed/
    anything else    fetched from UPSTREAM, so a live page can be checked with one thing changed: add ?v=static
                     (address in the markup), ?v=static,nocase or ?v=static,nocss to its address

Usage: lab.py [port] [upstream origin]   (run `npm run build:embed` first)
"""
import http.server, json, mimetypes, os, re, sys, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
UPSTREAM = sys.argv[2] if len(sys.argv) > 2 else 'https://valeriodonfrancesco.pro'
SRC = 'https://stream.mux.com/8izx3zG35t1ZxSvbjcNmkrAawz9Jhe0172VdCUge25vE.m3u8'
CHAPTERS = 'WEBVTT\n\n00:00:00.000 --> 00:00:28.000\nOne\n\n00:00:28.000 --> 00:01:10.000\nTwo\n\n00:01:10.000 --> 00:01:51.000\nThree\n'

HEAD = '''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Red Thread lab: %s</title>
<link rel="stylesheet" href="/embed/red-thread.css">
<style>body { margin: 0; background: #14110f; color: #eee; font: 16px system-ui; } main { padding: 120px 16px 900px; }</style>
<main><p>%s</p><div id="stage">'''

ENGINES = {
    'native': "{ preferPlayback: 'native' }",
    'startpos': "{ engine: { hlsJs: { startPosition: 0.05 } } }",
    'pad0': "{ engine: { hlsJs: { skipBufferHolePadding: 0 } } }",
}

# Ways out of a film that is asked to play before its first data, tried one at a time with ?fix=
FIXES = {
    # the first play waits until there is something to play
    'defer': '''
      media.setAttribute('preload', 'auto');
      var inner = media.shadowRoot.querySelector('video'), play = media.play;
      media.play = function () {
        if (inner.readyState >= 3) { delete media.play; return play.call(media); }
        return new Promise(function (resolve, reject) {
          inner.addEventListener('canplay', function () { delete media.play; play.call(media).then(resolve, reject); }, { once: true });
        });
      };''',
    # a film that sits still with data ahead of it is seeked again, or paused and played
    'reseek': "watch(media, function (v) { v.currentTime = v.currentTime + 0.001; });",
    'pauseplay': "watch(media, function (v) { v.pause(); v.play(); });",
}

ARM = '''<script>
  // The address reaches the media element at the first gesture on the player, and no earlier.
  var stage = document.getElementById('stage');
  function watch(media, fix) {
    var inner = media.shadowRoot.querySelector('video'), last = -1, still = 0, tries = 0;
    setInterval(function () {
      if (inner.paused || tries >= 3) return;
      var t = inner.currentTime, ahead = 0;
      for (var i = 0; i < inner.buffered.length; i++) if (inner.buffered.start(i) <= t + 0.05 && inner.buffered.end(i) > t) ahead = inner.buffered.end(i) - t;
      still = t === last && ahead > 1 ? still + 1 : 0;
      last = t;
      if (still >= 4) { still = 0; tries++; fix(inner); }
    }, 250);
  }
  function arm() {
    var media = stage.querySelector('mux-video');
    if (media && !media.getAttribute('src') && media.dataset.src) {
      %s
      media.setAttribute('src', media.dataset.src);
    }
  }
  %s.forEach(function (type) { stage.addEventListener(type, arm, { capture: true, passive: true }); });
</script>'''


# Pages without the skin, to find which layer a fault belongs to: the browser, hls.js, the media element or the
# player. One button; `window.__state()` reports the video underneath.
RAW = '''<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Red Thread lab: raw %(kind)s</title>
<style>body { margin: 0; background: #14110f; color: #eee; font: 16px system-ui; } main { padding: 40px 16px; } video, mux-video { display: block; width: 640px; max-width: 100%%; aspect-ratio: 16 / 9; background: #000; } button { font: 600 22px system-ui; padding: 18px 28px; margin: 0 0 16px; }</style>
<main><button id="go">Play</button><div id="stage">%(markup)s</div></main>
%(scripts)s
<script type="module">
  %(imports)s
  const SRC = %(src)s;
  const go = document.getElementById('go');
  window.__ev = [];
  const video = () => { const m = document.querySelector('mux-video'); return m ? m.shadowRoot.querySelector('video') : document.querySelector('video'); };
  const watch = () => ['loadstart', 'loadedmetadata', 'loadeddata', 'canplay', 'play', 'playing', 'waiting', 'stalled', 'seeking', 'seeked', 'error', 'emptied', 'pause'].forEach((t) => video().addEventListener(t, () => window.__ev.push(t + '@' + Math.round(performance.now()))));
  window.__state = () => {
    const v = video(), b = [];
    for (let i = 0; i < v.buffered.length; i++) b.push([+v.buffered.start(i).toFixed(2), +v.buffered.end(i).toFixed(2)]);
    const tracks = [...v.querySelectorAll('track')].map((t) => t.kind + ':' + t.track.mode + ':' + t.readyState);
    return { tracks, paused: v.paused, t: +v.currentTime.toFixed(2), readyState: v.readyState, networkState: v.networkState, preload: v.preload, src: String(v.currentSrc || v.src).slice(0, 12), buffered: b, err: v.error ? v.error.code : null, events: window.__ev.splice(0) };
  };
  const note = (p) => { if (p && p.catch) p.catch((e) => window.__ev.push('play rejected: ' + e.name)); };
  %(start)s
  watch();
  window.__ready = true;
</script>
'''

RAW_KINDS = {
    # the browser's own HLS: address and play in the same click
    'native': dict(markup='<video preload="none" playsinline crossorigin></video>',
                   start="go.addEventListener('click', () => { const v = video(); v.src = SRC; note(v.play()); });"),
    # the same, with the address at the press and play at the release, as a player that loads on the first gesture
    'native-down': dict(markup='<video preload="none" playsinline crossorigin></video>',
                        start="go.addEventListener('pointerdown', () => { video().src = SRC; }); go.addEventListener('click', () => note(video().play()));"),
    # hls.js on its own, loading as soon as it has the address
    'hls': dict(markup='<video preload="none" playsinline crossorigin></video>', scripts='<script src="/hlsjs/hls.min.js"></script>',
                start="go.addEventListener('click', () => { const v = video(), h = new Hls(); h.attachMedia(v); h.loadSource(SRC); note(v.play()); });"),
    # hls.js told to wait for play before it loads, which is how Video.js maps preload=\"none\"
    'hls-onplay': dict(markup='<video preload="none" playsinline crossorigin></video>', scripts='<script src="/hlsjs/hls.min.js"></script>',
                       start="go.addEventListener('pointerdown', () => { const v = video(), h = new Hls({ autoStartLoad: false }); h.attachMedia(v); h.loadSource(SRC); v.addEventListener('play', () => h.startLoad(), { once: true }); }); go.addEventListener('click', () => note(video().play()));"),
    # the Mux media element with no player around it
    'mux': dict(markup='<mux-video preload="none" playsinline crossorigin></mux-video>', imports="import '/embed/red-thread.js';",
                start="const m = document.querySelector('mux-video'); go.addEventListener('pointerdown', () => m.setAttribute('src', SRC)); go.addEventListener('click', () => note(m.play()));"),
    'mux-auto': dict(markup='<mux-video preload="auto" playsinline crossorigin></mux-video>', imports="import '/embed/red-thread.js';",
                     start="const m = document.querySelector('mux-video'); go.addEventListener('pointerdown', () => m.setAttribute('src', SRC)); go.addEventListener('click', () => note(m.play()));"),
    # the same with a chapters track beside it, loaded long before the address arrives
    'player-chapters': dict(markup='<video-player><mux-video preload="none" playsinline crossorigin><track kind="chapters" label="English" srclang="en" src="/lab/chapters.vtt" default></mux-video></video-player>', imports="import '/embed/red-thread.js';",
                            start="const m = document.querySelector('mux-video'); go.addEventListener('pointerdown', () => m.setAttribute('src', SRC)); go.addEventListener('click', () => note(document.querySelector('video-player').store.play()));"),
    # the element inside a player, still with no skin: the player's store asks for play
    'player': dict(markup='<video-player><mux-video preload="none" playsinline crossorigin></mux-video></video-player>', imports="import '/embed/red-thread.js';",
                   start="const m = document.querySelector('mux-video'); go.addEventListener('pointerdown', () => m.setAttribute('src', SRC)); go.addEventListener('click', () => note(document.querySelector('video-player').store.play()));"),
}


def raw_page(kind):
    k = RAW_KINDS.get(kind)
    if not k:
        return None
    return RAW % dict(kind=kind, markup=k['markup'], scripts=k.get('scripts', ''), imports=k.get('imports', ''), src=json.dumps(SRC), start=k['start'])


def skin(media):
    template = open(os.path.join(ROOT, 'src/video/skin.html'), encoding='utf-8').read()
    return template.replace('<!-- Add a compatible media component here. -->', media)


STORYBOARD = '<track kind="metadata" label="thumbnails" default data-storyboard>'


def lab_page(name, engine=None, fix=None, on=None, tracks=None):
    if fix and fix.endswith('-up'):  # a single parameter, so the address needs no quoting in a shell
        fix, on = fix[:-3], 'up'
    source = 'media.source = %s;' % ENGINES[engine] if engine in ENGINES else ''
    source += FIXES.get(fix, '')
    # which events hand the address over: by default the earliest ones, with ?on=up only a finished gesture
    events = "['pointerup', 'keydown']" if on == 'up' else "['pointerdown', 'touchstart', 'keydown', 'focusin']"
    track = '<track kind="chapters" label="English" srclang="en" src="/lab/chapters.vtt" default>'
    # ?tracks=none leaves the chapters out; ?tracks=storyboard also places the track <mux-video> would otherwise add
    # when the address arrives (it then only fills in that track's address, and re-inserts nothing)
    if tracks == 'none':
        track = ''
    elif tracks == 'storyboard':
        track += STORYBOARD
    module = '<script type="module" src="/embed/red-thread.js"></script>'
    if name == 'static':
        media = '<mux-video src="%s" preload="metadata" playsinline crossorigin>%s</mux-video>' % (SRC, track)
        return HEAD % (name, 'Address in the markup.') + '<video-player>' + skin(media) + '</video-player></div></main>' + module
    if name == 'late':
        media = '<mux-video data-src="%s" preload="none" playsinline crossorigin>%s</mux-video>' % (SRC, track)
        return HEAD % (name, 'Address at the first gesture.') + '<video-player>' + skin(media) + '</video-player></div></main>' + module + ARM % (source, events)
    if name == 'js':
        media = '<mux-video playsinline crossorigin>%s</mux-video>' % track
        script = '''<script type="module">
  import '/embed/red-thread.js';
  const player = document.createElement('video-player');
  player.innerHTML = %s;
  document.getElementById('stage').append(player);
  const media = document.querySelector('mux-video');
  %s
  media.preload = 'metadata';
  media.src = %s;
</script>''' % (json.dumps(skin(media)).replace('</', '<\\/'), source, json.dumps(SRC))
        return HEAD % (name, 'Player made by a script.') + '</div></main>' + script
    return None


def changed(html, variants):
    """The live page with one thing different."""
    if 'static' in variants:
        html = re.sub(r'(<mux-video\b[^>]*?)\bdata-src=', r'\1src=', html)
        html = re.sub(r'(<mux-video\b[^>]*?)preload="none"', r'\1preload="metadata"', html)
    if 'storyboard' in variants:
        html = re.sub(r'(<mux-video\b[^>]*>\s*<track\b[^>]*>)', lambda m: m.group(1) + STORYBOARD, html, count=1)
    if 'nocase' in variants:
        html = re.sub(r'<script[^>]*red-thread-case\.js[^>]*></script>', '', html)
    if 'nocss' in variants:
        html = re.sub(r'<link[^>]*/assets/site\.css[^>]*>', '', html)
    return html


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def send(self, status, body, ctype):
        if isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path, query = url.path, urllib.parse.parse_qs(url.query)
        if path == '/lab/chapters.vtt':
            return self.send(200, CHAPTERS, 'text/vtt; charset=utf-8')
        if path.startswith('/lab/raw/'):
            page = raw_page(path[9:])
            return self.send(200, page, 'text/html; charset=utf-8') if page else self.send(404, 'no such raw page', 'text/plain')
        if path == '/hlsjs/hls.min.js':
            return self.send(200, open(os.path.join(ROOT, 'node_modules/hls.js/dist/hls.min.js'), 'rb').read(), 'text/javascript')
        if path.startswith('/lab/'):
            page = lab_page(path[5:], *[query.get(k, [None])[0] for k in ('engine', 'fix', 'on', 'tracks')])
            return self.send(200, page, 'text/html; charset=utf-8') if page else self.send(404, 'no such lab page', 'text/plain')
        if path.startswith('/embed/'):
            file = os.path.normpath(os.path.join(ROOT, 'dist-embed', path[7:]))
            if not file.startswith(os.path.join(ROOT, 'dist-embed') + os.sep) or not os.path.isfile(file):
                return self.send(404, 'not built: npm run build:embed', 'text/plain')
            return self.send(200, open(file, 'rb').read(), mimetypes.guess_type(file)[0] or 'application/octet-stream')
        try:
            with urllib.request.urlopen(urllib.request.Request(UPSTREAM + path, headers={'User-Agent': 'red-thread-lab'}), timeout=30) as r:
                body, ctype = r.read(), r.headers.get('Content-Type', 'application/octet-stream')
        except Exception as e:
            return self.send(502, 'upstream: %s' % e, 'text/plain')
        if 'text/html' in ctype and 'v' in query:
            body = changed(body.decode('utf-8'), query['v'][0].split(','))
        self.send(200, body, ctype)

    def log_message(self, fmt, *args):
        sys.stderr.write('lab %s\n' % (fmt % args))


if __name__ == '__main__':
    print('lab on http://127.0.0.1:%d, upstream %s' % (PORT, UPSTREAM), flush=True)
    http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
