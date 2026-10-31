#!/usr/bin/env python3
"""Assemble and independently verify an exact-candidate CI -> VM handoff.

A handoff is transport, NOT a release and not proof the application was run in
a VM. A private-VM broker must verify it before calling the stage executor.
No SSH, private VM access, installer execution or signature creation here.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys

import release_coordinator as gate


def assemble(job_dir: Path, evidence_dir: Path, target: Path):
    manifest, manifest_hash, checks = gate.manifest_for(job_dir)
    receipt, source = gate.github_receipt(job_dir, evidence_dir, manifest_hash, checks)
    policy = job_dir / "policy.json"
    policy_sig = job_dir / "policy.sig"
    gate.require(policy.is_file() and not policy.is_symlink()
                 and policy_sig.is_file() and not policy_sig.is_symlink(),
                 "operator policy/signature missing")
    p = gate.load(policy)
    gate.require(isinstance(p, dict) and
                 set(p) == {"schema", "job_id", "checks"} and
                 p["schema"] == "devnet-qa-checklist-v1" and
                 p["job_id"] == manifest["job_id"] and
                 p["checks"] == manifest["checks"],
                 "operator-approved checklist mismatch")
    gate.require(not target.exists(), "handoff exists: never reuse or overwrite")
    target.mkdir(parents=True,mode=0o700)
    job_out = target / manifest["job_id"]
    job_out.mkdir(mode=0o700)
    gh_out = target / "evidence" / "github"
    gh_out.mkdir(mode=0o700,parents=True)
    inputs = [(job_dir / "candidate.zip", job_out / "candidate.zip"),
              (job_dir / "manifest.json", job_out / "manifest.json"),
              (policy, job_out / "policy.json"),
              (policy_sig, job_out / "policy.sig"),
              (receipt, gh_out / "receipt.json")]
    for src, dst in inputs:
        gate.require(src.is_file() and not src.is_symlink(), "missing/symlink source")
        shutil.copyfile(src,dst)
    details = {"schema":"devnet-qa-handoff-v1",
               "job_id":manifest["job_id"],
               "candidate_sha256":manifest["sha256"],
               "manifest_sha256":manifest_hash,
               "policy_sha256":gate.sha256(policy),
               "github_receipt_sha256":gate.sha256(receipt),
               "github_sha":source,
               "release_approved":False}
    (target/"HANDOFF.json").write_text(json.dumps(details,sort_keys=True,indent=2)+"\n")
    return details


def verify(target: Path, trust_dir: Path, repo: str,
           signature_verifier=gate.verify_trusted_signature,
           github_verifier=gate.verify_github_signature):
    gate.require(target.is_dir() and not target.is_symlink(), "invalid handoff")
    d=gate.load(target/"HANDOFF.json")
    gate.require(isinstance(d,dict) and set(d) ==
                 {"schema","job_id","candidate_sha256","manifest_sha256",
                  "policy_sha256","github_receipt_sha256","github_sha",
                  "release_approved"} and
                 d["schema"]=="devnet-qa-handoff-v1" and
                 d["release_approved"] is False, "handoff schema/approval violation")
    job_id=d["job_id"]
    gate.require(isinstance(job_id,str) and gate.ID.fullmatch(job_id),
                 "invalid handoff job id")
    job_dir=target/job_id
    evidence_dir=target/"evidence"
    gate.require(job_dir.is_dir() and not job_dir.is_symlink(),
                 "missing/unsafe job directory")
    for relative in ["candidate.zip","manifest.json","policy.json","policy.sig"]:
        path=job_dir/relative
        gate.require(path.is_file() and not path.is_symlink(),
                     "missing/unsafe handoff file "+relative)
    receipt_path=evidence_dir/"github"/"receipt.json"
    gate.require(receipt_path.is_file() and not receipt_path.is_symlink(),
                 "missing/unsafe GitHub receipt")
    manifest, manifest_hash, checks=gate.manifest_for(job_dir)
    gate.require(d["candidate_sha256"] == manifest["sha256"] and
                 d["manifest_sha256"] == manifest_hash and
                 d["policy_sha256"] == gate.sha256(job_dir/"policy.json") and
                 d["github_receipt_sha256"] == gate.sha256(receipt_path),
                 "handoff hashes do not match exact input bytes")
    gate.verified_policy(job_dir,trust_dir,signature_verifier)
    observed, source=gate.github_receipt(job_dir,evidence_dir,manifest_hash,checks)
    gate.require(d["github_sha"] == source and observed == receipt_path,
                 "handoff revision/receipt mismatch")
    # Verify BOTH GitHub-issued attestations; a JSON PASS is insufficient.
    github_verifier(receipt_path,repo,source)
    github_verifier(job_dir/"candidate.zip",repo,source)
    return {"schema":"devnet-qa-verified-handoff-v1",
            "job_id":job_id,"candidate_sha256":manifest["sha256"],
            "github_sha":source,"github":"PASS_SIGNED",
            "vm":"NOT_TESTED","host":"NOT_TESTED",
            "release_approved":False}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["assemble","verify"])
    parser.add_argument("--job-dir",type=Path)
    parser.add_argument("--evidence-dir",type=Path)
    parser.add_argument("--handoff-dir",type=Path,required=True)
    parser.add_argument("--trust-dir",type=Path,default=Path("/etc/devnet-qa/trust"))
    parser.add_argument("--repo",default="devnet82/vr-stack-control")
    args=parser.parse_args()
    try:
        if args.action=="assemble":
            gate.require(args.job_dir is not None and
                         args.evidence_dir is not None,
                         "assemble requires job-dir and evidence-dir")
            result=assemble(args.job_dir,args.evidence_dir,args.handoff_dir)
        else:
            result=verify(args.handoff_dir,args.trust_dir,args.repo)
    except (gate.Blocked,OSError,ValueError,KeyError,TypeError,
            json.JSONDecodeError) as exc:
        print(json.dumps({"decision":"BLOCKED","reason":str(exc),
                          "release_approved":False}))
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    sys.exit(main())
