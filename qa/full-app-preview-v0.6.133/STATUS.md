# VR Stack Control v0.6.133 — full application QA preview

Release approval: BLOCKED. Do not publish or deploy this preview.

User requested a complete app package rather than the update-only v0.6.132 hotfix.
New local preview ZIP SHA-256: c7308d0826705454b522ee9a13d648955c1dafbb8d445abf6475ec4b39ee2ddc.
Preview build uses original full v0.6.126 components, original v0.6.130 libmonado helper/Doctor and v0.6.132 metadata-sync behaviour.
Missing verified full v0.6.127 to v0.6.129 application sources prevent claiming feature parity.

The preview includes full binaries, a fail-closed user-scoped installer, dry run, preserved config, manifest backups and rollback.
Existing v0.6.130–v0.6.132 app upgrades retain the installed daemon, GUI and other runtime code, updating only version metadata and missing helper files.
Isolated preview regression suite: 7/7 PASS shared tests (two apps); shell and Python syntax, CRC, user-home upgrade and rollback checks PASS.
Native installed CachyOS VM for the new preview and physical Quest/SteamVR / GTK GUI regression remain NOT_TESTED.

Original releases and draft original ZIP assets were not edited or published.
QA preview ZIP is available only as a conversation artifact; not a GitHub release.