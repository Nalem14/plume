"""Ornis acts on this computer (Orneos OS). Ornis runs in the cloud: when it calls one of its computer_* tools
(ornis/agent/overlay/all_tools/orneos_computer.py), the request waits in the orneos app of the cloud until the
computer that is following the reply (ornis_chat.Chat.wait, in the top-bar applet or the Ornis app) picks it up,
runs it here and sends the result back.

The computer decides, never the conversation (ornis_consent): each request has a level, the user's mode says what
runs without a question, the rest is asked in a window (orneos-ornis-consent). Applications: ornis_apps; the
terminal: ornis_shell. Files stay inside the home folder; every action is written in the journal, with what is
needed to undo it (moves, writes, new folders).
"""
import json
import contextvars
import system
import os
import signal
import re
import shutil
import subprocess
import time
import unicodedata
from configparser import ConfigParser
from pathlib import Path

import ornis_local
import ornis_extensions
import ornis_apps
import ornis_consent
import ornis_shell

HOME = Path.home()
SKIP_DIRS = {".cache", ".local", ".var", ".mozilla", ".config", "node_modules", ".git", "__pycache__", ".Trash-1000"}


def _run(cmd, timeout=6):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.returncode, (out.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""


def _later(seconds, cmd):
    """Runs after the reply has gone back (restart, shut down…), in its own transient unit or detached process."""
    sec = max(1, int(seconds))
    if system.WINDOWS:
        pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        args_json = json.dumps([str(c) for c in cmd])
        script = f"Start-Sleep -Seconds {sec}; $a = ConvertFrom-Json '{args_json}'; & $a[0] $a[1..($a.Length-1)]"
        subprocess.Popen([pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif shutil.which("systemd-run"):
        subprocess.Popen(["systemd-run", "--user", "--collect", f"--on-active={sec}s", *cmd],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["sh", "-c", f"sleep {sec}; exec \"$@\"", "_", *cmd], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _norm(text):
    return "".join(c for c in unicodedata.normalize("NFKD", str(text).lower()) if not unicodedata.combining(c))


OUTSIDE_APPROVED = contextvars.ContextVar("ornis_outside_approved", default=False)


def _default_root() -> Path:
    ws = ornis_consent.settings().get("workspace") or ""
    if ws:
        try:
            p = Path(ws).resolve()
            if p.is_dir() and (p == HOME or HOME in p.parents):
                return p
        except OSError:
            pass
    return HOME


def _home_path(path, must_exist=True):
    """A path the user named, inside the home folder (or relative to the active workspace when set)."""
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("empty path")
    root = _default_root()
    if raw in (".", "./"):
        p = root
    else:
        p = Path(os.path.expanduser(raw))
        if not p.is_absolute():
            ws_cand = root / p
            home_cand = HOME / p
            if root != HOME and (ws_cand.exists() or (not must_exist and not home_cand.parent.exists())):
                p = ws_cand
            elif not home_cand.exists() and ws_cand.exists():
                p = ws_cand
            else:
                p = root / p if root != HOME and not raw.startswith(("Documents/", "Téléchargements/", "Downloads/", "Bureau/", "Desktop/", "Images/", "Pictures/", "Orneos/")) else home_cand
    p = p.resolve()
    if p != HOME and HOME not in p.parents and not OUTSIDE_APPROVED.get():
        raise ValueError("Outside-home paths require explicit permission")
    if must_exist and not p.exists():
        raise ValueError(f"not found: {raw}")
    return p


def _shown(p):
    return "~" if p == HOME else "~/" + str(p.relative_to(HOME)) if HOME in p.parents else str(p)


# ---- what the computer is ------------------------------------------------------------------------------------
def status():
    import platform
    out = dict(ornis_local.status())
    out["capabilities"] = list(ACTIONS)
    out["hostname"] = platform.node()
    usage = shutil.disk_usage(HOME)
    out["disk"] = {"free_gb": round(usage.free / 1e9, 1), "total_gb": round(usage.total / 1e9, 1),
                   "used_percent": round(100 * usage.used / usage.total)}
    if system.WINDOWS:
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            mem = MEMORYSTATUSEX(dwLength=ctypes.sizeof(MEMORYSTATUSEX))
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                out["memory"] = {"total_gb": round(mem.ullTotalPhys / 1e9, 1),
                                 "available_gb": round(mem.ullAvailPhys / 1e9, 1)}
            out["uptime_hours"] = round(ctypes.windll.kernel32.GetTickCount64() / 3600000.0, 1)

            class SYSTEM_POWER_STATUS(ctypes.Structure):
                _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                            ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                            ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
            pwr = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(pwr)) and 0 <= pwr.BatteryLifePercent <= 100:
                out["battery"] = {"percent": int(pwr.BatteryLifePercent),
                                  "state": "charging" if pwr.ACLineStatus == 1 else "discharging"}
        except Exception:
            pass
        return out
    if system.MACOS:
        code, batt = _run(["pmset", "-g", "batt"])
        m = re.search(r"(\d+)%;\s*([a-zA-Z ]+)", batt)
        if m:
            out["battery"] = {"percent": int(m.group(1)), "state": m.group(2).strip().lower()}
        code, memsize = _run(["sysctl", "-n", "hw.memsize"])
        if code == 0 and memsize.isdigit():
            out["memory"] = {"total_gb": round(int(memsize) / 1e9, 1)}
        code, vol = _run(["osascript", "-e", "get volume settings"])
        vm = re.search(r"output volume:(\d+).*output muted:(true|false)", vol)
        if vm:
            out["volume_percent"] = int(vm.group(1))
            out["muted"] = vm.group(2) == "true"
        return out
    if Path("/usr/libexec/orneos-status").is_file():
        code, about = _run(["/usr/libexec/orneos-status", "--about"], timeout=15)
        try:
            info = json.loads(about).get("about") or {}
            out["system"] = {k: info[k] for k in ("version", "channel", "driver", "machine") if info.get(k)}
        except (json.JSONDecodeError, AttributeError):
            pass
    for bat in sorted(Path("/sys/class/power_supply").glob("BAT*")):
        try:
            out["battery"] = {"percent": int((bat / "capacity").read_text(encoding="utf-8").strip()),
                              "state": (bat / "status").read_text(encoding="utf-8").strip().lower()}
        except (OSError, ValueError):
            pass
        break
    try:
        mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines() if ":" in line)
        total = int(mem["MemTotal"].split()[0]) / 1e6
        avail = int(mem["MemAvailable"].split()[0]) / 1e6
        out["memory"] = {"total_gb": round(total, 1), "available_gb": round(avail, 1)}
        out["uptime_hours"] = round(float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0]) / 3600, 1)
    except (OSError, KeyError, ValueError, IndexError):
        pass
    if shutil.which("nmcli"):
        code, wifi = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "device", "wifi"])
        ssid = next((line.split(":", 1)[1] for line in wifi.splitlines() if line.startswith("yes:")), "")
        if ssid:
            out["wifi"] = ssid
    if shutil.which("wpctl"):
        code, vol = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        m = re.search(r"([\d.]+)", vol)
        if m:
            out["volume_percent"] = round(float(m.group(1)) * 100)
            out["muted"] = "MUTED" in vol
    return out


# ---- opening -------------------------------------------------------------------------------------------------
def _desktop_entries():
    dirs = [Path("/usr/share/applications"), HOME / ".local/share/applications",
            Path("/var/lib/flatpak/exports/share/applications"), HOME / ".local/share/flatpak/exports/share/applications"]
    lang = (os.environ.get("LANG") or "fr")[:2]
    for d in dirs:
        for f in sorted(d.glob("*.desktop")) if d.is_dir() else []:
            cp = ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(f, encoding="utf-8")
                e = cp["Desktop Entry"]
            except Exception:  # noqa: BLE001 - a broken entry is skipped
                continue
            if e.get("NoDisplay", "false") == "true" or e.get("Type", "Application") != "Application":
                continue
            names = [e.get(k, "") for k in (f"Name[{lang}]", "Name", f"GenericName[{lang}]", "GenericName", "Keywords", f"Keywords[{lang}]")]
            yield f, e.get(f"Name[{lang}]") or e.get("Name") or f.stem, _norm(" ".join(names))


def open_target(target):
    """An application by its name, a file or folder of the home, or a web address."""
    target = str(target or "").strip()
    if system.WINDOWS or system.MACOS:
        try:
            path = _home_path(target)
            res = ornis_local.open_target(str(path))
            return {"opened": _shown(path)} if "opened" in res else res
        except ValueError:
            return ornis_local.open_target(target)
    if re.match(r"^(https?://|mailto:)", target):
        subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {"opened": target}
    try:
        path = _home_path(target)
        subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {"opened": _shown(path)}
    except ValueError:
        pass
    words = _norm(target).replace("orneos", "").split()
    best, best_score = None, 0
    for f, name, hay in _desktop_entries():
        if not words:
            break
        score = sum(2 if w in _norm(name).split() else 1 for w in words if w in hay)
        if score > best_score:
            best, best_score = (f, name), score
    if best is None:
        if shutil.which(target):
            subprocess.Popen([shutil.which(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return {"opened": target}
        return {"error": f"no application or file called « {target} » on this computer"}
    subprocess.Popen(["gio", "launch", str(best[0])] if shutil.which("gio") else ["kioclient", "exec", str(best[0])],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return {"opened": best[1]}


# ---- settings ----------------------------------------------------------------------------------------------------
def volume(level=None, mute=None):
    if system.MACOS:
        if mute is not None:
            _run(["osascript", "-e", f"set volume output muted {'true' if mute else 'false'}"])
        if level is not None:
            level = max(0, min(100, int(level)))
            _run(["osascript", "-e", f"set volume output volume {level}"])
            if level > 0 and mute is None:
                _run(["osascript", "-e", "set volume output muted false"])
        code, vol = _run(["osascript", "-e", "get volume settings"])
        vm = re.search(r"output volume:(\d+).*output muted:(true|false)", vol)
        if code != 0 or not vm:
            return {"error": "no sound output"}
        return {"volume_percent": int(vm.group(1)), "muted": vm.group(2) == "true"}
    if shutil.which("wpctl"):
        sink = "@DEFAULT_AUDIO_SINK@"
        if mute is not None:
            _run(["wpctl", "set-mute", sink, "1" if mute else "0"])
        if level is not None:
            level = max(0, min(100, int(level)))
            _run(["wpctl", "set-volume", sink, f"{level / 100:.2f}"])
            if level > 0 and mute is None:
                _run(["wpctl", "set-mute", sink, "0"])
        code, vol = _run(["wpctl", "get-volume", sink])
        m = re.search(r"([\d.]+)", vol)
        if code == 0 and m:
            return {"volume_percent": round(float(m.group(1)) * 100), "muted": "MUTED" in vol}
    if shutil.which("pactl"):
        sink = "@DEFAULT_SINK@"
        if mute is not None:
            _run(["pactl", "set-sink-mute", sink, "1" if mute else "0"])
        if level is not None:
            level = max(0, min(100, int(level)))
            _run(["pactl", "set-sink-volume", sink, f"{level}%"])
            if level > 0 and mute is None:
                _run(["pactl", "set-sink-mute", sink, "0"])
        code, vol = _run(["pactl", "get-sink-volume", sink])
        _, m_out = _run(["pactl", "get-sink-mute", sink])
        m = re.search(r"(\d+)%", vol)
        if code == 0 and m:
            return {"volume_percent": int(m.group(1)), "muted": "yes" in m_out.lower()}
    return {"error": "no sound output"}


def brightness(level):
    level = max(1, min(100, int(level)))
    if system.WINDOWS:
        pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        cmd = f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods).WmiSetBrightness(1, {level})"
        if _run([pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", cmd], timeout=10)[0] == 0:
            return {"brightness_percent": level}
        return {"error": "this screen's brightness cannot be changed from the computer (external monitor?)"}
    if system.MACOS:
        if shutil.which("brightness") and _run(["brightness", f"{level / 100:.2f}"])[0] == 0:
            return {"brightness_percent": level}
        return {"error": "this screen's brightness cannot be changed automatically on this Mac"}
    try:
        import dbus  # noqa: PLC0415
        bus = dbus.SessionBus()
        obj = bus.get_object("org.kde.ScreenBrightness", "/org/kde/ScreenBrightness/display0")
        props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        top = int(props.Get("org.kde.ScreenBrightness.Display", "MaxBrightness"))
        dbus.Interface(obj, "org.kde.ScreenBrightness.Display").SetBrightness(dbus.Int32(round(top * level / 100)), dbus.UInt32(0))
        return {"brightness_percent": level}
    except Exception:  # noqa: BLE001 - no Plasma screen brightness (desktop screen, older Plasma)
        pass
    if shutil.which("brightnessctl") and _run(["brightnessctl", "set", f"{level}%"])[0] == 0:
        return {"brightness_percent": level}
    if shutil.which("gdbus"):
        code, _ = _run(["gdbus", "call", "--session", "--dest", "org.gnome.SettingsDaemon.Power",
                        "--object-path", "/org/gnome/SettingsDaemon/Power",
                        "--method", "org.freedesktop.DBus.Properties.Set",
                        "org.gnome.SettingsDaemon.Power.Screen", "Brightness", f"<int32 {level}>"])
        if code == 0:
            return {"brightness_percent": level}
    return {"error": "this screen's brightness cannot be changed from the computer (external monitor?)"}


def appearance(mode):
    mode = str(mode).lower()
    mode = ("dark" if mode in ("dark", "sombre", "dunkel")
            else "auto" if mode in ("auto", "automatic", "automatique", "automatisch", "system")
            else "light")
    if Path("/usr/libexec/orneos-status").is_file():
        code, _ = _run(["/usr/libexec/orneos-status", "--theme", mode], timeout=30)
        return {"appearance": mode} if code == 0 else {"error": "the appearance could not be changed"}
    if system.MACOS:
        val = "true" if mode == "dark" else "false"
        code, _ = _run(["osascript", "-e", f'tell application "System Events" to tell appearance preferences to set dark mode to {val}'])
        return {"appearance": mode} if code == 0 else {"error": "the appearance could not be changed"}
    if system.WINDOWS:
        val = "0" if mode == "dark" else "1"
        key = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        c1, _ = _run(["reg", "add", key, "/v", "AppsUseLightTheme", "/t", "REG_DWORD", "/d", val, "/f"])
        c2, _ = _run(["reg", "add", key, "/v", "SystemUsesLightTheme", "/t", "REG_DWORD", "/d", val, "/f"])
        return {"appearance": mode} if c1 == 0 and c2 == 0 else {"error": "the appearance could not be changed"}
    if shutil.which("plasma-apply-colorscheme"):
        scheme = "BreezeDark" if mode == "dark" else "BreezeLight"
        if _run(["plasma-apply-colorscheme", scheme])[0] == 0:
            return {"appearance": mode}
    if shutil.which("gsettings"):
        scheme = "prefer-dark" if mode == "dark" else "default"
        if _run(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", scheme])[0] == 0:
            return {"appearance": mode}
    return {"error": "the appearance could not be changed"}


def clipboard(text):
    text = str(text or "")
    if shutil.which("wl-copy"):
        subprocess.Popen(["wl-copy", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"copied_characters": len(text)}
    if system.MACOS and shutil.which("pbcopy"):
        subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
        return {"copied_characters": len(text)}
    if system.WINDOWS and shutil.which("clip"):
        subprocess.run(["clip"], input=text, text=True, timeout=5)
        return {"copied_characters": len(text)}
    import cloud  # noqa: PLC0415
    return {"copied_characters": len(text)} if cloud.copy_to_clipboard(text) else {"error": "no clipboard"}


def timer(minutes, label):
    minutes = max(1, min(24 * 60, int(minutes)))
    label = str(label or "").strip()[:120] or "Ornis"
    if system.MACOS:
        _later(minutes * 60, ["osascript", "-e", f'display notification {json.dumps("⏰ " + label)} with title "Ornis"'])
    elif system.WINDOWS:
        pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        _later(minutes * 60, [pwsh, "-NoLogo", "-NoProfile", "-Command",
                              f"Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show({json.dumps('⏰ ' + label)}, 'Ornis')"])
    else:
        _later(minutes * 60, ["notify-send", "-a", "Ornis", "-i", "eu.orneos.ornis", "-u", "critical", "⏰ " + label])
    return {"in_minutes": minutes, "at": time.strftime("%H:%M", time.localtime(time.time() + minutes * 60)), "label": label}


def lock():
    if system.WINDOWS:
        code, _ = _run(["rundll32.exe", "user32.dll,LockWorkStation"])
        return {"locked": code == 0}
    if system.MACOS:
        code, _ = _run(["pmset", "displaysleepnow"])
        return {"locked": code == 0}
    code, _ = _run(["loginctl", "lock-session"])
    return {"locked": code == 0}


def power(action):
    if system.WINDOWS:
        cmds = {
            "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "restart": ["shutdown.exe", "/r", "/t", "0"],
            "shutdown": ["shutdown.exe", "/s", "/t", "0"],
            "logout": ["shutdown.exe", "/l"],
        }
    elif system.MACOS:
        cmds = {
            "sleep": ["pmset", "sleepnow"],
            "restart": ["osascript", "-e", 'tell application "System Events" to restart'],
            "shutdown": ["osascript", "-e", 'tell application "System Events" to shut down'],
            "logout": ["osascript", "-e", 'tell application "System Events" to log out'],
        }
    else:
        cmds = {
            "sleep": ["systemctl", "suspend"],
            "restart": ["systemctl", "reboot"],
            "shutdown": ["systemctl", "poweroff"],
            "logout": ["qdbus6", "org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logout"]
                      if shutil.which("qdbus6") else ["loginctl", "terminate-user", os.environ.get("USER", "")],
        }
    if action not in cmds:
        return {"error": "unknown action, use sleep, restart, shutdown or logout"}
    _later(8, cmds[action])         # the answer reaches the cloud first
    return {"done": action, "in_seconds": 8}


# ---- files of the home -------------------------------------------------------------------------------------------
def find_files(query, folder="", limit=20):
    """Files and folders of the home whose name has all the words, newest first (Baloo's index when it is on)."""
    words = [_norm(w) for w in str(query or "").split() if w]
    root = _home_path(folder) if folder else _default_root()
    limit = max(1, min(50, int(limit or 20)))
    found = []
    if words and shutil.which("baloosearch6"):
        code, out = _run(["baloosearch6", "-d", str(root), "-l", str(limit * 3), " ".join(words)], timeout=8)
        found = [Path(line) for line in out.splitlines() if line.startswith("/") and Path(line).exists()]
    if not found:
        seen = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
            for name in dirnames + filenames:
                seen += 1
                if all(w in _norm(name) for w in words):
                    found.append(Path(dirpath) / name)
            if seen > 60000 or len(found) > limit * 5:
                break
    found = sorted(set(found), key=lambda p: -p.stat().st_mtime if p.exists() else 0)[:limit]
    return [{"path": _shown(p), "folder": p.is_dir(), "size_kb": round(p.stat().st_size / 1024) if p.is_file() else None,
             "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))} for p in found]


DOC_CACHE = ornis_consent.STATE / "ornis-doc-cache"


def _cached_doc_text(fp: Path) -> str | None:
    """Extracts and caches plain text from .docx, .odt, .xlsx or .pdf keyed by path + mtime + size."""
    import hashlib
    ext = fp.suffix.lower()
    if ext not in (".docx", ".odt", ".xlsx", ".pdf"):
        return None
    try:
        st = fp.stat()
        if st.st_size > 15_000_000:
            return None
        key = hashlib.sha1(f"{fp}:{int(st.st_mtime)}:{st.st_size}".encode("utf-8")).hexdigest()[:20]
        cache_file = DOC_CACHE / f"{key}.txt"
        if cache_file.is_file():
            return cache_file.read_text(encoding="utf-8", errors="replace")
        text = None
        if ext in (".docx", ".odt", ".xlsx"):
            text = _extract_office_text(fp)
        elif ext == ".pdf" and shutil.which("pdftotext"):
            code, out = _run(["pdftotext", "-layout", str(fp), "-"], timeout=15)
            if code == 0:
                text = out
        if text is not None:
            try:
                DOC_CACHE.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(text[:300_000], encoding="utf-8")
            except OSError:
                pass
        return text
    except OSError:
        return None


def _grep_office_docs(root: Path, rx, glob_pat: str, matches: list, limit: int) -> bool:
    """Searches inside .docx, .odt, .xlsx and .pdf files in root, appending up to `limit` total matches."""
    import fnmatch
    if len(matches) >= limit:
        return True
    docs = []
    if root.is_file() and root.suffix.lower() in (".docx", ".odt", ".xlsx", ".pdf"):
        docs.append(root)
    elif root.is_dir():
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
            for name in filenames:
                if name.startswith(".") or Path(name).suffix.lower() not in (".docx", ".odt", ".xlsx", ".pdf"):
                    continue
                if glob_pat and not fnmatch.fnmatch(name, glob_pat):
                    continue
                docs.append(Path(dirpath) / name)
                if len(docs) >= 120:
                    break
            if len(docs) >= 120:
                break
    for fp in docs:
        text = _cached_doc_text(fp)
        if not text:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                matches.append({"path": _shown(fp), "line": lineno, "text": line.strip()[:240]})
                if len(matches) >= limit:
                    return True
    return False


def grep_files(pattern, folder="", glob="", case_sensitive=False, limit=40):
    """Search inside text and office/PDF files in a folder or the active workspace by regex or literal pattern."""
    import fnmatch
    pattern = str(pattern or "").strip()
    if not pattern:
        raise ValueError("empty search pattern")
    root = _home_path(folder) if folder else _default_root()
    limit = max(1, min(100, int(limit or 40)))
    glob_pat = str(glob or "").strip()
    try:
        rx = re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
    except re.error:
        rx = re.compile(re.escape(pattern), 0 if case_sensitive else re.IGNORECASE)
    matches = []
    if shutil.which("rg") and root.is_dir():
        cmd = ["rg", "--line-number", "--no-heading", "--color=never", "--max-columns=240",
               "--max-filesize=2M", f"--max-count={limit}"]
        if not case_sensitive:
            cmd.append("-i")
        if glob_pat:
            cmd += ["-g", glob_pat]
        cmd += ["--", pattern, str(root)]
        code, out = _run(cmd, timeout=10)
        if code in (0, 1):
            for raw_line in out.splitlines():
                parts = raw_line.split(":", 2)
                if len(parts) == 3 and parts[1].isdigit():
                    p = Path(parts[0])
                    matches.append({"path": _shown(p), "line": int(parts[1]), "text": parts[2].strip()[:240]})
                    if len(matches) >= limit:
                        break
            trunc = len(out.splitlines()) > limit
            if len(matches) < limit:
                trunc = _grep_office_docs(root, rx, glob_pat, matches, limit) or trunc
            return {"folder": _shown(root), "count": len(matches), "matches": matches, "truncated": trunc}
    files_scanned = 0
    targets = [root] if root.is_file() else []
    if root.is_dir():
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS]
            for name in filenames:
                if name.startswith(".") or (glob_pat and not fnmatch.fnmatch(name, glob_pat)):
                    continue
                targets.append(Path(dirpath) / name)
                if len(targets) >= 4000:
                    break
            if len(targets) >= 4000:
                break
    for fp in targets:
        files_scanned += 1
        if fp.suffix.lower() in (".docx", ".odt", ".xlsx", ".pdf"):
            text = _cached_doc_text(fp)
            if not text:
                continue
        else:
            try:
                if fp.stat().st_size > 2_000_000:
                    continue
                raw = fp.read_bytes()
                if b"\x00" in raw[:4096]:
                    continue
                text = raw.decode("utf-8", "replace")
            except OSError:
                continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                matches.append({"path": _shown(fp), "line": lineno, "text": line.strip()[:240]})
                if len(matches) >= limit:
                    return {"folder": _shown(root), "count": len(matches), "matches": matches, "truncated": True}
    return {"folder": _shown(root), "count": len(matches), "matches": matches, "truncated": False}


def move_files(paths, destination):
    dest = _home_path(destination, must_exist=False)
    dest.mkdir(parents=True, exist_ok=True)
    moved, problems, undo = [], [], []
    for raw in paths or []:
        try:
            src = _home_path(raw)
            if src == HOME or src in dest.parents or src == dest:
                raise ValueError("cannot move a folder into itself")
            target = dest / src.name
            n = 2
            while target.exists():
                target = dest / f"{src.stem} ({n}){src.suffix}"
                n += 1
            shutil.move(str(src), str(target))
            moved.append(_shown(target))
            undo.append([str(target), str(src)])
        except (ValueError, OSError) as error:
            problems.append(f"{raw}: {error}")
    return {"moved": moved, "problems": problems, "_undo": {"type": "move", "pairs": undo} if undo else None}


def create_folder(path):
    p = _home_path(path, must_exist=False)
    existed = p.exists()
    p.mkdir(parents=True, exist_ok=True)
    return {"created": _shown(p), "_undo": None if existed else {"type": "mkdir", "path": str(p)}}


def list_folder(path="~", hidden=False, limit=100):
    p = _home_path(path) if path and path != "~" else _default_root()
    if not p.is_dir():
        raise ValueError(f"not a folder: {path}")
    limit = max(1, min(300, int(limit or 100)))
    rows = []
    for child in sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())):
        if child.name.startswith(".") and not hidden:
            continue
        try:
            st = child.stat()
        except OSError:
            continue
        rows.append({"name": child.name + ("/" if child.is_dir() else ""),
                     "size_kb": round(st.st_size / 1024) if child.is_file() else None,
                     "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
    return {"folder": _shown(p), "count": len(rows), "items": rows[:limit], "more": max(0, len(rows) - limit)}


def _extract_office_text(p: Path) -> str | None:
    """Extracts plain text from .docx, .odt or .xlsx using stdlib zipfile + ElementTree."""
    import zipfile
    import xml.etree.ElementTree as ET
    ext = p.suffix.lower()
    if ext not in (".docx", ".odt", ".xlsx"):
        return None
    try:
        with zipfile.ZipFile(p) as zf:
            if ext == ".docx" and "word/document.xml" in zf.namelist():
                root = ET.fromstring(zf.read("word/document.xml"))
                paras = []
                for para in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                    runs = [t.text for t in para.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t") if t.text]
                    if runs:
                        paras.append("".join(runs))
                return "\n".join(paras)
            if ext == ".odt" and "content.xml" in zf.namelist():
                root = ET.fromstring(zf.read("content.xml"))
                return "\n".join("".join(el.itertext()).strip() for el in root.iter("{urn:oasis:names:tc:opendocument:xmlns:text:1.0}p") if "".join(el.itertext()).strip())
            if ext == ".xlsx":
                shared = []
                if "xl/sharedStrings.xml" in zf.namelist():
                    sroot = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                    for si in sroot.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                        shared.append("".join(t.text or "" for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
                lines = []
                for name in sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")):
                    wroot = ET.fromstring(zf.read(name))
                    for row in wroot.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
                        vals = []
                        for cell in row.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                            kind = cell.attrib.get("t", "")
                            v_el = cell.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                            val = v_el.text if v_el is not None and v_el.text is not None else ""
                            if kind == "s" and val.isdigit() and int(val) < len(shared):
                                val = shared[int(val)]
                            vals.append(val)
                        if any(vals):
                            lines.append("\t".join(vals))
                return "\n".join(lines)
    except Exception:
        return None
    return None


def read_file(path, max_chars=20000, start_line=None, end_line=None):
    p = _home_path(path)
    if p.is_dir():
        return list_folder(str(p))
    max_chars = max(500, min(60000, int(max_chars or 20000)))
    office_text = _extract_office_text(p)
    if office_text is not None:
        text = office_text
    elif p.suffix.lower() == ".pdf" and shutil.which("pdftotext"):
        code, text = _run(["pdftotext", "-layout", str(p), "-"], timeout=30)
    else:
        raw = p.read_bytes()[:max(max_chars * 6, 500_000)]
        if b"\x00" in raw[:8192]:
            code, kind = _run(["file", "-b", str(p)])
            return {"path": _shown(p), "error": f"not a text file ({kind or 'binary'})"}
        text = raw.decode("utf-8", "replace")
    all_lines = text.splitlines()
    total_lines = len(all_lines)
    if start_line is not None or end_line is not None:
        s = max(1, int(start_line or 1))
        e = min(total_lines, int(end_line or (s + 299))) if total_lines else s
        sliced = [f"{idx}: {line}" for idx, line in enumerate(all_lines[s - 1:e], start=s)]
        joined = "\n".join(sliced)
        return {"path": _shown(p), "size_kb": round(p.stat().st_size / 1024), "content": joined[:max_chars],
                "start_line": s, "end_line": e, "total_lines": total_lines,
                "truncated": len(joined) > max_chars or e < total_lines}
    return {"path": _shown(p), "size_kb": round(p.stat().st_size / 1024), "content": text[:max_chars],
            "total_lines": total_lines, "truncated": len(text) > max_chars}


BACKUPS = ornis_consent.STATE / "ornis-backups"


def write_file(path, content, mode="create"):
    """create: a new file (never over another); overwrite: the old one is kept to undo; append: added at the end."""
    p = _home_path(path, must_exist=False)
    content = str(content or "")
    mode = mode if mode in ("create", "overwrite", "append") else "create"
    if p.is_dir():
        raise ValueError("that is a folder")
    if mode == "create" and p.exists():
        raise ValueError(f"{_shown(p)} exists already: say overwrite or append")
    backup = None
    if p.exists():
        BACKUPS.mkdir(parents=True, exist_ok=True)
        backup = BACKUPS / f"{int(time.time())}-{p.name}"
        shutil.copy2(p, backup)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a" if mode == "append" else "w", encoding="utf-8") as f:
        f.write(content)
    return {"written": _shown(p), "characters": len(content), "mode": mode,
            "_undo": {"type": "write", "path": str(p), "backup": str(backup) if backup else None}}


def edit_file(path, old_text, new_text, replace_all=False):
    """Surgical replacement inside an existing text file, keeping a backup for Undo and returning a unified diff."""
    import difflib
    p = _home_path(path)
    if p.is_dir():
        raise ValueError("that is a folder")
    old_text = str(old_text if old_text is not None else "")
    new_text = str(new_text if new_text is not None else "")
    if not old_text:
        raise ValueError("old_text must not be empty")
    current = p.read_text(encoding="utf-8")
    count = current.count(old_text)
    if count == 0:
        raise ValueError(f"old_text was not found in {_shown(p)}: read the target lines with computer_read_file first")
    if count > 1 and not replace_all:
        raise ValueError(f"old_text appears {count} times in {_shown(p)}: include more surrounding context or set replace_all=True")
    updated = current.replace(old_text, new_text) if replace_all else current.replace(old_text, new_text, 1)
    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = BACKUPS / f"{int(time.time())}-{p.name}"
    shutil.copy2(p, backup)
    p.write_text(updated, encoding="utf-8")
    diff = "".join(difflib.unified_diff(
        current.splitlines(True), updated.splitlines(True),
        fromfile=_shown(p), tofile=_shown(p), n=3
    ))[:12000]
    return {"edited": _shown(p), "replacements": count if replace_all else 1, "diff": diff,
            "_undo": {"type": "write", "path": str(p), "backup": str(backup)}}


def _trash_one(p: Path) -> bool:
    if shutil.which("gio"):
        return _run(["gio", "trash", str(p)], timeout=30)[0] == 0
    if system.MACOS:
        trash_dir = HOME / ".Trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        dest = trash_dir / p.name
        n = 2
        while dest.exists():
            dest = trash_dir / f"{p.stem} ({n}){p.suffix}"
            n += 1
        try:
            shutil.move(str(p), str(dest))
            return True
        except OSError:
            return False
    if system.WINDOWS:
        pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        method = "DeleteDirectory" if p.is_dir() else "DeleteFile"
        script = (f"Add-Type -AssemblyName Microsoft.VisualBasic; "
                  f"[Microsoft.VisualBasic.FileIO.FileSystem]::{method}({json.dumps(str(p))}, 'OnlyErrorDialogs', 'SendToRecycleBin')")
        return _run([pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script], timeout=30)[0] == 0
    # FreeDesktop Trash fallback on Linux without gio
    trash_base = Path(os.environ.get("XDG_DATA_HOME") or (HOME / ".local/share")) / "Trash"
    files_dir, info_dir = trash_base / "files", trash_base / "info"
    try:
        files_dir.mkdir(parents=True, exist_ok=True)
        info_dir.mkdir(parents=True, exist_ok=True)
        name = p.name
        n = 2
        while (files_dir / name).exists() or (info_dir / f"{name}.trashinfo").exists():
            name = f"{p.stem} ({n}){p.suffix}"
            n += 1
        from urllib.parse import quote
        now_str = time.strftime("%Y-%m-%dT%H:%M:%S")
        (info_dir / f"{name}.trashinfo").write_text(f"[Trash Info]\nPath={quote(str(p))}\nDeletionDate={now_str}\n", encoding="utf-8")
        shutil.move(str(p), str(files_dir / name))
        return True
    except OSError:
        return False


def trash_files(paths):
    done, problems = [], []
    for raw in paths or []:
        try:
            p = _home_path(raw)
            if p == HOME or p == HOME / "Orneos":
                raise ValueError("not this folder")
            ok = _trash_one(p)
            (done if ok else problems).append(_shown(p) if ok else f"{raw}: could not be put in the trash")
        except ValueError as error:
            problems.append(f"{raw}: {error}")
    return {"in_trash": done, "problems": problems, "note": "The user can restore them from the Trash (Corbeille)."}


# ---- applications running ---------------------------------------------------------------------------------------
# never closed by Ornis: the desktop itself
PROTECTED = {"plasmashell", "kwin_wayland", "kwin_x11", "kwin_wayland_wr", "systemd", "Xwayland", "plasmalogin", "sddm",
             "dbus-daemon", "dbus-broker", "pipewire", "wireplumber", "ksmserver", "kded6", "startplasma-wa", "polkit-kde-au",
             "xdg-desktop-por", "kactivitymanag", "baloo_file", "ksecretd", "kwalletd6", "gmenudbusmenupr", "at-spi-bus-laun",
             "gnome-shell", "mutter", "Finder", "WindowServer", "Dock", "SystemUIServer", "loginwindow", "launchd",
             "explorer", "explorer.exe", "dwm", "dwm.exe", "csrss.exe", "winlogon.exe", "svchost.exe", "lsass.exe", "services.exe"}


def _my_processes():
    """[(pid, name, command line, cpu seconds, memory kB)] of the user."""
    if system.WINDOWS:
        pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        code, out = _run([pwsh, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                          "Get-Process | Select-Object Id,ProcessName,CPU,WorkingSet64 | ConvertTo-Json -Compress"], timeout=10)
        try:
            rows = json.loads(out) if code == 0 and out else []
            if isinstance(rows, dict):
                rows = [rows]
            for r in rows:
                yield int(r.get("Id") or 0), str(r.get("ProcessName") or ""), str(r.get("ProcessName") or ""), float(r.get("CPU") or 0.0), int(r.get("WorkingSet64") or 0) // 1024
        except Exception:
            pass
        return
    if system.MACOS or not Path("/proc").is_dir():
        code, out = _run(["ps", "-axo", "pid=,cputime=,rss=,comm="], timeout=8)
        for line in out.splitlines():
            parts = line.strip().split(None, 3)
            if len(parts) < 4 or not parts[0].isdigit():
                continue
            try:
                tparts = [float(x) for x in parts[1].replace("-", ":").split(":")]
                cpu = sum(v * (60 ** i) for i, v in enumerate(reversed(tparts)))
                name = Path(parts[3]).name
                yield int(parts[0]), name, parts[3], cpu, int(parts[2])
            except ValueError:
                continue
        return
    uid = os.getuid()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            fields = (entry / "stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            name = (entry / "comm").read_text(encoding="utf-8").strip()
            args = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            rss = int(fields[21]) * os.sysconf("SC_PAGE_SIZE") // 1024
            cpu = (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
        except (OSError, IndexError, ValueError):
            continue
        yield int(entry.name), name, args, cpu, rss


def processes(sort="cpu", limit=12):
    """The user's applications by processor use (over one second) or memory, grouped by name."""
    before = {pid: cpu for pid, _n, _a, cpu, _r in _my_processes()}
    time.sleep(1)
    apps = {}
    for pid, name, _args, cpu, rss in _my_processes():
        a = apps.setdefault(name, {"name": name, "cpu_percent": 0.0, "memory_mb": 0, "processes": 0})
        a["cpu_percent"] = round(a["cpu_percent"] + 100 * max(0.0, cpu - before.get(pid, cpu)), 1)
        a["memory_mb"] += round(rss / 1024)
        a["processes"] += 1
    key = "memory_mb" if str(sort).startswith("mem") else "cpu_percent"
    rows = sorted(apps.values(), key=lambda a: (-a[key], -a["memory_mb"]))[:max(1, min(40, int(limit or 12)))]
    load = round(os.getloadavg()[0], 2) if hasattr(os, "getloadavg") else 0.0
    return {"sorted_by": key, "apps": rows, "load": load, "cpus": os.cpu_count()}


def quit_app(name):
    """Closes an application of the user (SIGTERM: it may still ask to save), never a part of the desktop."""
    words = _norm(name).replace("orneos", "").split()
    if not words:
        raise ValueError("say which application")
    targets = {}
    for pid, comm, args, _cpu, _rss in _my_processes():
        if comm in PROTECTED or pid in (os.getpid(), os.getppid()):
            continue
        if all(w in _norm(comm) for w in words) or (all(w in _norm(args) for w in words) and ("/app/" in args or system.MACOS or system.WINDOWS)):
            targets[pid] = comm
    if not targets and shutil.which("flatpak"):
        code, out = _run(["flatpak", "ps", "--columns=instance,application"])
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 2 and all(w in parts[1].lower() for w in words):
                _run(["flatpak", "kill", parts[1]])
                return {"closed": [parts[1]]}
    if not targets:
        return {"error": f"no running application called « {name} »"}
    for pid in targets:
        try:
            if system.WINDOWS:
                _run(["taskkill", "/PID", str(pid)])
            else:
                os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    return {"closed": sorted(set(targets.values())), "processes": len(targets)}


# ---- settings of the system ---------------------------------------------------------------------------------------
def setting(name, value):
    name, value = str(name or "").lower(), str(value if value is not None else "").strip()
    on = value.lower() in ("on", "true", "1", "yes", "oui", "ein", "an")
    if name == "wifi":
        if system.MACOS:
            code, _ = _run(["networksetup", "-setairportpower", "en0", "on" if on else "off"])
            return {"wifi": "on" if on else "off"} if code == 0 else {"error": "Wi-Fi could not be changed"}
        if system.WINDOWS:
            code, _ = _run(["netsh", "interface", "set", "interface", "Wi-Fi", "enabled" if on else "disabled"])
            return {"wifi": "on" if on else "off"} if code == 0 else {"error": "Wi-Fi could not be changed"}
        code, _ = _run(["nmcli", "radio", "wifi", "on" if on else "off"])
        return {"wifi": "on" if on else "off"} if code == 0 else {"error": "Wi-Fi could not be changed"}
    if name == "wifi_network":
        if not value:
            raise ValueError("say which network")
        if system.WINDOWS:
            code, _ = _run(["netsh", "wlan", "connect", f"name={value}"], timeout=30)
            return {"connected": value} if code == 0 else {"error": f"could not join « {value} »"}
        code, out = _run(["nmcli", "connection", "up", "id", value], timeout=40)
        if code != 0:
            code, out = _run(["nmcli", "device", "wifi", "connect", value], timeout=40)
        return {"connected": value} if code == 0 else {"error": f"could not join « {value} » (unknown network or a password is needed: open the network settings)"}
    if name == "bluetooth":
        if system.MACOS and shutil.which("blueutil"):
            code, _ = _run(["blueutil", "--power", "1" if on else "0"])
            return {"bluetooth": "on" if on else "off"} if code == 0 else {"error": "Bluetooth could not be changed"}
        code, _ = _run(["bluetoothctl", "power", "on" if on else "off"], timeout=10)
        if code != 0 and shutil.which("rfkill"):
            code, _ = _run(["rfkill", "unblock" if on else "block", "bluetooth"])
        return {"bluetooth": "on" if on else "off"} if code == 0 else {"error": "Bluetooth could not be changed"}
    if name == "power_profile":
        profile = {"eco": "power-saver", "economy": "power-saver", "saver": "power-saver", "balanced": "balanced",
                   "performance": "performance"}.get(value.lower(), value.lower())
        code, _ = _run(["powerprofilesctl", "set", profile])
        return {"power_profile": profile} if code == 0 else {"error": "use power-saver, balanced or performance"}
    return {"error": "settings: wifi, wifi_network, bluetooth, power_profile"}


# ---- screenshot and visual capture ---------------------------------------------------------------------------------
def screenshot(target="screen", delay_seconds=0):
    """Captures the active screen or window to a PNG file (and returns optional local OCR text if tesseract is installed)."""
    target = str(target or "screen").strip().lower()
    if target not in ("screen", "window"):
        target = "screen"
    try:
        delay = max(0, min(10, int(delay_seconds or 0)))
    except (TypeError, ValueError):
        delay = 0
    if delay:
        time.sleep(delay)
    out_dir = Path(os.environ.get("XDG_CACHE_HOME") or (HOME / ".cache")) / "orneos" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in sorted(out_dir.glob("ornis-*.png"))[:-25]:
        try:
            old.unlink()
        except OSError:
            pass
    out_path = out_dir / f"ornis-{int(time.time() * 1000)}.png"
    captured = False
    if system.MACOS and shutil.which("screencapture"):
        flag = ["-x", "-o"] if target == "window" else ["-x"]
        code, _ = _run(["screencapture", *flag, str(out_path)], timeout=15)
        captured = code == 0 and out_path.is_file()
    elif system.WINDOWS:
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
            "$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
            "$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; "
            "$g = [System.Drawing.Graphics]::FromImage($bmp); "
            "$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); "
            f"$bmp.Save({json.dumps(str(out_path))}, [System.Drawing.Imaging.ImageFormat]::Png)"
        )
        code, _ = _run(["powershell", "-NoProfile", "-Command", ps], timeout=15)
        captured = code == 0 and out_path.is_file()
    else:
        cmds = []
        if shutil.which("spectacle"):
            cmds.append(["spectacle", "-b", "-n", "-a" if target == "window" else "-f", "-o", str(out_path)])
        if shutil.which("grim"):
            cmds.append(["grim", str(out_path)])
        if shutil.which("gnome-screenshot"):
            cmds.append(["gnome-screenshot", *(["-w"] if target == "window" else []), "-f", str(out_path)])
        if shutil.which("scrot"):
            cmds.append(["scrot", *(["-u"] if target == "window" else []), str(out_path)])
        if shutil.which("import"):
            cmds.append(["import", "-window", "root", str(out_path)])
        for cmd in cmds:
            code, _ = _run(cmd, timeout=15)
            if code == 0 and out_path.is_file() and out_path.stat().st_size > 0:
                captured = True
                break
    if not captured:
        try:
            from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
            app = QGuiApplication.instance()
            screen = app.primaryScreen() if app else None
            if screen is not None:
                pix = screen.grabWindow(0)
                if not pix.isNull() and pix.save(str(out_path), "PNG"):
                    captured = True
        except Exception:  # noqa: BLE001
            pass
    if not captured or not out_path.is_file():
        return {"error": "could not capture the screen on this system"}
    res = {"path": str(out_path), "name": out_path.name, "size": out_path.stat().st_size, "target": target}
    if shutil.which("tesseract"):
        code, ocr = _run(["tesseract", str(out_path), "stdout", "--oem", "1", "-l", "fra+eng"], timeout=15)
        if code != 0 or not ocr.strip():
            code, ocr = _run(["tesseract", str(out_path), "stdout"], timeout=15)
        if code == 0 and ocr.strip():
            res["ocr_text"] = ocr.strip()[:8000]
    return res


# ---- terminal and applications ------------------------------------------------------------------------------------
def run_command(command, cwd="", wait=25, on_output=None):
    try:
        where = _home_path(cwd or "")
    except ValueError:
        where = _default_root()
    return ornis_shell.start(command, str(where), wait=max(1, min(55, float(wait or 25))), on_output=on_output)


def command_status(job, wait=30, stop=False, on_output=None):
    return ornis_shell.stop(job) if stop else ornis_shell.status(job, max(0, min(55, float(wait or 0))), on_output=on_output)


ACTIONS = {
    "extensions": lambda a: ornis_extensions.catalogue(),
    "skill_read": lambda a: ornis_extensions.read_skill(a.get("name"), a.get("file")),
    "mcp_tools": lambda a: ornis_extensions.invoke(a.get("server"), "tools/list", {}),
    "mcp_call": lambda a: ornis_extensions.invoke(a.get("server"), "tools/call", {"name": a.get("tool"), "arguments": a.get("arguments") or {}}),
    "skill_install": lambda a: ornis_extensions.install_skill(a.get("name"), a.get("content") or "", a.get("preset") or "", _lang()),
    "mcp_add": lambda a: ornis_extensions.add_mcp(a.get("name"), a.get("command") or "", a.get("args") or [], a.get("url") or "",
                                                  a.get("env") or {}, a.get("preset") or "", a.get("token") or ""),
    "extension_remove": lambda a: ornis_extensions.remove_extension(a.get("kind"), a.get("name")),
    "status": lambda a: status(),
    "open": lambda a: open_target(a.get("target")),
    "volume": lambda a: volume(a.get("level"), a.get("mute")),
    "brightness": lambda a: brightness(a.get("level", 50)),
    "appearance": lambda a: appearance(a.get("mode")),
    "clipboard": lambda a: clipboard(a.get("text")),
    "timer": lambda a: timer(a.get("minutes", 5), a.get("label")),
    "lock": lambda a: lock(),
    "power": lambda a: power(a.get("action")),
    "find_files": lambda a: find_files(a.get("query"), a.get("folder", ""), a.get("limit", 20)),
    "grep_files": lambda a: grep_files(a.get("pattern"), a.get("folder", ""), a.get("glob", ""), a.get("limit", 60), bool(a.get("case_sensitive"))),
    "move_files": lambda a: move_files(a.get("paths") or [], a.get("destination")),
    "create_folder": lambda a: create_folder(a.get("path")),
    "list_folder": lambda a: list_folder(a.get("path") or "", bool(a.get("hidden")), a.get("limit", 100)),
    "read_file": lambda a: read_file(a.get("path"), a.get("max_chars", 20000), a.get("start_line"), a.get("end_line")),
    "write_file": lambda a: write_file(a.get("path"), a.get("content"), a.get("mode") or "create"),
    "edit_file": lambda a: edit_file(
        a.get("path"),
        a.get("old_string") if a.get("old_string") is not None else a.get("old_text"),
        a.get("new_string") if a.get("new_string") is not None else a.get("new_text"),
        bool(a.get("replace_all")),
    ),
    "trash_files": lambda a: trash_files(a.get("paths") or []),
    "processes": lambda a: processes(a.get("sort") or "cpu", a.get("limit", 12)),
    "quit_app": lambda a: quit_app(a.get("name")),
    "setting": lambda a: setting(a.get("name"), a.get("value")),
    "find_app": lambda a: ornis_apps.find(a.get("query")),
    "install_app": lambda a: ornis_apps.install(a.get("source"), a.get("app_id")),
    "remove_app": lambda a: ornis_apps.remove(a.get("source"), a.get("app_id")),
    "run_command": lambda a: run_command(a.get("command"), a.get("cwd") or "", a.get("wait", 25), a.get("_on_output")),
    "command_status": lambda a: command_status(a.get("job"), a.get("wait", 30), bool(a.get("stop")), a.get("_on_output")),
    "open_terminal": lambda a: ornis_shell.in_terminal(a.get("command") or "", a.get("cwd") or str(_default_root())),
    "screenshot": lambda a: screenshot(a.get("target") or "screen", a.get("delay_seconds", 0)),
}
# how much each action can change (ornis_consent): the commands are read one by one (ornis_shell.classify)
LEVEL = {
    "extensions": "info", "skill_read": "info", "mcp_tools": "change", "mcp_call": "change",
    "skill_install": "change", "mcp_add": "change", "extension_remove": "change",
    "status": "info", "find_files": "info", "grep_files": "info", "list_folder": "info", "read_file": "info", "processes": "info",
    "find_app": "info", "command_status": "info",
    "open": "light", "volume": "light", "brightness": "light", "appearance": "light", "clipboard": "light",
    "timer": "light", "lock": "light", "screenshot": "light",
    "move_files": "change", "create_folder": "change", "write_file": "change", "edit_file": "change", "trash_files": "change",
    "quit_app": "change", "setting": "change", "install_app": "change", "remove_app": "change",
    "power": "admin",
}


# ---- words ----------------------------------------------------------------------------------------------------------
WORDS = {
    "fr": {"title": "Ornis veut agir sur cet ordinateur", "allow": "Autoriser", "always": "Toujours autoriser", "deny": "Refuser",
           "status": "Lire l'état de l'ordinateur (batterie, disque, réseau)", "open": "Ouvrir « {target} »",
           "volume": "Régler le son", "brightness": "Régler la luminosité à {level} %", "appearance": "Passer en apparence {mode}",
           "clipboard": "Copier un texte dans le presse-papiers", "timer": "Minuteur de {minutes} min : {label}",
           "lock": "Verrouiller l'écran", "power": "{action} l'ordinateur", "find_files": "Chercher des fichiers : « {query} »",
           "grep_files": "Chercher « {pattern} » dans les fichiers",
           "move_files": "Déplacer {count} élément(s) vers {destination}", "create_folder": "Créer le dossier {path}",
           "list_folder": "Lister le dossier {path}", "read_file": "Lire le fichier {path}",
           "write_file": "Écrire dans le fichier {path}", "edit_file": "Modifier le fichier {path}",
           "trash_files": "Mettre {count} élément(s) à la corbeille",
           "processes": "Voir les applications qui tournent", "quit_app": "Fermer « {name} »",
           "setting": "Réglage : {name} → {value}", "find_app": "Chercher l'application « {query} »",
           "install_app": "Installer {app_id}", "remove_app": "Désinstaller {app_id}",
           "skill_install": "Installer la compétence « {name}{preset} »", "mcp_add": "Ajouter le serveur MCP « {name}{preset} »",
           "extension_remove": "Retirer « {name} » ({kind})",
           "run_command": "Exécuter une commande", "command_status": "Suivre une commande en cours",
           "open_terminal": "Ouvrir un terminal", "screenshot": "Capturer l'écran",
           "sleep": "Mettre en veille", "restart": "Redémarrer", "shutdown": "Éteindre", "logout": "Fermer la session de",
           "dark": "sombre", "light": "claire", "auto": "automatique (claire le jour, sombre la nuit)", "flatpak": "Flathub", "rpm": "paquet système",
           "ran": "Ornis a agi sur l'ordinateur", "blocked": "Ornis n'exécute jamais cela"},
    "en": {"title": "Ornis wants to act on this computer", "allow": "Allow", "always": "Always allow", "deny": "Deny",
           "status": "Read the computer's state (battery, disk, network)", "open": "Open “{target}”",
           "volume": "Change the sound", "brightness": "Set the brightness to {level} %", "appearance": "Switch to the {mode} appearance",
           "clipboard": "Copy a text to the clipboard", "timer": "{minutes} min timer: {label}",
           "lock": "Lock the screen", "power": "{action} the computer", "find_files": "Search files: “{query}”",
           "grep_files": "Search “{pattern}” inside files",
           "move_files": "Move {count} item(s) to {destination}", "create_folder": "Create the folder {path}",
           "list_folder": "List the folder {path}", "read_file": "Read the file {path}",
           "write_file": "Write to the file {path}", "edit_file": "Edit the file {path}",
           "trash_files": "Move {count} item(s) to the trash",
           "processes": "See the running applications", "quit_app": "Quit “{name}”",
           "setting": "Setting: {name} → {value}", "find_app": "Look for the app “{query}”",
           "install_app": "Install {app_id}", "remove_app": "Uninstall {app_id}",
           "skill_install": "Install the skill “{name}{preset}”", "mcp_add": "Add the MCP server “{name}{preset}”",
           "extension_remove": "Remove “{name}” ({kind})",
           "run_command": "Run a command", "command_status": "Follow a running command", "open_terminal": "Open a terminal",
           "screenshot": "Take a screenshot",
           "sleep": "Put to sleep", "restart": "Restart", "shutdown": "Shut down", "logout": "Log out of",
           "dark": "dark", "light": "light", "auto": "automatic (light by day, dark at night)", "flatpak": "Flathub", "rpm": "system package",
           "ran": "Ornis acted on the computer", "blocked": "Ornis never runs this"},
    "de": {"title": "Ornis möchte auf diesem Computer handeln", "allow": "Erlauben", "always": "Immer erlauben", "deny": "Ablehnen",
           "status": "Zustand des Computers lesen (Akku, Speicher, Netzwerk)", "open": "„{target}“ öffnen",
           "volume": "Ton einstellen", "brightness": "Helligkeit auf {level} % setzen", "appearance": "Zum Erscheinungsbild {mode} wechseln",
           "clipboard": "Text in die Zwischenablage kopieren", "timer": "Timer {minutes} Min.: {label}",
           "lock": "Bildschirm sperren", "power": "Computer: {action}", "find_files": "Dateien suchen: „{query}“",
           "grep_files": "„{pattern}“ in Dateien suchen",
           "move_files": "{count} Element(e) nach {destination} verschieben", "create_folder": "Ordner {path} erstellen",
           "list_folder": "Ordner {path} auflisten", "read_file": "Datei {path} lesen",
           "write_file": "In die Datei {path} schreiben", "edit_file": "Datei {path} bearbeiten",
           "trash_files": "{count} Element(e) in den Papierkorb",
           "processes": "Laufende Anwendungen ansehen", "quit_app": "„{name}“ beenden",
           "setting": "Einstellung: {name} → {value}", "find_app": "App „{query}“ suchen",
           "install_app": "{app_id} installieren", "remove_app": "{app_id} deinstallieren",
           "skill_install": "Fähigkeit „{name}{preset}“ installieren", "mcp_add": "MCP-Server „{name}{preset}“ hinzufügen",
           "extension_remove": "„{name}“ entfernen ({kind})",
           "run_command": "Einen Befehl ausführen", "command_status": "Laufenden Befehl verfolgen",
           "open_terminal": "Ein Terminal öffnen", "screenshot": "Bildschirmfoto aufnehmen",
           "sleep": "Ruhezustand", "restart": "Neu starten", "shutdown": "Herunterfahren", "logout": "Abmelden",
           "dark": "dunkel", "light": "hell", "auto": "automatische (tagsüber hell, nachts dunkel)", "flatpak": "Flathub", "rpm": "Systempaket",
           "ran": "Ornis hat auf dem Computer gehandelt", "blocked": "Ornis führt das nie aus"},
}
DENIED = "The user refused this action on the computer. Do not retry it unless they ask."
TIMEOUT = "The user did not answer on the computer within 90 seconds: nothing was done. Ask them whether to try again."
BLOCKED = ("Refused on the computer, in every mode: this command could destroy the system or the user's files. "
           "Do not try another way; if the user really wants it, they can type it themselves in a terminal.")


def _lang():
    return (os.environ.get("LANG") or "fr")[:2]


def _words():
    return WORDS.get(_lang(), WORDS["en"])


def describe(action, args):
    w = _words()
    args = args if isinstance(args, dict) else {}
    values = {k: str(v)[:80] for k, v in args.items() if not isinstance(v, (list, dict))}
    values["count"] = len(args.get("paths") or [])
    values["action"] = w.get(str(args.get("action")), str(args.get("action")))
    values["mode"] = w.get(str(args.get("mode")), str(args.get("mode")))
    if action == "install_app" or action == "remove_app":
        values["app_id"] = f"{str(args.get('name') or '').strip()[:60] or args.get('app_id')} ({w.get(str(args.get('source')), args.get('source'))})"
    if action in ("skill_install", "mcp_add"):     # a preset is named after itself
        values["name"], values["preset"] = str(args.get("name") or args.get("preset") or "")[:64], ""
    text = w.get(action, action)
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    if action in ("move_files", "trash_files"):
        text += "\n" + "\n".join(str(p) for p in (args.get("paths") or [])[:6])
    return re.sub(r"\{\w+\}", "", text)


def request_for(action, args):
    """What the user is asked about: {action, level, sensitive, blocked, can_always, rule, title, summary, command?,
    cwd?, reason, source?, in_workspace?}."""
    args = args if isinstance(args, dict) else {}
    level = LEVEL.get(action, "change")
    req = {"action": action, "level": level, "sensitive": False, "blocked": "", "reason": str(args.get("reason") or "")[:300],
           "title": _words()["title"], "summary": describe(action, args), "lang": _lang()}
    paths = [args.get(k) for k in ("path", "destination", "folder", "cwd") if args.get(k)] + list(args.get("paths") or [])
    req["sensitive"] = any(ornis_consent.sensitive(os.path.expanduser(str(p)) if str(p).startswith("~") else str(p))
                           for p in paths) or (action in ("find_files", "grep_files") and ornis_consent.sensitive(str(args.get("folder") or "")))
    resolved_paths = []
    for p in paths + ([args.get("target")] if action == "open" else []):
        if not p:
            continue
        resolved = Path(str(p)).expanduser()
        resolved = (resolved if resolved.is_absolute() else _default_root() / resolved).resolve()
        resolved_paths.append(resolved)
        if (resolved != HOME and HOME not in resolved.parents) or ornis_consent.sensitive(str(resolved)):
            req["sensitive"] = True
    if resolved_paths and all(ornis_consent.in_workspace(str(rp)) for rp in resolved_paths):
        req["in_workspace"] = True
    if action == "screenshot":
        # Capturing the screen can expose private windows, so ask unless explicitly allowed by rule
        req["sensitive"] = True
    if action in ("mcp_tools", "mcp_call"):
        req["summary"] = ornis_extensions.describe(args.get("server"), args.get("tool"), args.get("arguments"))
        req["sensitive"] = True  # third-party code is never silently trusted through its annotations
    if action in ("skill_install", "mcp_add", "extension_remove"):
        # what Ornis installs is shown in full, and always asked: a skill guides it, a server runs code here
        req["preview"] = ornis_extensions.preview(action, args)
        req["sensitive"] = True
    if action == "write_file":
        import difflib
        raw = Path(str(args.get("path") or "")).expanduser()
        path = (raw if raw.is_absolute() else _default_root() / raw).resolve()
        try:
            old = path.read_text(encoding="utf-8") if path.is_file() and path.stat().st_size <= 200000 else ""
            new = str(args.get("content") or "")
            if args.get("mode") == "append":
                new = old + new
            req["preview"] = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=str(path), tofile=str(path)))[:20000]
        except (OSError, UnicodeError):
            pass
    if action == "edit_file":
        import difflib
        raw = Path(str(args.get("path") or "")).expanduser()
        path = (raw if raw.is_absolute() else _default_root() / raw).resolve()
        try:
            old = path.read_text(encoding="utf-8") if path.is_file() and path.stat().st_size <= 400000 else ""
            old_s = str(args.get("old_string") if args.get("old_string") is not None else (args.get("old_text") or ""))
            new_s = str(args.get("new_string") if args.get("new_string") is not None else (args.get("new_text") or ""))
            if old and old_s and old_s in old:
                new = old.replace(old_s, new_s) if args.get("replace_all") else old.replace(old_s, new_s, 1)
                req["preview"] = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=str(path), tofile=str(path)))[:20000]
        except (OSError, UnicodeError):
            pass
    if action in ("run_command", "open_terminal") and (args.get("command") or action == "run_command"):
        info = ornis_shell.classify(args.get("command") or "")
        cwd_val = str(args.get("cwd") or str(_default_root()))
        req.update(level=info["level"] if action == "run_command" else max(info["level"], "light", key=ornis_consent.LEVELS.index),
                   blocked=info["blocked"], sensitive=req["sensitive"] or info["sensitive"],
                   command=str(args.get("command") or ""), cwd=cwd_val)
        req["rule"] = ornis_shell.rule_for(req["command"])
        req["can_always"] = bool(req["rule"]) and not req["sensitive"]
        return req
    if action == "open_terminal":
        req["level"] = "light"
    if action in ("install_app", "remove_app"):
        req["source"] = str(args.get("source") or "")
        if req["source"] == "rpm":
            req["level"] = "admin"
    if action == "command_status" and args.get("stop"):
        req["level"] = "light"
    req["rule"] = action
    req["can_always"] = (req["level"] in ("info", "light") and not req["sensitive"]) or action == "screenshot"
    return req


# ---- undo -----------------------------------------------------------------------------------------------------------
def undoable_entries(limit=10):
    """Returns recent journal entries that can still be undone, newest first."""
    out = []
    for e in ornis_consent.journal(ornis_consent.JOURNAL_KEEP):
        if isinstance(e.get("undo"), dict) and not e.get("undone") and e.get("outcome", "ok") == "ok":
            u = e["undo"]
            path_str = ""
            if u.get("path"):
                path_str = str(u["path"])
            elif u.get("pairs"):
                path_str = str(u["pairs"][0][0])
            target = Path(path_str).name if path_str else ""
            out.append({
                "id": e.get("id"),
                "summary": e.get("summary") or "",
                "target": target,
                "name": target,
                "path": path_str,
                "time": e.get("time") or e.get("at") or 0,
            })
            if len(out) >= limit:
                break
    return out


def undo_latest():
    """Undoes the most recent undoable local file change and returns {ok, id, summary, target, restored} or raises ValueError."""
    entries = undoable_entries(1)
    if not entries:
        raise ValueError("nothing to undo")
    top = entries[0]
    res = undo(top["id"])
    if not res.get("ok"):
        raise ValueError(res.get("error") or "undo failed")
    res.update(id=top["id"], summary=top["summary"], target=top["target"], name=top["name"], restored=top["path"])
    return res


def undo(entry_id):
    """Undoes a journal entry (moves back, restores a file, removes a new empty folder): {ok} or {error}."""
    entry = next((e for e in ornis_consent.journal(ornis_consent.JOURNAL_KEEP) if e.get("id") == entry_id), None)
    if not entry or not isinstance(entry.get("undo"), dict) or entry.get("undone"):
        return {"error": "nothing to undo"}
    u = entry["undo"]
    try:
        if u["type"] == "move":
            for now, before in u["pairs"]:
                if Path(now).exists() and not Path(before).exists():
                    Path(before).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(now, before)
        elif u["type"] == "write":
            if u.get("backup") and Path(u["backup"]).exists():
                shutil.copy2(u["backup"], u["path"])
            elif Path(u["path"]).exists():
                Path(u["path"]).unlink()
        elif u["type"] == "mkdir":
            Path(u["path"]).rmdir()
    except OSError as error:
        return {"error": str(error)}
    ornis_consent.finish(entry_id, undone=True)
    return {"ok": True}


# ---- running a request ------------------------------------------------------------------------------------------------
def _outcome(result):
    if isinstance(result, dict) and ("error" in result or result.get("problems")):
        return "error"
    if isinstance(result, dict) and result.get("done") is False:
        return "running"
    return "ok"


def run(action, args, on_state=None, asker=None):
    """Runs one request of Ornis, after the user's yes when the mode asks for it; always an answer for the agent.
    on_state(phase, request): « asking » while the user is asked, « running » while it runs. asker(request): the app
    asks itself (above its message box) instead of the window, see ornis_consent.ask."""
    action = str(action)
    args = dict(args) if isinstance(args, dict) else {}
    fn = ACTIONS.get(action)

    if fn is None:
        return {"error": f"unknown action {action}"}
    if action == "command_status":
        # following (or stopping) a command the user already allowed: never asked again, not journaled again
        if on_state and not args.get("stop"):
            req_status = request_for(action, args)
            args["_on_output"] = lambda job, tail, sec: on_state(
                "running", dict(req_status, job=job, output=tail, seconds=sec)
            )
        try:
            return fn(args)
        except ValueError as error:
            return {"error": str(error)}
    req = request_for(action, args)
    mode = ornis_consent.settings()["mode"]
    entry = {"action": action, "summary": req["summary"], "level": req["level"], "mode": mode,
             "command": req.get("command"), "reason": req["reason"]}
    decision = ornis_consent.decide(req)
    if decision == "block":
        ornis_consent.log(dict(entry, decision="blocked", outcome="refused"))
        return {"refused": BLOCKED}
    if decision == "ask":
        if on_state:
            on_state("asking", req)
        answer = ornis_consent.ask(req, _words(), asker)
        if answer.get("answer") not in ("allow", "always"):
            ornis_consent.log(dict(entry, decision="timeout" if answer.get("timeout") else "denied", outcome="refused"))
            return {"refused": TIMEOUT if answer.get("timeout") else DENIED}
        edited = str(answer.get("command") or "").strip()
        if req.get("command") is not None and edited and edited != req["command"]:
            # the user changed the command: it is read again, and Ornis learns what ran
            info = ornis_shell.classify(edited)
            if info["blocked"]:
                ornis_consent.log(dict(entry, command=edited, decision="blocked"))
                return {"refused": BLOCKED}
            args["command"] = edited
            entry["command"] = edited
            entry["edited"] = True
        if answer.get("answer") == "always" and req.get("can_always"):
            ornis_consent.add_rule("command" if req.get("command") is not None else "action", req["rule"],
                                   req["rule"] if req.get("command") is not None else req["summary"].split("\n")[0],
                                   req["level"])
        entry["decision"] = "allowed" if answer.get("answer") == "allow" else "always"
    else:
        entry["decision"] = "auto" if mode != "ask" else "rule"
        if req["level"] in ("change", "admin"):
            ornis_consent.tell(_words()["ran"], (entry.get("command") or req["summary"])[:200])
    entry_id = ornis_consent.log(entry)
    if on_state:
        on_state("running", req)
        if action == "run_command":
            args["_on_output"] = lambda job, tail, sec: on_state(
                "running", dict(req, job=job, output=tail, seconds=sec)
            )
    outside = OUTSIDE_APPROVED.set(bool(req["sensitive"]))
    try:
        result = fn(args)
    except (ValueError, TypeError) as error:
        result = {"error": str(error)}
    except Exception as error:  # noqa: BLE001 - always an answer, never a hung agent
        result = {"error": f"failed: {error.__class__.__name__}"}
    OUTSIDE_APPROVED.reset(outside)
    undo_info = result.pop("_undo", None) if isinstance(result, dict) else None
    job = result.get("job") if isinstance(result, dict) else None
    ornis_consent.finish(entry_id, outcome=_outcome(result), undo=undo_info, job=job)
    if entry.get("edited") and isinstance(result, dict):
        result["note_command_edited_by_user"] = args["command"]
    return result
