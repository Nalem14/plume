"""Ornis's limits, ready to show (docs/plans/2026-11-19-ornis-limites.md).

The cloud keeps them (OrnisQuota): fixed windows opened by the first request (a session of 5 hours, a week…), or a
rolling one. GET /ocs/v2.php/apps/orneos/api/v1/ornis/limits gives each window's share and when it renews; this
module turns that into the texts every app shows (Ornis, Plume, Notes, Tasks, Meet, Photos, Passwords, the panel and
the widgets of Orneos OS), so they all say the same thing the same way: « Session de 5 h · 48 % », « Ornis revient
demain à 9:00, dans 2 h 31. ». Shares and times only, never a number of credits.
"""
from __future__ import annotations

import time
from datetime import datetime

TEXT = {
    "fr": {
        "names": {"session": "Session de 5 h", "week": "Semaine", "month": "Mois", "day": "24 h glissantes"},
        "hours": "Sur {n} h", "days": "Sur {n} jours",
        "titles": {"session": "Session d’Ornis terminée", "week": "Limite de la semaine atteinte",
                   "month": "Limite du mois atteinte", "day": "Limite d’Ornis du jour atteinte"},
        "title": "Limite d’Ornis atteinte",
        "used": "{p} % utilisé", "full": "Limite atteinte", "left": "{p} % disponible",
        "renew": "se renouvelle {when}", "rolling": "chaque usage se libère {n} h après",
        "fresh": "commence à votre prochaine demande",
        "back": "Ornis revient {when}, dans {span}.", "back_short": "Ornis revient {when}.",
        "other": "{name} : encore {p} % disponible.", "kept": "Votre conversation est gardée : reprenez-la au retour d’Ornis.",
        "warn": "{name} : {p} % utilisé · {renew}", "line": "{name} · {p} %",
        "notify": "Me prévenir", "notify_on": "Vous serez prévenu", "returned": "Ornis est de retour : vous pouvez reprendre.",
        "sources": {"chat": "Discussion", "code": "Code", "ide": "Éditeur", "bot": "Bots", "voice": "Dictée",
                    "mail": "Courrier", "other": "Autres"},
        "at": "à {t}", "tomorrow": "demain à {t}", "weekday": "{d} à {t}", "date": "le {date} à {t}",
        "weekdays": ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"],
        "min": "{n} min", "hm": "{h} h {m}", "d": "{n} j",
    },
    "en": {
        "names": {"session": "5-hour session", "week": "Week", "month": "Month", "day": "Rolling 24 hours"},
        "hours": "Over {n} hours", "days": "Over {n} days",
        "titles": {"session": "Ornis session over", "week": "Weekly limit reached",
                   "month": "Monthly limit reached", "day": "Ornis daily limit reached"},
        "title": "Ornis limit reached",
        "used": "{p}% used", "full": "Limit reached", "left": "{p}% available",
        "renew": "renews {when}", "rolling": "each use frees up {n} hours later",
        "fresh": "starts with your next request",
        "back": "Ornis is back {when}, in {span}.", "back_short": "Ornis is back {when}.",
        "other": "{name}: {p}% still available.", "kept": "Your conversation is kept: carry on when Ornis is back.",
        "warn": "{name}: {p}% used · {renew}", "line": "{name} · {p}%",
        "notify": "Notify me", "notify_on": "You will be notified", "returned": "Ornis is back: you can carry on.",
        "sources": {"chat": "Chat", "code": "Code", "ide": "Editor", "bot": "Bots", "voice": "Dictation",
                    "mail": "Mail", "other": "Other"},
        "at": "at {t}", "tomorrow": "tomorrow at {t}", "weekday": "on {d} at {t}", "date": "on {date} at {t}",
        "weekdays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "min": "{n} min", "hm": "{h} h {m}", "d": "{n} d",
    },
    "de": {
        "names": {"session": "5-Stunden-Sitzung", "week": "Woche", "month": "Monat", "day": "Gleitende 24 Stunden"},
        "hours": "Über {n} Stunden", "days": "Über {n} Tage",
        "titles": {"session": "Ornis-Sitzung beendet", "week": "Wochenlimit erreicht",
                   "month": "Monatslimit erreicht", "day": "Tageslimit von Ornis erreicht"},
        "title": "Ornis-Limit erreicht",
        "used": "{p} % genutzt", "full": "Limit erreicht", "left": "{p} % verfügbar",
        "renew": "erneuert sich {when}", "rolling": "jede Nutzung wird {n} Stunden später frei",
        "fresh": "beginnt mit Ihrer nächsten Anfrage",
        "back": "Ornis ist {when} wieder da, in {span}.", "back_short": "Ornis ist {when} wieder da.",
        "other": "{name}: noch {p} % verfügbar.", "kept": "Ihre Unterhaltung bleibt erhalten: Machen Sie weiter, sobald Ornis zurück ist.",
        "warn": "{name}: {p} % genutzt · {renew}", "line": "{name} · {p} %",
        "notify": "Benachrichtigen", "notify_on": "Sie werden benachrichtigt", "returned": "Ornis ist wieder da: Sie können weitermachen.",
        "sources": {"chat": "Chat", "code": "Code", "ide": "Editor", "bot": "Bots", "voice": "Diktat",
                    "mail": "Mail", "other": "Sonstiges"},
        "at": "um {t}", "tomorrow": "morgen um {t}", "weekday": "am {d} um {t}", "date": "am {date} um {t}",
        "weekdays": ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
        "min": "{n} Min.", "hm": "{h} Std. {m}", "d": "{n} T.",
    },
}


def _t(lang: str) -> dict:
    return TEXT.get((lang or "fr")[:2], TEXT["en"])


def when(ts: int, lang: str, now: float | None = None) -> str:
    """« à 15:12 » today, « demain à 9:00 », « jeudi à 10:12 » within the week, « le 27/11 à 10:12 » after (local time)."""
    t = _t(lang)
    at = datetime.fromtimestamp(ts)
    today = datetime.fromtimestamp(now or time.time()).date()
    days = (at.date() - today).days
    # by hand: strftime's « %-I » and « %-d » do not exist on Windows (Plume), and « %b » follows the system's language
    clock = (f"{at.hour % 12 or 12}:{at.minute:02d} {'AM' if at.hour < 12 else 'PM'}" if lang[:2] == "en"
             else f"{at.hour:02d}:{at.minute:02d}")
    if days <= 0:
        return t["at"].format(t=clock)
    if days == 1:
        return t["tomorrow"].format(t=clock)
    if days < 7:
        return t["weekday"].format(d=t["weekdays"][at.weekday()], t=clock)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    date = (f"{months[at.month - 1]} {at.day}" if lang[:2] == "en"
            else f"{at.day:02d}.{at.month:02d}." if lang[:2] == "de" else f"{at.day:02d}/{at.month:02d}")
    return t["date"].format(date=date, t=clock)


def span(seconds: float, lang: str) -> str:
    """« 12 min », « 2 h 31 », « 3 j »."""
    t = _t(lang)
    m = max(1, int(-(-seconds // 60)))
    if m < 60:
        return t["min"].format(n=m)
    if m < 48 * 60:
        return t["hm"].format(h=m // 60, m=f"{m % 60:02d}")
    return t["d"].format(n=round(m / 1440))


def name(window: dict, lang: str) -> str:
    t = _t(lang)
    seconds = int(window.get("seconds") or 0)
    return t["names"].get(str(window.get("id")), (t["hours"] if seconds < 48 * 3600 else t["days"]).format(
        n=round(seconds / 3600) if seconds < 48 * 3600 else round(seconds / 86400)))


def renewal(window: dict, lang: str) -> str:
    t = _t(lang)
    if window.get("rolling"):
        return t["rolling"].format(n=round(int(window.get("seconds") or 0) / 3600))
    if window.get("open") and window.get("resets_at"):
        return t["renew"].format(when=when(int(window["resets_at"]), lang))
    return t["fresh"]


def level(percent: int, warn: int = 80) -> str:
    return "full" if percent >= 100 else "warn" if percent >= warn else "ok"


def view(limits: dict | None, lang: str, now: float | None = None) -> dict:
    """Everything an app shows of /ornis/limits, as text: {} when unknown or unlimited.

    percent, level: the window that will stop Ornis first (the ring); line: « Session de 5 h · 48 % »; detail:
    its renewal, or the warning from 80 %; windows: [{name, percent, level, used, renew}]; sources: « Code 62 % ·
    Discussion 31 % »; blocked: the card when a window is full: {title, when, others, kept, notify, notify_on, at}."""
    if not isinstance(limits, dict) or limits.get("unlimited") or not limits.get("windows"):
        return {}
    t = _t(lang)
    now = now or time.time()
    warn = int(limits.get("warn") or 80)
    windows = [w for w in limits["windows"] if isinstance(w, dict)]
    rows = []
    for w in windows:
        p = max(0, min(100, int(w.get("percent") or 0)))
        rows.append({"id": str(w.get("id")), "name": name(w, lang), "percent": p, "level": level(p, warn),
                     "used": t["full"] if p >= 100 else t["used"].format(p=p), "renew": renewal(w, lang)})
    nxt = next((r for r, w in zip(rows, windows) if w.get("id") == (limits.get("next") or {}).get("window")), rows[0])
    nxt_w = windows[rows.index(nxt)]
    blocked = limits.get("blocked") if isinstance(limits.get("blocked"), dict) else None
    out = {
        "percent": 100 if blocked else nxt["percent"],
        "level": "full" if blocked else nxt["level"],
        "line": t["line"].format(name=nxt["name"], p=100 if blocked else nxt["percent"]),
        "detail": (t["back_short"].format(when=when(int(blocked["resets_at"]), lang, now)) if blocked
                   else t["warn"].format(name=nxt["name"], p=nxt["percent"], renew=renewal(nxt_w, lang))
                   if nxt["level"] != "ok" else renewal(nxt_w, lang)),
        "windows": rows,
        "sources": " · ".join(f"{t['sources'].get(k, k)} {v} %" if lang[:2] != "en" else f"{t['sources'].get(k, k)} {v}%"
                              for k, v in (limits.get("sources") or {}).items()),
        "blocked": None,
    }
    if blocked:
        at = int(blocked["resets_at"])
        others = " ".join(t["other"].format(name=r["name"], p=100 - r["percent"])
                          for r in rows if r["id"] != blocked.get("window") and r["percent"] < 100)
        out["blocked"] = {
            "window": str(blocked.get("window")),
            "title": t["titles"].get(str(blocked.get("window")), t["title"]),
            "when": t["back"].format(when=when(at, lang, now), span=span(at - now, lang)),
            "short": t["back_short"].format(when=when(at, lang, now)),
            "others": others, "kept": t["kept"], "at": at,
            "notify": bool(limits.get("notify")), "notify_label": t["notify_on"] if limits.get("notify") else t["notify"],
        }
    return out


def message(limits: dict | None, lang: str) -> str:
    """One line for the apps that only say it in passing (Notes, Tasks, Photos…): « Session d’Ornis terminée.
    Ornis revient à 15:12. », or « » when nothing is known (the app keeps its own wording)."""
    v = view(limits, lang)
    b = v.get("blocked") if v else None
    return f"{b['title']}. {b['short']}" if b else ""


LIMITS = "/ocs/v2.php/apps/orneos/api/v1/ornis/limits?format=json"


def fetch(server: str, user: str, password: str) -> dict | None:
    """/ornis/limits of the account, with `percent` of the window that will stop Ornis first; a cloud without the
    windows answers as before (integration_openai's rolling 24 h: {percent} only). None when unknown or unlimited."""
    import cloud  # noqa: PLC0415 - the apps put /usr/share/orneos on their path
    status, body = cloud.ocs(server, user, password, LIMITS)
    data = (body.get("ocs") or {}).get("data") if isinstance(body, dict) and "ocs" in body else body
    if status in (200, 100) and isinstance(data, dict) and isinstance(data.get("windows"), list):
        if data.get("unlimited") or not data["windows"]:
            return None
        data["percent"] = 100 if data.get("blocked") else int((data.get("next") or {}).get("percent") or 0)
        return data
    status, body = cloud.rest(server, user, password, "/apps/integration_openai/quota-info")
    if status in (200, 100) and isinstance(body, dict):
        usage = body.get("quota_usage") or ((body.get("ocs") or {}).get("data") or {}).get("quota_usage")
        slot = usage[0] if isinstance(usage, list) and usage else (
            (usage.get(0) or usage.get("0")) if isinstance(usage, dict) else None)
        if isinstance(slot, dict) and int(slot.get("limit") or 0) > 0:
            return {"percent": min(100, round(100 * max(0, int(slot.get("used") or 0)) / int(slot["limit"])))}
    return None


def ring(limits: dict | None, lang: str) -> dict | None:
    """What the small apps' ring shows: {percent, line, detail} (line: « Session de 5 h · 48 % »)."""
    if not limits:
        return None
    v = view(limits, lang)
    return {"percent": int(limits.get("percent") or 0), "line": v.get("line", ""), "detail": v.get("detail", "")}
