# Devnet registered application acceptance — QA BLOCKED

This is a **candidate-specific acceptance gate** for the existing Devnet Master QA.
It is not another router, a replacement for the fixed-scope controller v0.4.4,
or a licence for AI self-approval. The candidate-aware VM-stage engine has
passed its regression tests but has NOT been deployed or used to run a real app.

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
- `handoff.py`: assembles and checks a SHA256-bound transport bundle containing
  the exact ZIP, the unmodified approved checklist and signature, and the
  independently GitHub-attested receipt. Neither handoff creation nor checking
  can grant VM PASS or release approval.
- `test_handoff.py`: covers signed policy, two independent GitHub attestations,
  altered packages, altered checklists, symlinks, missing files and false approval.
- `stage_executor.py`: executes only the protected, exact per-app VM/host driver
  commands after checking the signed operator manifest, matching candidate bytes
  and signed GitHub handoff. Captures actual subprocess logs, stops on failure,
  prevents evidence reuse and intentionally cannot sign or approve itself.
  VM/host protected drivers, isolated signing services and host broker are not
  yet provisioned.
- `test_stage_executor.py`: verified regressions for real fixture subprocesses,
  failure aborts, driver scope, fresh evidence and gaming pause; these are
  fixture tests, NOT actual CachyOS GUI acceptance.
- `test_release_coordinator.py`: positive test and negative cases covering
  missing signatures, changed candidate/checklist/revision, missing stages,
  FAIL statuses, altered logs and broken chain.
- `.github/workflows/devnet-coordinator-regressions.yml`: tests this new
  code on GitHub; testing the coordinator does NOT certify a real application.
- `.github/workflows/devnet-application-qa.yml`: candidate GitHub stage;
  currently deliberately BLOCKED until a real candidate is registered.

## Exact release-closure contract
1. Operator signs the **stable** `qa/application/jobs/ID/policy.json`
   checklist using an offline private key and saves `policy.sig`. A changing
   candidate `manifest.json` must contain the EXACT same approved checks but
   binds the new source ZIP SHA256. The existing policy may be reused only
   when that approved checklist is unchanged; every new candidate revision
   still requires all applicable tests to be run again. Public key at
   `/etc/devnet-qa/trust/operator.pub` must be root-owned/non-writable.
2. Register the exact application ZIP at `qa/application/jobs/ID/candidate.zip`.
   Manifest binds the ZIP SHA256, complete applicable checks and stages.
   Do not substitute old router/Master QA ZIPs for an application.
3. Execute real candidate-specific tests in GitHub FIRST. The scope-limited
   `qa-stage-evidence/ID/receipt.json` must be independently GitHub-attested
   by the designated workflow, then placed at
   `EVIDENCE/github/receipt.json`. The coordinator validates the exact source
   commit with `/usr/bin/gh attestation verify`.
4. Deploy the new stage executor with a root-controlled, job-specific VM
   test driver in the CachyOS guest. The driver must install the **same**
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
- No current FULL application ZIP and complete operator-approved registration
  exists on this QA branch. We found an unpublished draft release asset
  `vr-stack-control-v0.6.132.zip` (SHA256
  `04118623d828de96526e1c185409c586bf9ed1b4b1318451e4301277ff69baf1`,
  4,675 bytes), but the 30 Sep QA engineering report identifies it as a
  **version-sync hotfix**, NOT the full application. A provisional full-app
  registration was withdrawn; the original draft ZIP was NOT touched.
- GitHub Actions cannot read that draft-release asset using its current
  token: `Resource not accessible by integration (HTTP 403)`.
  Do not publish the draft or weaken token restrictions just to make CI green.
- The full-app preview v0.6.135 ZIP was not uploaded to GitHub according
  to its own archived STATUS.md; no exact full-app candidate is supplied.
- There is no protected, complete, operator-signed per-application checklist.
- `stage_executor.py` exists, but has NOT been installed on the VM. Real
  candidate-specific install/GUI/tray/rollback driver and independent signer
  have not been deployed or verified.
- No protected host acceptance executor or signer has been deployed.
- No full-scope receipt chain has been generated or validated.
- GitHub coordinator regression run 41141854109: **41/41 PASS** on commit
  b8e8bab0e9734669cf8fc506d831402dd1cac549 (includes transport tampering
  protection and real fixture subprocesses, not real application execution).
- GitHub application-stage run 41140630122: blocked with HTTP 403 when
  attempting to read the inaccessible unpublished draft asset.
- GitHub application-stage run 41140960760: intentionally BLOCKED because
  no complete application is registered. Neither is a full acceptance run.

**Release remains BLOCKED.** The original v0.4.4 runner, router v0.2.4,
Master QA v0.3.8, original ZIPs, existing VM and gaming guard are preserved.

## Implementation boundary

The newly added `package-private-vm-handoff` GitHub job depends on the
independent GitHub attestation verification job. It cannot trigger until an
actual candidate completes GitHub checks. Its output is an unsigned transport
artifact and does **not** execute real CachyOS VM, host GUI or rollback checks.
The local broker, real application-specific VM test driver, protected signer
and automatic dispatch are still missing. The earlier full native CachyOS
GitHub VM workflow was specific to a small hotfix and is NOT a substitute for
full application GitHub-first testing. Real GitHub-hosted VM acceptance remains
NOT_TESTED for any full application candidate.

A preserved `devnet-master-qa-registered-application-stages-v0.1.0-QA-BLOCKED.zip`
exists in the ChatGPT Library, but its original bytes could not be materialised
through the present connection. Do not represent it as inspected or assume
that its contents were installed or integrated.
