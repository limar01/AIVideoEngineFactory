#!/usr/bin/env bash
# agent_mode.sh — make the emulator fully agent-drivable (idempotent; safe to re-run)
#
#   bash agent_mode.sh [serial]
#
# Applies everything that was verified by hand on 2026-09-26:
#   * animation scales 0 — UI reaches steady state fast, taps land predictably
#   * stay-awake + keyguard dismissed — no lock screen blocking an agent
#   * Chrome: first-run screens skipped (--disable-fre etc.) + renderer
#     accessibility so agents can READ web page text, not just screenshot it
#   * pre-granted notification permissions — kills the "notifications make
#     things easier" dialog that otherwise covers the page
#   * adbd in root mode + /system remount (overlayfs), if -writable-system
#
# Run AFTER the AVD has finished booting. Prints a PASS/FAIL summary.
set -uo pipefail

S="${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}"
SERIAL="${1:-emulator-5554}"
A="$S/platform-tools/adb -s $SERIAL"
PASS=0; FAIL=0
ok()   { echo "  [PASS] $1"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

# ---- wait for boot -----------------------------------------------------------
for i in $(seq 1 40); do
  b=$($A shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
  [ "$b" = "1" ] && break
  sleep 3
done
[ "$b" = "1" ] || { echo "FATAL: $SERIAL never finished booting"; exit 1; }
echo "== agent_mode: $SERIAL (booted) =="

# ---- root + writable system --------------------------------------------------
$A root >/dev/null 2>&1; sleep 3
case "$($A shell id 2>/dev/null)" in
  *uid=0\(root\)*) ok "adbd is root (uid=0)" ;;
  *)               bad "adbd is NOT root — is this a google_apis (userdebug) image?" ;;
esac
$A remount >/dev/null 2>&1
if $A shell 'touch /system/etc/.agent_mode_probe && rm -f /system/etc/.agent_mode_probe' 2>/dev/null; then
  ok "/system is writable (overlayfs)"
else
  bad "/system is read-only — launch the AVD with -writable-system"
fi

# ---- UI stability ------------------------------------------------------------
$A shell settings put global window_animation_scale 0
$A shell settings put global transition_animation_scale 0
$A shell settings put global animator_duration_scale 0
[ "$($A shell settings get global window_animation_scale | tr -d '\r')" = "0" ] \
  && ok "animations disabled (fast, deterministic UI)" || bad "animation scales"

$A shell svc power stayon true
$A shell settings put secure lockscreen.disabled 1
$A shell wm dismiss-keyguard >/dev/null 2>&1
$A shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1
[ "$($A shell settings get secure lockscreen.disabled | tr -d '\r')" = "1" ] \
  && ok "no lock screen, screen stays on" || bad "lockscreen/stayon"

# ---- Chrome: skip first-run + expose page text to the a11y tree --------------
$A shell 'echo "chrome --disable-fre --no-first-run --no-default-browser-check --disable-search-engine-choice-screen --force-renderer-accessibility" > /data/local/tmp/chrome-command-line' 2>/dev/null
$A shell chmod 644 /data/local/tmp/chrome-command-line 2>/dev/null
$A shell am set-debug-app --persistent com.android.chrome >/dev/null 2>&1
if $A shell 'grep -q force-renderer-accessibility /data/local/tmp/chrome-command-line' 2>/dev/null; then
  ok "Chrome: FRE skipped + renderer accessibility ON (web page text is readable)"
else
  bad "Chrome command-line flags"
fi

# ---- pre-grant runtime permissions (avoids dialogs on top of the app) --------
for pkg_perm in \
    "com.android.chrome android.permission.POST_NOTIFICATIONS" \
    "com.android.chrome android.permission.ACCESS_FINE_LOCATION" \
    "com.android.chrome android.permission.CAMERA" \
    "org.fdroid.fdroid android.permission.POST_NOTIFICATIONS" ; do
  set -- $pkg_perm
  $A shell pm grant "$1" "$2" >/dev/null 2>&1
done
ok "runtime permissions pre-granted where the package exists (best effort)"

# ---- summary -----------------------------------------------------------------
echo "== agent_mode done: $PASS passed, $FAIL failed =="
echo "Agent quick start:"
echo "  $A shell am start -a android.intent.action.VIEW -d https://example.com    # browser"
echo "  $A shell uiautomator dump /sdcard/ui.xml && $A pull /sdcard/ui.xml          # read screen"
echo "  $A exec-out screencap -p > /tmp/shot.png                                    # see screen"
exit 0
