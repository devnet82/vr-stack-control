#!/usr/bin/env python3
"""Devnet Master QA: independently verify a registered candidate's stage chain.

This is a fail-closed release-acceptance *gate*, not a privileged executor.
The existing v0.4.4 fixed-scope controller remains untouched.
No AI result, systemd exit code or 13-check PASS_LIMITED result grants acceptance.
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

SCHEMA = "devnet-trusted-stage-v1"
MANDATORY = frozenset(("install", "upgrade", "rollback", "gui", "tray",
                       "recovery", "security"))
ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
GIT_SHA = re.compile(r"^[a-f0-9]{40}$")
WORKFLOW = "devnet-application-qa.yml"
STAGES = ("github", "vm", "host")


class Blocked(Exception):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def manifest_for(job_dir: Path):
    manifest_file = job_dir / "manifest.json"
    manifest = load(manifest_file)
    require(isinstance(manifest, dict), "invalid manifest type")
    require(set(manifest) == {"job_id", "candidate", "sha256", "checks"},
            "manifest schema mismatch")
    job_id = manifest["job_id"]
    require(isinstance(job_id, str) and ID.fullmatch(job_id), "invalid job ID")
    require(job_dir.name == job_id, "job directory mismatch")
    require(manifest["candidate"] ==
            "qa/application/jobs/" + job_id + "/candidate.zip",
            "candidate path is not exact")
    candidate_sha = manifest["sha256"]
    require(isinstance(candidate_sha, str) and SHA256.fullmatch(candidate_sha),
            "invalid candidate SHA256")
    candidate = job_dir / "candidate.zip"
    require(candidate.is_file() and not candidate.is_symlink(),
            "candidate ZIP missing or symlink")
    require(sha256(candidate) == candidate_sha, "candidate ZIP bytes changed")
    checks = manifest["checks"]
    require(isinstance(checks, list) and checks, "empty checklist")
    by_stage = {s: [] for s in STAGES}
    all_ids = set()
    for check in checks:
        require(isinstance(check, dict) and set(check) ==
                {"id", "stage", "argv"}, "check schema mismatch")
        cid, stage, argv = check["id"], check["stage"], check["argv"]
        require(isinstance(cid, str) and ID.fullmatch(cid) and cid not in all_ids,
                "invalid or duplicate check ID")
        require(stage in STAGES and isinstance(argv, list), "invalid check stage")
        if stage != "github":
            require(argv == [], "VM and host commands must come from trusted executors")
        else:
            require(len(argv) > 0 and all(isinstance(a, str) and a for a in argv),
                    "GitHub test has no valid executable")
        by_stage[stage].append(cid)
        all_ids.add(cid)
    require(MANDATORY.issubset(all_ids), "required lifecycle checks missing")
    require(by_stage["github"], "no candidate-specific GitHub tests")
    require(by_stage["vm"], "no actual VM acceptance checks registered")
    return manifest, sha256(manifest_file), by_stage


def verified_policy(job_dir, trust_dir, signature_verifier):
    """Check stable approved scope separately from the changing candidate revision."""
    policy_path = job_dir / "policy.json"
    signature_verifier(policy_path, job_dir / "policy.sig", trust_dir / "operator.pub")
    policy = load(policy_path)
    require(isinstance(policy, dict) and
            set(policy) == {"schema", "job_id", "checks"} and
            policy.get("schema") == "devnet-qa-checklist-v1" and
            policy.get("job_id") == job_dir.name,
            "approved QA policy schema/job mismatch")
    manifest = load(job_dir / "manifest.json")
    require(isinstance(manifest, dict) and
            policy["checks"] == manifest.get("checks"),
            "candidate checklist changed without operator policy approval")
    return sha256(policy_path)


def github_receipt(job_dir, evidence_dir, manifest_hash, by_stage):
    path = evidence_dir / "github" / "receipt.json"
    r = load(path)
    require(isinstance(r, dict), "GitHub receipt invalid")
    require(r.get("schema") == 1, "wrong GitHub receipt schema")
    require(r.get("job_id") == job_dir.name, "wrong GitHub job")
    require(r.get("candidate_sha256") == sha256(job_dir / "candidate.zip"),
            "GitHub candidate mismatch")
    require(r.get("manifest_sha256") == manifest_hash, "GitHub checklist mismatch")
    require(r.get("full_acceptance") is False and
            r.get("release_approved") is False, "GitHub receipt claims acceptance")
    source = r.get("github_sha")
    require(isinstance(source, str) and GIT_SHA.fullmatch(source),
            "missing exact GitHub source commit")
    results = r.get("checks")
    require(isinstance(results, list) and len(results) ==
            sum(map(len, by_stage.values())), "incomplete GitHub checklist")
    # Order and stages are fixed by the manifest, not by AI-produced records.
    expected = [(c["id"], c["stage"]) for c in load(job_dir / "manifest.json")["checks"]]
    for item, (cid, stage) in zip(results, expected):
        require(isinstance(item, dict) and item.get("id") == cid,
                "GitHub check identity mismatch")
        if stage == "github":
            require(item.get("status") == "PASS" and
                    item.get("exit_code") == 0 and
                    isinstance(item.get("output_sha256"), str) and
                    SHA256.fullmatch(item["output_sha256"]),
                    "GitHub test missing successful execution evidence")
        else:
            require(item.get("stage") == stage and
                    item.get("status") == "NOT_TESTED",
                    "GitHub attempted to certify later stages")
    return path, source


def verify_github_signature(path: Path, repo: str, source: str):
    require(bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo)),
            "invalid pinned GitHub repository")
    gh = Path("/usr/bin/gh")
    require(gh.is_file() and not gh.is_symlink() and gh.stat().st_uid == 0 and
            (gh.stat().st_mode & 0o022) == 0, "trusted GitHub verifier binary unavailable")
    args = [str(gh), "attestation", "verify", str(path), "--repo", repo,
            "--signer-workflow", repo + "/.github/workflows/" + WORKFLOW,
            "--source-digest", source]
    try:
        p = subprocess.run(args, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked("GitHub independent attestation unavailable") from exc
    require(p.returncode == 0, "GitHub signature/source verification failed")


def verify_trusted_signature(path: Path, signature: Path, key: Path):
    # Only protected, root-provisioned signing identities can verify VM/host.
    require(key.is_file() and not key.is_symlink() and
            key.stat().st_uid == 0 and
            (key.stat().st_mode & 0o022) == 0,
            "trusted stage public key missing or unprotected")
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        public = serialization.load_pem_public_key(key.read_bytes())
        require(isinstance(public, Ed25519PublicKey),
                "trusted stage key is not Ed25519")
        public.verify(signature.read_bytes(), path.read_bytes())
    except (ImportError, OSError, ValueError, TypeError) as exc:
        raise Blocked("trusted signature verification unavailable") from exc
    except Exception as exc:
        raise Blocked("trusted stage signature failed") from exc


def signed_stage(stage, job_dir, evidence_dir, trust_dir, source, manifest_hash,
                 check_ids, previous_receipt_sha, verify_signature=verify_trusted_signature):
    path = evidence_dir / stage / "receipt.json"
    signature = evidence_dir / stage / "receipt.sig"
    key = trust_dir / (stage + ".pub")
    require(path.is_file() and signature.is_file(),
            stage.upper() + " signed execution receipt absent")
    verify_signature(path, signature, key)
    r = load(path)
    require(isinstance(r, dict) and set(r) ==
            {"schema", "stage", "job_id", "candidate_sha256", "manifest_sha256",
             "github_sha", "previous_receipt_sha256", "checks", "release_approved"},
            stage.upper() + " signed receipt schema mismatch")
    require(r["schema"] == SCHEMA and r["stage"] == stage and
            r["job_id"] == job_dir.name, "stage identity mismatch")
    require(r["candidate_sha256"] == sha256(job_dir / "candidate.zip") and
            r["manifest_sha256"] == manifest_hash and
            r["github_sha"] == source,
            stage.upper() + " wrong application/checklist/revision")
    require(r["previous_receipt_sha256"] == previous_receipt_sha and
            r["release_approved"] is False, "broken evidence chain/unsafe approval")
    checks = r["checks"]
    require(isinstance(checks, dict) and set(checks) == set(check_ids),
            stage.upper() + " incomplete registered checklist")
    for cid in check_ids:
        item = checks[cid]
        require(isinstance(item, dict) and set(item) ==
                {"status", "log", "log_sha256"},
                stage.upper() + " missing per-check execution evidence")
        require(item["status"] == "PASS" and
                item["log"] == "logs/" + cid + ".log" and
                isinstance(item["log_sha256"], str) and
                SHA256.fullmatch(item["log_sha256"]),
                stage.upper() + " invalid check result/evidence path")
        log = path.parent / "logs" / (cid + ".log")
        require(log.is_file() and not log.is_symlink() and
                sha256(log) == item["log_sha256"],
                stage.upper() + " missing or tampered execution log")
    return sha256(path)


def assess(job_dir: Path, evidence_dir: Path, trust_dir: Path, repo: str,
           github_verifier=verify_github_signature,
           stage_verifier=verify_trusted_signature):
    # Every invocation independently rebuilds identity and evidence; never
    # inherits a PASS or persists an AI-issued approval.
    # Signed stable checklist persists across candidate revisions; exact
    # candidate SHA/revision and all actual results MUST be retested afresh.
    verified_policy(job_dir, trust_dir, stage_verifier)
    m, manifest_hash, by_stage = manifest_for(job_dir)
    gh_path, source = github_receipt(job_dir, evidence_dir, manifest_hash, by_stage)
    github_verifier(gh_path, repo, source)
    github_verifier(job_dir / "candidate.zip", repo, source)
    previous = sha256(gh_path)
    previous = signed_stage("vm", job_dir, evidence_dir, trust_dir, source,
                            manifest_hash, by_stage["vm"], previous, stage_verifier)
    if by_stage["host"]:
        previous = signed_stage("host", job_dir, evidence_dir, trust_dir, source,
                                manifest_hash, by_stage["host"], previous, stage_verifier)
    return {"schema": "devnet-acceptance-gate-v1",
            "job_id": m["job_id"], "candidate_sha256": m["sha256"],
            "manifest_sha256": manifest_hash, "github_sha": source,
            "github": "PASS_SIGNED", "vm": "PASS_SIGNED",
            "host": "PASS_SIGNED" if by_stage["host"] else "NOT_APPLICABLE",
            "decision": "READY_FOR_OPERATOR_ACCEPTANCE",
            "release_approved": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--job-dir", type=Path, required=True)
    p.add_argument("--evidence-dir", type=Path, required=True)
    p.add_argument("--trust-dir", type=Path,
                   default=Path("/etc/devnet-qa/trust"))
    p.add_argument("--repo", default="devnet82/vr-stack-control")
    args = p.parse_args()
    try:
        result = assess(args.job_dir.resolve(), args.evidence_dir.resolve(),
                        args.trust_dir.resolve(), args.repo)
    except (Blocked, OSError, KeyError, TypeError, ValueError,
            json.JSONDecodeError) as exc:
        print(json.dumps({"decision": "BLOCKED",
                          "reason": str(exc), "release_approved": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
