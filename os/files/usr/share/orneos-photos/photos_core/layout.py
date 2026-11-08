"""Pure layout of the library, kept out of Qt so it can be tested: the justified rows of the grid (each photo at
its own proportions, every row the full width), the years and months as cards, and the memories found in the
dates (this day in other years, the days with many photos in a row).

A day id is Memories': days since 1970-01-01, in the local time the photo was taken.
"""
from datetime import date, timedelta

EPOCH = date(1970, 1, 1)
GAP = 4                      # pixels between photos, and between rows


def day_date(dayid):
    return EPOCH + timedelta(days=int(dayid))


def dayid_of(d):
    return (d - EPOCH).days


def aspect(photo):
    w, h = int(photo.get("w") or 0), int(photo.get("h") or 0)
    if w <= 0 or h <= 0:
        return 1.0
    return max(0.4, min(3.0, w / h))


class Words:
    """The words of dates, from the app's strings (months_long, weekdays…, lang)."""

    def __init__(self, t, lang):
        self.months = t["months_long"].split(",")
        self.weekdays = t["weekdays_long"].split(",")
        self.lang = lang
        self.t = t

    def day(self, d, today=None):
        today = today or date.today()
        if d == today:
            return self.t["today"]
        if d == today - timedelta(days=1):
            return self.t["yesterday"]
        month = self.months[d.month - 1]
        weekday = self.weekdays[d.weekday()]
        year = "" if d.year == today.year else f" {d.year}"
        if self.lang == "en":
            return f"{weekday}, {month} {d.day}{(',' + year) if year else ''}"
        if self.lang == "de":
            return f"{weekday}, {d.day}. {month}{year}"
        return f"{weekday} {d.day} {month}{year}"

    def month(self, year, month):
        name = self.months[month - 1]
        return f"{name[:1].upper()}{name[1:]} {year}"

    def span(self, first, last):
        """« 12–15 août 2025 », « 30 juil. – 2 août 2025 »."""
        if first == last:
            return self.day(first, today=date(1, 1, 1)).split(" ", 1)[1] if self.lang != "en" else self.day(first)
        m1, m2 = self.months[first.month - 1], self.months[last.month - 1]
        if self.lang == "en":
            if first.month == last.month:
                return f"{m1} {first.day}–{last.day}, {last.year}"
            return f"{m1} {first.day} – {m2} {last.day}, {last.year}"
        dot = "." if self.lang == "de" else ""
        if first.month == last.month:
            return f"{first.day}{dot}–{last.day}{dot} {m1} {last.year}"
        return f"{first.day}{dot} {m1} – {last.day}{dot} {m2} {last.year}"


def justify(photos, width, target, last_full=False):
    """Rows of photos filling the width at about the target height. [(height, [(photo, width)])]."""
    rows, line, ratio = [], [], 0.0
    width = max(120, int(width))
    for photo in photos:
        a = aspect(photo)
        line.append((photo, a))
        ratio += a
        if ratio * target + GAP * (len(line) - 1) >= width:
            rows.append(_fit(line, ratio, width, None))
            line, ratio = [], 0.0
    if line:
        rows.append(_fit(line, ratio, width, None if last_full else target))
    return rows


def _fit(line, ratio, width, height):
    room = width - GAP * (len(line) - 1)
    h = height if height is not None else room / ratio
    h = min(h, room / ratio)                     # a last row never overflows
    items, used = [], 0
    for i, (photo, a) in enumerate(line):
        w = int(round(a * h))
        if height is None and i == len(line) - 1:
            w = room - used                      # the last photo takes the rounding
        items.append((photo, max(8, w)))
        used += w
    return int(round(h)), items


def grid(photos, width, target, words, by="day", pending=()):
    """The rows of the timeline: a heading for each day (or month), then its photos, justified.
    Each row: {kind: "head", title, sub, key} or {kind: "row", h, items: [{i, fileid, etag, w, video,
    duration, fav, pending, live}]}. i is the photo's index in the flat order (selection, viewer)."""
    rows, group, key = [], [], None
    flat = 0

    def close():
        nonlocal flat
        if not group:
            return
        d = day_date(group[0]["dayid"])
        title = words.day(d) if by == "day" else words.month(d.year, d.month)
        rows.append({"kind": "head", "title": title, "sub": str(len(group)), "key": key, "dayid": group[0]["dayid"]})
        for h, line in justify(group, width, target):
            items = []
            for photo, w in line:
                items.append({"i": flat, "fileid": photo["fileid"], "etag": photo["etag"], "w": w,
                              "video": bool(photo.get("video")), "duration": int(photo.get("duration") or 0),
                              "fav": bool(photo.get("fav")), "live": bool(photo.get("live")),
                              "pending": photo["fileid"] in pending, "turn": int(photo.get("turn") or 0)})
                flat += 1
            rows.append({"kind": "row", "h": h, "items": items, "key": key})
        group.clear()

    for photo in photos:
        d = day_date(photo["dayid"])
        k = f"d{photo['dayid']}" if by == "day" else f"m{d.year}-{d.month:02d}"
        if k != key:
            close()
            key = k
        group.append(photo)
    close()
    return rows


def _cover(photos):
    best = next((p for p in photos if p.get("fav") and not p.get("video")), None)
    best = best or next((p for p in photos if not p.get("video")), None) or photos[0]
    return best


def years(photos):
    """[{year, count, fileid, etag}] newest first."""
    out, bucket, year = [], [], None
    for photo in photos:
        y = day_date(photo["dayid"]).year
        if y != year and bucket:
            out.append(_card_year(year, bucket))
            bucket = []
        year = y
        bucket.append(photo)
    if bucket:
        out.append(_card_year(year, bucket))
    return out


def _card_year(year, bucket):
    cover = _cover(bucket)
    return {"year": year, "count": len(bucket), "fileid": cover["fileid"], "etag": cover["etag"],
            "dayid": bucket[0]["dayid"]}


def months(photos, words):
    out, bucket, key = [], [], None
    for photo in photos:
        d = day_date(photo["dayid"])
        k = (d.year, d.month)
        if k != key and bucket:
            out.append(_card_month(key, bucket, words))
            bucket = []
        key = k
        bucket.append(photo)
    if bucket:
        out.append(_card_month(key, bucket, words))
    return out


def _card_month(key, bucket, words):
    cover = _cover(bucket)
    return {"year": key[0], "month": key[1], "title": words.month(*key), "count": len(bucket),
            "fileid": cover["fileid"], "etag": cover["etag"], "dayid": bucket[0]["dayid"]}


def memories(photos, words, today=None, limit=12):
    """Memories found in the dates alone: this day (± 3 days) in each earlier year, then the stretches of
    consecutive days with many photos (a trip, a party), the most recent first.
    [{key, kind: "onthisday"|"event", title, sub, count, fileid, etag, first, last}] (first/last: day ids)."""
    today = today or date.today()
    out = []
    by_year = {}
    for photo in photos:
        d = day_date(photo["dayid"])
        if d.year >= today.year:
            continue
        try:
            same = date(d.year, today.month, today.day)
        except ValueError:                        # 29 February
            same = date(d.year, today.month, 28)
        if abs((d - same).days) <= 3:
            by_year.setdefault(d.year, []).append(photo)
    for year in sorted(by_year, reverse=True):
        bucket = by_year[year]
        cover = _cover(bucket)
        n = today.year - year
        out.append({"key": f"otd{year}", "kind": "onthisday",
                    "title": words.t["memory_years"].split("|")[0 if n == 1 else 1].replace("%1", str(n)),
                    "sub": words.t["memory_onthisday"], "count": len(bucket), "fileid": cover["fileid"],
                    "etag": cover["etag"], "first": min(p["dayid"] for p in bucket), "last": max(p["dayid"] for p in bucket)})
    # stretches: days at most one day apart, together at least 20 photos, within the last three years
    since = dayid_of(today) - 3 * 366
    days = {}
    for photo in photos:
        if photo["dayid"] >= since:
            days.setdefault(photo["dayid"], []).append(photo)
    runs, run = [], []
    for dayid in sorted(days):
        if run and dayid - run[-1] > 2:
            runs.append(run)
            run = []
        run.append(dayid)
    if run:
        runs.append(run)
    events = []
    for run in runs:
        bucket = [p for d in run for p in days[d]]
        if len(bucket) < 20 or len(run) > 21:
            continue
        cover = _cover(bucket)
        first, last = day_date(run[0]), day_date(run[-1])
        events.append({"key": f"ev{run[0]}", "kind": "event", "title": words.span(first, last),
                       "sub": "", "count": len(bucket), "fileid": cover["fileid"], "etag": cover["etag"],
                       "first": run[0], "last": run[-1]})
    events.sort(key=lambda e: -e["last"])
    return (out + events)[:limit]
