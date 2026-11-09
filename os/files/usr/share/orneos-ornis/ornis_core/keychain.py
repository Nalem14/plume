"""The Trousseau (Mots de passe) for the browsers of Ornis: the sign-ins of a site, filled into the page by Ornis,
never read by the model. A bot is allowed once by the person (bot profile `keychain`), then signs in by itself,
saves the accounts it creates (with a password it generated and never saw), and fills verification codes.

The vault is the one of Mots de passe (passwords_core.vault: AES-256-GCM, its key in the system's keychain),
read fresh each time; a new entry is written there and sent to the cloud at once, so the Mots de passe window
(another process on Orneos OS) gets it from the cloud even if it rewrites its copy meanwhile.
Nothing here is ever logged, printed or returned to the model: usernames go back, passwords and codes never.
"""
from __future__ import annotations

import threading

import cloud


class Unavailable(Exception):
    """No Trousseau here (not signed in, Mots de passe not installed, vault not readable)."""


def _modules():
    try:
        from passwords_core import generator, sites, totp  # noqa: PLC0415
        from passwords_core.api import Api  # noqa: PLC0415
        from passwords_core.vault import Vault  # noqa: PLC0415
    except ImportError as error:
        raise Unavailable("Mots de passe is not installed here") from error
    return Vault, Api, sites, totp, generator


def _vault():
    Vault, _api, _sites, _totp, _gen = _modules()
    account = cloud.account()
    if not account:
        raise Unavailable("not signed in to Orneos")
    vault = Vault(account[1])
    if not vault.load():
        raise Unavailable("the Trousseau is not readable on this computer yet (open Mots de passe once)")
    return vault, account


def _base(host: str) -> str:
    """mastodon.social, www.linkedin.com → linkedin.com: the site, not one of its servers."""
    parts = [p for p in str(host or "").lower().strip(".").split(".") if p]
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in ("co", "com", "org", "net", "gouv", "ac", "gov"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def logins(host: str) -> list[dict]:
    """The entries of this site (same site, any of its servers), the most relevant first: {id, label, username,
    has_code}. Never a password."""
    vault, _account = _vault()
    _V, _A, sites, totp, _g = _modules()
    want = _base(sites.host(host) or host)
    out = []
    for entry in vault.entries().values():
        if entry.get("trashed") or not entry.get("password"):
            continue
        site = sites.host(entry.get("url") or "") or sites.host(entry.get("label") or "")
        if not site or _base(site) != want:
            continue
        out.append({"id": entry["id"], "label": str(entry.get("label") or site), "username": str(entry.get("username") or ""),
                    "has_code": totp.find(entry.get("customFields")) >= 0, "favorite": bool(entry.get("favorite")),
                    "exact": site == (sites.host(host) or host), "updated": int(entry.get("updated") or 0)})
    out.sort(key=lambda e: (not e["exact"], not e["favorite"], -e["updated"]))
    return out


def secret(entry_id: str) -> tuple[str, str]:
    """(username, password) of one entry: only for filling a page here, in this process."""
    vault, _account = _vault()
    entry = vault.entry(entry_id) or {}
    return str(entry.get("username") or ""), str(entry.get("password") or "")


def code(entry_id: str) -> str:
    """The verification code of this entry now ("" when it has none)."""
    vault, _account = _vault()
    _V, _A, _s, totp, _g = _modules()
    fields = (vault.entry(entry_id) or {}).get("customFields") or []
    index = totp.find(fields)
    if index < 0:
        return ""
    config = totp.parse(fields[index].get("value"))
    return totp.code(config)[0] if config else ""


def _root_folder() -> str:
    try:
        from passwords_core.api import ROOT_FOLDER  # noqa: PLC0415
        return ROOT_FOLDER
    except ImportError:
        return ""


def generate() -> str:
    _V, _A, _s, _t, generator = _modules()
    return generator.strong()


def save(site: str, username: str, password: str, url: str = "", label: str = "", note: str = "") -> str:
    """A new sign-in (an account a bot just made, or one it was given), into the vault and to the cloud at once.
    An entry of the same site and username gets the new password instead of a second entry."""
    vault, account = _vault()
    Vault, Api, sites, _t, _g = _modules()
    host = sites.host(url or site) or site
    existing = next((e for e in vault.entries().values() if not e.get("trashed")
                     and _base(sites.host(e.get("url") or "") or "") == _base(host)
                     and str(e.get("username") or "").lower() == str(username or "").lower()), None)
    if existing:
        entry_id = vault.save_entry({**existing, "password": password}, ["password"])
    else:
        entry_id = vault.save_entry({"label": label or host, "username": username, "password": password,
                                     "url": url or f"https://{host}", "notes": note, "customFields": [],
                                     "folder": _root_folder(), "tags": [], "favorite": False})

    def push():
        try:
            vault.push(Api(account))
        except Exception:  # noqa: BLE001 - offline: Mots de passe sends it with its next sync
            pass
    threading.Thread(target=push, daemon=True, name="ornis-keychain-push").start()
    return entry_id
