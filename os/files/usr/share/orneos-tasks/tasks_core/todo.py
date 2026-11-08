"""Tasks as the cloud keeps them: one VTODO per iCalendar object, in the lists (calendars) of the account.

Read for the window (index), written from the window's fields (new, update), completed (a repeating task
moves on to its next date and leaves a completed copy behind, as on macOS), and merged property by property
when it changed both here and elsewhere (merge). Edits keep every property Tâches does not know, so nothing
the cloud's Tasks app, a phone or Thunderbird wrote is lost.

The same properties as the cloud's Tasks app: X-APPLE-SORT-ORDER (manual order), X-PINNED (the flag),
RELATED-TO (subtasks), CATEGORIES (tags), PRIORITY (1 high, 5 medium, 9 low). Ours: X-ORNEOS-MAIL (the
Message-ID of a mail tagged « À faire »), X-ORNEOS-MAIL-FROM, X-ORNEOS-NOTE (the id of a note of Notes),
X-ORNEOS-LINK (one per linked mail, note or task, its title in X-TITLE: links.py), X-ORNEOS-SECTION (the section of
its list it sits in; other apps ignore it).
Timed dates are written in UTC (no VTIMEZONE to keep in step); all-day ones as dates.

Reminders: relative to the due date (RELATED=END), so they follow it; for an all-day task they ring at
DAY_HOUR (9:00, as on macOS: PT9H the same day, -PT15H the day before), never at midnight. A reminder at a
precise moment is an absolute TRIGGER (VALUE=DATE-TIME, UTC), possible without a due date. Repeats are the
presets of REPEATS or any RRULE (every N days, weeks on some days, until a date, a number of times).
"""
import os
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from icalendar import Alarm, Calendar, Todo, vRecur

PRODID = "-//Orneos//Taches//FR"
VOLATILE = {"DTSTAMP", "LAST-MODIFIED", "SEQUENCE"}
REPEATS = {
    "DAILY": "FREQ=DAILY",
    "WEEKDAYS": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    "WEEKLY": "FREQ=WEEKLY",
    "BIWEEKLY": "FREQ=WEEKLY;INTERVAL=2",
    "MONTHLY": "FREQ=MONTHLY",
    "YEARLY": "FREQ=YEARLY",
}
DAY_HOUR = 9                    # all-day reminders ring then


def local_zone():
    tz = os.environ.get("TZ", "").lstrip(":")
    if "/" not in tz:
        path = os.path.realpath("/etc/localtime")
        tz = path.split("zoneinfo/", 1)[1] if "zoneinfo/" in path else ""
    if "/" not in tz:                       # Windows: no /etc/localtime, Qt knows the IANA name
        try:
            from PySide6.QtCore import QTimeZone  # noqa: PLC0415
            tz = bytes(QTimeZone.systemTimeZoneId().data()).decode()
        except ImportError:
            tz = "UTC"
    try:
        return ZoneInfo(tz)
    except Exception:
        return timezone.utc


def parse(ics):
    try:
        return Calendar.from_ical(ics)
    except Exception:
        return None


def _todo(cal):
    return next(iter(cal.walk("VTODO")), None) if cal is not None else None


def _moment(value):
    """(aware local datetime, all_day) of a DATE or DATE-TIME (floating times are local)."""
    tz = local_zone()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=tz)
        return value.astimezone(tz), False
    if isinstance(value, date):
        return datetime.combine(value, time(), tz), True
    return None, False


def _value(comp, key):
    prop = comp.get(key)
    return getattr(prop, "dt", None) if prop is not None else None


def _text(comp, key):
    value = comp.get(key)
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()


def _repeat_key(rule):
    if not rule:
        return ""
    for key, text in REPEATS.items():
        if rule.replace(";WKST=MO", "") == text:
            return key
    return "CUSTOM"


def _rrule_text(comp):
    prop = comp.get("RRULE")
    if prop is None:
        return ""
    return prop.to_ical().decode() if hasattr(prop, "to_ical") else str(prop)


def _categories(comp):
    out = []
    raw = comp.get("CATEGORIES")
    for prop in raw if isinstance(raw, list) else ([raw] if raw is not None else []):
        cats = getattr(prop, "cats", None)
        if cats is None:
            cats = str(prop).split(",")
        out += [str(c).strip() for c in cats if str(c).strip()]
    return list(dict.fromkeys(out))


def _parent(comp):
    raw = comp.get("RELATED-TO")
    for prop in raw if isinstance(raw, list) else ([raw] if raw is not None else []):
        reltype = str(getattr(prop, "params", {}).get("RELTYPE", "PARENT")).upper()
        if reltype == "PARENT":
            return str(prop).strip()
    return ""


def _alarms(comp, due, start, all_day=False):
    """[{"before": minutes (relative to the due date) | None, "at": epoch}] of the reminders. For an all-day
    task, a trigger between midnight and one hour before it (written by older versions, or by apps that mean
    « that day ») rings at DAY_HOUR: a reminder at midnight is never what was meant."""
    out = []
    for alarm in comp.walk("VALARM"):
        trigger = alarm.get("TRIGGER")
        if trigger is None:
            continue
        value = trigger.dt
        if isinstance(value, timedelta):
            related = str(trigger.params.get("RELATED", "START")).upper()
            anchor = due if (related == "END" or start is None) else start
            if anchor is None:
                continue
            at = anchor + value
            if all_day and timedelta(hours=-1) <= value <= timedelta(0):
                at = anchor + timedelta(hours=DAY_HOUR)
            before = int(-value.total_seconds() // 60) if related == "END" or start is None else None
            out.append({"before": before, "at": int(at.timestamp())})
        else:
            moment, _ = _moment(value)
            if moment is not None:
                out.append({"before": None, "at": int(moment.timestamp())})
    return out


def index(ics):
    """What the window, the store and the reminders need of one object, or None."""
    comp = _todo(parse(ics))
    if comp is None:
        return None
    due, due_day = _moment(_value(comp, "DUE"))
    start, start_day = _moment(_value(comp, "DTSTART"))
    when = due or start
    all_day = due_day if due is not None else start_day
    completed_at, _ = _moment(_value(comp, "COMPLETED"))
    status = _text(comp, "STATUS").upper()
    done = status == "COMPLETED" or completed_at is not None or _text(comp, "PERCENT-COMPLETE") == "100"
    created, _ = _moment(_value(comp, "CREATED"))
    modified, _ = _moment(_value(comp, "LAST-MODIFIED"))
    try:
        priority = int(_text(comp, "PRIORITY") or 0)
    except ValueError:
        priority = 0
    try:
        sort = int(_text(comp, "X-APPLE-SORT-ORDER")) if _text(comp, "X-APPLE-SORT-ORDER") else None
    except ValueError:
        sort = None
    rule = _rrule_text(comp)
    alarms = _alarms(comp, when, start, bool(when) and all_day)
    return {
        "uid": _text(comp, "UID"),
        "title": _text(comp, "SUMMARY"),
        "notes": str(comp.get("DESCRIPTION") or "").strip(),
        "due": (when.strftime("%Y-%m-%d") if all_day else when.strftime("%Y-%m-%dT%H:%M")) if when else "",
        "due_ts": int(when.timestamp()) if when else 0,
        "all_day": bool(all_day) if when else False,
        "done": bool(done),
        "done_ts": int(completed_at.timestamp()) if completed_at else 0,
        "cancelled": status == "CANCELLED",
        "priority": priority,
        "flagged": _text(comp, "X-PINNED").lower() == "true",
        "parent": _parent(comp),
        "sort": sort,
        "tags": _categories(comp),
        "url": _text(comp, "URL"),
        "location": _text(comp, "LOCATION"),
        "alarms": alarms,
        "alarm": alarm_key(alarms, bool(when) and all_day),
        "repeat": _repeat_key(rule),
        "rrule": rule,
        "mail": _text(comp, "X-ORNEOS-MAIL"),
        "mail_from": _text(comp, "X-ORNEOS-MAIL-FROM"),
        "note": _text(comp, "X-ORNEOS-NOTE"),
        "section": _text(comp, "X-ORNEOS-SECTION"),
        "links": _links(comp),
        "created": int(created.timestamp()) if created else 0,
        "modified": int(modified.timestamp()) if modified else 0,
        "hide_subtasks": _text(comp, "X-OC-HIDESUBTASKS") == "1",
    }


def _links(comp):
    values = comp.get("X-ORNEOS-LINK")
    values = values if isinstance(values, list) else [values] if values is not None else []
    return [{"url": str(v).strip(), "title": str(getattr(v, "params", {}).get("X-TITLE", ""))} for v in values if str(v).strip()]


def alarm_key(alarms, all_day=False):
    """The window's choice for the reminder: "" none, "0" at the time (the day itself, at DAY_HOUR, for an
    all-day task), "15" or "60" minutes before, "1440" the day before, "custom" anything else (an exact
    moment, several reminders, another delay)."""
    if not alarms:
        return ""
    if len(alarms) > 1 or alarms[0]["before"] is None:
        return "custom"
    before = alarms[0]["before"]
    if all_day:
        # minutes before midnight of the day: PT9H is -540 (that day), -PT15H is 900 (the day before)
        return "0" if -1440 < before <= 60 else "1440" if 60 < before <= 1440 else "custom"
    return str(before) if before in (0, 15, 60, 1440) else "custom"


# ---- writing ---------------------------------------------------------------------------------------------
def _parse_due(value):
    """"2026-10-22" (all day) or "2026-10-22T18:00" (local) → date or UTC datetime."""
    if not value:
        return None
    if "T" not in value:
        return date.fromisoformat(value[:10])
    moment = datetime.fromisoformat(value[:16])
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=local_zone())
    return moment.astimezone(timezone.utc)


def _set(comp, key, value):
    comp.pop(key, None)
    if value not in (None, "", [], False):
        comp.add(key, value)


def _stamp(comp):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for key in ("DTSTAMP", "LAST-MODIFIED"):
        comp.pop(key, None)
        comp.add(key, now)
    seq = int(str(comp.get("SEQUENCE", 0) or 0) or 0)
    comp.pop("SEQUENCE", None)
    comp.add("SEQUENCE", seq + 1)


def _all_day(comp):
    value = _value(comp, "DUE")
    value = value if value is not None else _value(comp, "DTSTART")
    return value is not None and not isinstance(value, datetime)


def _alarm_state(comp):
    """(the window's choice, all day) of the reminders as they are now."""
    due, due_day = _moment(_value(comp, "DUE"))
    start, start_day = _moment(_value(comp, "DTSTART"))
    when = due or start
    all_day = bool(when) and (due_day if due is not None else start_day)
    return alarm_key(_alarms(comp, when, start, all_day), all_day), all_day


def _set_alarm(comp, key, title):
    """key: "" none, "0" / "15" / "60" / "1440" (see alarm_key), or "at:2026-11-06T09:00" (a precise moment,
    local time). "custom" keeps what is there."""
    key = str(key or "")
    if key == "custom":
        return
    for sub in list(comp.subcomponents):
        if sub.name == "VALARM":
            comp.subcomponents.remove(sub)
    if not key:
        return
    alarm = Alarm()
    alarm.add("ACTION", "DISPLAY")
    alarm.add("DESCRIPTION", title or "Rappel")
    if key.startswith("at:"):
        try:
            moment = datetime.fromisoformat(key[3:19])
        except ValueError:
            return
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=local_zone())
        alarm.add("TRIGGER", moment.astimezone(timezone.utc).replace(second=0, microsecond=0), parameters={"VALUE": "DATE-TIME"})
    else:
        if comp.get("DUE") is None and comp.get("DTSTART") is None:
            return
        minutes = int(key)
        if _all_day(comp):
            # the day itself or the day before, at DAY_HOUR
            trigger = timedelta(hours=DAY_HOUR) - timedelta(days=1 if minutes >= 1440 else 0)
        else:
            trigger = timedelta(minutes=-minutes)
        alarm.add("TRIGGER", trigger, parameters={"RELATED": "END"})
    comp.add_component(alarm)


def _apply(comp, fields):
    if "title" in fields:
        _set(comp, "SUMMARY", str(fields["title"]).strip())
    if "notes" in fields:
        _set(comp, "DESCRIPTION", str(fields["notes"]).strip())
    if "url" in fields:
        _set(comp, "URL", str(fields["url"]).strip())
    if "location" in fields:
        _set(comp, "LOCATION", str(fields["location"]).strip())
    if "due" in fields:
        before_key, was_all_day = _alarm_state(comp)
        had_date = comp.get("DUE") is not None or comp.get("DTSTART") is not None
        due = _parse_due(fields["due"])
        _set(comp, "DUE", due)
        if due is None:
            comp.pop("DTSTART", None)
            # the reminders relative to the date go with it; one at a precise moment stays
            for sub in list(comp.subcomponents):
                if sub.name == "VALARM" and isinstance(getattr(sub.get("TRIGGER"), "dt", None), timedelta):
                    comp.subcomponents.remove(sub)
        elif "alarm" not in fields and had_date and was_all_day != (not isinstance(due, datetime)) \
                and before_key in ("0", "15", "60", "1440"):
            # a time given or taken away: the reminder chosen keeps its meaning (that day ↔ at the time)
            fields = dict(fields, alarm="1440" if before_key == "1440" else "0")
        if due is not None and comp.get("DTSTART") is not None:
            # a start after the new due date would make the task invalid: it follows
            start = _value(comp, "DTSTART")
            if type(start) is not type(due) or start > due:
                _set(comp, "DTSTART", due)
    if "priority" in fields:
        prio = int(fields["priority"] or 0)
        _set(comp, "PRIORITY", prio if prio else None)
    if "flagged" in fields:
        _set(comp, "X-PINNED", "true" if fields["flagged"] else None)
    if "tags" in fields:
        comp.pop("CATEGORIES", None)
        tags = [str(t).strip().lstrip("#") for t in fields["tags"] if str(t).strip().lstrip("#")]
        if tags:
            comp.add("CATEGORIES", tags)
    if "parent" in fields:
        comp.pop("RELATED-TO", None)
        if fields["parent"]:
            comp.add("RELATED-TO", fields["parent"], parameters={"RELTYPE": "PARENT"})
    if "sort" in fields:
        _set(comp, "X-APPLE-SORT-ORDER", str(int(fields["sort"])))
    if "mail" in fields:
        _set(comp, "X-ORNEOS-MAIL", fields["mail"])
    if "mail_from" in fields:
        _set(comp, "X-ORNEOS-MAIL-FROM", fields["mail_from"])
    if "section" in fields:
        _set(comp, "X-ORNEOS-SECTION", str(fields["section"] or "").strip())
    if "note" in fields:
        _set(comp, "X-ORNEOS-NOTE", str(fields["note"] or ""))
    if "links" in fields:
        comp.pop("X-ORNEOS-LINK", None)
        for link in fields["links"] or []:
            if str(link.get("url") or "").strip():
                title = str(link.get("title") or "").strip().replace('"', "'")
                comp.add("X-ORNEOS-LINK", str(link["url"]).strip(), parameters={"X-TITLE": title} if title else None)
    if "repeat" in fields:
        key = str(fields["repeat"] or "")
        if key != "CUSTOM":
            comp.pop("RRULE", None)
            rule = REPEATS.get(key) or (key if key.startswith("FREQ=") else "")
            if rule:
                comp.add("RRULE", vRecur.from_ical(rule))
                if comp.get("DTSTART") is None and comp.get("DUE") is not None:
                    comp.add("DTSTART", _value(comp, "DUE"))
    if "alarm" in fields:
        # relative to the due date (RELATED=END): it follows when the date changes
        _set_alarm(comp, fields["alarm"], str(comp.get("SUMMARY") or ""))
    if "done" in fields:
        _set_done(comp, bool(fields["done"]))


def _set_done(comp, done):
    for key in ("STATUS", "COMPLETED", "PERCENT-COMPLETE"):
        comp.pop(key, None)
    if done:
        comp.add("STATUS", "COMPLETED")
        comp.add("COMPLETED", datetime.now(timezone.utc).replace(microsecond=0))
        comp.add("PERCENT-COMPLETE", 100)
    else:
        comp.add("STATUS", "NEEDS-ACTION")


def new(fields, uid=None):
    """(uid, ics) of a new task from the window's fields."""
    uid = uid or str(uuid.uuid4())
    cal = Calendar()
    cal.add("PRODID", PRODID)
    cal.add("VERSION", "2.0")
    comp = Todo()
    comp.add("UID", uid)
    comp.add("CREATED", datetime.now(timezone.utc).replace(microsecond=0))
    comp.add("STATUS", "NEEDS-ACTION")
    _apply(comp, fields)
    _stamp(comp)
    cal.add_component(comp)
    return uid, cal.to_ical().decode()


def update(ics, fields):
    cal = parse(ics)
    comp = _todo(cal)
    if comp is None:
        return ics
    _apply(comp, fields)
    _stamp(comp)
    return cal.to_ical().decode()


def complete(ics, done=True):
    """(ics, copy): the task completed (or open again). A repeating one moves to its next date instead, and
    copy is the completed occurrence to keep (a new object), like on macOS. copy is None otherwise."""
    cal = parse(ics)
    comp = _todo(cal)
    if comp is None:
        return ics, None
    rule = _rrule_text(comp)
    due_value = _value(comp, "DUE")
    start_value = _value(comp, "DTSTART")
    anchor = due_value if due_value is not None else start_value
    if done and rule and anchor is not None:
        moment, all_day = _moment(anchor)
        first, _ = _moment(start_value if start_value is not None else anchor)
        parts = rule_parts(rule)
        count = int(parts.get("COUNT") or 0) if str(parts.get("COUNT") or "").isdigit() else 0
        try:
            rr = rrulestr(_local_rule(rule), dtstart=first.replace(tzinfo=None))
            following = rr.after(moment.replace(tzinfo=None))
        except Exception:
            following = None
        if count == 1:
            following = None                # the last time: done for good
        if following is not None:
            if count > 1:
                # the dates move on, so the count left goes down with them
                comp.pop("RRULE", None)
                comp.add("RRULE", vRecur.from_ical(";".join(f"{k}={count - 1 if k == 'COUNT' else v}" for k, v in parts.items())))
            copy_cal = parse(ics)
            copy = _todo(copy_cal)
            copy.pop("UID", None)
            copy.add("UID", str(uuid.uuid4()))
            copy.pop("RRULE", None)
            for sub in list(copy.subcomponents):
                if sub.name == "VALARM":
                    copy.subcomponents.remove(sub)
            _set_done(copy, True)
            _stamp(copy)
            # in wall-clock time: a task at 18:00 stays at 18:00 across a change of summer time
            shift = following - moment.replace(tzinfo=None)
            tz = local_zone()
            for key, value in (("DUE", due_value), ("DTSTART", start_value)):
                if value is None:
                    continue
                comp.pop(key, None)
                if all_day and not isinstance(value, datetime):
                    comp.add(key, value + timedelta(days=shift.days))
                else:
                    wall = _moment(value)[0].replace(tzinfo=None) + shift
                    comp.add(key, wall.replace(tzinfo=tz).astimezone(timezone.utc))
            _set_done(comp, False)
            _stamp(comp)
            return cal.to_ical().decode(), copy_cal.to_ical().decode()
    _set_done(comp, done)
    _stamp(comp)
    return cal.to_ical().decode(), None


def rule_parts(rule):
    """{"FREQ": "WEEKLY", "INTERVAL": "2", "BYDAY": "MO,TH", …} of an RRULE (without « RRULE: »), in order."""
    out = {}
    for part in str(rule or "").removeprefix("RRULE:").split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            out[key.strip().upper()] = value.strip()
    return out


def _local_rule(rule):
    """The rule for dateutil, whose dates here are local and naive: an UNTIL in UTC becomes local, an UNTIL that
    is a date takes in the whole of that day."""
    parts = rule_parts(rule)
    until = parts.get("UNTIL", "")
    if until:
        try:
            if until.endswith("Z"):
                moment = datetime.strptime(until, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(local_zone())
                parts["UNTIL"] = moment.strftime("%Y%m%dT%H%M%S")
            elif len(until) == 8:
                parts["UNTIL"] = until + "T235959"
        except ValueError:
            parts.pop("UNTIL")
    return ";".join(f"{k}={v}" for k, v in parts.items())


# ---- merge (changed here and elsewhere) --------------------------------------------------------------------
def _unfold(ics):
    lines = []
    for raw in (ics or "").replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _split(ics):
    """(before, {key: [lines]} in order, after) around the first VTODO; a VALARM is one key with its lines."""
    lines = _unfold(ics)
    try:
        begin = lines.index("BEGIN:VTODO")
        end = lines.index("END:VTODO", begin)
    except ValueError:
        return None
    props, block, inside = {}, None, False
    for line in lines[begin + 1:end]:
        if line == "BEGIN:VALARM":
            inside, block = True, [line]
            continue
        if inside:
            block.append(line)
            if line == "END:VALARM":
                props.setdefault("VALARM", []).extend(block)
                inside = False
            continue
        name = line.split(":", 1)[0].split(";", 1)[0].upper()
        props.setdefault(name, []).append(line)
    return lines[:begin + 1], props, lines[end:]


def merge(base, ours, theirs):
    """The task with the properties changed here on top of the cloud's version; a property changed on both
    sides keeps the value from here."""
    b, o, t = _split(base or ""), _split(ours), _split(theirs)
    if o is None or t is None:
        return ours
    b_props = b[1] if b else {}
    o_props, t_props = o[1], t[1]
    out = {}
    for key in list(t_props) + [k for k in o_props if k not in t_props]:
        if key in VOLATILE:
            continue
        mine, base_v, other = o_props.get(key), b_props.get(key), t_props.get(key)
        value = mine if mine != base_v else other
        if value:
            out[key] = value
    lines = t[0] + [line for values in out.values() for line in values] + t[2]
    merged = "\r\n".join(lines) + "\r\n"
    cal = parse(merged)
    comp = _todo(cal)
    if comp is None:
        return ours
    _stamp(comp)
    return cal.to_ical().decode()


def next_alarm(row, after):
    """The next reminder of an open task after `after` (epoch), or 0."""
    if row.get("done") or row.get("cancelled"):
        return 0
    times = [a["at"] for a in row.get("alarms") or [] if a["at"] > after]
    return min(times) if times else 0
