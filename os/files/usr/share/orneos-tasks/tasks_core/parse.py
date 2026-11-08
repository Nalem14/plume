"""Natural language in the « Nouvelle tâche » field, like macOS: « Appeler Inès demain 18h !! #travail »
gives the title « Appeler Inès », tomorrow at 18:00, medium priority, the tag travail. Dates, times,
repeats (« tous les 3 jours », « un samedi sur deux », « tous les mois le 5 »), a day of the month alone
(« le 12 »), the end of the month, priorities (! !! !!!), #tags and @list, in French, English and German. The window shows what was
understood as chips while one types; a chip can be removed to keep the words in the title.

Pure Python: parse(text, lang, now) → {title, due, repeat, priority, tags, list, chips}.
"""
import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta

WEEKDAYS = {
    "fr": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
    "en": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
    "de": ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"],
}
MONTHS = {
    "fr": ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre", "novembre", "decembre"],
    "en": ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"],
    "de": ["januar", "februar", "marz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november", "dezember"],
}
NUMBERS = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "dix": 10,
           "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ten": 10,
           "einem": 1, "einer": 1, "zwei": 2, "drei": 3, "vier": 4, "funf": 5, "zehn": 10}
PARTS = {"matin": "09:00", "midi": "12:00", "apres-midi": "15:00", "soir": "19:00",
         "morning": "09:00", "noon": "12:00", "afternoon": "15:00", "evening": "19:00", "tonight": "19:00",
         "fruh": "09:00", "mittag": "12:00", "nachmittag": "15:00", "abend": "19:00"}
# words left at the end of the title once a date is taken out (« Appeler Inès le »)
DANGLING = {"le", "la", "a", "au", "pour", "avant", "des", "de", "d", "on", "at", "by", "for", "in", "am", "um", "bis",
            "fur", "vor", "ab"}


def fold(text):
    """Lower case without accents, same length as the text (so spans map back onto it)."""
    out = []
    for ch in text:
        base = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in base if not unicodedata.combining(c)) or ch
        out.append(base[0].lower() if len(base) >= 1 else ch.lower())
    return "".join(out).replace("’", "'")


def _alt(words):
    return "(" + "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True)) + ")"


def _next_weekday(today, index, strictly=True):
    days = (index - today.weekday()) % 7
    if days == 0 and strictly:
        days = 7
    return today + timedelta(days=days)


def _add_months(day, months):
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _number(word):
    return int(word) if word.isdigit() else NUMBERS.get(word, 0)


def rules(lang):
    """[(kind, regex, handler(match, today, now) → value)] for one language, the longest phrases first."""
    wd = WEEKDAYS[lang]
    mo = MONTHS[lang]
    R = []

    def day(value):
        return lambda m, today, now: ("day", value(m, today))

    if lang == "fr":
        R += [
            ("repeat_every", r"\b(?:tous les|toutes les|chaque) (\d+|deux|trois|quatre|cinq|six|sept|huit|dix) (jours|semaines|mois|ans)\b", None),
            ("repeat_other", rf"\b(?:un|une) {_alt(wd)} sur deux\b", None),
            ("repeat_other", rf"\btous les deux {_alt(wd)}s?\b", None),
            ("repeat", r"\b(tous les jours|chaque jour|quotidiennement)\b", "DAILY"),
            ("repeat", r"\b(en semaine|tous les jours ouvres|chaque jour ouvre)\b", "WEEKDAYS"),
            ("repeat", r"\b(toutes les deux semaines|une semaine sur deux)\b", "BIWEEKLY"),
            ("repeat", r"\b(toutes les semaines|chaque semaine|hebdomadaire)\b", "WEEKLY"),
            ("repeat", r"\b(tous les mois|chaque mois|mensuel(?:lement)?)\b", "MONTHLY"),
            ("repeat", r"\b(tous les ans|chaque annee|annuel(?:lement)?)\b", "YEARLY"),
            ("repeat_day", rf"\b(?:tous les|chaque) {_alt(wd)}s?\b", None),
            ("day", r"\b(apres-demain|apres demain)\b", lambda m, t, n: t + timedelta(days=2)),
            ("day", r"\b(demain)\b", lambda m, t, n: t + timedelta(days=1)),
            ("day", r"\b(aujourd'hui|ce jour)\b", lambda m, t, n: t),
            ("daypart", r"\b(ce soir|cet apres-midi|ce midi|ce matin)\b", None),
            ("day", r"\b(la semaine prochaine)\b", lambda m, t, n: _next_weekday(t, 0)),
            ("day", r"\b(ce week-end|ce weekend)\b", lambda m, t, n: _next_weekday(t, 5, strictly=False)),
            ("day", r"\b(le mois prochain)\b", lambda m, t, n: _add_months(t.replace(day=1), 1)),
            ("day", rf"\b{_alt(wd)}( prochain)?\b", lambda m, t, n: _next_weekday(t, wd.index(m.group(1)))),
            ("in", r"\bdans (\d+|une?|deux|trois|quatre|cinq|six|sept|huit|dix) (jours?|semaines?|mois|heures?|h|minutes?|min)\b", None),
            ("date_m", rf"\b(?:le )?(\d{{1,2}}|1er) {_alt(mo)}(?: (\d{{4}}))?\b", None),
            ("date_n", r"\b(?:le )?(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", "dm"),
            ("eom", r"\b(?:a la |en |pour la )?fin (?:du|de) mois\b", None),
            ("dom", r"\b(?:le |avant le |pour le )(\d{1,2}|1er)\b(?![a-z\d]| ?(?:h\b|h\d|:)|[/.]\d)", None),
            ("time", r"\b(?:a |vers |pour )?(\d{1,2}) ?(?:h|:) ?(\d{2})?\b", None),
            ("time_word", r"\b(?:a )?(midi|minuit)\b", None),
            ("part", r"\b(?:le |dans la |en )?(matin|apres-midi|soir)\b", None),
        ]
    elif lang == "en":
        R += [
            ("repeat_every", r"\bevery (\d+|two|three|four|five|ten) (days|weeks|months|years)\b", None),
            ("repeat_other", rf"\bevery other {_alt(wd)}\b", None),
            ("repeat", r"\b(every day|daily)\b", "DAILY"),
            ("repeat", r"\b(every weekday|on weekdays|weekdays)\b", "WEEKDAYS"),
            ("repeat", r"\b(every other week|every 2 weeks|biweekly)\b", "BIWEEKLY"),
            ("repeat", r"\b(every week|weekly)\b", "WEEKLY"),
            ("repeat", r"\b(every month|monthly)\b", "MONTHLY"),
            ("repeat", r"\b(every year|yearly|annually)\b", "YEARLY"),
            ("repeat_day", rf"\bevery {_alt(wd)}\b", None),
            ("day", r"\b(the day after tomorrow)\b", lambda m, t, n: t + timedelta(days=2)),
            ("day", r"\b(tomorrow)\b", lambda m, t, n: t + timedelta(days=1)),
            ("day", r"\b(today)\b", lambda m, t, n: t),
            ("daypart", r"\b(tonight|this evening|this afternoon|this morning)\b", None),
            ("day", r"\b(next week)\b", lambda m, t, n: _next_weekday(t, 0)),
            ("day", r"\b(this weekend|at the weekend|on the weekend)\b", lambda m, t, n: _next_weekday(t, 5, strictly=False)),
            ("day", r"\b(next month)\b", lambda m, t, n: _add_months(t.replace(day=1), 1)),
            ("day", rf"\b(?:on |next )?{_alt(wd)}\b", lambda m, t, n: _next_weekday(t, wd.index(m.group(1)))),
            ("in", r"\bin (\d+|an?|one|two|three|four|five|ten) (days?|weeks?|months?|hours?|h|minutes?|mins?)\b", None),
            ("date_m", rf"\b(?:on )?{_alt(mo)} (\d{{1,2}})(?:st|nd|rd|th)?(?:,? (\d{{4}}))?\b", "md"),
            ("date_m", rf"\b(?:on )?(\d{{1,2}})(?:st|nd|rd|th)? {_alt(mo)}(?: (\d{{4}}))?\b", None),
            ("date_n", r"\b(?:on )?(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", "dm"),
            ("eom", r"\b(?:at the |by the |by )?end of (?:the )?month\b", None),
            ("dom", r"\b(?:on |by )?the (\d{1,2})(?:st|nd|rd|th)\b", None),
            ("dom", r"\bon the (\d{1,2})\b(?! ?(?::|/|\d|am|pm))", None),
            ("time", r"\b(?:at |by )?(\d{1,2})(?::(\d{2}))? ?(am|pm)\b", "ampm"),
            ("time", r"\b(?:at |by )?(\d{1,2}):(\d{2})\b", None),
            ("time_word", r"\b(?:at )?(noon|midnight)\b", None),
            ("part", r"\b(?:in the )?(morning|afternoon|evening)\b", None),
        ]
    else:
        R += [
            ("repeat_other", rf"\bjeden zweiten {_alt(wd)}\b", None),
            ("repeat_every", r"\balle (\d+|zwei|drei|vier|funf|zehn) (tage|wochen|monate|jahre)\b", None),
            ("repeat", r"\b(taglich|jeden tag)\b", "DAILY"),
            ("repeat", r"\b(werktags|an werktagen)\b", "WEEKDAYS"),
            ("repeat", r"\b(alle zwei wochen|alle 2 wochen|zweiwochentlich)\b", "BIWEEKLY"),
            ("repeat", r"\b(wochentlich|jede woche)\b", "WEEKLY"),
            ("repeat", r"\b(monatlich|jeden monat)\b", "MONTHLY"),
            ("repeat", r"\b(jahrlich|jedes jahr)\b", "YEARLY"),
            ("repeat_day", rf"\bjeden {_alt(wd)}\b", None),
            ("day", r"\b(ubermorgen)\b", lambda m, t, n: t + timedelta(days=2)),
            ("daypart", r"\b(heute (?:morgen|mittag|nachmittag|abend))\b", None),
            ("day", r"\b(morgen)\b", lambda m, t, n: t + timedelta(days=1)),
            ("day", r"\b(heute)\b", lambda m, t, n: t),
            ("day", r"\b(nachste woche)\b", lambda m, t, n: _next_weekday(t, 0)),
            ("day", r"\b(am wochenende)\b", lambda m, t, n: _next_weekday(t, 5, strictly=False)),
            ("day", r"\b(nachsten monat)\b", lambda m, t, n: _add_months(t.replace(day=1), 1)),
            ("day", rf"\b(?:am |nachsten |nachste )?{_alt(wd)}\b", lambda m, t, n: _next_weekday(t, wd.index(m.group(1)))),
            ("in", r"\bin (\d+|einem|einer|zwei|drei|vier|funf|zehn) (tagen?|wochen?|monaten?|monat|stunden?|minuten?)\b", None),
            ("date_m", rf"\b(?:am )?(\d{{1,2}})\. ?{_alt(mo)}(?: (\d{{4}}))?\b", None),
            ("date_n", r"\b(?:am )?(\d{1,2})\.(\d{1,2})\.(\d{2,4})?", "dm"),
            ("eom", r"\b(?:am |zum |bis )?(?:monatsende|ende des monats)\b", None),
            ("dom", r"\b(?:am |bis zum |zum )(\d{1,2})\.(?! ?\d)", None),
            ("time", r"\b(?:um )?(\d{1,2})(?::(\d{2}))? ?uhr(?: (\d{2}))?\b", "uhr"),
            ("time", r"\b(?:um )?(\d{1,2}):(\d{2})\b", None),
            ("part", r"\b(?:am )?(fruh|mittag|nachmittag|abend)s?\b", None),
        ]
    return [(kind, re.compile(pattern), value) for kind, pattern, value in R]


def parse(text, lang="fr", now=None, keep=(), month_first=False):
    """What the words say. keep: the kinds of chips the person removed (their words stay in the title)."""
    now = now or datetime.now()
    today = now.date()
    lang = lang if lang in WEEKDAYS else "fr"
    folded = fold(text)
    taken = [False] * len(text)
    out = {"day": None, "time": None, "repeat": "", "priority": 0, "tags": [], "list": "", "chips": []}
    wd = WEEKDAYS[lang]
    mo = MONTHS[lang]

    def take(m, group=0):
        a, b = m.span(group)
        if any(taken[a:b]):
            return False
        for i in range(a, b):
            taken[i] = True
        return True

    for kind, pattern, value in rules(lang):
        for m in pattern.finditer(folded):
            if any(taken[m.start():m.end()]):
                continue
            if kind == "repeat" and not out["repeat"] and "repeat" not in keep:
                take(m)
                out["repeat"] = value
            elif kind == "repeat_every" and not out["repeat"] and "repeat" not in keep:
                count, unit = _number(m.group(1)), m.group(2)
                if not count:
                    continue
                take(m)
                freq = ("DAILY" if unit.startswith(("jour", "day", "tag")) else "WEEKLY" if unit.startswith(("semaine", "week", "woche"))
                        else "MONTHLY" if unit.startswith(("mois", "month", "monat")) else "YEARLY")
                out["repeat"] = freq if count == 1 else "BIWEEKLY" if (freq, count) == ("WEEKLY", 2) else f"FREQ={freq};INTERVAL={count}"
            elif kind == "repeat_other" and not out["repeat"] and "repeat" not in keep:
                take(m)
                out["repeat"] = "BIWEEKLY"
                out["day"] = out["day"] or _next_weekday(today, wd.index(m.group(1)), strictly=False)
            elif kind == "eom" and out["day"] is None and "day" not in keep:
                take(m)
                out["day"] = today.replace(day=calendar.monthrange(today.year, today.month)[1])
            elif kind == "dom" and out["day"] is None and "day" not in keep:
                dnum = 1 if m.group(1) == "1er" else int(m.group(1))
                if not 1 <= dnum <= 31:
                    continue
                found, month = None, today.replace(day=1)
                for _ in range(13):         # this month if the day is still to come, else the next that has it
                    if dnum <= calendar.monthrange(month.year, month.month)[1] and month.replace(day=dnum) >= today:
                        found = month.replace(day=dnum)
                        break
                    month = _add_months(month, 1)
                if found is None:
                    continue
                take(m)
                out["day"] = found
            elif kind == "repeat_day" and not out["repeat"] and "repeat" not in keep:
                take(m)
                out["repeat"] = "WEEKLY"
                out["day"] = out["day"] or _next_weekday(today, wd.index(m.group(1)), strictly=False)
            elif kind == "day" and out["day"] is None and "day" not in keep:
                take(m)
                out["day"] = value(m, today, now)
            elif kind == "daypart" and "day" not in keep:
                take(m)
                words = m.group(1).split()
                part = words[-1]
                out["day"] = out["day"] or today
                if out["time"] is None and "time" not in keep:
                    out["time"] = PARTS.get("tonight" if part == "tonight" else part, "19:00")
            elif kind == "in" and "day" not in keep and out["day"] is None:
                count, unit = _number(m.group(1)), m.group(2)
                if not count:
                    continue
                take(m)
                if unit.startswith(("h", "stund")):
                    moment = now + timedelta(hours=count)
                    out["day"], out["time"] = moment.date(), moment.strftime("%H:%M")
                elif unit.startswith("min"):
                    moment = now + timedelta(minutes=count)
                    out["day"], out["time"] = moment.date(), moment.strftime("%H:%M")
                elif unit.startswith(("semaine", "week", "woche")):
                    out["day"] = today + timedelta(weeks=count)
                elif unit.startswith(("mois", "month", "monat")):
                    out["day"] = _add_months(today, count)
                else:
                    out["day"] = today + timedelta(days=count)
            elif kind == "date_m" and out["day"] is None and "day" not in keep:
                if value == "md":
                    month, dnum, year = mo.index(m.group(1)) + 1, m.group(2), m.group(3)
                else:
                    dnum, month, year = m.group(1), mo.index(m.group(2)) + 1, m.group(3)
                dnum = 1 if dnum == "1er" else int(dnum)
                try:
                    found = date(int(year) if year else today.year, month, dnum)
                except ValueError:
                    continue
                if not year and found < today:
                    found = found.replace(year=today.year + 1)
                take(m)
                out["day"] = found
            elif kind == "date_n" and out["day"] is None and "day" not in keep:
                a, b, year = int(m.group(1)), int(m.group(2)), m.group(3)
                dnum, month = (b, a) if month_first else (a, b)
                if year and len(year) == 2:
                    year = "20" + year
                try:
                    found = date(int(year) if year else today.year, month, dnum)
                except ValueError:
                    continue
                if not year and found < today:
                    found = found.replace(year=today.year + 1)
                take(m)
                out["day"] = found
            elif kind == "time" and out["time"] is None and "time" not in keep:
                hour = int(m.group(1))
                minute = int(m.group(2) or (m.group(3) if value == "uhr" and m.lastindex >= 3 and m.group(3) else 0) or 0)
                if value == "ampm":
                    suffix = m.group(3)
                    hour = hour % 12 + (12 if suffix == "pm" else 0)
                if hour > 23 or minute > 59:
                    continue
                # « 3 h » alone could be a duration: only a clock time with h/:/uhr counts
                take(m)
                out["time"] = f"{hour:02d}:{minute:02d}"
            elif kind == "time_word" and out["time"] is None and "time" not in keep:
                take(m)
                out["time"] = "12:00" if m.group(1) in ("midi", "noon") else "00:00"
            elif kind == "part" and out["time"] is None and "time" not in keep and (out["day"] is not None):
                take(m)
                out["time"] = PARTS[m.group(1)]

    # !, !!, !!! (alone), #tags and @list
    if "priority" not in keep:
        for m in re.finditer(r"(?:(?<=\s)|^)(!{1,3})(?=\s|$)", text):
            if take(m):
                out["priority"] = {1: 9, 2: 5, 3: 1}[len(m.group(1))]
                break
    if "tags" not in keep:
        for m in re.finditer(r"(?:(?<=\s)|^)#([^\W\d_][\w\-/]{0,40})", text, re.UNICODE):
            if take(m):
                out["tags"].append(m.group(1))
    if "list" not in keep:
        for m in re.finditer(r"(?:(?<=\s)|^)@([\w\-]{1,40})", text, re.UNICODE):
            if take(m):
                out["list"] = m.group(1)
                break

    if out["time"] and out["day"] is None:
        hour, minute = map(int, out["time"].split(":"))
        out["day"] = today if (hour, minute) > (now.hour, now.minute) else today + timedelta(days=1)

    words = "".join(" " if taken[i] else ch for i, ch in enumerate(text))
    words = re.sub(r"\s+", " ", words).strip(" ,;:-")
    parts = words.split(" ")
    while parts and fold(parts[-1]).strip(".,") in DANGLING:
        parts.pop()
    out["title"] = " ".join(parts).strip(" ,;:-")
    due = ""
    if out["day"] is not None:
        due = out["day"].isoformat() + (f"T{out['time']}" if out["time"] else "")
    out["due"] = due
    for kind in ("day", "time", "repeat", "priority", "tags", "list"):
        if kind in ("day", "time") and not out[kind]:
            continue
        if kind in ("repeat", "list") and not out[kind]:
            continue
        if kind == "priority" and not out[kind]:
            continue
        if kind == "tags" and not out[kind]:
            continue
        out["chips"].append(kind)
    out.pop("day")
    out.pop("time")
    return out
