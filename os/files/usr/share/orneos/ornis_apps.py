"""Applications on Orneos OS, for Ornis: what is installed, what Flathub and Fedora offer, installing and removing.

Flathub first (what Discover installs): sandboxed, at once, updated with the others, no restart. A Fedora package
(rpm-ostree) only when there is no Flatpak, or for what lives in the system (drivers, command-line tools, shell
extensions): it is added to the system image and ready after the next restart. The installation runs as a job
(ornis_shell): Ornis follows it, the settings window shows it and can stop it.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from configparser import ConfigParser
from pathlib import Path

import ornis_shell

HOME = Path.home()
FLATPAK_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+){2,}$")
PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,120}$")
REMOTE = "flathub"


def _run(cmd, timeout=30):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return out.returncode, out.stdout or "", out.stderr or ""
    except (OSError, subprocess.TimeoutExpired):
        return 127, "", ""


def _words(text):
    return [w for w in re.split(r"[\s,]+", str(text or "").lower()) if w]


def installed_flatpaks() -> list[dict]:
    if not shutil.which("flatpak"):
        return []
    code, out, _ = _run(["flatpak", "list", "--app", "--columns=application,name,version,origin,installation"])
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and FLATPAK_ID.match(parts[0]):
            rows.append({"id": parts[0], "name": parts[1], "version": parts[2] if len(parts) > 2 else "",
                         "source": "flatpak", "installation": parts[4] if len(parts) > 4 else ""})
    return rows


def layered_packages() -> dict:
    """{requested: [packages added with rpm-ostree], pending: added but waiting for the restart}"""
    if not shutil.which("rpm-ostree"):
        return {"requested": [], "pending": []}
    import json  # noqa: PLC0415
    code, out, _ = _run(["rpm-ostree", "status", "--json"], timeout=20)
    try:
        deployments = json.loads(out).get("deployments") or []
    except ValueError:
        return {"requested": [], "pending": []}
    booted = next((d for d in deployments if d.get("booted")), {})
    staged = next((d for d in deployments if d.get("staged")), None)
    now = set(booted.get("requested-packages") or []) | set(booted.get("requested-local-packages") or [])
    later = set((staged or {}).get("requested-packages") or []) | set((staged or {}).get("requested-local-packages") or [])
    return {"requested": sorted(now), "pending": sorted(later - now) if staged else []}


def _desktop_apps():
    """The applications of the menu (system, Flatpak, the user's): {name, id, file}."""
    lang = (os.environ.get("LANG") or "fr")[:2]
    dirs = [Path("/usr/share/applications"), HOME / ".local/share/applications",
            Path("/var/lib/flatpak/exports/share/applications"), HOME / ".local/share/flatpak/exports/share/applications"]
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
            yield {"name": e.get(f"Name[{lang}]") or e.get("Name") or f.stem, "id": f.stem,
                   "hay": " ".join([e.get("Name", ""), e.get(f"Name[{lang}]", ""), e.get("GenericName", ""),
                                    e.get(f"Keywords[{lang}]", ""), e.get("Keywords", ""), f.stem]).lower()}


def search_flathub(query: str, limit: int = 6) -> list[dict]:
    if not shutil.which("flatpak"):
        return []
    code, out, _ = _run(["flatpak", "search", "--columns=application,name,description,version,remotes", query], timeout=40)
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 5 or not FLATPAK_ID.match(parts[0]) or REMOTE not in parts[4].split(","):
            continue
        rows.append({"id": parts[0], "name": parts[1], "summary": parts[2][:160], "version": parts[3], "source": "flatpak"})
    # the app named like the question first (« steam » → Steam, not a Steam tool)
    words = _words(query)
    rows.sort(key=lambda r: (r["name"].lower() != " ".join(words), not all(w in r["name"].lower() for w in words)))
    return rows[:limit]


def search_packages(query: str, limit: int = 6) -> list[dict]:
    """Fedora packages whose name matches (rpm-ostree search, else dnf), best effort: they need their metadata."""
    words = _words(query)
    if not words:
        return []
    found = []
    for cmd in (["rpm-ostree", "search", *words], ["dnf", "-q", "search", "--", *words]):
        if not shutil.which(cmd[0]):
            continue
        code, out, _ = _run(cmd, timeout=60)
        for line in out.splitlines():
            m = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._+-]*?)(?:\.(?:x86_64|noarch|aarch64|i686))?\s+:\s+(.*)$", line)
            if m and m.group(1) not in {f["package"] for f in found}:
                found.append({"package": m.group(1), "summary": m.group(2)[:160], "source": "rpm"})
        if found:
            break
    found.sort(key=lambda r: (r["package"].lower() != "-".join(words), not all(w in r["package"].lower() for w in words)))
    return found[:limit]


def find(query: str) -> dict:
    words = _words(query)
    if not words:
        return {"error": "say which application"}
    if os.name == "nt":
        installed = []
        start_dirs = [
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        ]
        for d in start_dirs:
            if not d.is_dir():
                continue
            for lnk in d.rglob("*.lnk"):
                if all(w in lnk.stem.lower() for w in words):
                    installed.append({"name": lnk.stem, "id": lnk.stem})
        winget_rows = []
        if shutil.which("winget"):
            _c, out, _ = _run(["winget", "search", "--accept-source-agreements", "-n", "6", query], timeout=30)
            for line in out.splitlines():
                parts = re.split(r"\s{2,}", line.strip())
                if len(parts) >= 3 and "." in parts[1] and not parts[0].startswith("-"):
                    winget_rows.append({"id": parts[1], "name": parts[0], "version": parts[2], "source": "winget"})
        return {"installed": installed[:6], "winget": winget_rows[:6],
                "advice": "Already installed: open it with computer_open. Otherwise use computer_install_app with source=winget."}
    if os.uname().sysname == "Darwin":
        installed = []
        for d in (Path("/Applications"), Path("/System/Applications"), HOME / "Applications"):
            for app in sorted(d.glob("*.app")) if d.is_dir() else []:
                if all(w in app.stem.lower() for w in words):
                    installed.append({"name": app.stem, "id": app.stem})
        brew_rows = []
        if shutil.which("brew"):
            _c, out, _ = _run(["brew", "search", query], timeout=30)
            for token in out.split():
                if PACKAGE.match(token) and all(w in token.lower() for w in words):
                    brew_rows.append({"id": token, "name": token, "source": "brew"})
        return {"installed": installed[:6], "brew": brew_rows[:6],
                "advice": "Already installed: open it with computer_open. Otherwise use computer_install_app with source=brew."}
    installed = []
    for app in _desktop_apps():
        if all(w in app["hay"] for w in words):
            installed.append({"name": app["name"], "id": app["id"]})
    flathub = search_flathub(query)
    have = {a["id"] for a in installed_flatpaks()}
    for row in flathub:
        row["installed"] = row["id"] in have
    out = {"installed": installed[:6], "flathub": flathub}
    if not flathub:
        out["fedora_packages"] = search_packages(query)
        layered = layered_packages()
        for row in out["fedora_packages"]:
            row["installed"] = row["package"] in layered["requested"]
            row["after_restart"] = row["package"] in layered["pending"]
    out["advice"] = ("Already installed: open it with computer_open. Otherwise prefer Flathub (computer_install_app "
                     "source=flatpak). A Fedora package (source=rpm) only without a Flatpak: it is ready after a restart.")
    return out


def install(source: str, app_id: str, wait: float = 25) -> dict:
    """Starts the installation as a job; Ornis follows it with computer_command_status."""
    source = str(source or "").lower()
    app_id = str(app_id or "").strip()
    if source == "flatpak":
        if not FLATPAK_ID.match(app_id):
            return {"error": "a Flathub application id is like com.valvesoftware.Steam (computer_find_app gives it)"}
        # system-wide like Discover; the user's own installation when the system one is refused
        cmd = (f"flatpak install -y --noninteractive {REMOTE} {app_id} || "
               f"flatpak install -y --noninteractive --user {REMOTE} {app_id}")
        out = ornis_shell.start(cmd, wait=wait, label=f"Flathub · {app_id}", kind="install")
        out["after"] = "Once done, it is in the menu: computer_open can start it."
        return out
    if source == "rpm":
        local = Path(os.path.expanduser(app_id))
        if app_id.endswith(".rpm"):
            if not local.is_absolute():
                local = HOME / local
            local = local.resolve()
            if HOME not in local.parents or not local.is_file():
                return {"error": "the .rpm file must be in the home folder"}
            if shutil.which("orneos-rpm"):
                subprocess.Popen(["orneos-rpm", str(local)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
                return {"opened": "the Orneos package installer window, the user goes on there", "file": str(local)}
            target = str(local)
        elif PACKAGE.match(app_id):
            target = app_id
        else:
            return {"error": "not a package name"}
        import shlex  # noqa: PLC0415
        if shutil.which("rpm-ostree"):
            out = ornis_shell.start(f"rpm-ostree install --idempotent --allow-inactive {shlex.quote(target)}", wait=wait,
                                    label=f"rpm-ostree · {target}", kind="install")
            out["after"] = ("Added to the system image: available after the next restart (offer computer_power restart). "
                            "The system asked for the user's password in a window.")
            return out
        if shutil.which("dnf"):
            return ornis_shell.start(f"pkexec dnf install -y {shlex.quote(target)}", wait=wait, label=f"dnf · {target}", kind="install")
        return {"error": "rpm-ostree or dnf is not available on this computer"}
    if source == "apt" and PACKAGE.match(app_id) and shutil.which("apt-get"):
        import shlex  # noqa: PLC0415
        return ornis_shell.start(f"pkexec apt-get install -y {shlex.quote(app_id)}", wait=wait, label=f"apt · {app_id}", kind="install")
    if source == "brew" and PACKAGE.match(app_id) and shutil.which("brew"):
        import shlex  # noqa: PLC0415
        return ornis_shell.start(f"brew install {shlex.quote(app_id)}", wait=wait, label=f"Homebrew · {app_id}", kind="install")
    if source == "winget" and PACKAGE.match(app_id) and shutil.which("winget"):
        return ornis_shell.start(f"winget install --exact --id \"{app_id}\" --accept-package-agreements --accept-source-agreements",
                                 wait=wait, label=f"winget · {app_id}", kind="install")
    return {"error": "source is flatpak, rpm, apt, brew or winget"}


def remove(source: str, app_id: str, wait: float = 25) -> dict:
    source = str(source or "").lower()
    app_id = str(app_id or "").strip()
    if source == "flatpak":
        if not FLATPAK_ID.match(app_id):
            return {"error": "a Flathub application id is like com.valvesoftware.Steam"}
        installation = next((a.get("installation") for a in installed_flatpaks() if a["id"] == app_id), None)
        if installation is None:
            return {"error": f"{app_id} is not installed"}
        scope = "--user " if installation == "user" else ""
        return ornis_shell.start(f"flatpak uninstall -y --noninteractive {scope}{app_id}", wait=wait,
                                 label=f"Flathub · {app_id}", kind="remove")
    if source == "rpm":
        if not PACKAGE.match(app_id):
            return {"error": "not a package name"}
        if shutil.which("rpm-ostree"):
            layered = layered_packages()
            if app_id not in layered["requested"] and app_id not in layered["pending"]:
                return {"error": f"{app_id} was not added with rpm-ostree: it is part of Orneos OS and stays"}
            out = ornis_shell.start(f"rpm-ostree uninstall {app_id}", wait=wait, label=f"rpm-ostree · {app_id}", kind="remove")
            out["after"] = "Removed from the system image at the next restart."
            return out
        if shutil.which("dnf"):
            import shlex  # noqa: PLC0415
            return ornis_shell.start(f"pkexec dnf remove -y {shlex.quote(app_id)}", wait=wait, label=f"dnf · {app_id}", kind="remove")
    if source == "apt" and PACKAGE.match(app_id) and shutil.which("apt-get"):
        import shlex  # noqa: PLC0415
        return ornis_shell.start(f"pkexec apt-get remove -y {shlex.quote(app_id)}", wait=wait, label=f"apt · {app_id}", kind="remove")
    if source == "brew" and PACKAGE.match(app_id) and shutil.which("brew"):
        import shlex  # noqa: PLC0415
        return ornis_shell.start(f"brew uninstall {shlex.quote(app_id)}", wait=wait, label=f"Homebrew · {app_id}", kind="remove")
    if source == "winget" and PACKAGE.match(app_id) and shutil.which("winget"):
        return ornis_shell.start(f"winget uninstall --exact --id \"{app_id}\"", wait=wait, label=f"winget · {app_id}", kind="remove")
    return {"error": "source is flatpak, rpm, apt, brew or winget"}
