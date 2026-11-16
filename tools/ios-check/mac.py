#!/usr/bin/env python3
"""Red Thread in Safari on a Mac (safaridriver through Selenium): click the picture and report whether the film
plays, then captions and a pluck of the thread.

Usage: mac.py <output dir> [name@@url@@selector-of-the-player ...]
Needs `sudo safaridriver --enable` once. Writes results.json and screenshots, and prints a summary.
"""
import json, os, sys, time

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains

from pagejs import HOOKS, STATE

OUT = sys.argv[1]
PAGES = [(a.split('@@') + ['media-container'])[:3] for a in sys.argv[2:]] or [
    ['demo', 'https://red-thread-skin.vercel.app/preview.html', 'media-container'],
]
os.makedirs(OUT, exist_ok=True)


def log(*a):
    print(*a, flush=True)


d = webdriver.Safari()
d.set_window_size(1280, 900)
d.set_script_timeout(30)
log('Safari', d.capabilities.get('browserVersion'), d.execute_script('return [innerWidth, innerHeight]'))
results, code = {}, 0


def state(name, sel, label, steps):
    s = d.execute_script(STATE, sel)
    s['step'] = label
    steps.append(s)
    log('  [%s] %s: paused=%s t=%s waiting=%s subtitles=%s caption=%s err=%s inner=%s hls=%s events=%s errors=%s' % (
        name, label, s['paused'], s['t'], s['waiting'], s['subtitles'], json.dumps(s['caption']), s['error'],
        json.dumps(s['inner']), json.dumps(s['hls']), s['events'], s['errors']))
    return s


def click_at(sel, fx, fy):
    """A click at a fraction of the element's box."""
    el = d.find_element('css selector', sel)
    w, h = el.size['width'], el.size['height']
    ActionChains(d).move_to_element_with_offset(el, int(w * (fx - 0.5)), int(h * (fy - 0.5))).click().perform()


for name, url, sel in PAGES:
    steps, playing = [], False
    log('== %s: %s' % (name, url))
    try:
        d.get(url)
        if '/lab/raw/' in url:  # no skin: one button, and the page reports the video itself
            for _ in range(40):
                time.sleep(0.5)
                if d.execute_script('return !!window.__ready'):
                    break
            time.sleep(1.0)
            ActionChains(d).click(d.find_element('css selector', '#go')).perform()
            for wait, label in ((1.5, 'click +1.5s'), (3.0, 'click +4.5s'), (4.0, 'click +8.5s')):
                time.sleep(wait)
                s = d.execute_script('return window.__state()')
                s['step'] = label
                steps.append(s)
                log('  [%s] %s: %s' % (name, label, json.dumps(s)))
            playing = (s['paused'] is False) and (s['t'] or 0) > 1.0
            raise StopIteration
        for _ in range(40):
            time.sleep(0.5)
            if d.execute_script("var p = document.querySelector('video-player'); return !!(p && p.store && document.querySelector('red-thread canvas'));"):
                break
        d.execute_script("document.querySelector(arguments[0]).scrollIntoView({ block: 'center' }); return true;", sel)
        time.sleep(1.5)
        d.execute_script(HOOKS)
        state(name, sel, 'loaded', steps)
        d.save_screenshot(os.path.join(OUT, name + '-1-loaded.png'))

        click_at('media-container', 0.5, 0.35)
        for wait, label in ((1.5, 'click +1.5s'), (3.0, 'click +4.5s'), (4.0, 'click +8.5s')):
            time.sleep(wait)
            s = state(name, sel, label, steps)
        d.save_screenshot(os.path.join(OUT, name + '-2-playing.png'))
        playing = (s['paused'] is False) and (s['t'] or 0) > 1.0

        if playing:
            d.execute_script("document.querySelector('.rt-captions-button').click(); document.querySelector('video-player').store.seek(28.3); return true;")
            time.sleep(2.5)
            state(name, sel, 'captions on', steps)
            d.save_screenshot(os.path.join(OUT, name + '-3-captions.png'))
            # a click on the thread, two thirds along: the film goes there
            click_at('media-container', 0.66, 0.96)
            time.sleep(2.5)
            state(name, sel, 'after a click on the thread at two thirds', steps)
            d.save_screenshot(os.path.join(OUT, name + '-4-seek.png'))
    except StopIteration:
        pass
    except Exception as e:
        log('  FAILED:', type(e).__name__, str(e)[:300])
    results[name] = {'url': url, 'playing': playing, 'steps': steps}
    if not playing:
        code = 1

json.dump(results, open(os.path.join(OUT, 'results.json'), 'w'), indent=1)
log('SUMMARY ' + json.dumps({k: v['playing'] for k, v in results.items()}))
d.quit()
sys.exit(code)
