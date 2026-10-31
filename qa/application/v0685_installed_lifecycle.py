#!/usr/bin/env python3
"""Execute original VR Stack Control v0.6.85 installer in disposable CI HOME.

This is an Ubuntu GitHub runner smoke/lifecycle stage only, NEVER a CachyOS
installed-VM, GUI, tray, hardware, rollback or user acceptance certification.
No sudo, no release writes, no modification to host user's actual HOME.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main(candidate, evidence):
    evidence.mkdir(parents=True, exist_ok=True)
    report = {"schema":"devnet-v0685-disposable-ubuntu-lifecycle-v1",
              "candidate_sha256": sha(candidate),
              "checks":{}, "release_approved":False,
              "installed_cachyos_vm":"NOT_TESTED",
              "real_gui":"NOT_TESTED",
              "real_tray":"NOT_TESTED",
              "upgrade_to_new_revision":"NOT_TESTED",
              "transactional_rollback":"NOT_TESTED"}
    with tempfile.TemporaryDirectory(prefix="devnet-v0685-", dir="/tmp") as tmp:
        root=Path(tmp)
        home=root/"home"
        home.mkdir(mode=0o700)
        src=root/"source"
        src.mkdir()
        with zipfile.ZipFile(candidate) as z:
            z.extractall(src)
        packages=list(src.glob("*/install.sh"))
        if len(packages)!=1:
            raise ValueError("exactly one full-app install.sh required")
        app=packages[0].parent
        sentinel=home/"outside-app-preserve.txt"
        sentinel.write_text("DO_NOT_TOUCH")
        config=home/".config/vr-stack/stack.conf"
        config.parent.mkdir(parents=True)
        config.write_text("DEVNET_PRESERVE_SENTINEL=yes\n")
        env={**os.environ,
             "HOME":str(home),
             "XDG_CONFIG_HOME":str(home/".config"),
             "XDG_DATA_HOME":str(home/".local/share"),
             "XDG_RUNTIME_DIR":str(root/"runtime"),
             "PATH":os.environ.get("PATH","/usr/bin:/bin")}
        (root/"runtime").mkdir(mode=0o700)
        expected={
            "vr-control":"bin/vr-control",
            "vr-control-gui":"bin/vr-control-gui",
            "vr-doctor":"bin/vr-doctor",
            "vr-stackd":"bin/vr-stackd",
            "vr-stack-tray":"bin/vr-stack-tray"}
        def test(id, callback):
            try:
                detail=callback()
                report["checks"][id]={"status":"PASS","detail":str(detail)[:300]}
                print(id,"PASS",flush=True)
            except Exception as e:
                report["checks"][id]={"status":"FAIL","detail":repr(e)[:350]}
                print(id,"FAIL",str(e),flush=True)
                raise
        def command(name):
            p=subprocess.run(["/usr/bin/bash",name],
                             cwd=app,env=env,stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                             text=True,timeout=45,check=False)
            (evidence/(name+".log")).write_text(p.stdout)
            if p.returncode:
                raise RuntimeError(f"{name} returned {p.returncode}; review log artifact")
            return f"{name} returned 0"
        def installed():
            for name,original in expected.items():
                observed=home/".local/bin"/name
                if not observed.is_file():
                    raise ValueError("missing installed "+name)
                if sha(observed)!=sha(app/original):
                    raise ValueError("installed file does not match ZIP "+name)
            return f"{len(expected)} exact installed executable hashes verified"
        try:
            test("fresh_install",lambda:command("install.sh"))
            test("exact_install_hashes",installed)
            test("reinstall",lambda:command("install.sh"))
            test("reinstalled_file_hashes",installed)
            def config_preserved():
                if config.read_text()!="DEVNET_PRESERVE_SENTINEL=yes\n":
                    raise ValueError("pre-existing user configuration changed")
                return "original config bytes unchanged"
            test("preserve_existing_config",config_preserved)
            test("uninstall",lambda:command("uninstall.sh"))
            def uninstalled():
                present=[name for name in expected if (home/".local/bin"/name).exists()]
                if present:
                    raise ValueError("installed app files remain after uninstall: "+str(present))
                return "app executables removed"
            test("uninstall_removes_app_files",uninstalled)
            test("uninstall_preserves_user_config",config_preserved)
            def outside_preserved():
                if sentinel.read_text()!="DO_NOT_TOUCH":
                    raise ValueError("unrelated user data changed")
                return "unrelated data unchanged"
            test("outside_user_data_preserved",outside_preserved)
        except Exception:
            report["result"]="FAIL"
        else:
            report["result"]="PASS_LIMITED"
        finally:
            (evidence/"lifecycle-receipt.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return 0 if report["result"]=="PASS_LIMITED" else 2

if __name__=="__main__":
    if len(sys.argv)!=3:
        raise SystemExit("usage: v0685_installed_lifecycle.py CANDIDATE_ZIP EVIDENCE_DIR")
    sys.exit(main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve()))
