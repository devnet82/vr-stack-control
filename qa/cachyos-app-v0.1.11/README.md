# Devnet CachyOS App VM QA v0.1.11

The existing real CachyOS KVM test now retrieves the frozen application ZIP directly from a GitHub Release.

## One-time release upload

Create a GitHub Release in **devnet82/vr-stack-control** with tag:

`cachyos-repair-qa-assets-v0.1.19`

Attach **one** file, with this exact name:

`devnet-cachyos-repair-v0.1.19.zip`

Frozen SHA-256 (checked by the workflow):

`435bc2a88a99eef4cd5e85d71d50ca36e3d3f40361efe53db85e57e2d20fea0c`

No Dropbox link or repository secret is required. The candidate contains `tests/fixtures/known-good-v0.1.17.zip`, so the earlier release does not need a separate upload. Do not rename or repackage the original candidate.

**Privacy:** The existing repository is public. Any attached Release ZIP will be publicly downloadable. If private hosting is required, use a private repository and move the QA workflow into it before uploading.

## QA

Workflow: `.github/workflows/cachyos-app-vm-qa-v0.1.11.yml`

Branch: `qa/cachyos-app-acceptance-v0.1.11`

It boots CachyOS in two KVM chipsets, verifies the original ZIP hash, transfers the candidate to the guest and runs packaged source checks, PySide6 acceptance where possible, real isolated staged install/upgrade/rollback/uninstall, and guest BTRFS snapshot checks. It blocks full 100% approval for untested GRUB/reboot, native session and physical hardware recovery; missing ZIP is not a PASS.

QA harness versions are independent of the unchanged application version v0.1.19.
