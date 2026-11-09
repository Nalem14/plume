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
GROUPS = ROOT / "groups.json"
GROUP_LOGS = ROOT / "groups"
GROUP_FILES = ROOT / "group-files"   # each group's shared folder (unless the person chose one): every member writes there
NOTICES = ROOT / "notices.jsonl"
MAX_BOTS = 24            # a bot that creates bots in a loop stops here
MAX_GROUPS = 24
GROUP_HOPS = 3           # bots answering bots in a group without a human message in between
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


# Starting points of the « Nouveau bot » window: a name, a role, a face and a SOUL the person edits as they like
TEMPLATES = {
    "fr": [
        {"key": "watch", "title": "Veille", "description": "Suit un sujet sur le web et en fait un point court",
         "face": {"shape": "circle", "color": "#1A5F7A"},
         "soul": "# SOUL\n\nTu fais de la veille sur les sujets que la personne te confie.\n\n- Cherche avec Orneos Recherche, lis les sources, garde les plus fiables.\n- Rends un point court : ce qui a changé, pourquoi ça compte, les liens.\n- Note dans ta mémoire les sujets suivis et les sources utiles.\n- Propose une routine si un point régulier est utile.\n"},
        {"key": "writer", "title": "Rédaction", "description": "Écrit articles, mails et pages à partir de notes",
         "face": {"shape": "teardrop", "color": "#7C5CFF"},
         "soul": "# SOUL\n\nTu rédiges pour la personne : articles, mails, pages, posts.\n\n- Demande le public et le but si ce n’est pas clair, puis écris.\n- Phrases courtes, concrètes, sans jargon. Pas de formules creuses.\n- Écris dans des fichiers Markdown de ton dossier et dis lequel.\n- Garde en mémoire le ton et les préférences de la personne.\n"},
        {"key": "review", "title": "Relecture", "description": "Relit, corrige et resserre les textes",
         "face": {"shape": "pill", "color": "#E85D4C"},
         "soul": "# SOUL\n\nTu relis les textes qu’on te donne.\n\n- Corrige l’orthographe, la grammaire et la ponctuation.\n- Resserre : retire les répétitions et le jargon, garde le sens.\n- Dis en trois lignes ce que tu as changé et pourquoi.\n- Ne réécris pas tout : respecte la voix de l’auteur.\n"},
        {"key": "dev", "title": "Développement", "description": "Code, teste et corrige dans un projet",
         "face": {"shape": "hexagon", "color": "#2F7D6D"},
         "soul": "# SOUL\n\nTu développes dans le dossier de travail.\n\n- Lis le projet avant de changer quoi que ce soit.\n- Petits changements, puis les tests ; dis ce que tu as vérifié.\n- Explique les choix en une phrase, pas plus.\n- Écris en skill les procédures qui reviennent (build, déploiement).\n"},
        {"key": "organize", "title": "Organisation", "description": "Range les fichiers, prépare les points et les listes",
         "face": {"shape": "square", "color": "#D4A017"},
         "soul": "# SOUL\n\nTu aides la personne à s’organiser.\n\n- Range les fichiers par sujet, nomme-les clairement, ne supprime rien sans accord.\n- Prépare des listes de tâches et des points courts.\n- Propose des routines pour ce qui revient chaque semaine.\n"},
    ],
    "en": [
        {"key": "watch", "title": "Watch", "description": "Follows a topic on the web and sums it up",
         "face": {"shape": "circle", "color": "#1A5F7A"},
         "soul": "# SOUL\n\nYou watch the topics the person gives you.\n\n- Search with Orneos Search, read the sources, keep the reliable ones.\n- Report briefly: what changed, why it matters, the links.\n- Keep the topics and good sources in your memory.\n- Suggest a routine when a regular update helps.\n"},
        {"key": "writer", "title": "Writer", "description": "Writes articles, emails and pages from notes",
         "face": {"shape": "teardrop", "color": "#7C5CFF"},
         "soul": "# SOUL\n\nYou write for the person: articles, emails, pages, posts.\n\n- Ask for the audience and goal when unclear, then write.\n- Short, concrete sentences, no jargon.\n- Write Markdown files in your folder and say which.\n- Remember their tone and preferences.\n"},
        {"key": "review", "title": "Proofreader", "description": "Reads, corrects and tightens texts",
         "face": {"shape": "pill", "color": "#E85D4C"},
         "soul": "# SOUL\n\nYou proofread the texts you are given.\n\n- Fix spelling, grammar and punctuation.\n- Tighten: remove repetition and jargon, keep the meaning.\n- Say in three lines what you changed and why.\n- Keep the author's voice.\n"},
        {"key": "dev", "title": "Developer", "description": "Codes, tests and fixes in a project",
         "face": {"shape": "hexagon", "color": "#2F7D6D"},
         "soul": "# SOUL\n\nYou develop in the working folder.\n\n- Read the project before changing anything.\n- Small changes, then the tests; say what you checked.\n- Explain choices in one sentence.\n- Write recurring procedures as skills.\n"},
        {"key": "organize", "title": "Organizer", "description": "Sorts files, prepares updates and lists",
         "face": {"shape": "square", "color": "#D4A017"},
         "soul": "# SOUL\n\nYou help the person stay organised.\n\n- Sort files by topic, name them clearly, delete nothing without consent.\n- Prepare task lists and short updates.\n- Suggest routines for what comes back every week.\n"},
    ],
    "de": [
        {"key": "watch", "title": "Recherche", "description": "Verfolgt ein Thema im Web und fasst es zusammen",
         "face": {"shape": "circle", "color": "#1A5F7A"},
         "soul": "# SOUL\n\nDu verfolgst die Themen, die dir die Person gibt.\n\n- Suche mit Orneos Suche, lies die Quellen, behalte die verlässlichen.\n- Berichte kurz: was sich geändert hat, warum es zählt, die Links.\n- Merke dir Themen und gute Quellen.\n"},
        {"key": "writer", "title": "Texte", "description": "Schreibt Artikel, Mails und Seiten aus Notizen",
         "face": {"shape": "teardrop", "color": "#7C5CFF"},
         "soul": "# SOUL\n\nDu schreibst für die Person: Artikel, Mails, Seiten.\n\n- Frag nach Zielgruppe und Ziel, wenn unklar, dann schreib.\n- Kurze, konkrete Sätze, kein Jargon.\n- Schreib Markdown-Dateien in deinen Ordner und sag welche.\n"},
        {"key": "review", "title": "Lektorat", "description": "Liest, korrigiert und strafft Texte",
         "face": {"shape": "pill", "color": "#E85D4C"},
         "soul": "# SOUL\n\nDu liest Texte Korrektur.\n\n- Korrigiere Rechtschreibung, Grammatik, Zeichensetzung.\n- Straffe: Wiederholungen und Jargon raus, Sinn bleibt.\n- Sag in drei Zeilen, was du geändert hast.\n"},
        {"key": "dev", "title": "Entwicklung", "description": "Programmiert, testet und behebt Fehler in einem Projekt",
         "face": {"shape": "hexagon", "color": "#2F7D6D"},
         "soul": "# SOUL\n\nDu entwickelst im Arbeitsordner.\n\n- Lies das Projekt, bevor du etwas änderst.\n- Kleine Änderungen, dann die Tests; sag, was du geprüft hast.\n- Schreib wiederkehrende Abläufe als Skills.\n"},
        {"key": "organize", "title": "Organisation", "description": "Ordnet Dateien, bereitet Listen und Übersichten vor",
         "face": {"shape": "square", "color": "#D4A017"},
         "soul": "# SOUL\n\nDu hilfst der Person, organisiert zu bleiben.\n\n- Ordne Dateien nach Thema, lösche nichts ohne Zustimmung.\n- Bereite Aufgabenlisten und kurze Übersichten vor.\n"},
    ],
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
        "custom": bool(face.get("custom")),
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
    data.setdefault("unread", 0)
    data.setdefault("created_by", "")
    data.setdefault("paused", False)   # its routines, messages and group turns wait; the person can still write to it
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
def create(fields: dict, *, lang: str = "fr", actor: str = "") -> dict:
    """Create a bot. fields: id, title, description, folder?, face?, soul?, enabled_skills?.
    actor: the bot creating it (its MCP/CLI), empty for the person: a bot may only point the new one at its own
    working folder (or none), never widen what can be written on this computer."""
    tid = _ok_id(fields.get("id") or "")
    if get(tid):
        raise ValueError(f"bot already exists: {tid}")
    if len(load_index().get("bots") or []) >= MAX_BOTS:
        raise ValueError(f"too many bots on this computer ({MAX_BOTS}); delete one first")
    actor = str(actor or "").strip()
    if actor:
        _check_folder_scope(actor, fields.get("folder"))
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
        "face": {"shape": shape, "color": color, "locked": bool(face.get("locked")),
                 "custom": bool(face.get("locked") or face.get("shape") or face.get("color"))},
        "enabled_skills": list(fields.get("enabled_skills") or []),
        "exchange_seen": {},
        "created_by": actor,
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
                "exchange_seen", "peer_depth", "group_depth", "human_turn", "approvals", "updated", "unread",
                "paused", "group_turn"):
        if key in fields and fields[key] is not None:
            profile[key] = fields[key]
    if "title" in fields:
        profile["title"] = str(profile.get("title") or bot_id)[:80]
    if "description" in fields:
        profile["description"] = str(profile.get("description") or "")[:500]
    if "face" in fields and isinstance(fields["face"], dict):
        face = dict(profile.get("face") or {})
        face.update({k: fields["face"][k] for k in ("shape", "color", "locked")
                     if k in fields["face"] and fields["face"][k] is not None})
        if face.get("shape") not in SHAPES:
            face.pop("shape", None)
        auto = face_from_name(profile.get("title") or bot_id)
        face["shape"] = face.get("shape") or auto["shape"]
        face["color"] = face.get("color") or auto["color"]
        face["custom"] = True                    # chosen by someone: a later rename keeps it
        profile["face"] = face
    elif "title" in fields and fields["title"]:
        face = profile.get("face") or {}
        if not face.get("locked") and not face.get("custom"):
            profile["face"] = {**face_from_name(str(fields["title"])), "locked": False, "custom": False}
    touch = bool("human_turn" in fields and "updated" not in fields)
    return _write_profile(bot_id, profile, touch=touch)


@_transaction
def remove(bot_id: str, *, confirm: bool = False, actor: str = "") -> bool:
    if not confirm:
        raise ValueError("bot_delete requires confirm: true")
    tid = _ok_id(bot_id)
    if actor:
        check_manage(actor, tid, delete=True)
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
    # leave every group (a group left with fewer than two bots stays, the person decides)
    try:
        data = _load_groups()
        for g in data["groups"]:
            if tid in g.get("members", []):
                g["members"] = [m for m in g["members"] if m != tid]
                if g.get("lead") == tid:
                    g["lead"] = (g["members"] or [""])[0]
        _save_groups(data)
    except (OSError, ValueError):
        pass
    # drop routines attached to this bot
    try:
        import ornis_cron  # noqa: PLC0415
        for task in list(ornis_cron.tasks()):
            if task.get("bot") == tid:
                ornis_cron.remove(task["id"])
    except Exception:  # noqa: BLE001
        pass
    return True


def _check_folder_scope(actor: str, folder) -> None:
    """A bot may give a working folder only inside its own (or its profile): never open more of the disk."""
    if not str(folder or "").strip():
        return
    path = Path(str(folder).strip()).expanduser().resolve()
    roots = [Path(working_folder(actor)).resolve(), bot_dir(actor).resolve()]
    if not any(path == r or path.is_relative_to(r) for r in roots):
        raise ValueError("a bot can only use a folder inside its own working folder; ask the person to choose another one")


def check_manage(actor: str, target: str, *, delete: bool = False) -> None:
    """What a bot may do to a profile: itself, or the bots it created. The person (no actor) may do everything."""
    actor, target = str(actor or "").strip(), _ok_id(target)
    if not actor:
        return
    if actor == target:
        if delete:
            raise ValueError("a bot cannot delete itself; ask the person")
        return
    profile = get(target)
    if profile and profile.get("created_by") == actor:
        return
    raise ValueError(f"`{target}` is not yours: a bot changes only itself or the bots it created; ask the person")


# ---- unread and notifications -------------------------------------------------------------------------------------
@_transaction
def bump_unread(bot_id: str, n: int = 1) -> None:
    """A bot spoke while its conversation was not in front (routine, message, group): the list shows a badge."""
    profile = get(bot_id)
    if not profile:
        return
    profile["unread"] = min(99, int(profile.get("unread") or 0) + max(1, int(n)))
    _write_profile(bot_id, profile, touch=False)


@_transaction
def clear_unread(bot_id: str) -> None:
    profile = get(bot_id)
    if profile and int(profile.get("unread") or 0):
        profile["unread"] = 0
        _write_profile(bot_id, profile, touch=False)


@_transaction
def push_notice(bot_id: str, title: str, text: str) -> dict:
    """notify_user: a desktop notification from a bot (picked up by the window, which shows it once)."""
    bid = _ok_id(bot_id)
    if not get(bid):
        raise ValueError(f"unknown bot: {bid}")
    body = str(text or "").strip()
    if not body:
        raise ValueError("message is empty")
    # at most 6 notifications per bot and hour: a routine in a loop must not flood the desktop
    recent = [r for r in _read_notices() if r.get("bot") == bid and time.time() - float(r.get("at") or 0) < 3600]
    if len(recent) >= 6:
        raise ValueError("notification limit reached (6 per hour); write in your conversation instead")
    row = {"id": str(uuid.uuid4()), "bot": bid, "title": str(title or "").strip()[:80], "text": body[:400],
           "at": time.time(), "shown": False}
    ROOT.mkdir(parents=True, exist_ok=True)
    with NOTICES.open("a", encoding="utf-8") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _read_notices() -> list[dict]:
    try:
        lines = NOTICES.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-200:]:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


@_transaction
def take_notices() -> list[dict]:
    """The notifications not shown yet (marked shown; the file keeps the last day for the hourly limit)."""
    rows = _read_notices()
    fresh = [r for r in rows if not r.get("shown")]
    if not fresh:
        return []
    keep = [dict(r, shown=True) for r in rows if time.time() - float(r.get("at") or 0) < 86400]
    system.private_write(NOTICES, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep))
    return fresh


# ---- groups: several bots in one room, each with its own identity, memory and thread -----------------------------
# A group is a shared journal (groups/<id>.jsonl) plus who is in it. A message is delivered to the bots it concerns
# (@mentions, else the lead, or everyone) as a turn of their own durable conversation, with the recent room
# transcript: no merged « super bot », every bot answers as itself. Their answers are posted back to the room, and an
# answer that @mentions another member hands it over (GROUP_HOPS at most without a human message).
def _empty_groups() -> dict:
    return {"version": 1, "groups": []}


def _load_groups() -> dict:
    try:
        data = json.loads(GROUPS.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("groups"), list):
            return data
    except (OSError, ValueError):
        pass
    return _empty_groups()


def _save_groups(data: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    system.private_write(GROUPS, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _group_view(g: dict) -> dict:
    g = dict(g)
    g.setdefault("title", g.get("id") or "")
    g.setdefault("description", "")
    g["members"] = [m for m in g.get("members") or [] if get(m)]
    if g.get("lead") not in g["members"]:
        g["lead"] = (g["members"] or [""])[0]
    if g.get("reply") not in ("lead", "all"):
        g["reply"] = "lead"
    g.setdefault("unread", 0)
    g.setdefault("read_at", 0)       # the person's last visit: the « Non lu » bar goes before what came after
    g.setdefault("anchor", "")       # the message at the top of the view when they left, scrolled up (else "")
    g.setdefault("folder", "")       # the shared folder chosen by the person ("" = group-files/<id>)
    g.setdefault("updated", 0)
    g.setdefault("preview", "")
    return g


def list_groups() -> list[dict]:
    rows = [_group_view(g) for g in _load_groups()["groups"]]
    return sorted(rows, key=lambda g: -float(g.get("updated") or 0))


def get_group(group_id: str) -> dict | None:
    gid = str(group_id or "").strip().lower()
    hit = next((g for g in _load_groups()["groups"] if g.get("id") == gid), None)
    return _group_view(hit) if hit else None


def group_folder(group_id: str) -> str:
    """Where the members of a group work together: the folder chosen for it, else its own under group-files/."""
    g = get_group(group_id) or {}
    chosen = str(g.get("folder") or "").strip()
    if chosen and Path(chosen).is_dir():
        return chosen
    path = GROUP_FILES / str(g.get("id") or group_id)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def shared_folders(bot_id: str) -> list[str]:
    """The shared folders of the groups a bot is in (writable in its sandbox, next to its own folder)."""
    return [group_folder(g["id"]) for g in groups_of(bot_id)]


def groups_of(bot_id: str) -> list[dict]:
    return [g for g in list_groups() if bot_id in g["members"]]


def _clean_members(members) -> list[str]:
    out = []
    for m in members or []:
        try:
            mid = _ok_id(m)
        except ValueError:
            continue
        if get(mid) and mid not in out:
            out.append(mid)
    return out


@_transaction
def create_group(fields: dict, *, actor: str = "") -> dict:
    title = str(fields.get("title") or "").strip()[:80]
    if not title:
        raise ValueError("a group needs a title")
    members = _clean_members(fields.get("members"))
    if actor and actor not in members:
        members.insert(0, actor)                 # a bot that makes a group is in it
    if len(members) < 2:
        raise ValueError("a group needs at least two bots")
    data = _load_groups()
    if len(data["groups"]) >= MAX_GROUPS:
        raise ValueError(f"too many groups ({MAX_GROUPS}); delete one first")
    import unicodedata  # noqa: PLC0415
    plain = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()   # « Équipe » → equipe
    base = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:30] or "group"
    gid, n = base, 2
    while any(g.get("id") == gid for g in data["groups"]):
        gid, n = f"{base}-{n}", n + 1
    lead = str(fields.get("lead") or "").strip().lower()
    folder = _folder_value(fields.get("folder"))
    if actor and folder:
        _check_folder_scope(actor, folder)       # a bot shares only what it may already write
    now = time.time()
    group = {"id": gid, "title": title, "description": str(fields.get("description") or "")[:500], "folder": folder,
             "members": members, "lead": lead if lead in members else members[0],
             "reply": fields.get("reply") if fields.get("reply") in ("lead", "all") else "lead",
             "created": now, "updated": now, "preview": "", "unread": 0, "created_by": actor}
    data["groups"].append(group)
    _save_groups(data)
    return _group_view(group)


@_transaction
def update_group(group_id: str, fields: dict, *, actor: str = "") -> dict:
    data = _load_groups()
    g = next((x for x in data["groups"] if x.get("id") == str(group_id or "").strip().lower()), None)
    if not g:
        raise ValueError(f"unknown group: {group_id}")
    if actor and actor not in (g.get("members") or []):
        raise ValueError("only a member of this group can change it")
    if "title" in fields and str(fields["title"] or "").strip():
        g["title"] = str(fields["title"]).strip()[:80]
    if "description" in fields and fields["description"] is not None:
        g["description"] = str(fields["description"])[:500]
    if "members" in fields and fields["members"] is not None:
        members = _clean_members(fields["members"])
        if len(members) < 2:
            raise ValueError("a group needs at least two bots")
        g["members"] = members
    if "folder" in fields and fields["folder"] is not None:
        if actor:
            raise ValueError("only the person changes a group's shared folder")
        g["folder"] = _folder_value(fields["folder"])
    if "lead" in fields and fields["lead"] in (g.get("members") or []):
        g["lead"] = fields["lead"]
    if fields.get("reply") in ("lead", "all"):
        g["reply"] = fields["reply"]
    for key in ("unread", "preview", "updated", "human_turn", "read_at", "anchor"):
        if key in fields and fields[key] is not None:
            g[key] = fields[key]
    _save_groups(data)
    return _group_view(g)


@_transaction
def remove_group(group_id: str) -> bool:
    gid = str(group_id or "").strip().lower()
    data = _load_groups()
    before = len(data["groups"])
    data["groups"] = [g for g in data["groups"] if g.get("id") != gid]
    if len(data["groups"]) == before:
        return False
    _save_groups(data)
    try:
        (GROUP_LOGS / f"{gid}.jsonl").unlink()
    except OSError:
        pass
    drop_group_inbox(gid)                        # what was still waiting for this room goes too
    return True


def read_group(group_id: str, *, limit: int = 200) -> list[dict]:
    gid = str(group_id or "").strip().lower()
    try:
        lines = (GROUP_LOGS / f"{gid}.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines[-max(1, min(1000, limit)):]:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def group_size(group_id: str) -> int:
    """How many messages the room holds (the view loads the last ones, then older ones as you scroll up)."""
    gid = str(group_id or "").strip().lower()
    try:
        with (GROUP_LOGS / f"{gid}.jsonl").open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def mentions(text: str, members: list[str]) -> list[str]:
    """Members named with @id or @Title in a message (in their order of appearance)."""
    low = str(text or "").lower()
    found = []
    for mid in members:
        profile = get(mid) or {}
        names = {mid, str(profile.get("title") or "").lower()}
        at = min((low.find("@" + n) for n in names if n and ("@" + n) in low), default=-1)
        if at >= 0:
            found.append((at, mid))
    return [mid for _, mid in sorted(found)]


@_transaction
def post_group(group_id: str, sender: str, text: str, *, depth: int = 0, route: bool = True,
               only: list[str] | None = None) -> dict:
    """Write one message in the room ("user" for the person) and queue it for the bots it concerns.
    `only`: deliver to these members whatever the text says (a reply « to everyone »)."""
    g = get_group(group_id)
    if not g:
        raise ValueError(f"unknown group: {group_id}")
    sender = str(sender or "").strip().lower()
    if sender != "user" and sender not in g["members"]:
        raise ValueError("only a member of this group can write in it")
    body = str(text or "").strip()
    if not body:
        raise ValueError("message is empty")
    row = {"id": str(uuid.uuid4()), "from": sender, "text": body[:16000], "at": time.time(), "depth": int(depth)}
    GROUP_LOGS.mkdir(parents=True, exist_ok=True)
    with (GROUP_LOGS / f"{g['id']}.jsonl").open("a", encoding="utf-8") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
    fields = {"preview": body[:120], "updated": row["at"]}
    if sender == "user":
        fields["human_turn"] = row["at"]
    update_group(g["id"], fields)
    targets: list[str] = []
    if route:
        others = [m for m in g["members"] if m != sender]
        named = mentions(body, others)
        if only is not None:
            targets = [m for m in only if m in others]
        elif named:
            targets = named
        elif sender == "user":
            awake = [m for m in others if not (get(m) or {}).get("paused")]
            # a lead on pause: the first member awake answers instead (nobody would otherwise)
            lead = g["lead"] if g["lead"] in awake else (awake or [g["lead"]])[0]
            targets = list(others) if g["reply"] == "all" else [lead]
        # a bot's answer that names nobody ends there; one that names others hands over (GROUP_HOPS at most)
        if sender != "user" and depth >= GROUP_HOPS:
            targets = []
        for mid in targets:
            queue_inbound(mid, {"id": str(uuid.uuid4()), "kind": "group", "group": g["id"], "msg": row["id"],
                                "from": sender, "text": row["text"], "depth": int(depth) + (0 if sender == "user" else 1),
                                "at": row["at"]})
    row["targets"] = targets
    return row


@_transaction
def group_notice(group_id: str, text: str) -> dict:
    """A line from Ornis in the room (a bot could not answer): shown centred, never delivered to anyone."""
    gid = str(group_id or "").strip().lower()
    row = {"id": str(uuid.uuid4()), "from": "system", "text": str(text or "").strip()[:400], "at": time.time(), "depth": 0}
    GROUP_LOGS.mkdir(parents=True, exist_ok=True)
    with (GROUP_LOGS / f"{gid}.jsonl").open("a", encoding="utf-8") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def turn_depth(bot_id: str, group_id: str) -> int:
    """Hand-overs used in the group turn this bot is answering now (0 outside one: a routine posting starts afresh)."""
    profile = get(bot_id) or {}
    if str(profile.get("group_turn") or "") != str(group_id or "").strip().lower():
        return 0
    return int(profile.get("group_depth") or 0)


def group_transcript(group_id: str, *, upto: str = "", limit: int = 14) -> str:
    """The room's last messages for a bot's turn (it did not see the others' answers in its own thread)."""
    g = get_group(group_id) or {}
    rows = read_group(group_id, limit=200)
    if upto:
        cut = next((i for i, r in enumerate(rows) if r.get("id") == upto), -1)
        if cut >= 0:
            rows = rows[:cut + 1]
    names = {"user": "The person"}
    for mid in g.get("members") or []:
        names[mid] = f"{(get(mid) or {}).get('title') or mid} (@{mid})"
    out = []
    for r in [r for r in rows if r.get("from") != "system"][-limit:]:
        text = str(r.get("text") or "")
        if len(text) > 1500:
            text = text[:1500] + " […]"
        out.append(f"- {names.get(r.get('from'), r.get('from'))}: {text}")
    return "\n".join(out)


def group_prompt(bot_id: str, item: dict) -> str:
    """The turn a bot gets for a room message (hidden in its thread: a pill says « In the group … »)."""
    g = get_group(item.get("group") or "") or {}
    members = ", ".join(f"@{m}" + (" (lead)" if m == g.get("lead") else "") for m in g.get("members") or [])
    sender = "the person" if item.get("from") == "user" else f"@{item.get('from')}"
    desc = f"Purpose: {g['description']}\n" if g.get("description") else ""
    return (
        f"[Group message in « {g.get('title') or item.get('group')} » (group id `{g.get('id')}`)]\n"
        f"Members: {members}. You are @{bot_id}: answer as yourself, from your own role, memory and skills.\n{desc}"
        f"Shared folder of the group (every member reads and writes it; put the files you work on together there, "
        f"and name them in your answer): {group_folder(g.get('id') or item.get('group') or '')}\n"
        f"Recent messages in the room:\n{group_transcript(item.get('group') or '', upto=item.get('msg') or '')}\n\n"
        f"The last message (from {sender}) is for you. Your final answer is posted in the room as is: keep it "
        "short, like a chat message. Do the work first if it is asked (tools, files). To hand a part over, name the "
        "member with @id in your answer (they will get it); otherwise name nobody. If nothing needs an answer from "
        "you, reply exactly [SILENT].\n"
    )


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
def fail_inbound(bot_id: str, message_id: str, *, limit: int = 3) -> bool:
    """A delivery that failed (offline, quota, stopped) is tried again later, then dropped after `limit` tries.
    True when it was dropped now (the room says it once, not at each try)."""
    path = bot_dir(bot_id) / "inbox.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    items, dropped = [], False
    for r in data.get("items") or []:
        if r.get("id") == message_id:
            r = dict(r, tries=int(r.get("tries") or 0) + 1)
            if r["tries"] >= limit:
                dropped = True
                continue
        items.append(r)
    data["items"] = items
    system.private_write(path, json.dumps(data, ensure_ascii=False) + "\n")
    return dropped


@_transaction
def drop_group_inbox(group_id: str) -> None:
    """What still waits for a group's bots there (the group was stopped or deleted)."""
    for profile in list_bots():
        inbox = bot_dir(profile["id"]) / "inbox.json"
        try:
            box = json.loads(inbox.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        kept = [r for r in box.get("items") or [] if r.get("group") != group_id]
        if len(kept) != len(box.get("items") or []):
            box["items"] = kept
            system.private_write(inbox, json.dumps(box, ensure_ascii=False) + "\n")


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
    rooms = groups_of(profile["id"])
    if rooms:
        parts.append("## Your groups\n" + "\n".join(
            f"- `{g['id']}` « {g['title']} » with " + ", ".join(f"@{m}" for m in g["members"] if m != profile["id"])
            + (" — you lead it" if g["lead"] == profile["id"] else "")
            + f"; shared folder: {group_folder(g['id'])}" for g in rooms) + "\n\n")
    parts.append(
        "## Autonomy\n"
        "- Prefer an existing skill or installed connector before inventing one.\n"
        "- When a multi-step procedure will come back, write a skill under your profile "
        f"`{bot_dir(bot_id) / 'skills'}`.\n"
        "- Keep memory tidy; never store secrets.\n"
        "- **Routines** = local cron tasks (`cron_create`, or the `ornis-cron` CLI when MCP is missing): they attach "
        "to this bot and run **in this thread**. When the person asks for routines, create them now (a schedule that "
        "fits each recurring job, a prompt that says exactly what to do and where to write), then list them; never "
        "answer that you will remember. Preparing content is not publishing: a routine may draft and report, and "
        "anything public waits for the person's go.\n"
        "- Message another bot with `bot_message` (or the CLI below). Delivery is queued; "
        "do not wait for a reply in the same tool call.\n"
        "- Groups: `group_list`, `group_read`, `group_post` (a room shared with other bots and the person; "
        "@id hands work to a member).\n"
        "- `notify_user` shows a desktop notification: only for something the person must see soon "
        "(a routine result they asked to be told about, a blocking problem).\n"
        "- If bot_* tools are missing from your tool list, run the local CLI instead:\n"
        f"  `{bots_cli}` list\n"
        f"  `{bots_cli}` create '{{\"id\":\"…\",\"title\":\"…\",\"description\":\"…\"}}'\n"
        f"  `{bots_cli}` message '{{\"target\":\"…\",\"message\":\"…\"}}'\n"
        f"  `{bots_cli}` group-post '{{\"group\":\"…\",\"message\":\"…\"}}'   (also: groups, group-read, group-create)\n"
        f"  `{bots_cli}` notify '{{\"message\":\"…\"}}'   (also: exchange '{{\"peer\":\"…\"}}')\n"
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
