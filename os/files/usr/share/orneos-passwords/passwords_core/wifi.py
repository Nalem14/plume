"""The Wi-Fi networks this computer remembers (NetworkManager), like the Wi-Fi section of macOS Passwords:
the name, the security, the key on demand, and a QR code a phone scans to join.

They are not sent to the cloud: they belong to this computer. A key is read only when asked (nmcli asks
NetworkManager, which may ask the Plasma wallet or polkit for networks shared by every user).
"""
import shutil
import subprocess
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot

from passwords_core import qr


def _nmcli(*args, timeout=15):
    if not shutil.which("nmcli"):
        return None
    try:
        res = subprocess.run(["nmcli", "-t", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout if res.returncode == 0 else None


def _split(line):
    """nmcli -t fields: colon-separated, with \\: and \\\\ escaped."""
    out, cur, i = [], "", 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            cur += line[i + 1]
            i += 2
            continue
        if ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    out.append(cur)
    return out


def networks():
    out = _nmcli("-f", "NAME,UUID,TYPE,TIMESTAMP", "connection", "show")
    rows = []
    for line in (out or "").splitlines():
        parts = _split(line)
        if len(parts) >= 3 and parts[2] in ("802-11-wireless", "wifi"):
            rows.append({"name": parts[0], "uuid": parts[1], "used": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0})
    return sorted(rows, key=lambda r: -r["used"])


def secret(uuid):
    """(ssid, security, key): security is "WPA", "WEP", "SAE" or "" (open)."""
    values = []
    # one field per call: how nmcli lays several out (lines or colons) changed between versions
    for field in ("802-11-wireless.ssid", "802-11-wireless-security.key-mgmt", "802-11-wireless-security.psk",
                  "802-11-wireless-security.wep-key0"):
        out = _nmcli("-s", "-g", field, "connection", "show", "uuid", uuid, timeout=40)
        if out is None:
            return None
        values.append(out.rstrip("\n").replace("\\:", ":").replace("\\\\", "\\"))
    ssid, mgmt, psk, wep = values
    security = {"wpa-psk": "WPA", "sae": "WPA", "none": "WEP", "ieee8021x": "WEP"}.get(mgmt, "WPA" if psk else "")
    return ssid, security, psk or wep


def join_code(ssid, security, key):
    """The text phones read in a Wi-Fi QR code (the ZXing format every camera app knows)."""
    def esc(text):
        return "".join("\\" + c if c in '\\;,:"' else c for c in text)
    kind = security if key else "nopass"
    return f"WIFI:T:{kind};S:{esc(ssid)};P:{esc(key)};;" if key else f"WIFI:T:nopass;S:{esc(ssid)};;"


class Wifi(QObject):
    changed = Signal()
    keyReady = Signal(str, "QVariantMap")       # uuid, {ssid, security, key, qr} ({} when refused)
    _listed = Signal(list)
    _key = Signal(str, object)

    def __init__(self):
        super().__init__()
        self._rows = []
        self._loaded = False
        self._listed.connect(self._set_rows)
        self._key.connect(lambda uuid, data: self.keyReady.emit(uuid, data or {}))

    @Property("QVariantList", notify=changed)
    def networks(self):
        return self._rows

    @Property(bool, notify=changed)
    def available(self):
        return bool(shutil.which("nmcli"))

    @Slot()
    def load(self):
        threading.Thread(target=lambda: self._listed.emit(networks()), daemon=True).start()

    def _set_rows(self, rows):
        self._rows = rows
        self._loaded = True
        self.changed.emit()

    @Slot(str)
    def reveal(self, uuid):
        def run():
            found = secret(uuid)
            if not found:
                self._key.emit(uuid, None)
                return
            ssid, security, key = found
            self._key.emit(uuid, {"ssid": ssid, "security": security, "key": key,
                                  "qr": qr.matrix(join_code(ssid, security, key))})
        threading.Thread(target=run, daemon=True).start()
