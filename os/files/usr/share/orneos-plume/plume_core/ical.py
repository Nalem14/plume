"""Events for Plume: index one calendar object for the cache, expand its occurrences over a range, and
build or edit it (recurrences, single-occurrence changes, invitations, reminders).

An object is one iCalendar resource: a master VEVENT and, for a recurring event, the occurrences that
were changed (RECURRENCE-ID). Edits keep every property Plume does not know, so nothing written by the
cloud or another client is lost. Times are written in the session's time zone, with its VTIMEZONE.
"""
import os
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
import meeting
from icalendar import Alarm, Calendar, Event, Timezone, TimezoneDaylight, TimezoneStandard, vCalAddress, vRecur

PRODID = "-//Orneos//Plume//FR"
MAX_OCCURRENCES = 1000


def zone_key():
    tz = os.environ.get("TZ", "").lstrip(":")
    if "/" in tz:
        return tz
    path = os.path.realpath("/etc/localtime")
    if "zoneinfo/" in path:
        return path.split("zoneinfo/", 1)[1]
    try:                                    # Windows: no /etc/localtime, Qt knows the IANA name
        from PySide6.QtCore import QTimeZone  # noqa: PLC0415
        key = bytes(QTimeZone.systemTimeZoneId().data()).decode()
    except ImportError:
        key = ""
    return key if "/" in key else "UTC"


def local_zone():
    try:
        return ZoneInfo(zone_key())
    except Exception:
        return timezone.utc


# ---- reading ---------------------------------------------------------------------------------------------
def parse(ics):
    try:
        return Calendar.from_ical(ics)
    except Exception:
        return None


def _events(cal):
    return [c for c in cal.walk("VEVENT")] if cal is not None else []


def _master(events):
    return next((e for e in events if "RECURRENCE-ID" not in e), events[0] if events else None)


def _when(value, tz):
    """iCalendar DATE or DATE-TIME → (aware datetime in tz, all_day). Floating times are local."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.astimezone(tz), False
    if isinstance(value, date):
        return datetime.combine(value, time(), tz), True
    return None, False


def _span(event, tz):
    """(start, end, all_day) of one VEVENT, end defaulting per RFC 5545."""
    if "DTSTART" not in event:
        return None, None, False
    start, all_day = _when(event.decoded("DTSTART"), tz)
    if start is None:
        return None, None, False
    if "DTEND" in event:
        end, _ = _when(event.decoded("DTEND"), tz)
    elif "DURATION" in event:
        end = start + event.decoded("DURATION")
    else:
        end = start + (timedelta(days=1) if all_day else timedelta())
    if end is None or end < start:
        end = start
    return start, end, all_day


def _rid_key(value, tz):
    moment, all_day = _when(value, tz)
    if moment is None:
        return ""
    return moment.strftime("%Y%m%d") if all_day else moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _rule_set(master, start, all_day):
    """dateutil rruleset of the master's RRULE, RDATE and EXDATE, anchored on start."""
    rule = dict(master["RRULE"])
    anchor = start.replace(tzinfo=None) if all_day else start
    until = rule.get("UNTIL")
    if until:
        value = until[0]
        if all_day:
            value = value.date() if isinstance(value, datetime) else value
            rule["UNTIL"] = [datetime.combine(value, time(23, 59, 59))]
        elif isinstance(value, datetime):
            value = value if value.tzinfo else value.replace(tzinfo=start.tzinfo)
            rule["UNTIL"] = [value.astimezone(timezone.utc)]
        else:
            rule["UNTIL"] = [datetime.combine(value, time(23, 59, 59), start.tzinfo).astimezone(timezone.utc)]
    text = vRecur(rule).to_ical().decode()
    rules = rrulestr(f"RRULE:{text}", dtstart=anchor, forceset=True, ignoretz=False)

    def moments(prop):
        values = master.get(prop)
        if values is None:
            return []
        values = values if isinstance(values, list) else [values]
        found = []
        for entry in values:
            for item in getattr(entry, "dts", []):
                moment, _ = _when(item.dt, start.tzinfo)
                if moment is not None:
                    found.append(moment.replace(tzinfo=None) if all_day else moment)
        return found

    for moment in moments("EXDATE"):
        rules.exdate(moment)
    for moment in moments("RDATE"):
        rules.rdate(moment)
    return rules


def index(ics, my_addresses=()):
    """Columns for the cache: uid, title, start/end timestamps, recurring, pending invitation."""
    tz = local_zone()
    events = _events(parse(ics))
    master = _master(events)
    if master is None:
        return None
    start, end, all_day = _span(master, tz)
    if start is None:
        return None
    recurring = "RRULE" in master or "RDATE" in master
    last = end
    if recurring:
        last = None
        rule = master.get("RRULE")
        if rule is not None and ("UNTIL" in rule or "COUNT" in rule):
            try:
                occurrences = list(_rule_set(master, start, all_day))
                if occurrences:
                    tail = occurrences[-1]
                    tail = tail.replace(tzinfo=tz) if tail.tzinfo is None else tail
                    last = tail + (end - start)
            except Exception:
                last = None
    for override in events:
        if override is not master:
            o_start, o_end, _ = _span(override, tz)
            if o_start is not None:
                start = min(start, o_start)
                if last is not None:
                    last = max(last, o_end)
    pending = any(_my_status(e, my_addresses) == "NEEDS-ACTION" for e in events) if my_addresses else False
    return {
        "uid": str(master.get("UID", "")),
        "title": str(master.get("SUMMARY", "")),
        "start_ts": int(start.timestamp()),
        "end_ts": int(last.timestamp()) if last is not None else None,
        "recurring": recurring,
        "pending": pending,
    }


def _address(value):
    return str(value).lower().removeprefix("mailto:").strip()


def _attendees(event):
    values = event.get("ATTENDEE")
    if values is None:
        return []
    return values if isinstance(values, list) else [values]


def _my_status(event, my_addresses):
    for attendee in _attendees(event):
        if _address(attendee) in my_addresses:
            return str(attendee.params.get("PARTSTAT", "NEEDS-ACTION")).upper()
    return ""


def _call(event):
    """(link, provider) of the event's video call: Google Meet, Teams, Zoom, Orneos Meet… (meeting.py)."""
    return meeting.in_event(lambda key: str(event.get(key, "") or ""))


def _meet_link(event):
    return _call(event)[0]


def _occurrence(event, start, end, all_day, rid, recurring, my_addresses):
    my_status = _my_status(event, my_addresses)
    return {
        "rid": rid,
        "title": str(event.get("SUMMARY", "")) or "",
        "location": str(event.get("LOCATION", "") or ""),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "startTs": start.timestamp(),
        "endTs": end.timestamp(),
        "allDay": all_day,
        "recurring": recurring,
        "cancelled": str(event.get("STATUS", "")).upper() == "CANCELLED",
        "myStatus": my_status,
        "meet": _meet_link(event),
        "meetName": _call(event)[1],
        "alarms": sorted({m for m in (_simple_alarm(sub) for sub in event.walk("VALARM")) if m is not None}),
        "organizer": _address(event["ORGANIZER"]) if "ORGANIZER" in event else "",
    }


def occurrences(ics, range_start, range_end, my_addresses=()):
    """Occurrences overlapping [range_start, range_end) (aware datetimes), in the session's zone."""
    tz = local_zone()
    events = _events(parse(ics))
    master = _master(events)
    if master is None:
        return []
    overrides = {}
    for event in events:
        if event is not master and "RECURRENCE-ID" in event:
            overrides[_rid_key(event.decoded("RECURRENCE-ID"), tz)] = event
    start, end, all_day = _span(master, tz)
    if start is None:
        return []
    duration = end - start
    found = []
    recurring = "RRULE" in master or "RDATE" in master
    if recurring and "RRULE" in master:
        try:
            rules = _rule_set(master, start, all_day)
        except Exception:
            rules = None
        if rules is not None:
            lo, hi = range_start - duration, range_end
            if all_day:
                lo, hi = lo.astimezone(tz).replace(tzinfo=None), hi.astimezone(tz).replace(tzinfo=None)
            for count, moment in enumerate(rules.between(lo, hi, inc=True)):
                if count >= MAX_OCCURRENCES:
                    break
                moment = moment.replace(tzinfo=tz) if moment.tzinfo is None else moment.astimezone(tz)
                rid = _rid_key(moment.date() if all_day else moment, tz)
                if rid in overrides:
                    continue
                o_end = moment + duration
                if o_end > range_start or (o_end == moment and moment >= range_start):
                    found.append(_occurrence(master, moment, o_end, all_day, rid, True, my_addresses))
    elif end > range_start and start < range_end or (start == end and range_start <= start < range_end):
        found.append(_occurrence(master, start, end, all_day, "", recurring, my_addresses))
    for rid, event in overrides.items():
        o_start, o_end, o_all_day = _span(event, tz)
        if o_start is not None and (o_end > range_start and o_start < range_end):
            item = _occurrence(event, o_start, o_end, o_all_day, rid, True, my_addresses)
            if not item["cancelled"]:
                found.append(item)
    return [item for item in found if not item["cancelled"]]


# ---- reminders: the ones Plume edits are "N minutes before the start" shown on screen; any other (an e-mail,
# a fixed date, after the end) is kept as it is --------------------------------------------------------------
def _simple_alarm(sub):
    """Minutes before the start (negative: after it, like 9:00 on the day of an all-day event), or None."""
    trigger = sub.get("TRIGGER")
    if trigger is None or not isinstance(trigger.dt, timedelta):
        return None
    if str(trigger.params.get("RELATED", "START")).upper() != "START":
        return None
    if str(sub.get("ACTION", "DISPLAY")).upper() not in ("DISPLAY", "AUDIO"):
        return None
    return int(-trigger.dt.total_seconds() // 60)


def _zone_times(event, start, end, all_day):
    """"HH:MM – HH:MM" of the event in its own time zone, when that is not the session's ("" otherwise)."""
    key = _tzid(event)
    if not key or all_day or start is None:
        return ""
    try:
        zone = ZoneInfo(key)
    except Exception:
        return ""
    return start.astimezone(zone).strftime("%H:%M") + " – " + end.astimezone(zone).strftime("%H:%M")


def _tzid(event):
    start = event.get("DTSTART")
    value = start.dt if start is not None else None
    if isinstance(value, datetime) and value.tzinfo is not None:
        key = getattr(value.tzinfo, "key", None) or str(start.params.get("TZID", ""))
        return key if key and key != zone_key() else ""
    return ""


# ---- repetition: what the editor shows and writes ---------------------------------------------------------
DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
EDITABLE_PARTS = {"FREQ", "INTERVAL", "BYDAY", "BYMONTHDAY", "COUNT", "UNTIL", "WKST"}


def repeat_info(rule, start=None):
    """The RRULE as the editor sees it: {freq, interval, byday, monthly ("day"/"weekday"), nth, count, until,
    editable, text}. editable is False for a rule the editor cannot show (it is then kept as it is)."""
    if rule is None:
        return {"freq": "", "interval": 1, "byday": [], "monthly": "day", "nth": 0, "count": 0, "until": "",
                "editable": True, "text": ""}
    def first(key, default=None):
        value = rule.get(key)
        return value[0] if isinstance(value, list) and value else (value if value not in (None, []) else default)
    freq = str(first("FREQ", "")).upper()
    byday = [str(d).upper() for d in (rule.get("BYDAY") or [])]
    editable = set(k.upper() for k in rule.keys()) <= EDITABLE_PARTS and freq in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
    monthly, nth = "day", 0
    plain = [d for d in byday if d in DAYS]
    if freq == "WEEKLY":
        editable = editable and len(plain) == len(byday)
    elif freq == "MONTHLY" and byday:
        m = re.fullmatch(r"([+-]?\d)(MO|TU|WE|TH|FR|SA|SU)", byday[0]) if len(byday) == 1 else None
        if m and -1 <= int(m.group(1)) <= 5 and int(m.group(1)) != 0:
            monthly, nth, plain = "weekday", int(m.group(1)), [m.group(2)]
        else:
            editable = False
    elif byday:
        editable = editable and freq == "DAILY" and len(plain) == len(byday)
    if "BYMONTHDAY" in rule:
        days = rule.get("BYMONTHDAY") or []
        editable = editable and freq == "MONTHLY" and len(days) == 1 and start is not None and int(days[0]) == start.day
    until = first("UNTIL")
    if isinstance(until, datetime):
        until = (until if until.tzinfo else until.replace(tzinfo=local_zone())).astimezone(local_zone()).date()
    return {
        "freq": freq, "interval": int(first("INTERVAL", 1) or 1), "byday": plain, "monthly": monthly, "nth": nth,
        "count": int(first("COUNT", 0) or 0), "until": until.isoformat() if isinstance(until, date) else "",
        "editable": editable, "text": vRecur(rule).to_ical().decode(),
    }


def _until_value(day, start):
    """UNTIL for the last day `day` (a date): a DATE for an all-day series, else the end of that local day in
    UTC (a floating series keeps a floating UNTIL)."""
    if not isinstance(start, datetime):
        return day
    end = datetime.combine(day, time(23, 59, 59))
    if start.tzinfo is None:
        return end
    return end.replace(tzinfo=start.tzinfo).astimezone(timezone.utc)


def build_rule(repeat, start):
    """vRecur from the editor's repeat {freq, interval, byday, monthly, nth, count, until}, or None."""
    freq = str(repeat.get("freq") or "").upper()
    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        return None
    rule = {"FREQ": freq}
    interval = int(repeat.get("interval") or 1)
    if interval > 1:
        rule["INTERVAL"] = interval
    days = [d for d in (repeat.get("byday") or []) if d in DAYS]
    if freq == "WEEKLY" and days:
        weekday = DAYS[start.weekday()]
        if days != [weekday]:
            rule["BYDAY"] = sorted(set(days), key=DAYS.index)
    elif freq == "DAILY" and days and len(days) < 7:
        rule["BYDAY"] = sorted(set(days), key=DAYS.index)
    elif freq == "MONTHLY" and repeat.get("monthly") == "weekday":
        nth = int(repeat.get("nth") or 0) or ((start.day - 1) // 7 + 1)
        rule["BYDAY"] = [f"{nth}{DAYS[start.weekday()]}"]
    count = int(repeat.get("count") or 0)
    until = str(repeat.get("until") or "")
    if count > 0:
        rule["COUNT"] = count
    elif until:
        rule["UNTIL"] = _until_value(date.fromisoformat(until[:10]), start)
    return vRecur(rule)


def details(ics, rid="", my_addresses=()):
    """Everything the event card and the editor need, for the master or one occurrence."""
    tz = local_zone()
    events = _events(parse(ics))
    master = _master(events)
    if master is None:
        return {}
    event = master
    if rid:
        for candidate in events:
            if "RECURRENCE-ID" in candidate and _rid_key(candidate.decoded("RECURRENCE-ID"), tz) == rid:
                event = candidate
    start, end, all_day = _span(event, tz)
    if event is master and rid and start is not None:
        moment = (datetime.strptime(rid, "%Y%m%d").replace(tzinfo=tz) if len(rid) == 8
                  else datetime.strptime(rid, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(tz))
        start, end = moment, moment + (end - start)
    rule = master.get("RRULE")
    freq = str(rule.get("FREQ", [""])[0]) if rule is not None else ""
    organizer = event.get("ORGANIZER")
    alarms, others = [], 0
    for sub in event.walk("VALARM"):
        minutes = _simple_alarm(sub)
        if minutes is None:
            others += 1
        elif str(minutes) not in alarms:
            alarms.append(str(minutes))
    people = []
    for attendee in _attendees(event):
        people.append({
            "email": _address(attendee),
            "name": str(attendee.params.get("CN", "")),
            "status": str(attendee.params.get("PARTSTAT", "NEEDS-ACTION")).upper(),
            "optional": str(attendee.params.get("ROLE", "")).upper() == "OPT-PARTICIPANT",
        })
    return {
        "uid": str(master.get("UID", "")),
        "rid": rid,
        "title": str(event.get("SUMMARY", "") or ""),
        "location": str(event.get("LOCATION", "") or ""),
        "description": str(event.get("DESCRIPTION", "") or ""),
        "start": start.isoformat() if start else "",
        "end": end.isoformat() if end else "",
        "allDay": all_day,
        "freq": freq,
        "recurring": rule is not None,
        "repeat": repeat_info(rule, start),
        "alarm": alarms[0] if alarms else "",
        "alarms": alarms,
        "otherAlarms": others,
        "tzid": _tzid(event),
        "zoneTimes": _zone_times(event, start, end, all_day),
        "organizer": _address(organizer) if organizer is not None else "",
        "organizerName": str(organizer.params.get("CN", "")) if organizer is not None else "",
        "attendees": people,
        "myStatus": _my_status(event, my_addresses),
        "meet": _meet_link(event),
        "meetName": _call(event)[1],
    }


# ---- writing ---------------------------------------------------------------------------------------------
def vtimezone(key, year=None):
    """VTIMEZONE for key, with yearly rules read from the zone's transitions of the current year."""
    tz = ZoneInfo(key)
    year = year or datetime.now().year
    comp = Timezone()
    comp.add("TZID", key)
    transitions = []
    day = datetime(year, 1, 1, 12, tzinfo=tz)
    previous = day.utcoffset()
    for _ in range(366):
        nxt = (day.astimezone(timezone.utc) + timedelta(days=1)).astimezone(tz)
        if nxt.utcoffset() != previous:
            instant = day.astimezone(timezone.utc)
            for _hour in range(25):
                instant += timedelta(hours=1)
                if instant.astimezone(tz).utcoffset() != previous:
                    break
            transitions.append((instant, previous, instant.astimezone(tz).utcoffset()))
            previous = nxt.utcoffset()
        day = nxt
    if not transitions:
        std = TimezoneStandard()
        std.add("DTSTART", datetime(1970, 1, 1))
        std.add("TZOFFSETFROM", previous)
        std.add("TZOFFSETTO", previous)
        std.add("TZNAME", datetime.now(tz).tzname() or key)
        comp.add_component(std)
        return comp
    for instant, before, after in transitions:
        wall = (instant + before).replace(tzinfo=None)
        sub = TimezoneDaylight() if after > before else TimezoneStandard()
        month_days = ((wall.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)).day
        nth = -1 if wall.day + 7 > month_days else (wall.day - 1) // 7 + 1
        weekday = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][wall.weekday()]
        sub.add("DTSTART", datetime.combine(_nth_weekday(1970, wall.month, wall.weekday(), nth), wall.time()))
        sub.add("TZOFFSETFROM", before)
        sub.add("TZOFFSETTO", after)
        sub.add("TZNAME", instant.astimezone(tz).tzname() or key)
        sub.add("RRULE", {"FREQ": "YEARLY", "BYMONTH": wall.month, "BYDAY": f"{nth}{weekday}"})
        comp.add_component(sub)
    return comp


def _nth_weekday(year, month, weekday, nth):
    """The nth (1-based, or -1 for the last) given weekday of a month: the first onset of a zone rule."""
    if nth > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (nth - 1))
    last = (date(year, month, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _parse_local(value, all_day):
    """"2026-10-22T12:30" or "2026-10-22" from the editor → date or aware datetime in the session's zone."""
    moment = datetime.fromisoformat(value)
    if all_day:
        return moment.date()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=local_zone())
    return moment.astimezone(local_zone())


def _set_times(event, fields):
    all_day = bool(fields.get("allDay"))
    start = _parse_local(fields["start"], all_day)
    end = _parse_local(fields.get("end") or fields["start"], all_day)
    if all_day and end <= start:
        end = start + timedelta(days=1)
    if not all_day and end < start:
        end = start
    # the same times as before: left as they are, in their own time zone (a meeting set in New York stays
    # at 9:00 there, through the changes of summer time on both sides)
    tz = local_zone()
    before, after, was_all_day = _span(event, tz)
    if before is not None and was_all_day == all_day:
        same = (before.date() == start and after.date() == end) if all_day else (before == start and after == end)
        if same:
            return
    for key in ("DTSTART", "DTEND", "DURATION"):
        event.pop(key, None)
    event.add("DTSTART", start)
    event.add("DTEND", end)


def _set_text(event, key, value):
    event.pop(key, None)
    if value:
        event.add(key, value)


def _apply(event, fields, me):
    """Fields of the editor onto one VEVENT (only the keys present are touched)."""
    if "title" in fields:
        _set_text(event, "SUMMARY", fields["title"].strip())
    if "location" in fields:
        _set_text(event, "LOCATION", fields["location"].strip())
    if "description" in fields:
        _set_text(event, "DESCRIPTION", fields["description"].strip())
    if "start" in fields:
        _set_times(event, fields)
    if "alarms" in fields or "alarm" in fields:
        wanted = fields["alarms"] if "alarms" in fields else [fields["alarm"]]
        minutes = []
        for value in wanted or []:
            if str(value) not in ("", "-1", "None"):
                try:
                    if int(value) not in minutes:
                        minutes.append(int(value))
                except (TypeError, ValueError):
                    pass
        # only the reminders Plume shows are replaced: an e-mail, a fixed date… stay
        for sub in list(event.subcomponents):
            if sub.name == "VALARM" and _simple_alarm(sub) is not None:
                event.subcomponents.remove(sub)
        for value in minutes:
            alarm = Alarm()
            alarm.add("ACTION", "DISPLAY")
            alarm.add("DESCRIPTION", fields.get("title") or str(event.get("SUMMARY", "")))
            alarm.add("TRIGGER", timedelta(minutes=-value))
            event.add_component(alarm)
    if "attendees" in fields:
        current = {_address(a): a for a in _attendees(event)}
        event.pop("ATTENDEE", None)
        names = {str(k).lower(): str(v) for k, v in (fields.get("guestNames") or {}).items()}
        optional = {str(e).lower() for e in fields.get("optional") or []}
        wanted = [e.strip().lower() for e in fields["attendees"] if e and "@" in e]
        for email in wanted:
            attendee = current.get(email)
            if attendee is None:
                attendee = vCalAddress(f"mailto:{email}")
                attendee.params["PARTSTAT"] = "NEEDS-ACTION"
                attendee.params["RSVP"] = "TRUE"
                attendee.params["CUTYPE"] = "INDIVIDUAL"
            if names.get(email) and names[email] != email and "CN" not in attendee.params:
                attendee.params["CN"] = names[email]
            if "optional" in fields:
                attendee.params["ROLE"] = "OPT-PARTICIPANT" if email in optional else "REQ-PARTICIPANT"
            elif "ROLE" not in attendee.params:
                attendee.params["ROLE"] = "REQ-PARTICIPANT"
            event.add("ATTENDEE", attendee, encode=0)
        if wanted and "ORGANIZER" not in event and me.get("email"):
            organizer = vCalAddress(f"mailto:{me['email']}")
            if me.get("name"):
                organizer.params["CN"] = me["name"]
            event.add("ORGANIZER", organizer, encode=0)
        if not wanted:
            event.pop("ORGANIZER", None)
    event.pop("DTSTAMP", None)
    event.add("DTSTAMP", datetime.now(timezone.utc))
    seq = int(event.get("SEQUENCE", 0) or 0)
    event.pop("SEQUENCE", None)
    event.add("SEQUENCE", seq + 1)


def _ensure_zone(cal):
    key = zone_key()
    if key == "UTC":
        return
    for comp in cal.walk("VTIMEZONE"):
        if str(comp.get("TZID")) == key:
            return
    try:
        cal.subcomponents.insert(0, vtimezone(key))
    except Exception:
        pass


def new_event(fields, me=None):
    """(uid, ics) of a new event from the editor's fields."""
    uid = f"{uuid.uuid4()}"
    cal = Calendar()
    cal.add("PRODID", PRODID)
    cal.add("VERSION", "2.0")
    cal.add("CALSCALE", "GREGORIAN")
    event = Event()
    event.add("UID", uid)
    event.add("CREATED", datetime.now(timezone.utc))
    _apply(event, fields, me or {})
    rule = _wanted_rule(fields, event)
    if rule is not None:
        event.add("RRULE", rule)
    cal.add_component(event)
    _ensure_zone(cal)
    return uid, cal.to_ical().decode()


def update_event(ics, fields, rid="", scope="all", me=None):
    """Edited ics. scope "this" changes one occurrence (RECURRENCE-ID), "all" the master."""
    cal = parse(ics)
    events = _events(cal)
    master = _master(events)
    tz = local_zone()
    target = master
    if rid and scope == "this":
        target = next((e for e in events if "RECURRENCE-ID" in e and _rid_key(e.decoded("RECURRENCE-ID"), tz) == rid), None)
        if target is None:
            target = Event()
            for key, value in master.property_items(recursive=False):
                if key not in ("BEGIN", "END", "RRULE", "RDATE", "EXDATE"):
                    target.add(key, value, encode=0)
            target.pop("RECURRENCE-ID", None)
            origin = _rid_value(rid, master, tz)
            target.add("RECURRENCE-ID", origin)
            m_start, m_end, _ = _span(master, tz)
            for key in ("DTSTART", "DTEND", "DURATION"):
                target.pop(key, None)
            if isinstance(origin, datetime):
                target.add("DTSTART", origin)
                target.add("DTEND", origin + (m_end - m_start))
            else:
                target.add("DTSTART", origin)
                target.add("DTEND", origin + timedelta(days=max(1, (m_end - m_start).days)))
            cal.add_component(target)
    elif rid and scope == "all" and "start" in fields and "RRULE" in master:
        # Moving "all" from one occurrence shifts the series by the same amount
        start, _, all_day = _span(master, tz)
        moved = _parse_local(fields["start"], bool(fields.get("allDay")))
        origin = _rid_value(rid, master, tz)
        shift = (moved if isinstance(moved, datetime) else datetime.combine(moved, time(), tz)) - \
                (origin if isinstance(origin, datetime) else datetime.combine(origin, time(), tz))
        end_moved = _parse_local(fields.get("end") or fields["start"], bool(fields.get("allDay")))
        length = (end_moved if isinstance(end_moved, datetime) else datetime.combine(end_moved, time(), tz)) - \
                 (moved if isinstance(moved, datetime) else datetime.combine(moved, time(), tz))
        new_start = start + shift
        fields = dict(fields)
        fields["start"] = (new_start.date() if fields.get("allDay") else new_start).isoformat()
        fields["end"] = ((new_start + length).date() if fields.get("allDay") else new_start + length).isoformat()
    _apply(target, fields, me or {})
    if target is master:
        _set_rule(master, fields)
    _ensure_zone(cal)
    return cal.to_ical().decode()


def _wanted_rule(fields, event):
    """The RRULE the editor asks for (None: no repetition). "repeat" (full) wins over "freq" (simple)."""
    start = event.decoded("DTSTART") if "DTSTART" in event else None
    if isinstance(fields.get("repeat"), dict):
        return build_rule(fields["repeat"], start) if start is not None else None
    if fields.get("freq"):
        return vRecur({"FREQ": fields["freq"]})
    return None


def _set_rule(master, fields):
    repeat = fields.get("repeat")
    if isinstance(repeat, dict):
        if repeat.get("keep"):
            return
        rule = _wanted_rule(fields, master)
        master.pop("RRULE", None)
        if rule is not None:
            master.add("RRULE", rule)
        return
    if "freq" in fields:
        rule = master.get("RRULE")
        if fields["freq"]:
            if rule is None or str(rule.get("FREQ", [""])[0]) != fields["freq"]:
                master.pop("RRULE", None)
                master.add("RRULE", {"FREQ": fields["freq"]})
        else:
            master.pop("RRULE", None)


# ---- "this and the following ones": the series ends before the occurrence, a new one starts there --------
def _plain_moments(master, start, all_day, limit):
    """The RRULE's moments (EXDATE ignored, as COUNT counts them) before limit."""
    rule = dict(master["RRULE"])
    rule.pop("UNTIL", None)                 # only the moments before limit count, which is before any UNTIL
    text = vRecur(rule).to_ical().decode()
    anchor = start.replace(tzinfo=None) if all_day else start
    stop = limit.replace(tzinfo=None) if all_day and isinstance(limit, datetime) else limit
    found = 0
    for moment in rrulestr(f"RRULE:{text}", dtstart=anchor, ignoretz=False):
        if moment >= stop:
            break
        found += 1
    return found


def _end_before(master, rid, tz):
    """(master with its RRULE ended just before the occurrence rid, how many came before) or (None, 0)."""
    start, _, all_day = _span(master, tz)
    origin = _rid_value(rid, master, tz)
    limit = datetime.combine(origin, time()) if not isinstance(origin, datetime) else origin
    before = _plain_moments(master, start, all_day, limit)
    if before == 0:
        return None, 0
    rule = dict(master["RRULE"])
    rule.pop("COUNT", None)
    rule.pop("UNTIL", None)
    dtstart = master.decoded("DTSTART")
    if isinstance(origin, datetime):
        last = origin - timedelta(seconds=1)
        rule["UNTIL"] = last.astimezone(timezone.utc) if getattr(dtstart, "tzinfo", None) else last.astimezone(tz).replace(tzinfo=None)
    else:
        rule["UNTIL"] = origin - timedelta(days=1)
    master.pop("RRULE", None)
    master.add("RRULE", rule)
    return master, before


def _later(event, origin, tz):
    """True for an override at or after the occurrence origin."""
    moment, _ = _when(event.decoded("RECURRENCE-ID"), tz)
    limit, _ = _when(origin, tz)
    return moment is not None and limit is not None and moment >= limit


def end_series(ics, rid):
    """ics of the series ended before the occurrence rid (its later changes removed), or None when rid is the
    first one (the whole series goes)."""
    cal = parse(ics)
    tz = local_zone()
    events = _events(cal)
    master = _master(events)
    if master is None or "RRULE" not in master:
        return None
    origin = _rid_value(rid, master, tz)
    ended, _ = _end_before(master, rid, tz)
    if ended is None:
        return None
    for event in events:
        if event is not master and "RECURRENCE-ID" in event and _later(event, origin, tz):
            cal.subcomponents.remove(event)
    return cal.to_ical().decode()


def split_series(ics, rid, fields, me=None):
    """(old ics, new uid, new ics): the series ends before rid, a new one with the editor's fields starts at
    rid and keeps the later changes and exceptions (moved with it). None when rid is the first occurrence."""
    cal = parse(ics)
    tz = local_zone()
    events = _events(cal)
    master = _master(events)
    if master is None or "RRULE" not in master:
        return None
    m_start, m_end, all_day = _span(master, tz)
    origin = _rid_value(rid, master, tz)
    original_rule = dict(master["RRULE"])
    copy = Event.from_ical(master.to_ical())
    ended, before = _end_before(master, rid, tz)
    if ended is None:
        return None

    uid = str(uuid.uuid4())
    new = Calendar()
    new.add("PRODID", PRODID)
    new.add("VERSION", "2.0")
    new.add("CALSCALE", "GREGORIAN")
    for zone in cal.walk("VTIMEZONE"):
        new.add_component(zone)
    head = copy
    for key in ("UID", "RECURRENCE-ID", "EXDATE", "RDATE", "DTSTART", "DTEND", "DURATION", "SEQUENCE", "CREATED"):
        head.pop(key, None)
    head.add("UID", uid)
    head.add("CREATED", datetime.now(timezone.utc))
    head.add("DTSTART", origin)
    head.add("DTEND", origin + (m_end - m_start) if isinstance(origin, datetime) else origin + timedelta(days=max(1, (m_end - m_start).days)))
    rule = dict(original_rule)
    if "COUNT" in rule:
        rule["COUNT"] = max(1, int(rule["COUNT"][0]) - before)
    head.pop("RRULE", None)
    head.add("RRULE", rule)
    fields = dict(fields)
    _apply(head, fields, me or {})
    repeat_changed = isinstance(fields.get("repeat"), dict) and not fields["repeat"].get("keep")
    if repeat_changed or (fields.get("freq") and fields.get("freq") != str(rule.get("FREQ", [""])[0])):
        _set_rule(head, fields)
    new.add_component(head)

    # later exceptions and changes follow the series, shifted with it when its time moved
    new_start = head.decoded("DTSTART")
    shift = None
    if not repeat_changed and type(new_start) is type(origin):
        shift = new_start - origin
    old_ex = master.get("EXDATE")
    if old_ex is not None and shift is not None:
        for entry in old_ex if isinstance(old_ex, list) else [old_ex]:
            for item in getattr(entry, "dts", []):
                moment, _ = _when(item.dt, tz)
                limit, _ = _when(origin, tz)
                if moment is not None and moment >= limit:
                    head.add("EXDATE", item.dt + shift)
    for event in events:
        if event is not master and "RECURRENCE-ID" in event and _later(event, origin, tz):
            cal.subcomponents.remove(event)
            if shift is None:
                continue
            moved = Event.from_ical(event.to_ical())
            rid_value = moved.decoded("RECURRENCE-ID")
            moved.pop("RECURRENCE-ID", None)
            moved.pop("UID", None)
            moved.add("UID", uid)
            moved.add("RECURRENCE-ID", rid_value + shift)
            new.add_component(moved)
    _ensure_zone(new)
    master.pop("DTSTAMP", None)
    master.add("DTSTAMP", datetime.now(timezone.utc))
    return cal.to_ical().decode(), uid, new.to_ical().decode()


def _rid_value(rid, master, tz):
    if len(rid) == 8:
        return datetime.strptime(rid, "%Y%m%d").date()
    moment = datetime.strptime(rid, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    start = master.decoded("DTSTART")
    if isinstance(start, datetime) and start.tzinfo is not None:
        return moment.astimezone(start.tzinfo)
    return moment.astimezone(tz)


def delete_occurrence(ics, rid):
    """ics without one occurrence (EXDATE on the master, its override removed)."""
    cal = parse(ics)
    tz = local_zone()
    events = _events(cal)
    master = _master(events)
    for event in events:
        if event is not master and "RECURRENCE-ID" in event and _rid_key(event.decoded("RECURRENCE-ID"), tz) == rid:
            cal.subcomponents.remove(event)
    master.add("EXDATE", _rid_value(rid, master, tz))
    return cal.to_ical().decode()


def set_status(ics, my_addresses, status):
    """Answer an invitation on every occurrence: ACCEPTED, TENTATIVE or DECLINED."""
    cal = parse(ics)
    for event in _events(cal):
        for attendee in _attendees(event):
            if _address(attendee) in my_addresses:
                attendee.params["PARTSTAT"] = status
                attendee.params.pop("RSVP", None)
        event.pop("DTSTAMP", None)
        event.add("DTSTAMP", datetime.now(timezone.utc))
    return cal.to_ical().decode()


# ---- invitations received by mail (iMIP, RFC 6047) -------------------------------------------------------
def invitation(ics, my_addresses=()):
    """What the calendar part of a mail says: its method (REQUEST, CANCEL, REPLY…), the event, and for a
    reply, who answered what. {} when it holds no event."""
    cal = parse(ics)
    master = _master(_events(cal))
    if master is None or "DTSTART" not in master:
        return {}
    info = details(ics, "", my_addresses)
    info["method"] = str(cal.get("METHOD", "") or "PUBLISH").upper()
    info["sequence"] = int(master.get("SEQUENCE", 0) or 0)
    info["cancelled"] = info["method"] == "CANCEL" or str(master.get("STATUS", "")).upper() == "CANCELLED"
    info["replier"] = {}
    if info["method"] == "REPLY" and info["attendees"]:
        info["replier"] = info["attendees"][0]
    return info


def invitation_text(info):
    """The invitation in a few lines, for Ornis (it reads the event's real times, not only the mail)."""
    if not info:
        return ""
    lines = ["[Calendar invitation attached]", f"Title: {info.get('title', '')}"]
    if info.get("allDay"):
        lines.append(f"Date: {info.get('start', '')[:10]} (all day)")
    else:
        lines.append(f"Start: {info.get('start', '')[:16].replace('T', ' ')}  End: {info.get('end', '')[:16].replace('T', ' ')} "
                     f"(local time, {zone_key()})")
    for key, label in (("location", "Location"), ("organizer", "Organizer"), ("meet", "Online meeting")):
        if info.get(key):
            lines.append(f"{label}: {info[key]}")
    return "\n".join(lines)


def stored_copy(ics, client_scheduled=False):
    """The calendar object kept from an invitation: no METHOD (a stored object has none). client_scheduled:
    Plume answers the organizer by mail itself (an address the cloud does not know as mine), so the cloud
    must not (SCHEDULE-AGENT=CLIENT on the organizer, RFC 6638)."""
    cal = parse(ics)
    out = Calendar()
    out.add("PRODID", PRODID)
    out.add("VERSION", "2.0")
    for comp in cal.subcomponents:
        if comp.name in ("VTIMEZONE", "VEVENT"):
            if comp.name == "VEVENT" and client_scheduled and "ORGANIZER" in comp:
                comp["ORGANIZER"].params["SCHEDULE-AGENT"] = "CLIENT"
            out.add_component(comp)
    return out.to_ical().decode()


def client_scheduled(ics):
    """True when Plume (not the cloud) answers this event's organizer."""
    for event in _events(parse(ics)):
        organizer = event.get("ORGANIZER")
        if organizer is not None and str(organizer.params.get("SCHEDULE-AGENT", "")).upper() == "CLIENT":
            return True
    return False


def sequence(ics):
    master = _master(_events(parse(ics)))
    return int(master.get("SEQUENCE", 0) or 0) if master is not None else 0


def reply(ics, my_address, status, name=""):
    """iTIP REPLY of my answer to the organizer: one ATTENDEE (me) per VEVENT, nothing else changed."""
    cal = parse(ics)
    out = Calendar()
    out.add("PRODID", PRODID)
    out.add("VERSION", "2.0")
    out.add("METHOD", "REPLY")
    for zone in cal.walk("VTIMEZONE"):
        out.add_component(zone)
    for event in _events(cal):
        answer = Event()
        for key in ("UID", "RECURRENCE-ID", "SEQUENCE", "DTSTART", "DTEND", "DURATION", "SUMMARY", "ORGANIZER"):
            if key in event:
                answer.add(key, event[key], encode=0)
        if "ORGANIZER" in answer:
            answer["ORGANIZER"].params.pop("SCHEDULE-AGENT", None)
        attendee = vCalAddress(f"mailto:{my_address}")
        for existing in _attendees(event):
            if _address(existing) == my_address.lower():
                attendee.params.update({k: v for k, v in existing.params.items() if k in ("CN", "ROLE", "CUTYPE")})
        if name and "CN" not in attendee.params:
            attendee.params["CN"] = name
        attendee.params["PARTSTAT"] = status
        answer.add("ATTENDEE", attendee, encode=0)
        answer.add("DTSTAMP", datetime.now(timezone.utc))
        out.add_component(answer)
    return out.to_ical().decode()
