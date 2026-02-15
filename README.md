# VR Stack Control v0.6.76-openxrfix4

This release replaces your old `vr-control --gui` YAD UI with a GTK GUI.

## Install

```bash
cd ~/Downloads
rm -rf vr-stack-control-v0.6.85
unzip -o vr-stack-control-v0.6.85.zip
cd vr-stack-control-v0.6.85
chmod +x install.sh uninstall.sh bin/*
./install.sh
systemctl --user daemon-reload
```

## Run

```bash
vr-control --gui
```

## What’s new

- Tracking backend ON/OFF toggle (start stack with or without tracking software like SlimeVR)
- `vr-control --gui` now opens the GTK GUI
- Profiles page: create / rename / delete / edit profiles
- Removed the old “Actions” tab (Start/Stop + settings cover most use-cases)
- Apps & Settings page includes inline “why this matters” help text

Tray integration is available again via an optional tray service:

- Start tray once: `vr-control tray`
- Autostart tray: `vr-control tray-enable`
- Disable tray: `vr-control tray-disable`

The backend service still runs headless; the tray is a separate GUI helper.

## v0.6.68 change

- XR Runtime names clarified:
  - **WiVRn (Native / Quest streaming)**
  - **SteamVR (Steam Link / Legacy)**
- New toggle: **Auto-start SteamVR** (default OFF). When OFF, selecting SteamVR will set the runtime but won’t auto-launch SteamVR.

### Steam per-game Launch Options helper (WiVRn)

If a Steam title insists on using the wrong runtime, set its Launch Options to:

```bash
env PRESSURE_VESSEL_IMPORT_OPENXR_1_RUNTIMES=1 \
  XR_RUNTIME_JSON="$HOME/.config/openxr/1/wivrn_runtime.json" \
  OPENXR_RUNTIME_JSON="$HOME/.config/openxr/1/wivrn_runtime.json" \
  %command%
```


## Tracking backend toggle

You can enable/disable tracking independently of the rest of the stack.

- ON: tracking starts first (before the server and VR app)
- OFF: the stack starts without tracking

Config keys (in `~/.config/vr-stack/stack.conf`):

```bash
tracking_enabled='true'
tracking_stop_when_disabled='true'
```

## Runner (new in v0.6.68)

The systemd user service now runs a Python daemon (`~/.local/bin/vr-stackd`).
This means the *app itself* manages the stack (start/stop/monitor) instead of
calling a bash runner script.

- Start: `systemctl --user start vr-stack-control.service`
- Stop:  `systemctl --user stop vr-stack-control.service`
- Logs:  `journalctl --user -fu vr-stack-control.service`
