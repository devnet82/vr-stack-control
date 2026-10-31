#!/usr/bin/env python3
"""Real v0.6.85 install/reinstall/uninstall in a disposable native CachyOS guest.

Runs untrusted application installer only via unprivileged 'nobody' user in a
temporary HOME; the guest itself is disposable, without network or host mounts.
NOT a real installed-CachyOS/KDE GUI/VR/host/release-acceptance test.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

SHA="db9af6ff47f3abcf07cf452ddd91e91cbd75a10296c0c6050bb5c612980d9cf3"
EXES={"vr-control":"bin/vr-control","vr-control-gui":"bin/vr-control-gui",
      "vr-doctor":"bin/vr-doctor","vr-stackd":"bin/vr-stackd",
      "vr-stack-tray":"bin/vr-stack-tray"}

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main(candidate, result_path, log_path):
    results={"schema":"devnet-v0685-native-cachyos-lifecycle-v1",
             "candidate_sha256":digest(candidate),
             "checks":{}, "release_approved":False,
             "installed_cachyos_vm":"NOT_TESTED", "kde_gui":"NOT_TESTED",
             "tray_visibility":"NOT_TESTED",
             "transactional_upgrade":"NOT_TESTED",
             "transactional_rollback":"NOT_TESTED",
             "physical_hardware":"NOT_TESTED"}
    log=[]
    def record(check, status, detail):
        results["checks"][check]={"status":status,"detail":str(detail)[:400]}
        log.append(f"{check} {status}: {detail}")
    def verify(check, action):
        try:
            detail=action()
            record(check,"PASS",detail)
            return True
        except Exception as ex:
            record(check,"FAIL",repr(ex))
            return False
    try:
        if not any(x.strip()=="ID=cachyos" for x in Path("/etc/os-release").read_text().splitlines()):
            raise RuntimeError("not a CachyOS guest")
        if os.geteuid()!=0:
            raise RuntimeError("guest setup must run as root; app runs as nobody")
        p=subprocess.run(["lsblk","-dn","-o","SERIAL","/dev/vda"],
                         capture_output=True,text=True,timeout=10)
        if p.returncode or p.stdout.strip()!="DEVNETCONTROL":
            raise RuntimeError("wrong VM evidence disk; stop")
        if results["candidate_sha256"]!=SHA:
            raise RuntimeError("original application ZIP hash mismatch")
        nobody=pwd.getpwnam("nobody")
        with tempfile.TemporaryDirectory(prefix="devnet-fullapp-guest-",dir="/var/tmp") as d:
            root=Path(d)
            home=root/"home"
            src=root/"source"
            home.mkdir()
            src.mkdir()
            with zipfile.ZipFile(candidate) as z:
                infos=z.infolist()
                for item in infos:
                    name=item.filename
                    path=PurePosixPath(name)
                    kind=stat.S_IFMT(item.external_attr >> 16)
                    if (not name or path.is_absolute() or
                        ".." in path.parts or "\\" in name or
                        kind not in (0,stat.S_IFDIR,stat.S_IFREG)):
                        raise RuntimeError("unsafe archive item")
                if z.testzip() is not None:
                    raise RuntimeError("bad ZIP CRC")
                z.extractall(src)
            app_dirs=list(src.glob("*/install.sh"))
            if len(app_dirs)!=1:
                raise RuntimeError("full app installer missing/ambiguous")
            app=app_dirs[0].parent
            for folder,dirs,files in os.walk(root):
                os.chown(folder,nobody.pw_uid,nobody.pw_gid)
                for entry in dirs+files:
                    path=Path(folder)/entry
                    if not path.is_symlink():
                        os.chown(path,nobody.pw_uid,nobody.pw_gid)
            config=home/".config"/"vr-stack"/"stack.conf"
            config.parent.mkdir(parents=True)
            # The parent .config was created AFTER the earlier ownership
            # walk. Leaving it root-owned would incorrectly block a genuine
            # unprivileged installer from creating ~/.config/systemd/user.
            os.chown(config.parent.parent,nobody.pw_uid,nobody.pw_gid)
            os.chown(config.parent,nobody.pw_uid,nobody.pw_gid)
            if config.parent.parent.stat().st_uid != nobody.pw_uid:
                raise RuntimeError("QA fixture config HOME ownership incorrect")
            config.write_text("ORIGINAL_GUEST_CONFIG=preserve\n")
            os.chown(config,nobody.pw_uid,nobody.pw_gid)
            unrelated=home/"KEEP_UNRELATED"
            unrelated.write_text("keep")
            os.chown(unrelated,nobody.pw_uid,nobody.pw_gid)
            env={"HOME":str(home),"PATH":"/usr/bin:/bin",
                 "XDG_CONFIG_HOME":str(home/".config"),
                 "XDG_DATA_HOME":str(home/".local/share"),
                 "LANG":"C.UTF-8"}
            def command(script):
                cmd=["/usr/bin/runuser","-u","nobody","--","/usr/bin/env","-i",
                     *[f"{k}={v}" for k,v in env.items()],
                     "/usr/bin/bash",str(app/script)]
                p=subprocess.run(cmd,cwd=app,capture_output=True,
                                 text=True,timeout=60,check=False)
                log.append("EXECUTED "+script+" exit="+str(p.returncode))
                log.append((p.stdout+"\n"+p.stderr)[-5000:])
                if p.returncode:
                    raise RuntimeError(script+" exit "+str(p.returncode))
                return "actual unprivileged installer exit 0"
            def hashes():
                for name,original in EXES.items():
                    target=home/".local/bin"/name
                    if not target.is_file() or digest(target)!=digest(app/original):
                        raise RuntimeError("incorrect installed artifact: "+name)
                return str(len(EXES))+" installed executable hashes match ZIP"
            def preserved():
                if config.read_text()!="ORIGINAL_GUEST_CONFIG=preserve\n":
                    raise RuntimeError("pre-existing config changed")
                if unrelated.read_text()!="keep":
                    raise RuntimeError("unrelated HOME data changed")
                return "config and unrelated user file retained"
            def removed():
                leftovers=[name for name in EXES if (home/".local/bin"/name).exists()]
                if leftovers:
                    raise RuntimeError("installer left files: "+repr(leftovers))
                return "all registered app executables removed"
            if verify("fresh_install",lambda:command("install.sh")):
                verify("exact_install_hashes",hashes)
                if verify("reinstall",lambda:command("install.sh")):
                    verify("reinstalled_hashes",hashes)
                verify("configuration_preserved",preserved)
                if verify("uninstall",lambda:command("uninstall.sh")):
                    verify("uninstall_removes_app_files",removed)
                    verify("uninstall_preserves_unrelated_data",preserved)
    except Exception as ex:
        record("harness","FAIL",repr(ex))
    finally:
        statuses=[x["status"] for x in results["checks"].values()]
        results["overall"]="FAIL" if not statuses or "FAIL" in statuses else "PASS_LIMITED"
        result_path.write_text(json.dumps(results,indent=2,sort_keys=True)+"\n")
        log_path.write_text("\n".join(log)+"\n")
    return 2 if results["overall"]=="FAIL" else 0

if __name__=="__main__":
    if len(sys.argv)!=4:
        raise SystemExit("usage: guest_v0685_lifecycle.py candidate.zip result.json log.txt")
    sys.exit(main(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3])))
