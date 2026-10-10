#!/usr/bin/env python3
"""Devnet guest-side CachyOS repair application QA, v0.1.11.

Designed to run ONLY inside a disposable CachyOS live VM. No real host writes.
Run after /dev/vda (the isolated DEVNETQA FAT image) is mounted at /mnt.
Never claims a GUI pass from an offscreen widget run or a booted live ISO.
"""
from __future__ import annotations
import hashlib, json, os, re, shutil, stat, subprocess, sys, tempfile, zipfile
from pathlib import Path, PurePosixPath

VERSION = "0.1.11"
APP_VERSION = "0.1.19"
APP_SHA256 = "435bc2a88a99eef4cd5e85d71d50ca36e3d3f40361efe53db85e57e2d20fea0c"
ROOT = Path("/mnt")
PASS = "PASS"
FAIL = "FAIL"
NOT_TESTED = "NOT_TESTED"


def run(args, *, timeout=90, cwd=None, env=None):
    try:
        r = subprocess.run(args, stdin=subprocess.DEVNULL, cwd=cwd, env=env,
                           text=True, errors="replace", stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return r.returncode, r.stdout[-30000:]
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, OSError) as exc:
        return 124 if isinstance(exc, subprocess.TimeoutExpired) else 127, str(exc)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_zip(path, expected):
    if not path.is_file():
        raise FileNotFoundError(f"candidate archive absent: {path.name}")
    if sha256(path) != expected:
        raise ValueError(f"candidate SHA-256 mismatch for {path.name}")
    with zipfile.ZipFile(path) as zf:
        seen = set()
        total = 0
        for info in zf.infolist():
            p = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            if (not info.filename or info.filename.startswith("/") or
                "\\" in info.filename or ":" in info.filename or
                ".." in p.parts or stat.S_ISLNK(mode) or
                info.filename in seen):
                raise ValueError("unsafe candidate ZIP entry")
            seen.add(info.filename)
            total += info.file_size
            if total > 800 * 1024 * 1024 or len(seen) > 10000:
                raise ValueError("candidate ZIP extraction safety limit")
        corrupt = zf.testzip()
        if corrupt:
            raise ValueError("candidate ZIP CRC mismatch")
    return len(seen)


def dependency_status(install_rc, import_rc):
    """An interrupted package install is never success, even if Qt imports."""
    return PASS if install_rc == 0 and import_rc == 0 else NOT_TESTED


def classify_desktop(returncode, output):
    if returncode != 0 or re.search(r"(?im)^Traceback |^FAILED\b|^ERROR:|^FAIL:", output):
        return FAIL
    m = re.search(r'(?m)^\s*\{', output)
    if not m:
        return NOT_TESTED
    try:
        obj, _ = json.JSONDecoder().raw_decode(output[m.start():])
    except (ValueError, TypeError):
        return NOT_TESTED
    if not isinstance(obj, dict) or 'pyside6' not in str(obj.get('test_scope', '')).lower():
        return NOT_TESTED
    checks = obj.get('checks_passed')
    if (not isinstance(checks, list) or len(checks) != 33 or
        any(not isinstance(s, str) or not s.strip() for s in checks) or
        len(set(checks)) != 33 or
        any(obj.get(k) for k in ('checks_failed', 'failures', 'errors', 'skipped'))):
        return FAIL
    return PASS


def desktop_session(uid):
    """Return platform + tested session variables from a real KDE compositor, if found."""
    proc = Path('/proc')
    for p in proc.iterdir():
        if not p.name.isdigit():
            continue
        try:
            if p.stat().st_uid != uid:
                continue
            name = (p / 'comm').read_text(errors='replace').strip()
            if name not in ('kwin_wayland', 'kwin_x11'):
                continue
            data = (p / 'environ').read_bytes().split(b'\0')
            e = dict(x.decode(errors='replace').split('=', 1) for x in data if b'=' in x)
            platform = 'wayland' if name == 'kwin_wayland' else 'xcb'
            kwargs = {k: v for k, v in e.items() if k in
                      ('WAYLAND_DISPLAY','DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR',
                       'DBUS_SESSION_BUS_ADDRESS','XDG_SESSION_TYPE')}
            if (platform == 'wayland' and kwargs.get('WAYLAND_DISPLAY')) or (platform == 'xcb' and kwargs.get('DISPLAY')):
                return platform, kwargs
        except (OSError, ValueError):
            continue
    return None, {}


def main():
    report = {'gate_version': VERSION, 'application_version': APP_VERSION,
              'candidate_sha256_expected': APP_SHA256,
              'checks': {}, 'logs': {}, 'limitations': []}
    def check(key, status, evidence):
        report['checks'][key] = {'status': status, 'evidence': evidence[:500]}
    def command_probe(name, args, timeout=20):
        rc, out = run(args, timeout=timeout)
        report['logs'][name] = {'returncode': rc, 'output': out[-6000:]}
        return rc, out
    try:
        osrel = Path('/etc/os-release').read_text(errors='replace')
        rc, kernel = command_probe('uname', ['uname', '-r'])
        rc2, virt = command_probe('virt', ['systemd-detect-virt'])
        correct = ('ID=cachyos' in osrel.lower() or 'PRETTY_NAME="CachyOS"' in osrel)
        check('real_cachyos_guest', PASS if correct and 'cachyos' in kernel.lower() else FAIL,
              f"os-release={osrel[:250]!r}; kernel={kernel.strip()}; virt={virt.strip()}")
        if not correct:
            raise RuntimeError('Refusing app acceptance outside genuine CachyOS')
        for key, argv in {
            'kernel': ['uname','-a'], 'sessions': ['loginctl','list-sessions','--no-legend'],
            'display_managers':['bash','-c','ps -eo uid,comm | grep -E "kwin_wayland|kwin_x11|Xorg|sddm" || true'],
            'bootloader_capabilities':['bash','-c','command -v grub-install || true; command -v pacstrap || true; command -v calamares || true'],
            'package_versions': ['bash','-c','pacman -Q pyside6 grub btrfs-progs plasma-workspace kwin 2>&1 || true'],
            'qt_probe': ['python3','-c','from PySide6.QtWidgets import QApplication;print("GUEST_PYSIDE6_IMPORT_PASS")']
        }.items(): command_probe(key, argv)
        qt_good = report['logs']['qt_probe']['returncode'] == 0
        python_executable = 'python3'
        dependency_rc = 0 if qt_good else 127
        if not qt_good:
            # Isolated Python wheels, with NO guest pacman -Syu / partial system upgrade.
            # The wheels were transferred by the host to a disposable guest FAT disk.
            venv = '/var/tmp/devnet-qa-pyside6-venv'
            rc, out = command_probe('create_guest_qa_venv',
                        ['python3','-m','venv',venv], timeout=45)
            if rc == 0:
                python_executable = venv + '/bin/python'
                dependency_rc, out = command_probe('offline_pyside6_install',
                    [python_executable,'-m','pip','install','--no-index',
                     '--find-links=/mnt/wheels','PySide6'], timeout=240)
                import_rc, _ = run([python_executable,'-c',
                    'from PySide6.QtWidgets import QApplication'],timeout=30)
                qt_good = dependency_status(dependency_rc,import_rc) == PASS
            else:
                report['logs']['offline_pyside6_install'] = {'returncode':127,
                        'output':'Cannot create private guest venv: '+out[-1500:]}
        check('guest_pyside6_dependency', PASS if qt_good else NOT_TESTED,
              'Clean isolated PySide6 import and completed package install' if qt_good
              else 'PySide6 dependency install could not complete; no system pacman upgrade attempted')
        app = ROOT / 'candidate.zip'
        try:
            count = validate_zip(app, APP_SHA256)
            check('exact_application_zip', PASS, f'v{APP_VERSION} SHA-256/CRC/safe members PASS, entries={count}')
        except (FileNotFoundError, ValueError, zipfile.BadZipFile) as exc:
            check('exact_application_zip', FAIL if app.is_file() else NOT_TESTED, str(exc))
            report['limitations'].append('No exact application ZIP in guest. Remaining app scenarios are NOT_TESTED.')
            return finalize(report)
        with tempfile.TemporaryDirectory(prefix='devnet-repair-qa-') as tmp:
            Path(tmp).chmod(0o755)
            with zipfile.ZipFile(app) as zf: zf.extractall(tmp)
            suite = sorted(Path(tmp).rglob('desktop_acceptance.py'))
            qa_sh = sorted(Path(tmp).rglob('qa.sh'))
            # Exercise actual packaged installers in a disposable DESTDIR.
            packaged_root = suite[0].parent.parent
            fixture = packaged_root / 'tests/fixtures/known-good-v0.1.17.zip'
            stage = Path(tmp) / 'isolated-install-root'
            stage.mkdir()
            envstage = dict(os.environ, DESTDIR=str(stage))
            install = packaged_root / 'install.sh'
            rollback = packaged_root / 'rollback.sh'
            uninstall = packaged_root / 'uninstall.sh'
            if not all(f.is_file() for f in (install, rollback, uninstall, fixture)):
                check('guest_staged_install_upgrade_rollback', FAIL,
                      'Missing exact-package installation scripts or 0.1.17 archive')
            else:
                history = Path(tmp) / 'history'
                history.mkdir()
                with zipfile.ZipFile(fixture) as hzf:
                    hzf.extractall(history)
                old_install = next(iter(history.rglob('install.sh')), None)
                cmds = [('install_previous', old_install),
                        ('upgrade_candidate', install),
                        ('rollback_to_previous', rollback),
                        ('upgrade_again', install),
                        ('uninstall_candidate', uninstall)]
                transitions = []
                expected = {'install_previous':'0.1.17',
                            'upgrade_candidate':'0.1.19',
                            'rollback_to_previous':'0.1.17',
                            'upgrade_again':'0.1.19'}
                for label, script in cmds:
                    if script is None:
                        transitions.append((label, 127, 'Historical installer missing'))
                        break
                    rc, out = run(['bash', str(script)], timeout=90,
                                  cwd=str(script.parent), env=envstage)
                    transitions.append((label, rc, out[-1600:]))
                    if label in expected:
                        vf = stage / 'usr/lib/devnet-cachyos-repair/VERSION'
                        actual = vf.read_text().strip() if vf.is_file() else 'MISSING'
                        if actual != expected[label]:
                            transitions.append((label+'_version_assertion', 1,
                                                'expected '+expected[label]+', got '+actual))
                            break
                    if rc:
                        break
                report['logs']['staged_install_upgrade_rollback'] = {
                    'transitions': [{'name':x, 'returncode':r, 'tail':o}
                                    for x, r, o in transitions]}
                good = len(transitions) == 5 and all(rc == 0 for _, rc, _ in transitions)
                check('guest_staged_install_upgrade_rollback', PASS if good else FAIL,
                      'Five real shell-script operations in isolated DESTDIR; see transitions')
                check('guest_staged_uninstall',
                      PASS if good and not (stage/'usr/lib/devnet-cachyos-repair').exists() else FAIL,
                      'Disposable application removed; backups preserved')
            if not suite:
                check('desktop_acceptance_packaged', FAIL, 'No desktop_acceptance.py in verified release ZIP')
                return finalize(report)
            check('desktop_acceptance_packaged', PASS, f'Packaged desktop runner: {suite[0].relative_to(tmp)}')
            users = []
            for path in Path('/home').iterdir():
                if path.is_dir():
                    rc, val = run(['id','-u',path.name])
                    if rc == 0 and val.strip().isdigit() and int(val.strip()) >= 1000:
                        users.append((path.name,int(val.strip())))
            if not users:
                check('guest_nonroot_desktop_user', NOT_TESTED, 'No regular CachyOS live user found')
                return finalize(report)
            username, uid = users[0]
            check('guest_nonroot_desktop_user', PASS, f'Detected non-root live guest user (uid={uid})')
            for p in Path(tmp).rglob('*'):
                try:
                    if p.is_dir(): p.chmod(0o755)
                    elif p.is_file(): p.chmod(0o644)
                except OSError: pass
            # An offscreen run is useful for widget regression but DOES NOT prove KDE.
            env = dict(os.environ)
            env.update({'QT_QPA_PLATFORM':'offscreen', 'PYTHONPATH':str(suite[0].parent.parent),
                        'XDG_RUNTIME_DIR':f'/run/user/{uid}'})
            argv = ['runuser','-u',username,'--','env',*['%s=%s'%(k,v) for k,v in env.items()
                         if k in ('QT_QPA_PLATFORM','PYTHONPATH','XDG_RUNTIME_DIR')],
                    python_executable,str(suite[0])]
            rc,out = run(argv,timeout=180,cwd=str(suite[0].parent.parent))
            report['logs']['offscreen_desktop_acceptance']={'returncode':rc,'output':out[-24000:]}
            check('guest_offscreen_33_widget_checks',classify_desktop(rc,out),
                  'Executed exact packaged PySide6 acceptance in guest via offscreen platform; not KDE acceptance')
            platform, sessionvars = desktop_session(uid)
            if platform:
                env = dict(sessionvars)
                env['QT_QPA_PLATFORM'] = platform
                env['PYTHONPATH'] = str(suite[0].parent.parent)
                env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'
                env['DBUS_SESSION_BUS_ADDRESS'] = f'unix:path=/run/user/{uid}/bus'
                argv = ['runuser','-u',username,'--','env',*['%s=%s'%(k,v) for k,v in env.items()],
                        python_executable,str(suite[0])]
                rc,out = run(argv,timeout=180,cwd=str(suite[0].parent.parent))
                report['logs']['real_kde_desktop_acceptance']={'returncode':rc,'output':out[-24000:]}
                check('guest_real_kde_33_gui_checks', classify_desktop(rc,out),
                      f'Ran packaged acceptance against actual guest KWin {platform} session')
                check(f'guest_kde_{"wayland" if platform=="wayland" else "x11"}',
                      PASS if classify_desktop(rc,out)==PASS else FAIL, f'KWin {platform} session and runner')
            else:
                check('guest_real_kde_33_gui_checks',NOT_TESTED,'No launchable KWin session environment found')
            if qa_sh:
                rc, out = run(['runuser','-u',username,'--','bash',str(qa_sh[0])],
                              timeout=480,cwd=str(qa_sh[0].parent))
                report['logs']['packaged_qa_sh']={'returncode':rc,'output':out[-24000:]}
                check('guest_packaged_regression_suite',PASS if rc==0 and 'PASS' in out else FAIL,
                      f'Exact packaged qa.sh exited {rc}; inspect full output')
            else:
                check('guest_packaged_regression_suite',FAIL,'Missing qa.sh in verified app archive')
    except Exception as exc:
        check('guest_runner_failure',FAIL,f'{type(exc).__name__}: {exc}')
    return finalize(report)


def finalize(report):
    # These acceptance requirements require separately proven actual operations.
    missing={
      'guest_real_install_uninstall':'No real install/uninstall transaction performed inside installed guest',
      'guest_upgrade_previous_release':'v0.1.17 -> v0.1.19 install/rollback not performed',
      'guest_doctor_repair':'No guided repairs or Doctor transitions exercised end-to-end',
      'guest_grub_disk_recovery_reboot':'Live ISO does not validate a real installed GRUB boot',
      'guest_kde_x11':'No verified native KDE X11 acceptance',
      'guest_kde_wayland':'No verified native KDE Wayland acceptance',
      'physical_hardware':'CachyOS VM cannot prove physical firmware/GPU/storage recovery',
    }
    for key, reason in missing.items():
        report['checks'].setdefault(key,{'status':NOT_TESTED,'evidence':reason})
    check = report['checks']
    report['release_decision'] = 'BLOCKED' if any(v['status'] != PASS for v in check.values()) else 'APPROVED'
    # A guest runner is never authorised to approve hardware acceptance.
    if report['release_decision'] == 'APPROVED':
        report['release_decision'] = 'BLOCKED'
        report['limitations'].append('Physical machine acceptance cannot be completed by a virtual machine')
    report['checks_run'] = len(check)
    dest = ROOT/'app-qa-v0.1.11.json'
    dest.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print('GUEST_APP_QA_REPORT_SAVED',dest)
    for key,value in sorted(check.items()):
        print(value['status'],key,value['evidence'][:150])
    print('GUEST_APP_MASTER_QA_'+report['release_decision'])
    return 0


if __name__=='__main__':
    raise SystemExit(main())