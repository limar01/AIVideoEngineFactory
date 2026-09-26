#!/usr/bin/env bash
# agent_mode_waiter.sh — wait for an AVD to finish booting, then apply agent mode.
#
#   bash agent_mode_waiter.sh [AVD_NAME] [SERIAL]
#
# Started detached by start_zillion_root_avd.sh. Runs exactly one boot-wait cycle,
# logs everything to logs/agent_mode.log, and exits non-zero if the boot never lands.
# All paths/values are passed as ARGUMENTS on purpose — the previous version relied on
# shell variables that were not present in the detached child, so it silently did nothing.
set -uo pipefail

AVD="${1:-zillion_root_avd}"
SERIAL="${2:-emulator-5554}"
DIR="$(cd "$(dirname "$0")" && pwd)"
S="${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}"
ADB="$S/platform-tools/adb"
LOG="$DIR/logs/agent_mode.log"
mkdir -p "$DIR/logs"

say() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
say "waiter start: avd=$AVD serial=$SERIAL (waiting for boot)"

boot=""
for i in $(seq 1 60); do
  boot="$("$ADB" -s "$SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')"
  [ "$boot" = "1" ] && break
  sleep 3
done

if [ "$boot" != "1" ]; then
  say "FAIL: $SERIAL did not finish booting within ~180s — agent mode NOT applied"
  exit 1
fi

say "boot complete — applying agent mode"
out="$(bash "$DIR/agent_mode.sh" "$SERIAL" 2>&1)"; rc=$?
printf '%s\n' "$out" | tee -a "$LOG"
pass=$(printf '%s\n' "$out" | grep -c '\[PASS\]')
say "agent_mode.sh exit=$rc (PASS=$pass) — single-run log, no double-write"
exit "$rc"
