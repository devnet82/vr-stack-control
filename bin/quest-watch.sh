#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="vr-stack-control.service"
INTERVAL="${1:-3}"

# Where to read logs for WiVRn connection hints:
# - journal: reads journalctl for the service
# - file: reads ~/.local/share/vr-stack.log
WIVRN_LOG_SOURCE="${WIVRN_LOG_SOURCE:-journal}"

# Regex to treat as "WiVRn connected"
WIVRN_CONNECTED_REGEX="${WIVRN_CONNECTED_REGEX:-connected|connection established|client.*connected|new client|session.*created}"

RUN_LOG="$HOME/.local/share/vr-stack.log"

have() { command -v "$1" >/dev/null 2>&1; }

notify() {
  local msg="$1"
  if have notify-send; then
    notify-send "VR Stack Control" "$msg"
  fi
}

quest_adb_state() {
  if ! have adb; then
    echo "no-adb"
    return
  fi

  if adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{found=1} END{exit !found}'; then
    echo "connected"
    return
  fi

  if adb devices 2>/dev/null | awk 'NR>1 && ($2=="unauthorized" || $2=="offline"){found=1} END{exit !found}'; then
    echo "unauthorized"
    return
  fi

  echo "disconnected"
}

wivrn_state() {
  local text=""
  if [[ "$WIVRN_LOG_SOURCE" == "file" ]]; then
    [[ -f "$RUN_LOG" ]] && text="$(tail -n 200 "$RUN_LOG" || true)"
  else
    text="$(journalctl --user -u "$SERVICE" -n 250 --no-pager 2>/dev/null || true)"
  fi

  if [[ -z "$text" ]]; then
    echo "unknown"
    return
  fi

  if echo "$text" | rg -i -q "$WIVRN_CONNECTED_REGEX"; then
    echo "connected"
  else
    echo "disconnected"
  fi
}

LAST_ADB=""
LAST_WIVRN=""

while true; do
  ADB="$(quest_adb_state)"
  WIVRN="$(wivrn_state)"

  if [[ "$ADB" != "$LAST_ADB" ]]; then
    case "$ADB" in
      connected)     notify "Quest ADB: connected" ;;
      unauthorized)  notify "Quest ADB: unauthorized/offline (check headset prompt)" ;;
      disconnected)  notify "Quest ADB: disconnected" ;;
      no-adb)        notify "Quest ADB: adb not installed (sudo pacman -S android-tools)" ;;
    esac
    LAST_ADB="$ADB"
  fi

  if [[ "$WIVRN" != "$LAST_WIVRN" ]]; then
    case "$WIVRN" in
      connected)    notify "WiVRn: client connected" ;;
      disconnected) notify "WiVRn: no client detected" ;;
      unknown)      : ;;
    esac
    LAST_WIVRN="$WIVRN"
  fi

  sleep "$INTERVAL"
done
