#!/usr/bin/env python3
from arenaAi_endpoints import ENDPOINT_HISTORY_UNIFIED, ARENA_ORIGIN
import os, json

COOKIE_FILES = [
    '/home/limar01/zillion/capture/full_cookies.txt',
    '/home/limar01/.config/zion/session_cookies.txt',
]
def load_cookies():
    for f in COOKIE_FILES:
        if os.path.exists(f):
            ck = open(f).read().strip()
            return {p.split('=', 1)[0]: p.split('=', 1)[1] for p in ck.split(', ') if '=' in p}
    return None

from curl_cffi import requests
cookies = load_cookies()
if cookies:
    r = requests.get(ARENA_ORIGIN + ENDPOINT_HISTORY_UNIFIED + '?limit=6&includeArchived=false',
                     cookies=cookies, impersonate='chrome', timeout=20)
    for e in json.loads(r.text).get('entries', []):
        print(e.get('id'), '|', (e.get('title') or '')[:50], '|', e.get('createdAt', '')[:16])
else:
    print('ERROR: session cookies not found')
