import json, urllib.request, socket, base64, hashlib, os, time

url = 'http://localhost:9228/json'
resp = urllib.request.urlopen(url, timeout=10)
tabs = json.loads(resp.read())

messenger_ws = None
for t in tabs:
    if 'messenger' in t.get('url', '').lower() and 'facebook.com/messages' in t.get('url', ''):
        messenger_ws = t.get('webSocketDebuggerUrl')
        print(f'Messenger: {t["url"]}')
        break

if not messenger_ws:
    print('No Messenger tab')
    exit(1)

parts = messenger_ws.replace('ws://', '').split('/')
host_port = parts[0]
path = '/' + '/'.join(parts[1:])

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
sock.connect((host_port.split(':')[0], int(host_port.split(':')[1])))

key = base64.b64encode(os.urandom(16)).decode()
crlf = chr(13) + chr(10)
handshake = ('GET ' + path + ' HTTP/1.1' + crlf +
    'Host: ' + host_port + crlf +
    'Upgrade: websocket' + crlf + 'Connection: Upgrade' + crlf +
    'Sec-WebSocket-Key: ' + key + crlf + 'Sec-WebSocket-Version: 13' + crlf + crlf).encode()
sock.sendall(handshake)
sock.recv(4096)

headers = sock.recv(4096).decode().split(crlf)
accept = None
for h in headers:
    if h.startswith('Sec-WebSocket-Accept:'):
        accept = h.split(': ')[1].strip()

magic = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
expected = base64.b64encode(hashlib.sha1((key + magic).encode()).digest()).decode()
if accept == expected:
    print('Handshake OK')
else:
    print('Accept mismatch')
    sock.close()
    exit(1)

def ws_send(msg):
    mb = msg.encode() if isinstance(msg, str) else msg
    l = len(mb); mk = os.urandom(4)
    f = bytearray([0x81])
    if l < 126: f.append(0x80 | l); f.extend(mk)
    sock.sendall(f + bytes([mb[i] ^ mk[i % 4] for i in range(l)]))

def ws_recv(timeout=3):
    sock.settimeout(timeout)
    try:
        h = sock.recv(2)
        if not h: return None
        l = h[1] & 0x7F
        if l == 126: l = int.from_bytes(sock.recv(2), 'big')
        elif l == 127: l = int.from_bytes(sock.recv(8), 'big')
        payload = sock.recv(l)
        if h[1] & 0x80:
            mk = sock.recv(4)
            payload = bytes([payload[i] ^ mk[i % 4] for i in range(l)])
        return payload.decode()
    except:
        return None

counter = [2100]
def cdp(expr):
    cid = counter[0]; counter[0] += 1
    ws_send(json.dumps({'id': cid, 'method': 'Runtime.evaluate', 'params': {'expression': expr, 'returnByValue': True}}))
    start = time.time()
    while time.time() - start < 5:
        r = ws_recv(1)
        if r:
            d = json.loads(r)
            if d.get('id') == cid:
                return d.get('result', {}).get('result', {}).get('value', None)
    return None

js_scan = """(() => {
    const r = [];
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let n = w.nextNode();
    let c = 0;
    while (n && c < 8000) {
        const t = (n.textContent || '').toLowerCase();
        const al = n.getAttribute('aria-label') || '';
        if (t.includes('meta ai') || t.includes('generate video') ||
            al.toLowerCase().includes('meta') || al.toLowerCase().includes('ai')) {
            r.push({
                tag: n.tagName,
                cls: (n.className || '').toString().substring(0, 80),
                text: (n.textContent || '').substring(0, 150),
                aria: al.substring(0, 100),
                role: n.getAttribute('role') || '',
                x: Math.round(n.getBoundingClientRect().left),
                y: Math.round(n.getBoundingClientRect().top),
                w: Math.round(n.getBoundingClientRect().width),
                h: Math.round(n.getBoundingClientRect().height)
            });
            if (r.length >= 15) break;
        }
        n = w.nextNode();
        c++;
    }
    return r;
})()"""

print('=== Scanning for Meta AI elements ===')
result = cdp(js_scan)
if result:
    print(f'Found {len(result)} elements:')
    for r in result:
        print(f'  [{r["tag"]}] aria="{r["aria"][:80]}"')
        print(f'    text: {r["text"][:150]}')
        print(f'    pos: x={r["x"]} y={r["y"]} w={r["w"]} h={r["h"]}')
        print()
else:
    print('No Meta AI elements found in DOM scan')

js_inputs = """(() => {
    const r = [];
    const s = [
        '[aria-label=Message]',
        '[aria-label=Type a message]',
        '[contenteditable=true]',
        'textarea',
        '[data-testid=composer]',
        '[role=textbox]',
        'input[placeholder]'
    ];
    for (const sel of s) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
            const rect = el.getBoundingClientRect();
            r.push({
                sel: sel,
                tag: el.tagName,
                text: (el.textContent || '').substring(0, 80),
                ph: (el.placeholder || '').substring(0, 80),
                x: Math.round(rect.left),
                y: Math.round(rect.top),
                w: Math.round(rect.width),
                h: Math.round(rect.height)
            });
        }
    }
    return r.slice(0, 20);
})()"""

print('=== Chat composer / input elements ===')
result2 = cdp(js_inputs)
if result2:
    print(f'Found {len(result2)} elements:')
    for r in result2:
        print(f'  [{r["sel"]}] {r["tag"]} ph="{r["ph"][:60]}" text="{r["text"][:60]}" pos=({r["x"]},{r["y"]}) {r["w"]}x{r["h"]}')
else:
    print('No input elements found')

print(f'\nTitle: {cdp("document.title")}')
print(f'URL: {cdp("window.location.href")}')

# Check for any sparkles/emoji button or AI icon
js_buttons = """(() => {
    const r = [];
    const buttons = document.querySelectorAll('button, [role=button], div[role=button]');
    for (const b of buttons) {
        const txt = (b.textContent || '').trim().substring(0, 100);
        const al = b.getAttribute('aria-label') || '';
        const cls = (b.className || '').toString().substring(0, 80);
        if (txt.includes('Meta') || txt.includes('AI') || txt.includes('Sparkle') || txt.includes('✨') ||
            al.toLowerCase().includes('meta') || al.toLowerCase().includes('ai') ||
            cls.toLowerCase().includes('meta') || cls.toLowerCase().includes('ai') ||
            cls.toLowerCase().includes('sparkle')) {
            const rect = b.getBoundingClientRect();
            r.push({
                tag: b.tagName,
                cls: cls,
                text: txt,
                aria: al.substring(0, 100),
                x: Math.round(rect.left),
                y: Math.round(rect.top),
                w: Math.round(rect.width),
                h: Math.round(rect.height)
            });
        }
    }
    return r.slice(0, 20);
})()"""

print('=== Buttons with AI/Meta/Sparkle ===')
result3 = cdp(js_buttons)
if result3:
    print(f'Found {len(result3)} buttons:')
    for r in result3:
        print(f'  [{r["tag"]}] cls="{r["cls"][:60]}"')
        print(f'    text: {r["text"][:100]}')
        print(f'    aria: {r["aria"][:80]}')
        print(f'    pos: x={r["x"]} y={r["y"]} {r["w"]}x{r["h"]}')
        print()
else:
    print('No AI/Meta buttons found')

sock.close()
print('\nDone.')
