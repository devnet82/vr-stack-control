#!/usr/bin/env python3
"""Fail-closed candidate registration and GitHub-stage evidence collector.
Never claims VM, GUI, tray, host or release acceptance.
"""
import argparse, hashlib, json, os, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
JOBS = ROOT / "qa/application/jobs"
OUT = ROOT / "qa-stage-evidence"
VALID = {"github", "vm", "host"}
REQUIRED = {"install", "upgrade", "rollback", "gui", "tray", "recovery", "security"}

def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()

def fail(s):
    raise ValueError(s)

def register(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {"job_id", "candidate", "sha256", "checks"}:
        fail("invalid registration keys")
    job = manifest["job_id"]
    if not isinstance(job, str) or not job or not all(c.isalnum() or c in "-_" for c in job):
        fail("invalid job id")
    candidate = JOBS / job / "candidate.zip"
    if manifest["candidate"] != f"qa/application/jobs/{job}/candidate.zip":
        fail("candidate must use registered immutable path")
    if not candidate.is_file() or digest(candidate) != manifest["sha256"]:
        fail("missing candidate or SHA256 mismatch")
    checks = manifest["checks"]
    if not isinstance(checks, list) or not checks:
        fail("empty checklist")
    ids = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"id", "stage", "argv"}:
            fail("invalid check schema")
        cid, stage, argv = check["id"], check["stage"], check["argv"]
        if not isinstance(cid, str) or not cid or not all(z.isalnum() or z in "-_" for z in cid) or cid in ids:
            fail("duplicate/empty check ID")
        ids.add(cid)
        if stage not in VALID or not isinstance(argv, list):
            fail("invalid stage/argv")
        if stage == "github":
            if not argv or not all(isinstance(x,str) and x for x in argv):
                fail("invalid GitHub executable")
            if pathlib.PurePath(argv[0]).is_absolute() or ".." in pathlib.PurePath(argv[0]).parts:
                fail("unsafe command path")
        elif argv:
            fail("VM/host checks must be performed by trusted downstream executor")
    if not any(x["stage"]=="github" for x in checks):
        fail("no GitHub-stage test registered")
    if not REQUIRED.issubset(ids):
        fail("mandatory lifecycle checklist incomplete")
    return job, candidate, checks

def run_one(job, check):
    # Exact command argv, no shell interpolation, no inherited secrets.
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": os.environ.get("RUNNER_TEMP", "/tmp"),
           "LANG": "C.UTF-8"}
    work = JOBS / job
    start = time.monotonic()
    try:
        cp = subprocess.run(check["argv"], cwd=work, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=180, check=False)
        return {"id":check["id"], "status":"PASS" if cp.returncode==0 else "FAIL",
                "exit_code":cp.returncode, "duration_ms":int((time.monotonic()-start)*1000),
                "output_sha256":hashlib.sha256(cp.stdout).hexdigest(),
                "output":cp.stdout.decode("utf-8","replace")[-20000:]}
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {"id":check["id"],"status":"BLOCKED","error":type(exc).__name__}

def run(manifest_path):
    m=json.loads(manifest_path.read_text())
    job,candidate,checks=register(m)
    if OUT.exists():
        fail("evidence directory already exists; no stale reuse")
    results=[run_one(job,c) if c["stage"]=="github" else
             {"id":c["id"],"status":"NOT_TESTED","stage":c["stage"]}
             for c in checks]
    receipt={"schema":1,"job_id":job,"candidate_sha256":digest(candidate),
             "manifest_sha256":digest(manifest_path),"github_sha":os.environ.get("GITHUB_SHA"),
             "checks":results,"full_acceptance":False,"release_approved":False}
    p=OUT/job
    p.mkdir(parents=True,exist_ok=False)
    (p/"receipt.json").write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    if any(x["status"]!="PASS" for x in results if x.get("stage","github")=="github"):
        fail("GitHub-stage check failure")
    print("GITHUB_STAGE: PASS; VM/HOST/RELEASE: NOT APPROVED")

def verify(manifest_path):
    m=json.loads(manifest_path.read_text())
    job,candidate,checks=register(m)
    p=OUT/job/"receipt.json"
    d=json.loads(p.read_text())
    if set(d)!={"schema","job_id","candidate_sha256","manifest_sha256","github_sha","checks","full_acceptance","release_approved"} or d["schema"]!=1 or d["job_id"]!=job:
        fail("invalid receipt schema/job")
    if d["github_sha"]!=os.environ.get("GITHUB_SHA") or not isinstance(d["github_sha"],str) or len(d["github_sha"])!=40:
        fail("wrong/missing GitHub commit identity")
    if d["candidate_sha256"]!=digest(candidate) or d["manifest_sha256"]!=digest(manifest_path):
        fail("receipt provenance mismatch")
    if d["full_acceptance"] is not False or d["release_approved"] is not False:
        fail("untrusted approval")
    if [x["id"] for x in d["checks"]] != [x["id"] for x in checks]:
        fail("incomplete checklist")
    for result,check in zip(d["checks"],checks):
        if check["stage"]=="github":
            if result["status"]!="PASS" or result.get("exit_code")!=0 or not isinstance(result.get("output_sha256"),str):
                fail("GitHub check not passed")
            # Do not confuse a captured log excerpt with complete output evidence.
            if "output" not in result or not isinstance(result["output"],str):
                fail("missing GitHub output excerpt")
        if check["stage"]!="github" and result["status"]!="NOT_TESTED":
            fail("VM/host acceptance cannot be certified here")
    print("GITHUB_RECEIPT: SCOPE_LIMITED_VERIFIED")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("mode",choices=["run","verify"])
    ap.add_argument("manifest",type=pathlib.Path)
    args=ap.parse_args()
    try:
        (run if args.mode=="run" else verify)(args.manifest)
    except (ValueError,KeyError,OSError,json.JSONDecodeError) as exc:
        print("QA BLOCKED:",exc,file=sys.stderr)
        sys.exit(1)
