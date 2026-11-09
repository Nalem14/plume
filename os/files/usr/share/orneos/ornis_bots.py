"""Local Code-mode bots: durable profiles under DATA/ornis-bots/<id>/.

Each bot has one canonical conversation, a SOUL.md, memory, skills, and optional
working folder. Exchanges between bots live in exchanges/<pair>.jsonl.
"""
from __future__ import annotations

import json
import contextlib
import functools
import re
import threading
import time
import uuid
from pathlib import Path

import system

ROOT = system.DATA / "ornis-bots"
INDEX = ROOT / "index.json"
EXCHANGES = ROOT / "exchanges"
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,38}[a-z0-9]$|^[a-z]{2,40}$")
LOCK = threading.RLock()

_depth = 0

@contextlib.contextmanager
def _locked():
    """Serialize app, HTTP MCP and fallback CLI read/modify/write transactions."""
    global _depth
    with LOCK:
        if _depth:
            yield
            return
        ROOT.mkdir(parents=True, exist_ok=True)
        with (ROOT / ".lock").open("a+b") as handle:
            if system.WINDOWS:
                import msvcrt
                handle.seek(0, 2)
                if handle.tell() == 0:    # msvcrt locks a byte range: one byte, written once
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            _depth = 1
            try:
                yield
            finally:
                _depth = 0
                if system.WINDOWS:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _transaction(fn):
    @functools.wraps(fn)
    def locked(*args, **kwargs):
        with _locked():
            return fn(*args, **kwargs)
    return locked

SHAPES = ("hexagon", "circle", "blob", "square", "triangle", "cloud", "teardrop", "pill")
COLORS = (
    "#7C5CFF", "#2F7D6D", "#1A5F7A", "#E85D4C", "#D4A017",
    "#C2185B", "#00897B", "#5C6BC0", "#EF6C00", "#6A1B9A",
    "#00838F", "#AD1457",
)

MEMORY_INDEX = "# Memory of this bot\n\n"
DEFAULT_SOUL = {
    "fr": """# SOUL

Tu es un bot Ornis autonome. Une seule conversation durable te lie à la personne.

- Décide, priorise, agis dans ton dossier de travail.
- Cherche d'abord une skill ou un connecteur **déjà là** avant d'en inventer.
- Quand une procédure de plusieurs étapes reviendra, écris-la en skill dans ton profil.
- Mets à jour ta mémoire : fusionne, corrige, retire ce qui est périmé. Jamais de secret.
- Une routine que tu crées tombe dans **ce** fil. Un message à un autre bot aussi.
""",
    "en": """# SOUL

You are an autonomous Ornis bot. One durable conversation ties you to the person.

- Decide, prioritise, act in your working folder.
- Look for a skill or connector **already there** before inventing one.
- When a multi-step procedure will come back, write it as a skill in your profile.
- Keep your memory tidy: merge, fix, drop what is stale. Never a secret.
- A routine you create lands in **this** thread. A message to another bot does too.
""",
    "de": """# SOUL

Du bist ein autonomer Ornis-Bot. Ein dauerhaftes Gespräch verbindet dich mit der Person.

- Entscheide, priorisiere, handle in deinem Arbeitsordner.
- Suche zuerst eine Skill oder einen Connector, der **schon da** ist.
- Wenn ein mehrstufiger Ablauf wiederkehrt, schreibe ihn als Skill in dein Profil.
- Halte dein Gedächtnis sauber: zusammenführen, korrigieren, Veraltetes löschen. Nie ein Geheimnis.
- Eine Routine, die du anlegst, landet in **diesem** Thread. Eine Nachricht an einen anderen Bot ebenso.
""",
}

MAINTENANCE_PROMPT = {
    "fr": (
        "Entretien hebdomadaire de ton profil : relis ta mémoire (memory/) et tes skills, "
        "dédoublonne ou retire ce qui est périmé ou faux, et dis en quelques lignes ce que tu as "
        "nettoyé. Si un connecteur déjà installé dans Ornis te manquerait pour ton travail, "
        "signale-le. Ne crée pas de fichier secret."
    ),
    "en": (
        "Weekly upkeep of your profile: reread your memory (memory/) and skills, merge or drop "
        "what is stale or wrong, and say in a few lines what you cleaned. If a connector already "
        "installed in Ornis would help your work, say so. Do not create secret files."
    ),
    "de": (
        "Wöchentliche Pflege deines Profils: lies Gedächtnis (memory/) und Skills erneut, "
        "führe zusammen oder lösche Veraltetes oder Falsches, und sag in wenigen Zeilen, was du "
        "bereinigt hast. Fehlt dir ein schon in Ornis installierter Connector, melde es. "
        "Keine Geheimdateien anlegen."
    ),
}


def _empty_index() -> dict:
    return {"version": 1, "bots": []}


def _ok_id(bot_id: str) -> str:
    tid = str(bot_id or "").strip().lower()
    if not ID_RE.match(tid):
        raise ValueError(
            "id must be 2–40 chars: lowercase letters, digits and dashes "
            "(not starting/ending with a dash)")
    return tid


def bot_dir(bot_id: str) -> Path:
    return ROOT / _ok_id(bot_id)


def workspace_of(bot_id: str) -> Path:
    """Default cwd when the bot has no project folder: its own workspace/."""
    path = bot_dir(bot_id) / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def face_from_name(name: str) -> dict:
    """Deterministic shape + colour from a title (same name → same face)."""
    n = sum(ord(c) for c in (name or "")) or 1
    return {"shape": SHAPES[n % len(SHAPES)], "color": COLORS[n % len(COLORS)]}


def load_index() -> dict:
    with LOCK:
        try:
            data = json.loads(INDEX.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("bots"), list):
                return _empty_index()
            return data
        except (OSError, ValueError):
            return _empty_index()


@_transaction
def save_index(data: dict) -> None:
    with LOCK:
        ROOT.mkdir(parents=True, exist_ok=True)
        system.private_write(INDEX, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def list_bots(*, include_hidden: bool = True) -> list[dict]:
    rows = []
    for entry in load_index().get("bots") or []:
        if not include_hidden and entry.get("hidden"):
            continue
        profile = get(entry.get("id") or "")
        if profile:
            rows.append(profile)
    return rows


def get(bot_id: str) -> dict | None:
    try:
        tid = _ok_id(bot_id)
    except ValueError:
        return None
    path = bot_dir(tid) / "profile.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    data["id"] = tid
    data.setdefault("title", tid)
    data.setdefault("description", "")
    face = data.get("face") if isinstance(data.get("face"), dict) else {}
    auto = face_from_name(data.get("title") or tid)
    data["face"] = {
        "shape": face.get("shape") or auto["shape"],
        "color": face.get("color") or auto["color"],
        "locked": bool(face.get("locked")),
    }
    data.setdefault("folder", "")
    data.setdefault("session", "")
    data.setdefault("hidden", False)
    data.setdefault("preview", "")
    data.setdefault("updated", 0)
    data.setdefault("created", 0)
    data.setdefault("enabled_skills", [])
    data.setdefault("exchange_seen", {})
    data.setdefault("approvals", [])
    return data


def _write_profile(bot_id: str, profile: dict, *, touch: bool = True) -> dict:
    tid = _ok_id(bot_id)
    root = bot_dir(tid)
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("memory", "skills", "enabled-skills", "workspace", "tmp"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    mem = root / "memory" / "MEMORY.md"
    if not mem.is_file():
        mem.write_text(MEMORY_INDEX, encoding="utf-8")
    soul = root / "SOUL.md"
    if not soul.is_file():
        lang = str(profile.get("lang") or "fr")[:2]
        soul.write_text(DEFAULT_SOUL.get(lang, DEFAULT_SOUL["en"]), encoding="utf-8")
    profile = dict(profile)
    profile["id"] = tid
    if touch or not profile.get("updated"):
        profile["updated"] = time.time()
    if "created" not in profile:
        profile["created"] = profile["updated"]
    system.private_write(root / "profile.json",
                         json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
    # keep the roster in sync
    with LOCK:
        data = load_index()
        entry = {"id": tid, "title": profile.get("title") or tid,
                 "hidden": bool(profile.get("hidden")), "updated": profile["updated"]}
        found = next((i for i, b in enumerate(data["bots"]) if b.get("id") == tid), -1)
        if found >= 0:
            data["bots"][found] = entry
        else:
            data["bots"].append(entry)
        data["bots"].sort(key=lambda b: -float(b.get("updated") or 0))
        save_index(data)
    return get(tid) or profile


def _folder_value(folder) -> str:
    if not str(folder or "").strip():
        return ""
    path = Path(str(folder).strip()).expanduser().resolve()
    if not path.is_dir():
        raise ValueError("Working folder does not exist")
    return str(path)


@_transaction
def create(fields: dict, *, lang: str = "fr") -> dict:
    """Create a bot. fields: id, title, description, folder?, face?, soul?, enabled_skills?."""
    tid = _ok_id(fields.get("id") or "")
    if get(tid):
        raise ValueError(f"bot already exists: {tid}")
    title = str(fields.get("title") or tid)[:80]
    face = fields.get("face") if isinstance(fields.get("face"), dict) else {}
    auto = face_from_name(title)
    if face.get("locked"):
        shape, color = face.get("shape") or auto["shape"], face.get("color") or auto["color"]
    else:
        shape, color = auto["shape"], auto["color"]
        if face.get("shape") in SHAPES:
            shape = face["shape"]
        if face.get("color"):
            color = str(face["color"])
    profile = {
        "id": tid,
        "title": title,
        "description": str(fields.get("description") or "")[:500],
        "folder": _folder_value(fields.get("folder")),
        "session": "",
        "hidden": False,
        "preview": "",
        "lang": (lang or "fr")[:2],
        "face": {"shape": shape, "color": color, "locked": bool(face.get("locked"))},
        "enabled_skills": list(fields.get("enabled_skills") or []),
        "exchange_seen": {},
    }
    created = _write_profile(tid, profile)
    if fields.get("soul"):
        set_soul(tid, str(fields["soul"]))
    if fields.get("enabled_skills"):
        created = set_enabled_skills(tid, fields["enabled_skills"])
    _seed_maintenance(tid, created, lang)
    return created


@_transaction
def update(bot_id: str, fields: dict) -> dict:
    profile = get(bot_id)
    if not profile:
        raise ValueError(f"unknown bot: {bot_id}")
    fields = dict(fields)
    if "folder" in fields:
        fields["folder"] = _folder_value(fields["folder"])
    for key in ("title", "description", "folder", "session", "preview", "hidden", "enabled_skills",
                "exchange_seen", "peer_depth", "human_turn", "approvals", "updated"):
        if key in fields and fields[key] is not None:
            profile[key] = fields[key]
    if "face" in fields and isinstance(fields["face"], dict):
        face = dict(profile.get("face") or {})
        face.update({k: fields["face"][k] for k in ("shape", "color", "locked")
                     if k in fields["face"] and fields["face"][k] is not None})
        if not face.get("locked"):
            auto = face_from_name(profile.get("title") or bot_id)
            face["shape"] = face.get("shape") or auto["shape"]
            face["color"] = face.get("color") or auto["color"]
        profile["face"] = face
    if "title" in fields and fields["title"] and not (profile.get("face") or {}).get("locked"):
        profile["face"] = {**face_from_name(str(fields["title"])), "locked": False}
    touch = bool("human_turn" in fields and "updated" not in fields)
    return _write_profile(bot_id, profile, touch=touch)


@_transaction
def remove(bot_id: str, *, confirm: bool = False) -> bool:
    if not confirm:
        raise ValueError("bot_delete requires confirm: true")
    tid = _ok_id(bot_id)
    root = bot_dir(tid)
    if not root.is_dir():
        return False
    import shutil  # noqa: PLC0415
    shutil.rmtree(root)
    with LOCK:
        data = load_index()
        data["bots"] = [b for b in data["bots"] if b.get("id") != tid]
        save_index(data)
    # A reused id must never inherit another bot's private exchanges or queued messages.
    for path in EXCHANGES.glob("*.jsonl"):
        if tid in path.stem.split("__"):
            path.unlink()
    for profile in list_bots():
        inbox = bot_dir(profile["id"]) / "inbox.json"
        try:
            data = json.loads(inbox.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        data["items"] = [r for r in data.get("items") or [] if r.get("from") != tid]
        system.private_write(inbox, json.dumps(data, ensure_ascii=False) + "\n")
    # drop routines attached to this bot
    try:
        import ornis_cron  # noqa: PLC0415
        for task in list(ornis_cron.tasks()):
            if task.get("bot") == tid:
                ornis_cron.remove(task["id"])
    except Exception:  # noqa: BLE001
        pass
    return True


def soul_path(bot_id: str) -> Path:
    return bot_dir(bot_id) / "SOUL.md"


def read_soul(bot_id: str) -> str:
    try:
        return soul_path(bot_id).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


@_transaction
def set_soul(bot_id: str, text: str) -> dict:
    if not get(bot_id):
        raise ValueError(f"unknown bot: {bot_id}")
    system.private_write(soul_path(bot_id), str(text or "").rstrip() + "\n")
    return update(bot_id, {})


def memory_index(bot_id: str) -> str:
    try:
        return (bot_dir(bot_id) / "memory" / "MEMORY.md").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def list_skills(bot_id: str) -> list[dict]:
    """Skills owned by this bot (skills/<name>/SKILL.md)."""
    out = []
    try:
        files = sorted((bot_dir(bot_id) / "skills").glob("*/SKILL.md"))
    except OSError:
        return out
    for path in files[:80]:
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:3000]
        except OSError:
            continue
        meta = re.match(r"^---\s*\n(.*?)\n---", head, re.S)
        fields = dict(re.findall(r"^(name|description):\s*(.+)$", meta.group(1), re.M)) if meta else {}
        out.append({
            "name": fields.get("name", path.parent.name).strip().strip("\"'"),
            "description": fields.get("description", "").strip().strip("\"'")[:200],
            "path": str(path),
            "owned": True,
        })
    return out


@_transaction
def set_enabled_skills(bot_id: str, names: list[str]) -> dict:
    """Which Ornis-global skills this bot may use (names under ornis-skills/)."""
    clean = []
    for name in names or []:
        n = re.sub(r"[^a-z0-9_-]+", "-", str(name).lower()).strip("-")
        if n and n not in clean:
            clean.append(n[:60])
    profile = update(bot_id, {"enabled_skills": clean[:80]})
    # refresh enabled-skills/ links for Vibe skill_paths
    link = bot_dir(bot_id) / "enabled-skills"
    try:
        import shutil  # noqa: PLC0415
        if link.is_dir():
            for child in link.iterdir():
                if child.is_symlink() or child.is_file():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
        link.mkdir(parents=True, exist_ok=True)
        import ornis_extensions  # noqa: PLC0415
        src_root = ornis_extensions.SKILLS
        for name in clean:
            src = src_root / name
            if src.is_dir():
                dest = link / name
                try:
                    dest.symlink_to(src, target_is_directory=True)
                except OSError:
                    if not dest.exists():
                        shutil.copytree(src, dest, symlinks=False)
    except Exception:  # noqa: BLE001
        pass
    return profile


def working_folder(bot_id: str) -> str:
    profile = get(bot_id)
    if not profile:
        raise ValueError(f"unknown bot: {bot_id}")
    folder = str(profile.get("folder") or "").strip()
    if folder and Path(folder).is_dir():
        return folder
    return str(workspace_of(bot_id))


def pair_key(a: str, b: str) -> str:
    x, y = sorted((_ok_id(a), _ok_id(b)))
    return f"{x}__{y}"


def exchange_path(a: str, b: str) -> Path:
    EXCHANGES.mkdir(parents=True, exist_ok=True)
    return EXCHANGES / f"{pair_key(a, b)}.jsonl"


@_transaction
def append_exchange(sender: str, target: str, message: str, *, kind: str = "message") -> dict:
    """Append one line to the shared journal. Returns the row."""
    sender, target = _ok_id(sender), _ok_id(target)
    if sender == target:
        raise ValueError("cannot message yourself")
    if not get(sender) or not get(target):
        raise ValueError("unknown bot")
    text = str(message or "").strip()
    if not text:
        raise ValueError("message is empty")
    depth = int((get(sender) or {}).get("peer_depth") or 0) + 1
    if depth > 3:
        raise ValueError("Automatic exchange limit reached; wait for a human message")
    row = {
        "burst": max(float((get(sender) or {}).get("human_turn") or 0),
                     float((get(target) or {}).get("human_turn") or 0)),
        "depth": depth,
        "id": str(uuid.uuid4()),
        "from": sender,
        "to": target,
        "text": text[:16000],
        "kind": kind,
        "at": time.time(),
    }
    path = exchange_path(sender, target)
    with LOCK:
        with path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    # bump previews
    try:
        update(sender, {"preview": text[:120], "updated": time.time()})
        update(target, {"preview": text[:120], "updated": time.time()})
    except ValueError:
        pass
    # queue delivery for the target
    queue_inbound(target, row)
    return row


def read_exchange(a: str, b: str, *, limit: int = 200) -> list[dict]:
    path = exchange_path(a, b)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines[-max(1, min(500, limit)):]:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


@_transaction
def queue_inbound(bot_id: str, row: dict) -> None:
    """Pending peer messages for a bot (delivered into its canonical session)."""
    path = bot_dir(bot_id) / "inbox.json"
    with LOCK:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {"items": []}
        items = list(data.get("items") or [])
        items.append(row)
        data["items"] = items
        system.private_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


@_transaction
def pop_inbound(bot_id: str, *, limit: int = 5) -> list[dict]:
    path = bot_dir(bot_id) / "inbox.json"
    with LOCK:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = list(data.get("items") or [])
        taken, rest = items[:limit], items[limit:]
        data["items"] = rest
        system.private_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return taken


@_transaction
def peek_inbound(bot_id: str) -> dict | None:
    try:
        data = json.loads((bot_dir(bot_id) / "inbox.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return next(iter(data.get("items") or []), None)


@_transaction
def ack_inbound(bot_id: str, message_id: str) -> None:
    path = bot_dir(bot_id) / "inbox.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    data["items"] = [r for r in data.get("items") or [] if r.get("id") != message_id]
    system.private_write(path, json.dumps(data, ensure_ascii=False) + "\n")


@_transaction
def mark_exchange_seen(bot_id: str, peer: str, at: float | None = None) -> None:
    profile = get(bot_id)
    if not profile:
        return
    seen = dict(profile.get("exchange_seen") or {})
    seen[_ok_id(peer)] = float(at if at is not None else time.time())
    update(bot_id, {"exchange_seen": seen})


def identity_block(bot_id: str, *, bots_cli: str = "ornis-bots") -> str:
    """Hidden prefix joined to the first message / after compact."""
    profile = get(bot_id)
    if not profile:
        return ""
    today = time.strftime("%Y-%m-%d (%A)")
    parts = [
        f"[Bot identity for `{profile['id']}` ({profile.get('title') or profile['id']}). "
        f"Today is {today}. This block is not shown to the person.\n",
        f"You are this bot. One durable conversation. `/new` and `/reset` compact this thread; "
        f"never fork it. Your SOUL overrides project and global style files.\n",
        f"Working folder: {working_folder(bot_id)}\n",
        f"Profile path: {bot_dir(bot_id)}\n\n",
    ]
    soul = read_soul(bot_id).strip()
    if soul:
        if len(soul) > 4000:
            soul = soul[:4000].rsplit("\n", 1)[0] + "\n[… cut: read the rest of SOUL.md when needed]"
        parts.append(f"## SOUL.md\n{soul}\n\n")
    desc = str(profile.get("description") or "").strip()
    if desc:
        parts.append(f"## Role\n{desc}\n\n")
    mem = memory_index(bot_id).strip()
    if mem and mem != MEMORY_INDEX.strip():
        if len(mem) > 6000:
            mem = mem[:6000].rsplit("\n", 1)[0] + "\n[…]"
        parts.append(f"## memory/MEMORY.md\n{mem}\n\n")
    own = list_skills(bot_id)
    if own:
        parts.append("## Your skills (load when useful)\n" +
                     "\n".join(f"- {s['name']}: {s['description']}" for s in own) + "\n\n")
    enabled = profile.get("enabled_skills") or []
    if enabled:
        parts.append("## Enabled Ornis skills\n" + ", ".join(enabled) + "\n\n")
    others = [b for b in list_bots(include_hidden=True) if b["id"] != profile["id"] and not b.get("hidden")]
    if others:
        parts.append("## Other bots on this computer\n" +
                     "\n".join(f"- `{b['id']}` — {b.get('title') or b['id']}"
                               + (f": {b['description']}" if b.get("description") else "")
                               for b in others) + "\n\n")
    parts.append(
        "## Autonomy\n"
        "- Prefer an existing skill or installed connector before inventing one.\n"
        "- When a multi-step procedure will come back, write a skill under your profile "
        f"`{bot_dir(bot_id) / 'skills'}`.\n"
        "- Keep memory tidy; never store secrets.\n"
        "- Routines you create (ornis-cron) attach to this bot and run **in this thread**.\n"
        "- Message another bot with `bot_message` (or the CLI below). Delivery is queued; "
        "do not wait for a reply in the same tool call.\n"
        "- If bot_* tools are missing from your tool list, run the local CLI instead:\n"
        f"  `{bots_cli}` list\n"
        f"  `{bots_cli}` create '{{\"id\":\"…\",\"title\":\"…\",\"description\":\"…\"}}'\n"
        f"  `{bots_cli}` message '{{\"target\":\"…\",\"message\":\"…\"}}'\n"
        f"  `{bots_cli}` soul / update / skills / delete — same JSON as the MCP tools.\n"
        "- Edit only your SOUL.md, memory/ and skills/ directly; use tools or CLI for profiles and messages.\n"
        "- End with `[SILENT]` when a peer message needs no visible reply.\n"
        "]\n\n"
    )
    return "".join(parts)


def _seed_maintenance(bot_id: str, profile: dict, lang: str) -> None:
    """Weekly Entretien routine; first due in a week."""
    try:
        import ornis_cron  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return
    import hashlib
    tid = "entretien-" + hashlib.sha256(bot_id.encode()).hexdigest()[:20]
    if ornis_cron.get(tid):
        return
    folder = working_folder(bot_id)
    prompt = MAINTENANCE_PROMPT.get((lang or "fr")[:2], MAINTENANCE_PROMPT["en"])
    try:
        now = time.time()
        # Keep the first run and every subsequent run on the same local weekday/time.
        local = time.localtime(now)
        schedule = f"{local.tm_min} {local.tm_hour} * * {(local.tm_wday + 1) % 7}"
        next_at = ornis_cron.next_run(schedule, now + 6 * 86400)
        ornis_cron.upsert({
            "id": tid,
            "title": {"fr": "Entretien", "en": "Upkeep", "de": "Pflege"}.get((lang or "fr")[:2], "Upkeep"),
            "description": "Weekly memory and skills tidy-up",
            "kind": "chat",
            "schedule": schedule,
            "prompt": prompt,
            "folder": folder,
            "bot": bot_id,
            "lang": (lang or "fr")[:2],
            "paused": False,
            "next_run": next_at,
            "allow_missing": True,
        }, create=True)
    except (ValueError, OSError):
        pass


def roster_for_prompt() -> list[dict]:
    return [{"id": b["id"], "title": b.get("title") or b["id"],
             "description": b.get("description") or "", "hidden": bool(b.get("hidden"))}
            for b in list_bots(include_hidden=True)]


def has_approval(bot_id: str, key: str) -> bool:
    """Whether this bot was already allowed to do this kind of action once."""
    key = str(key or "").strip()
    if not key:
        return False
    profile = get(bot_id)
    if not profile:
        return False
    return key in list(profile.get("approvals") or [])


@_transaction
def remember_approval(bot_id: str, key: str) -> bool:
    """Keep one « Autoriser » so the bot can work alone next time (and while you are away)."""
    key = str(key or "").strip()[:240]
    if not key:
        return False
    profile = get(bot_id)
    if not profile:
        return False
    kept = [str(x) for x in (profile.get("approvals") or []) if x]
    if key in kept:
        return True
    kept.append(key)
    profile["approvals"] = kept[-80:]
    _write_profile(bot_id, profile, touch=False)
    return True
