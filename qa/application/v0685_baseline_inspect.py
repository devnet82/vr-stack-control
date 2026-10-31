#!/usr/bin/env python3
"""Read-only inventory of the ORIGINAL published full-application release ZIP.

All findings are about package bytes, NOT install, GUI, rollback or release QA.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

APP_FILES = {"install.sh", "uninstall.sh", "bin/vr-control",
             "bin/vr-control-gui", "bin/vr-stack-tray", "bin/vr-stackd"}

def inspect(path: Path):
    with zipfile.ZipFile(path) as z:
        names = [i.filename for i in z.infolist() if not i.is_dir()]
        leading = {name.split("/", 1)[0] for name in names if "/" in name}
        prefix = (next(iter(leading)) + "/") if len(leading) == 1 and all(
            name.startswith(next(iter(leading)) + "/") for name in names) else ""
        normalized = [n[len(prefix):] if prefix else n for n in names]
        missing = sorted(APP_FILES - set(normalized))
        if missing:
            raise ValueError("Not a verified full-app package; required files absent: " + repr(missing))
        scripts = sorted(x for x in normalized if x.startswith("tests/"))
        result = {"schema":"devnet-original-zip-inventory-v1",
                  "zip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "entries":len(names),"root_prefix":prefix,
                  "required_app_files":sorted(APP_FILES),
                  "packaged_test_paths":scripts,
                  "packaged_test_count":len(scripts),
                  "full_app_layout":"PASS",
                  "real_installed_system":"NOT_TESTED",
                  "gui":"NOT_TESTED","tray":"NOT_TESTED",
                  "upgrade":"NOT_TESTED","rollback":"NOT_TESTED",
                  "release_approved":False}
        return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("candidate",type=Path)
    p.add_argument("receipt",type=Path)
    a = p.parse_args()
    result = inspect(a.candidate)
    a.receipt.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("FULL_APP_LAYOUT: PASS; INSTALLED_SYSTEM: NOT_TESTED; RELEASE: BLOCKED")

if __name__ == "__main__":
    main()
