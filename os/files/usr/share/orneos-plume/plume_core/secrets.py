"""The mail password: asked once, then kept in KWallet (folder "Orneos", one entry per address) on Orneos OS,
in the system's keychain elsewhere (macOS Keychain, Windows Credential Manager, Secret Service).

The wallet opens with the session (pam_kwallet), so Plume never asks again. Without a usable wallet,
the password goes to a file only this user can read, like the app password of Orneos Connect.
"""
import json

import system

FALLBACK = system.DATA / "plume-mail.json"


def _entry(address):
    return f"plume-mail:{address.lower()}"


def _file():
    try:
        return json.loads(FALLBACK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def get(address):
    return system.secret_get(_entry(address)) or _file().get(address.lower())


def put(address, password):
    if system.secret_set(_entry(address), password):
        forget_file(address)
        return "wallet"
    data = _file()
    data[address.lower()] = password
    system.private_write(FALLBACK, json.dumps(data))
    return "file"


def forget_file(address):
    data = _file()
    if address.lower() in data:
        data.pop(address.lower())
        system.private_write(FALLBACK, json.dumps(data))


def forget(address):
    system.secret_delete(_entry(address))
    forget_file(address)
