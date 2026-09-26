#!/usr/bin/env bash
# net_proxy.sh — capture what the emulator sends on the network (URLs + POST data).
#
#   net_proxy.sh start [PORT]      install CA + start proxy + point the device at it
#   net_proxy.sh stop              stop proxy + unset the device proxy (device keeps working)
#   net_proxy.sh status            is capture live? flows? is the CA app-visible?
#   net_proxy.sh flows [N]         last N flows, one line each (default 20)
#   net_proxy.sh show [N]          full JSON of flow N (default: the latest)
#   net_proxy.sh grep PATTERN      flows whose URL/body matches PATTERN
#   net_proxy.sh clear             truncate the flow log
#   net_proxy.sh hosts [SECONDS]   tcpdump fallback: DNS names only (works for pinned apps)
#   net_proxy.sh chrome-mitm on|off  Chrome accepts/refuses the MITM cert (test-only flag)
#
# Android 14+ reality, learned the hard way:
#   * apps read CA certs from the read-only Conscrypt APEX store, NOT /system/etc/security/cacerts
#   * a plain `adb shell mount -o bind` lands in the init namespace only — useless for apps
#   * every app has its own mount namespace; the CA has to be mounted in ALL of them
#   * source must be a SELinux-visible store (/data/local/tmp = shell_data_file -> avc denied)
#   * Chrome's TLS verifier refuses even a system-trusted MITM cert; on this test AVD Chrome
#     runs with --ignore-certificate-errors --disable-quic (toggle: chrome-mitm)
#
# Honest limits: certificate-pinned apps (banking, Meta, some Google) refuse the MITM cert —
# their hostnames still show via `net_proxy.sh hosts`. QUIC/UDP bypasses an HTTP proxy.
set -uo pipefail

S="${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}"
ADB="$S/platform-tools/adb"
SERIAL="${AVD_SERIAL:-emulator-5554}"
A="$ADB -s $SERIAL"
AVD_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
NET_DIR="${AVD_NET_DIR:-$HOME/arenabridge/net}"
LOG="${NET_DIR}/flows.jsonl"
MITM_LOG="${NET_DIR}/mitm.log"
PIDFILE="${NET_DIR}/mitmdump.pid"
CA_PEM="$HOME/.mitmproxy/mitmproxy-ca-cert.pem"
STORE=/system/etc/security/cacerts            # writable, SELinux-labelled, usable as bind source
APEX=/apex/com.android.conscrypt/cacerts      # what apps actually read
PORT="${2:-8080}"
HOST_ALIAS="10.0.2.2"          # from inside the emulator, this is the host's loopback

die() { echo "ERROR: $*" >&2; exit 1; }
echo_base() { echo "host_proxy=${HOST_ALIAS}:${PORT} log=${LOG}"; }
ca_hash() { openssl x509 -inform PEM -subject_hash_old -in "$CA_PEM" 2>/dev/null | head -1; }
zygote_pid() { $A shell "pidof zygote64 2>/dev/null" | tr -d '\r' | awk '{print $1}'; }

# ---- CA store ---------------------------------------------------------------
prepare_store() {
  local h; h="$(ca_hash)"; [ -n "$h" ] || die "cannot compute Android cert hash from $CA_PEM"
  [ -f "$CA_PEM" ] || die "no mitmproxy CA at $CA_PEM (run 'mitmdump -p 18080' once)"
  $A root >/dev/null 2>&1; sleep 2
  $A remount >/dev/null 2>&1
  # full AOSP store + our CA, then fix the SELinux label of the file we added
  $A shell "mkdir -p $STORE && cp -fn $APEX/*.0 $STORE/ 2>/dev/null; chmod 644 $STORE/*.0 2>/dev/null" >/dev/null
  $A push "$CA_PEM" "$STORE/$h.0" >/dev/null 2>&1 || die "push of CA to $STORE failed"
  $A shell "chmod 644 $STORE/$h.0; chcon u:object_r:system_security_cacerts_file:s0 $STORE/$h.0 2>/dev/null" >/dev/null
  local lab; lab=$($A shell "ls -Z $STORE/$h.0" | tr -d '\r')
  case "$lab" in
    *system_security_cacerts_file*) : ;;
    *) die "CA file has the wrong SELinux label: $lab" ;;
  esac
  echo "store ready: $STORE/$h.0 ($(echo "$lab" | awk '{print $1}'))"
}

# mount that store over the APEX path in EVERY distinct mount namespace on the device
mount_everywhere() {
  $A shell 'setenforce 0
seen=""; n=0
for p in /proc/[0-9]*; do
  pid=${p#/proc/}
  ns=$(readlink $p/ns/mnt 2>/dev/null) || continue
  case " $seen " in *" $ns "*) continue;; esac
  seen="$seen $ns"
  nsenter -t $pid -m -- mount -o bind /system/etc/security/cacerts /apex/com.android.conscrypt/cacerts 2>/dev/null && n=$((n+1))
done
echo "namespaces_mounted=$n"
setenforce 1' | tr -d '\r'
}

# real verification: is the APEX store, as an APP sees it, a bind of our store and does it hold our cert?
ca_app_visible() {
  local h zpid file_ok root; h="$(ca_hash)"; zpid="$(zygote_pid)"
  [ -n "$zpid" ] || return 1
  # functional test first: our CA must be visible inside the store APPS read
  file_ok=$($A shell "test -f /proc/$zpid/root$APEX/$h.0 && echo yes" 2>/dev/null | tr -d '\r')
  [ "$file_ok" = yes ] || { echo "  CA $h.0 is not visible in the app-visible store" >&2; return 1; }
  # and that store must be a bind of our writable copy (mountinfo field 4 = bind source)
  root=$($A shell "nsenter -t $zpid -m -- sh -c 'grep -m1 conscrypt /proc/self/mountinfo'" 2>/dev/null | tr -d '\r' | awk '{print $4}')
  [ "$root" = "$STORE" ] || echo "  note: app-visible store bind source is '$root' (expected $STORE)" >&2
  return 0
}

cert_denials() { $A shell "dmesg 2>/dev/null | grep -c 'avc:  *denied'" | tr -d '\r'; }

install_cert() {
  prepare_store || return 1
  echo "  $(mount_everywhere)"
  if ca_app_visible; then
    echo "CA active for apps ($(ca_hash).0, mounted in all namespaces)"
    return 0
  fi
  echo "CA not visible to apps yet — a framework restart is the reliable fix"
  return 10
}

restart_framework() {
  $A shell 'setsid nohup sh -c "stop; sleep 2; start" >/dev/null 2>&1 &' >/dev/null 2>&1
  echo "framework restarting — poll: adb shell getprop sys.boot_completed, then re-run net_proxy.sh start"
}

# ---- proxy ------------------------------------------------------------------
start_proxy() {
  pkill -f "mitmdump .*--listen-port $PORT" 2>/dev/null
  mkdir -p "$NET_DIR"; : > "$MITM_LOG"
  setsid nohup mitmdump --listen-host 0.0.0.0 --listen-port "$PORT" \
    -s "$AVD_DIR/netlog.py" --set flow_detail=0 --set termlog_verbosity=warn \
    >>"$MITM_LOG" 2>&1 </dev/null &
  echo $! > "$PIDFILE"
  sleep 3
  ss -ltn 2>/dev/null | grep -q ":${PORT} " || { tail -5 "$MITM_LOG" >&2; die "mitmdump did not start"; }
  echo "mitmdump listening on 0.0.0.0:${PORT} (pid $(cat "$PIDFILE"))"
}

point_device() {
  $A shell "settings put global http_proxy ${HOST_ALIAS}:${PORT}"
  local got; got=$($A shell settings get global http_proxy | tr -d '\r')
  [ "$got" = "${HOST_ALIAS}:${PORT}" ] || die "device proxy not set (got '$got')"
  echo "device proxy -> ${HOST_ALIAS}:${PORT}"
  $A shell am force-stop com.android.chrome >/dev/null 2>&1
}

# Chrome verifier is stricter than the platform: it refuses the MITM CA even when the system
# store trusts it. On this disposable test AVD we pass Chrome its own switch (test-only!).
chrome_mitm() {
  local flags="--disable-fre --no-first-run --no-default-browser-check --disable-search-engine-choice-screen --force-renderer-accessibility"
  case "${1:-on}" in
    on)  $A shell "echo 'chrome $flags --ignore-certificate-errors --disable-quic' > /data/local/tmp/chrome-command-line"
         $A shell "chmod 644 /data/local/tmp/chrome-command-line"
         echo "Chrome: accepts capture CA, QUIC off (test-only --ignore-certificate-errors)" ;;
    off) $A shell "echo 'chrome $flags' > /data/local/tmp/chrome-command-line"
         $A shell "chmod 644 /data/local/tmp/chrome-command-line"
         echo "Chrome: strict TLS verification restored (it will refuse the MITM cert)" ;;
    *) die "usage: net_proxy.sh chrome-mitm on|off" ;;
  esac
  $A shell am force-stop com.android.chrome >/dev/null 2>&1
}

# ---- fallback for apps that pin certs or use QUIC ---------------------------
hosts_fallback() {
  local secs="${1:-20}" out="$NET_DIR/hosts.txt"
  mkdir -p "$NET_DIR"
  echo "listening ${secs}s for DNS lookups on the device (names only, no bodies)…"
  $A shell "timeout $secs /system/bin/tcpdump -i any -nn -l -s0 'udp port 53'" > "$out" 2>/dev/null
  grep -aoE '([a-z0-9_-]+\.)+[a-z]{2,}' "$out" \
    | sed 's/\.$//' | grep -v '^[0-9.\-]*$' | sort | uniq -c | sort -rn | head -40
}

case "${1:-status}" in
  start)
    rc=0
    install_cert || rc=$?
    start_proxy || exit 1
    if [ "$rc" = "10" ]; then
      restart_framework
      echo "after boot completes, re-run: net_proxy.sh start   (framework restart was needed)"
      echo_base; exit 0
    fi
    point_device
    chrome_mitm on
    echo_base
    echo "capture is LIVE — try: avd open https://example.com  |  avd app launch <pkg>  |  net_proxy.sh flows"
    echo "NOTE: while this is on, apps need mitmdump alive. If the PC session dies: net_proxy.sh stop"
    ;;
  stop)
    $A shell "settings put global http_proxy :0" >/dev/null 2>&1
    $A shell "settings delete global http_proxy" >/dev/null 2>&1
    [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null
    pkill -f "mitmdump .*--listen-port $PORT" 2>/dev/null
    rm -f "$PIDFILE"
    echo "capture stopped (device proxy cleared, mitmdump killed) — device traffic is direct again"
    ;;
  status)
    local_pid="$(cat "$PIDFILE" 2>/dev/null || echo -)"
    listening=$(ss -ltn 2>/dev/null | grep -c ":${PORT} ")
    flows=$([ -f "$LOG" ] && wc -l < "$LOG" || echo 0)
    echo "mitmdump_pid=$local_pid listening=$listening flows=$flows port=$PORT"
    echo "device_proxy=$($A shell settings get global http_proxy 2>/dev/null | tr -d '\r')"
    if ca_app_visible; then echo "ca_app_visible=yes"; else echo "ca_app_visible=no"; fi
    echo "selinux_avc_denials_total=$(cert_denials)"
    ;;
  flows)
    [ -f "$LOG" ] || die "no flows yet ($LOG)"
    python3 - "$LOG" "${2:-20}" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
for r in rows[-int(sys.argv[2]):]:
    body = " BODY" if r.get("req_body") else ""
    print(f"{r['ts']}  {r['method']:5s} {r['status']}  {r['url'][:110]}  ({r['resp_bytes']}B){body}")
PY
    ;;
  show)
    [ -f "$LOG" ] || die "no flows yet ($LOG)"
    python3 - "$LOG" "${2:-}" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
if not rows:
    sys.exit("no flows")
r = rows[-1] if not sys.argv[2] else rows[int(sys.argv[2]) - 1]
print(json.dumps(r, indent=2, ensure_ascii=False))
PY
    ;;
  grep)
    [ -n "${2:-}" ] || die "usage: net_proxy.sh grep PATTERN"
    [ -f "$LOG" ] || die "no flows yet ($LOG)"
    python3 - "$LOG" "$2" <<'PY'
import json, sys
pat = sys.argv[2].lower()
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
hits = [r for r in rows if pat in json.dumps(r).lower()]
print(f"{len(hits)} match(es) of {len(rows)} flows")
for r in hits[-15:]:
    print(f"{r['ts']}  {r['method']:5s} {r['status']}  {r['url'][:110]}")
    if r.get("req_body"):
        print("    body:", r["req_body"][:200].replace("\n", " "))
PY
    ;;
  hosts) hosts_fallback "${2:-20}" ;;
  chrome-mitm) chrome_mitm "${2:-on}" ;;
  clear) : > "$LOG"; echo "flow log cleared" ;;
  *) sed -n '2,20p' "$0"; exit 2 ;;
esac
