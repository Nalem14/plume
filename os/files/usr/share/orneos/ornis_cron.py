"""Local Code-mode cron tasks: crontab parsing, storage under DATA/ornis-code/cron.json.

Shared by the Ornis app (ornis_core.cron) and the built-in MCP server (ornis_cron_mcp).
Nothing here talks to the cloud. Wall-clock hours (8 stays 8 across DST).
"""
from __future__ import annotations

import calendar
import contextlib
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import system

ROOT = system.DATA / "ornis-code"
STORE = ROOT / "cron.json"
LOCK = threading.RLock()            # this process (app, HTTP MCP threads)
_FLOCK = ROOT / "cron.lock"         # other processes (CLI fallback, stdio MCP)
_depth = 0
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")
MIN_INTERVAL = 15 * 60          # seconds
CATCH_UP = 6 * 3600             # miss older than this → "missed", not run
DEFER = 15 * 60
MAX_RUNS = 40


def defer_for_open_code(*, kind: str, folder: str, code_folder: str,
                        agent_alive: bool, code_busy: bool, manual: bool) -> bool:
    """Auto runs wait only when Code is mid-turn on the same folder (not an idle agent)."""
    return (not manual and kind == "chat" and bool(folder) and folder == code_folder
            and agent_alive and code_busy)
ALIASES = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@midnight": "0 0 * * *",
}
_FIELD = re.compile(r"^(\*|\d+(?:-\d+)?(?:/\d+)?|\*/\d+)(?:,(\*|\d+(?:-\d+)?(?:/\d+)?|\*/\d+))*$")


# ---- crontab ------------------------------------------------------------------------------------------------------

def expand_alias(expr: str) -> str:
    raw = " ".join(str(expr or "").strip().split())
    return ALIASES.get(raw.lower(), raw)


def _parse_field(field: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part or not _FIELD.match(part.replace(",", "")) and not re.match(
                r"^(\*|\d+(?:-\d+)?(?:/\d+)?|\*/\d+)$", part):
            raise ValueError(f"invalid cron field: {field}")
        if part.startswith("*/"):
            step = int(part[2:])
            if step < 1:
                raise ValueError(f"invalid step: {part}")
            out.update(range(lo, hi + 1, step))
            continue
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
            if step < 1:
                raise ValueError(f"invalid step: {step_s}")
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if not (lo <= start <= hi and lo <= end <= hi):
            raise ValueError(f"out of range {lo}-{hi}: {part}")
        if start > end:
            raise ValueError(f"bad range: {part}")
        out.update(range(start, end + 1, step))
    return out


def parse_schedule(expr: str) -> tuple[str, list[set[int]]]:
    """Normalise a crontab (5 fields or @alias). Returns (canonical, [min, hour, dom, mon, dow])."""
    raw = expand_alias(expr)
    if raw.lower() == "@reboot":
        raise ValueError("@reboot is not supported: Ornis must already be running")
    parts = raw.split()
    if len(parts) != 5:
        raise ValueError("schedule must be five cron fields (minute hour day month weekday) or @daily/@hourly/…")
    for p in parts:
        if not re.match(r"^[\d*/,*-]+$", p):
            raise ValueError(f"invalid cron field: {p}")
    fields = [
        _parse_field(parts[0], 0, 59),
        _parse_field(parts[1], 0, 23),
        _parse_field(parts[2], 1, 31),
        _parse_field(parts[3], 1, 12),
        {d % 7 for d in _parse_field(parts[4], 0, 7)},   # 0 and 7 = Sunday (crontab)
    ]
    if not all(fields):
        raise ValueError("empty cron field")
    return " ".join(parts), fields


def min_gap_seconds(fields: list[set[int]]) -> int:
    """Smallest gap between two matching wall times over a week (seconds). Used for the 15-minute floor."""
    minutes, hours = sorted(fields[0]), sorted(fields[1])
    if len(minutes) == 60 and len(hours) == 24 and len(fields[2]) == 31 and len(fields[3]) == 12 and len(fields[4]) == 7:
        return 60
    times = []
    for h in hours:
        for m in minutes:
            times.append(h * 60 + m)
    times = sorted(set(times))
    if len(times) < 2:
        # one time of day: gap is one day if every day, else larger — treat as ≥ 15 min
        return 86400 if fields[2] == set(range(1, 32)) and fields[4] else 7 * 86400
    gaps = [times[i + 1] - times[i] for i in range(len(times) - 1)]
    gaps.append(times[0] + 24 * 60 - times[-1])
    return min(gaps) * 60


def validate_schedule(expr: str) -> str:
    canonical, fields = parse_schedule(expr)
    gap = min_gap_seconds(fields)
    if gap < MIN_INTERVAL:
        raise ValueError(f"too frequent (minimum every {MIN_INTERVAL // 60} minutes); got about every {max(1, gap // 60)} min")
    return canonical


def _matches(when: datetime, fields: list[set[int]]) -> bool:
    mins, hours, _, mons, _ = fields
    if when.minute not in mins or when.hour not in hours or when.month not in mons:
        return False
    return _day_ok(when, fields)


def _day_ok(when: datetime, fields: list[set[int]]) -> bool:
    # crontab: day-of-month OR day-of-week when both are constrained (classic cron OR)
    _, _, doms, _, dows = fields
    dom_star = len(doms) == 31
    dow_star = len(dows) == 7
    day_ok = when.day in doms
    # Python: Monday=0 … Sunday=6; crontab: Sunday=0 … Saturday=6
    cron_dow = (when.weekday() + 1) % 7
    dow_ok = cron_dow in dows
    if dom_star and dow_star:
        return True
    if not dom_star and not dow_star:
        return day_ok or dow_ok
    if not dom_star:
        return day_ok
    return dow_ok


def next_run(expr: str, after: float | None = None) -> float:
    """Next matching local wall time strictly after `after` (unix)."""
    _, fields = parse_schedule(expr)
    start = datetime.fromtimestamp(after if after is not None else time.time())
    # start from the next minute
    cursor = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = cursor + timedelta(days=366 * 2)
    mins, hours, _, mons, _ = fields
    while cursor < limit:
        # jump whole months / days / hours that cannot match (an impossible date stays cheap)
        if cursor.month not in mons:
            cursor = (cursor.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
            continue
        if not _day_ok(cursor, fields):
            cursor = cursor.replace(hour=0, minute=0) + timedelta(days=1)
            continue
        if cursor.hour not in hours:
            cursor = cursor.replace(minute=0) + timedelta(hours=1)
            continue
        if cursor.minute in mins:
            return cursor.timestamp()
        cursor += timedelta(minutes=1)
    raise ValueError("no next run in the next two years")


def previous_run(expr: str, before: float | None = None) -> float | None:
    """Most recent matching local wall time at or before `before`."""
    _, fields = parse_schedule(expr)
    end = datetime.fromtimestamp(before if before is not None else time.time()).replace(second=0, microsecond=0)
    cursor = end
    limit = cursor - timedelta(days=366 * 2)
    mins, hours, _, mons, _ = fields
    while cursor > limit:
        if cursor.month not in mons:
            cursor = cursor.replace(day=1, hour=0, minute=0) - timedelta(minutes=1)
            continue
        if not _day_ok(cursor, fields):
            cursor = cursor.replace(hour=0, minute=0) - timedelta(minutes=1)
            continue
        if cursor.hour not in hours:
            cursor = cursor.replace(minute=0) - timedelta(minutes=1)
            continue
        if cursor.minute in mins:
            return cursor.timestamp()
        cursor -= timedelta(minutes=1)
    return None


def period_seconds(expr: str) -> int:
    try:
        return max(MIN_INTERVAL, min_gap_seconds(parse_schedule(expr)[1]))
    except ValueError:
        return 86400


def schedule_label(expr: str, lang: str = "fr") -> str:
    """A short human phrase when the expression is a common pattern; else the crontab itself."""
    try:
        canonical, fields = parse_schedule(expr)
    except ValueError:
        return str(expr or "")
    mins, hours, doms, mons, dows = fields
    fr = lang.startswith("fr")
    de = lang.startswith("de")

    def hm(h, m):
        if fr:
            return f"{h} h {m:02d}" if m else f"{h} h"
        if de:
            return f"{h}:{m:02d} Uhr"
        return f"{h}:{m:02d}"

    if len(mins) == 1 and len(hours) == 1 and len(doms) == 31 and len(mons) == 12:
        h, m = next(iter(hours)), next(iter(mins))
        if len(dows) == 7:
            if fr:
                return f"Tous les jours à {hm(h, m)}"
            if de:
                return f"Täglich um {hm(h, m)}"
            return f"Every day at {hm(h, m)}"
        if dows == {1, 2, 3, 4, 5}:
            if fr:
                return f"Jours ouvrés à {hm(h, m)}"
            if de:
                return f"Werktags um {hm(h, m)}"
            return f"Weekdays at {hm(h, m)}"
        if len(dows) == 1:
            names = {
                "fr": ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"],
                "de": ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"],
                "en": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
            }
            day = names["fr" if fr else "de" if de else "en"][next(iter(dows))]
            if fr:
                return f"Chaque {day} à {hm(h, m)}"
            if de:
                return f"Jeden {day} um {hm(h, m)}"
            return f"Every {day} at {hm(h, m)}"
    if mins == set(range(0, 60, 15)) and hours == set(range(24)) and len(doms) == 31 and len(mons) == 12 and len(dows) == 7:
        return "Toutes les 15 minutes" if fr else ("Alle 15 Minuten" if de else "Every 15 minutes")
    if mins == {0} and len(hours) == 24 and len(doms) == 31 and len(mons) == 12 and len(dows) == 7:
        return "Toutes les heures" if fr else ("Stündlich" if de else "Every hour")
    if len(mins) == 1 and len(hours) == 1 and len(doms) == 1 and len(mons) == 12 and len(dows) == 7:
        h, m, d = next(iter(hours)), next(iter(mins)), next(iter(doms))
        if fr:
            return f"Le {d} de chaque mois à {hm(h, m)}"
        if de:
            return f"Am {d}. jeden Monats um {hm(h, m)}"
        return f"On the {d} of each month at {hm(h, m)}"
    return canonical


def next_times(expr: str, n: int = 2, after: float | None = None) -> list[float]:
    out, t = [], after if after is not None else time.time()
    for _ in range(n):
        t = next_run(expr, t)
        out.append(t)
    return out


def plain_to_cron(kind: str, hour: int = 8, minute: int = 0, weekday: int = 1, every: int = 15) -> str:
    """Shortcuts for the simple UI. weekday: 0=Sun … 6=Sat (crontab). every: minutes (≥ 15)."""
    hour, minute = int(hour) % 24, int(minute) % 60
    if kind == "daily":
        return f"{minute} {hour} * * *"
    if kind == "weekdays":
        return f"{minute} {hour} * * 1-5"
    if kind == "weekly":
        return f"{minute} {hour} * * {int(weekday) % 7}"
    if kind == "hourly":
        return f"{minute} * * * *"
    if kind == "every":
        step = max(15, int(every))
        if 60 % step != 0:
            raise ValueError(f"every N minutes: N must divide 60 (15, 20, 30…); got {step}")
        return f"*/{step} * * * *"
    raise ValueError(f"unknown plain kind: {kind}")


# ---- storage ------------------------------------------------------------------------------------------------------

def _empty() -> dict:
    return {"version": 1, "tasks": []}


@contextlib.contextmanager
def _locked():
    """LOCK plus an advisory file lock, so a CLI/MCP process and the app never interleave a read-modify-write.

    Reentrant inside this process (patch → upsert). Best effort: no lock file → the thread lock alone."""
    global _depth
    with LOCK:
        if _depth:
            _depth += 1
            try:
                yield
            finally:
                _depth -= 1
            return
        handle = None
        try:
            ROOT.mkdir(parents=True, exist_ok=True)
            handle = open(_FLOCK, "a+b")  # noqa: SIM115
            if system.WINDOWS:
                import msvcrt  # noqa: PLC0415
                for _ in range(100):
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
            else:
                import fcntl  # noqa: PLC0415
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError:
            pass
        _depth = 1
        try:
            yield
        finally:
            _depth = 0
            if handle is not None:
                try:
                    if system.WINDOWS:
                        import msvcrt  # noqa: PLC0415
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl  # noqa: PLC0415
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
                handle.close()


def load() -> dict:
    with LOCK:
        try:
            data = json.loads(STORE.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
                return _empty()
            return data
        except (OSError, ValueError):
            return _empty()


def save(data: dict) -> None:
    with _locked():
        ROOT.mkdir(parents=True, exist_ok=True)
        system.private_write(STORE, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def tasks() -> list[dict]:
    return list(load().get("tasks") or [])


def get(task_id: str) -> dict | None:
    tid = str(task_id or "").strip()
    for t in tasks():
        if t.get("id") == tid:
            return dict(t)
    return None


def _ok_id(task_id: str) -> str:
    tid = str(task_id or "").strip().lower()
    if not ID_RE.match(tid):
        raise ValueError("id must be 3–40 chars: lowercase letters, digits and dashes (not starting/ending with a dash)")
    return tid


def upsert(task: dict, *, create: bool = False) -> dict:
    """Insert or replace a task. Validates schedule and id. Sets next_run and scheduleLabel."""
    with _locked():
        data = load()
        tid = _ok_id(task.get("id", ""))
        existing = next((t for t in data["tasks"] if t.get("id") == tid), None)
        if create and existing:
            raise ValueError(f"task already exists: {tid}")
        if not create and not existing and not task.get("allow_missing"):
            # update path: must exist unless caller merges
            pass
        schedule = validate_schedule(str(task.get("schedule") or ""))
        kind = str(task.get("kind") or "chat")
        if kind not in ("chat", "script"):
            raise ValueError("kind must be chat or script")
        folder = str(task.get("folder") or "").strip()
        if not folder:
            raise ValueError("folder is required")
        prompt = str(task.get("prompt") or "")
        command = str(task.get("command") or "")
        if kind == "chat" and not prompt.strip():
            raise ValueError("prompt is required for a chat task")
        if kind == "script" and not command.strip():
            raise ValueError("command is required for a script task")
        lang = str(task.get("lang") or "fr")
        now = time.time()
        row = dict(existing or {})
        row.update({
            "id": tid,
            "title": str(task.get("title") or tid)[:120],
            "description": str(task.get("description") or "")[:500],
            "folder": folder,
            "kind": kind,
            "prompt": prompt,
            "command": command,
            "schedule": schedule,
            "scheduleLabel": schedule_label(schedule, lang),
            "paused": bool(task.get("paused", row.get("paused", False))),
            "updated": now,
            "runs": list(row.get("runs") or [])[:MAX_RUNS],
        })
        if "created" not in row:
            row["created"] = now
        # Honor an explicit next_run (defer / force queue); else recompute from the crontab
        if task.get("next_run") is not None:
            row["next_run"] = float(task["next_run"])
        elif not row["paused"]:
            row["next_run"] = next_run(schedule, now)
        else:
            row["next_run"] = row.get("next_run") or next_run(schedule, now)
        if "pending" in task:
            if task["pending"]:
                row["pending"] = task["pending"]
            else:
                row.pop("pending", None)
        elif task.get("clear_pending"):
            row.pop("pending", None)
        if task.get("pending_previous"):
            row["pending_previous"] = task["pending_previous"]   # what an AI update replaced (ask mode: « Annuler »)
        if not row.get("pending"):
            row.pop("pending_previous", None)
        if "force_run" in task:
            if task["force_run"]:
                row["force_run"] = True
            else:
                row.pop("force_run", None)
        data["tasks"] = [row if t.get("id") == tid else t for t in data["tasks"]]
        if not existing:
            data["tasks"].append(row)
        save(data)
        return dict(row)


def set_next_run(task_id: str, when: float) -> dict:
    """Set next_run without recomputing from the crontab (defer, catch-up)."""
    with _locked():
        data = load()
        for t in data["tasks"]:
            if t.get("id") != task_id:
                continue
            t["next_run"] = float(when)
            t["updated"] = time.time()
            save(data)
            return dict(t)
        raise ValueError(f"unknown task: {task_id}")


def clear_flag(task_id: str, *flags: str) -> dict:
    """Drop pending / force_run without touching next_run."""
    with _locked():
        data = load()
        for t in data["tasks"]:
            if t.get("id") != task_id:
                continue
            for f in flags:
                t.pop(f, None)
            t["updated"] = time.time()
            save(data)
            return dict(t)
        raise ValueError(f"unknown task: {task_id}")


def patch(task_id: str, fields: dict, lang: str = "fr") -> dict:
    with _locked():
        row = get(task_id)
        if not row:
            raise ValueError(f"unknown task: {task_id}")
        fields = {k: v for k, v in fields.items() if v is not None}
        if "schedule" in fields and expand_alias(fields["schedule"]) != row.get("schedule"):
            row.pop("next_run", None)        # the old due time belonged to the old rhythm
        row.update(fields)
        row["lang"] = lang
        return upsert(row, create=False)


def remove(task_id: str) -> bool:
    with _locked():
        data = load()
        before = len(data["tasks"])
        data["tasks"] = [t for t in data["tasks"] if t.get("id") != task_id]
        if len(data["tasks"]) == before:
            return False
        save(data)
        return True


def set_paused(task_id: str, paused: bool, lang: str = "fr") -> dict:
    return patch(task_id, {"paused": bool(paused)}, lang)


def add_run(task_id: str, run: dict) -> dict:
    with _locked():
        data = load()
        for t in data["tasks"]:
            if t.get("id") != task_id:
                continue
            runs = list(t.get("runs") or [])
            runs.insert(0, run)
            t["runs"] = runs[:MAX_RUNS]
            t["updated"] = time.time()
            save(data)
            return dict(t)
        raise ValueError(f"unknown task: {task_id}")


def update_run(task_id: str, run_id: str, fields: dict) -> dict:
    with _locked():
        data = load()
        for t in data["tasks"]:
            if t.get("id") != task_id:
                continue
            for r in t.get("runs") or []:
                if r.get("id") == run_id:
                    r.update(fields)
                    t["updated"] = time.time()
                    save(data)
                    return dict(t)
            raise ValueError(f"unknown run: {run_id}")
        raise ValueError(f"unknown task: {task_id}")


def bump_next(task_id: str, from_time: float | None = None) -> dict:
    with _locked():
        data = load()
        for t in data["tasks"]:
            if t.get("id") != task_id:
                continue
            t["next_run"] = next_run(t["schedule"], from_time if from_time is not None else time.time())
            t["updated"] = time.time()
            save(data)
            return dict(t)
        raise ValueError(f"unknown task: {task_id}")


def mtime() -> float:
    try:
        return STORE.stat().st_mtime
    except OSError:
        return 0.0
