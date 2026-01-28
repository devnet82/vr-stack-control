#!/usr/bin/env bash
set -Eeuo pipefail

CFG="$HOME/.config/vr-stack/stack.conf"
LOG="$HOME/.local/share/vr-stack.log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "=== $(date) vr-stack-run start ==="

if [[ ! -f "$CFG" ]]; then
  echo "ERROR: Missing config: $CFG"
  echo "Create it from the GUI, or copy config/stack.conf.example to ~/.config/vr-stack/stack.conf"
  exit 1
fi

# shellcheck disable=SC1090
source "$CFG"

have_pgrep() { pgrep -f "$1" >/dev/null 2>&1; }

# --- OpenXR runtime pin ---
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
mkdir -p "$HOME/.config/openxr/1"
if [[ -n "${OPENXR_JSON:-}" ]]; then
  ln -sf "${OPENXR_JSON}" "$HOME/.config/openxr/1/active_runtime.json"
fi
export OPENXR_RUNTIME_JSON="$HOME/.config/openxr/1/active_runtime.json"
export XR_RUNTIME_JSON="$OPENXR_RUNTIME_JSON"

echo "OpenXR runtime: $(readlink -f "$HOME/.config/openxr/1/active_runtime.json" 2>/dev/null || echo "(not set)")"

# Prevent double-run races
LOCK="$HOME/.local/share/vr-stack.lock"
exec 9>"$LOCK"
flock -n 9 || { echo "Already running, exiting."; exit 0; }

TRACK_PID=""
READY_PID=""

# --- Start Tracking app (optional) ---
if [[ -n "${TRACK_CMD:-}" ]]; then
  if [[ -n "${TRACK_READY_PGREP:-}" ]] && have_pgrep "${TRACK_READY_PGREP}"; then
    echo "Tracking backend already running (${TRACK_READY_PGREP})"
  else
    echo "Starting tracking: ${TRACK_CMD}"
    bash -lc "${TRACK_CMD}" & TRACK_PID="$!"
    disown || true
  fi

  if [[ -n "${TRACK_READY_PGREP:-}" ]]; then
    echo "Waiting for tracking ready: ${TRACK_READY_PGREP}"
    for _ in {1..150}; do
      have_pgrep "${TRACK_READY_PGREP}" && break
      sleep 0.2
    done
    READY_PID="$(pgrep -n -f "${TRACK_READY_PGREP}" || true)"
    if [[ -z "$READY_PID" ]]; then
      echo "ERROR: Tracking backend did not become ready (${TRACK_READY_PGREP})"
      exit 1
    fi
    echo "Tracking backend PID: $READY_PID"
  fi
else
  echo "Tracking: skipped"
fi

# --- Start / restart server (optional) ---
if [[ -n "${SERVER_CMD:-}" ]]; then
  if [[ -n "${SERVER_PGREP:-}" ]] && have_pgrep "${SERVER_PGREP}"; then
    echo "Restarting server cleanly (${SERVER_PGREP})..."
    pkill -f "${SERVER_PGREP}" || true
    sleep 1
  fi
  echo "Starting server: ${SERVER_CMD}"
  bash -lc "${SERVER_CMD}" & disown || true
  sleep 1
else
  echo "Server: skipped"
fi

# --- Start VR app (optional) ---
if [[ -n "${VR_CMD:-}" ]]; then
  if [[ -n "${VR_PGREP:-}" ]] && ! have_pgrep "${VR_PGREP}"; then
    echo "Starting VR app: ${VR_CMD}"
    bash -lc "${VR_CMD}" & disown || true
  else
    echo "VR app already running or no pgrep pattern set"
  fi
else
  echo "VR app: skipped"
fi

echo "Running processes:"
pgrep -af "slimevr\.jar|wivrn-server|(^|/)(wayvr)(\\s|$)|/opt/slimevr/slimevr|vr-stack-run\.sh" || true

# --- Shutdown cascade trigger ---
echo "Waiting for shutdown trigger..."
if [[ -n "$TRACK_PID" ]]; then
  while kill -0 "$TRACK_PID" 2>/dev/null; do sleep 1; done
elif [[ -n "$READY_PID" ]]; then
  while kill -0 "$READY_PID" 2>/dev/null; do sleep 1; done
elif [[ -n "${VR_PGREP:-}" ]]; then
  while have_pgrep "${VR_PGREP}"; do sleep 1; done
else
  sleep 2
fi

echo "Shutdown trigger fired — stopping stack"
[[ -n "${VR_PGREP:-}" ]] && pkill -f "${VR_PGREP}" || true
[[ -n "${SERVER_PGREP:-}" ]] && pkill -f "${SERVER_PGREP}" || true
[[ -n "${TRACK_READY_PGREP:-}" ]] && pkill -f "${TRACK_READY_PGREP}" || true

echo "=== $(date) vr-stack-run done ==="
