"""Portable native capabilities. No cloud-side execution, no shell for opening a path."""
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import system


def is_orneos():
    try:
        return 'ORNEOS_BUILD=' in Path('/etc/os-release').read_text() or Path('/usr/share/orneos/os.json').is_file()
    except OSError:
        return False


def shell():
    if system.WINDOWS:
        return [shutil.which('pwsh') or shutil.which('powershell') or 'powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command']
    return [shutil.which('bash') or '/bin/sh', '-c']


def environment():
    # Do not inherit cloud credentials, API tokens or unrelated developer secrets into commands / MCP servers.
    names = ('PATH', 'HOME', 'USER', 'USERNAME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'SYSTEMROOT', 'WINDIR',
             'COMSPEC', 'PATHEXT', 'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL', 'DISPLAY', 'WAYLAND_DISPLAY',
             'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'SHELL')
    return {k: v for k, v in os.environ.items() if k.upper() in names}


ALL_CAPABILITIES = [
    'status', 'open', 'volume', 'brightness', 'appearance', 'clipboard', 'timer', 'lock', 'power',
    'find_files', 'grep_files', 'move_files', 'create_folder', 'list_folder', 'read_file', 'write_file', 'edit_file', 'trash_files',
    'processes', 'quit_app', 'setting', 'find_app', 'install_app', 'remove_app',
    'run_command', 'command_status', 'open_terminal', 'screenshot',
    'extensions', 'skill_read', 'mcp_tools', 'mcp_call',
]

_SANDBOX_CACHE = None


def sandbox_available() -> str:
    """Returns 'bwrap' on Linux/Orneos OS when bubblewrap works, 'seatbelt' on macOS when sandbox-exec is present, else ''."""
    global _SANDBOX_CACHE
    if _SANDBOX_CACHE is not None:
        return _SANDBOX_CACHE
    if system.MACOS and shutil.which('sandbox-exec'):
        _SANDBOX_CACHE = 'seatbelt'
        return _SANDBOX_CACHE
    if not system.WINDOWS and not system.MACOS and shutil.which('bwrap'):
        try:
            res = subprocess.run(['bwrap', '--ro-bind', '/', '/', '--', 'true'],
                                 capture_output=True, timeout=2)
            if res.returncode == 0:
                _SANDBOX_CACHE = 'bwrap'
                return _SANDBOX_CACHE
        except (OSError, subprocess.SubprocessError):
            pass
    _SANDBOX_CACHE = ''
    return _SANDBOX_CACHE


def _distro():
    if is_orneos():
        return 'Orneos OS'
    if system.MACOS:
        ver = platform.mac_ver()[0]
        return f'macOS {ver}'.strip()
    if system.WINDOWS:
        return f'Windows {platform.release()}'.strip()
    try:
        for line in Path('/etc/os-release').read_text(encoding='utf-8').splitlines():
            if line.startswith('PRETTY_NAME='):
                return line.split('=', 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return platform.system()


def status():
    disk = shutil.disk_usage(Path.home())
    os_name = 'Orneos OS' if is_orneos() else ('macOS' if system.MACOS else ('Windows' if system.WINDOWS else platform.system()))
    desktop = os.environ.get('XDG_CURRENT_DESKTOP') or ('Aqua' if system.MACOS else ('Windows' if system.WINDOWS else ''))
    ws = ''
    try:
        import ornis_consent
        ws = ornis_consent.settings().get('workspace') or ''
    except Exception:
        pass
    return {'os': os_name, 'distro': _distro(), 'desktop': desktop, 'platform': sys.platform,
            'release': platform.release(), 'architecture': platform.machine(), 'home': str(Path.home()),
            'shell': Path(shell()[0]).name, 'disk_free': disk.free, 'cpu_count': os.cpu_count(),
            'capabilities': list(ALL_CAPABILITIES), 'is_orneos': is_orneos(),
            'sandbox': sandbox_available(), 'workspace': ws,
            'native_integration': True,
            'security': 'Runs as the local user after local permission checks; OS sandbox active when available. Tool results reach the cloud model.'}


def open_target(target):
    from urllib.parse import urlparse
    target = str(target or '').strip()
    if urlparse(target).scheme in ('https', 'http', 'mailto'):
        system.open_url(target)
        return {'opened': target}
    p = Path(target).expanduser()
    if not p.is_absolute():
        cand = Path.home() / p
        if cand.exists():
            p = cand
    if p.exists():
        from PySide6.QtCore import QUrl
        system.open_url(QUrl.fromLocalFile(str(p.resolve())).toString())
        return {'opened': str(p)}
    # Applications are argv entries, never evaluated as shell source.
    if system.MACOS:
        for base in (Path('/Applications'), Path('/System/Applications'), Path.home() / 'Applications'):
            app_bundle = base / (target if target.endswith('.app') else f'{target}.app')
            if app_bundle.exists():
                subprocess.Popen(['open', '-a', str(app_bundle)], env=environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return {'opened': app_bundle.stem}
        res = subprocess.run(['open', '-Ra', target], env=environment(), capture_output=True)
        if res.returncode == 0:
            subprocess.Popen(['open', '-a', target], env=environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {'opened': target}
    elif system.WINDOWS:
        exe = shutil.which(target) or shutil.which(target + '.exe')
        if exe:
            subprocess.Popen([exe], env=environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {'opened': target}
        start_dirs = [
            Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'Microsoft/Windows/Start Menu/Programs',
            Path(os.environ.get('APPDATA', '')) / 'Microsoft/Windows/Start Menu/Programs',
        ]
        needle = target.lower()
        for d in start_dirs:
            if not d.is_dir():
                continue
            for lnk in d.rglob('*.lnk'):
                if needle in lnk.stem.lower():
                    from PySide6.QtCore import QUrl
                    system.open_url(QUrl.fromLocalFile(str(lnk)).toString())
                    return {'opened': lnk.stem}
    elif shutil.which(target):
        subprocess.Popen([shutil.which(target)], env=environment(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {'opened': target}
    return {'error': 'Application or path not found. Use the native shell after checking the platform.'}


def helper(name):
    """Same permission/activity windows in installed OS, source checkout and frozen Plume."""
    if name not in ('consent', 'computer'):
        raise ValueError('unknown helper')
    if system.FROZEN:
        return [sys.executable, '--ornis-helper=' + name]
    script = system.SHARE.parent / 'libexec' / ('orneos-ornis-' + name)
    if not script.is_file():
        script = system.SHARE / 'orneos' / 'helpers' / ('orneos-ornis-' + name)
    return [sys.executable, str(script)]


def dispatch_helper():
    name = next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--ornis-helper=')), '')
    if not name:
        return
    if name == 'code-hook':                  # Ornis Code's post_tool hook (ornis_code_hook): long outputs to .ornis/tmp
        import ornis_code_hook
        raise SystemExit(ornis_code_hook.main())
    if name == 'cron-mcp':                   # built-in MCP for local Code cron tasks
        import ornis_cron_mcp
        raise SystemExit(ornis_cron_mcp.main())
    if name == 'cron-cli':                   # same tools over argv/JSON when MCP cannot connect
        import ornis_cron_cli
        raise SystemExit(ornis_cron_cli.main(
            [a for a in sys.argv[1:] if not a.startswith('--ornis-helper=')]))
    if name == 'search-mcp':                 # Orneos Search for Code (web_search / read_web_page)
        import ornis_search_mcp
        raise SystemExit(ornis_search_mcp.main())
    if name == 'search-cli':                 # same tools over argv/JSON when MCP cannot connect
        import ornis_search_cli
        raise SystemExit(ornis_search_cli.main(
            [a for a in sys.argv[1:] if not a.startswith('--ornis-helper=')]))
    if name == 'bots-mcp':                   # built-in MCP for local Code bots
        import ornis_bots_mcp
        raise SystemExit(ornis_bots_mcp.main())
    if name == 'bots-cli':                   # same tools over argv/JSON when MCP cannot connect
        import ornis_bots_cli
        raise SystemExit(ornis_bots_cli.main(
            [a for a in sys.argv[1:] if not a.startswith('--ornis-helper=')]))
    if name not in ('consent', 'computer'):
        raise SystemExit(2)
    import runpy
    script = system.SHARE / 'orneos' / 'helpers' / ('orneos-ornis-' + name)
    sys.argv = [str(script), *[a for a in sys.argv[1:] if not a.startswith('--ornis-helper=')]]
    runpy.run_path(str(script), run_name='__main__')
    raise SystemExit(0)


def enabled():
    try:
        return json.loads((system.CONFIG / 'ornis.json').read_text(encoding='utf-8')).get('local_tools', True) is not False
    except (ValueError, OSError):
        return True


def workspace_context(ws_path: str | None = None) -> dict:
    """Inspects the active local workspace directory: path, top files, git status, and project instructions (ORNEOS.md / AGENTS.md / CLAUDE.md)."""
    try:
        import ornis_consent
        raw = ws_path if ws_path is not None else (ornis_consent.settings().get('workspace') or '')
    except Exception:
        raw = ws_path or ''
    if not raw:
        return {}
    try:
        p = Path(raw).expanduser().resolve()
        home = Path.home().resolve()
        if not p.is_dir() or (p != home and home not in p.parents):
            return {}
        shown = '~/' + str(p.relative_to(home)) if home in p.parents else str(p)
        entries = []
        for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))[:35]:
            if child.name in ('.git', 'node_modules', '__pycache__', '.venv', 'venv', 'target', 'dist', 'build'):
                continue
            entries.append(child.name + ('/' if child.is_dir() else ''))
        out = {'path': shown, 'entries': entries}
        # Git branch and dirty count
        if (p / '.git').exists() and shutil.which('git'):
            try:
                res = subprocess.run(['git', '-C', str(p), 'status', '--porcelain', '-b'],
                                     capture_output=True, text=True, timeout=1.5, env=environment())
                if res.returncode == 0 and res.stdout:
                    lines = res.stdout.strip().splitlines()
                    branch = lines[0].removeprefix('## ').split('...')[0].strip() if lines else ''
                    dirty = len(lines) - 1 if lines else 0
                    out['git'] = {'branch': branch, 'dirty_files': max(0, dirty)}
            except (OSError, subprocess.SubprocessError):
                pass
        # Project guide (ORNEOS.md, AGENTS.md, CLAUDE.md)
        for guide_name in ('ORNEOS.md', 'AGENTS.md', 'CLAUDE.md', '.cursorrules'):
            guide = p / guide_name
            if guide.is_file() and not guide.is_symlink():
                try:
                    text = guide.read_text(encoding='utf-8', errors='replace').strip()[:3000]
                    if text:
                        out['guide_file'] = guide_name
                        out['guide_excerpt'] = text
                        break
                except OSError:
                    pass
        return out
    except OSError:
        return {}


def context_snapshot() -> dict:
    """Compact local environment, workspace, skills and MCP snapshot sent on turn 1 so the agent needs 0 discovery round-trips."""
    st = status()
    snap = {
        'os': st['os'],
        'distro': st['distro'],
        'shell': st['shell'],
        'arch': st['architecture'],
        'is_orneos': st['is_orneos'],
        'sandbox': st['sandbox'],
    }
    ws = workspace_context(st.get('workspace'))
    if ws:
        snap['workspace'] = ws
    try:
        import ornis_extensions
        cat = ornis_extensions.catalogue()
        if cat.get('skills'):
            snap['skills'] = [{'name': s['name'], 'description': s['description'][:120]} for s in cat['skills'][:25]]
        if cat.get('mcpServers'):
            snap['mcpServers'] = cat['mcpServers'][:20]
    except Exception:
        pass
    return snap
