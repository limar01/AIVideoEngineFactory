#!/usr/bin/env python3
"""
zion send <message> — magpadala ng mensahe sa Arena AI at i-echo ang tugon ng AI.

Flow:
  1. create-chat POST sa loob ng live browser (via CDP) — kailangan dahil ang
     reCAPTCHA v3 at Cloudflare cookies ay naka-bind sa browser context.
  2. Hintayin ang AI processing (poll).
  3. Mag-navigate sa /agent/{sessionId} para i-render ang page.
  4. I-extract ang AI response text mula sa DOM at i-echo ito.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
import websocket
from pathlib import Path

from arenaAi_endpoints import (
    ARENA_ORIGIN,
    ARENA_AGENT_PAGE,
    RECAPTCHA_SITE_KEY,
    RECAPTCHA_ACTION_DEFAULT,
    ENDPOINT_CREATE_CHAT,
)

DEBUG_PORT = os.environ.get('ZION_PORT', '9222')

def get_ws():
    for _ in range(8):
        try:
            data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json', timeout=3))
            for t in data:
                if t.get('type') == 'page' and ARENA_ORIGIN in t.get('url', ''):
                    return t['webSocketDebuggerUrl']
        except Exception:
            time.sleep(1)
    return None

class CDP:
    def __init__(self, ws):
        self.ws = websocket.create_connection(ws, timeout=90)
        self.mid = [0]
    def send(self, method, params=None):
        self.mid[0] += 1
        self.ws.send(json.dumps({'id': self.mid[0], 'method': method, 'params': params or {}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get('id') == self.mid[0]:
                return m
    def eval(self, expr, awaitp=True):
        return self.send('Runtime.evaluate', {'expression': expr, 'awaitPromise': awaitp, 'returnByValue': True})

def rsc_fetch(cdp, sid):
    """Kunin ang lahat ng `type:"text"` parts mula sa RSC ng /agent/{sid}
    gamit ang fetch sa loob ng kasalukuyang page — WALANG page.navigate.
    (Iniiwasan nito ang focus shift papuntang ASUS; ang tab ay hindi ginagalaw.)

    Ang regex ay kumukuha ng raw (JSON-escaped) text value; ang unescaping
    (\\n, \\", atbp.) ay ginagawa sa Python sa pamamagitan ng json.loads."""
    js_re = r'\{"type":"text","text":"((?:[^"\\]|\\.)*)"[^}]*\}'
    expr = (
        "(async()=>{"
        "try{"
        "const r=await fetch('/agent/" + sid + "',"
        "{headers:{'accept':'text/html','rsc':'1'}});"
        "const txt=await r.text();"
        "const out=[];"
        "const re=/" + js_re + "/g;"
        "let m;"
        "while((m=re.exec(txt))!==null){out.push(m[1]);}"
        "return out;"
        "}catch(e){return ['__ERR__'+e.message];}"
        "})()"
    )
    r = cdp.eval(expr)
    val = r.get('result', {}).get('result', {}).get('value', '')
    if isinstance(val, str) and val.startswith('__ERR__'):
        return []
    if not isinstance(val, list):
        return []
    # I-decode ang bawat JSON-escaped text part
    decoded = []
    for v in val:
        if isinstance(v, str):
            try:
                decoded.append(json.loads('"' + v + '"'))
            except Exception:
                decoded.append(v)
        else:
            decoded.append(v)
    return decoded

def wait_for_reply(cdp, sid, msg, tries=40):
    """Poll ang RSC hanggang lumitaw ang assistant reply (text part na hindi ang
    user msg). Para hindi makuha ang half-stream na sagot, hintayin hanggang
    ma-stabilize (pareho sa dalawang magkasunod na poll na may laman)."""
    last = None
    for i in range(tries):
        parts = rsc_fetch(cdp, sid)
        replies = [p for p in parts if p.strip() and p.strip() != msg.strip()]
        if replies:
            joined = '\n'.join(replies)
            if joined == last:
                return replies  # stable, complete na ang sagot
            last = joined
        time.sleep(2)
    return []

def extract_reply(txt, msg):
    """Kunin ang malinis na AI reply mula sa DOM text gamit ang markers."""
    # Markers: ang reply ay nasa pagitan ng huling 'Thought for X seconds' block at
    # 'Was this task successful?' / 'Keep working' / 'Workspace'.
    end_markers = ['Was this task successful?', 'Keep working', 'Workspace']
    # Hanapin ang simula ng assistant reply: pagkatapos ng user's message at ng
    # 'Thought for X seconds' na hindi na bahagi ng reasoning.
    # Simpleng: hanapin ang unang "Was this task..." o "Keep working" at kunin ang lahat bago.
    idx_txt = txt
    # Kunin ang AI response sa pamamagitan ng paghahanap sa "Agent Mode" section.
    # Ang text pagkatapos ng 'Agent Mode' hanggang bago ang 'Was this task successful?'
    am = idx_txt.find('Agent Mode')
    if am == -1:
        return idx_txt.strip()
    seg = idx_txt[am:]
    # Alisin ang bago ang 'Was this task...' o 'Keep working' end marker
    best = len(seg)
    for mk in end_markers:
        i = seg.find(mk)
        if i != -1 and i < best:
            best = i
    reply = seg[:best].strip()
    # Alisin ang "Thought for X seconds" na may kasamang reasoning block.
    # Ang AI reply ang text pagkatapos ng HULING "Thought for X seconds" heading,
    # na nagtatapos bago ang susunod na user message o end marker.
    # Simpleng paraan: kunin ang text pagkatapos ng huling kahon ng "Thought for".
    lines = reply.split('\n')
    # Hanapin ang huling indeks ng linya na nagsisimula sa "Thought for"
    last_thought = -1
    for i, ln in enumerate(lines):
        if ln.strip().startswith('Thought for'):
            last_thought = i
    if last_thought != -1:
        # Ang reply ay ang lahat pagkatapos ng thought block. Ang thought reasoning
        # ay nagtatapos sa isang blangkong linya bago ang aktwal na reply.
        rest = lines[last_thought + 1:]
        while rest and rest[0].strip() == '':
            rest.pop(0)
        result = '\n'.join(rest).strip()
    else:
        result = reply.strip()

    # Alisin ang reasoning-style text (na kadalasang nagsisimula sa "The user.../I should...").
    # Ang aktwal na sagot ay nagsisimula matapos ang unang blangkong linya pagkatapos ng reasoning.
    # Simpleng paraan: i-cut pagkatapos ang unang 'Thought for' reasoning block;
    # ang ACTUAL reply ay ang pinakamahabang tuluy-tuloy na text na hindi sinisimulan sa "The user".
    filtered_lines = result.split('\n')
    # Hanapin ang unang linya na mukhang isang tunay na sagot (hindi nagsisimula sa
    # "The user", "I should", "They want", "I'll", "The task", "This is" atbp.)
    start_idx = 0
    reasoning_prefixes = ('The user', 'I should', 'They want', "I'll", 'The task', 'This is', 'I can', 'I will', 'They asked')
    for i, ln in enumerate(filtered_lines):
        s = ln.strip()
        if s and not s.startswith(reasoning_prefixes):
            start_idx = i
            break
    result = '\n'.join(filtered_lines[start_idx:]).strip()

    if msg and result.startswith(msg):
        result = result[len(msg):].lstrip('\n').strip()
    return result

def main():
    if len(sys.argv) < 2:
        print('Usage: zion send "<message>"'); sys.exit(1)
    msg = ' '.join(sys.argv[1:])
    ws_url = get_ws()
    if not ws_url:
        print('ERROR: probe browser offline — launch it with --remote-debugging-port=%s' % DEBUG_PORT)
        sys.exit(1)
    cdp = CDP(ws_url)
    cdp.send('Runtime.enable')
    cdp.send('Page.enable')

    # Step 1: create-chat POST sa loob ng browser
    expr = '''(async()=>{
      try{
        const g=window.grecaptcha;
        const sk=''' + json.dumps(RECAPTCHA_SITE_KEY) + ''';
        const token=await g.enterprise.execute(sk,{action:''' + json.dumps(RECAPTCHA_ACTION_DEFAULT) + '''});
        const msgId=crypto.randomUUID();
        const payload={message:{id:msgId,role:'user',parts:[{type:'text',text:''' + json.dumps(msg) + '''}]},recaptchaV3Token:token,timezone:'Asia/Manila'};
        const resp=await fetch(''' + json.dumps('/nextjs-api/stream/create-chat') + ''',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)});
        const txt=await resp.text();
        return 'STATUS:'+resp.status+'|BODY:'+txt;
      }catch(e){return 'ERR:'+e.message;}
    })()'''
    r = cdp.eval(expr)
    val = r.get('result', {}).get('result', {}).get('value', '')
    status = val.split('|BODY:')[0] if '|BODY:' in val else val
    body = val.split('|BODY:', 1)[1] if '|BODY:' in val else ''
    print('◆ create-chat →', status)
    m = re.search(r'"id":"([0-9a-f-]{36})"', body)
    if not m or 'STATUS:200' not in status:
        print('  server:', body[:200]); sys.exit(1)
    sid = m.group(1)
    print('◆ session:', sid)

    # Step 2: hintayin ang AI response sa pamamagitan ng RSC fetch — WALANG navigation
    print('◆ waiting for AI response...')
    replies = wait_for_reply(cdp, sid, msg)

    # Step 3: i-extract ang AI response
    print()
    # Ang pinaka-maaasahang sagot ay ang huling text part ng assistant (hindi ang user msg)
    answer = extract_reply('\n'.join(replies), msg) if replies else ''
    if not answer:
        answer = '(walang response pa)'
    print('━━━ AI RESPONSE ━━━')
    print(answer)

main()
