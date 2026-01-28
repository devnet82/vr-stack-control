#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="vr-stack-control.service"
CFG_DIR="$HOME/.config/vr-stack"
CFG="$CFG_DIR/stack.conf"
RUN_LOG="$HOME/.local/share/vr-stack.log"

mkdir -p "$CFG_DIR"

PROFILES_DIR="$CFG_DIR/profiles"
mkdir -p "$PROFILES_DIR"

list_profiles() { ls -1 "$PROFILES_DIR"/*.conf 2>/dev/null | xargs -n1 basename | sed 's/\.conf$//' || true; }

current_profile_name() {
  if [[ -L "$CFG" ]]; then
    basename "$(readlink -f "$CFG")" | sed 's/\.conf$//'
  else
    echo "default"
  fi
}

ensure_default_profile() {
  if [[ ! -f "$PROFILES_DIR/default.conf" ]]; then
    [[ -f "$CFG" && ! -L "$CFG" ]] && cp -f "$CFG" "$PROFILES_DIR/default.conf" || true
  fi
  if [[ ! -L "$CFG" ]]; then
    rm -f "$CFG"
    ln -sf "$PROFILES_DIR/default.conf" "$CFG"
  fi
}

switch_profile() {
  ensure_default_profile
  local items choice
  items="$(list_profiles)"
  [[ -z "$items" ]] && yad --info --title="VR Control Panel" --text="No profiles found." && return 0
  choice="$(printf "%s\n" $items | yad --list --title="Select Profile" --column="Profile" --height=420 --width=420 --center --button="Select":0 --button="Cancel":1 2>/dev/null)" || return 1
  [[ -z "$choice" ]] && return 0
  ln -sf "$PROFILES_DIR/$choice.conf" "$CFG"
}

save_current_as_profile() {
  ensure_default_profile
  local name
  name="$(yad --entry --title="New Profile" --text="Profile name:" --entry-text="new-profile" --center 2>/dev/null)" || return 1
  [[ -z "${name// }" ]] && return 0
  name="$(sed -E 's/[^a-zA-Z0-9._-]+/-/g' <<<"$name")"
  cp -f "$(readlink -f "$CFG")" "$PROFILES_DIR/$name.conf"
  ln -sf "$PROFILES_DIR/$name.conf" "$CFG"
}

delete_profile() {
  ensure_default_profile
  local items choice cur
  cur="$(current_profile_name)"
  items="$(list_profiles | sed "/^$cur$/d")"
  [[ -z "$items" ]] && yad --info --title="VR Control Panel" --text="No deletable profiles (current is '$cur')." && return 0
  choice="$(printf "%s\n" $items | yad --list --title="Delete Profile" --column="Profile" --height=420 --width=420 --center --button="Delete":0 --button="Cancel":1 2>/dev/null)" || return 1
  [[ -z "$choice" ]] && return 0
  rm -f "$PROFILES_DIR/$choice.conf"
}

have() { command -v "$1" >/dev/null 2>&1; }

is_active() { systemctl --user is-active --quiet "$SERVICE"; }
is_enabled() { systemctl --user is-enabled --quiet "$SERVICE"; }

status_str() { is_active && echo "RUNNING" || echo "STOPPED"; }
autostart_str() { is_enabled && echo "ENABLED" || echo "DISABLED"; }

adb_state() {
  if ! command -v adb >/dev/null 2>&1; then echo "no-adb"; return; fi
  if adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{found=1} END{exit !found}'; then echo "connected"; return; fi
  if adb devices 2>/dev/null | awk 'NR>1 && ($2=="unauthorized" || $2=="offline"){found=1} END{exit !found}'; then echo "unauthorized"; return; fi
  echo "disconnected"
}

wivrn_state() {
  local regex="${WIVRN_CONNECTED_REGEX:-connected|connection established|client.*connected|new client|session.*created}"
  local text
  text="$(journalctl --user -u "$SERVICE" -n 250 --no-pager 2>/dev/null || true)"
  [[ -z "$text" ]] && { echo "unknown"; return; }
  echo "$text" | rg -i -q "$regex" && echo "connected" || echo "disconnected"
}

strip_exec_placeholders() {
  # Remove common DesktopEntry placeholders like %u %U %f %F etc.
  sed -E "s/[[:space:]]%[a-zA-Z]//g; s/[[:space:]]%[0-9]?[a-zA-Z]//g" <<<"$1"
}

desktop_apps_list() {
  # Output lines: Name<TAB>Exec<TAB>DesktopFile
  local dirs=("$HOME/.local/share/applications" "/usr/share/applications")
  for d in "${dirs[@]}"; do
    [[ -d "$d" ]] || continue
    for f in "$d"/*.desktop; do
      [[ -f "$f" ]] || continue
      local name exec
      name="$(rg -m1 '^Name=' "$f" | head -n1 | sed 's/^Name=//')"
      exec="$(rg -m1 '^Exec=' "$f" | head -n1 | sed 's/^Exec=//')"
      [[ -n "${name:-}" && -n "${exec:-}" ]] || continue
      exec="$(strip_exec_placeholders "$exec")"
      printf "%s\t%s\t%s\n" "$name" "$exec" "$f"
    done
  done | sort -u
}

path_cmds_list() {
  local cmds=( slimevr wayvr wivrn-server monado-service envision steamvr )
  for c in "${cmds[@]}"; do
    if command -v "$c" >/dev/null 2>&1; then
      printf "%s\t%s\n" "$c (PATH)" "$c"
    fi
  done
}

build_menu() {
  {
    desktop_apps_list | while IFS=$'\t' read -r name exec file; do
      printf "%s\t%s\n" "$name (Desktop)" "$exec"
    done
    path_cmds_list
    printf "%s\t%s\n" "None (skip this stage)" ""
  } | awk -F'\t' 'NF>=2 {print $1 "|" $2}' | sort -u
}

pick_from_menu() {
  local title="$1"
  local current_exec="${2:-}"
  local menu values choice picked_label custom

  menu="$(build_menu)"
  values="$(cut -d'|' -f1 <<<"$menu" | paste -sd',' -)"

  choice="$(yad --title="VR Control Panel" \
    --form --center --width=940 --height=240 --borders=12 \
    --field="$title:CB" "$values" \
    --field="Custom command (overrides dropdown):" "$current_exec" \
    --button="OK":0 --button="Cancel":1 2>/dev/null)" || return 1

  picked_label="$(cut -d'|' -f1 <<<"$choice")"
  custom="$(cut -d'|' -f2- <<<"$choice")"

  if [[ -n "${custom// }" ]]; then
    printf "%s\n" "$custom"
    return 0
  fi

  awk -F'|' -v lbl="$picked_label" '$1==lbl {print $2; exit}' <<<"$menu"
}

load_cfg() {
  TRACK_CMD="/opt/slimevr/slimevr"
  TRACK_READY_PGREP="slimevr\.jar"
  SERVER_CMD="wivrn-server"
  SERVER_PGREP="wivrn-server"
  VR_CMD="wayvr"
  VR_PGREP="(^|/)(wayvr)(\\s|$)"
  OPENXR_JSON="/usr/share/openxr/1/openxr_wivrn.json"

  if [[ -f "$CFG" ]]; then
    # shellcheck disable=SC1090
    source "$CFG"
  fi
}

save_cfg() {
  cat > "$CFG" <<EOF2
# VR Stack configuration (bash-sourced)

TRACK_CMD="$(printf "%s" "${TRACK_CMD:-}" | sed "s/\"/\\\\\"/g")"
TRACK_READY_PGREP="$(printf "%s" "${TRACK_READY_PGREP:-}" | sed "s/\"/\\\\\"/g")"

SERVER_CMD="$(printf "%s" "${SERVER_CMD:-}" | sed "s/\"/\\\\\"/g")"
SERVER_PGREP="$(printf "%s" "${SERVER_PGREP:-}" | sed "s/\"/\\\\\"/g")"

VR_CMD="$(printf "%s" "${VR_CMD:-}" | sed "s/\"/\\\\\"/g")"
VR_PGREP="$(printf "%s" "${VR_PGREP:-}" | sed "s/\"/\\\\\"/g")"

OPENXR_JSON="$(printf "%s" "${OPENXR_JSON:-}" | sed "s/\"/\\\\\"/g")"
EOF2
}

edit_patterns() {
  local out
  out="$(yad --title="VR Control Panel" --form --center --width=940 --height=270 --borders=12 \
    --field="Tracking ready pgrep (blank = no wait):" "${TRACK_READY_PGREP:-}" \
    --field="Server pgrep pattern:" "${SERVER_PGREP:-}" \
    --field="VR app pgrep pattern:" "${VR_PGREP:-}" \
    --button="OK":0 --button="Cancel":1 2>/dev/null)" || return 1

  TRACK_READY_PGREP="$(cut -d'|' -f1 <<<"$out")"
  SERVER_PGREP="$(cut -d'|' -f2 <<<"$out")"
  VR_PGREP="$(cut -d'|' -f3 <<<"$out")"
}

copy_debug_bundle() {
  local tmp
  tmp="$(mktemp)"
  {
    echo "=== VR DEBUG BUNDLE ==="
    echo "Timestamp: $(date -Is)"
    echo "Host: $(hostname)"
    echo
    echo "--- config ($CFG) ---"
    [[ -f "$CFG" ]] && cat "$CFG" || echo "(missing)"
    echo
    echo "--- systemd status ---"
    systemctl --user status "$SERVICE" --no-pager || true
    echo
    echo "--- systemd show ---"
    systemctl --user show -p ActiveState -p SubState -p Result "$SERVICE" || true
    echo
    echo "--- processes ---"
    pgrep -af "slimevr\.jar|wivrn-server|(^|/)(wayvr)(\\s|$)|/opt/slimevr/slimevr|vr-stack-run\.sh" || echo "(none)"
    echo
    echo "--- journal (last 250) ---"
    journalctl --user -u "$SERVICE" -n 250 --no-pager || true
    echo
    echo "--- runner log ($RUN_LOG) tail 200 ---"
    [[ -f "$RUN_LOG" ]] && tail -n 200 "$RUN_LOG" || echo "(missing)"
  } > "$tmp"

  if have xclip; then
    xclip -selection clipboard < "$tmp" || true
    yad --info --title="VR Control Panel" --text="Debug info copied to clipboard."
  else
    yad --text-info --title="VR Debug Bundle" --filename="$tmp" --width=980 --height=650
  fi
  rm -f "$tmp"
}

show_logs() {
  journalctl --user -u "$SERVICE" -n 250 --no-pager 2>/dev/null | \
    yad --text-info --title="VR Logs (journalctl)" --width=980 --height=650 --wrap
}

load_cfg
ensure_default_profile
load_cfg

while true; do
  state="$(status_str)"
  auto="$(autostart_str)"

  choice="$(yad --title="VR Control Panel" --center --width=760 --height=390 --borders=12 \
    --list --column="Action" \
    "Status: $state" \
    "Quest ADB: $(adb_state) | WiVRn: $(wivrn_state)" \
    "Autostart on login: $auto" \
    "Profile: $(current_profile_name)" \
    "Select profile…" \
    "Save current as new profile…" \
    "Delete a profile…" \
    "Set Tracking app…" \
    "Set Server app…" \
    "Set VR app…" \
    "Edit readiness/pgrep patterns…" \
    "Save config" \
    "Start VR" \
    "Stop VR" \
    "Restart VR" \
    "Toggle autostart" \
    "View logs" \
    "Copy debug bundle" \
    "Quit" \
    --button="Select":0 --button="Close":1 2>/dev/null)" || exit 0

  case "$choice" in
    "Select profile…")
      switch_profile || true
      ;;
    "Save current as new profile…")
      save_current_as_profile || true
      ;;
    "Delete a profile…")
      delete_profile || true
      ;;
    "Set Tracking app…")
      TRACK_CMD="$(pick_from_menu "Tracking app" "${TRACK_CMD:-}")" || continue
      [[ "$TRACK_CMD" == *slimevr* ]] && TRACK_READY_PGREP="slimevr\.jar"
      ;;
    "Set Server app…")
      SERVER_CMD="$(pick_from_menu "Server app" "${SERVER_CMD:-}")" || continue
      [[ "$SERVER_CMD" == "wivrn-server" ]] && SERVER_PGREP="wivrn-server"
      ;;
    "Set VR app…")
      VR_CMD="$(pick_from_menu "VR app (OpenXR client)" "${VR_CMD:-}")" || continue
      [[ "$VR_CMD" == "wayvr" ]] && VR_PGREP="(^|/)(wayvr)(\\s|$)"
      ;;
    "Edit readiness/pgrep patterns…")
      edit_patterns || true
      ;;
    "Save config")
      save_cfg
      yad --info --title="VR Control Panel" --text="Saved:\n$CFG"
      ;;
    "Start VR")
      save_cfg
      systemctl --user start "$SERVICE"
      ;;
    "Stop VR")
      systemctl --user stop "$SERVICE"
      ;;
    "Restart VR")
      save_cfg
      systemctl --user restart "$SERVICE"
      ;;
    "Toggle autostart")
      if is_enabled; then
        systemctl --user disable "$SERVICE" || true
      else
        systemctl --user enable "$SERVICE" || true
      fi
      ;;
    "View logs")
      show_logs
      ;;
    "Copy debug bundle")
      copy_debug_bundle
      ;;
    "Quit"|*)
      exit 0
      ;;
  esac

  load_cfg
done
