#!/usr/bin/env python3
"""Exact unchanged v0.6.85 full-application archive checks INSIDE a real CachyOS guest.

NO artificial VERSION file. Original v0.6.85 release encodes version in its
GUI, control CLI and tray source. This stage verifies actual native guest,
identity of disposable disk, original ZIP hash, CRC, paths, script syntax, and
original version markers. It never grants installed-GUI/host/release approval.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

EXPECTED="db9af6ff47f3abcf07cf452ddd91e91cbd75a10296c0c6050bb5c612980d9cf3"
PREFIX="vr-stack-control-v0.6.85/"
REQUIRED={"install.sh","uninstall.sh","bin/vr-control","bin/vr-control-gui",
          "bin/vr-stack-tray","bin/vr-stackd","bin/vr-doctor"}
VERSION_FILES={"bin/vr-control","bin/vr-control-gui","bin/vr-stack-tray"}

def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as s:
        for b in iter(lambda:s.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def analyze(candidate):
    report={"schema":"devnet-native-cachyos-v0685-package-v1",
            "candidate_sha256":sha(candidate),
            "checks":{}, "release_approved":False,
            "installed_cachyos_system":"NOT_TESTED",
            "kde_gui":"NOT_TESTED","tray_visibility":"NOT_TESTED",
            "transactional_upgrade":"NOT_TESTED",
            "transactional_rollback":"NOT_TESTED","host_hardware":"NOT_TESTED"}
    def check(name, ok, detail):
        report["checks"][name]={"status":"PASS" if ok else "FAIL",
                                "detail":str(detail)[:400]}
        if not ok:
            raise ValueError(name+": "+str(detail))
    try:
        osrel=Path("/etc/os-release").read_text()
        check("native_cachyos",any(x.strip()=="ID=cachyos" for x in osrel.splitlines()),
              "real CachyOS /etc/os-release")
        blk=subprocess.run(["/usr/bin/lsblk","-dn","-o","SERIAL","/dev/vda"],
                           capture_output=True,text=True,timeout=10)
        check("control_disk_identity",blk.returncode==0 and
              blk.stdout.strip()=="DEVNETCONTROL",
              "pinned disposable virtio control disk")
        check("exact_sha256",report["candidate_sha256"]==EXPECTED,
              report["candidate_sha256"])
        with zipfile.ZipFile(candidate) as z:
            infos=z.infolist()
            names=set()
            total=0
            for entry in infos:
                name=entry.filename
                parts=PurePosixPath(name)
                mode=stat.S_IFMT(entry.external_attr >> 16)
                if (not name or name in names or not name.startswith(PREFIX) or
                    "\\" in name or parts.is_absolute() or
                    ".." in parts.parts or
                    mode not in (0,stat.S_IFDIR,stat.S_IFREG)):
                    raise ValueError("unsafe/duplicated archive member")
                names.add(name)
                total+=entry.file_size
                if total>150_000_000 or len(names)>2000:
                    raise ValueError("ZIP limits exceeded")
            check("zip_integrity",z.testzip() is None,"real CRC of every ZIP member")
            check("full_application_layout",
                  REQUIRED.issubset({n[len(PREFIX):] for n in names}),
                  "required app executables and installer present")
            count=0
            for member in infos:
                if member.is_dir():
                    continue
                data=z.read(member)
                head=data.split(b"\n",1)[0]
                if head.startswith(b"#!/usr/bin/env python3") or member.filename.endswith(".py"):
                    compile(data,member.filename,"exec")
                    count+=1
                elif b"bash" in head and head.startswith(b"#!"):
                    p=subprocess.run(["/usr/bin/bash","-n"],input=data,
                                     capture_output=True,timeout=12)
                    if p.returncode:
                        raise ValueError("invalid Bash syntax "+member.filename)
                    count+=1
            check("native_syntax",count>=7,
                  str(count)+" actual Python/Bash source files parsed")
            for item in VERSION_FILES:
                data=z.read(PREFIX+item)
                check("version_"+item.replace("/","_"),
                      b"v0.6.85" in data,
                      "original v0.6.85 application source marker")
    except Exception as ex:
        report["harness_error"]=repr(ex)[:500]
    statuses=[x["status"] for x in report["checks"].values()]
    report["overall"]="PARTIAL" if statuses and all(x=="PASS" for x in statuses) else "FAIL"
    return report

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("usage: guest_v0685_package.py /mnt/candidate.zip /mnt/qa-result.json")
    try:
        result=analyze(Path(sys.argv[1]))
        Path(sys.argv[2]).write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        print(json.dumps({"overall":result["overall"],"checks":result["checks"]},sort_keys=True))
        raise SystemExit(0 if result["overall"]=="PARTIAL" else 2)
    except (OSError,ValueError,zipfile.BadZipFile) as ex:
        print("CACHYOS_GUEST_BLOCKED",repr(ex),file=sys.stderr)
        raise SystemExit(2)
