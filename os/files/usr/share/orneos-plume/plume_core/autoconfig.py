"""Finding the servers of an external mailbox from its address alone, like Thunderbird does.

In order: the providers Plume knows (with what they ask for: an app password, or nothing possible yet), by
the address or, for a domain of its own, by where its mail arrives (MX: Google Workspace, Microsoft 365…),
the provider's own autoconfig file, Thunderbird's database (ISPDB, it only learns the domain), then the
usual names (imap.<domain>, mail.<domain>) tried for real. Every candidate is checked with the password
before being kept, so a wrong guess never ends up in the settings.
"""
import re
import secrets
import smtplib
import socket
import ssl
import struct
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET

from plume_core import imap

TIMEOUT = 8

# note: "app_password" (the account password is refused: an app password is needed), "oauth" (the provider
# only accepts its own sign-in page, which Plume does not offer yet)
KNOWN = {
    "gmail.com": ("imap.gmail.com", "smtp.gmail.com", "app_password", False),
    "googlemail.com": ("imap.gmail.com", "smtp.gmail.com", "app_password", False),
    "yahoo.com": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com", "app_password", True),
    "yahoo.fr": ("imap.mail.yahoo.com", "smtp.mail.yahoo.com", "app_password", True),
    "icloud.com": ("imap.mail.me.com", "smtp.mail.me.com", "app_password", True),
    "me.com": ("imap.mail.me.com", "smtp.mail.me.com", "app_password", True),
    "mac.com": ("imap.mail.me.com", "smtp.mail.me.com", "app_password", True),
    "outlook.com": (None, None, "oauth", True),
    "outlook.fr": (None, None, "oauth", True),
    "hotmail.com": (None, None, "oauth", True),
    "hotmail.fr": (None, None, "oauth", True),
    "live.com": (None, None, "oauth", True),
    "live.fr": (None, None, "oauth", True),
    "msn.com": (None, None, "oauth", True),
    "proton.me": (None, None, "bridge", True),
    "protonmail.com": (None, None, "bridge", True),
    "orange.fr": ("imap.orange.fr", "smtp.orange.fr", "", True),
    "wanadoo.fr": ("imap.orange.fr", "smtp.orange.fr", "", True),
    "free.fr": ("imap.free.fr", "smtp.free.fr", "", True),
    "sfr.fr": ("imap.sfr.fr", "smtp.sfr.fr", "", True),
    "neuf.fr": ("imap.sfr.fr", "smtp.sfr.fr", "", True),
    "laposte.net": ("imap.laposte.net", "smtp.laposte.net", "", True),
    "gmx.fr": ("imap.gmx.net", "mail.gmx.net", "", True),
    "gmx.de": ("imap.gmx.net", "mail.gmx.net", "", True),
    "gmx.net": ("imap.gmx.net", "mail.gmx.net", "", True),
    "web.de": ("imap.web.de", "smtp.web.de", "", True),
    "posteo.de": ("posteo.de", "posteo.de", "", True),
    "mailbox.org": ("imap.mailbox.org", "smtp.mailbox.org", "", True),
}


# a domain of its own hosted by a known provider, found by the end of its MX: (imap, smtp, note, saveSent)
HOSTED = (
    ((".google.com", ".googlemail.com"), ("imap.gmail.com", "smtp.gmail.com", "workspace", False)),
    ((".mail.protection.outlook.com", ".outlook.com"), (None, None, "oauth", True)),
    ((".protonmail.ch", ".proton.me"), (None, None, "bridge", True)),
    ((".zoho.eu",), ("imap.zoho.eu", "smtp.zoho.eu", "", True)),
    ((".zoho.com",), ("imap.zoho.com", "smtp.zoho.com", "", True)),
)
_hosted = {}                      # domain → provider found by its MX (or None), for this session
SMTP_PORTS = {"smtp.mail.me.com": (587, "starttls")}       # the providers whose SMTP is not on 465


def mx_hosts(domain):
    """The MX hosts of a domain, asked to the resolver of this computer (nothing goes to a third party)."""
    try:
        name = domain.encode("idna")
    except UnicodeError:
        return []
    if sys.platform == "win32":
        return _mx_nslookup(domain)
    servers = []
    try:
        with open("/etc/resolv.conf") as conf:
            servers = [line.split()[1] for line in conf if line.startswith("nameserver") and len(line.split()) > 1]
    except OSError:
        pass
    for server in servers[:3]:
        hosts = _mx_udp(name, server.split("%")[0])
        if hosts is not None:
            return hosts
    return []


def _mx_udp(name, server):
    """One MX query over UDP: the hosts, or None when this server did not answer."""
    qid = secrets.randbits(16)
    question = b"".join(bytes([len(p)]) + p for p in name.rstrip(b".").split(b".")) + b"\0"
    packet = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0) + question + struct.pack(">HH", 15, 1)
    family = socket.AF_INET6 if ":" in server else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as sock:
            sock.settimeout(3)
            sock.sendto(packet, (server, 53))
            data = sock.recv(4096)
    except OSError:
        return None
    try:
        rid, flags, qd, an = struct.unpack(">HHHH", data[:8])
        if rid != qid:
            return None
        if flags & 0x000F:                       # NXDOMAIN, refused…: no MX
            return []

        def read_name(pos):
            labels, jumped, end = [], False, pos
            for _ in range(64):
                length = data[pos]
                if length & 0xC0 == 0xC0:
                    if not jumped:
                        end = pos + 2
                    pos, jumped = ((length & 0x3F) << 8) | data[pos + 1], True
                    continue
                if length == 0:
                    return ".".join(labels), (end if jumped else pos + 1)
                labels.append(data[pos + 1:pos + 1 + length].decode("ascii", "replace"))
                pos += 1 + length
            raise ValueError("name loop")

        pos = 12
        for _ in range(qd):
            pos = read_name(pos)[1] + 4
        hosts = []
        for _ in range(an):
            pos = read_name(pos)[1]
            kind, _cls, _ttl, size = struct.unpack(">HHIH", data[pos:pos + 10])
            pos += 10
            if kind == 15:
                hosts.append((struct.unpack(">H", data[pos:pos + 2])[0], read_name(pos + 2)[0].lower()))
            pos += size
        return [host for _pref, host in sorted(hosts)]
    except (struct.error, IndexError, ValueError):
        return None


def _mx_nslookup(domain):
    """Windows has no resolv.conf: its own nslookup asks the resolver of the system."""
    try:
        out = subprocess.run(["nslookup", "-type=mx", domain], capture_output=True, text=True, timeout=8,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [host.rstrip(".").lower() for host in re.findall(r"exchanger\s*=\s*(\S+)", out)]


def provider(address, lookup=True):
    """(imap, smtp, note, saveSent) of the provider behind this address, or None when unknown. A domain
    of its own is looked up by its MX (slow: lookup=False only answers from what is known already)."""
    domain = address.rpartition("@")[2].lower().strip()
    if domain in KNOWN:
        return KNOWN[domain]
    if domain in _hosted or not lookup or "." not in domain:
        return _hosted.get(domain)
    found = None
    for host in mx_hosts(domain):
        found = next((p for ends, p in HOSTED if host.endswith(ends)), None)
        if found:
            break
    _hosted[domain] = found
    return found


def looked_up(address):
    """True when provider() answers this address without a lookup."""
    domain = address.rpartition("@")[2].lower().strip()
    return domain in KNOWN or domain in _hosted


def oauth_provider(address, lookup=False):
    """"google" or "microsoft" when this address can sign in with that provider's page, else ""."""
    found = provider(address, lookup) or (None, None, "", True)
    return "google" if found[0] == "imap.gmail.com" else "microsoft" if found[2] == "oauth" else ""


def note_for(address, lookup=False):
    """What the provider of this address asks for: "", "app_password", "workspace" (Google with a domain
    of its own: an app password, which its administrator may have turned off), "oauth" or "bridge"."""
    return (provider(address, lookup) or (None, None, "", True))[2]


def _server(host, port, security):
    return {"host": host, "port": int(port), "security": security}


def _from_xml(data, address):
    """Servers of a Mozilla autoconfig file (clientConfig v1.1), best first."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    local = address.partition("@")[0]

    def login_of(node):
        user = (node.findtext("username") or "%EMAILADDRESS%").strip()
        return user.replace("%EMAILADDRESS%", address).replace("%EMAILLOCALPART%", local) \
            .replace("%EMAILDOMAIN%", address.rpartition("@")[2])

    def security_of(node):
        kind = (node.findtext("socketType") or "").upper()
        return "ssl" if kind == "SSL" else "starttls" if kind == "STARTTLS" else "plain"

    imaps = [n for n in root.iter("incomingServer") if n.get("type") == "imap" and security_of(n) != "plain"]
    smtps = [n for n in root.iter("outgoingServer") if n.get("type") == "smtp" and security_of(n) != "plain"]
    if not imaps or not smtps:
        return None
    i, o = imaps[0], smtps[0]
    return {"imap": _server(i.findtext("hostname"), i.findtext("port") or 993, security_of(i)),
            "smtp": _server(o.findtext("hostname"), o.findtext("port") or 465, security_of(o)),
            "login": login_of(i)}


def _fetch(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Orneos Plume"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return res.read(200_000)
    except Exception:
        return None


def _reachable(host, port):
    try:
        socket.create_connection((host, port), timeout=4).close()
        return True
    except OSError:
        return False


def candidates(address):
    """Possible settings for this address, most likely first (not checked yet)."""
    domain = address.rpartition("@")[2].lower()
    found = []
    known = provider(address)
    if known and known[0]:
        found.append({"imap": _server(known[0], 993, "ssl"), "smtp": _server(known[1], *SMTP_PORTS.get(known[1], (465, "ssl"))),
                      "login": address})
    if not known:
        for url in (f"https://autoconfig.{domain}/mail/config-v1.1.xml?emailaddress={address}",
                    f"https://autoconfig.thunderbird.net/v1.1/{domain}"):
            data = _fetch(url)
            config = _from_xml(data, address) if data else None
            if config:
                found.append(config)
                break
        for host in (f"imap.{domain}", f"mail.{domain}", domain):
            if _reachable(host, 993):
                smtp_host = f"smtp.{domain}" if host.startswith("imap.") else host
                port = 465 if _reachable(smtp_host, 465) else 587
                found.append({"imap": _server(host, 993, "ssl"),
                              "smtp": _server(smtp_host, port, "ssl" if port == 465 else "starttls"), "login": address})
                break
    return found


def check_imap(config, password, xoauth2=False):
    """"" when the mailbox opens, else "auth", "offline" or "server". xoauth2: password is an access token."""
    server = config["imap"]
    try:
        imap.Connection(config.get("login") or "", password, timeout=15,
                        server=(server["host"], int(server["port"]), server["security"]), xoauth2=xoauth2).close()
        return ""
    except imap.MailError as error:
        return error.kind


def smtp_session(server, timeout=20):
    """An SMTP session on (host, port, security), not logged in yet."""
    host, port, security = server
    if security == "ssl":
        return smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=timeout)
    session = smtplib.SMTP(host, port, timeout=timeout)
    if security == "starttls":
        session.starttls(context=ssl.create_default_context())
    return session


def smtp_login(session, user, password, xoauth2=False):
    """Signs in on an SMTP session: with the password, or with an OAuth access token (XOAUTH2)."""
    if not xoauth2:
        session.login(user, password)
        return
    session.ehlo_or_helo_if_needed()
    said = []

    def respond(challenge=None):
        if said:                        # the server explained a refusal: end the exchange
            return ""
        said.append(1)
        return f"user={user}\x01auth=Bearer {password}\x01\x01"
    session.auth("XOAUTH2", respond, initial_response_ok=True)


def check_smtp(config, password, xoauth2=False):
    server = config["smtp"]
    try:
        with smtp_session((server["host"], int(server["port"]), server["security"])) as session:
            smtp_login(session, config.get("login") or "", password, xoauth2)
        return ""
    except smtplib.SMTPAuthenticationError:
        return "auth"
    except (smtplib.SMTPException, OSError, ssl.SSLError):
        return "offline"


def discover(address, password):
    """(settings, "") for the first candidate that opens with this password, else (None, reason):
    "oauth" / "bridge" (the provider needs what Plume cannot do yet), "auth" (refused: wrong password, or an
    app password needed), "notfound" (no server answered)."""
    note = note_for(address, lookup=True)
    if note in ("oauth", "bridge"):
        return None, note
    reason = "notfound"
    for config in candidates(address):
        result = check_imap(config, password)
        if not result:
            config["saveSent"] = (provider(address) or (None, None, "", True))[3]
            return config, ""
        if result == "auth":
            reason = "auth"
    return None, reason

