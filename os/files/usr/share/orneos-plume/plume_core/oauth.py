"""Signing in with Google or Microsoft for an external mailbox (OAuth 2 with PKCE), like Thunderbird does.

The browser opens the provider's own page (its password, its two-step verification); the answer comes back to
a one-time local address (http://127.0.0.1:<port>/, http://localhost:<port>/ for Microsoft, whose desktop
apps are registered with it). Only the refresh token is kept, in the keychain (secrets), with the client it was
given to; the access token lives in memory and is renewed on its own. IMAP and SMTP then sign in with XOAUTH2.

The apps (client ids) are published by orneos.eu (/updates/plume/oauth), so they can be set or changed without
a new Plume: a provider without one is not offered.
"""
import base64
import hashlib
import html
import json
import os
import secrets as rand
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from plume_core import imap, secrets

FEED = os.environ.get("PLUME_OAUTH_FEED") or "https://orneos.eu/updates/plume/oauth"
TIMEOUT = 15
WAIT = 600                          # seconds the browser has to come back

PROVIDERS = {
    "google": {
        "auth": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "scope": "openid email profile https://mail.google.com/",
        "mail_scope": "https://mail.google.com/",
        "host": "127.0.0.1",
        "extra": {"access_type": "offline", "prompt": "consent"},
        "imap": {"host": "imap.gmail.com", "port": 993, "security": "ssl"},
        "smtp": {"host": "smtp.gmail.com", "port": 465, "security": "ssl"},
    },
    "microsoft": {
        "auth": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "openid email profile offline_access https://outlook.office.com/IMAP.AccessAsUser.All "
                 "https://outlook.office.com/SMTP.Send",
        "mail_scope": "IMAP.AccessAsUser.All",
        "host": "localhost",
        "extra": {"prompt": "select_account"},
        "imap": {"host": "outlook.office365.com", "port": 993, "security": "ssl"},
        "smtp": {"host": "smtp.office365.com", "port": 587, "security": "starttls"},
    },
}
# tests: the providers' pages on a local fake (scheme://host:port), the mail servers too
if os.environ.get("PLUME_OAUTH_BASE"):
    for _p in PROVIDERS.values():
        for _k in ("auth", "token"):
            _p[_k] = os.environ["PLUME_OAUTH_BASE"] + urllib.parse.urlsplit(_p[_k]).path
        _p["host"] = "127.0.0.1"
if os.environ.get("PLUME_OAUTH_SERVERS"):
    _imap, _smtp = os.environ["PLUME_OAUTH_SERVERS"].split(",")
    for _p in PROVIDERS.values():
        _p["imap"] = {"host": _imap.split(":")[0], "port": int(_imap.split(":")[1]), "security": "plain"}
        _p["smtp"] = {"host": _smtp.split(":")[0], "port": int(_smtp.split(":")[1]), "security": "plain"}


class OAuthError(Exception):
    """kind: "unavailable" (no app for this provider), "cancelled", "denied" (refused on the provider's page),
    "timeout", "offline", "refused" (the provider would not give the tokens), "scope" (the access to the mail
    was left unticked on the provider's page: Google asks for each permission)."""

    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


_apps = {"at": 0.0, "data": {}}


def apps(fresh=False):
    """{provider: {"client_id", "client_secret"?}} published by orneos.eu, kept an hour."""
    if fresh or time.time() - _apps["at"] > 3600:
        try:
            req = urllib.request.Request(FEED, headers={"User-Agent": "Orneos Plume"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                data = json.loads(res.read(20_000))
            _apps["data"] = {k: v for k, v in data.items() if k in PROVIDERS and isinstance(v, dict) and v.get("client_id")}
            _apps["at"] = time.time()
        except (OSError, ValueError, AttributeError):
            pass                    # offline: what was known, if anything
    return _apps["data"]


def _post(url, fields):
    """(status, JSON answer); the providers explain a refusal in JSON with a 400."""
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "Orneos Plume", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return res.status, json.loads(res.read(200_000) or b"{}")
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read(200_000) or b"{}")
        except ValueError:
            return error.code, {}
    except (OSError, ValueError):
        return 0, {}


def _claims(id_token):
    """What the id token says (it comes straight from the provider's token endpoint, over TLS)."""
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError, AttributeError):
        return {}


class SignIn:
    """One sign-in: url to open in the browser, then wait() for the answer. cancel() from any thread."""

    def __init__(self, provider, hint="", page_done="", page_failed=""):
        app = apps().get(provider)
        if provider not in PROVIDERS or not app:
            raise OAuthError("unavailable")
        self.provider, self.app, self.conf = provider, app, PROVIDERS[provider]
        self.pages = (page_done, page_failed)
        self.verifier = rand.token_urlsafe(64)
        self.state = rand.token_urlsafe(24)
        self.answer = None
        self.cancelled = threading.Event()
        sign_in = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                if query.get("state", [""])[0] != sign_in.state:
                    self.send_error(404)
                    return
                sign_in.answer = {k: v[0] for k, v in query.items()}
                ok = "code" in sign_in.answer
                body = (sign_in.pages[0] if ok else sign_in.pages[1]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.server.timeout = 0.5
        self.redirect = f"http://{self.conf['host']}:{self.server.server_port}/"
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b"=").decode()
        params = {"client_id": app["client_id"], "response_type": "code", "redirect_uri": self.redirect,
                  "scope": self.conf["scope"], "state": self.state, "code_challenge": challenge,
                  "code_challenge_method": "S256", **self.conf["extra"]}
        if hint:
            params["login_hint"] = hint
        self.url = self.conf["auth"] + "?" + urllib.parse.urlencode(params)

    def cancel(self):
        self.cancelled.set()

    def wait(self):
        """{"address", "name", "secret", "access", "expires"} once the provider answered; OAuthError otherwise."""
        deadline = time.time() + WAIT
        try:
            while self.answer is None:
                if self.cancelled.is_set():
                    raise OAuthError("cancelled")
                if time.time() > deadline:
                    raise OAuthError("timeout")
                self.server.handle_request()
        finally:
            self.server.server_close()
        if "code" not in self.answer:
            raise OAuthError("denied")
        fields = {"grant_type": "authorization_code", "code": self.answer["code"], "redirect_uri": self.redirect,
                  "client_id": self.app["client_id"], "code_verifier": self.verifier}
        if self.app.get("client_secret"):
            fields["client_secret"] = self.app["client_secret"]
        status, tokens = _post(self.conf["token"], fields)
        if status == 0:
            raise OAuthError("offline")
        if not tokens.get("access_token") or not tokens.get("refresh_token"):
            raise OAuthError("refused")
        granted = tokens.get("scope")
        if granted is not None and self.conf["mail_scope"] not in granted:
            print("plume: signed in without the mail permission, granted:", granted, file=sys.stderr)
            raise OAuthError("scope")
        claims = _claims(tokens.get("id_token", ""))
        address = (claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "").strip()
        if "@" not in address:
            raise OAuthError("refused")
        secret = {"oauth": self.provider, "refresh": tokens["refresh_token"], "client_id": self.app["client_id"]}
        if self.app.get("client_secret"):
            secret["client_secret"] = self.app["client_secret"]
        return {"address": address, "name": claims.get("name", ""), "secret": json.dumps(secret),
                "access": tokens["access_token"], "expires": time.time() + int(tokens.get("expires_in") or 3600)}


def page(title, text):
    """The page the browser shows once the provider sent it back to Plume."""
    e = html.escape
    return ("<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            f"<title>{e(title)}</title><style>:root{{color-scheme:light dark}}body{{margin:0;min-height:100vh;display:grid;"
            "place-items:center;font:16px/1.5 system-ui,sans-serif;background:#F6F7FB;color:#0F2440}}"
            "@media(prefers-color-scheme:dark){body{background:#0A192F;color:#E8ECF5}}"
            "main{max-width:420px;padding:24px;text-align:center}h1{font-size:22px;margin:0 0 8px}p{margin:0;opacity:.75}"
            f"</style></head><body><main><h1>{e(title)}</h1><p>{e(text)}</p></main></body></html>")


# ---- access tokens -------------------------------------------------------------------------------------------
_tokens = {}                        # address → (access token, expires at)
_refresh = {}                       # address → the latest refresh token (Microsoft gives a new one each time)
_lock = threading.Lock()


def remember(address, access, expires):
    with _lock:
        _tokens[address.lower()] = (access, expires)


def forget(address):
    with _lock:
        _tokens.pop(address.lower(), None)
        _refresh.pop(address.lower(), None)


def is_oauth(secret):
    return bool(secret) and secret.startswith("{") and '"oauth"' in secret


def access_token(address, secret):
    """A valid access token for this mailbox, renewed when it is about to expire. imap.MailError "auth" when the
    provider no longer accepts the refresh token (revoked, password changed), "offline" when it cannot be asked."""
    key = address.lower()
    with _lock:
        token = _tokens.get(key)
        if token and token[1] - time.time() > 120:
            return token[0]
        try:
            data = json.loads(secret)
            conf = PROVIDERS[data["oauth"]]
        except (ValueError, KeyError, TypeError) as error:
            raise imap.MailError("auth") from error
        fields = {"grant_type": "refresh_token", "refresh_token": _refresh.get(key, data["refresh"]),
                  "client_id": data["client_id"]}
        if data.get("client_secret"):
            fields["client_secret"] = data["client_secret"]
        if data["oauth"] == "microsoft":
            fields["scope"] = conf["scope"]
        status, tokens = _post(conf["token"], fields)
        if status == 0 or status >= 500:
            raise imap.MailError("offline")
        if not tokens.get("access_token"):
            raise imap.MailError("auth")
        if tokens.get("refresh_token") and tokens["refresh_token"] != fields["refresh_token"]:
            _refresh[key] = tokens["refresh_token"]
            data["refresh"] = tokens["refresh_token"]
            secrets.put(address, json.dumps(data))
        _tokens[key] = (tokens["access_token"], time.time() + int(tokens.get("expires_in") or 3600))
        return tokens["access_token"]
