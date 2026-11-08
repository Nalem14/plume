"""Contacts from a CSV file: the exports of Google Contacts and Outlook (English, French, German headers).

Each row becomes the editor's fields (vcard.build writes the card). Unknown columns are left aside; a row
without a name, an address or a number is skipped.
"""
import csv
import io
import re

# a header, folded (lower case, no accents, single spaces) → where it goes
NAME = {
    "given": ("first name", "given name", "prenom", "vorname"),
    "family": ("last name", "family name", "nom", "nachname", "nom de famille"),
    "fn": ("name", "display name", "nom complet", "full name", "anzeigename"),
    "nickname": ("nickname", "surnom", "spitzname"),
    "org": ("organization name", "organization 1 - name", "company", "societe", "entreprise", "firma"),
    "title": ("organization title", "organization 1 - title", "job title", "fonction", "position", "titre"),
    "bday": ("birthday", "anniversaire", "date de naissance", "geburtstag"),
    "note": ("notes", "note", "notizen"),
    "url": ("website 1 - value", "web page", "page web", "site web", "webseite"),
    "categories": ("labels", "group membership", "categories", "kategorien"),
}
# Outlook's fixed columns: (header words, kind)
EMAILS = (("e-mail address", "home"), ("e-mail 2 address", "work"), ("e-mail 3 address", "other"),
          ("adresse de messagerie", "home"), ("adresse de messagerie 2", "work"), ("adresse de messagerie 3", "other"),
          ("e-mail-adresse", "home"), ("e-mail 2: adresse", "work"), ("e-mail 3: adresse", "other"),
          ("email", "home"), ("e-mail", "home"), ("courriel", "home"))
PHONES = (("mobile phone", "cell"), ("business phone", "work"), ("business phone 2", "work"), ("home phone", "home"),
          ("home phone 2", "home"), ("other phone", "other"), ("primary phone", "other"), ("business fax", "fax"),
          ("home fax", "fax"), ("tel. mobile", "cell"), ("telephone mobile", "cell"), ("portable", "cell"),
          ("tel. bureau", "work"), ("telephone (bureau)", "work"), ("tel. domicile", "home"),
          ("telephone (domicile)", "home"), ("autre telephone", "other"), ("telecopie (bureau)", "fax"),
          ("mobiltelefon", "cell"), ("telefon geschaftlich", "work"), ("telefon privat", "home"),
          ("phone", "other"), ("telephone", "other"))
ADDRESSES = {  # prefix → kind; then street / city / region / postal code / country after it
    "business": "work", "home": "home", "other": "other", "bureau": "work", "domicile": "home", "autre": "other",
    "geschaftlich": "work", "privat": "home", "weitere": "other",
}
PARTS = {"street": ("street", "rue", "strasse"), "city": ("city", "ville", "ort"),
         "region": ("state", "region", "province", "bundesland"),
         "code": ("postal code", "code postal", "postleitzahl"), "country": ("country/region", "country", "pays", "land")}
KINDS = {"mobile": "cell", "cell": "cell", "work": "work", "home": "home", "fax": "fax", "main": "work",
         "domicile": "home", "travail": "work", "bureau": "work", "portable": "cell"}


def fold(text):
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text.replace("_", " ")).strip()


def is_csv(path_text, head):
    return path_text.lower().endswith((".csv", ".txt")) or ("," in head.split("\n")[0] and "BEGIN:VCARD" not in head.upper())


def _reader(text):
    first = text.split("\n", 1)[0]
    delimiter = ";" if first.count(";") > first.count(",") else "\t" if first.count("\t") > first.count(",") else ","
    return csv.reader(io.StringIO(text), delimiter=delimiter)


def decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            text = data.decode(encoding)
            if encoding == "utf-16" and "\x00" in text:
                continue
            return text
        except UnicodeDecodeError:
            continue
    return data.decode("cp1252", "replace")          # Outlook on Windows


def _kind(text):
    words = fold(text).replace("*", " ").split()
    return next((KINDS[w] for w in words if w in KINDS), "other")


def parse(text):
    rows = list(_reader(text))
    if len(rows) < 2:
        return []
    heads = [fold(h) for h in rows[0]]
    out = []
    for row in rows[1:]:
        row = row + [""] * (len(heads) - len(row))
        cells = {h: row[i].strip() for i, h in enumerate(heads) if h and row[i].strip()}
        if not cells:
            continue
        fields = {"emails": [], "phones": [], "addresses": []}
        for key, names in NAME.items():
            for name in names:
                if cells.get(name):
                    fields.setdefault(key, cells[name])
                    break
        fields["categories"] = fields.get("categories") or ""
        if fields["categories"]:
            # Google: « Amis ::: * myContacts »
            fields["categories"] = [c.strip() for c in re.split(r":::|;|,", fields["categories"])
                                    if c.strip() and not c.strip().startswith("*") and c.strip() != "myContacts"]
        else:
            fields["categories"] = []
        if fields.get("bday"):
            fields["bday"] = _date(fields["bday"])
        # Google: « E-mail 1 - Type », « E-mail 1 - Value » (several values joined by « ::: »)
        for head, value in cells.items():
            m = re.fullmatch(r"(e-mail|phone|address) (\d+) - (value|formatted|street|city|region|postal code|country)", head)
            if not m:
                continue
            kind = _kind(cells.get(f"{m.group(1)} {m.group(2)} - type", ""))
            if m.group(1) == "e-mail" and m.group(3) == "value":
                fields["emails"] += [{"type": kind if kind != "cell" else "other", "value": v.strip()}
                                     for v in value.split(":::") if v.strip()]
            elif m.group(1) == "phone" and m.group(3) == "value":
                fields["phones"] += [{"type": kind, "value": v.strip()} for v in value.split(":::") if v.strip()]
        for n in sorted({h.split(" - ")[0] for h in cells if re.fullmatch(r"address \d+ - .*", h)}):
            adr = {"type": _kind(cells.get(f"{n} - type", "")), "street": cells.get(f"{n} - street", ""),
                   "city": cells.get(f"{n} - city", ""), "region": cells.get(f"{n} - region", ""),
                   "code": cells.get(f"{n} - postal code", ""), "country": cells.get(f"{n} - country", "")}
            if not any(adr[k] for k in ("street", "city", "code", "country")) and cells.get(f"{n} - formatted"):
                adr["street"] = cells[f"{n} - formatted"]
            if any(adr[k] for k in ("street", "city", "code", "country")):
                fields["addresses"].append(adr)
        # Outlook's fixed columns
        for name, kind in EMAILS:
            if cells.get(name) and "@" in cells[name] and all(e["value"] != cells[name] for e in fields["emails"]):
                fields["emails"].append({"type": kind, "value": cells[name]})
        for name, kind in PHONES:
            if cells.get(name) and all(p["value"] != cells[name] for p in fields["phones"]):
                fields["phones"].append({"type": kind, "value": cells[name]})
        for prefix, kind in ADDRESSES.items():
            adr = {"type": kind}
            for part, words in PARTS.items():
                adr[part] = next((cells[h] for h in cells for w in words
                                  if h in (f"{prefix} {w}", f"{w} ({prefix})", f"{w} {prefix}", f"{prefix}: {w}")), "")
            if any(adr[k] for k in ("street", "city", "code", "country")):
                fields["addresses"].append(adr)
        if not fields.get("fn") and not fields.get("given") and not fields.get("family"):
            fields["fn"] = fields.get("org") or (fields["emails"][0]["value"] if fields["emails"] else "")
        if fields.get("fn") or fields.get("given") or fields.get("family") or fields["emails"] or fields["phones"]:
            out.append(fields)
    return out


def _date(text):
    text = text.strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text) or re.fullmatch(r"--(\d{1,2})-(\d{1,2})", text)
    if m and len(m.groups()) == 3:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    if m:
        return f"--{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
    if m:
        # Outlook writes the date of the system: day first in Europe, month first in the US
        a, b, year = int(m.group(1)), int(m.group(2)), m.group(3)
        day, month = (a, b) if a > 12 or b <= 12 else (b, a)
        if year in ("1604", "0000"):
            return f"--{month:02d}-{day:02d}"
        return f"{year}-{month:02d}-{day:02d}"
    return ""
