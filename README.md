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


# WI VRN + WAYVR + SLIMEVR ON CACHYOS (QUEST 3)
COMPLETE FIRST-TIME SETUP GUIDE

This is the exact process that was followed to get a fully working
WiVRn + WayVR + SlimeVR setup on CachyOS using a Quest 3.

Nothing here is theoretical.
Every command listed below was actually run.

Follow every step in order.
Do not skip steps.


WHAT YOU END UP WITH

- Quest 3 connects wirelessly to the PC
- WayVR runs without OpenXR errors
- SlimeVR body tracking works
- No duplicate launches
- Correct OpenXR runtime every time

Final stack order:

SlimeVR (SolarXR IPC)
WiVRn OpenXR runtime
WiVRn server
Quest WiVRn APK
WayVR


REQUIREMENTS

- CachyOS (Wayland session)
- Meta Quest 3
- USB cable (one-time setup)
- PC and Quest on the same Wi-Fi
- Internet access


## PART 1 — INSTALL PC SOFTWARE

Run exactly:

```bash
yay -S wivrn-full-git
sudo pacman -S wayvr slimevr android-tools github-cli
```

This installs:

- WiVRn server (working AUR build)
- WayVR compositor
- SlimeVR server
- ADB (for Quest)
- GitHub CLI (for APK download)


VERIFY COMMANDS EXIST (DO NOT SKIP)

```bash
command -v wayvr
command -v wivrn-server
command -v slimevr
```

If any command is missing, stop and fix it before continuing.


## PART 2 — QUEST DEVELOPER MODE + ADB

Enable developer mode (phone):

Meta Quest app
Devices → Quest 3
Developer Mode → ON

Reboot the headset.


Enable USB debugging (headset):

Settings → System → Developer
Enable USB Debugging


Connect Quest to PC:

```bash
adb kill-server
adb start-server
adb devices
```

Inside the headset:
- Accept USB debugging
- Tick Always allow

Verify again:

```bash
adb devices
```

Expected output:

XXXXXXXXXXXX    device

If not, stop and fix before continuing.


## PART 3 — DOWNLOAD AND INSTALL QUEST APK

Login to GitHub CLI:

```bash
gh auth login
gh auth status
```

You must see:
Logged in to github.com


Download WiVRn Quest APK (GitHub Actions build)

Example run ID used:
21321590049

```bash
gh run download 21321590049 --repo WiVRn/WiVRn --name apk-Release
```

Extract:

```bash
unzip -o *.zip
ls *.apk
```

You must see exactly one APK.


Install APK to Quest:

Inside headset:
Settings → Apps → WiVRn → Uninstall
Reboot headset

Install:

```bash
adb install -r *.apk
```

Expected output:
Success

Verify:

```bash
adb shell pm list packages | grep -i wivrn
```

Expected:
package:org.wivrn.client


REQUIRED QUEST SETTING (SLIMEVR USERS)

Inside Quest WiVRn app:
- Disable Enable body tracking
- Let SlimeVR / SolarXR provide tracking


## PART 4 — FIX OPENXR RUNTIME (CRITICAL STEP)

Run:

```bash
mkdir -p ~/.config/openxr/1
ln -sf /usr/share/openxr/1/openxr_wivrn.json ~/.config/openxr/1/active_runtime.json
```

Verify:

```bash
readlink -f ~/.config/openxr/1/active_runtime.json
```

It must output:
/usr/share/openxr/1/openxr_wivrn.json

If it does not, stop and fix before continuing.


RESULT

At this point you have:

- Correct OpenXR runtime (WiVRn)
- WiVRn server running correctly
- Quest APK matched to the server
- WayVR launching cleanly
- SlimeVR providing trackers properly

This is the exact configuration that worked.



```bash
tracking_enabled='true'
tracking_stop_when_disabled='true'

- Start: `systemctl --user start vr-stack-control.service`
- Stop:  `systemctl --user stop vr-stack-control.service`
- Logs:  `journalctl --user -fu vr-stack-control.service`
