# Full application QA preview 0.6.135 — release BLOCKED

The user requested a complete application with the accumulated incremental updates.
**This is not a published GitHub release or approved replacement for the working installation.**

**Original, preserved preview ZIP SHA-256:** `888902798d190de59cc5b1271ffb19101267ec05e6bc1f819728e671f8b8c71e`. The exact ZIP was built locally and is **not uploaded to GitHub**, so GitHub Actions has not physically tested these exact new ZIP bytes in an installed CachyOS guest.

Source baseline: v0.6.126 original full app, v0.6.130 libmonado + Doctor update, v0.6.132 version sync.

Safety improvements: Remove hard-coded username from tray systemd service; per-user nonblocking flock; nonzero PARTIAL_ROLLBACK if preserving modified new files.

**Baseline source gap:** v0.6.127–v0.6.129 full source not verified. Feature parity with the user's current working application cannot be certified.

Local QA (11 October 2026; unprivileged disposable Debian container):
- 7/7 common full-installer tests PASS across the two newest preview candidates.
- 15/15 extended ZIP, version, portability, symlink, malicious rollback reference, tamper preservation, permission failure and file-lock regression tests PASS.
- Exact ZIP extracted and actually installed, reinstalled and rolled back in isolated HOME: PASS for both.
- ZIP SHA-256, CRC/path safety, shell syntax, Python AST, source watch/icon integrity and no forced service starts: PASS.
- Actual WiVRn, Quest 3, SteamVR, KDE GTK3 UI and hardware not tested.

**NOT_TESTED:** Genuine installed CachyOS GRUB/BTRFS/KVM of this exact new ZIP; full historical existing-app upgrade; actual KDE GUI/tray; real connected hardware; long-run/runtime/full Master QA.
Prior native VM fixture tests for previous original hotfix ZIPs do not establish acceptance of these new full-app previews.

All original candidate ZIPs, GitHub drafts and published releases remain untouched.
