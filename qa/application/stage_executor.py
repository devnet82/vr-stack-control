#!/usr/bin/env python3
"""Registered Devnet QA stage executor (unprivileged, unsigned, fail closed).

Trust assumptions:
  * Complete operator checklist is signed by an offline private key.
  * The root-owned, non-writable driver defines real app-specific commands.
  * GitHub source/ZIP/receipt are independently attested before VM execution.
  * This process cannot sign evidence or approve a release.
  * A separate, privileged verifier must decide whether evidence is genuine.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import release_coordinator as gate

MAX_OUTPUT = 2_000_000
MAX_TIMEOUT = 300

def safe_driver(path: Path, ids):
    gate.require(path.is_file() and not path.is_symlink() and
                 path.stat().st_uid == 0 and
                 not (path.stat().st_mode & 0o022),
                 "trusted root-controlled driver unavailable")
    driver = gate.load(path)
    gate.require(isinstance(driver, dict) and set(driver) ==
                 {"schema", "stage", "job_id", "checks"},
                 "invalid driver schema")
    checks = driver["checks"]
    gate.require(driver["schema"] == "devnet-stage-driver-v1" and
                 isinstance(checks, dict) and set(checks) == set(ids),
                 "driver does not cover EXACT registered stage checklist")
    for cid, test in checks.items():
        gate.require(isinstance(test, dict) and set(test) ==
                     {"argv", "timeout"}, "invalid trusted test schema")
        argv = test["argv"]
        timeout = test["timeout"]
        gate.require(isinstance(argv, list) and bool(argv) and
                     all(isinstance(x, str) and bool(x) and "\x00" not in x
                         for x in argv) and
                     isinstance(timeout, int) and not isinstance(timeout, bool) and
                     1 <= timeout <= MAX_TIMEOUT, "invalid trusted command")
        executable = Path(argv[0])
        gate.require(executable.is_absolute() and executable.is_file() and
                     not executable.is_symlink(), "not a fixed absolute executable")
    return driver

def game_guard():
    # The host broker is separately required to pause VM dispatch when gaming.
    # For direct host-only tests this guard must be present and callable.
    p = Path("/home/dave/.local/lib/devnet-qa-automation/agent.py")
    gate.require(p.is_file() and not p.is_symlink(), "host game guard unavailable")
    import importlib.util
    spec = importlib.util.spec_from_file_location("devnet_gameguard", p)
    gate.require(spec is not None and spec.loader is not None,
                 "host game guard cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    gate.require(not module.gaming_now(), "gaming pause active")

def run_stage(job_dir: Path, evidence_dir: Path, driver_path: Path, trust_dir: Path,
              repo: str, stage: str, *,
              github_verifier=gate.verify_github_signature,
              signature_verifier=gate.verify_trusted_signature,
              pause=game_guard):
    gate.require(stage in ("vm", "host"), "unsupported stage")
    signature_verifier(job_dir/"manifest.json", job_dir/"manifest.sig",
                       trust_dir/"operator.pub")
    manifest, manifest_hash, by_stage = gate.manifest_for(job_dir)
    gh_receipt, source = gate.github_receipt(job_dir, evidence_dir, manifest_hash, by_stage)
    github_verifier(gh_receipt, repo, source)
    previous = gate.sha256(gh_receipt)
    if stage == "host":
        previous = gate.signed_stage("vm", job_dir, evidence_dir, trust_dir,
                                     source, manifest_hash, by_stage["vm"],
                                     previous, signature_verifier)
    ids = by_stage[stage]
    gate.require(ids, "empty stage; never invent non-applicability")
    driver = safe_driver(driver_path, ids)
    gate.require(driver["job_id"] == manifest["job_id"] and
                 driver["stage"] == stage, "driver pinned to a different job/stage")
    candidate = job_dir/"candidate.zip"
    gate.require(candidate.is_file() and not candidate.is_symlink() and
                 gate.sha256(candidate) == manifest["sha256"],
                 "exact candidate missing or changed")
    # Never inherit a prior PASS, even if the previous build appears identical.
    root = evidence_dir/stage
    gate.require(not root.exists(), "existing stage evidence: start a fresh revision/run")
    root.mkdir(parents=True, mode=0o700)
    (root/"logs").mkdir(mode=0o700)
    results = {}
    all_pass = True
    for cid in ids:
        # On host, a live guard is mandatory before EVERY command.
        if stage == "host":
            pause()
        command = driver["checks"][cid]
        log_path = root/"logs"/(cid+".log")
        start = time.monotonic()
        with log_path.open("xb") as log:
            os.chmod(log_path, 0o600)
            try:
                # No shell interpolation, no inherited credentials, no home writes.
                cp = subprocess.run(command["argv"], cwd=job_dir,
                                    env={"PATH":"/usr/bin:/bin", "LANG":"C.UTF-8",
                                         "HOME":"/tmp", "DEVNET_QA_CANDIDATE":str(candidate)},
                                    stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT,
                                    timeout=command["timeout"], check=False)
                ok = cp.returncode == 0
                code = cp.returncode
            except (subprocess.TimeoutExpired, OSError) as exc:
                ok = False
                code = -1
                log.write(("QA BLOCKED: "+type(exc).__name__+"\n").encode())
            log.flush()
            os.fsync(log.fileno())
        if log_path.stat().st_size > MAX_OUTPUT:
            ok = False
        all_pass = all_pass and ok
        results[cid] = {"status":"PASS" if ok else "FAIL",
                        "log":"logs/"+cid+".log",
                        "log_sha256":gate.sha256(log_path)}
        if not ok:
            # Stop after failure rather than running destructive follow-on tests.
            break
    if not all_pass:
        (root/"blocked.json").write_text(json.dumps({
            "stage":stage, "job_id":manifest["job_id"],
            "result":"BLOCKED", "checks":results,
            "release_approved":False},sort_keys=True)+"\n")
        raise gate.Blocked("stage failed: no signed PASS receipt created")
    receipt = {"schema":gate.SCHEMA, "stage":stage,
               "job_id":manifest["job_id"],
               "candidate_sha256":manifest["sha256"],
               "manifest_sha256":manifest_hash,
               "github_sha":source,
               "previous_receipt_sha256":previous,
               "checks":results,"release_approved":False}
    (root/"receipt.json").write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    # Deliberately NO receipt.sig: a distinct trusted executor/signer must
    # independently inspect real logs and sign from a protected identity.
    return {"stage":stage,"result":"EXECUTED_UNSIGNED",
            "checks_passed":len(ids), "release_approved":False}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--job-dir", type=Path, required=True)
    p.add_argument("--evidence-dir", type=Path, required=True)
    p.add_argument("--driver", type=Path, required=True)
    p.add_argument("--trust-dir", type=Path, default=Path("/etc/devnet-qa/trust"))
    p.add_argument("--repo", default="devnet82/vr-stack-control")
    p.add_argument("--stage", choices=["vm","host"], required=True)
    a = p.parse_args()
    try:
        d = run_stage(a.job_dir.resolve(), a.evidence_dir.resolve(),
                      a.driver, a.trust_dir, a.repo, a.stage)
    except (gate.Blocked, OSError, ValueError, KeyError,
            TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"stage":a.stage, "result":"BLOCKED",
                          "reason":str(exc), "release_approved":False}))
        return 2
    print(json.dumps(d, sort_keys=True))
    return 0

if __name__ == "__main__":
    sys.exit(main())
