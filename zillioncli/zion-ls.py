#!/usr/bin/env python3
"""
zion ls — listahan ng mga kamakailang chat sa Arena AI.
Gumagamit ng GET /api/history/unified sa pamamagitan ng curl_cffi (Chrome TLS fingerprint)
para pumasa sa Cloudflare bot detection.
"""
from arenaAi_endpoints import ENDPOINT_HISTORY_UNIFIED, ARENA_ORIGIN
import sys, os, re, glob

# Ang cookies ay galing sa na-capture na full_cookies.txt (session ng probe browser)
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

def main():
    from curl_cffi import requests
    limit = sys.argv[1] if len(sys.argv) > 1 else '10'
    cookies = load_cookies()
    if not cookies:
        print('ERROR: session cookies not found. Capture them first (see ~/.agents/skills/zion)')
        sys.exit(1)
    try:
        r = requests.get(
            ARENA_ORIGIN + ENDPOINT_HISTORY_UNIFIED + f'?limit={limit}&includeArchived=false',
            cookies=cookies, impersonate='chrome', timeout=20
        )
        if r.status_code != 200:
            print('ERROR: HTTP', r.status_code, r.text[:150]); sys.exit(1)
        import json
        data = json.loads(r.text)
        entries = data.get('entries', [])
        if not entries:
            print('(walang chat history)')
            return
        print(f'── Arena chat history (last {len(entries)}) ──')
        for e in entries:
            kind = e.get('type', '?')
            cid = e.get('id', '')[:13]
            title = (e.get('title') or '(no title)')[:55]
            created = (e.get('createdAt') or '')[:16]
            print(f'  [{kind}] {cid} | {title}')
            print(f'           {created}')
    except Exception as e:
        print('ERROR:', e); sys.exit(1)

main()
