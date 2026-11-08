"""Which site an address belongs to (the same rules as the browser extension, extension/lib/sites.js), and the
sites that accept a verification code from an authenticator app.

A login matches a site when both are on the same registrable domain: accounts.example.com and
www.example.com match, example.com.evil.net does not. A short list of shared suffixes covers the common
cases without shipping the full public suffix list.
"""
import re
from urllib.parse import urlsplit

SHARED = {
    "co.uk", "org.uk", "gov.uk", "ac.uk", "me.uk", "com.au", "net.au", "org.au", "co.nz", "co.jp", "ne.jp", "or.jp",
    "com.br", "com.mx", "com.ar", "com.tr", "com.cn", "com.hk", "com.sg", "co.in", "co.za", "co.kr", "com.tw",
    "gouv.fr", "asso.fr", "nom.fr", "com.fr", "tm.fr", "gv.at", "co.at", "or.at", "com.es", "com.pl", "com.pt", "co.il",
    "github.io", "gitlab.io", "netlify.app", "vercel.app", "pages.dev", "herokuapp.com", "blogspot.com", "web.app",
    "firebaseapp.com",
}

# Sites where a code from an authenticator app (TOTP) can be turned on: each one is suggested in the security
# view when its login has no code yet. Registrable domains, as site() gives them.
TWO_FACTOR = {
    "google.com", "gmail.com", "youtube.com", "microsoft.com", "live.com", "outlook.com", "office.com", "apple.com",
    "icloud.com", "amazon.com", "amazon.fr", "amazon.de", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "linkedin.com", "github.com", "gitlab.com", "bitbucket.org", "atlassian.com", "paypal.com", "dropbox.com",
    "discord.com", "twitch.tv", "steampowered.com", "steamcommunity.com", "epicgames.com", "ubisoft.com", "ea.com",
    "battle.net", "blizzard.com", "nintendo.com", "playstation.com", "xbox.com", "ovh.com", "ovhcloud.com",
    "ovh.net", "free.fr", "proton.me", "protonmail.com", "tiktok.com", "snapchat.com", "reddit.com", "binance.com",
    "coinbase.com", "kraken.com", "revolut.com", "stripe.com", "shopify.com", "wordpress.com", "cloudflare.com",
    "godaddy.com", "gandi.net", "ionos.fr", "ionos.com", "ionos.de", "slack.com", "notion.so", "zoom.us",
    "adobe.com", "ebay.com", "ebay.fr", "ebay.de", "airbnb.com", "airbnb.fr", "booking.com", "uber.com",
    "yahoo.com", "mozilla.org", "firefox.com", "npmjs.com", "docker.com", "digitalocean.com", "hetzner.com",
    "scaleway.com", "infomaniak.com", "mailchimp.com", "hubspot.com", "salesforce.com", "figma.com", "canva.com",
    "trello.com", "asana.com", "wise.com", "kucoin.com", "bitpanda.com", "okx.com", "pinterest.com", "tumblr.com",
    "mastodon.social", "vinted.fr", "leboncoin.fr", "lydia-app.com", "qonto.com", "shine.fr", "malt.fr",
    "doctolib.fr", "orneos.eu",
}


def host(value):
    """Host of a url or of a bare domain ("example.com/login"), lower-case, without "www."; "" when none."""
    text = str(value or "").strip()
    if not text:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.I):
        if re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", text, re.I):
            return ""                       # another scheme (javascript:, mailto:), not a host:port
        text = "https://" + text
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return ""
    name = parts.hostname.lower().rstrip(".")
    return name[4:] if name.startswith("www.") else name


def site(name):
    """Registrable domain of a host: mail.google.com → google.com, a.b.co.uk → b.co.uk."""
    if not name:
        return ""
    if re.fullmatch(r"[\d.]+", name) or ":" in name or "." not in name:
        return name
    labels = name.split(".")
    last2 = ".".join(labels[-2:])
    return ".".join(labels[-3:]) if last2 in SHARED and len(labels) >= 3 else last2


def site_of(url):
    return site(host(url))


def link(url):
    """An address that opens in the browser: https:// added to a bare domain, nothing for other schemes."""
    text = str(url or "").strip()
    if not text:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.I):
        if re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", text, re.I):
            return ""
        text = "https://" + text
    return text if host(text) else ""


def two_factor(url):
    return site_of(url) in TWO_FACTOR
