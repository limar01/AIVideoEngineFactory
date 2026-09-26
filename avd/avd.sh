#!/usr/bin/env bash
# avd — one-command control of the rooted Android emulator, built for LLM/Hermes agents.
#
#   avd <command> [args]
#
# Design rules (agent-first):
#   * every command is ONE line, deterministic, and prints compact plain text
#   * no colours, no pagers, non-zero exit codes on failure
#   * never guess coordinates: `avd tap-text` reads them from the UI tree itself
#   * idempotent: `avd ensure` always leaves a rooted, agent-mode device
#
# Run `avd help` for the command list.
set -uo pipefail

S="${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}"
ADB="$S/platform-tools/adb"
SERIAL="${AVD_SERIAL:-emulator-5554}"
AVD_NAME="${AVD_NAME:-zillion_root_avd}"
AVD_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
TMP="${AVD_TMP:-/tmp}"
A="$ADB -s $SERIAL"

die() { echo "ERROR: $*" >&2; exit 1; }
adbq() { timeout 60 $A "$@" 2>/dev/null; }

need_device() {
  $ADB devices 2>/dev/null | awk 'NR>1 && $2=="device"' | grep -q "$SERIAL" \
    || die "no device on $SERIAL — run: avd ensure"
}

# ---------------------------------------------------------------- status/ensure
cmd_status() {
  local state="stopped"
  $ADB devices 2>/dev/null | awk 'NR>1' | grep -q "$SERIAL" && state="present"
  local boot anim
  boot=$(adbq shell getprop sys.boot_completed | tr -d '\r')
  anim=$(adbq shell settings get global window_animation_scale | tr -d '\r')
  local root_uid
  root_uid=$(adbq shell id 2>/dev/null | tr -d '\r' | cut -c1-24)
  local agent_pass="never"
  [ -f "$AVD_DIR/logs/agent_mode.log" ] && \
    agent_pass=$(grep -o 'agent_mode done: [0-9]* passed, [0-9]* failed' "$AVD_DIR/logs/agent_mode.log" 2>/dev/null | tail -1 | sed 's/agent_mode done: //')
  echo "state=$state boot=${boot:-none} serial=$SERIAL"
  echo "identity=${root_uid:-unknown}"
  echo "animations=$([ "$anim" = "0" ] && echo off || echo "${anim:-?}")  last_agent_mode=${agent_pass:-never}"
  [ "$boot" = "1" ] || echo "hint: run 'avd ensure' to start/wait for a ready device"
}

cmd_ensure() {
  need_boot=0
  if ! $ADB devices 2>/dev/null | awk 'NR>1' | grep -q "$SERIAL"; then
    echo "starting $AVD_NAME ..."
    bash "$AVD_DIR/start_zillion_root_avd.sh" "$AVD_NAME" >/dev/null 2>&1 || die "launcher failed"
    need_boot=1
  fi
  for i in $(seq 1 60); do
    b=$(adbq shell getprop sys.boot_completed | tr -d '\r')
    [ "$b" = "1" ] && break
    sleep 3
  done
  [ "${b:-}" = "1" ] || die "device never finished booting"
  # idempotent — guarantees root + agent-mode state even if the waiter missed it
  bash "$AVD_DIR/agent_mode.sh" "$SERIAL" 2>&1 | sed -n 's/^\(.*\)$/\1/p'
  local uid; uid=$(adbq shell id | tr -d '\r' | cut -c1-20)
  echo "ready: $SERIAL $uid"
  case "$uid" in *uid=0*) ;; *) echo "WARNING: not root — is the image google_apis (userdebug)?" ;; esac
}

cmd_stop() { $ADB -s "$SERIAL" emu kill 2>&1 | tail -1; }

# ---------------------------------------------------------------- observe
_uidump() {  # $1 = local destination (retries — a screen mid-transition can fail)
  need_device
  local remote="/sdcard/.avd_ui_$$.xml" attempt
  for attempt in 1 2 3 4; do
    adbq shell uiautomator dump "$remote" >/dev/null 2>&1
    adbq shell cat "$remote" > "$1" 2>/dev/null
    if [ -s "$1" ] && grep -q 'bounds=' "$1" 2>/dev/null; then
      adbq shell rm -f "$remote" >/dev/null 2>&1
      return 0
    fi
    sleep 2
  done
  adbq shell rm -f "$remote" >/dev/null 2>&1
  die "UI dump failed after 4 attempts (screen off or no window?) — try: avd key unlock"
}

_texts() {  # print unique visible texts from a dump
  python3 - "$1" <<'PY'
import re, sys
xml = open(sys.argv[1], errors='replace').read()
seen, out = set(), []
for t in re.findall(r'text="([^"]+)"', xml):
    t = t.strip()
    if t and t not in seen:
        seen.add(t); out.append(t)
print(" | ".join(out[:40]))
PY
}

cmd_text() { local f="$TMP/.avd_ui_$$.xml"; _uidump "$f"; _texts "$f"; rm -f "$f"; }

cmd_ui() {
  local out="${1:-$TMP/avd_ui.xml}"; _uidump "$out"; echo "$out"
  echo "elements=$(grep -o 'bounds=' "$out" | wc -l) bytes=$(wc -c < "$out")"
}

cmd_shot() {
  local out="${1:-$TMP/avd_shot.png}"
  need_device
  $A exec-out screencap -p > "$out" 2>/dev/null
  [ -s "$out" ] || die "screenshot failed"
  echo "$out $(wc -c < "$out") bytes"
}

cmd_info() {
  need_device
  echo "model=$(adbq shell getprop ro.product.model | tr -d '\r') api=$(adbq shell getprop ro.build.version.sdk | tr -d '\r')"
  echo "screen=$(adbq shell wm size | tr -d '\r') density=$(adbq shell wm density | tr -d '\r')"
  echo "uptime=$(adbq shell uptime | tr -d '\r')"
  echo "battery=$(adbq shell dumpsys battery | grep -m1 level | tr -d '\r ')"
  echo "focus=$(adbq shell dumpsys window | grep -m1 mCurrentFocus | tr -d '\r' | cut -c1-90)"
}

# ---------------------------------------------------------------- interact
cmd_tap() { need_device; [ $# -eq 2 ] || die "usage: avd tap X Y"; adbq shell input tap "$1" "$2" >/dev/null; sleep 1; echo "tapped $1 $2"; cmd_text; }

cmd_tap_text() {
  need_device
  [ $# -ge 1 ] || die 'usage: avd tap-text "Label"'
  local label="$*" f="$TMP/.avd_ui_$$.xml"
  _uidump "$f"
  local coords
  coords=$(python3 - "$f" "$label" <<'PY'
import re, sys
xml, label = open(sys.argv[1], errors='replace').read(), sys.argv[2].lower()
pat = r'text="([^"]*)"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"'
best = None
for txt, x1, y1, x2, y2 in re.findall(pat, xml):
    tl = txt.lower()
    if tl == label: best = (x1, y1, x2, y2); break
    if best is None and (label in tl or tl in label) and txt.strip():
        best = (x1, y1, x2, y2)
if not best:
    # try reversed attribute order: bounds before text
    pat2 = r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="([^"]*)"'
    for x1, y1, x2, y2, t in re.findall(pat2, xml):
        tl = t.lower()
        if tl == label: best = (x1, y1, x2, y2); break
        if best is None and (label in tl or tl in label) and t.strip():
            best = (x1, y1, x2, y2)
if not best: sys.exit(3)
x1, y1, x2, y2 = map(int, best)
print((x1+x2)//2, (y1+y2)//2)
PY
) || { rm -f "$f"; die "no element matching '$label'"; }
  rm -f "$f"
  adbq shell input tap $coords >/dev/null
  sleep 2
  echo "tapped '$label' at $coords"
  cmd_text
}

cmd_type() {
  need_device
  [ $# -ge 1 ] || die 'usage: avd type "text"'
  local t="${*// /%s}"     # adb input text needs %s for spaces
  adbq shell input text "$t" >/dev/null
  echo "typed: $*"
}

cmd_key() {
  need_device
  case "${1:-}" in
    home) K=3 ;; back) K=4 ;; enter) K=66 ;; tab) K=61 ;;
    recents) K=187 ;; power) K=26 ;; unlock) K=82 ;;
    up) K=19 ;; down) K=20 ;; left) K=21 ;; right) K=22 ;;
    *) die "keys: home back enter tab recents power unlock up down left right" ;;
  esac
  adbq shell input keyevent "$K" >/dev/null
  sleep 1; echo "key $1 sent"
}

cmd_swipe() {
  need_device
  [ $# -ge 4 ] || die "usage: avd swipe X1 Y1 X2 Y2 [MS]"
  adbq shell input swipe "$1" "$2" "$3" "$4" "${5:-300}" >/dev/null
  echo "swiped $1,$2 -> $3,$4"
}

cmd_open() {
  need_device
  [ $# -ge 1 ] || die "usage: avd open URL"
  local url="$1"; case "$url" in http*) ;; *) url="https://$url" ;; esac
  adbq shell am start -a android.intent.action.VIEW -d "$url" >/dev/null
  sleep 6
  echo "opened $url"
  cmd_text
}

# ---------------------------------------------------------------- apps
cmd_app() {
  need_device
  local sub="${1:-list}"; shift || true
  case "$sub" in
    list)
      adbq shell pm list packages -3 | sed 's/^package://' | tr '\n' ' '; echo ;;
    launch)
      [ $# -ge 1 ] || die "usage: avd app launch <package|label>"
      local pkg="$1"
      if ! adbq shell pm list packages | grep -q "package:$pkg"; then
        pkg=$(adbq shell pm list packages -3 | sed 's/^package://' | grep -i "$1" | head -1)
        [ -n "$pkg" ] || die "no installed package matching '$1'"
      fi
      adbq shell monkey -p "$pkg" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
      sleep 5; echo "launched $pkg"; cmd_text ;;
    install)
      [ $# -ge 1 ] || die "usage: avd app install <local.apk|URL>"
      local src="$1"
      case "$src" in
        http*)
          local dl="$TMP/avd_dl_$(basename "$src" | tr -dc 'A-Za-z0-9._-')"
          echo "downloading $src"
          curl -fsSL --max-time 120 -o "$dl" "$src" || die "download failed"
          src="$dl" ;;
      esac
      [ -f "$src" ] || die "apk not found: $src"
      echo "installing $(basename "$src") ($(wc -c < "$src") bytes)"
      $A install -r "$src" 2>&1 | tail -2
      rm -f "$TMP"/avd_dl_* 2>/dev/null ;;
    uninstall) adbq shell pm uninstall "$2" | tr -d '\r' ;;
    clear)     adbq shell pm clear "$2" | tr -d '\r' ;;
    stop)      adbq shell am force-stop "$2"; echo "stopped $2" ;;
    grant)     adbq shell pm grant "$2" "$3"; echo "granted $3 -> $2" ;;
    *) die "app subcommands: list launch install uninstall clear stop grant" ;;
  esac
}

# ---------------------------------------------------------------- device utils
cmd_root() {
  need_device
  $A root 2>&1 | tail -1
  sleep 3
  $A remount 2>&1 | tail -1
  echo "id=$(adbq shell id | tr -d '\r' | cut -c1-24)"
}

cmd_log() {
  need_device
  adbq logcat -d -v brief | tail -"${1:-60}"
}

cmd_prop() {
  need_device
  case "${1:-get}" in
    get) adbq shell getprop "$2" | tr -d '\r' ;;
    set) adbq shell setprop "$2" "$3"; echo "set $2=$3" ;;
    *) die "usage: avd prop get NAME | avd prop set NAME VALUE" ;;
  esac
}

cmd_geo() {
  need_device
  [ $# -eq 2 ] || die "usage: avd geo LAT LON"
  $A emu geo fix "$2" "$1" >/dev/null 2>&1
  echo "gps set to $1,$2"
}

cmd_record() {
  need_device
  local secs="${1:-10}" out="${2:-$TMP/avd_record.mp4}"
  adbq shell screenrecord --time-limit "$secs" /sdcard/.avd_rec.mp4 >/dev/null 2>&1
  $A pull /sdcard/.avd_rec.mp4 "$out" >/dev/null 2>&1
  adbq shell rm -f /sdcard/.avd_rec.mp4 >/dev/null 2>&1
  [ -s "$out" ] || die "recording failed"
  echo "$out $(wc -c < "$out") bytes"
}

cmd_push() { need_device; $A push "$1" "$2" 2>&1 | tail -1; }
cmd_pull() { need_device; $A pull "$1" "$2" 2>&1 | tail -1; }

cmd_help() {
  cat <<'EOF'
avd — control the rooted Android emulator (agent-friendly)

  avd ensure                     start if needed, wait for boot, apply agent mode, prove root
  avd status                     state / identity / agent-mode status
  avd stop                       shut the emulator down

  avd text                       visible screen text (read this instead of screenshots when you can)
  avd ui [file]                  full UI tree XML (elements + bounds)
  avd shot [file]                screenshot PNG -> path
  avd info                       model, api, screen, density, uptime, battery, focused window
  avd log [lines]                recent logcat

  avd tap X Y                    tap coordinates
  avd tap-text "Label"           find an element by its text, tap its centre, return new screen text
  avd type "text"                type into the focused field
  avd key home|back|enter|tab|recents|power|unlock|up|down|left|right
  avd swipe X1 Y1 X2 Y2 [MS]
  avd open URL                   open in Chrome (page text becomes readable)

  avd app list                   third-party packages
  avd app launch <pkg|label>     launch app, then return screen text
  avd app install <apk|URL>      install from a local APK or a download URL
  avd app uninstall|clear|stop|grant <pkg> [perm]

  avd root                       adb root + remount /system
  avd prop get NAME | set NAME VALUE
  avd geo LAT LON                fake GPS (e.g. avd geo 14.676 121.044)
  avd record [secs] [file]       screen recording
  avd push <local> <remote> | avd pull <remote> <local>

Environment: AVD_NAME, AVD_SERIAL, ANDROID_SDK_ROOT
EOF
}

# ---------------------------------------------------------------- dispatch
case "${1:-help}" in
  status)   shift; cmd_status "$@" ;;
  ensure)   shift; cmd_ensure "$@" ;;
  stop)     shift; cmd_stop "$@" ;;
  text)     shift; cmd_text "$@" ;;
  ui)       shift; cmd_ui "$@" ;;
  shot)     shift; cmd_shot "$@" ;;
  info)     shift; cmd_info "$@" ;;
  tap)      shift; cmd_tap "$@" ;;
  tap-text) shift; cmd_tap_text "$@" ;;
  type)     shift; cmd_type "$@" ;;
  key)      shift; cmd_key "$@" ;;
  swipe)    shift; cmd_swipe "$@" ;;
  open)     shift; cmd_open "$@" ;;
  app)      shift; cmd_app "$@" ;;
  root)     shift; cmd_root "$@" ;;
  log)      shift; cmd_log "$@" ;;
  prop)     shift; cmd_prop "$@" ;;
  geo)      shift; cmd_geo "$@" ;;
  record)   shift; cmd_record "$@" ;;
  push)     shift; cmd_push "$@" ;;
  pull)     shift; cmd_pull "$@" ;;
  help|-h|--help) cmd_help ;;
  *) echo "unknown command: $1" >&2; cmd_help; exit 2 ;;
esac
