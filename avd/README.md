# 📱 zillion_root_avd — rooted Android emulator for agents

A **rooted** Android emulator running on the PC (Omarchy), reachable by cloud agents through the
Zillion bridge. Use it to build/test Android apps, automate UI, capture screenshots, inspect
traffic, and modify the system image — without touching a physical device.

> **Status:** created + root-verified 2026-09-26 on `limar01@omarchy` (PC lane `zillionOM`).

---

## TL;DR for agents

**If you are a Hermes agent running on this PC — use the `avd` helper. It is on your PATH.**

```bash
avd ensure          # start/wait/root/agent-mode — always run this first
avd text            # read the screen (cheap, no image needed)
avd tap-text "Sign in"   # act by label — coordinates are read from the UI tree, never guessed
avd shot /tmp/s.png # see the screen when text is not enough
avd open https://example.com
avd app install https://f-droid.org/F-Droid.apk
avd help
```

Skill installed at `~/.hermes/skills/zillion-avd/SKILL.md` — load it for the full workflow.

**If you are a cloud-sandbox agent** (no local `adb`), drive the PC over the bridge:

```bash
A="$HOME/Android/Sdk/platform-tools/adb -s emulator-5554"   # runs ON the PC via tunnel exec

# 0. agent mode is AUTOMATIC — the launcher applies it once boot completes
#    (manual fallback:  bash ~/Projects/workspace/project/avd/agent_mode.sh)
# 1. is it up?          $A devices
# 2. get root           $A root && $A shell id          # -> uid=0(root)
# 3. make /system RW    $A remount                       # -> "Overlayfs enabled. Remount succeeded"
# 4. screenshot         $A exec-out screencap -p > /tmp/shot.png
```

Cloud agents **cannot run `adb` locally** — every command must execute **on the PC**
through the bridge (see *Agent access* below).

---

## Hermes agents (on this PC)

The Hermes profiles on this machine (prima, fable, lumen, rivet, scope, zillion, …) reach the
emulator **directly** — same machine, so plain `adb`, no tunnel required.

**Interface:** `avd` (symlink `~/.local/bin/avd` → `…/project/avd/avd.sh`), plus the skill
`~/.hermes/skills/zillion-avd/SKILL.md`.

| Need | Command |
|---|---|
| be sure it's ready | `avd ensure` (idempotent: starts, waits for boot, roots, applies agent mode) |
| read the screen | `avd text` · `avd ui /tmp/ui.xml` · `avd shot /tmp/s.png` |
| act | `avd tap-text "Label"` · `avd tap X Y` · `avd type "…"` · `avd key back` · `avd swipe …` |
| browse | `avd open https://…` (page text comes back readable) |
| apps | `avd app install <apk\|URL>` · `launch` · `list` · `grant` · `clear` · `uninstall` |
| diagnose | `avd info` · `avd log 80` · `avd status` |
| device control | `avd root` · `avd prop set …` · `avd geo 14.676 121.044` · `avd record 10` |

**Why a helper instead of raw adb:** LLM agents fumble long `adb` pipelines and guess
coordinates. `avd tap-text` reads `bounds=` out of the UI tree itself and returns the *new* screen
text afterwards, so the agent can verify each step. `avd ensure` removes the "device is half-up"
failure mode entirely.

**Agent-mode state is applied automatically** by `agent_mode_waiter.sh` whenever the launcher
starts the device (log: `logs/agent_mode.log`, currently `6 passed, 0 failed`). Nothing to
remember after a PC reboot — but `avd ensure` re-asserts it anyway and is cheap (~7 s warm).

**Guardrails for agents:** one action then verify; prefer `avd text` over screenshots; keep each
command short (seconds); ask the user before destructive operations on real data; no Play Store
(APKs / F-Droid only).

---

## What this AVD is

| Property | Value |
|---|---|
| Name | `zillion_root_avd` |
| Device profile | Pixel 7 |
| Android | 16 (API **36**), `sdk_gphone64_x86_64` |
| Image | `system-images;android-36;google_apis;x86_64` — **userdebug**, `ro.debuggable=1` |
| Root | ✅ `adb root` → `uid=0(root)` · `su` at `/system/xbin/su` · `/system` + `/vendor` writable (overlayfs) |
| RAM / CPU | 4 GB / 4 cores |
| Data partition | 4 GB |
| Screen | 1080×2400 @ 420 dpi |
| Play Store | **disabled** (Play images are production builds and *cannot* be rooted) |
| ADB serial | `emulator-5554` |
| GPU mode | `swiftshader_indirect` (software) — **required on this machine** |

**Where things live (PC):**

| Path | What |
|---|---|
| `~/Android/Sdk/` | SDK, platform-tools (`adb`), emulator 37.1.11 |
| `~/Projects/workspace/project/avd/avd.sh` | **`avd` CLI** — one-command agent control (symlinked as `~/.local/bin/avd`) |
| `~/Projects/workspace/project/avd/start_zillion_root_avd.sh` | launcher (idempotent, safe to re-run) |
| `~/Projects/workspace/project/avd/agent_mode.sh` | makes a booted device agent-ready (root, no keyguard, Chrome flags) |
| `~/Projects/workspace/project/avd/agent_mode_waiter.sh` | waits for boot, then applies agent mode automatically |
| `~/Projects/workspace/project/avd/README.md` | this file |
| `~/.hermes/skills/zillion-avd/SKILL.md` | Hermes skill so on-PC agents discover all of the above |
| `~/Projects/workspace/project/avd/logs/` | emulator logs, `agent_mode.log`, captured screenshots |
| `~/.android/avd/zillion_root_avd.ini` | AVD definition (points at the data dir below) |
| `/home/limar01/wdchd320ggb/android_avd/zillion_root_avd.avd/` | real AVD data — on the **WD drive** (`ANDROID_AVD_HOME`), 170 GB free |
| `…/zillion_root_avd.avd/system.img.qcow2` | persisted `/system` modifications (see *Persistence*) |

---

## Start / stop

```bash
# start — the launcher returns immediately, then auto-applies agent mode after boot
~/Projects/workspace/project/avd/start_zillion_root_avd.sh

# watch the automatic agent-mode run
tail -f ~/Projects/workspace/project/avd/logs/agent_mode.log

# start a different AVD name
~/Projects/workspace/project/avd/start_zillion_root_avd.sh ai_pipeline_avd

# force a GPU mode
GPU_MODE=swiftshader_indirect ~/Projects/workspace/project/avd/start_zillion_root_avd.sh

# stop cleanly (cold stop)
$HOME/Android/Sdk/platform-tools/adb -s emulator-5554 emu kill

# wait for boot
until [ "$(adb -s emulator-5554 shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do sleep 5; done
```

**Agent mode is automatic.** The launcher spawns a detached waiter that polls `sys.boot_completed`
and then runs `agent_mode.sh` (root, `/system` remount, animations off, no keyguard, Chrome flags,
permissions). It also re-asserts agent mode when the AVD was already running. Log:
`logs/agent_mode.log`. Agents therefore never need to configure the device — only to check it:

```bash
grep -c '\[PASS\]' ~/Projects/workspace/project/avd/logs/agent_mode.log   # last run should be 6
```

Cold boot takes **~30–45 s** with software rendering. First-ever boot showed a harmless
*"Messages isn't responding"* dialog — ignore it (slow renderer, not a fault).

---

## Root & system modification

```bash
A="$HOME/Android/Sdk/platform-tools/adb -s emulator-5554"

$A root                  # restart adbd as root (uid=0)
$A remount               # enable overlayfs on /system  → "Remount succeeded"
$A shell id              # uid=0(root) gid=0(root) context=u:r:su:s0
$A shell getenforce      # Enforcing (expected; root works via the su context)

# write to the system partition
$A shell 'echo hello > /system/etc/mytest && cat /system/etc/mytest'

# system properties
$A shell 'setprop persist.sys.foo bar; getprop persist.sys.foo'
```

`adb remount` printed *"Now reboot your device for settings to take effect"* — the reboot is needed
once to flip the mount to overlayfs; after that writes work immediately and persist.

**Persistence (verified):**
- `/system` writes survive a **guest reboot** ✅
- and survive a **cold stop + restart** ✅ — stored in `system.img.qcow2` inside the AVD dir.

**Reset the system partition** (drop all `/system` mods):

```bash
adb -s emulator-5554 emu kill
rm -f /home/limar01/wdchd320ggb/android_avd/zillion_root_avd.avd/system.img.qcow2
```

**Full factory reset** (wipes user data too): `rm -f …/zillion_root_avd.avd/userdata-qemu.img`
(emulator recreates it on next start) — or recreate the AVD entirely.

---

## Full agent control — capability matrix (every row verified live)

Agents have **full control**: root, apps, browser, installs, UI automation, network.

| Capability | How | Verified |
|---|---|---|
| **Root shell** | `adb root` → `uid=0`; `su` at `/system/xbin/su`; `adb remount` opens `/system` | ✅ |
| **Modify system** | write `/system`, `/vendor`, set `persist.*` props — **persists across reboots** | ✅ |
| **Launch any app** | `am start` by intent/URL, or `monkey -p <pkg> -c android.intent.category.LAUNCHER 1` | ✅ (Chrome, F-Droid) |
| **Browse the web** | Chrome opens URLs; **page text is readable by agents** (renderer accessibility ON) | ✅ (`Example Domain` read from the a11y tree) |
| **Internet from apps** | guest has working network+DNS (ping 8.8.8.8 / example.com; F-Droid fetched its catalogue) | ✅ |
| **Install apps** | `adb install -r app.apk`, APKs fetched from the internet on the PC first, or F-Droid inside the device | ✅ (F-Droid 1.23.2 installed + launched) |
| **Read the screen** | `uiautomator dump` → parse `text=` + `bounds=` for any element | ✅ (used to tap Chrome's dialog) |
| **Drive the UI** | `input tap/swipe/text/keyevent` at coordinates taken from the dump | ✅ |
| **Watch it happen** | `screencap` (PNG) for frames, `screenrecord` (MP4) for motion | ✅ |
| **Automate UI reliably** | animations disabled, screen stays on, keyguard dismissed, permission dialogs pre-granted | ✅ |
| **Fake device state** | `emu geo fix`, `gsm call`, `dumpsys battery set level`, sensors | ✅ |
| **No per-command approval** | CF tunnel lane = gate-free `exec`; MQTT lane `pc` gates system-ish ops for Boss approval | ✅ |
| **See network traffic** | `net_proxy.sh start` → every proxied request as a JSON line: URL, method, status, **POST body** | ✅ (Chrome + F-Droid + Google apps) |

**What is NOT possible (be honest):**
- GUI clicking from the PC's desktop — agents act through `adb`, not by moving a mouse on Hyprland.
- Google Play Store apps — this is a `google_apis` (userdebug) image with Play disabled *by design*;
  that's exactly what makes root possible. Install APKs directly or use F-Droid.
- Very long single commands (>~90 s) — the tunnel returns HTTP 524; launch detached and poll.

## Network capture — see the URLs and POST data the device sends

Every proxied request becomes one JSON line in `~/arenabridge/net/flows.jsonl`
(method, URL, status, headers with auth-ish ones redacted, request body).

```bash
NP=~/Projects/workspace/project/avd/net_proxy.sh

$NP start            # CA into every mount namespace + mitmdump :8080 + device proxy + Chrome flags
$NP status           # is capture live? how many flows? is the CA app-visible?
$NP flows 20         # last 20: time, method, status, URL, bytes, BODY marker
$NP show             # full JSON of the newest flow (headers + body)
$NP grep password    # search URLs and bodies
$NP hosts 20         # 20 s tcpdump: hostnames only (works for cert-pinned apps too)
$NP stop             # proxy off — device back to direct networking
```

Verified live (2026-09-26):

| What | Evidence |
|---|---|
| Browser GET + POST body | Chrome → public form → flow `POST …/submit (89B) BODY`; server logged `body=username=boss&note=hello-from-emulator` |
| Real browser click | tap on the page's Submit button (278,909) → the same POST captured |
| Third-party app (F-Droid) | repo refresh: 100+ `https://f-droid.org/repo/...` URLs |
| Third-party app (Wikipedia) | `GET en.wikipedia.org/api/rest_v1/feed/...` **and** `POST intake-analytics.wikimedia.org/v1/events` — the analytics JSON body is decrypted (app version `WikipediaApp/r/50606`, session id, `app_open` event) |
| System/Google apps | `devicekey` POST 801 B, `google-ohttp-relay` POST 200 + body, `update.googleapis` POST 749 B, Chrome `optimizationguide` POST 21 679 B + protobuf body |
| Encrypted relays (OHTTP) | still visible as a flow (URL + sizes); body opaque by design |

**Honest limits — do not overstate coverage:**
- **Certificate-pinned apps** (banking, Meta, some Google) refuse the MITM CA; their hostnames are
  still visible with `net_proxy.sh hosts`.
- **QUIC / UDP** bypasses an HTTP proxy. Chrome is forced to TCP here (`--disable-quic`); apps that
  insist on QUIC may not be captured.
- **Private / loopback addresses are not proxied at all** (Chrome skips them) — for browser demos use a
  public URL (this setup uses a cloudflared quick tunnel in front of `echoform.py`).
- **Chrome's TLS verifier refuses the MITM CA** even when the system store trusts it, so Chrome runs
  with the test-only `--ignore-certificate-errors` flag (`net_proxy.sh chrome-mitm on|off`). Fine on
  this disposable AVD — never do this on a phone with real accounts.
- Capture works **only while mitmdump runs on the PC**. If the PC session dies, apps lose networking
  until `net_proxy.sh stop` clears the device proxy.

Demo helpers: `echoform.py` on :8099 (`/` = form, `/auto` = auto-POST page) + its cloudflared quick
tunnel (URL in `~/arenabridge/net/cf_8099.log`); `netlog.py` is the mitmproxy addon that writes the JSONL.

## UI automation recipe (read → decide → tap)

The pattern that works — never guess coordinates, always read them:

```bash
A="$HOME/Android/Sdk/platform-tools/adb -s emulator-5554"
$A shell uiautomator dump /sdcard/ui.xml && $A pull /sdcard/ui.xml /tmp/ui.xml
```

```python
# on the PC (or over the tunnel), find an element by its visible text
import re
xml = open('/tmp/ui.xml', errors='replace').read()
m = re.search(r'text="No thanks"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
if m:
    x1, y1, x2, y2 = map(int, m.groups())
    print((x1 + x2) // 2, (y1 + y2) // 2)      # -> tap here
```

```bash
$A shell input tap <x> <y>            # then re-dump to confirm what changed
```

Worked example from setup: Chrome showed a notifications promo over `example.com`.
The dump gave `No thanks` at `(564,1757)`; the tap cleared it and the page text became readable.

---

## Everyday recipes

```bash
A="$HOME/Android/Sdk/platform-tools/adb -s emulator-5554"
S=$HOME/Projects/workspace/project/avd/logs     # put artifacts here

# --- screenshots ---
$A exec-out screencap -p > $S/shot.png          # ~0.25–1.4 MB PNG

# --- screen recording (max 180 s) ---
$A shell screenrecord --time-limit 10 /sdcard/rec.mp4
$A pull /sdcard/rec.mp4 $S/rec.mp4

# --- UI hierarchy (for automated tapping) ---
$A shell uiautomator dump /sdcard/window.xml     # ~13 KB for the launcher
$A pull /sdcard/window.xml $S/window.xml

# --- input ---
$A shell input tap 540 1200                      # x y  (screen is 1080x2400)
$A shell input swipe 540 1800 540 600 300        # x1 y1 x2 y2 duration_ms
$A shell input text 'hello'                      # no spaces; use %s for spaces
$A shell input keyevent KEYCODE_HOME             # 3=HOME, 4=BACK, 26=POWER, 82=UNLOCK

# --- apps ---
$A install -r /path/to/app-debug.apk
$A shell pm list packages | grep -i myapp
$A shell monkey -p com.example.myapp -c android.intent.category.LAUNCHER 1   # launch
$A shell am force-stop com.example.myapp
$A shell pm clear com.example.myapp               # wipe app data
$A shell pm grant com.example.myapp android.permission.CAMERA   # skip the dialog

# --- logs & state ---
$A logcat -d -v brief | tail -100                 # dump (no follow)
$A logcat -c                                      # clear
$A shell dumpsys activity activities | grep -m3 mResumedActivity
$A shell dumpsys battery set level 42             # fake battery level
$A shell wm size                                  # 1080x2400
```

**Emulator console (via adb, no telnet needed):**

```bash
$A emu avd name            # confirm which AVD
$A emu geo fix 121.03 14.6 # GPS (lat lon) — Quezon City
$A emu gsm call 12345      # fake call
$A emu kill                # stop
```

---

## Agent access (how a cloud agent drives this from the sandbox)

The emulator is **not** reachable from the public internet. Agents reach it like this:

```
Cloud sandbox ──HMAC-signed HTTPS──▶ PC CF tunnel (zg :8788) ──▶ shell on Omarchy ──▶ adb ──▶ emulator
Cloud sandbox ──HMAC-signed MQTT───▶ PC worker v4.5.2 (lane pc) ─┘
```

**Rule 0: never assume a local `adb`.** There is no emulator inside the sandbox. Every `adb`
command is a *remote* command. Two lanes are available:

1. **CF tunnel (`zg`) — primary.** `exec` + `read`, no per-command approval. Use it for everything.
2. **MQTT lane `pc` — backup.** `worker.py` ops `exec` / `get_file` / `put_file` / `manifest`
   (paths relative to `SYNC_ROOT=/home/limar01`), and **system-ish ops gate on Boss approval**
   (`approve <id> allow|allow_all|deny`). Prefer the tunnel; use MQTT when the tunnel is down.

### Minimal agent helper (runs in the cloud sandbox)

```python
import os, json, time, uuid, hmac, hashlib, urllib.request

KEY  = open(os.path.expanduser("~/arenabridge/arenabridge.key")).read().strip()
BASE = open(os.path.expanduser("~/zillion_pc_cf_url.txt")).read().strip()   # PC tunnel URL
ADB  = "$HOME/Android/Sdk/platform-tools/adb -s emulator-5554"

def pc(cmd, timeout=60):
    """Run a shell command on the PC through the CF tunnel."""
    d = json.dumps({"op": "exec", "id": "x_" + uuid.uuid4().hex[:6],
                    "cmd": cmd, "timeout": timeout, "ts": time.time()},
                   separators=(",", ":"))
    env = json.dumps({"d": d, "h": hmac.new(KEY.encode(), d.encode(),
                                            hashlib.sha256).hexdigest()}).encode()
    req = urllib.request.Request(BASE + "/", data=env,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout + 15) as r:
        return json.loads(json.loads(r.read().decode())["d"])

def adb(args, timeout=60):
    """Run an adb command against the emulator and return stdout."""
    return pc(f"{ADB} {args}", timeout=timeout).get("output", "")
```

Discover the PC tunnel URL if you don't have it saved: it is the signed, retained `pc/pres`
(mq: `arenabridge/53cf4a5803c91726b892e5d0785085c6/pc/pres`) or the file
`~/arenabridge/pc_tunnel_url.txt` **on the PC itself**.

### Hard constraints (learned the hard way)

| Constraint | Detail |
|---|---|
| **Payload < ~90 s** | Cloudflare HTTP 524 kills the *response* at ~90 s, but the command **keeps running** on the PC. For anything longer (cold boot, `screenrecord`, big pulls) launch it detached and **poll** in later calls. |
| **Never `sleep` inside a payload** to cover a long wait — poll instead. |
| **KILL-LOOP / SELF-MATCH rule** | A `pgrep`/`grep` whose own command line contains the search string matches itself. Use anchored patterns (`pgrep -f '[e]mulator -avd'`) or scan `/proc/*/cmdline`. This bit us during setup. |
| **No GUI clicking** | Agents see the screen only via `screencap`; drive the UI with `input tap` / `uiautomator`, not by hoping a window is focused. |
| **One instance per AVD** | `multiinstance.lock` in the AVD dir prevents doubles. Check `adb devices` before launching. |
| **Disk** | AVD data lives on the WD drive (170 GB free). The root btrfs partition has only ~13 GB free — do **not** move AVDs there. |
| **PC reboot kills the emulator** | It is not a service. Relaunch with the start script (the AVD itself, including `/system` mods, persists). |
| **Broker quirk** | The PC worker may sit on a fallback broker (`broker.hivemq.com`) for ~2 min after start before rotating to `broker.emqx.io`; early MQTT probes may time out. Retry, or use the tunnel. |

### Typical agent flow

```text
1. pc("$ADB devices")                        → emulator-5554  device
2. pc("$ADB root")                           → restarting adbd as root
3. pc("$ADB remount")                        → Overlayfs enabled / Remount succeeded
4. pc("$ADB install -r /path/app-debug.apk") → Success
5. pc("$ADB shell monkey -p <pkg> … 1")      → launched
6. pc("$ADB exec-out screencap -p > /tmp/s.png")   (write to a file on the PC)
7. read /tmp/s.png back over the tunnel (base64 read op, ≤8 MB) and look at it
8. pc("$ADB logcat -d | tail -80")           → find the crash / log line
```

For long captures: `setsid nohup … &` on the PC, then poll `ls -l` / `tail` in follow-up calls.

---

## Verification log (2026-09-26, all live-checked through the tunnel)

| Check | Result |
|---|---|
| `adb shell id` | `uid=0(root) gid=0(root) groups=0(root),… context=u:r:su:s0` |
| Build | `userdebug`, `ro.debuggable=1`, SDK 36 (Android 16) |
| `su` binary | `/system/xbin/su` |
| `adb remount` | `Overlayfs enabled. Remount succeeded` |
| `/system` write | `SYSTEM_WRITE_OK` (file created + removed) |
| `/vendor` write | `VENDOR_RW_OK` |
| `persist.*` setprop | writable |
| `/system` write after **guest reboot** | persisted ✅ |
| `/system` write after **cold stop + restart** | persisted ✅ (`system.img.qcow2`) |
| `uiautomator dump` | OK (13,201 bytes) |
| `screenrecord --time-limit 3` | OK (61,160 bytes MP4) |
| `input tap` / `keyevent` | OK |
| Screen | `1080x2400`, density `420` |
| GPU | `-gpu host` **failed** on GTX 1060 + Xwayland → `swiftshader_indirect` used |
| Guest network | `ping 8.8.8.8` 0% loss; DNS resolves; F-Droid catalogue downloaded in-app ✅ |
| Install from internet | F-Droid 1.23.2 APK (12,426,276 B, sha256 `985f5181…`) downloaded on PC → `adb install` → launched ✅ |
| Chrome automation | first-run bypassed (`--disable-fre`) + `--force-renderer-accessibility` → page text readable (`Example Domain`) ✅ |
| UI-driven dialog dismissal | `uiautomator dump` → `No thanks` bounds `(449,1694)-(680,1820)` → tap `(564,1757)` → dialog gone ✅ |
| Agent-mode settings | animations 0, `stayon true`, `lockscreen.disabled=1`, permissions pre-granted ✅ |

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Emulator process alive but no device in `adb devices` | GPU init failed. Kill it and relaunch with `GPU_MODE=swiftshader_indirect`. |
| `Your GPU cannot be used for hardware rendering` | Expected on NVIDIA + Xwayland. Software rendering is the supported mode here. |
| `adb remount` → `Remount failed` | Either the emulator wasn't started with `-writable-system`, or the one-time reboot after the first remount hasn't happened yet. |
| `touch: '/system/…': Read-only file system` | Run `adb root` then `adb remount` first (and see the reboot note above). |
| `device offline` | Still booting. Poll `getprop sys.boot_completed`. |
| "X isn't responding" dialog right after boot | Software-renderer slowness. Dismiss with `input tap` or ignore. |
| Chrome shows a first-run / "make Chrome yours" / notifications promo | Run `agent_mode.sh` (sets `--disable-fre` + pre-grants notifications). A promo already on screen: dump the UI, find its button text, tap the bounds. |
| Web page text missing from `uiautomator dump` | Chrome needs `--force-renderer-accessibility` in `/data/local/tmp/chrome-command-line` (agent_mode.sh writes it). Then force-stop + relaunch Chrome. |
| Agent's taps land on the wrong thing / UI still animating | Run `agent_mode.sh` — it zeroes animation scales and dismisses the keyguard. |
| App installs but won't open | `pm list packages -3`, then `monkey -p <pkg> -c android.intent.category.LAUNCHER 1`; check `logcat -d | tail -50`. |
| Tunnel exec times out at ~90 s | Expected 524. The work continues on the PC — poll for results. |
| MQTT exec returns "LOCKED … approval" | Worker-side approval gate. Boss must reply `approve <id> allow`. Use the CF tunnel for gate-free ops. |
| AVD won't start: lock held | Another instance is running: `adb devices` / `emu kill`, or remove `multiinstance.lock` after killing qemu. |

---

## Recreating this AVD from scratch

```bash
S=$HOME/Android/Sdk
$S/cmdline-tools/latest/bin/sdkmanager "system-images;android-36;google_apis;x86_64"
echo no | $S/cmdline-tools/latest/bin/avdmanager create avd \
  -n zillion_root_avd -k "system-images;android-36;google_apis;x86_64" -d pixel_7
# then tweak config.ini: hw.ramSize=4096, hw.cpu.ncore=4, hw.keyboard=yes,
#                        hw.gpu.enabled=yes, hw.gpu.mode=host, PlayStore.enabled=false
$S/emulator/emulator -avd zillion_root_avd -writable-system -no-snapshot -no-boot-anim \
  -no-metrics -gpu swiftshader_indirect
```

> Use `google_apis` (userdebug) — **never** `google_apis_playstore`; Play images are production
> builds with `ro.debuggable=0` and cannot be rooted.

---

*Maintained by the Zillion PC lane. Companion files: `start_zillion_root_avd.sh`, `logs/`.
Doctrine: verify before claiming — every command in this README was executed on the live AVD.*

## Meta AI video factory (added 2026-09-26)

Generate and extend Meta AI videos inside Messenger, then assemble them offline. Full QA write-up:
`META_AI_LONG_VIDEO_QA.md`.

```sh
# one clip (type -> send -> wait -> harvest into ~/factory/clips + manifest.jsonl)
sh metaai_gen2.sh --send "a red vintage motorcycle on a rainy Tokyo street at night, cinematic" 300
# composer already holds the text (e.g. an "extend" prompt you typed)
sh metaai_gen2.sh --send-existing 300

# batch: one prompt per line -> clips -> one long video (optional target length in seconds)
sh factory_run.sh prompts.txt out/film.mp4 60
# ... and narrate it: 4th arg = narration text file (TTS -> bed -> mix -> mux, all offline)
sh factory_run.sh prompts.txt out/film_narrated.mp4 60 narration.txt

# sound on its own (AI audio engine, stage 1 of the pipeline)
sh audio_engine.sh check                          # what TTS/ffmpeg pieces exist on this host
sh audio_engine.sh tts "line one. line two." out/voice.wav
sh audio_engine.sh bed out/bed.wav 60 room        # room tone / wind bed, N seconds
sh audio_engine.sh mux film.mp4 out/voice.wav out/narrated.mp4 replace
sh audio_engine.sh lipsync                        # stage 2 — exits 10 with the Wav2Lip plan

# finish a film so real players behave: faststart is mandatory, motion kills the "frozen" look
sh factory_polish.sh check    out/film.mp4                       # codecs + faststart=YES/NO
sh factory_polish.sh faststart out/film.mp4 out/film_web.mp4     # lossless remux (moov -> front)
sh factory_polish.sh motion   out/film.mp4 out/film_move.mp4 1.12 26 18
sh factory_polish.sh preview  out/film_move.mp4 out/prev.mp4 360

# stitch existing clips (normalises size/fps/SAR, adds silent AAC when a clip has no audio)
sh factory_stitch.sh out/ladder.mp4 clips/*.mp4
TARGET=60 sh factory_stitch.sh out/film.mp4 clips/*.mp4     # repeat until >= 60 s, then ffmpeg -t 60
```

Measured facts (624x624, 24 fps, silent, H.264): fresh clip 5.208 s; extend +3.83 s three times
(9.04 / 12.88 / 16.71), then +7.67 (24.38), then a plateau at ~24.5 s. Longer needs stitching.

Sound: Meta AI clips are silent — narration/ambience come from `audio_engine.sh` (espeak-ng here;
piper/Coqui/cloud are drop-in upgrades) and are muxed onto the stitched film. Verified end to end:
60.209 s narrated film and a 40.315 s four-scene narrated film (batch: 5 prompts, 12 s apart, 95-108 s
wall time each, zero failures, ~10 min total rig time).

Both `.sh` harnesses + `factory_run.sh` are agent-operable: no downloads, POSIX sh + adb + ffmpeg only.

Rules that matter (learned the hard way, all in the QA doc):
1. tap the Send button via the uiautomator tree — a multi-line prompt moves it ~120 px down;
2. detect a new clip by diffing the ExoPlayer cache, not by counting nodes (the chat list is virtualised);
3. **press Play on the newest bubble** — generated reels are not downloaded until played;
4. the capture rig (net_proxy.sh) must be OFF for playback: reels show "Couldn't play reel" while mitm is on;
5. never pull a cache file while it is still growing — settle-check, then verify frame counts;
6. run long waits detached (`setsid nohup ... > log`) because a >2 min synchronous tunnel call can 524;
7. **finish with `factory_polish.sh`**: ffmpeg writes `moov` at the END of the file by default, so a
   browser/streamed player shows a **still frame while the audio plays** — always `faststart` (the
   factory scripts now pass `-movflags +faststart` and `factory_run.sh` verifies it). If the picture is
   still lifeless, that is the *content*: Meta AI's extend tail is near-static — use
   `factory_polish.sh motion` (gentle pan/zoom) or `MOTION=1` on `factory_run.sh`;
8. generation is **stochastic** — the same prompt twice gives different bytes (`sha16` differs), so log
   `sha16` per clip in `manifest.jsonl` and never dedupe or re-fetch by prompt text.
