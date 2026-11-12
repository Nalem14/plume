"""What Ornis may do on this computer without asking, and asking when it may not.

Ornis runs in the cloud: what reaches this computer may come from a text it read (a mail, a web page), not from the
user. So the computer decides, never the conversation. Each request has a level:

  info     reads only (state of the computer, a folder, a file, a command that only looks)
  light    small and undone in a click (open an app, sound, brightness, appearance, timer, lock)
  change   changes files or the system, for the user only (write, move, install a Flatpak, a command that writes)
  admin    the whole system or for good (rpm-ostree, sudo, restart, shut down)

and the user's mode says which run without a question:

  ask      (Demander, by default) every request asks, except what the user allowed for good
  auto     (Automatique) info and light run at once; change and admin ask
  full     (Autonome, for a while or for good) everything runs at once

Whatever the mode, some always ask (secrets: SSH keys, wallets, the app password of the cloud…) and some never run
(wiping a disk or the home folder): ornis_shell.classify says which. Every decision is written in a journal that the
settings window (ornis_computer_ui) shows, with « Annuler » for what can be undone.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import system
HOME = Path.home()
CONFIG = system.CONFIG / "ornis-computer.json"
STATE = system.STATE
JOURNAL = STATE / "ornis-computer.jsonl"
JOURNAL_KEEP = 400
DIALOG = "/usr/libexec/orneos-ornis-consent"
SETTINGS = "/usr/libexec/orneos-ornis-computer"
ASK_SECONDS = 90
LEVELS = ("info", "light", "change", "admin")
MODES = ("ask", "auto", "full")
# what runs at once in each mode
SILENT = {"ask": set(), "auto": {"info", "light"}, "full": {"info", "light", "change", "admin"}}

# Secrets of the user, and what starts by itself: reading or touching them always asks, in every mode, and is never
# allowed for good
SENSITIVE = (
    "~/.ssh", "~/.gnupg", "~/.pki", "~/.netrc", "~/.aws", "~/.kube", "~/.docker/config.json", "~/.password-store",
    "~/.local/share/kwalletd", "~/.local/share/keyrings", "~/.config/orneos", "~/.config/Orneos", "~/.config/Nextcloud",
    "~/.local/share/orneos/passwords", "~/.mozilla", "~/.config/chromium", "~/.config/google-chrome",
    "~/.var/app/org.mozilla.firefox", "~/.config/BraveSoftware", "~/.config/microsoft-edge", "~/.bash_history",
    "~/Library/Keychains", "~/Library/Application Support/Orneos", "~/Library/Application Support/Google",
    "~/AppData/Roaming/Orneos", "~/AppData/Local/Google", "~/AppData/Local/Microsoft",
    "~/AppData/Roaming/Microsoft/Credentials", "~/Library/LaunchAgents",
    "/etc/shadow", "/etc/gshadow", "/etc/sudoers",
    # what starts by itself at the next login: a way to stay on the computer
    "~/.bashrc", "~/.bash_profile", "~/.profile", "~/.zshrc", "~/.config/autostart", "~/.config/systemd/user",
    "~/.config/environment.d", "~/.local/share/applications", "~/.config/plasma-workspace/env",
)


def _expand(path: str) -> str:
    return path.replace("~", str(HOME), 1) if path.startswith("~") else path


def sensitive(text: str) -> bool:
    """Whether a path or a command names one of the user's secrets."""
    text = str(text or "")
    expanded = text.replace("$HOME", str(HOME)).replace("${HOME}", str(HOME))
    expanded = re.sub(r"(^|[\s=\"'(:])~(?=/)", lambda m: m.group(1) + str(HOME), expanded)
    # On macOS/Windows, system.DATA == system.CONFIG (~/Library/Application Support/Orneos, ~/AppData/Roaming/Orneos).
    # Ornis Code's own bot workspaces, profiles and logs live under DATA/ornis-bots and DATA/ornis-code: only the
    # token file (credentials.json) inside ornis-code is a secret.
    if "credentials.json" in expanded:
        return True
    for sub in ("ornis-bots", "ornis-code"):
        for base in (str(system.DATA / sub), f"~/Library/Application Support/Orneos/{sub}",
                     f"~/AppData/Roaming/Orneos/{sub}", f"Library/Application Support/Orneos/{sub}",
                     f"AppData/Roaming/Orneos/{sub}"):
            for variant in {base, base.replace("\\", "/"), base.replace("/", "\\")}:
                expanded = expanded.replace(variant, "/tmp/ornis-safe")
                text = text.replace(variant, "/tmp/ornis-safe")
    if str(system.CONFIG) in expanded or str(system.STATE) in expanded:
        return True
    for item in SENSITIVE:
        full = _expand(item)
        if full in expanded:
            return True
        if not item.startswith("~"):
            continue
        # relative to the home: « cat .ssh/id_rsa » run from ~
        rel = item[2:]
        if re.search(r"(^|[\s\"'=])(\./)?" + re.escape(rel) + r"(/|\b|$)", text):
            return True
    return False


# ---- settings -------------------------------------------------------------------------------------------------
def _clean_workspace(raw: str) -> str:
    raw = str(raw or "").strip()
    if not raw:
        return ""
    try:
        p = Path(os.path.expanduser(raw))
        if not p.is_absolute():
            p = HOME / p
        p = p.resolve()
        if p == HOME or HOME not in p.parents or not p.is_dir() or sensitive(str(p)):
            return ""
        return str(p)
    except OSError:
        return ""


def settings() -> dict:
    """{mode, until (0: no end), rules: [{kind, value, label, at}], workspace, workspace_auto, sandbox}."""
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    mode = data.get("mode") if data.get("mode") in MODES else "ask"
    until = float(data.get("until") or 0)
    if mode != "ask" and until and until < time.time():
        mode, until = "ask", 0
    rules = [r for r in data.get("rules") or [] if isinstance(r, dict) and r.get("kind") in ("action", "command")]
    # older versions kept the actions allowed for good as a list of names
    for name in data.get("always") or []:
        if isinstance(name, str) and not any(r["kind"] == "action" and r["value"] == name for r in rules):
            rules.append({"kind": "action", "value": name, "label": name, "level": "light", "at": 0})
    workspace = _clean_workspace(data.get("workspace") or "")
    workspace_auto = data.get("workspace_auto", True) is not False
    sandbox = data.get("sandbox", True) is not False
    return {"mode": mode, "until": until, "rules": rules, "workspace": workspace,
            "workspace_auto": workspace_auto, "sandbox": sandbox}


def _save(data: dict) -> None:
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG.with_suffix(".tmp")
        payload = {"mode": data["mode"], "until": data.get("until") or 0, "rules": data["rules"],
                   "workspace": _clean_workspace(data.get("workspace") or ""),
                   "workspace_auto": data.get("workspace_auto", True) is not False,
                   "sandbox": data.get("sandbox", True) is not False}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
        os.replace(tmp, CONFIG)
    except OSError:
        pass


def set_mode(mode: str, minutes: int = 0) -> dict:
    """Changes the mode; `minutes` > 0 puts it back to « ask » after that time (only for auto and full)."""
    data = settings()
    data["mode"] = mode if mode in MODES else "ask"
    data["until"] = time.time() + minutes * 60 if minutes > 0 and data["mode"] != "ask" else 0
    _save(data)
    return data


def set_workspace(path: str = "", auto_write: bool | None = None) -> dict:
    """Pins or clears the active local workspace directory inside the home folder."""
    data = settings()
    data["workspace"] = _clean_workspace(path)
    if auto_write is not None:
        data["workspace_auto"] = bool(auto_write)
    _save(data)
    return data


def set_sandbox(enabled: bool) -> dict:
    data = settings()
    data["sandbox"] = bool(enabled)
    _save(data)
    return data


def in_workspace(path: str | Path, workspace: str | None = None) -> bool:
    """True when `path` is inside the active workspace and does not touch `.git/hooks`, `.git/config`, `.env` or secrets."""
    ws = _clean_workspace(workspace if workspace is not None else settings().get("workspace") or "")
    if not ws:
        return False
    try:
        ws_path = Path(ws).resolve()
        target = Path(os.path.expanduser(str(path or ""))).resolve()
        if target != ws_path and ws_path not in target.parents:
            return False
        if sensitive(str(target)):
            return False
        parts = target.relative_to(ws_path).parts if target != ws_path else ()
        if parts and parts[0] == ".git" and (len(parts) < 2 or parts[1] in ("hooks", "config")):
            return False
        if target.name == ".env" or target.name.startswith(".env."):
            return False
        return True
    except (OSError, ValueError):
        return False


def add_rule(kind: str, value: str, label: str = "", level: str = "light") -> None:
    data = settings()
    if not any(r["kind"] == kind and r["value"] == value for r in data["rules"]):
        data["rules"].append({"kind": kind, "value": value, "label": label or value, "level": level,
                              "at": int(time.time())})
        _save(data)


def remove_rule(kind: str, value: str) -> None:
    data = settings()
    data["rules"] = [r for r in data["rules"] if not (r["kind"] == kind and r["value"] == value)]
    _save(data)


def rule_allows(request: dict, rules: list[dict]) -> bool:
    """A rule « Toujours autoriser » covers this request: the same action, or a command of the same program and
    sub-command, never above the level the rule was made at (« nmcli device » from a list does not connect)."""
    rank = LEVELS.index(request.get("level") or "admin")
    for r in rules:
        if rank > LEVELS.index(r.get("level") if r.get("level") in LEVELS else "change"):
            continue
        if request.get("command") is not None:
            key = str(request.get("rule") or "")
            if r["kind"] == "command" and key and r["value"] == key:
                return True
        elif r["kind"] == "action" and r["value"] == request.get("rule"):
            return True
    return False


# ---- journal ----------------------------------------------------------------------------------------------------
def log(entry: dict) -> str:
    """Adds a line to the journal; returns its id (to complete it with its outcome, `finish`)."""
    entry = {"id": f"{time.time():.6f}", "at": int(time.time()), **entry}
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        lines = JOURNAL.read_text(encoding="utf-8").splitlines() if JOURNAL.exists() else []
        lines = lines[-(JOURNAL_KEEP - 1):] + [json.dumps(entry, ensure_ascii=False)]
        tmp = JOURNAL.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n")
        os.replace(tmp, JOURNAL)
    except OSError:
        pass
    return entry["id"]


def finish(entry_id: str, **fields) -> None:
    try:
        lines = JOURNAL.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    out = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("id") == entry_id:
            row.update(fields)
        out.append(json.dumps(row, ensure_ascii=False))
    try:
        tmp = JOURNAL.with_suffix(".tmp")
        tmp.write_text("\n".join(out) + "\n")
        os.replace(tmp, JOURNAL)
    except OSError:
        pass


def journal(limit: int = 100) -> list[dict]:
    try:
        lines = JOURNAL.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= limit:
            break
    return out


def clear_journal() -> None:
    try:
        JOURNAL.unlink()
    except OSError:
        pass


# ---- deciding -----------------------------------------------------------------------------------------------------
def decide(request: dict) -> str:
    """'run' (at once), 'ask' or 'block', for a request {level, sensitive, blocked, can_always, rule, command, in_workspace}."""
    if request.get("blocked"):
        return "block"
    if request.get("sensitive"):
        return "ask"
    data = settings()
    if request.get("level") in SILENT[data["mode"]]:
        return "run"
    if (data["mode"] == "auto" and data.get("workspace") and data.get("workspace_auto", True)
            and request.get("in_workspace") and request.get("action") in ("write_file", "edit_file", "create_folder", "move_files")):
        return "run"
    if request.get("can_always") and rule_allows(request, data["rules"]):
        return "run"
    return "ask"


def _graphical() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")) and os.path.isfile(DIALOG)


def ask(request: dict, words: dict, asker=None) -> dict:
    """Asks the user on this computer: {answer: allow|always|deny, command: the command as the user left it}.
    In the app that follows the answer when it can (`asker`: Ornis and Plume show it above the message box, as the
    Code mode), otherwise the window (orneos-ornis-consent) when there is a screen, else a notification. No answer
    in time: deny."""
    if asker is not None:
        try:
            answer = asker(dict(request, mode=settings()["mode"], seconds=ASK_SECONDS))
        except Exception:  # noqa: BLE001 - the window below asks instead
            answer = None
        if isinstance(answer, dict) and answer.get("answer") in ("allow", "always", "deny"):
            return answer
    if _graphical() or system.WINDOWS or system.MACOS or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        payload = dict(request, mode=settings()["mode"], seconds=ASK_SECONDS)
        try:
            from ornis_local import helper
            out = subprocess.run([DIALOG] if DIALOG != "/usr/libexec/orneos-ornis-consent" else helper("consent"), input=json.dumps(payload, ensure_ascii=False), capture_output=True, text=True,
                                 timeout=ASK_SECONDS + 15)
            answer = json.loads(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else {}
            if isinstance(answer, dict) and answer.get("answer") in ("allow", "always", "deny"):
                return answer
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            pass
    if not shutil.which("notify-send"):
        return {"answer": "deny"}
    cmd = ["notify-send", "-a", "Ornis", "-i", "eu.orneos.ornis", "-u", "critical", "--wait", "-t", str(ASK_SECONDS * 1000),
           f"--action=allow={words['allow']}"]
    if request.get("can_always"):
        cmd.append(f"--action=always={words['always']}")
    body = request.get("summary") or ""
    if request.get("command") is not None:
        body += "\n" + request["command"][:300]
    cmd += [f"--action=deny={words['deny']}", request.get("title") or words["title"], body]
    try:
        answer = subprocess.run(cmd, capture_output=True, text=True, timeout=ASK_SECONDS + 5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        answer = ""
    return {"answer": answer if answer in ("allow", "always") else "deny"}


def tell(title: str, body: str) -> None:
    """A passing notification, for what ran without a question but changes something: the user sees it happen."""
    if system.notify(title, body):
        return
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-a", "Ornis", "-i", "eu.orneos.ornis", "-t", "6000", title, body[:300]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def open_settings() -> None:
    from ornis_local import helper
    subprocess.Popen(helper("computer"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
