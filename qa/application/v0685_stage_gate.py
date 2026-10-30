#!/usr/bin/env python3
"""Independent fail-closed scope-limited v0.6.85 GitHub + native guest evidence check.

Never turns a genuine CachyOS LIVE ISO run into installed-KDE/host acceptance.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

EXPECTED="db9af6ff47f3abcf07cf452ddd91e91cbd75a10296c0c6050bb5c612980d9cf3"
UBUNTU={"fresh_install","exact_install_hashes","reinstall",
        "reinstalled_file_hashes","preserve_existing_config","uninstall",
        "uninstall_removes_app_files","uninstall_preserves_user_config",
        "outside_user_data_preserved"}
GUEST_PACKAGE={"native_cachyos","control_disk_identity","exact_sha256",
               "zip_integrity","full_application_layout","native_syntax",
               "version_bin_vr-control","version_bin_vr-control-gui",
               "version_bin_vr-stack-tray"}
GUEST_LIFECYCLE={"fresh_install","exact_install_hashes","reinstall",
                 "reinstalled_hashes","configuration_preserved","uninstall",
                 "uninstall_removes_app_files","uninstall_preserves_unrelated_data"}

class Blocked(Exception):
    pass

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):
            h.update(b)
    return h.hexdigest()

def must(cond,msg):
    if not cond: raise Blocked(msg)

def verify_stage(doc,ids,overall,scope):
    must(isinstance(doc,dict) and doc.get("release_approved") is False,scope+" unsafe approval")
    must(doc.get("overall",doc.get("result"))==overall,scope+" incomplete outcome")
    checks=doc.get("checks")
    must(isinstance(checks,dict) and set(checks)==ids,scope+" incomplete check registry")
    for key in sorted(ids):
        item=checks[key]
        must(isinstance(item,dict) and item.get("status")=="PASS",
             scope+" check "+key+" not PASS")
    return len(ids)

def evaluate(candidate,ubuntu,guest,guest_lifecycle,source_sha,run_id):
    must(bool(re.fullmatch("[a-f0-9]{40}",source_sha)),"invalid exact GitHub commit")
    must(str(run_id).isdigit() and int(run_id)>0,"invalid GitHub run")
    must(candidate.is_file() and not candidate.is_symlink()
         and sha(candidate)==EXPECTED,"wrong candidate ZIP bytes")
    docs=[]
    for path in (ubuntu,guest,guest_lifecycle):
        must(path.is_file() and not path.is_symlink(),"required original evidence missing")
        docs.append(json.loads(path.read_text()))
    u,g,l=docs
    for idx,doc in enumerate(docs):
        must(doc.get("candidate_sha256")==EXPECTED,
             "check evidence candidate SHA mismatch: "+str(idx))
    n1=verify_stage(u,UBUNTU,"PASS_LIMITED","ubuntu-disposable")
    n2=verify_stage(g,GUEST_PACKAGE,"PARTIAL","real-cachyos-liveiso-package")
    n3=verify_stage(l,GUEST_LIFECYCLE,"PASS_LIMITED","real-cachyos-liveiso-lifecycle")
    must(g.get("schema")=="devnet-native-cachyos-v0685-package-v1",
         "not the correct native guest")
    must(l.get("schema")=="devnet-v0685-native-cachyos-lifecycle-v1",
         "not the correct native lifecycle")
    must(u.get("schema")=="devnet-v0685-disposable-ubuntu-lifecycle-v1",
         "not the correct Ubuntu lifecycle")
    must(g.get("installed_cachyos_system")=="NOT_TESTED"
         and l.get("installed_cachyos_vm")=="NOT_TESTED"
         and u.get("real_gui")=="NOT_TESTED",
         "missing explicit untested limits")
    return {"schema":"devnet-v0685-github-scope-receipt-v1",
            "github_sha":source_sha,"github_run_id":str(run_id),
            "candidate_sha256":EXPECTED,
            "original_candidate":"vr-stack-control-v0.6.85.zip",
            "candidate_type":"original-full-app-historical-baseline",
            "ubuntu_disposable_install_pass":n1,
            "real_cachyos_liveiso_package_pass":n2,
            "real_cachyos_liveiso_lifecycle_pass":n3,
            "source_evidence_sha256":{str(i):sha(p) for i,p in enumerate(
                (ubuntu,guest,guest_lifecycle))},
            "decision":"PASS_LIMITED",
            "installed_cachyos_kde_gui":"NOT_TESTED",
            "tray_pointer_and_visibility":"NOT_TESTED",
            "upgrade_rollback_revision":"NOT_TESTED",
            "physical_vr_host":"NOT_TESTED",
            "full_master_qa":"BLOCKED",
            "release_approved":False}

if __name__=="__main__":
    if len(sys.argv)!=6:
        raise SystemExit("usage: v0685_stage_gate.py candidate.zip ubuntu.json guest.json guest_lifecycle.json output.json")
    try:
        paths=list(map(Path,sys.argv[1:]))
        receipt=evaluate(*paths[:4],os.environ["GITHUB_SHA"],os.environ["GITHUB_RUN_ID"])
        must(not paths[4].exists(),"cannot overwrite previously accepted evidence")
        paths[4].write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
        print("EXACT_GITHUB_AND_LIVE_CACHYOS_STAGE: PASS_LIMITED; MASTER_QA: BLOCKED")
    except (OSError,KeyError,ValueError,TypeError,Blocked,json.JSONDecodeError) as ex:
        print("EVIDENCE_BLOCKED:",repr(ex),file=sys.stderr)
        raise SystemExit(2)
