"""Shared helpers for Orneos OS updates: channels (stable / unstable) and image variants (NVIDIA driver)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

REGISTRY = "registry.orneos.eu/orneos/os"
STATE_DIR = Path("/var/lib/orneos")
CHANNEL_FILE = STATE_DIR / "channel"
VARIANT_FILE = STATE_DIR / "variant"  # auto (default), standard, nvidia, nvidia-580
# After a rollback: digest of the version left behind. Automatic updates wait for another one.
PAUSE_FILE = STATE_DIR / "paused-digest"
REF_FILE = STATE_DIR / "image-ref"
ADMIN = "/usr/libexec/orneos-os-admin"

CHANNELS = {
    "stable": "latest",
    "unstable": "unstable",
}


# One image per graphics driver. AMD and Intel use the free drivers of the standard image.
VARIANTS = {
    "standard": REGISTRY,
    "nvidia": f"{REGISTRY}-nvidia",          # current driver: Turing and newer (GTX 16xx, RTX 20xx…50xx)
    "nvidia-580": f"{REGISTRY}-nvidia-580",  # legacy branch: Maxwell, Pascal, Volta (GTX 750…10xx)
}
# PCI device ids of NVIDIA GPUs grow with the architecture: Maxwell starts at 0x1340 (GM108), Turing at
# 0x1e00 (TU102). Older cards (Kepler and before) have no maintained driver for this kernel: nouveau.
NVIDIA_TURING, NVIDIA_MAXWELL = 0x1E00, 0x1340


def detect_variant() -> str:
    """The image this hardware needs, from the display controllers on the PCI bus."""
    best = "standard"
    for dev in Path("/sys/bus/pci/devices").glob("*"):
        try:
            vendor = (dev / "vendor").read_text().strip()
            klass = (dev / "class").read_text().strip()
            device = int((dev / "device").read_text().strip(), 16)
        except (OSError, ValueError):
            continue
        if vendor != "0x10de" or not klass.startswith("0x03"):
            continue
        if device >= NVIDIA_TURING:
            return "nvidia"
        if device >= NVIDIA_MAXWELL:
            best = "nvidia-580"
    return best


def variant_choice() -> str:
    """What the user chose: auto, or a forced variant."""
    try:
        value = VARIANT_FILE.read_text(encoding="utf-8").strip().lower()
        if value in VARIANTS:
            return value
    except OSError:
        pass
    return "auto"


def variant() -> str:
    choice = variant_choice()
    return detect_variant() if choice == "auto" else choice


def lang() -> str:
    return (os.environ.get("LANG") or "fr").split("_", 1)[0][:2]


def booted_ref() -> str:
    """The image reference currently booted according to bootc / rpm-ostree."""
    if shutil.which("bootc"):
        try:
            r = subprocess.run(
                ["bootc", "status", "--format", "json"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            data = json.loads(r.stdout or "{}")
            booted = (data.get("status") or {}).get("booted") or {}
            img = ((booted.get("image") or {}).get("image") or {}).get("image", "")
            if img:
                return img
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, AttributeError):
            pass
    for d in _deployments():
        if d.get("booted"):
            ref = d.get("container-image-reference") or ""
            if ref:
                if ":" in ref and not ref.startswith("registry.") and not ref.startswith("localhost"):
                    ref = ref.split(":", 1)[1]
                return ref
    return ""


TRANSPORTS = ("ostree-unverified-registry:", "ostree-remote-registry:", "ostree-image-signed:",
              "ostree-unverified-image:", "ostree-remote-image:")


def deployment_ref(d: dict) -> str:
    """Image reference of an rpm-ostree deployment, without the ostree transport prefix."""
    ref = d.get("container-image-reference") or ""
    for prefix in TRANSPORTS:
        if ref.startswith(prefix):
            ref = ref[len(prefix):]
            break
    if ref.startswith("registry:"):
        ref = ref[len("registry:"):]
    return ref


def default_deployment() -> dict:
    """The deployment the next boot uses (a staged update if there is one, else the booted one)."""
    deps = _deployments()
    return deps[0] if deps else {}


LAYERING_KEYS = ("requested-packages", "requested-local-packages", "requested-base-removals",
                 "requested-base-local-replacements", "requested-modules")


def has_layering(d: dict) -> bool:
    """User packages added with rpm-ostree (orneos-rpm, drivers…): only rpm-ostree carries them over."""
    return any(d.get(k) for k in LAYERING_KEYS)


def deployment_digest(d: dict) -> str:
    for k in ("container-image-reference-digest", "container-image-digest", "manifest-digest"):
        if d.get(k):
            return str(d[k])
    return ""


def booted_digest() -> str:
    """Manifest digest of the image the next boot uses (rpm-ostree), else the booted one (bootc)."""
    dig = deployment_digest(default_deployment())
    if dig:
        return dig
    if shutil.which("bootc"):
        try:
            r = subprocess.run(
                ["bootc", "status", "--format", "json"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            data = json.loads(r.stdout or "{}")
            dig = ((((data.get("status") or {}).get("booted") or {}).get("image")) or {}).get("imageDigest", "")
            if dig:
                return dig
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, AttributeError):
            pass
    return ""


def fetch_remote_digests(ref: str) -> set[str]:
    """Digests published for ``ref``: the index push.sh writes, and this machine's manifest in it."""
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(os.uname().machine, os.uname().machine)
    try:
        host_path, _, tag = ref.rpartition(":")
        host, _, repo = host_path.partition("/")
        url = f"https://{host}/v2/{repo}/manifests/{tag or 'latest'}"
        req = urllib.request.Request(url, headers={"Accept": ", ".join((
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
        ))})
        with urllib.request.urlopen(req, timeout=10) as resp:
            digests = {resp.headers.get("Docker-Content-Digest") or ""}
            body = json.loads(resp.read() or b"{}")
        for m in body.get("manifests") or []:
            if (m.get("platform") or {}).get("architecture") == arch:
                digests.add(m.get("digest") or "")
        return digests - {""}
    except Exception:
        return set()


def channel() -> str:
    try:
        value = CHANNEL_FILE.read_text(encoding="utf-8").strip().lower()
        if value in CHANNELS:
            return value
    except OSError:
        pass
    ref = booted_ref().lower()
    if ":unstable" in ref or "unstable" in ref:
        return "unstable"
    return "stable"


def tag_for(ch: str | None = None) -> str:
    return CHANNELS.get(ch or channel(), "latest")


def image_ref(ch: str | None = None, var: str | None = None) -> str:
    return f"{VARIANTS.get(var or variant(), REGISTRY)}:{tag_for(ch)}"


def os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    for path in (Path("/etc/os-release"), Path("/usr/lib/os-release")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            data[k] = v.strip().strip('"')
        break
    return data


def orneos_build() -> str:
    """Build id written at image compose time (YYYYMMDD.HHMM). Changes on every Orneos push."""
    return os_release().get("ORNEOS_BUILD") or os_release().get("VERSION") or ""


def _deployments() -> list[dict]:
    try:
        result = subprocess.run(
            ["rpm-ostree", "status", "--json"],
            capture_output=True, text=True, timeout=60, check=False,
        )
        data = json.loads(result.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
    return list(data.get("deployments") or [])


def deploy_label(d: dict) -> str:
    return _deploy_label(d)


def _deploy_label(d: dict) -> str:
    # Prefer container image version / ostree version; fall back to short checksum.
    for key in ("version", "container-image-name", "base-commit-meta"):
        val = d.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:48]
        if isinstance(val, dict):
            for meta in ("version", "ostree.version", "org.opencontainers.image.version"):
                if meta in val and val[meta]:
                    return str(val[meta])[:48]
    checksum = d.get("checksum") or ""
    return (checksum[:12] + "…") if checksum else "—"


def pending_deployment() -> str | None:
    deps = _deployments()
    if not deps or deps[0].get("booted"):
        return None
    return _deploy_label(deps[0])


def rollback_deployment() -> dict | None:
    """The version before the running one (rpm-ostree keeps it), if any."""
    deps = _deployments()
    for i, d in enumerate(deps):
        if d.get("booted"):
            return deps[i + 1] if i + 1 < len(deps) else None
    return None


def deploy_date(d: dict) -> str:
    ts = d.get("timestamp")
    return time.strftime("%d/%m/%Y", time.localtime(int(ts))) if ts else ""


def updates_paused() -> bool:
    return PAUSE_FILE.is_file()


def booted_version() -> str:
    """What the updates UI shows as the running system.

    Uses ORNEOS_BUILD from os-release (moves on every image we publish). The Fedora
    OSTREE_VERSION alone often stays the same across Orneos-only rebuilds.
    """
    build = orneos_build()
    pretty = os_release().get("PRETTY_NAME") or ""
    if build and build != "dev":
        return build if not pretty else f"{build}"
    for d in _deployments():
        if d.get("booted"):
            return _deploy_label(d)
    return pretty or ""


def pkexec_admin(*args: str, timeout: int = 3600) -> tuple[int, str]:
    cmd = ["pkexec", ADMIN, *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return 127, "pkexec is not available"
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    out = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode, out


def prompt_reboot() -> None:
    subprocess.run(
        [
            "busctl", "--user", "call", "org.kde.LogoutPrompt", "/LogoutPrompt",
            "org.kde.LogoutPrompt", "promptReboot",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False,
    )
