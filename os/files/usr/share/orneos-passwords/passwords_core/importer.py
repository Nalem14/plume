"""Import from another password manager: the CSV export of Chrome, Edge, Brave, Firefox, Safari / Apple
Passwords, Bitwarden, 1Password, KeePassXC, Proton Pass, Dashlane, NordPass, LastPass, or any CSV whose header
names its columns. Read here, nothing is sent until the person confirms (then entries go through the same
queue as the ones typed by hand: an import works offline too).
"""
import csv
import io

# column → the names other apps give it (lower-case)
COLUMNS = {
    "label": ("name", "title", "nom", "titel", "account", "item name", "login_name"),
    "url": ("url", "login_uri", "website", "web site", "uri", "urls", "adresse", "site", "login url", "origin"),
    "username": ("username", "login_username", "user", "login", "email", "e-mail", "identifiant", "benutzername",
                 "user name", "username/email"),
    "password": ("password", "login_password", "mot de passe", "passwort", "pass"),
    "notes": ("notes", "note", "comments", "extra", "commentaire", "notizen"),
    "otp": ("totp", "login_totp", "otpauth", "otp", "otpsecret", "otp secret", "one-time password", "2fa"),
    "favorite": ("favorite", "favourite", "fav", "favori"),
    "folder": ("folder", "group", "grouping", "vault", "category", "dossier"),
}
FORMATS = (
    ("bitwarden", {"login_uri", "login_password"}),
    ("firefox", {"httprealm", "formactionorigin"}),
    ("keepassxc", {"group", "title", "totp"}),
    ("onepassword", {"title", "otpauth"}),
    ("apple", {"title", "url", "otpauth"}),
    ("proton", {"vault", "createtime"}),
    ("dashlane", {"otpsecret"}),
    ("lastpass", {"grouping", "extra"}),
    ("chrome", {"name", "url", "username", "password"}),
)


def _decode(raw: bytes):
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = raw.decode(encoding)
            if "\x00" not in text:
                return text
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def read(path):
    """{format, rows: [{label, url, username, password, notes, otp, favorite}], skipped} or {error}."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read(32 * 1024 * 1024)
    except OSError:
        return {"error": "unreadable"}
    text = _decode(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        return {"error": "empty"}
    where = {}
    for key, names in COLUMNS.items():
        for i, h in enumerate(header):
            if h in names and key not in where:
                where[key] = i
    if "password" not in where:
        return {"error": "columns"}
    found = set(header)
    name = next((n for n, needed in FORMATS if needed <= found), "csv")
    rows, skipped = [], 0
    for line in reader:
        def get(key):
            i = where.get(key)
            return line[i].strip() if i is not None and i < len(line) else ""
        password = get("password")
        if name == "bitwarden" and "type" in header and line[header.index("type")].strip() not in ("login", ""):
            skipped += 1                            # cards, notes, identities: not passwords
            continue
        if not password and not get("otp"):
            skipped += 1
            continue
        url = get("url").split(",")[0].strip()
        if name == "firefox" and url.startswith("chrome://"):
            skipped += 1
            continue
        rows.append({"label": get("label"), "url": url, "username": get("username"), "password": password,
                     "notes": get("notes"), "otp": get("otp"), "folder": get("folder"),
                     "favorite": get("favorite").lower() in ("1", "true", "yes", "oui", "x")})
    return {"format": name, "rows": rows, "skipped": skipped}
