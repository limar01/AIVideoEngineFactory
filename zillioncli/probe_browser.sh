#!/usr/bin/env bash
# Zillion CLI — Probe Browser Manager
# Ensures Chromium CDP on :9222 for Arena session (used by Omarchy Zillion app + zion CLI).

set -u

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}"
if [[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" && -d "${XDG_RUNTIME_DIR}/hypr" ]]; then
  export HYPRLAND_INSTANCE_SIGNATURE="$(ls "$XDG_RUNTIME_DIR/hypr" 2>/dev/null | head -n 1)"
fi

PORT="${ZION_PORT:-9222}"
PROFILE="$HOME/.config/chromium-zillion-probe"
ARENA_URL="https://arena.ai/agent"
# headed = visible window (login / captcha). headless = background CDP.
MODE="${ZION_PROBE_MODE:-headed}"   # headed|headless

is_online() {
  curl -s --max-time 2 "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1
}

clear_locks() {
  rm -f "$PROFILE"/SingletonLock "$PROFILE"/SingletonSocket "$PROFILE"/SingletonCookie 2>/dev/null || true
}

start_probe() {
  local extra=()
  if [[ "$MODE" == "headless" ]]; then
    extra+=(--headless=new --disable-gpu)
  else
    extra+=(--class=ZillionProbe --name=zillion-probe --window-size=1280,900)
  fi

  clear_locks
  setsid -f /usr/bin/chromium \
    --ozone-platform=wayland \
    --password-store=gnome-libsecret \
    --remote-debugging-port="${PORT}" \
    --remote-allow-origins='*' \
    --user-data-dir="${PROFILE}" \
    --no-first-run \
    --no-default-browser-check \
    --noerrdialogs \
    "${extra[@]}" \
    "${ARENA_URL}" \
    >/tmp/zion-probe.log 2>&1 </dev/null || true

  for _ in $(seq 1 40); do
    sleep 0.4
    if is_online; then
      echo "STARTED (port ${PORT}, mode=${MODE}, profile=${PROFILE})"
      return 0
    fi
  done
  echo "FAILED TO START (see /tmp/zion-probe.log)"
  return 1
}

case "${1:-status}" in
  status)
    if is_online; then echo "ONLINE"; exit 0; else echo "OFFLINE"; exit 1; fi
    ;;
  start|ensure)
    if is_online; then
      echo "ALREADY ONLINE"
      exit 0
    fi
    echo "Starting probe browser (mode=${MODE})..."
    start_probe
    ;;
  headed)
    MODE=headed
    if is_online; then
      # Already up — if headless, restart headed for login UI
      UA="$(curl -s --max-time 2 http://127.0.0.1:${PORT}/json/version 2>/dev/null || true)"
      if echo "$UA" | grep -qi Headless; then
        "$0" stop >/dev/null 2>&1 || true
        sleep 1
        MODE=headed start_probe
      else
        echo "ALREADY ONLINE (headed)"
        exit 0
      fi
    else
      start_probe
    fi
    ;;
  headless)
    MODE=headless
    if is_online; then echo "ALREADY ONLINE"; exit 0; fi
    start_probe
    ;;
  stop)
    pkill -f "user-data-dir=${PROFILE}" 2>/dev/null || true
    pkill -f "remote-debugging-port=${PORT}" 2>/dev/null || true
    sleep 0.5
    clear_locks
    echo "STOPPED"
    ;;
  restart)
    "$0" stop >/dev/null 2>&1 || true
    sleep 1
    "$0" start
    ;;
  *)
    echo "Usage: probe_browser.sh [ensure|start|headed|headless|stop|restart|status]"
    exit 2
    ;;
esac
