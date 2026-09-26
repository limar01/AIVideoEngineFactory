#!/usr/bin/env bash
# mqpc.sh — wrapper sa bridge/mq_pc.py (PC lane) — 2>&1 kinukuha BOTH stdout/stderr
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$ROOT/bridge/mq_pc.py" "$@" 2>&1
