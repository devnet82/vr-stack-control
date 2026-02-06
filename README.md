# VR Stack Control v0.6.52

This release replaces your old `vr-control --gui` YAD UI with a GTK GUI.

## Install

```bash
pkill -9 -f "vr-control --gui" 2>/dev/null || true
pkill -9 -f yad 2>/dev/null || true

cd ~/Downloads
unzip -o vr-stack-control-v0.6.52.zip
cd vr-stack-control-v0.6.52
bash install.sh
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

Note: Tray integration was removed in v0.6.30. Closing the window exits normally.

## v0.6.52 change

- Apps & Settings now shows **Detected paths (read-only)** so you can verify where OpenXR / SteamVR / XRizer are found.


## Tracking backend toggle

You can enable/disable tracking independently of the rest of the stack.

- ON: tracking starts first (before the server and VR app)
- OFF: the stack starts without tracking

Config keys (in `~/.config/vr-stack/stack.conf`):

```bash
tracking_enabled='true'
tracking_stop_when_disabled='true'
```
