#!/usr/bin/env bash
set -euo pipefail

rm -f "$HOME/.local/bin/vr-doctor"
rm -f "$HOME/.local/bin/vr-control"
rm -f "$HOME/.local/bin/vr-control-gui"
rm -f "$HOME/.local/bin/vr-stackd"
rm -f "$HOME/.local/bin/vr-stack-tray"
rm -f "$HOME/.local/bin/vr-stack-run.sh"

rm -f "$HOME/.local/share/applications/vr-control-panel.desktop"
rm -f "$HOME/.local/share/applications/vr-stack-tray.desktop"

rm -f "$HOME/.config/systemd/user/vr-stack-control.service"
rm -f "$HOME/.config/systemd/user/vr-stack-tray.service"

systemctl --user daemon-reload >/dev/null 2>&1 || true

echo "Uninstalled VR Stack Control"
