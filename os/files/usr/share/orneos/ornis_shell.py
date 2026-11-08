"""Ornis's terminal on Orneos OS: commands the user allowed (ornis_consent), run as the user, without a terminal.

`classify` reads a command before anything runs: its level (info: only looks; change; admin: root or the whole
system), whether it names a secret, and whether it must never run (wiping a disk, the home folder or the system).
`start` runs it as a job: its output goes to a file, it keeps going when Ornis stops waiting (an installation of
ten minutes), and `status` / `stop` follow it from any process: the Ornis app, the top-bar applet's helper or the
settings window, which lists the jobs with « Arrêter ».

No terminal: a command that waits for an answer gets nothing on its input (use -y). `sudo` asks for the password
in a window (ksshaskpass); `pkexec` in the system's window.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import signal
import shutil
import subprocess
import time
import uuid
import system
from pathlib import Path

from ornis_consent import STATE, sensitive

JOBS = STATE / "ornis-jobs"
KEEP = 40
OUTPUT_MAX = 12000
MAX_HOURS = 3
HOME = Path.home()

# Commands that only look. The first word decides; for some, the second too (READ_SUB) or an option changes it (WRITE_OPT).
READ = {
    "ls", "cat", "head", "tail", "grep", "egrep", "fgrep", "rg", "find", "fd", "df", "du", "free", "uname", "ps", "pgrep",
    "whoami", "id", "groups", "date", "cal", "uptime", "lsblk", "lscpu", "lspci", "lsusb", "lsmod", "lshw", "which", "type",
    "echo", "printf", "pwd", "wc", "sort", "uniq", "cut", "tr", "column", "file", "stat", "env", "printenv", "hostname",
    "sensors", "fastfetch", "neofetch", "inxi", "upower", "tree", "realpath", "readlink", "basename", "dirname", "md5sum",
    "sha1sum", "sha256sum", "diff", "cmp", "test", "true", "false", "seq", "lsof", "ss", "dig", "host", "nslookup", "ping",
    "journalctl", "dmesg", "glxinfo", "vulkaninfo", "nvidia-smi", "xdpyinfo", "wpctl", "pactl", "locale", "getent",
    "awk", "sed", "jq", "less", "more", "top", "htop", "nproc", "arch", "w", "who", "last", "lslogins", "findmnt", "blkid",
    "smartctl", "efibootmgr", "mokutil", "bootctl", "kscreen-doctor", "pdftotext", "exiftool", "identify", "ffprobe",
    "nmcli", "systemctl", "rpm", "rpm-ostree", "flatpak", "git", "hostnamectl", "loginctl", "localectl", "timedatectl",
    "bluetoothctl", "toolbox", "podman", "fwupdmgr", "ip", "resolvectl", "powerprofilesctl", "xdg-mime", "kreadconfig6",
    "kreadconfig5", "gsettings", "dconf", "qdbus6", "qdbus", "busctl", "fc-list", "fc-match", "command", "sleep", "time",
    "python3", "bc", "factor", "numfmt", "uptime", "tac", "nl", "fold", "strings", "xxd", "od", "base64",
}
# for these, only the listed sub-commands look; the others change
READ_SUB = {
    "nmcli": {"general", "g", "device", "d", "connection", "c", "con", "radio", "r", "networking", "n", "monitor", "-t", "-f",
              "-p", "-g"},
    "systemctl": {"status", "list-units", "list-unit-files", "list-timers", "list-sockets", "is-active", "is-enabled",
                  "is-failed", "show", "cat", "--user", "--failed", "--no-pager", "-a", "--all", "--type"},
    "rpm": {"-q", "-qa", "-qi", "-ql", "-qf", "-qR", "--query", "-V", "--verify", "-qc", "-qd", "--changelog"},
    "rpm-ostree": {"status", "db", "search", "--version", "-h", "--help"},
    "flatpak": {"list", "search", "info", "remotes", "remote-ls", "history", "ps", "--version", "documents", "permissions",
                "permission-show", "remote-info"},
    "git": {"status", "log", "diff", "show", "branch", "remote", "blame", "shortlog", "describe", "rev-parse", "ls-files",
            "--version", "tag", "config"},
    "hostnamectl": {"status"}, "loginctl": {"list-sessions", "show-session", "session-status", "list-users", "show-user"},
    "localectl": {"status", "list-keymaps", "list-locales"}, "timedatectl": {"status", "show", "list-timezones"},
    "bluetoothctl": {"show", "devices", "info", "list", "paired-devices"},
    "toolbox": {"list"}, "podman": {"ps", "images", "info", "version", "inspect", "logs"},
    "fwupdmgr": {"get-devices", "get-updates", "get-history"}, "ip": {"a", "addr", "address", "r", "route", "link", "l", "-br",
                                                                         "-c", "-4", "-6", "neigh", "-j", "show"},
    "resolvectl": {"status", "query", "dns"}, "powerprofilesctl": {"get", "list"}, "xdg-mime": {"query"},
    "gsettings": {"get", "list-keys", "list-schemas", "list-recursively"}, "dconf": {"read", "list", "dump"},
    "efibootmgr": {"-v"}, "mokutil": {"--sb-state", "--list-enrolled"},
    "bootctl": {"status", "list"}, "python3": {"--version", "-V"},
    "smartctl": {"-a", "-H", "-i", "--all", "--health", "--info"}, "busctl": {"list", "status", "tree", "introspect", "get-property"},
    "winget": {"list", "search", "show", "--info", "--version", "-v"},
    "brew": {"list", "info", "search", "config", "doctor", "leaves", "outdated", "--version", "--prefix", "--cellar"},
}
PWSH_READ = {
    "get-childitem", "gci", "dir", "get-content", "gc", "type", "select-string", "sls", "get-process", "gps",
    "get-service", "gsv", "get-item", "gi", "get-itemproperty", "gp", "test-path", "measure-object", "select-object",
    "where-object", "sort-object", "format-table", "format-list", "out-string", "convertto-json", "convertfrom-json",
    "get-date", "get-location", "gl", "get-command", "gcm", "get-help", "get-computerinfo", "get-ciminstance",
    "get-wmiobject", "get-netipaddress", "get-netadapter", "get-volume", "get-psdrive", "systeminfo", "ipconfig",
    "tasklist", "where.exe", "winget", "brew", "sw_vers", "system_profiler", "vm_stat", "pmset", "diskutil",
}
PWSH_ADMIN = {
    "format-volume", "clear-disk", "initialize-disk", "diskpart", "set-executionpolicy", "new-service",
    "stop-service", "restart-computer", "stop-computer", "bcdedit", "reg", "reg.exe", "sc.exe", "netsh",
    "takeown", "icacls", "chkdsk", "sfc", "dism",
}
PWSH_NO_RULE = {
    "remove-item", "ri", "del", "erase", "rd", "rmdir", "move-item", "mi", "copy-item", "ci", "set-content", "sc",
    "add-content", "ac", "clear-content", "clc", "stop-process", "spps", "taskkill", "invoke-webrequest", "iwr",
    "invoke-restmethod", "irm", "invoke-expression", "iex", "start-process", "saps", "pwsh", "powershell",
    "powershell.exe", "cmd", "cmd.exe", "osascript",
}
# options that make a looking command write
WRITE_OPT = {
    "find": {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"},
    "sed": {"-i", "--in-place"}, "sort": {"-o", "--output"}, "git": {"-d", "-D", "--delete", "--set-upstream-to", "add",
                                                                     "rm", "set-url", "--add", "--unset"},
    "nmcli": {"up", "down", "delete", "modify", "add", "connect", "disconnect", "on", "off", "reload", "import", "edit"},
    "dconf": {"write", "reset", "load"}, "tree": {"-o"}, "kscreen-doctor": {"output."}, "efibootmgr": {"-c", "-B", "-o", "-n", "-a", "-A"},
    "journalctl": {"--vacuum-size", "--vacuum-time", "--vacuum-files", "--rotate", "--flush"},
    "bluetoothctl": {"power", "pair", "remove", "connect", "disconnect", "trust"}, "python3": {"-c"},
    "qdbus6": set(), "qdbus": set(), "busctl": {"call", "set-property"},
}
# a dbus call can do anything: they change, unless they only read a property
DBUS_READ = re.compile(r"\b(Get|GetAll|Introspect|org\.freedesktop\.DBus\.Properties\.Get)\b")
ADMIN = {"sudo", "pkexec", "su", "doas", "run0", "bootc", "ostree", "mount", "umount", "useradd", "userdel", "usermod",
         "passwd", "chpasswd", "groupadd", "visudo", "firewall-cmd", "setenforce", "grubby", "mkinitrd", "dracut",
         "modprobe", "rmmod", "insmod", "fdisk", "parted", "sfdisk", "gdisk", "cryptsetup", "lvcreate", "swapon", "swapoff",
         "dnf", "dnf5", "yum", "fwupdtool", "reboot", "poweroff", "shutdown", "halt", "systemd-sysext", "update-crypto-policies"}
ADMIN_SUB = {"rpm-ostree": {"install", "uninstall", "remove", "override", "reset", "rebase", "upgrade", "update", "deploy",
                            "rollback", "kargs", "initramfs", "initramfs-etc", "apply-live", "usroverlay", "cancel", "cleanup",
                            "refresh-md", "reload"},
             "rpm": {"-i", "-U", "-e", "--install", "--upgrade", "--erase", "-F", "--freshen"},
             "fwupdmgr": {"update", "install", "downgrade", "reinstall", "unlock"}, "flatpak": {"--system"},
             "hostnamectl": {"set-hostname", "hostname"}, "timedatectl": {"set-time", "set-timezone", "set-ntp"},
             "localectl": {"set-locale", "set-keymap", "set-x11-keymap"}}

# Never, whatever the mode: the user can still type it in a terminal. Targets of a recursive removal that would
# wipe the system, the home folder, or the Orneos folder (synced: the cloud would follow).
_HOMES = r"(?:~|\$HOME|\$\{HOME\}|" + re.escape(str(HOME)) + r")"
_ROOTS = (r"(?:/|/\*|/(?:usr|etc|var|boot|home|root|bin|sbin|lib|lib64|opt|sysroot|ostree)/?\*?|" + _HOMES +
          r"/?\*?|" + _HOMES + r"/(?:Orneos|Documents|Images|Pictures|Bureau|Desktop|Téléchargements|Downloads)/?\*?)")
BLOCKED = [
    ("wipe", re.compile(r"\brm\b(?=[^;&|]*\s-[a-zA-Z]*[rR])[^;&|]*\s[\"']?" + _ROOTS + r"[\"']?(?:\s|$|;|&|\|)")),
    ("wipe", re.compile(r"--no-preserve-root")),
    ("disk", re.compile(r"\b(mkfs(\.\w+)?|wipefs|blkdiscard|mkswap)\b")),
    ("disk", re.compile(r"\bdd\b[^;&|]*\bof=/dev/")),
    ("disk", re.compile(r"\b(shred|cat|cp|tee)\b[^;&|]*\s/dev/(sd|nvme|vd|hd|mmcblk|dm-)")),
    ("disk", re.compile(r">\s*/dev/(sd|nvme|vd|hd|mmcblk|dm-)")),
    ("bomb", re.compile(r":\s*\(\s*\)\s*\{[^}]*:\s*\|\s*:")),
    ("perms", re.compile(r"\bch(mod|own)\b[^;&|]*\s-[a-zA-Z]*R[^;&|]*\s[\"']?" + _ROOTS + r"[\"']?(?:\s|$)")),
    ("wipe", re.compile(r"\bfind\b[^;&|]*\s" + _ROOTS + r"\s[^;&|]*-delete")),
]
# never « always »: what removes, kills or rewrites files is asked each time
NO_RULE = {"rm", "rmdir", "shred", "truncate", "dd", "mv", "cp", "chmod", "chown", "chgrp", "kill", "pkill", "killall",
           "xargs", "bash", "sh", "zsh", "eval", "exec", "source", ".", "tee", "ln", "rsync", "scp", "ssh", "curl", "wget",
           "python3", "perl", "node", "find", "sed", "awk", "crontab", "at", "systemd-run", "flatpak-spawn", "env"}
REMOTE_SCRIPT = re.compile(r"\b(curl|wget)\b[^|;&]*\|\s*(sudo\s+)?(ba|z|da)?sh\b")


def _segments(command: str) -> list[list[str]] | None:
    """The simple commands of a line ([words…] each), or None when it cannot be read for sure."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
        lex.whitespace_split = True
        lex.commenters = ""
        tokens = list(lex)
    except ValueError:
        return None
    out, cur = [], []
    for tok in tokens:
        if tok and set(tok) <= set(";&|()"):
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        out.append(cur)
    return out


def _redirects_to_file(command: str) -> bool:
    """Writes into a file (> x, >> x, tee x), /dev/null and 2>&1 aside."""
    cleaned = re.sub(r"\d?>&\d|&?>{1,2}\s*/dev/null|\d>{1,2}\s*/dev/null", "", command)
    return bool(re.search(r"(^|[^<])>{1,2}", cleaned))


def _strip_env(words: list[str]) -> list[str]:
    """Without the variables set in front (LANG=C ls) nor a time / nice / env in front."""
    i = 0
    while i < len(words) and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[i]) or words[i] in ("nice", "ionice", "env", "time",
                                                                                                    "stdbuf", "timeout")):
        i += 1
        if i < len(words) and words[i - 1] in ("timeout",) and re.match(r"^\d", words[i]):
            i += 1
    return words[i:]


def _level(words: list[str]) -> str:
    words = _strip_env(words)
    if not words:
        return "info"
    head = os.path.basename(words[0])
    head_low = head.lower()
    args = words[1:]
    rest = set(args)
    rest_low = {a.lower() for a in args}
    sub = next((w for w in args if not w.startswith("-")), None)
    sub_low = sub.lower() if sub else None
    if head in ADMIN or head_low in PWSH_ADMIN or head_low in ("runas", "runas.exe", "gsudo", "gsudo.exe") or (head_low == "osascript" and "administrator privileges" in " ".join(args).lower()):
        return "admin"
    if head_low in ("start-process", "saps") and "-verb" in rest_low and "runas" in rest_low:
        return "admin"
    if head in ADMIN_SUB and (rest & ADMIN_SUB[head]):
        return "admin"
    if head == "systemctl" and "--user" not in rest and sub is not None and sub not in READ_SUB["systemctl"]:
        return "admin"
    if head == "ip" and rest & {"add", "del", "delete", "set", "flush", "change", "replace"}:
        return "admin"
    if head not in READ and head_low not in PWSH_READ:
        return "change"
    if head in WRITE_OPT and (rest & WRITE_OPT[head]
                              or any(w.startswith(o) for w in args for o in WRITE_OPT[head] if o.endswith("."))):
        return "change"
    if head in ("qdbus6", "qdbus") and len(args) > 2 and not DBUS_READ.search(" ".join(args)):
        return "change"
    if head == "awk" and re.search(r"system\s*\(|>|\|\s*\"", " ".join(args)):
        return "change"
    if head == "python3":
        return "info" if args and args[0] in READ_SUB["python3"] else "change"
    if head == "command":
        return "info" if rest & {"-v", "-V"} else "change"
    if head == "git" and sub == "config":
        return "info" if rest & {"--get", "-l", "--list", "--get-all"} else "change"
    if head_low == "diskutil" and sub_low not in (None, "list", "info", "apfs"):
        return "change"
    if head in READ_SUB and head not in ("nmcli", "ip") and sub is not None and sub not in READ_SUB[head]:
        return "change"
    if head_low in READ_SUB and head not in READ_SUB and sub_low is not None and sub_low not in READ_SUB[head_low]:
        return "change"
    return "info"


def classify(command: str) -> dict:
    """{level: info|change|admin, sensitive, blocked: reason or "", words: of a simple command (for « toujours »),
    simple: one command without chaining, redirection nor substitution}."""
    command = str(command or "").strip()
    out = {"level": "change", "sensitive": sensitive(command), "blocked": "", "words": [], "simple": False}
    for reason, pattern in BLOCKED:
        if pattern.search(command):
            out["blocked"] = reason
            out["level"] = "admin"
            return out
    if re.search(r"(?i)\b(format-volume|clear-disk|initialize-disk|diskpart|cipher\s+/w:|format\s+[a-z]:|(?:remove-item|ri|rd|rmdir|del|erase)\b[^;\n]*(?:[a-z]:[\\/]?(?:[\s'\"]|$)|\$env:userprofile|\$home|~[\\/]?[\s'\"]?$|c:[\\/]windows|c:[\\/]users(?:[\\/]?[\s'\"]|$)))", command):
        out.update(blocked="wipe", level="admin")
        return out
    segments = _segments(command)
    substitution = bool(re.search(r"\$\(|`|<\(|>\(", command))
    if segments is None or not segments:
        return out
    levels = [_level(s) for s in segments]
    rank = max(("info", "change", "admin").index(lv) for lv in levels)
    if substitution or _redirects_to_file(command):
        rank = max(rank, 1)
    if REMOTE_SCRIPT.search(command) or re.search(r"(?i)\b(invoke-webrequest|iwr|invoke-restmethod|irm|downloadstring|curl|wget)\b[^;\n]*\|\s*(invoke-expression|iex|pwsh|powershell)\b", command):
        rank = 2
        out["sensitive"] = True        # a script from the web, run as is: always asked, even in autonomous mode
    if re.search(r"(^|\s)(sudo|pkexec|su|doas|run0)(\s|$)", command) or re.search(r"(?i)\bstart-process\b[^;\n]*-verb\s+runas\b", command):
        rank = 2
    out["simple"] = len(segments) == 1 and not substitution and not _redirects_to_file(command)
    if out["simple"]:
        out["words"] = _strip_env(segments[0])
    out["level"] = ("info", "change", "admin")[max(1, rank)]
    out["read_only"] = rank == 0 and not substitution and not _redirects_to_file(command)
    return out


def outside(command: str, folder: str = "") -> bool:
    """Conservative path check for reusable approvals and sandbox retries."""
    for word in re.split(r"[\s\"'=;,|&]+", command):
        if not word or word in ("/dev/null", "/dev/stdout", "/dev/stderr") or word.startswith(("https://", "http://")):
            continue
        if word.startswith("~") or re.search(r"\$\{?HOME|\$env:|%USERPROFILE%", word, re.I) or ".." in word.replace("\\", "/").split("/"):
            return True
        if word.startswith("/") or re.match(r"^[a-z]:[\\/]", word, re.I) or (folder and not word.startswith("-") and ("/" in word or (Path(folder) / word).exists())):
            try:
                if not folder or not (Path(folder) / word).resolve().is_relative_to(Path(folder).resolve()):
                    return True
            except (OSError, ValueError):
                return True
    return False


def admin_execution(command: str, env: dict) -> tuple[str, str]:
    """Prepare an already approved admin call. Never read a password from stdin.
    Unsupported elevation is left to the user's terminal, without starting it detached.
    sudo -n fails authentication immediately but an authenticated command may run for hours.
    """
    if classify(command).get("level") != "admin":
        return command, ""
    info = classify(command)
    words = info.get("words") or []
    if os.name == "nt" or not info.get("simple") or not words or Path(words[0]).name != "sudo":
        return "", "terminal"
    # Only sudo's command form: options can override noninteractive/askpass semantics.
    if len(words) < 2 or words[1].startswith("-"):
        return "", "terminal"
    display = bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY") or system.MACOS)
    helper = next((shutil.which(n) for n in ("ksshaskpass", "ssh-askpass", "gnome-ssh-askpass") if shutil.which(n)), "") if display else ""
    if helper:
        env["SUDO_ASKPASS"] = helper
    else:
        env.pop("SUDO_ASKPASS", None)
    match = re.match(r"^\s*((?:/usr/bin/|/bin/)?sudo)\s+([^\s-][\s\S]*)$", command)
    if not match:
        return "", "terminal"
    return match[1] + (" -A -- " if helper else " -n -- ") + match[2], ""


def rule_for(command: str, folder: str = "") -> str:
    """What « Toujours autoriser » keeps for a simple command: its program, and its sub-command when it has one
    (« git status », « flatpak list », « ls »). Empty: no rule possible (chained commands, removals, kills…)."""
    info = classify(command)
    words = info["words"]
    if (folder and outside(command, folder)) or not words or info["blocked"] or info["sensitive"] or info["level"] == "admin":
        return ""
    head = os.path.basename(words[0])
    if head in NO_RULE or head.lower() in PWSH_NO_RULE:
        return ""
    return "exact: " + str(command).strip()


# ---- jobs ---------------------------------------------------------------------------------------------------------
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\r(?!\n)")
WRAPPER = r"""
sudo() { command sudo -A "$@"; }
export -f sudo 2>/dev/null
cd -- "$ORNIS_CWD" 2>/dev/null || cd
"""


def _dir(job: str) -> Path:
    if not re.match(r"^[a-f0-9]{8,32}$", str(job or "")):
        raise ValueError("unknown job")
    return JOBS / job


def _cleanup() -> None:
    try:
        jobs = sorted((p for p in JOBS.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for old in jobs[:-KEEP]:
        if (old / "exit").exists():
            shutil.rmtree(old, ignore_errors=True)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # a finished child of this process that nobody waited for is a zombie: not alive
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        return state != "Z"
    except (OSError, IndexError):
        return True


def start(command: str, cwd: str = "~", wait: float = 25, label: str = "", kind: str = "command", on_output=None) -> dict:
    """Runs a command (already allowed) in the background; waits up to `wait` seconds for it to end."""
    from ornis_process import start as native_start
    return native_start(command, cwd, wait, label, kind, on_output=on_output)


def _read_output(folder: Path) -> tuple[str, int]:
    try:
        raw = (folder / "output").read_bytes()
    except OSError:
        return "", 0
    text = _ANSI.sub("", raw.decode("utf-8", "replace"))
    size = len(text)
    if size > OUTPUT_MAX:
        head = OUTPUT_MAX // 4
        text = text[:head] + f"\n[… {size - OUTPUT_MAX} characters skipped …]\n" + text[-(OUTPUT_MAX - head):]
    return text.strip(), size


def status(job: str, wait: float = 0, _proc=None, on_output=None) -> dict:
    """{job, label, done, exit_code, stopped, output, seconds}: waits up to `wait` s for the end."""
    from ornis_process import status as native_status
    return native_status(job, wait, on_output=on_output)


def stop(job: str) -> dict:
    from ornis_process import stop as native_stop
    return native_stop(job)


def jobs(limit: int = 20) -> list[dict]:
    """The latest jobs, newest first, without their whole output (the last lines)."""
    try:
        folders = sorted((p for p in JOBS.iterdir() if p.is_dir()), key=lambda p: -p.stat().st_mtime)[:limit]
    except OSError:
        return []
    out = []
    for folder in folders:
        try:
            row = status(folder.name)
        except ValueError:
            continue
        if "error" in row:
            continue
        row["output"] = "\n".join(row["output"].splitlines()[-40:])
        out.append(row)
    return out


def in_terminal(command: str = "", cwd: str = "~") -> dict:
    """Opens a terminal window in a folder, optionally running a command there: the user sees it and can answer it."""
    where = Path(os.path.expanduser(str(cwd or "~")))
    if not where.is_absolute():
        where = HOME / where
    work_dir = str(where) if where.is_dir() else str(HOME)
    shown_dir = str(where).replace(str(HOME), "~", 1)
    if system.MACOS:
        if command:
            script = f'tell application "Terminal"\nactivate\ndo script {json.dumps(f"cd {shlex.quote(work_dir)} && {command}")}\nend tell'
            subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        else:
            subprocess.Popen(["open", "-a", "Terminal", work_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {"opened": "terminal", "command": command, "folder": shown_dir}
    if system.WINDOWS:
        wt = shutil.which("wt") or shutil.which("wt.exe")
        pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell.exe"
        if wt:
            cmd = [wt, "-d", work_dir]
            if command:
                cmd += [pwsh, "-NoExit", "-Command", command]
        else:
            cmd = ["cmd.exe", "/c", "start", "", "/D", work_dir, pwsh]
            if command:
                cmd += ["-NoExit", "-Command", command]
        subprocess.Popen(cmd, cwd=work_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"opened": "terminal", "command": command, "folder": shown_dir}
    term = (shutil.which("konsole") or shutil.which("ptyxis") or shutil.which("kgx")
            or shutil.which("gnome-terminal") or shutil.which("xfce4-terminal")
            or shutil.which("alacritty") or shutil.which("kitty") or shutil.which("xterm"))
    if not term:
        return {"error": "no terminal application on this computer"}
    base = os.path.basename(term)
    cmd = [term]
    if base == "konsole":
        cmd += ["--workdir", work_dir]
        if command:
            cmd += ["--hold", "-e", "bash", "-c", command]
    elif base == "gnome-terminal":
        cmd += [f"--working-directory={work_dir}"]
        if command:
            cmd += ["--", "bash", "-c", command + "; exec bash"]
    elif base in ("ptyxis", "kgx"):
        cmd += [f"--working-directory={work_dir}"]
        if command:
            cmd += ["-e", f"bash -c {shlex.quote(command + '; exec bash')}"]
    elif command:
        cmd += ["-e", "bash", "-c", command + "; exec bash"]
    subprocess.Popen(cmd, cwd=work_dir, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return {"opened": "terminal", "command": command, "folder": shown_dir}
