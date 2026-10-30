#!/usr/bin/env python3
"""Static checks for the exact archived application ZIP; never execute ZIP code.

GitHub first-stage only. These checks do not certify install, GUI, tray or rollback.
"""
import argparse
import pathlib
import stat
import subprocess
import sys
import tempfile
import zipfile

MAX_ARCHIVE_BYTES = 50_000_000
MAX_UNPACKED_BYTES = 150_000_000
MAX_MEMBER_COUNT = 2000

def inspect(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("missing candidate or unsafe symlink")
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("candidate too large")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if not members or len(members) > MAX_MEMBER_COUNT:
            raise ValueError("invalid member count")
        names = set()
        total = 0
        for item in members:
            name = item.filename
            parts = pathlib.PurePosixPath(name)
            if (not name or name.startswith("/") or "\\" in name or
                any(part in (".", "..") for part in name.split("/")) or
                str(parts) != name.rstrip("/") or name in names or
                "\x00" in name):
                raise ValueError("unsafe archive path or duplicate")
            names.add(name)
            kind = stat.S_IFMT(item.external_attr >> 16)
            if kind not in (0, stat.S_IFDIR, stat.S_IFREG):
                raise ValueError("links and special files prohibited")
            total += item.file_size
            if total > MAX_UNPACKED_BYTES:
                raise ValueError("unpacked size limit exceeded")
        if archive.testzip() is not None:
            raise ValueError("ZIP member CRC error")
        return members

def run(mode, path):
    members = inspect(path)
    if mode in ("integrity", "safety"):
        print(mode.upper(), "PASS", "members", len(members))
        return
    syntax = 0
    with zipfile.ZipFile(path) as z:
        for m in members:
            if m.is_dir():
                continue
            data = z.read(m)
            if m.filename.endswith(".py"):
                compile(data, m.filename, "exec")
                syntax += 1
            elif m.filename.endswith((".sh", ".bash")):
                # bash -n parses from standard input without executing application code.
                result = subprocess.run(["/usr/bin/bash", "-n"], input=data,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, timeout=10)
                if result.returncode:
                    raise ValueError("shell syntax error: " + m.filename)
                syntax += 1
    if not syntax:
        raise ValueError("candidate has no supported source files for syntax checks")
    print("STATIC_SYNTAX_PASS", syntax)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["integrity", "safety", "python_syntax"])
    parser.add_argument("candidate", type=pathlib.Path)
    args = parser.parse_args()
    try:
        run(args.mode, args.candidate)
    except (ValueError, OSError, RuntimeError, SyntaxError,
            zipfile.BadZipFile, subprocess.TimeoutExpired) as ex:
        print("QA BLOCKED:", ex, file=sys.stderr)
        raise SystemExit(2)
