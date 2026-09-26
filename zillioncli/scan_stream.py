#!/usr/bin/env python3
from arenaAi_endpoints import ARENA_ORIGIN
import re, urllib.request

html = open('/tmp/agent.html').read()
chunks = set(re.findall(r'src="([^"]+\.js[^"]*)"', html))
base = ARENA_ORIGIN
hits = set()
for ch in chunks:
    url = ch if ch.startswith('http') else base + ch
    try:
        d = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=10).read().decode('utf-8', 'ignore')
    except Exception:
        continue
    # lahat ng pagbanggit ng /nextjs-api/...
    for m in re.findall(r'/nextjs-api/[A-Za-z0-9_/.-]+', d):
        hits.add(m)
# hanapin din ang mga stream route na may template/concatenation
for ch in chunks:
    url = ch if ch.startswith('http') else base + ch
    try:
        d = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=10).read().decode('utf-8', 'ignore')
    except Exception:
        continue
    for m in re.findall(r'"/nextjs-api/stream/[a-zA-Z-]+/"', d):
        hits.add('TRAILING:' + m)
    for m in re.findall(r'/nextjs-api/stream/[a-zA-Z-]+/\$\{', d):
        hits.add('DYN:' + m)
print('--- merged routes ---')
for h in sorted(hits):
    print(h)
