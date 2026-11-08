"""Contacts for Plume: read a vCard (3.0 or 4.0) into plain fields, and write fields back into it.

Writing keeps every line Plume does not manage (photos from the phone, custom fields, labels): only
the properties of the editor are replaced. New cards are vCard 3.0, like the cloud's own.
"""
import base64
import re
import uuid
from datetime import datetime, timezone

# vCard property → the editor's field: a property is replaced only when its field is given
MANAGED = {"FN": "fn", "N": "given", "ORG": "org", "TITLE": "title", "EMAIL": "emails", "TEL": "phones",
           "ADR": "addresses", "BDAY": "bday", "NOTE": "note", "CATEGORIES": "categories", "URL": "url",
           "NICKNAME": "nickname", "ANNIVERSARY": "anniversary", "X-ANNIVERSARY": "anniversary",
           "RELATED": "related", "REV": None, "PRODID": None}
PRODID = "-//Orneos//Plume//FR"
KINDS = {"cell", "work", "home", "fax"}
RELATIONS = ("spouse", "child", "parent", "sibling", "friend", "colleague", "assistant", "other")
# Apple's own labels (X-ABLabel of a group), written _$!<Mobile>!$_: the ones that are a kind of ours
APPLE = {"mobile": "cell", "iphone": "cell", "home": "home", "work": "work", "other": "other", "homefax": "fax",
         "workfax": "fax", "otherfax": "fax", "main": "work"}
FIELDS = ("fn", "given", "family", "org", "title", "nickname", "bday", "anniversary", "note", "url", "categories",
          "emails", "phones", "addresses", "related", "photo")


def _unfold(text):
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _split(line):
    """(group, NAME, {PARAM: [values]}, value) of one content line."""
    head, _, value = _split_unquoted(line, ":")
    parts = _split_all_unquoted(head, ";")
    name = parts[0]
    group = ""
    if "." in name:
        group, name = name.split(".", 1)
    params = {}
    for part in parts[1:]:
        key, _, val = part.partition("=")
        key = key.upper()
        if not val:                        # vCard 2.1 style: TEL;CELL
            key, val = "TYPE", key
        values = val.strip('"').split(",") if key == "TYPE" else _split_all_unquoted(val, ",")
        for item in values:
            params.setdefault(key, []).append(item.strip('"'))
    return group, name.upper(), params, value


def _split_unquoted(text, sep):
    quoted = False
    for i, ch in enumerate(text):
        if ch == '"':
            quoted = not quoted
        elif ch == sep and not quoted:
            return text[:i], sep, text[i + 1:]
    return text, "", ""


def _split_all_unquoted(text, sep):
    out, current, quoted = [], "", False
    for ch in text:
        if ch == '"':
            quoted = not quoted
        if ch == sep and not quoted:
            out.append(current)
            current = ""
        else:
            current += ch
    out.append(current)
    return out


def _unescape(value):
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


def _escape(value):
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _components(value):
    """Structured value (N, ADR, ORG): split on unescaped ;"""
    return [_unescape(part) for part in re.split(r"(?<!\\);", value)]


def _types(params):
    return [t for t in params.get("TYPE", []) if t]


def _kind(params, phone=False):
    types = {t.lower() for t in _types(params)}
    if phone and "fax" in types:
        return "fax"
    for wanted in ("cell", "work", "home"):
        if wanted in types:
            return wanted
    return "other"


def _apple_label(raw):
    """_$!<Mobile>!$_ → (kind or "", shown text); a label typed on the phone → ("", itself)."""
    m = re.fullmatch(r"_\$!<(.+)>!\$_", raw.strip())
    if not m:
        return "", raw.strip()
    inner = m.group(1)
    return APPLE.get(inner.lower().replace(" ", ""), ""), inner


def _item(name, head, params, raw_value, labels, group, **extra):
    """One address, number or postal address, with what it takes to write it back as it was."""
    kind = _kind(params, phone=name == "TEL") if name != "RELATED" else _relation(params)
    item = {"type": kind, "label": "", "pref": _pref(params), "_head": head, "_kind": kind, "_value": raw_value,
            "_extra": [t for t in _types(params) if t.lower() not in KINDS | {"other"} | set(RELATIONS)]}
    raw = labels.get(group, "") if group else ""
    if raw:
        apple_kind, shown = _apple_label(raw)
        if apple_kind:
            item["type"] = item["_kind"] = apple_kind
        else:
            item["label"] = shown
        item["_label"] = raw
        item["_labelShown"] = item["label"]
    item.update(extra)
    return item


def _pref(params):
    return "pref" in {t.lower() for t in _types(params)} or bool(params.get("PREF"))


def _relation(params):
    types = {t.lower() for t in _types(params)}
    for wanted in RELATIONS:
        if wanted in types:
            return wanted
    return {"co-worker": "colleague", "kin": "other", "sweetheart": "spouse"}.get(next(iter(types), ""), "other")


def parse(text):
    card = {"uid": "", "fn": "", "given": "", "family": "", "org": "", "title": "", "nickname": "", "emails": [],
            "phones": [], "addresses": [], "related": [], "bday": "", "anniversary": "", "note": "", "categories": [],
            "photo": "", "url": "", "urls": [], "cloud": ""}
    lines = _unfold(text)
    labels = {}
    for line in lines:
        try:
            group, name, _, value = _split(line)
        except ValueError:
            continue
        if group and name == "X-ABLABEL":
            labels[group] = _unescape(value)
    for line in lines:
        try:
            group, name, params, value = _split(line)
        except ValueError:
            continue
        head = _split_unquoted(line, ":")[0]
        head = head.split(".", 1)[1] if group else head
        if name == "UID":
            card["uid"] = value.strip()
        elif name == "FN":
            card["fn"] = _unescape(value).strip()
        elif name == "N":
            parts = _components(value) + ["", ""]
            card["family"], card["given"] = parts[0].strip(), parts[1].strip()
        elif name == "ORG":
            card["org"] = " · ".join(p for p in _components(value) if p.strip())
        elif name == "TITLE":
            card["title"] = _unescape(value).strip()
        elif name == "NICKNAME" and not card["nickname"]:
            card["nickname"] = _unescape(value).strip()
        elif name == "EMAIL" and value.strip():
            card["emails"].append(_item(name, head, params, value, labels, group, value=value.strip().removeprefix("mailto:")))
        elif name == "TEL" and value.strip():
            card["phones"].append(_item(name, head, params, value, labels, group, value=value.strip().removeprefix("tel:")))
        elif name == "ADR":
            parts = (_components(value) + [""] * 7)[:7]
            if any(p.strip() for p in parts):
                card["addresses"].append(_item(name, head, params, value, labels, group, pobox=parts[0], ext=parts[1],
                                               street=parts[2].strip(), city=parts[3].strip(), region=parts[4].strip(),
                                               code=parts[5].strip(), country=parts[6].strip()))
        elif name == "RELATED" and value.strip():
            card["related"].append(_item(name, head, params, value, labels, group, value=_unescape(value).strip()))
        elif name == "BDAY" and not card["bday"]:
            card["bday"] = _bday(value.strip(), params)
        elif name in ("ANNIVERSARY", "X-ANNIVERSARY") and not card["anniversary"]:
            card["anniversary"] = _bday(value.strip(), params)
        elif name == "X-ABDATE" and group and _apple_label(labels.get(group, ""))[1].lower() == "anniversary" \
                and not card["anniversary"]:
            card["anniversary"] = _bday(value.strip(), params)     # the iPhone's anniversary
        elif name == "NOTE":
            card["note"] = _unescape(value).strip()
        elif name == "CATEGORIES":
            card["categories"] += [c.strip() for c in _unescape(value).split(",") if c.strip()]
        elif name == "CLOUD" and not card["cloud"]:   # federated cloud id: uid@server (team members)
            card["cloud"] = value.strip()
        elif name == "URL" and value.strip():
            card["urls"].append(value.strip())
        elif name == "PHOTO" and not card["photo"]:
            card["photo"] = _photo(params, value.strip())
    card["url"] = card["urls"][0] if card["urls"] else ""
    if not card["fn"]:
        card["fn"] = " ".join(p for p in (card["given"], card["family"]) if p) or card["org"] or \
            (card["emails"][0]["value"] if card["emails"] else "")
    return card


def _bday(value, params=None):
    """1990-12-31, or --12-31 without the year (vCard 4, or Apple's year 1604 with X-APPLE-OMIT-YEAR)."""
    params = params or {}
    if {v.lower() for v in params.get("VALUE", [])} == {"text"}:
        return ""
    value = value.split("T")[0]
    digits = value.replace("-", "")
    if value.startswith("--") and len(value) >= 6:
        return "--" + value[-5:] if "-" in value[2:] else f"--{value[2:4]}-{value[4:6]}"
    if len(digits) >= 8 and digits[:8].isdigit():
        year = digits[:4]
        omit = (params.get("X-APPLE-OMIT-YEAR") or [""])[0]
        if year == omit or year == "1604" or year == "0000":
            return f"--{digits[4:6]}-{digits[6:8]}"
        return f"{year}-{digits[4:6]}-{digits[6:8]}"
    return ""


def _photo(params, value):
    if value.startswith(("http://", "https://", "data:")):
        return value
    encoding = {e.lower() for e in params.get("ENCODING", [])}
    if "b" in encoding or "base64" in encoding:
        kind = (params.get("TYPE") or ["jpeg"])[0].lower()
        kind = {"jpg": "jpeg"}.get(kind, kind)
        try:
            base64.b64decode(value[:64] + "=" * (-len(value[:64]) % 4))
        except ValueError:
            return ""
        return f"data:image/{kind};base64,{value}"
    return ""


def _fold(line):
    raw = line.encode()
    if len(raw) <= 75:
        return line
    out, current = [], b""
    for ch in line:
        piece = ch.encode()
        if len(current) + len(piece) > (75 if not out else 74):
            out.append(current.decode())
            current = b""
        current += piece
    out.append(current.decode())
    return "\r\n ".join(out)


def _date_line(name, value, v4):
    if not value.startswith("--") or v4:
        return f"{name}:{value}"
    return f"{name};X-APPLE-OMIT-YEAR=1604:1604-{value[2:]}"


def build(fields, original=None, new_uid=False):
    """vCard text from the editor's fields, merged into the original card when there is one.
    Only the properties whose field is given are replaced; an item left as it was is written back as it
    came (its types, PREF, label), so a card from a phone loses nothing.
    fields["photo"]: None (or absent) keeps the card's photo, "" removes it, a data: URL replaces it.
    new_uid: a copy (a read-only card saved into my contacts), under its own UID."""
    kept, version, uid = [], "3.0", fields.get("uid") or str(uuid.uuid4())
    name_rest = ["", "", ""]              # middle names, prefix, suffix: not in the editor, kept
    photo = fields.get("photo")
    if photo and not photo.startswith("data:image/"):
        photo = None                      # a photo given by address stays as it is
    managed = {name for name, key in MANAGED.items() if key is None or key in fields}
    if "given" in fields or "family" in fields:
        managed.add("N")
    if photo is not None:
        managed.add("PHOTO")
    bday_kept = None
    apple_anniversary = ""                # the iPhone's own anniversary line stays while the date does not change
    if original and "anniversary" in fields:
        before = parse(original)
        for line in _unfold(original):
            try:
                group, name, params, value = _split(line)
            except ValueError:
                continue
            if name == "X-ABDATE" and group and before["anniversary"] == _bday(value.strip(), params) \
                    and not any(_split(l)[1] in ("ANNIVERSARY", "X-ANNIVERSARY") for l in _unfold(original) if ":" in l):
                apple_anniversary = group
    if original:
        lines = _unfold(original)
        parsed, dropped_groups, url_seen = [], set(), False
        for line in lines:
            try:
                group, name, params, value = _split(line)
            except ValueError:
                continue
            drop = name in managed
            if name == "URL" and drop:
                drop = not url_seen       # the editor shows the first address only: the others stay
                url_seen = True
            if name == "BDAY" and drop and not _bday(value.strip(), params):
                bday_kept = line          # a birthday in words (« vers 1980 ») the editor cannot show
                drop = False
            if name == "X-ABDATE" and group and group == apple_anniversary and \
                    fields.get("anniversary") != parse(original)["anniversary"]:
                drop = True
            if drop and group:
                dropped_groups.add(group)
            parsed.append((line, group, name, value, drop))
        for line, group, name, value, drop in parsed:
            if name in ("BEGIN", "END"):
                continue
            if name == "VERSION":
                version = value.strip() or version
                continue
            if name == "UID":
                uid = uid if new_uid else value.strip() or uid
                continue
            if name == "N":
                name_rest = (_components(value) + ["", "", "", "", ""])[2:5]
            if name == "BDAY" and line is bday_kept:
                if fields.get("bday"):
                    continue              # a date typed now takes its place
                kept.append(line)
                continue
            if drop or (group and group in dropped_groups):
                continue
            kept.append(line)
    v4 = version.startswith("4")
    used_groups = set()
    for line in kept:
        try:
            used_groups.add(_split(line)[0].lower())
        except ValueError:
            pass
    next_group = [0]

    def group_name():
        while True:
            next_group[0] += 1
            name = f"item{next_group[0]}"
            if name not in used_groups:
                used_groups.add(name)
                return name

    def typed(name, kind, extra=()):
        words = []
        if kind and kind != "other":
            word = {"cell": "CELL", "work": "WORK", "home": "HOME", "fax": "FAX"}.get(kind, kind.upper())
            words.append(word.lower() if v4 else word)
        words += [e for e in extra if e.lower() not in {w.lower() for w in words}]
        return f"{name};TYPE={','.join(words)}" if words else name

    def item_lines(name, item, value):
        """The line(s) of one item: as it came when its kind and value did not change."""
        same_kind = item.get("_head") and item.get("type") == item.get("_kind") \
            and (item.get("label") or "") == (item.get("_labelShown") or "")
        if same_kind and _item_value(name, item) == item.get("_value_parsed", _item_value_from_raw(name, item)):
            line = f"{item['_head']}:{item['_value']}"
        elif same_kind:
            line = f"{item['_head']}:{value}"
        else:
            head = typed(name, item.get("type", ""), item.get("_extra") or ())
            if name == "RELATED" and v4:
                head += ";VALUE=text"
            line = f"{head}:{value}"
        label = (item.get("label") or "").strip()
        raw_label = item.get("_label") if same_kind else ""
        if label or raw_label:
            group = group_name()
            return [f"{group}.{line}", f"{group}.X-ABLabel:{_escape(raw_label or label)}"]
        return [line]

    fn = fields.get("fn") or " ".join(p for p in (fields.get("given", ""), fields.get("family", "")) if p) \
        or fields.get("org", "") or next((e["value"] for e in fields.get("emails", []) if e.get("value")), "")
    out = ["BEGIN:VCARD", f"VERSION:{version}", f"PRODID:{PRODID}", f"UID:{uid}"]
    if "FN" in managed or not original:
        out.append(f"FN:{_escape(fn)}")
    if "N" in managed or not original:
        out.append("N:" + ";".join(_escape(p) for p in [fields.get("family", ""), fields.get("given", "")] + name_rest))
    if fields.get("nickname"):
        out.append(f"NICKNAME:{_escape(fields['nickname'])}")
    if fields.get("org"):
        # « Société · Service »: the components parse() joined
        out.append("ORG:" + ";".join(_escape(p.strip()) for p in fields["org"].split(" · ")))
    if fields.get("title"):
        out.append(f"TITLE:{_escape(fields['title'])}")
    for item in fields.get("emails", []):
        if item.get("value", "").strip():
            out += item_lines("EMAIL", item, item["value"].strip())
    for item in fields.get("phones", []):
        if item.get("value", "").strip():
            out += item_lines("TEL", item, ("tel:" if v4 and "VALUE=URI" in (item.get("_head") or "").upper() else "")
                              + item["value"].strip())
    for item in fields.get("addresses", []):
        parts = [item.get(k, "").strip() for k in ("street", "city", "region", "code", "country")]
        if any(parts):
            value = ";".join([_escape(item.get("pobox", "") or ""), _escape(item.get("ext", "") or "")]
                             + [_escape(p) for p in parts])
            out += item_lines("ADR", item, value)
    for item in fields.get("related", []):
        if item.get("value", "").strip():
            out += item_lines("RELATED", item, _escape(item["value"].strip()))
    if fields.get("bday"):
        out.append(_date_line("BDAY", fields["bday"], v4))
    if fields.get("anniversary") and not (apple_anniversary and original and
                                          fields["anniversary"] == parse(original)["anniversary"]):
        out.append(_date_line("ANNIVERSARY" if v4 else "X-ANNIVERSARY", fields["anniversary"], v4))
    if fields.get("note"):
        out.append(f"NOTE:{_escape(fields['note'])}")
    if fields.get("categories"):
        out.append("CATEGORIES:" + ",".join(_escape(c) for c in fields["categories"] if c.strip()))
    if fields.get("url"):
        out.append(f"URL:{fields['url']}")
    if photo and photo.startswith("data:image/") and ";base64," in photo:
        kind, data = photo[len("data:image/"):].split(";base64,", 1)
        out.append(f"PHOTO:{photo}" if v4 else f"PHOTO;ENCODING=b;TYPE={kind.upper()}:{data}")
    out += kept
    out.append("REV:" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    out.append("END:VCARD")
    return uid, "\r\n".join(_fold(line) for line in out) + "\r\n"


def _item_value(name, item):
    """What the editor shows of an item, to tell whether it changed."""
    if name == "ADR":
        return tuple((item.get(k) or "").strip() for k in ("street", "city", "region", "code", "country"))
    return (item.get("value") or "").strip()


def _item_value_from_raw(name, item):
    raw = item.get("_value", "")
    if name == "ADR":
        parts = (_components(raw) + [""] * 7)[:7]
        return tuple(p.strip() for p in parts[2:7])
    if name == "RELATED":
        return _unescape(raw).strip()
    return raw.strip().removeprefix("mailto:").removeprefix("tel:")


# ---- three versions of one card: mine wins where I changed something, the other side elsewhere ------
def _key(item):
    return (item.get("value") or "").strip().lower() or "|".join(
        (item.get(k) or "").strip().lower() for k in ("street", "city", "code", "country"))


def _same(a, b):
    def flat(items):
        return [(i.get("type"), i.get("label") or "", _key(i)) for i in items] if isinstance(items, list) \
            and items and isinstance(items[0], dict) else items
    return flat(a) == flat(b)


def _merge_list(base, mine, theirs):
    """Items by their value: what I added or changed is there, what I removed is gone, the rest is theirs."""
    base_keys = {_key(i): i for i in base}
    mine_keys = {_key(i): i for i in mine}
    out = []
    for item in theirs:
        k = _key(item)
        if k in base_keys and k not in mine_keys:
            continue                                   # I removed it
        if k in mine_keys and not _same([mine_keys[k]], [base_keys.get(k, {})]):
            out.append(mine_keys[k])                   # I changed its kind or label
        else:
            out.append(item)
    have = {_key(i) for i in out}
    for item in mine:
        if _key(item) not in base_keys and _key(item) not in have:
            out.append(item)                           # I added it
    return out


def merge(base_text, mine_text, theirs_text):
    """The card written again after the server refused mine (changed elsewhere meanwhile)."""
    base, mine, theirs = parse(base_text), parse(mine_text), parse(theirs_text)
    out = dict(theirs)
    for key in FIELDS:
        if key == "photo":
            continue
        if key in ("emails", "phones", "addresses", "related"):
            out[key] = _merge_list(base[key], mine[key], theirs[key])
        elif key == "categories":
            added = [c for c in mine[key] if c not in base[key]]
            removed = {c for c in base[key] if c not in mine[key]}
            out[key] = [c for c in theirs[key] if c not in removed] + [c for c in added if c not in theirs[key]]
        elif not _same(mine[key], base[key]):
            out[key] = mine[key]
    out["photo"] = (mine["photo"] or "") if mine["photo"] != base["photo"] else None
    out["uid"] = theirs["uid"] or mine["uid"]
    return build(out, theirs_text)[1]


def complete(existing, extra):
    """existing's fields completed with what extra knows and it does not (an imported card of the same
    person, a duplicate merged into it); nothing of existing is replaced. Returns (fields, changed)."""
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in existing.items()}
    changed = False
    for key in ("given", "family", "org", "title", "nickname", "bday", "anniversary", "url"):
        if not out.get(key) and extra.get(key):
            out[key] = extra[key]
            changed = True
    if extra.get("note") and extra["note"] not in (out.get("note") or ""):
        out["note"] = ((out.get("note") or "") + "\n\n" + extra["note"]).strip()
        changed = True
    for key in ("emails", "phones", "addresses", "related"):
        have = {_digits(_key(i)) if key == "phones" else _key(i) for i in out.get(key) or []}
        for item in extra.get(key) or []:
            k = _digits(_key(item)) if key == "phones" else _key(item)
            if k and k not in have:
                out[key].append({kk: vv for kk, vv in item.items() if not kk.startswith("_")})
                have.add(k)
                changed = True
    for c in extra.get("categories") or []:
        if c not in out["categories"]:
            out["categories"].append(c)
            changed = True
    if not out.get("photo") and extra.get("photo", "").startswith("data:image/"):
        out["photo"] = extra["photo"]
        changed = True
    else:
        out["photo"] = None
    return out, changed


def _digits(value):
    """A number to compare: digits only, a French +33 written as its 0."""
    d = re.sub(r"\D", "", value or "")
    if d.startswith("33") and len(d) == 11:
        d = "0" + d[2:]
    elif d.startswith("0033"):
        d = "0" + d[4:]
    return d


def split_file(text):
    """The cards of a .vcf file (one or many)."""
    cards, current = [], []
    for line in _unfold(text):
        upper = line.upper()
        if upper.startswith("BEGIN:VCARD"):
            current = [line]
        elif upper.startswith("END:VCARD") and current:
            current.append(line)
            cards.append("\r\n".join(current) + "\r\n")
            current = []
        elif current:
            current.append(line)
    return cards
