"""Verification codes (TOTP, RFC 6238), computed here: no network, no clock but the computer's.

The cloud's Passwords app has no field for them, so the setup key lives in a hidden custom field of the
entry (label "OTP", type secret, an otpauth:// URI): the cloud keeps it, encrypted like the password, and its
web page shows it as a secret. Fields written by other apps are read too: an otpauth:// URI anywhere, or a
base32 key in a field called OTP, TOTP, 2FA, A2F…
"""
import base64
import hashlib
import hmac
import re
import struct
import time
from urllib.parse import parse_qs, quote, unquote, urlsplit

FIELD_LABEL = "OTP"
LABELS = re.compile(r"^\s*(otp|totp|2fa|a2f|mfa|authenticator|code\s*2fa|clé\s*2fa|2fa\s*key|otpauth)\s*$", re.I)
ALGORITHMS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}


def _secret(raw, shortest=8):
    """Normalised base32 secret, or "" when it is not one."""
    s = re.sub(r"[\s-]", "", str(raw or "")).upper().rstrip("=")
    if len(s) < shortest or not re.fullmatch(r"[A-Z2-7]+", s):
        return ""
    try:
        base64.b32decode(s + "=" * (-len(s) % 8))
    except ValueError:
        return ""
    return s


def parse(value):
    """{secret, digits, period, algorithm, issuer, account} from an otpauth://totp URI or a bare base32 key;
    None otherwise (HOTP counters are not supported: they change on use)."""
    value = str(value or "").strip()
    if value.lower().startswith("otpauth://"):
        parts = urlsplit(value)
        if parts.netloc.lower() != "totp":
            return None
        query = {k.lower(): v[0] for k, v in parse_qs(parts.query).items()}
        secret = _secret(query.get("secret"))
        if not secret:
            return None
        label = unquote(parts.path.lstrip("/"))
        issuer, _, account = label.partition(":") if ":" in label else ("", "", label)
        try:
            digits = int(query.get("digits") or 6)
            period = int(query.get("period") or 30)
        except ValueError:
            return None
        algorithm = (query.get("algorithm") or "SHA1").upper()
        if digits not in (6, 7, 8) or not 10 <= period <= 120 or algorithm not in ALGORITHMS:
            return None
        return {"secret": secret, "digits": digits, "period": period, "algorithm": algorithm,
                "issuer": query.get("issuer") or issuer.strip(), "account": account.strip()}
    secret = _secret(value, 16)            # a bare key: at least 80 bits, so a word is never taken for one
    if not secret:
        return None
    return {"secret": secret, "digits": 6, "period": 30, "algorithm": "SHA1", "issuer": "", "account": ""}


def code(config, now=None):
    """(code, seconds left in this period)."""
    now = time.time() if now is None else now
    period = config["period"]
    counter = int(now // period)
    key = base64.b32decode(config["secret"] + "=" * (-len(config["secret"]) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), ALGORITHMS[config["algorithm"]]).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** config["digits"])
    return str(number).zfill(config["digits"]), period - int(now % period)


def uri(config, label="", issuer=""):
    """The otpauth:// URI kept in the cloud (and shown as a QR to move the code to another app)."""
    issuer = issuer or config.get("issuer") or ""
    account = config.get("account") or label or "Orneos"
    name = quote(f"{issuer}:{account}" if issuer else account, safe="@:")
    params = f"secret={config['secret']}"
    if issuer:
        params += "&issuer=" + quote(issuer, safe="")
    if config.get("algorithm", "SHA1") != "SHA1":
        params += "&algorithm=" + config["algorithm"]
    if config.get("digits", 6) != 6:
        params += f"&digits={config['digits']}"
    if config.get("period", 30) != 30:
        params += f"&period={config['period']}"
    return f"otpauth://totp/{name}?{params}"


def find(fields):
    """Index of the field that holds the verification code of an entry, or -1."""
    for i, field in enumerate(fields or []):
        value = str(field.get("value") or "")
        if value.lower().startswith("otpauth://totp") and parse(value):
            return i
    for i, field in enumerate(fields or []):
        if LABELS.match(str(field.get("label") or "")) and parse(field.get("value")):
            return i
    return -1
