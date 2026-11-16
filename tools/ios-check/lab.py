#!/usr/bin/env python3
"""A small local site for the iPhone check, to tell apart what a page does from what the skin's build does.

    /lab/static      the embed build (dist-embed/) on a bare page, the media address in the markup
    /lab/late        the same, but the address is handed over at the first gesture (as a page that asks nothing of
                     the video host until the visitor reaches for the player)
    /lab/js          the same, but the player is made by a script once the module has loaded
                     (late and js take ?engine=native, startpos or pad0: see ENGINES)
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

ARM = '''<script>
  // The address reaches the media element at the first gesture on the player, and no earlier.
  var stage = document.getElementById('stage');
  function arm() {
    var media = stage.querySelector('mux-video');
    if (media && !media.getAttribute('src') && media.dataset.src) {
      %s
      media.setAttribute('src', media.dataset.src);
    }
  }
  ['pointerdown', 'touchstart', 'keydown', 'focusin'].forEach(function (type) { stage.addEventListener(type, arm, { capture: true, passive: true }); });
</script>'''


def skin(media):
    template = open(os.path.join(ROOT, 'src/video/skin.html'), encoding='utf-8').read()
    return template.replace('<!-- Add a compatible media component here. -->', media)


def lab_page(name, engine=None):
    source = 'media.source = %s;' % ENGINES[engine] if engine in ENGINES else ''
    track = '<track kind="chapters" label="English" srclang="en" src="/lab/chapters.vtt" default>'
    module = '<script type="module" src="/embed/red-thread.js"></script>'
    if name == 'static':
        media = '<mux-video src="%s" preload="metadata" playsinline crossorigin>%s</mux-video>' % (SRC, track)
        return HEAD % (name, 'Address in the markup.') + '<video-player>' + skin(media) + '</video-player></div></main>' + module
    if name == 'late':
        media = '<mux-video data-src="%s" preload="none" playsinline crossorigin>%s</mux-video>' % (SRC, track)
        return HEAD % (name, 'Address at the first gesture.') + '<video-player>' + skin(media) + '</video-player></div></main>' + module + ARM % source
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
        if path.startswith('/lab/'):
            page = lab_page(path[5:], query.get('engine', [None])[0])
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
