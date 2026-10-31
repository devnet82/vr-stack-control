#!/usr/bin/env python3
"""Additive Devnet Master QA real CLI contract check; unsigned, never approves release."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

SCHEMA="devnet-runner-dependency-reality-v1"
VERSION=re.compile(r"\A(?:opencode[ \t]+)?v?2\.(\d+)\.(\d+)(?:[-+][a-zA-Z0-9.-]+)?\Z",re.I)

def parse_opencode(raw):
    m=VERSION.fullmatch(raw.strip())
    if not m:
        raise ValueError("unsupported OpenCode v2 output")
    return "2."+m.group(1)+"."+m.group(2)

def digest(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as fp:
        for chunk in iter(lambda:fp.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def live_target():
    exe=shutil.which("opencode")
    if not exe:
        raise RuntimeError("BLOCKED: real OpenCode missing")
    exe=Path(exe).resolve(strict=True)
    if not exe.is_file():
        raise RuntimeError("BLOCKED: OpenCode executable unavailable")
    cp=subprocess.run([str(exe),"--version"],stdin=subprocess.DEVNULL,
                      capture_output=True,text=True,timeout=20,check=False)
    if cp.returncode:
        raise RuntimeError("BLOCKED: OpenCode --version exit "+str(cp.returncode))
    return exe,cp,parse_opencode(cp.stdout)

def identity(p):
    p=Path(p).resolve(strict=True)
    if not p.is_file():
        raise RuntimeError("BLOCKED: runner/candidate not a file")
    return digest(p)

def capture(runner,candidate,job,revision):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",job) or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}",revision):
        raise ValueError("invalid job/revision identity")
    exe,cp,version=live_target()
    return dict(schema=SCHEMA,kind="LIVE_EXECUTION",argv=[str(exe),"--version"],
                binary_sha256=digest(exe),runner_sha256=identity(runner),
                candidate_sha256=identity(candidate),job_id=job,revision=revision,
                stdout=cp.stdout,stderr=cp.stderr,exit_code=cp.returncode,
                parsed_version=version,timestamp=datetime.now(timezone.utc).isoformat(),
                release_approved=False,scope="CLI_ONLY")

def verify(r,runner,candidate,job,revision):
    mandatory={"schema","kind","argv","binary_sha256","runner_sha256","candidate_sha256",
               "job_id","revision","stdout","stderr","exit_code","parsed_version",
               "timestamp","release_approved","scope"}
    if not isinstance(r,dict) or set(r)!=mandatory:
        raise ValueError("incomplete evidence")
    if r["schema"]!=SCHEMA or r["kind"]!="LIVE_EXECUTION" or r["scope"]!="CLI_ONLY" or r["release_approved"] is not False or r["exit_code"]!=0:
        raise ValueError("untrusted evidence or approval")
    when=datetime.fromisoformat(r["timestamp"])
    if when.tzinfo is None or not timedelta(seconds=-30)<=datetime.now(timezone.utc)-when<=timedelta(minutes=15):
        raise ValueError("stale/future evidence")
    if (r["runner_sha256"]!=identity(runner) or r["candidate_sha256"]!=identity(candidate)
            or r["job_id"]!=job or r["revision"]!=revision):
        raise ValueError("different candidate or runner revision")
    exe,cp,version=live_target()
    if r["argv"]!=[str(exe),"--version"] or r["binary_sha256"]!=digest(exe) or r["parsed_version"]!=version:
        raise ValueError("executable/version mismatch")
    if r["stdout"]!=cp.stdout or parse_opencode(r["stdout"])!=version:
        raise ValueError("captured stdout does not match re-executed native CLI")
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("mode",choices=["capture","verify"])
    ap.add_argument("evidence",type=Path)
    ap.add_argument("--runner",type=Path,required=True)
    ap.add_argument("--candidate",type=Path,required=True)
    ap.add_argument("--job",required=True)
    ap.add_argument("--revision",required=True)
    a=ap.parse_args()
    try:
        if a.mode=="capture":
            if a.evidence.exists():
                raise ValueError("existing evidence cannot be reused")
            r=capture(a.runner,a.candidate,a.job,a.revision)
            a.evidence.parent.mkdir(parents=True,exist_ok=True)
            with a.evidence.open("x") as out:
                json.dump(r,out,indent=2,sort_keys=True)
                out.write("\n")
            a.evidence.chmod(0o600)
        else:
            verify(json.loads(a.evidence.read_text()),a.runner,a.candidate,a.job,a.revision)
        print("PASS_LIMITED: REAL_CLI; MASTER QA/RELEASE STILL BLOCKED")
        return 0
    except (OSError,RuntimeError,ValueError,KeyError,TypeError,IndexError,
            subprocess.TimeoutExpired,json.JSONDecodeError) as e:
        print("BLOCKED:",e,file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
