#!/usr/bin/env bash
set -Eeuo pipefail

CFG_DIR="$HOME/.config/vr-stack"
CFG="$CFG_DIR/stack.conf"
LOG="$HOME/.local/share/vr-stack.log"

mkdir -p "$CFG_DIR" "$(dirname "$LOG")"

# Defaults
TRACKING_ENABLED="true"
TRACK_STOP_WHEN_DISABLED="true"

TRACK_CMD="/opt/slimevr/slimevr"
TRACK_READY_PGREP="slimevr\.jar"

SERVER_CMD="wivrn-server"
SERVER_PGREP="wivrn-server"

VR_CMD="wayvr"
VR_PGREP="(^|/)(wayvr)(\s|$)"

OPENXR_JSON="/usr/share/openxr/1/openxr_wivrn.json"

# OpenXR runtime selector: wivrn | steamvr
XR_RUNTIME="wivrn"

strip_quotes() {
  local v="$1"
  if [[ ${#v} -ge 2 && ${v:0:1} == '"' && ${v: -1} == '"' ]]; then
    v="${v:1:-1}"
  fi
  if [[ ${#v} -ge 2 && ${v:0:1} == "'" && ${v: -1} == "'" ]]; then
    v="${v:1:-1}"
  fi
  printf '%s' "$v"
}

is_true() {
  case "${1,,}" in
    1|true|yes|on|enable|enabled) return 0;;
    *) return 1;;
  esac
}

load_cfg() {
  [[ -f "$CFG" ]] || return 0
  while IFS= read -r line; do
    line="${line%%#*}"
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" != *"="* ]] && continue
    local k="${line%%=*}"
    local v="${line#*=}"
    k="$(echo "$k" | xargs)"
    v="${v#"${v%%[![:space:]]*}"}"
    v="${v%"${v##*[![:space:]]}"}"
    v="$(strip_quotes "$v")"

    case "$k" in
      TRACKING_ENABLED|tracking_enabled) TRACKING_ENABLED="$v" ;;
      TRACK_STOP_WHEN_DISABLED|tracking_stop_when_disabled) TRACK_STOP_WHEN_DISABLED="$v" ;;

      TRACK_CMD|tracking_cmd) TRACK_CMD="$v" ;;
      TRACK_READY_PGREP|track_ready_pgrep|tracking_ready) TRACK_READY_PGREP="$v" ;;

      SERVER_CMD|server_cmd) SERVER_CMD="$v" ;;
      SERVER_PGREP|server_pgrep) SERVER_PGREP="$v" ;;

      VR_CMD|vr_cmd) VR_CMD="$v" ;;
      VR_PGREP|vr_pgrep) VR_PGREP="$v" ;;

      OPENXR_JSON|openxr_json) OPENXR_JSON="$v" ;;
      XR_RUNTIME|xr_runtime) XR_RUNTIME="$v" ;;
    esac
  done < "$CFG"
}

have_pgrep() { pgrep -f "$1" >/dev/null 2>&1; }

force_openxr() {
  mkdir -p "$HOME/.config/openxr/1"
  ln -sf "$OPENXR_JSON" "$HOME/.config/openxr/1/active_runtime.json"
  export OPENXR_RUNTIME_JSON="$HOME/.config/openxr/1/active_runtime.json"
  export XR_RUNTIME_JSON="$OPENXR_RUNTIME_JSON"
}


stop_xrizer() {
  # Best-effort: stop XRizer + remove env that forces it.
  # This only affects processes launched by this script.
  unset VR_OVERRIDE VR_RUNTIME OPENVR_RUNTIME OPENVR_CONFIG_PATH
  unset XRIZER_RUNTIME XRIZER_PREFIX XRIZER_PATH
  # If XRizer processes are running, try to stop them.
  /usr/bin/pkill -f /opt/xrizer >/dev/null 2>&1 || true
  /usr/bin/pkill -f xrizer >/dev/null 2>&1 || true
}



disable_xrizer_for_steamvr() {
  # XRizer (OpenVR→OpenXR translation) can hijack SteamVR/Wine OpenVR apps.
  # When the user selects SteamVR, we try to stop XRizer *and* remove its env influence
  # for anything we launch from this script.
  unset VR_OVERRIDE VR_CONFIG_PATH VR_RUNTIME OPENVR_RUNTIME OPENVR_CONFIG_PATH XRIZER_RUNTIME
  /usr/bin/pkill -f "/opt/xrizer" >/dev/null 2>&1 || true
  /usr/bin/pkill -f "xrizer" >/dev/null 2>&1 || true
}

stop_component_by_pattern() {
  local pat="$1"
  [[ -z "$pat" ]] && return 0
  /usr/bin/pkill -f "$pat" >/dev/null 2>&1 || true
}

stop_stack() {
  echo "Stopping stack…"
  stop_component_by_pattern "$VR_PGREP"
  /usr/bin/pkill -x wivrn-server >/dev/null 2>&1 || true

  if is_true "$TRACKING_ENABLED"; then
    stop_component_by_pattern "$TRACK_READY_PGREP"
  else
    if is_true "$TRACK_STOP_WHEN_DISABLED"; then
      stop_component_by_pattern "$TRACK_READY_PGREP"
    else
      echo "Tracking stop skipped (tracking_enabled=false and tracking_stop_when_disabled=false)"
    fi
  fi
}

start_stack() {
  force_openxr

  echo "TRACKING_ENABLED=$TRACKING_ENABLED"
  echo "TRACK_CMD=$TRACK_CMD"
  echo "SERVER_CMD=$SERVER_CMD"
  echo "VR_CMD=$VR_CMD"
  echo "OPENXR_JSON=$OPENXR_JSON"
echo "XR_RUNTIME=$XR_RUNTIME"

  # Start tracking (optional)
  if is_true "$TRACKING_ENABLED"; then
    if [[ -n "${TRACK_CMD:-}" ]]; then
      if ! have_pgrep "$TRACK_CMD" && ! have_pgrep "$TRACK_READY_PGREP"; then
        echo "Starting tracking: $TRACK_CMD"
        APPIMAGE_EXTRACT_AND_RUN=1 $TRACK_CMD & disown || true
      else
        echo "Tracking already running"
      fi

      if [[ -n "${TRACK_READY_PGREP:-}" ]]; then
        echo "Waiting for tracking ready: $TRACK_READY_PGREP"
        for _ in {1..120}; do
          have_pgrep "$TRACK_READY_PGREP" && break
          sleep 0.25
        done
      fi
    fi
  else
    echo "Tracking disabled (tracking_enabled=false)"
  fi

  # Start server (dedupe)
  if [[ -n "${SERVER_CMD:-}" ]]; then
    if have_pgrep "$SERVER_PGREP"; then
      echo "Server already running"
    else
      echo "Starting server: $SERVER_CMD"
      $SERVER_CMD & disown || true
      sleep 1
    fi
  fi

  # Start VR app
  if [[ "${XR_RUNTIME,,}" == "steamvr" ]]; then
    echo "SteamVR selected: disabling XRizer for launched apps…"
    stop_xrizer
  fi

  # If SteamVR is selected, disable XRizer before launching the VR app.
  if [[ "${XR_RUNTIME,,}" == "steamvr" ]]; then
    disable_xrizer_for_steamvr
  fi
  if [[ -n "${VR_CMD:-}" ]]; then
    if have_pgrep "$VR_PGREP"; then
      echo "VR app already running"
    else
      echo "Starting VR app: $VR_CMD"
      $VR_CMD & disown || true
    fi
  fi
}

main() {
  load_cfg

  exec >>"$LOG" 2>&1
  echo "=== $(date -Is) vr-stack-run $* ==="

  case "${1-}" in
    start|"" ) start_stack ;;
    stop) stop_stack ;;
    restart)
      stop_stack
      start_stack
      ;;
    *)
      echo "Usage: vr-stack-run.sh [start|stop|restart]" >&2
      exit 2
      ;;
  esac

  echo "=== $(date -Is) vr-stack-run done ==="
}

main "$@"
