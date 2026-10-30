# Devnet registered application acceptance — QA BLOCKED

This is a **candidate-specific acceptance gate** for the existing Devnet Master QA.
It is not another router, a replacement for the fixed-scope controller v0.4.4,
or a licence for AI self-approval. It cannot execute real VM GUI tests yet.

## Confirmed installed-system fault (30 October 2026)
The existing `~/.local/lib/devnet-qa-automation/controller.py` checks exactly
13 fixed `vr-stack-v0.6.132` tests, returns `PASS_LIMITED` upon completion
and is called by `agent.py once`. Agent returns exit 0 on `PASS_LIMITED`.
This only proves the *bounded smoke-test scope*. It does not register other
applications, run exact-candidate GitHub CI, execute upgrade/rollback/GUI
tests, or independently close full Master QA.

## New coordinator and scope
- `registered_gate.py`: runs the candidate's GitHub-stage tests; requires an
  exact ZIP, full required lifecycle IDs and a hash-bound manifest.
- `release_coordinator.py`: rechecks ALL provenance every invocation, refuses
  inherited results, requires independently signed operator checklist,
  independently attested GitHub stage, and separately signed VM and host
  receipts with per-check SHA256 logs.
- `test_release_coordinator.py`: positive test and negative cases covering
  missing signatures, changed candidate/checklist/revision, missing stages,
  FAIL statuses, altered logs and broken chain.
- `.github/workflows/devnet-coordinator-regressions.yml`: tests this new
  code on GitHub; testing the coordinator does NOT certify a real application.
- `.github/workflows/devnet-application-qa.yml`: candidate GitHub stage;
  currently deliberately BLOCKED until a real candidate is registered.

## Exact release-closure contract
1. Operator signs `qa/application/jobs/ID/manifest.json` using an **offline
   operator private key**; commit signature to `manifest.sig`. Public key at
   `/etc/devnet-qa/trust/operator.pub` must be root-owned/non-writable.
2. Register the exact application ZIP at `qa/application/jobs/ID/candidate.zip`.
   Manifest binds the ZIP SHA256, complete applicable checks and stages.
   Do not substitute old router/Master QA ZIPs for an application.
3. Execute real candidate-specific tests in GitHub FIRST. The scope-limited
   `qa-stage-evidence/ID/receipt.json` must be independently GitHub-attested
   by the designated workflow, then placed at
   `EVIDENCE/github/receipt.json`. The coordinator validates the exact source
   commit with `/usr/bin/gh attestation verify`.
4. A trusted CachyOS VM executor (still missing) must install the **same**
   candidate and run every registered VM check. Its `EVIDENCE/vm/receipt.json`
   must be signed as `receipt.sig` with a private key inaccessible to OpenCode,
   the regular user process and the AI. Root-owned public key:
   `/etc/devnet-qa/trust/vm.pub`.
5. If any host checks are required, a separately authorised host executor
   must run them with the gaming guard honoured, and sign
   `EVIDENCE/host/receipt.json` with its *different* protected key. Root-owned
   public key: `/etc/devnet-qa/trust/host.pub`. Omission of host checks
   requires a genuinely applicable, operator-signed checklist scope.
6. VM/host receipt schema: `schema=devnet-trusted-stage-v1`, `stage`,
   `job_id`, `candidate_sha256`, `manifest_sha256`, `github_sha`,
   `previous_receipt_sha256`, `checks`, `release_approved=false`.
   Every `checks[ID]` has `status=PASS`, `log=logs/ID.log` and the
   SHA256 digest of the real file in `EVIDENCE/STAGE/logs/ID.log`.
   VM receipt chains to the GitHub receipt; host receipt chains to VM.
7. Only a verified result of `READY_FOR_OPERATOR_ACCEPTANCE` permits
   *requesting* the user's final acceptance. It **never** grants release
   approval itself. Any changed ZIP/checklist/source revision invalidates
   all prior receipts; run GitHub→VM→host again.

Evaluate (read-only; requires actual signed evidence and trusted public keys):

```sh
python3 qa/application/release_coordinator.py \
  --job-dir qa/application/jobs/ID \
  --evidence-dir /mnt/devnet-ai/qa/evidence/ID
```

## Current blockers — do NOT misreport as passed
- No genuine candidate ZIP and complete operator-approved registration exists
  on the current QA branch.
- No trusted, candidate-specific CachyOS VM install/GUI/tray/rollback executor
  or separate signer has been deployed.
- No protected host acceptance executor or signer has been deployed.
- No full-scope receipt chain has been generated or validated.
- GitHub coordinator regression run 41140097961: 21/21 PASS on commit\n  8b0e42d82610403c886ef35474b4050d04d82e6d.\n- GitHub application-stage run 41140214160: 21/21 regression PASS, then\n  **expected BLOCKED** because no real candidate registration exists.\n  This is NOT completed application acceptance.

**Release remains BLOCKED.** The original v0.4.4 runner, router v0.2.4,
Master QA v0.3.8, original ZIPs, existing VM and gaming guard are preserved.
