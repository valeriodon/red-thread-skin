#!/usr/bin/env python3
"""Create and boot a fresh iPhone simulator on the newest iOS runtime. Prints udid/name/runtime for $GITHUB_OUTPUT."""
import json, re, subprocess, sys, time


def sh(*a, check=True):
    r = subprocess.run(a, capture_output=True, text=True)
    if check and r.returncode:
        print(' '.join(a), '->', r.returncode, r.stdout, r.stderr, file=sys.stderr)
        raise SystemExit(1)
    return r.stdout


def ver(s):
    return tuple(int(x) for x in re.findall(r'\d+', s))


runtimes = [r for r in json.loads(sh('xcrun', 'simctl', 'list', 'runtimes', '-j'))['runtimes']
            if r.get('isAvailable') and (r.get('platform') == 'iOS' or r['identifier'].split('.')[-1].startswith('iOS'))]
runtimes.sort(key=lambda r: ver(r['version']), reverse=True)
print('iOS runtimes:', [r['version'] for r in runtimes], file=sys.stderr)
prefer = ['iPhone 16e', 'iPhone 14', 'iPhone 13', 'iPhone 17', 'iPhone 16', 'iPhone 15']
choice = None
for r in runtimes:
    names = {d['name']: d['identifier'] for d in r.get('supportedDeviceTypes', [])}
    for p in prefer:
        if p in names:
            choice = (r, p, names[p])
            break
    if choice:
        break
if not choice:
    raise SystemExit('no iPhone runtime found')
rt, name, dtype = choice
udid = sh('xcrun', 'simctl', 'create', 'rt-' + name.replace(' ', '-'), dtype, rt['identifier']).strip()
print('created', name, rt['version'], udid, file=sys.stderr)
sh('xcrun', 'simctl', 'boot', udid)
sh('xcrun', 'simctl', 'bootstatus', udid, '-b')
for key in ('RemoteAutomationEnabled', 'WebKitRemoteAutomationEnabled'):
    sh('xcrun', 'simctl', 'spawn', udid, 'defaults', 'write', 'com.apple.mobilesafari', key, '-bool', 'true', check=False)
time.sleep(20)  # let SpringBoard settle after the first boot
print('udid=' + udid)
print('name=' + name)
print('runtime=' + rt['version'])
