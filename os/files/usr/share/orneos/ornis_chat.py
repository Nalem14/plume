"""Ornis on Orneos OS: the conversations of the cloud assistant (the same ones as in the cloud), shared by the top-bar
applet (/usr/libexec/orneos-ornis) and the Ornis app (/usr/share/orneos-ornis).

In the cloud, Ornis is an agent (ornis/agent in the Orneos repository): it reads and acts in the account (agenda,
mail, notes, files…). A reply can stop on actions to confirm (sending, creating, sharing…): `pending` lists them,
`generate(…, confirm=True|False)` carries on. While it works, `check()` gives the text written so far and the tools
used. Every call is blocking: run them off the UI thread.
"""
import json
import re
import time
import uuid
import system
import ornis_local
import xml.etree.ElementTree as ET
from urllib.parse import quote, unquote

from cloud import dav, ocs, rest

DESKTOP = "/ocs/v2.php/apps/orneos/api/v1/ornis/desktop"

# Ends each question so Ornis knows it talks to Orneos OS (ornis/agent/overlay/ornis.py explains it); hidden when shown back
OS_TAG = "\n\n(Orneos OS)"
LOCAL_TAG = re.compile(r"\n*\(Plume local: [a-f0-9]{32}\)$")
CHANNELS = {}  # process-local, only conversations explicitly sent from this device
# Ends the question that starts a Work job (a job in several steps, delivered in the Drive: ornis/README.md)
WORK_TAG = "(Mode Work)"
# ... and the one that starts a deep research (a Work job on the web, delivered as a sourced report)
RESEARCH_TAG = "(Mode Recherche)"
# ... the one asked in plan mode (read-only: Ornis looks, then proposes a plan; ornis/agent/overlay/ornis.py)
PLAN_TAG = "(Mode Plan)"
# ... and « /compact »: the agent replaces the conversation by a summary and answers with it
COMPACT_TAG = "(Ornis compact)"
# « Rapide »: this question without the model's reasoning (faster, cheaper); read by the agent, hidden everywhere
FAST_TAG = "(Réflexion rapide)"
# ... and an ephemeral conversation: the agent neither reads nor writes its memories; the apps delete it once left
EPHEMERAL_TAG = "(Éphémère)"
# ... and a question asked in a project of the Work mode: the agent reads the project (instructions, folder, memory)
PROJECT_TAG = re.compile(r"\n*\(Projet: [a-f0-9]{8,16}\)")
# what Plume had open when the question was asked (a message, an event, a contact): read by the agent, never shown
# (the question shows its label as a badge, about()). « [Plume · <label>] … [/Plume] », ahead of the other tags.
ABOUT_BLOCK = re.compile(r"\n*\[Plume · ([^\]\n]{0,160})\]\n.*?\n\[/Plume\]", re.S)
PROJECTS = "/ocs/v2.php/apps/orneos/api/v1/ornis/projects"
CONTEXT = "/ocs/v2.php/apps/orneos/api/v1/ornis/context"
# What the computer still does for a question asked in plan mode: reading only (the agent offers no other tool then)
PLAN_ACTIONS = {"status", "find_files", "grep_files", "list_folder", "read_file", "processes", "command_status", "screenshot",
                "extensions", "skill_read", "mcp_tools", "find_app"}
READONLY = set()   # conversations whose question being answered was asked in plan mode (process-local)
WORK = "/ocs/v2.php/apps/orneos/api/v1/ornis/work"
PROFILE = "/ocs/v2.php/apps/orneos/api/v1/ornis"
CHAT = "/ocs/v2.php/apps/assistant/chat"
ASSIGNMENTS = "/ocs/v2.php/apps/assistant/assignments"
PINS = "/ocs/v2.php/apps/orneos/api/v1/ornis/pins"
ARCHIVED = "/ocs/v2.php/apps/orneos/api/v1/ornis/archived"
FEEDBACK = "/ocs/v2.php/apps/orneos/api/v1/ornis/feedback"
USAGE = "/ocs/v2.php/apps/orneos/api/v1/ornis/usage"
REGION = "/ocs/v2.php/apps/orneos/api/v1/ornis/region"
READ = "/ocs/v2.php/apps/orneos/api/v1/ornis"      # unread / read: the same on every device (orneos app, OrnisRead)
ASSISTANT = "/ocs/v2.php/apps/assistant/api/v1"

# What Ornis reads in a message (the cloud: integration_openai, the relay, OnlyOffice for Office files)
MAX_ATTACHMENTS = 10                   # integration_openai's limit
MAX_BYTES = 50 * 1024 * 1024           # Mistral's limit for a document
IMAGE_TYPES = ("png", "jpg", "jpeg", "webp", "gif")
DOCUMENT_TYPES = ("pdf", "docx", "doc", "odt", "rtf", "xlsx", "xls", "ods", "pptx", "ppt", "odp")
TEXT_TYPES = ("txt", "md", "markdown", "csv", "tsv", "json", "xml", "html", "htm", "yaml", "yml", "ics", "vcf", "log")


def attachment_kind(name: str) -> str:
    """image, document or text when Ornis can read the file, "" when it cannot (by its extension)."""
    ext = str(name or "").rsplit(".", 1)[-1].lower() if "." in str(name or "") else ""
    return "image" if ext in IMAGE_TYPES else "document" if ext in DOCUMENT_TYPES else "text" if ext in TEXT_TYPES else ""


class Error(Exception):
    """A call the cloud refused or could not answer; `code` is the HTTP status (0: offline)."""

    def __init__(self, code: int, message: str = ""):
        super().__init__(message or f"HTTP {code}")
        self.code = code
        self.message = message


def _data(body):
    # The chat API answers bare JSON; the others an OCS envelope
    if isinstance(body, dict) and isinstance(body.get("ocs"), dict):
        return body["ocs"].get("data")
    return body


def _q(value) -> str:
    return quote(str(value), safe="")


def _ok(status: int) -> bool:
    return status in (100, 200, 201)


def clean(text: str) -> str:
    out = ABOUT_BLOCK.sub("", PROJECT_TAG.sub("", LOCAL_TAG.sub("", str(text or "").strip()))).strip().removesuffix(OS_TAG.strip()).strip()
    for tag in (WORK_TAG, RESEARCH_TAG, PLAN_TAG, COMPACT_TAG, FAST_TAG, EPHEMERAL_TAG):
        out = out.removesuffix(tag).strip()
    return out


def about(text: str) -> str:
    """The label of what Plume had open when the question was asked ("" : nothing)."""
    found = ABOUT_BLOCK.search(str(text or ""))
    return found.group(1).strip() if found else ""


def about_block(label: str, body: str, limit: int = 6000) -> str:
    """What the agent reads of the open message, event or contact, after the question."""
    label = " ".join(str(label or "").replace("]", ")").split())[:160]
    body = str(body or "").replace("[/Plume]", "[/ Plume]").strip()
    if len(body) > limit:
        body = body[:limit].rstrip() + " […]"
    return f"\n\n[Plume · {label}]\n{body}\n[/Plume]"


def ask_mode(text: str) -> str:
    """"plan" for a question asked in plan mode, "compact" for « /compact », "" otherwise (their tags are hidden by clean())."""
    tail = LOCAL_TAG.sub("", str(text or "").strip())[-60:]
    return "compact" if COMPACT_TAG in tail else "plan" if PLAN_TAG in tail else ""


# Formulas: the model is asked for plain symbols (× ÷ ² √), but LaTeX still slips through ($…$, \(…\), $$…$$):
# shown as text, never as backslashes. Code (fenced or `inline`) is left as it is.
_MATH = re.compile(r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<![\w$\\])\$(?=\S)([^$\n]+?)(?<=\S)\$(?![\w$])", re.S)
_SYMBOLS = {
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓", "approx": "≈", "simeq": "≃", "sim": "∼", "neq": "≠",
    "ne": "≠", "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "ll": "≪", "gg": "≫", "infty": "∞", "to": "→",
    "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔", "iff": "⇔",
    "implies": "⇒", "sum": "Σ", "prod": "Π", "int": "∫", "partial": "∂", "nabla": "∇", "in": "∈", "notin": "∉",
    "subset": "⊂", "subseteq": "⊆", "cup": "∪", "cap": "∩", "emptyset": "∅", "forall": "∀", "exists": "∃",
    "neg": "¬", "land": "∧", "lor": "∨", "circ": "°", "degree": "°", "ldots": "…", "cdots": "⋯", "dots": "…",
    "%": "%", "€": "€", "euro": "€", "$": "$", "&": "&", "#": "#", "_": "_", "{": "{", "}": "}", ",": " ",
    ";": " ", ":": " ", "!": "", "quad": " ", "qquad": "  ", " ": " ", "left": "", "right": "", "displaystyle": "",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ", "eta": "η",
    "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
_SUP = str.maketrans("0123456789+-=()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ")
_SUB = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")


def _group(s: str, i: int) -> tuple[str, int]:
    """The {…} (or single character) starting at i, and where it ends."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] != "{":
        return s[i], i + 1
    depth, j = 0, i
    while j < len(s):
        depth += {"{": 1, "}": -1}.get(s[j], 0)
        if depth == 0:
            return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def _wrap(part: str) -> str:
    return part if re.fullmatch(r"[\w., ·√²³⁰-⁹]+", part) else f"({part})"


def latex_text(tex: str) -> str:
    """A LaTeX formula as readable text: \\frac{a}{b} → a/b, x^{2} → x², \\sqrt{x} → √x, \\times → ×…"""
    out, i = [], 0
    while i < len(tex):
        ch = tex[i]
        if ch == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", tex[i:])
            name, i = m.group(1), i + len(m.group(0))
            if name in ("frac", "dfrac", "tfrac"):
                num, i = _group(tex, i)
                den, i = _group(tex, i)
                out.append(f"{_wrap(latex_text(num))}/{_wrap(latex_text(den))}")
            elif name == "sqrt":
                arg, i = _group(tex, i)
                out.append("√" + _wrap(latex_text(arg)))
            elif name in ("text", "mathrm", "mathbf", "mathit", "textbf", "operatorname", "mbox", "boldsymbol", "mathsf"):
                arg, i = _group(tex, i)
                out.append(latex_text(arg))
            else:
                out.append(_SYMBOLS.get(name, name))
        elif ch in "^_":
            arg, i = _group(tex, i + 1)
            arg = latex_text(arg)
            table = _SUP if ch == "^" else _SUB
            out.append(arg.translate(table) if all(c in "0123456789+-=()" + ("n" if ch == "^" else "") for c in arg)
                       else ("^" if ch == "^" else "_") + _wrap(arg))
        elif ch in "{}":
            i += 1
        else:
            out.append(ch)
            i += 1
    return re.sub(r" {2,}", " ", "".join(out)).strip()


def plain_math(text: str) -> str:
    """Every formula of a reply as text (inline stays inline, display ones on their own line), code untouched."""
    parts = re.split(r"(```.*?(?:```|$)|`[^`\n]*`)", text or "", flags=re.S)
    for k in range(0, len(parts), 2):
        parts[k] = _MATH.sub(lambda m: (latex_text(m.group(1)) if m.group(1) is not None
                                        else latex_text(m.group(2)) if m.group(2) is not None
                                        else latex_text(m.group(3) or m.group(4) or "")), parts[k])
    return "".join(parts)


def is_work(text: str) -> bool:
    """The question that started a Work job or a deep research (its tag is hidden by clean())."""
    return job_kind(text) != ""


def job_kind(text: str) -> str:
    """"research" for the question that started a deep research, "work" for a Work job, "" otherwise"""
    tail = LOCAL_TAG.sub("", str(text or "").strip())[-60:]
    return "research" if RESEARCH_TAG in tail else "work" if WORK_TAG in tail else ""


def title(text: str) -> str:
    """A conversation's title on one line: the cloud names it after the first question, tag and line breaks included."""
    return " ".join(clean(text).split())


def sources(raw) -> list[str]:
    """The tools a reply used (tool names), from the message's `sources` (a JSON list, sometimes of lists)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            return []
    out = []
    for item in raw if isinstance(raw, list) else []:
        name = item[0] if isinstance(item, list) and item else item
        if isinstance(name, str) and name and name not in out:
            out.append(name)
    return out


def steps(raw) -> list[dict]:
    """The tool calls of a turn, in order: [{tool, detail}] (the agent's "steps" output, JSON; [] for an older agent)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            return []
    return [{"tool": str(s.get("tool") or ""), "detail": str(s.get("detail") or "")[:140]}
            for s in (raw if isinstance(raw, list) else []) if isinstance(s, dict) and s.get("tool")][:40]


def actions(raw) -> list[dict]:
    """Actions waiting for the user's yes or no: [{name, title, icon, args}], `title` translated by the cloud when it knows it."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            return []
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        name = str(item.get("name") or "")
        out.append({"id": str(item.get("id") or len(out)), "name": name, "title": name, "icon": str(item.get("icon") or ""),
                    "args": {str(k): v for k, v in args.items()}})
    return out


def attachments(raw) -> list[dict]:
    """The files of a message: [{file_id, type}] (type: Image, File… as the clients sent it)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except json.JSONDecodeError:
            return []
    return [{"file_id": str(a.get("file_id")), "type": str(a.get("type") or "")}
            for a in (raw if isinstance(raw, list) else []) if isinstance(a, dict) and a.get("file_id") is not None]


def message(row: dict) -> dict | None:
    role = str(row.get("role") or "assistant").lower()
    if role == "system":  # the instructions the assistant stores at the head of each session
        return None
    content = clean(row.get("content"))
    kind = job_kind(row.get("content")) if role in ("human", "user") else ""
    mode = ask_mode(row.get("content")) if role in ("human", "user") else ""
    files = attachments(row.get("attachments"))
    if not content and role != "assistant" and not files:
        return None
    return {
        "id": str(row.get("id") or ""),
        "role": "human" if role in ("human", "user") else "assistant",
        "content": content,
        "timestamp": int(row.get("timestamp") or 0),
        "sources": sources(row.get("sources")),
        # what the model thought before answering (Ornis reasons: ornis/relay RELAY_REASONING), shown folded
        "reasoning": str(row.get("reasoning") or "").strip() if role not in ("human", "user") else "",
        "attachments": files,
        "work": bool(kind),
        "research": kind == "research",
        "plan": mode == "plan",
        "compact": mode == "compact",
        "about": about(row.get("content")) if role in ("human", "user") else "",
        "task": str(row.get("ocp_task_id") or row.get("ocpTaskId") or ""),     # its steps are read from the task
    }


class Chat:
    def __init__(self, server: str, user: str, password: str):
        self.server, self.user, self.password = server, user, password

    def _ocs(self, path, method="GET", body=None):
        return ocs(self.server, self.user, self.password, path, method=method, body=body)

    # ---- conversations ---------------------------------------------------------------------------------
    def sessions(self) -> list[dict]:
        status, body = self._ocs(f"{CHAT}/sessions?format=json")
        if not _ok(status):
            raise Error(status)
        rows = _data(body)
        rows = rows.get("sessions") if isinstance(rows, dict) else rows
        out = []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and row.get("id") is not None:
                out.append({"id": str(row["id"]), "title": title(row.get("title")),
                            "timestamp": int(row.get("timestamp") or 0), "remembered": bool(row.get("is_remembered")),
                            "scheduled": row.get("assignment_id") is not None,
                            "pending": bool(row.get("agency_pending_actions"))})
        out.sort(key=lambda s: -s["timestamp"])
        return out

    def task_sessions(self) -> list[dict]:
        """The conversations of the scheduled tasks, which the cloud lists apart (one per task: each run adds to it)."""
        status, body = self._ocs(f"{CHAT}/sessions?isAssignment=true&format=json")
        if not _ok(status):
            raise Error(status)
        rows = _data(body)
        rows = rows.get("sessions") if isinstance(rows, dict) else rows
        return [{"id": str(r["id"]), "assignment": str(r.get("assignment_id")), "title": title(r.get("title")),
                 "timestamp": int(r.get("timestamp") or 0)}
                for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict) and r.get("id") is not None]

    def messages(self, session_id: str, limit: int = 200) -> list[dict]:
        status, body = self._ocs(f"{CHAT}/messages?sessionId={_q(session_id)}&limit={int(limit)}&format=json")
        if not _ok(status):
            raise Error(status)
        rows = _data(body)
        rows = rows.get("messages") if isinstance(rows, dict) else rows
        out = [m for m in (message(r) for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)) if m]
        out.sort(key=lambda m: (m["timestamp"], m["id"].zfill(12)))
        return out

    def new_session(self, title: str = "") -> str:
        status, body = self._ocs(f"{CHAT}/new_session?format=json", "PUT", {"timestamp": int(time.time()), "title": title})
        data = _data(body)
        session = data.get("session") if isinstance(data, dict) and isinstance(data.get("session"), dict) else data
        if not _ok(status) or not isinstance(session, dict) or session.get("id") is None:
            raise Error(status)
        return str(session["id"])

    def fork(self, session_id: str, upto: str, title: str) -> str:
        """« Bifurquer » : a new conversation with this one's messages up to `upto` (included), the original untouched.
        The agent reads them as the conversation so far (the assistant passes a session's messages as its history)."""
        rows = self.messages(session_id)
        at = next((i for i, m in enumerate(rows) if m["id"] == str(upto)), None)
        if at is None:
            raise Error(404)
        new = self.new_session(title)
        try:
            for m in rows[:at + 1]:
                if m["role"] not in ("human", "assistant") or not (m.get("content") or "").strip():
                    continue
                status, _ = self._ocs(f"{CHAT}/new_message?format=json", "PUT",
                                      {"sessionId": int(new), "role": m["role"], "content": m["content"],
                                       "timestamp": int(m.get("timestamp") or time.time()), "firstHumanMessage": False})
                if not _ok(status):
                    raise Error(status)
        except Error:
            try:
                self.delete(new)
            except Error:
                pass
            raise
        return new

    def rename(self, session_id: str, title: str) -> None:
        status, _ = self._ocs(f"{CHAT}/update_session?format=json", "PATCH", {"sessionId": int(session_id), "title": title})
        if not _ok(status):
            raise Error(status)

    def remember(self, session_id: str, on: bool) -> None:
        """Whether Ornis keeps what it learned in this conversation for the next ones (the assistant's memories)."""
        status, _ = self._ocs(f"{CHAT}/sessions/{_q(session_id)}?format=json", "PUT", {"is_remembered": bool(on)})
        if not _ok(status):
            raise Error(status)

    def delete(self, session_id: str) -> None:
        status, _ = self._ocs(f"{CHAT}/delete_session?sessionId={_q(session_id)}&format=json", "DELETE")
        if not _ok(status):
            raise Error(status)

    def delete_message(self, session_id: str, message_id: str) -> None:
        status, _ = self._ocs(f"{CHAT}/delete_message?sessionId={_q(session_id)}&messageId={_q(message_id)}&format=json", "DELETE")
        if not _ok(status) and status != 404:
            raise Error(status)

    def check_session(self, session_id: str) -> dict:
        """{task: id of the reply being written or None, title, pending: [actions], remembered}"""
        status, body = self._ocs(f"{CHAT}/check_session?sessionId={_q(session_id)}&format=json")
        if not _ok(status):
            raise Error(status)
        data = _data(body) if isinstance(_data(body), dict) else {}
        return {"task": data.get("messageTaskId"), "title": title(data.get("sessionTitle")),
                "pending": actions(data.get("sessionAgencyPendingActions")), "remembered": bool(data.get("is_remembered"))}

    # ---- asking ------------------------------------------------------------------------------------------
    def send(self, session_id: str, text: str, first: bool = False, files: list[dict] | None = None, work: bool | str = False,
             mode: str = "", project: str = "", fast: bool = False, ephemeral: bool = False) -> str:
        """Posts the user's message and starts Ornis's reply; returns the reply's task id.
        files: [{file_id, type}] already in the cloud (upload() or file_id()); work: it starts a Work job ("research":
        a deep research); mode: "plan" (read-only, the computer refuses what writes too) or "compact" (« /compact »);
        project: the id of the conversation's project (Work mode), whose instructions the agent then follows."""
        if mode == "plan":
            READONLY.add(str(session_id))
        else:
            READONLY.discard(str(session_id))
        channel = uuid.uuid4().hex if ornis_local.enabled() else ""
        if channel:
            CHANNELS[str(session_id)] = channel
            try:
                ctx_q = "&context=" + _q(json.dumps(ornis_local.context_snapshot(), ensure_ascii=False))
            except Exception:  # noqa: BLE001
                ctx_q = ""
            self._ocs(f"{DESKTOP}/next?format=json&channel={channel}{ctx_q}")
        else:
            CHANNELS.pop(str(session_id), None)
        tag = RESEARCH_TAG if work == "research" else WORK_TAG if work else PLAN_TAG if mode == "plan" else COMPACT_TAG if mode == "compact" else ""
        body = {"sessionId": int(session_id), "role": "human", "content": text.strip() + (f"\n\n(Projet: {project})" if re.fullmatch(r"[a-f0-9]{8,16}", project or "") else "") + ("\n\n" + EPHEMERAL_TAG if ephemeral else "") + ("\n\n" + FAST_TAG if fast and mode != "compact" else "") + ("\n\n" + tag if tag else "") + (f"\n\n(Plume local: {channel})" if channel else ""),
                "timestamp": int(time.time()), "firstHumanMessage": bool(first)}
        if files:
            body["attachments"] = [{"type": str(f.get("type") or "File"), "file_id": int(f["file_id"])} for f in files]
        status, body = self._ocs(f"{CHAT}/new_message?format=json", "PUT", body)
        if not _ok(status):
            raise Error(status, str((_data(body) or {}).get("error") or "") if isinstance(_data(body), dict) else "")
        data = _data(body)
        task = data.get("taskId") if isinstance(data, dict) else None
        if not task and first:
            task = self.check_session(session_id).get("task")
        return str(task) if task else self.generate(session_id)

    def generate(self, session_id: str, confirm: bool | None = None) -> str:
        """(Re)starts Ornis's reply; with confirm, carries on with (True) or without (False) the pending actions."""
        extra = "" if confirm is None else f"&agencyConfirm={1 if confirm else 0}"
        status, body = self._ocs(f"{CHAT}/generate?sessionId={_q(session_id)}{extra}&format=json")
        data = _data(body)
        if not _ok(status) or not isinstance(data, dict) or not data.get("taskId"):
            raise Error(status, str(data.get("error") or "") if isinstance(data, dict) else "")
        return str(data["taskId"])

    def put_edits(self, session_id: str, calls: list[dict]) -> None:
        """The fields the user changed in the actions to confirm ([{index, args: {key: text}}]): the agent applies them."""
        status, _ = self._ocs(f"/ocs/v2.php/apps/orneos/api/v1/ornis/edits/{_q(session_id)}?format=json", "PUT", {"calls": calls})
        if not _ok(status):
            raise Error(status)

    def regenerate(self, session_id: str, message_id: str) -> str:
        status, body = self._ocs(f"{CHAT}/regenerate?sessionId={_q(session_id)}&messageId={_q(message_id)}&format=json")
        data = _data(body)
        if not _ok(status) or not isinstance(data, dict) or not data.get("taskId"):
            raise Error(status)
        return str(data["taskId"])

    def check(self, session_id: str, task_id: str) -> dict:
        """{state: running|done|failed, text: written so far or the reply, reasoning: thought so far, sources, pending,
        message, error}"""
        status, body = self._ocs(f"{CHAT}/check_generation?taskId={_q(task_id)}&sessionId={_q(session_id)}&format=json")
        data = _data(body) if isinstance(_data(body), dict) else {}
        if status in (202, 417):
            out = data.get("task_output") if isinstance(data.get("task_output"), dict) else {}
            return {"state": "running", "text": clean(out.get("output")), "sources": sources(out.get("sources")),
                    "steps": steps(out.get("steps")),
                    "reasoning": str(out.get("reasoning") or "").strip(), "slow": bool(data.get("slow_pickup"))}
        if _ok(status) and data.get("content") is not None:
            msg = message(data) or {"id": str(data.get("id") or ""), "role": "assistant", "content": "", "sources": []}
            return {"state": "done", "text": msg["content"], "sources": msg["sources"], "message": msg,
                    "reasoning": msg.get("reasoning", ""),
                    "pending": actions(data.get("sessionAgencyPendingActions"))}
        if status == 0:
            return {"state": "running", "text": "", "sources": [], "offline": True}
        return {"state": "failed", "error": str(data.get("userFacingErrorMessage") or data.get("error") or f"HTTP {status}")}

    def task_steps(self, task_id: str) -> list[dict]:
        """The steps of an answer, from its task (kept by the cloud for months): [] when gone or from an older agent."""
        status, body = self._ocs(f"/ocs/v2.php/taskprocessing/task/{_q(task_id)}?format=json")
        data = _data(body)
        task = data.get("task") if _ok(status) and isinstance(data, dict) else None
        output = task.get("output") if isinstance(task, dict) else None
        return steps(output.get("steps")) if isinstance(output, dict) else []

    def context(self, session_id: str) -> dict:
        """What the next question of a conversation will carry, measured by the agent after the last turn:
        {tokens, parts: {instructions, user_rules, memories, skills, tools, conversation, tool_results, files}, limit,
        compacted, compacted_at} ({tokens: 0} before the first answer)."""
        status, body = self._ocs(f"{CONTEXT}/{_q(session_id)}?format=json")
        if not _ok(status):
            raise Error(status)
        data = _data(body)
        return data if isinstance(data, dict) else {}

    def cancel(self, task_id: str) -> None:
        """Stops a reply being written (the task of the cloud's AI)."""
        self._ocs(f"/ocs/v2.php/taskprocessing/task/{_q(task_id)}/cancel?format=json", "POST", {})

    def computer(self, on_state=None, session_id="", asker=None) -> int:
        """Runs what Ornis asked of this computer while it writes (ornis_desktop), and answers; how many ran.
        The computer decides what needs the user's yes (ornis_consent: the mode, the rules, a window to ask).
        on_state({action, summary, phase: asking|running|done, command}) follows each request, for the UI."""
        channel = CHANNELS.get(str(session_id))
        if not channel or not ornis_local.enabled():
            return 0
        status, body = self._ocs(f"{DESKTOP}/next?format=json&channel={channel}")
        data = _data(body)
        jobs = data.get("requests") if _ok(status) and isinstance(data, dict) else None
        for job in jobs or []:
            import ornis_desktop  # noqa: PLC0415 - only on Orneos OS, only when asked

            def state(phase, req, job=job):
                if on_state:
                    on_state({"id": str(job.get("id")), "action": req.get("action"), "summary": req.get("summary"),
                              "command": req.get("command"), "level": req.get("level"), "phase": phase,
                              "job": str(req.get("job") or ""), "output": str(req.get("output") or ""),
                              "seconds": int(req.get("seconds") or 0)})
            if str(session_id) in READONLY and job.get("action") not in PLAN_ACTIONS:
                result = {"error": "Plan mode: read-only. Nothing was changed; propose this step in the plan instead."}
            else:
                result = ornis_desktop.run(job.get("action"), job.get("args") or {}, on_state=state, asker=asker)
            if job.get("action") == "screenshot" and isinstance(result, dict) and result.get("path"):
                try:
                    from pathlib import Path as _Path  # noqa: PLC0415
                    p = _Path(str(result["path"]))
                    if p.is_file() and p.stat().st_size <= 15 * 1024 * 1024:
                        result["file_id"] = self.upload(p.name, p.read_bytes(), "image/png")
                except Exception:  # noqa: BLE001
                    pass
            self._ocs(f"{DESKTOP}/results?format=json", "POST", {"id": str(job.get("id")), "result": result, "channel": channel})
            if on_state:
                on_state({"id": str(job.get("id")), "action": job.get("action"), "phase": "done"})
        return len(jobs or [])

    def wait(self, session_id: str, task_id: str, timeout: float = 180, on_progress=None, asker=None) -> dict:
        """Polls check() until the reply is there (or failed, or the time is up), running on this computer what
        Ornis asks of it meanwhile. While it does, the progress carries `computer`: what it is asking or running."""
        deadline = time.time() + timeout
        delay = 0.5
        last = {"state": "running", "text": "", "sources": []}

        def on_state(info):
            nonlocal deadline
            deadline = max(deadline, time.time() + 120)      # the user's answer on the computer is not Ornis's time
            if on_progress:
                on_progress(dict(last, computer=None if info.get("phase") == "done" else info))
        while time.time() < deadline:
            if self.computer(on_state, session_id, asker):
                delay = 0.6
            result = self.check(session_id, task_id)
            if result["state"] != "running":
                return result
            last = result
            if on_progress:
                on_progress(result)
            time.sleep(delay)
            # every half second while the agent works: the text it writes shows as it comes (the cloud keeps
            # it in the task; a check is one light read)
            delay = 0.5
        return {"state": "failed", "error": "timeout"}

    # ---- attachments -------------------------------------------------------------------------------------------
    def upload(self, name: str, data: bytes, mime: str = "application/octet-stream") -> str:
        """A file from this computer, put in the Drive (Assistant folder) for Ornis to read: its file id."""
        boundary = uuid.uuid4().hex
        safe = str(name or "fichier").replace('"', "").replace("\r", "").replace("\n", "")
        payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="data"; filename="{safe}"\r\n'
                   f"Content-Type: {mime}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        from cloud import _call, _parse  # noqa: PLC0415 - a large file needs more than ocs()'s 20 s
        status, raw = _call(f"{self.server}{ASSISTANT}/input-file?filename={_q(safe)}&format=json", self.user, self.password,
                            "POST", payload, {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=180)
        data = _data(_parse(raw))
        if not _ok(status) or not isinstance(data, dict) or not data.get("fileId"):
            raise Error(status)
        return str(data["fileId"])

    def transcribe(self, data: bytes, mime: str) -> str:
        """Dictation: a recording as text, by Voxtral through the cloud (counted in the day's Ornis allowance, nothing
        kept). Error(429) when the allowance is used up."""
        boundary = uuid.uuid4().hex
        payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="dictation"\r\n'
                   f"Content-Type: {mime}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
        from cloud import _call, _parse  # noqa: PLC0415 - up to 10 minutes of audio: more than ocs()'s 20 s
        status, raw = _call(f"{self.server}{PROFILE}/transcribe?format=json", self.user, self.password,
                            "POST", payload, {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=120)
        data = _data(_parse(raw))
        if not _ok(status) or not isinstance(data, dict):
            raise Error(status)
        return str(data.get("text") or "").strip()

    def _propfind(self, path: str, depth: str) -> list[dict]:
        url = f"/remote.php/dav/files/{_q(self.user)}/" + "/".join(_q(p) for p in path.strip("/").split("/") if p)
        if depth == "1" and not url.endswith("/"):
            url += "/"
        body = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
                "<d:prop><oc:fileid/><d:resourcetype/><d:getcontenttype/><d:getcontentlength/><d:getlastmodified/></d:prop></d:propfind>")
        status, raw = dav(self.server, self.user, self.password, url, "PROPFIND", body, depth=depth)
        if status != 207:
            raise Error(status)
        ns = {"d": "DAV:", "oc": "http://owncloud.org/ns"}
        root = f"/remote.php/dav/files/{self.user}/"
        out = []
        for resp in ET.fromstring(raw).findall("d:response", ns):
            href = unquote(resp.findtext("d:href", "", ns))
            rel = "/" + href.split(root, 1)[-1].strip("/") if root in href else href
            prop = resp.find("d:propstat/d:prop", ns)
            if prop is None:
                continue
            folder = prop.find("d:resourcetype/d:collection", ns) is not None
            out.append({"path": rel, "name": rel.rsplit("/", 1)[-1] or "/", "folder": folder,
                        "file_id": prop.findtext("oc:fileid", "", ns), "mime": prop.findtext("d:getcontenttype", "", ns),
                        "size": int(prop.findtext("d:getcontentlength", "0", ns) or 0)})
        return out

    def file_id(self, path: str) -> dict:
        """A file already in the Drive (a path like /Documents/x.pdf): {file_id, name, size}, nothing to upload."""
        rows = self._propfind(path, "0")
        if not rows or rows[0]["folder"]:
            raise Error(404)
        return rows[0]

    def folder(self, path: str = "/") -> list[dict]:
        """A Drive folder for the file picker: folders first, then files, by name; hidden ones left out."""
        rows = [r for r in self._propfind(path, "1")[1:] if not r["name"].startswith(".")]
        rows.sort(key=lambda r: (not r["folder"], r["name"].lower()))
        return rows

    def _dav_url(self, path: str) -> str:
        return f"/remote.php/dav/files/{_q(self.user)}/" + "/".join(_q(p) for p in path.strip("/").split("/") if p)

    def make_folder(self, path: str) -> None:
        """A Drive folder (a project's), with its parents; nothing when it is already there."""
        built = ""
        for part in [p for p in path.strip("/").split("/") if p]:
            built += "/" + part
            status, _ = dav(self.server, self.user, self.password, self._dav_url(built), "MKCOL")
            if status not in (201, 405):           # 405: already there
                raise Error(status)

    def put_file(self, path: str, data: bytes) -> None:
        """A file of this computer written in the Drive (a project's files), replacing one of the same name."""
        from cloud import _call  # noqa: PLC0415 - a large file needs more than ocs()'s 20 s
        status, _ = _call(f"{self.server}{self._dav_url(path)}", self.user, self.password, "PUT", data,
                          {"Content-Type": "application/octet-stream"}, timeout=300)
        if status not in (200, 201, 204):
            raise Error(status)

    def public_link(self, path: str) -> str:
        """A read-only public link to a file of the Drive (files_sharing): its address."""
        status, body = self._ocs("/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json", "POST",
                                 {"path": "/" + path.strip("/"), "shareType": 3, "permissions": 1})
        data = _data(body)
        if not _ok(status) or not isinstance(data, dict) or not data.get("url"):
            raise Error(status)
        return str(data["url"])

    def file_name(self, file_id: str) -> str:
        status, body = self._ocs(f"{ASSISTANT}/file/{_q(file_id)}/info?format=json")
        data = _data(body)
        return str(data.get("name") or "") if _ok(status) and isinstance(data, dict) else ""

    def preview(self, file_id: str, size: int = 256) -> bytes:
        """A thumbnail of an image in the Drive (the cloud's preview), b"" when there is none."""
        from cloud import _call  # noqa: PLC0415
        status, raw = _call(f"{self.server}/index.php/core/preview?fileId={_q(file_id)}&x={size}&y={size}&a=1&forceIcon=0",
                            self.user, self.password, headers={"Accept": "image/*"})
        return raw if status == 200 else b""

    # ---- scheduled tasks (Ornis runs them on its own, each in a new conversation) ------------------------------
    def assignments(self) -> list[dict]:
        status, body = self._ocs(f"{ASSIGNMENTS}?format=json")
        if not _ok(status):
            raise Error(status)
        data = _data(body)
        rows = data.get("assignments") if isinstance(data, dict) else []
        return [{"id": str(r.get("id")), "prompt": str(r.get("prompt") or ""), "recurrence": str(r.get("recurrence") or ""),
                 "starts_at": int(r.get("starts_at") or 0), "last_run_at": int(r.get("last_run_at") or 0),
                 "timezone": str(r.get("timezone") or "")} for r in (rows or []) if isinstance(r, dict)]

    def delete_assignment(self, assignment_id: str) -> None:
        status, _ = self._ocs(f"{ASSIGNMENTS}/{_q(assignment_id)}?format=json", "DELETE")
        if not _ok(status):
            raise Error(status)

    # ---- pins --------------------------------------------------------------------------------------------------
    def pins(self) -> list[str]:
        """Pinned conversations, newest pin first: kept by the cloud (orneos app), the same as in the browser."""
        status, body = self._ocs(f"{PINS}?format=json")
        return self._pin_list(status, body)

    def set_pins(self, ids) -> list[str]:
        status, body = self._ocs(f"{PINS}?format=json", "PUT", {"pins": [int(i) for i in ids if str(i).isdigit()]})
        return self._pin_list(status, body)

    def archived(self) -> list[str]:
        """Archived conversations (out of the list, kept), the same in the browser and on every device."""
        status, body = self._ocs(f"{ARCHIVED}?format=json")
        return self._id_list(status, body, "archived")

    def set_archived(self, ids) -> list[str]:
        status, body = self._ocs(f"{ARCHIVED}?format=json", "PUT", {"archived": [int(i) for i in ids if str(i).isdigit()]})
        return self._id_list(status, body, "archived")

    def votes(self) -> dict:
        """The user's 👍 / 👎 on Ornis's answers: {message id: 1 | -1}."""
        status, body = self._ocs(f"{FEEDBACK}?format=json")
        if not _ok(status):
            raise Error(status)
        data = _data(body)
        votes = data.get("votes") if isinstance(data, dict) else None
        return {str(k): int(v) for k, v in (votes or {}).items() if str(k).isdigit() and v in (1, -1)} if isinstance(votes, dict) else {}

    def vote(self, message_id=0, vote: int = 0, reason: str = "", comment: str = "", excerpt: str = "", asked: bool = False,
             product: str = "chat", ref: str = "", meta: dict | None = None) -> None:
        """👍 (1), 👎 (-1) or neither (0) on an answer: one row per answer in the cloud, no account named. The Chat names
        its answer by message id, Code and Bots by product and ref. A 👎 may say why (a reason, the user's words) and
        carry the exchange, only when the user ticked it (excerpt). asked: from the « Was it useful? » card (vote 0:
        closed without one). meta: facts of the turn, no content."""
        body = {"vote": int(vote), "product": product}
        if str(message_id).isdigit() and int(message_id) > 0:
            body["messageId"] = int(message_id)
        else:
            body["ref"] = str(ref)[:200]
        if asked:
            body["asked"] = True
        if meta:
            body["meta"] = meta
        if reason or comment or excerpt:
            body.update(reason=str(reason)[:20], comment=str(comment)[:500], excerpt=str(excerpt)[:3000])
        status, _ = self._ocs(f"{FEEDBACK}?format=json", "PUT", body)
        if not _ok(status):
            raise Error(status)

    @staticmethod
    def _id_list(status, body, key) -> list[str]:
        if not _ok(status):
            raise Error(status)
        data = _data(body)
        ids = data.get(key) if isinstance(data, dict) else None
        return [str(i) for i in ids if str(i).isdigit()] if isinstance(ids, list) else []

    def projects(self) -> dict:
        """The Work mode's projects, the same on every device: {projects: [...], sessions: {session id: project id}}."""
        status, body = self._ocs(f"{PROJECTS}?format=json")
        return self._project_data(status, body)

    def set_projects(self, projects: list, sessions: dict) -> dict:
        status, body = self._ocs(f"{PROJECTS}?format=json", "PUT", {"projects": projects, "sessions": sessions})
        return self._project_data(status, body)

    @staticmethod
    def _project_data(status, body) -> dict:
        if not _ok(status):
            raise Error(status)
        data = _data(body)
        data = data if isinstance(data, dict) else {}
        sessions = data.get("sessions") if isinstance(data.get("sessions"), dict) else {}
        return {"projects": [p for p in data.get("projects") or [] if isinstance(p, dict)],
                "sessions": {str(k): str(v) for k, v in sessions.items()}}

    @staticmethod
    def _pin_list(status, body) -> list[str]:
        if not _ok(status):
            raise Error(status)
        data = _data(body)
        pins = data.get("pins") if isinstance(data, dict) else None
        return [str(p) for p in pins if str(p).isdigit()] if isinstance(pins, list) else []

    # ---- the Work mode (orneos app, OrnisWork) ---------------------------------------------------------------
    def work_estimate(self) -> dict:
        """{allowed (in the plan), limit, used, remaining, low, high}: what a job takes of today's allowance."""
        status, body = self._ocs(f"{WORK}/estimate?format=json")
        data = _data(body)
        if not _ok(status) or not isinstance(data, dict):
            raise Error(status)
        return data

    def work_jobs(self) -> list[dict]:
        """The jobs, newest first: {session, title, folder, status, plan, done, current, reason, started, updated}."""
        status, body = self._ocs(f"{WORK}?format=json")
        data = _data(body)
        if not _ok(status) or not isinstance(data, dict):
            raise Error(status)
        return [dict(j, session=str(j.get("session"))) for j in data.get("jobs") or [] if isinstance(j, dict)]

    def work_job(self, session_id: str) -> dict | None:
        status, body = self._ocs(f"{WORK}/{_q(session_id)}?format=json")
        data = _data(body)
        if status == 404:
            return None
        if not _ok(status) or not isinstance(data, dict):
            raise Error(status)
        return data

    # ---- « Personnaliser Ornis »: the user's instructions and what Ornis remembers (the same everywhere) ----------
    def profile(self) -> dict:
        """{name, about, style, enabled, limits, memories: [{id, title, text, updated}], remembered: [{id, title}]}"""
        status, body = self._ocs(f"{PROFILE}/profile?format=json")
        data = _data(body)
        if not _ok(status) or not isinstance(data, dict):
            raise Error(status)
        return data

    def save_profile(self, change: dict) -> dict:
        status, body = self._ocs(f"{PROFILE}/profile?format=json", "PUT", change)
        data = _data(body)
        if not _ok(status) or not isinstance(data, dict):
            raise Error(status)
        return data

    def forget_memory(self, file_id) -> None:
        status, _ = self._ocs(f"{PROFILE}/memories/{_q(file_id)}?format=json", "DELETE")
        if not _ok(status) and status != 404:
            raise Error(status)

    def forget_remembered(self, session_id) -> None:
        status, _ = self._ocs(f"{PROFILE}/remembered/{_q(session_id)}?format=json", "DELETE")
        if not _ok(status):
            raise Error(status)

    def forget_work(self, session_id: str) -> None:
        self._ocs(f"{WORK}/{_q(session_id)}?format=json", "DELETE")

    # ---- read / unread (the cloud keeps it: what is read here is read in the browser and in Plume) ---------------
    def unread(self) -> dict[str, int]:
        """{session id: answers not read yet}, only the conversations that have some (scheduled tasks included)."""
        status, body = self._ocs(f"{READ}/unread?format=json")
        return self._unread(status, body)

    def mark_read(self, session_id: str, last_message_id: int = 0) -> dict[str, int]:
        """The conversation shown to the user is read (its notifications leave the cloud's bell); what remains unread."""
        status, body = self._ocs(f"{READ}/read?format=json", "PUT", {"sessionId": int(session_id), "lastMessageId": last_message_id})
        return self._unread(status, body)

    @staticmethod
    def _unread(status, body) -> dict[str, int]:
        if not _ok(status):
            raise Error(status)
        data = _data(body)
        rows = data.get("unread") if isinstance(data, dict) else None
        return {str(k): int(v) for k, v in rows.items()} if isinstance(rows, dict) else {}

    # ---- allowance ---------------------------------------------------------------------------------------------
    def usage(self) -> dict | None:
        """The usage panel (orneos app, /ornis/usage): {used, limit, percent, hours: 24 counts oldest first, ai: the
        account's AI offer and what it can take, or None when orneos.eu did not answer}."""
        status, body = self._ocs(f"{USAGE}?format=json")
        data = _data(body) if _ok(status) else None
        if not isinstance(data, dict) or not isinstance(data.get("hours"), list):
            return None
        data["hours"] = [max(0, int(n or 0)) for n in data["hours"][:24]]
        return data

    def use_reset(self) -> dict:
        """Spend one banked Ornis reset. {ok, reason, available, tokens}; reason is early, none, empty or failed."""
        status, body = self._ocs(f"{USAGE}/reset?format=json", "POST", {})
        data = _data(body) if _ok(status) else None
        return data if isinstance(data, dict) else {"ok": False, "reason": "failed"}

    def region(self) -> dict | None:
        """Where Ornis runs for the account (orneos app, OrnisRegion): {region, effective, needs_consent, regions:
        {eu: {available, providers}, global: {available, providers: [{name, country, country_name}], countries}}}."""
        status, body = self._ocs(f"{REGION}?format=json")
        data = _data(body) if _ok(status) else None
        return data if isinstance(data, dict) and data.get("regions") else None

    def set_region(self, region: str, accept: list | None = None) -> dict:
        """Choose « eu » or « global » (with the country codes the warning showed). {…region, error?}."""
        status, body = self._ocs(f"{REGION}?format=json", "PUT", {"region": region, "accept": list(accept or [])})
        data = _data(body)
        data = data if isinstance(data, dict) else {}
        if not _ok(status) and not data.get("error"):
            data["error"] = "failed"
        return data

    def quota(self) -> dict | None:
        """Today's Ornis allowance (integration_openai, text tokens over a rolling 24 h): {used, limit, percent}."""
        status, body = rest(self.server, self.user, self.password, "/index.php/apps/integration_openai/quota-info")
        if not _ok(status) or not isinstance(body, dict):
            return None
        usage = body.get("quota_usage")
        slot = usage[0] if isinstance(usage, list) and usage else (usage or {}).get("0") if isinstance(usage, dict) else None
        if not isinstance(slot, dict) or int(slot.get("limit") or 0) <= 0:
            return None
        used, limit = max(0, int(slot.get("used") or 0)), int(slot["limit"])
        return {"used": used, "limit": limit, "percent": min(100, round(100 * used / limit))}
