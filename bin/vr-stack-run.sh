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

# WiVRn server (OpenXR runtime side)
SERVER_CMD="wivrn-server"
SERVER_PGREP="wivrn-server"

# Desktop/overlay app for WiVRn mode
VR_CMD="wayvr --openxr --show"
VR_PGREP="(^|/)(wayvr)(\s|$)"

# Per-user WiVRn OpenXR runtime JSON (absolute path)
OPENXR_JSON="$HOME/.config/openxr/1/wivrn_runtime.json"

# OpenXR runtime selector: wivrn | steamvr
XR_RUNTIME="wivrn"

# SteamVR launcher (AppID 250820)
STEAMVR_LAUNCH="steam steam://rungameid/250820"

# If true, starting the stack in SteamVR mode will also launch SteamVR.
# Default is false: many users prefer to launch SteamVR manually, and auto-launch
# can feel like SteamVR is "popping up" when switching runtimes.
STEAMVR_AUTOSTART="false"

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

      STEAMVR_LAUNCH|steamvr_launch) STEAMVR_LAUNCH="$v" ;;
      STEAMVR_AUTOSTART|steamvr_autostart) STEAMVR_AUTOSTART="$v" ;;
    esac
  done < "$CFG"
}

have_pgrep() { pgrep -f "$1" >/dev/null 2>&1; }
have_pgrep_exact() { pgrep -x "$1" >/dev/null 2>&1; }

ensure_wivrn_runtime_json() {
  # Ensure we have a stable, absolute-path WiVRn runtime JSON.
  local target="$HOME/.config/openxr/1/wivrn_runtime.json"
  mkdir -p "$HOME/.config/openxr/1"
  if [[ ! -f "$target" ]]; then
    cat >"$target" <<JSON
{
  "file_format_version": "1.0.0",
  "runtime": {
    "name": "WiVRn",
    "library_path": "/usr/lib/wivrn/libopenxr_wivrn.so"
  }
}
JSON
  fi
}

best_effort_detect_steamvr_openxr_json() {
  local candidates=(
    "/usr/share/openxr/1/openxr_steamvr.json"
    "/usr/share/openxr/1/openxr_steamvr_linux.json"
    "$HOME/.steam/steam/steamapps/common/SteamVR/steamxr_linux64.json"
    "$HOME/.local/share/Steam/steamapps/common/SteamVR/steamxr_linux64.json"
  )
  local p
  for p in "${candidates[@]}"; do
    [[ -f "$p" ]] && { echo "$p"; return 0; }
  done
  return 1
}

force_openxr() {
  mkdir -p "$HOME/.config/openxr/1"

  if [[ "${XR_RUNTIME,,}" == "steamvr" ]]; then
    # If user didn't supply an OpenXR JSON for SteamVR, try to find one.
    if [[ -z "${OPENXR_JSON:-}" || ! -f "${OPENXR_JSON:-}" ]]; then
      OPENXR_JSON="$(best_effort_detect_steamvr_openxr_json || true)"
    fi
  else
    ensure_wivrn_runtime_json
    OPENXR_JSON="$HOME/.config/openxr/1/wivrn_runtime.json"
  fi

  [[ -n "${OPENXR_JSON:-}" ]] && install -m 644 "$OPENXR_JSON" "$HOME/.config/openxr/1/active_runtime.json" || true
  export OPENXR_RUNTIME_JSON="$HOME/.config/openxr/1/active_runtime.json"
  export XR_RUNTIME_JSON="$OPENXR_RUNTIME_JSON"
}

stop_xrizer() {
  # Best-effort: stop XRizer processes so SteamVR can run cleanly.
  unset VR_OVERRIDE VR_RUNTIME OPENVR_RUNTIME OPENVR_CONFIG_PATH
  unset XRIZER_RUNTIME XRIZER_PREFIX XRIZER_PATH
  /usr/bin/pkill -f "/opt/xrizer" >/dev/null 2>&1 || true
  /usr/bin/pkill -f "xrizer" >/dev/null 2>&1 || true
}

stop_component_by_pattern() {
  local pat="$1"
  [[ -z "$pat" ]] && return 0
  /usr/bin/pkill -f "$pat" >/dev/null 2>&1 || true
}

stop_steamvr() {
  # SteamVR processes
  /usr/bin/pkill -f "vrcompositor" >/dev/null 2>&1 || true
  /usr/bin/pkill -f "vrserver" >/dev/null 2>&1 || true
  /usr/bin/pkill -f "vrmonitor" >/dev/null 2>&1 || true
  /usr/bin/pkill -f "vrwebhelper" >/dev/null 2>&1 || true
  /usr/bin/pkill -f "steamwebhelper" >/dev/null 2>&1 || true
  /usr/bin/pkill -f "steamvr" >/dev/null 2>&1 || true
}

stop_wivrn_side() {
  stop_component_by_pattern "$VR_PGREP"
  /usr/bin/pkill -x wivrn-server >/dev/null 2>&1 || true
}

stop_stack() {
  echo "Stopping stack…"

  # Always stop overlay + WiVRn server
  stop_wivrn_side

  # If user is in SteamVR mode, also stop SteamVR bits
  if [[ "${XR_RUNTIME,,}" == "steamvr" ]]; then
    stop_steamvr
  fi

  # Stop tracking if configured
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

start_tracking() {
  if ! is_true "$TRACKING_ENABLED"; then
    echo "Tracking disabled (tracking_enabled=false)"
    return 0
  fi

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
}

start_stack() {
  force_openxr

  echo "TRACKING_ENABLED=$TRACKING_ENABLED"
  echo "TRACK_CMD=$TRACK_CMD"
  echo "SERVER_CMD=$SERVER_CMD"
  echo "VR_CMD=$VR_CMD"
  echo "OPENXR_JSON=$OPENXR_JSON"
  echo "XR_RUNTIME=$XR_RUNTIME"

  start_tracking

  if [[ "${XR_RUNTIME,,}" == "steamvr" ]]; then
    # SteamVR mode: WiVRn + WayVR must NOT run.
    echo "SteamVR mode: stopping WiVRn + WayVR (if running)"
    stop_wivrn_side

    echo "SteamVR mode: stopping XRizer (so SteamVR can own OpenVR/OpenXR)"
    stop_xrizer

    if [[ -z "${OPENXR_JSON:-}" ]]; then
      echo "WARNING: SteamVR OpenXR runtime JSON not found. SteamVR may not expose OpenXR."
    fi

    if is_true "$STEAMVR_AUTOSTART"; then
      echo "Launching SteamVR…"
      bash -lc "$STEAMVR_LAUNCH" & disown || true
    else
      echo "SteamVR mode selected (auto-launch disabled)."
      echo "Tip: Launch SteamVR manually (or enable steamvr_autostart=true)."
    fi
    return 0
  fi

  # WiVRn mode: stop SteamVR if it is running (prevents compositor conflicts)
  stop_steamvr

  # Start WiVRn server (dedupe)
  if [[ -n "${SERVER_CMD:-}" ]]; then
    if [[ "$SERVER_PGREP" == "wivrn-server" ]] && have_pgrep_exact wivrn-server; then
      echo "Server already running"
    elif have_pgrep "$SERVER_PGREP"; then
      echo "Server already running"
    else
      echo "Starting server: $SERVER_CMD"
      $SERVER_CMD & disown || true
      sleep 1
    fi
  fi

  # Start overlay/desktop app
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

  # Prevent concurrent invocations (double-clicks, rapid restarts) from starting wivrn-server twice.
  local lock="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/vr-stack-run.lock"
  exec 9>"$lock"
  flock -n 9 || { echo "Another vr-stack-run is already running"; exit 0; }

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
