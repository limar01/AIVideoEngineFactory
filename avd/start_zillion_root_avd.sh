#!/usr/bin/env bash
# zillion_root_avd launcher — Pixel 7 / Android 16 (API 36) google_apis x86_64 (userdebug = rootable)
#
#   Usage: ./start_zillion_root_avd.sh [AVD_NAME]
#   Stop:  adb -s emulator-5554 emu kill
#
# Behaviour:
#   1. launches the AVD detached (software GPU by default — this host needs it)
#   2. spawns agent_mode_waiter.sh, which waits for boot and then applies agent mode
#      (root, /system remount, no keyguard, animations off, Chrome automation flags)
#   3. if the AVD is already running it just re-asserts agent mode and exits
#
# Logs: logs/<avd>.log (emulator) · logs/agent_mode.log (waiter + agent mode)
set -uo pipefail

S="${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}"
AVD="${1:-zillion_root_avd}"
SERIAL="${SERIAL:-emulator-5554}"
DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$DIR/logs"
LOG="$DIR/logs/${AVD}.log"
AMLOG="$DIR/logs/agent_mode.log"
WAITER="$DIR/agent_mode_waiter.sh"

if [ ! -f "$WAITER" ]; then
  echo "FATAL: $WAITER missing (it applies agent mode after boot)"; exit 2
fi
chmod +x "$WAITER" "$DIR/agent_mode.sh" 2>/dev/null

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}"
export DISPLAY="${DISPLAY:-:0}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

# --- already running? (scan /proc — never matches this script's own cmdline) --
running=0
for p in /proc/[0-9]*; do
  [ -r "$p/cmdline" ] || continue
  if tr '\0' ' ' < "$p/cmdline" 2>/dev/null | grep -q -- "-avd $AVD"; then running=1; break; fi
done

if [ "$running" = "1" ]; then
  echo "$AVD is already running — re-asserting agent mode (log: $AMLOG)"
  setsid nohup bash "$WAITER" "$AVD" "$SERIAL" >/dev/null 2>&1 </dev/null &
  "$S/platform-tools/adb" devices
  exit 0
fi

echo "starting $AVD (gpu=${GPU_MODE:-swiftshader_indirect}) -> log: $LOG"
setsid nohup "$S/emulator/emulator" -avd "$AVD" -writable-system -no-snapshot \
  -no-boot-anim -no-metrics -gpu "${GPU_MODE:-swiftshader_indirect}" >"$LOG" 2>&1 </dev/null &

# agent mode lands automatically once the guest finishes booting
setsid nohup bash "$WAITER" "$AVD" "$SERIAL" >/dev/null 2>&1 </dev/null &

sleep 4
echo "launched detached — agent_mode applies automatically after boot"
echo "  watch:  tail -f $AMLOG"
echo "  root:   $S/platform-tools/adb -s $SERIAL root && $S/platform-tools/adb -s $SERIAL shell id"
