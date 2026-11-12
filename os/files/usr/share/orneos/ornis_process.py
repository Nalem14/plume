"""Bounded cross-platform command jobs, supervised by the native app (never the cloud)."""
import json
import os
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

import ornis_local
from ornis_consent import STATE

JOBS = STATE / 'ornis-jobs'
RUNNING = {}
LOCK = threading.Lock()
MAX_OUTPUT = 1024 * 1024


def _sandbox_wrap(argv, where: Path, command: str, kind: str) -> list[str]:
    """Wraps commands in an OS sandbox (bubblewrap on Linux, sandbox-exec on macOS) when available.
    Read-only commands get a read-only filesystem; workspace commands get write access only to the active workspace and /tmp."""
    if kind != 'command':
        return argv
    try:
        import ornis_consent
        import ornis_shell
        cfg = ornis_consent.settings()
        if not cfg.get('sandbox', True):
            return argv
        info = ornis_shell.classify(command)
        if info.get('level') == 'admin':
            return argv
        read_only = bool(info.get('read_only'))
        ws_str = str(cfg.get('workspace') or '').strip()
        ws_path = Path(ws_str).resolve() if ws_str and Path(ws_str).is_dir() else None
        in_ws = bool(ws_path and (where == ws_path or ws_path in where.parents))
        if not read_only and not in_ws:
            return argv
        sb = ornis_local.sandbox_available()
        home = Path.home().resolve()
        if sb == 'bwrap':
            cmd = ['bwrap', '--ro-bind', '/', '/', '--dev', '/dev', '--proc', '/proc',
                   '--bind', '/tmp', '/tmp']
            if not read_only and ws_path:
                cmd += ['--bind', str(ws_path), str(ws_path)]
            # no --die-with-parent: it kills the job when the *thread* that started it ends (a worker thread)
            cmd += ['--chdir', str(where)]
            if not info.get('sensitive'):
                for secret in ('.ssh', '.gnupg', '.pki', '.aws', '.kube', '.password-store'):
                    sp = home / secret
                    if sp.is_dir():
                        cmd += ['--tmpfs', str(sp)]
            return [*cmd, '--', *argv]
        if sb == 'seatbelt':
            ws_allow = f'(allow file-write* (subpath "{ws_path}"))' if (not read_only and ws_path) else ''
            profile = (
                '(version 1)(allow default)'
                f'(deny file-write* (subpath "{home}"))'
                f'{ws_allow}'
                '(allow file-write* (subpath "/tmp") (subpath "/private/tmp") (subpath "/dev"))'
            )
            if not info.get('sensitive'):
                for secret in ('.ssh', '.gnupg', '.aws', '.kube'):
                    profile += f'(deny file-read* (subpath "{home / secret}"))'
            return ['sandbox-exec', '-p', profile, *argv]
    except Exception:
        pass
    return argv


def start(command, cwd='~', wait=25, label='', kind='command', on_output=None, sandbox=True):
    from ornis_shell import _cleanup
    _cleanup()
    where = Path(cwd).expanduser()
    where = (where if where.is_absolute() else Path.home() / where).resolve()
    if not where.is_dir():
        raise ValueError('Working directory does not exist')
    with LOCK:
        if len(RUNNING) >= 4:
            raise ValueError('Four local commands are already running; follow or stop one first')
        job = uuid.uuid4().hex[:12]
        folder = JOBS / job
        folder.mkdir(parents=True, mode=0o700)
        env = ornis_local.environment()
        env.update(ORNIS_CWD=str(where), ORNIS='1', NO_COLOR='1', PAGER='cat', GIT_PAGER='cat', TERM='dumb')
        from ornis_shell import admin_execution
        command_to_run, manual = admin_execution(str(command), env)
        if manual:
            return dict(done=True, exit_code=126, output="Authentication requires your terminal. Copy and run this command there:\n" + str(command), command=command, job="", seconds=0, manual=True)
        # ssh, scp, git over ssh: no terminal here, so its password and « trust this server? » go to a window
        # (OpenSSH ≥ 8.4 with SSH_ASKPASS_REQUIRE); without such a program, a key (ssh-agent) still works
        askpass = next((p for p in ('/usr/bin/ksshaskpass', '/usr/libexec/openssh/ksshaskpass', '/usr/bin/ssh-askpass',
                                    '/usr/libexec/openssh/gnome-ssh-askpass', '/usr/lib/ssh/x11-ssh-askpass',
                                    '/usr/lib/openssh/gnome-ssh-askpass') if Path(p).is_file()), '')
        if askpass and not env.get('SSH_ASKPASS'):
            env['SSH_ASKPASS'] = askpass
            env['SSH_ASKPASS_REQUIRE'] = 'force'
        argv = [*ornis_local.shell(), command_to_run]
        if sandbox:
            argv = _sandbox_wrap(argv, where, str(command), kind)
        proc = subprocess.Popen(argv, cwd=str(where), env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=os.name != 'nt',
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        RUNNING[job] = proc
    meta = dict(id=job, command=command, cwd=str(where), label=label or command[:120], kind=kind, started=time.time(), supervisor=os.getpid())
    (folder / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')
    (folder / 'pid').write_text(str(proc.pid))

    def collect():
        # Keep a bounded tail on disk. read1 returns as soon as output is available.
        tail = b''
        try:
            with (folder / 'output').open('wb') as out:
                while True:
                    chunk = proc.stdout.read1(8192)
                    if not chunk:
                        break
                    tail = (tail + chunk)[-MAX_OUTPUT:]
                    out.seek(0); out.write(tail); out.truncate(); out.flush()
            code = proc.wait()
            (folder / 'exit.tmp').write_text(str(code))
            (folder / 'exit.tmp').replace(folder / 'exit')
        finally:
            proc.stdout.close()
            with LOCK:
                RUNNING.pop(job, None)
    threading.Thread(target=collect, daemon=True).start()
    def supervise():
        deadline = time.monotonic() + 3 * 3600
        while proc.poll() is None:
            if (folder / 'stopped').exists() or time.monotonic() >= deadline:
                stop(job)
                return
            time.sleep(.2)
    threading.Thread(target=supervise, daemon=True).start()
    return status(job, wait, on_output=on_output)


def _folder(job):
    import re
    if not re.fullmatch(r'[a-f0-9]{12}', str(job)):
        raise ValueError('Invalid job')
    return JOBS / job


def status(job, wait=0, on_output=None):
    folder = _folder(job)
    try:
        meta = json.loads((folder / 'meta.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'error': 'Unknown job', 'job': job}
    from ornis_shell import _read_output
    deadline = time.monotonic() + min(55, max(0, float(wait)))
    last_emit = 0.0
    last_sig = None
    while alive(int(meta.get('supervisor', 0))) and time.monotonic() < deadline and not (folder / 'exit').exists():
        now = time.monotonic()
        if on_output is not None and now - last_emit >= 0.4:
            last_emit = now
            out_now, _ = _read_output(folder)
            tail = '\n'.join(out_now.splitlines()[-8:])
            sec = round(time.time() - meta['started'])
            sig = (tail, sec)
            if sig != last_sig:
                last_sig = sig
                try:
                    on_output(job, tail, sec)
                except Exception:
                    pass
        time.sleep(.15)
    output, _ = _read_output(folder)
    done = (folder / 'exit').exists()
    if not done:
        done = not alive(int(meta.get('supervisor', 0)))
    try:
        code = int((folder / 'exit').read_text(encoding="utf-8")) if done else None
    except (ValueError, OSError):
        code = -1
    return dict(note='' if done else 'Still running: follow this job with computer_command_status; do not start it again.', job=job, label=meta['label'], command=meta['command'], kind=meta['kind'], output=output,
                done=done, exit_code=code, seconds=round(time.time()-meta['started']), stopped=(folder/'stopped').exists())


def stop(job):
    folder = _folder(job)
    with LOCK:
        proc = RUNNING.get(job)
    if not (folder / 'exit').exists():
        (folder / 'stopped').write_text('1')
    if proc and proc.poll() is None:
        (folder / 'stopped').write_text('1')
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=10)
        else:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return status(job, 3)


def stop_all():
    for job in list(RUNNING):
        stop(job)


def alive(pid):
    if pid <= 0:
        return False
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        try:
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
