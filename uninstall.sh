#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="vr-stack-control.service"

systemctl --user stop "$SERVICE" >/dev/null 2>&1 || true
systemctl --user disable "$SERVICE" >/dev/null 2>&1 || true

rm -f "$HOME/bin/vr-stack-run.sh"
rm -f "$HOME/bin/vr-control-gui.sh"
rm -f "$HOME/bin/vr-tray.sh"
rm -f "$HOME/bin/quest-watch.sh"
rm -f "$HOME/.config/systemd/user/$SERVICE"
rm -f "$HOME/.local/share/applications/vr-control-panel.desktop"
rm -f "$HOME/.local/share/applications/vr-tray.desktop"

systemctl --user daemon-reload

echo "Uninstalled VR Stack Control."
echo "Note: your config/logs were left intact:"
echo "  $HOME/.config/vr-stack/stack.conf"
echo "  $HOME/.local/share/vr-stack.log"
