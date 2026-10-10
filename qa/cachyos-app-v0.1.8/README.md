# Devnet CachyOS Repair guest acceptance harness v0.1.8

This is an isolated *QA harness*, not a new repair application release. Devnet CachyOS Repair remains v0.1.19.

GitHub: `devnet82/vr-stack-control` branch `qa/cachyos-app-acceptance-v0.1.8`.

- Runs a real official CachyOS live ISO in GitHub Actions QEMU/KVM on Q35 and PC emulated chipsets. Captures guest screenshots and boot/BTRFS restoration evidence.
- Executes `guest_app_qa.py` inside the genuine CachyOS guest, probes available KDE sessions/GRUB capabilities and attempts `pacman -Syu --needed pyside6 unzip` on the **disposable guest only** if PySide6 is missing.
- Does not count an offscreen PySide6 widget test as actual KDE acceptance. GUI acceptance is recorded only if 33 distinct named checks finish on an actual KWin session.
- Requires v0.1.19 ZIP SHA-256 `435bc2a88a99eef4cd5e85d71d50ca36e3d3f40361efe53db85e57e2d20fea0c`; a mismatch blocks execution.
- Enforces a BLOCKED verdict until full installed guest GRUB/reboot, real install/upgrade/rollback, Wayland/X11, Doctor operations, and physical hardware acceptance have been evidenced.

**Application input is NOT provided to GitHub by default** because the linked repository is public. To supply packages without committing source ZIPs to the public repository, the repository owner can set private repository Actions secrets `DEVNET_QA_APP_019_URL` (time-limited private download URL to exact v0.1.19 ZIP), optionally `DEVNET_QA_APP_017_URL` (previous release). GitHub runner downloads them privately and verifies the pinned archive digest before transfer to the guest. Do not put ZIP links in workflow YAML or logs. GitHub-hosted Actions may still expose downloaded source to parties with workflow edit or runner access; keep secrets limited and expiring. URLs must be under the user's control. The 0.1.17 input is staged but a full upgrade is not claimed until the installer path is inspected and executed in a disposable installed guest.

Archive and real machine tests require exact-build evidence and an independent review; no script can test user's real machine by running in GitHub.

Developers: run `python3 -m unittest -q test_guest_app_qa.py` in the harness folder. The 15 local tests cover output classifier, ZIP safety and negative paths, not the actual GUI.