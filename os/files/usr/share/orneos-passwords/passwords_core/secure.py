"""The local vault: what the cloud has, plus the changes not sent yet, encrypted on disk (AES-256-GCM).

The key is random, made once per account and kept in KWallet (folder "Orneos"), which opens with the session
(pam_kwallet): nothing to type. In Plume on Windows and macOS (or a Linux without KWallet), the system's
keychain keeps it (Gestionnaire d'identifiants, Trousseau, Secret Service). Without a usable one it goes to
a file only this user can read, like the app password of Orneos Connect. The vault file alone is useless: a copied disk, a backup or another account
on the same computer cannot read it. Losing the key only loses the copy: the cloud has everything, except the
changes made offline and not sent yet.
"""
import base64
import json
import os
import secrets
import shutil
import subprocess

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import system

DATA = system.DATA
VAULT = DATA / "passwords.vault"
KEY_FILE = DATA / "passwords.key"
FOLDER, WALLET = "Orneos", "kdewallet"
MAGIC = b"ORNPW1"


def _entry(user):
    return f"passwords-vault:{user.lower()}"


def _wallet():
    return shutil.which("kwallet-query") if os.environ.get("PASSWORDS_NO_WALLET") != "1" else None


def _keychain():
    """The system's keychain, where there is no KWallet (Plume on Windows, macOS, another Linux)."""
    return system._keyring() if os.environ.get("PASSWORDS_NO_WALLET") != "1" else None


def _keychain_read(ring, user):
    try:
        value = ring.get_password(system.SERVICE, _entry(user))
    except Exception:  # noqa: BLE001 - locked, refused: asked again next time
        return "error", None
    if not value:
        return "missing", None
    try:
        key = base64.b64decode(value, validate=True)
    except ValueError:
        return "missing", None
    return ("ok", key) if len(key) == 32 else ("missing", None)


def _write_private(path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def _key_from_file(user):
    try:
        return base64.b64decode(json.loads(KEY_FILE.read_text(encoding="utf-8")).get(user.lower(), ""))
    except (OSError, ValueError, json.JSONDecodeError):
        return b""


def _key_to_file(user, key):
    try:
        data = json.loads(KEY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data[user.lower()] = base64.b64encode(key).decode()
    _write_private(KEY_FILE, json.dumps(data).encode())


def _wallet_read(tool, user):
    """("ok", key), ("missing", None) when the wallet has no key for this account, ("error", None) when it
    could not be asked (closed, refused, timed out)."""
    try:
        res = subprocess.run([tool, "-f", FOLDER, "-r", _entry(user), WALLET],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return "error", None
    value = res.stdout.strip()
    said = (res.stdout + res.stderr).lower()
    if res.returncode == 0 and value and "not found" not in said:
        try:
            key = base64.b64decode(value, validate=True)
        except ValueError:
            return "missing", None
        return ("ok", key) if len(key) == 32 else ("missing", None)
    if (res.returncode == 0 and not value) or "not found" in said or "does not exist" in said:
        return "missing", None
    return "error", None


def key_for(user, create=True):
    """The vault key of this account (32 bytes), made the first time. None when the wallet cannot be read
    right now (closed, refused): the vault waits rather than starting a new one over the old."""
    tool = _wallet()
    ring = None if tool else _keychain()
    if tool or ring:
        state, key = _wallet_read(tool, user) if tool else _keychain_read(ring, user)
        if state == "ok":
            return key
        if state == "error":
            return _key_from_file(user) or None
    key = _key_from_file(user)
    if key or not create:
        return key or None
    key = secrets.token_bytes(32)
    if tool:
        try:
            res = subprocess.run([tool, "-f", FOLDER, "-w", _entry(user), WALLET],
                                 input=base64.b64encode(key).decode(), capture_output=True, text=True, timeout=20)
            if res.returncode == 0 and _wallet_read(tool, user) == ("ok", key):
                return key
        except (OSError, subprocess.TimeoutExpired):
            pass
    elif ring:
        try:
            ring.set_password(system.SERVICE, _entry(user), base64.b64encode(key).decode())
            if _keychain_read(ring, user) == ("ok", key):
                return key
        except Exception:  # noqa: BLE001 - the file below keeps it
            pass
    _key_to_file(user, key)
    return key


def encrypt(key, user, payload: dict) -> bytes:
    nonce = secrets.token_bytes(12)
    data = json.dumps(payload, separators=(",", ":")).encode()
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, b"orneos-passwords:" + user.lower().encode())


def decrypt(key, user, blob: bytes):
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 28:
        return None
    nonce, data = blob[len(MAGIC):len(MAGIC) + 12], blob[len(MAGIC) + 12:]
    try:
        return json.loads(AESGCM(key).decrypt(nonce, data, b"orneos-passwords:" + user.lower().encode()))
    except (InvalidTag, ValueError):
        return None


def load(user, path=None):
    """The saved vault of this account, or None (none yet, another account's, no key)."""
    path = path or VAULT
    try:
        blob = path.read_bytes()
    except OSError:
        return None
    key = key_for(user, create=False)
    return decrypt(key, user, blob) if key else None


def save(user, payload, path=None):
    key = key_for(user)
    if key is None:
        return False
    _write_private(path or VAULT, encrypt(key, user, payload))
    return True


def forget(path=None):
    """Signed out, or another account: the copy goes (the cloud keeps everything)."""
    try:
        (path or VAULT).unlink()
    except OSError:
        pass
