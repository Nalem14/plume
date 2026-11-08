"""The video call of an event: its link and who runs it (Google Meet, Teams, Zoom, Orneos Meet…), as macOS
finds it, to offer « Rejoindre » in Plume, the clock and the event's reminder.

Invitations rarely put the link in URL: Teams writes it in DESCRIPTION (between < >) and in
X-MICROSOFT-ONLINEMEETINGEXTERNALLINK, Google in X-GOOGLE-CONFERENCE and DESCRIPTION, Zoom in LOCATION.
Pure Python, no dependency: every part of the system imports it.
"""
import re

# (host or path pattern, name shown); the first link that matches wins, in the order of the fields given
PROVIDERS = [
    (r"meet\.google\.com/[a-z0-9-]+", "Google Meet"),
    (r"teams\.microsoft\.com/(?:l/meetup-join|meet)/", "Teams"),
    (r"teams\.live\.com/meet/", "Teams"),
    (r"(?:[\w-]+\.)?zoom\.us/(?:j|my|w)/", "Zoom"),
    (r"(?:[\w-]+\.)?webex\.com/", "Webex"),
    (r"whereby\.com/", "Whereby"),
    (r"meet\.jit\.si/|jitsi", "Jitsi"),
    (r"facetime\.apple\.com/", "FaceTime"),
    (r"/call/[a-z0-9]+|spreed|meet\.orneos\.eu", "Orneos Meet"),
]
FIELDS = ("URL", "CONFERENCE", "X-GOOGLE-CONFERENCE", "X-MICROSOFT-ONLINEMEETINGEXTERNALLINK",
          "X-MICROSOFT-SKYPETEAMSMEETINGURL", "LOCATION", "DESCRIPTION")
LINK = re.compile(r"https://[^\s<>\"'\\]+", re.I)
# a call of our cloud: Meet joins it on the computer (meet.orneos.eu/<code> is the short form of /call/<code>)
OURS = re.compile(r"^https://(?:(?:app\.orneos\.eu|cloud\.bucaille-thommy\.fr)(?:/index\.php)?/call/|meet\.orneos\.eu/)"
                  r"([a-z0-9]{4,30})(?:[/?#]|$)", re.I)
JOIN = {"fr": "Rejoindre", "en": "Join", "de": "Beitreten"}


def find(*texts):
    """(url, provider name) of the first video call link in these texts, else ("", "")."""
    for text in texts:
        for url in LINK.findall(str(text or "")):
            url = url.rstrip(".,;:)]>")
            for pattern, name in PROVIDERS:
                if re.search(pattern, url, re.I):
                    return url, name
    return "", ""


def in_event(get):
    """The call of a VEVENT; get(name) gives the text of one of its properties ("" when absent)."""
    return find(*(get(name) for name in FIELDS))


def join_label(lang):
    return JOIN.get((lang or "en")[:2], JOIN["en"])


def talk_token(url):
    """The conversation of an Orneos Meet link of our cloud, else ""."""
    m = OURS.match(str(url or "").strip())
    return m.group(1).lower() if m else ""


def join(url):
    """An Orneos Meet link joins in the Meet app when it is there (Orneos OS, Plume). False: open it elsewhere."""
    token = talk_token(url)
    if not token:
        return False
    try:
        import system  # noqa: PLC0415 - only the apps of the system have it
    except ImportError:
        return False
    return system.has_app("meet") and bool(system.launch("meet", f"--call={token}"))
