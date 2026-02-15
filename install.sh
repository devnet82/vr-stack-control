#!/usr/bin/env bash
set -e

APP_DIR="$PWD"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/vr-stack"
SYSTEMD_DIR="$HOME/.config/systemd/user"

mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$CONFIG_DIR" "$SYSTEMD_DIR"

install -m 0755 "$APP_DIR/bin/vr-control" "$BIN_DIR/vr-control"
install -m 0755 "$APP_DIR/bin/vr-control-gui" "$BIN_DIR/vr-control-gui"
install -m 0755 "$APP_DIR/bin/vr-doctor" "$BIN_DIR/vr-doctor"

# Tray icon (GTK StatusIcon)
if [ -f "$APP_DIR/bin/vr-stack-tray" ]; then
  install -m 0755 "$APP_DIR/bin/vr-stack-tray" "$BIN_DIR/vr-stack-tray"
fi

# New: Python daemon that replaces vr-stack-run.sh
install -m 0755 "$APP_DIR/bin/vr-stackd" "$BIN_DIR/vr-stackd"

# Keep the legacy runner script (optional) for debugging/back-compat, but it is not used by the service.
if [ -f "$APP_DIR/bin/vr-stack-run.sh" ]; then
  install -m 0755 "$APP_DIR/bin/vr-stack-run.sh" "$BIN_DIR/vr-stack-run.sh"
fi

install -m 0644 "$APP_DIR/systemd/vr-stack-control.service" "$SYSTEMD_DIR/vr-stack-control.service"
if [ -f "$APP_DIR/systemd/vr-stack-tray.service" ]; then
  install -m 0644 "$APP_DIR/systemd/vr-stack-tray.service" "$SYSTEMD_DIR/vr-stack-tray.service"
fi

install -m 0644 "$APP_DIR/desktop/vr-control-panel.desktop" "$DESKTOP_DIR/vr-control-panel.desktop"
if [ -f "$APP_DIR/desktop/vr-stack-tray.desktop" ]; then
  install -m 0644 "$APP_DIR/desktop/vr-stack-tray.desktop" "$DESKTOP_DIR/vr-stack-tray.desktop"
fi

if [ -f "$APP_DIR/config/stack.conf.example" ] && [ ! -f "$CONFIG_DIR/stack.conf" ]; then
  cp -n "$APP_DIR/config/stack.conf.example" "$CONFIG_DIR/stack.conf"
fi

systemctl --user daemon-reload >/dev/null 2>&1 || true
update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true

echo "Installed to:"
echo "  $BIN_DIR/vr-control"
echo "  $BIN_DIR/vr-control-gui"
echo "  $BIN_DIR/vr-stackd"
echo "Launch with: vr-control --gui"
echo "Shortcut: VR Stack Control will appear in your app launcher menu"
echo "Tray: vr-control tray (or: vr-control tray-enable for autostart)"
