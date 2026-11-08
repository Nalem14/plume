"""Ornis in Plume: summaries, suggested replies, writing tools, events from plain words.

Each request is a task of the cloud's AI (task processing, core:text2text:chat), so it counts in the same
24 h allowance as the top-bar applet and the cloud's assistant. Nothing is sent before the person asks,
except the summary of an opened message when they turned that option on. Answers are kept in memory for
the session (the same summary is not asked twice), never on disk.
"""
import json
import re
import threading
import time
from datetime import datetime
from urllib.parse import quote

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

import cloud

TASK = "core:text2text:chat"
LIMIT = 12000              # characters of a message given to the model

LANGS = {"fr": "French", "en": "English", "de": "German", "es": "Spanish", "it": "Italian"}

STYLE = {
    "proofread": "Correct spelling, grammar and punctuation. Change nothing else: same words, tone and layout.",
    "professional": "Rewrite it in a more professional, polished tone. Keep the meaning and the language.",
    "friendly": "Rewrite it in a warmer, friendlier tone. Keep the meaning and the language.",
    "concise": "Make it shorter and clearer, keeping every piece of information. Keep the language.",
    "expand": "Develop it a little: complete the sentences, add the natural politeness. Keep the language.",
}

SYSTEM = ("You are Ornis, the assistant of Orneos, built into Plume, its mail and calendar app. "
          "Answer with the requested content only: no preamble, no comment, no quotes around it, no Markdown "
          "headings. Light Markdown (bold, lists, links) is fine where the answer is read, never in JSON. "
          "Never invent facts that are not in the text you were given. "
          "A message you write is written for the person, in their name and their voice: never sign it Ornis, "
          "never mention yourself or an assistant, and never leave placeholders such as [Prénom] or [Name].")

# what a writing model adds at the end of a message written for someone else: its own name as a signature
_SELF_NAME = r"(?:Ornis|l['’]assistant(?: d['’]Orneos)?|(?:votre|your|ihr) assistant(?: Ornis)?)"
_SELF_LINE = re.compile(r"(?i)^\s*[-–—]*\s*" + _SELF_NAME + r"\s*[.!]?\s*$")
_SELF_AFTER_CLOSING = re.compile(r"(?i)^(?P<keep>.{2,40}?)[,;]?\s+(?:[-–—]\s*)?" + _SELF_NAME + r"\s*[.!]?\s*$")
_PLACEHOLDER = re.compile(r"(?:\s+(?:pour|de|du|des|sur|concernant|for|about|regarding|on|für|über|zu)(?=\s*\[))?"
                          r"\s*\[(?:(?:pr[ée]nom|nom|name|first name|vorname|destinataire|recipient|votre nom|"
                          r"your name|ihr name)\]|(?:pr[ée]ciser|ins[ée]rer|indiquer|ajouter|compl[ée]ter|"
                          r"specify|insert|add|fill|angeben|einf[üu]gen)\b[^\]\n]*\](?!\())", re.I)
_GREETING = re.compile(r"^\s*(bonjour|bonsoir|salut|coucou|hello|hi|hey|dear|cher|ch[èe]re|madame|monsieur|"
                       r"hallo|liebe|lieber|sehr geehrte|guten tag|moin|ciao|hola)\b", re.I)


def _unsigned(text):
    """A written message without the « Ornis » signature nor the [Prénom] placeholders a model may leave."""
    lines = text.rstrip().split("\n")
    if lines and _SELF_LINE.match(lines[-1]):                # « Bonne journée,\nOrnis »
        lines.pop()
    elif len(lines) > 1:
        m = _SELF_AFTER_CLOSING.match(lines[-1])             # « Bonne journée, Ornis »
        if m:
            lines[-1] = m.group("keep").rstrip(" ,;") + ","
    text = "\n".join(lines).rstrip()
    return _PLACEHOLDER.sub("", text).replace(" ,", ",")


def _continued(beginning, answer):
    """The beginning the person wrote, untouched, then what the model wrote after it (without what it
    repeated of the beginning: its own greeting, or the beginning copied whole)."""
    beginning = beginning.rstrip()
    if not beginning:
        return answer
    def flat(t):
        return re.sub(r"\s+", " ", t).strip().lower()
    if flat(answer).startswith(flat(beginning)):
        # copied whole: keep what follows, cut after the same number of non-space characters
        want = len(re.sub(r"\s", "", beginning))
        seen = 0
        for i, ch in enumerate(answer):
            if not ch.isspace():
                seen += 1
            if seen == want:
                answer = answer[i + 1:]
                break
    else:
        lines = answer.lstrip().split("\n")
        # a greeting of its own while the person already wrote one
        if lines and _GREETING.match(lines[0]) and _GREETING.match(beginning) and len(lines[0]) < 80:
            lines = lines[1:]
        answer = "\n".join(lines)
    answer = answer.strip("\n ")
    if not answer:
        return beginning
    last = beginning.split("\n")[-1]
    if _GREETING.match(last) and last.endswith((",", "!")):
        joiner = "\n\n"                                    # « Salut Clément, » then the message
    elif last.endswith((".", "!", "?", ":")):
        joiner = "\n"
    else:
        joiner = "" if answer[:1] in ",.;:!?" else " "      # a sentence left unfinished
    return beginning + joiner + answer


def _json_in(text, accept=lambda value: True):
    """The first JSON array or object in a model answer that accept() takes (the model may wrap it in ```
    or a sentence, which can hold brackets of its own: « voir [1] »)."""
    text = re.sub(r"(?s)```(?:json)?(.*?)```", r"\1", _unthink(text))
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                value = decoder.raw_decode(text, i)[0]
            except json.JSONDecodeError:
                continue
            if accept(value):
                return value
    return None


def _replies_like(value):
    if isinstance(value, dict):
        return any(_replies_like(v) for v in value.values() if isinstance(v, list))
    return isinstance(value, list) and any(isinstance(r, dict) or (isinstance(r, str) and r.strip()) for r in value)


def _unthink(text):
    """Reasoning models may put their thoughts first, between <think> tags."""
    return re.sub(r"(?s)^\s*<think>.*?</think>", "", text or "").strip()


def _clean(text):
    """Strip what models add around the asked text."""
    text = _unthink(text)
    text = re.sub(r"(?s)^```[a-z]*\n(.*)\n```$", r"\1", text).strip()
    for opener, closer in (('"', '"'), ("«", "»"), ("“", "”"), ("„", "“")):
        if len(text) > 1 and text.startswith(opener) and text.endswith(closer) and text.count(opener) == 1:
            return text[1:-1].strip()
    return text


class Ornis(QObject):
    answered = Signal(int, str, "QVariant")     # request id, kind, result
    failed = Signal(int, str, str)              # request id, kind, message
    changed = Signal()
    _done = Signal(int, str, object, str)
    _quotaRead = Signal(object)

    def __init__(self, plume, store):
        super().__init__()
        self._plume = plume
        self._store = store
        self._next = 0
        self._busy = set()
        self._dropped = set()
        self._cache = {}
        self._quota = None
        # queued: a cached answer (or an error found at once) must reach QML after ask() returned its id
        self._done.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self._quotaRead.connect(self._set_quota)

    # ---- state ------------------------------------------------------------------------------------------
    @Property(bool, notify=changed)
    def busy(self):
        return bool(self._busy)

    @Property("QVariantMap", notify=changed)
    def quota(self):
        return self._quota or {}

    @Property(bool, notify=changed)
    def autoSummary(self):
        return bool(self._store.get("ornis_auto_summary", False))

    @autoSummary.setter
    def autoSummary(self, value):
        self._store.set("ornis_auto_summary", bool(value))
        self.changed.emit()

    @Slot(int, result=bool)
    def running(self, request):
        return request in self._busy

    @Slot(str, result="QVariant")
    def cached(self, key):
        return self._cache.get(key)

    # ---- requests ---------------------------------------------------------------------------------------
    @Slot(str, "QVariantMap", result=int)
    def ask(self, kind, data):
        """Start one request; the answer comes through answered(id, kind, result) or failed(id, kind, text).
        kinds: summary, replies, rewrite, draft, event, mailEvent, question, contact (a signature read into a card)."""
        data = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(data).items()}
        self._next += 1
        request = self._next
        key = data.get("cacheKey") or ""
        if key and key in self._cache:
            self._done.emit(request, kind, self._cache[key], "")
            return request
        account = self._plume.account()
        if account is None:
            self._done.emit(request, kind, None, self._plume.t["ornis_offline"])
            return request
        prompt = self._prompt(kind, data)
        self._busy.add(request)
        self.changed.emit()

        def run():
            answer, error = self._run_task(account, prompt)
            result = None
            if not error:
                result = self._parse(kind, answer, data)
                if result is None:
                    error = self._plume.t["ornis_unclear"]
                elif key:
                    self._cache[key] = result
            elif error == "quota":
                error = self._plume.t["ornis_quota"]
            else:
                error = self._plume.t["ornis_failed"]
            self._done.emit(request, kind, result, error)
            self._refresh_quota(account)
        threading.Thread(target=run, daemon=True).start()
        return request

    @Slot(int)
    def cancel(self, request):
        """The answer is no longer wanted (the panel was closed): it will be dropped."""
        if request in self._busy:
            self._busy.discard(request)
            self._dropped.add(request)
            self.changed.emit()

    @Slot()
    def loadQuota(self):
        account = self._plume.account()
        if account is not None:
            threading.Thread(target=self._refresh_quota, args=(account,), daemon=True).start()

    def _finish(self, request, kind, result, error):
        if request in self._dropped:
            self._dropped.discard(request)
            return
        if request in self._busy:
            self._busy.discard(request)
            self.changed.emit()
        if error:
            self.failed.emit(request, kind, error)
        else:
            self.answered.emit(request, kind, result)

    # ---- prompts ----------------------------------------------------------------------------------------
    def _language(self):
        return LANGS.get(self._plume.lang, "French")

    @staticmethod
    def _mail_block(data):
        text = (data.get("text") or "")[:LIMIT]
        return (f"From: {data.get('from', '')}\nDate: {data.get('date', '')}\nSubject: {data.get('subject', '')}\n\n{text}")

    def _prompt(self, kind, data):
        ui = self._language()
        if kind == "summary":
            return ("Summarise this " + ("conversation" if data.get("thread") else "email") + " in " + ui
                    + " as a Markdown list of 1 to 3 short items starting with \"- \". "
                    "If the sender expects something (an answer, a date, a payment, a document), say it in the "
                    "last bullet, starting with the action. Mention dates and amounts exactly.\n\n"
                    + self._mail_block(data))
        if kind == "replies":
            return ("Suggest 3 different short replies the recipient could send to this email (accept, decline "
                    "or ask for something, as fits). Write them in the language of the email, signed by nobody. "
                    "Answer with a JSON array only: [{\"label\": \"2 to 4 words in " + ui + "\", "
                    "\"text\": \"the reply, 1 to 3 sentences\"}].\n\n" + self._mail_block(data))
        if kind == "rewrite":
            mode = data.get("mode", "proofread")
            if mode.startswith("translate:"):
                target = LANGS.get(mode.split(":", 1)[1], mode.split(":", 1)[1])
                instruction = f"Translate it into {target}. Keep the tone and the layout."
            elif mode == "custom":
                instruction = ("Apply this instruction to it: " + data.get("instruction", "")
                               + ". Keep its language unless the instruction says otherwise.")
            else:
                instruction = STYLE.get(mode, STYLE["proofread"])
            context = ""
            if data.get("context"):
                context = "For context, it answers this email (do not repeat it):\n" + data["context"][:4000] + "\n\n"
            return (context + instruction + " Keep paragraphs and line breaks. Answer with the new text only.\n\n"
                    "Text:\n" + data.get("text", ""))
        if kind == "draft":
            parts = []
            if data.get("context"):
                parts.append("It answers this email:\n" + data["context"][:6000])
            facts = []
            name = re.sub(r"\s*<[^>]*>\s*", "", data.get("from") or "").strip()
            if data.get("from"):
                facts.append("Written by: " + data["from"])
            if data.get("to"):
                facts.append("To: " + data["to"])
            if data.get("subject"):
                facts.append("Subject: " + data["subject"])
            if facts:
                parts.append("\n".join(facts))
            beginning = (data.get("beginning") or "").strip()
            signed = data.get("signed")
            closing = ("End with a closing line only (such as « Bonne journée, »): the sender's signature is "
                       "added after it." if signed else
                       "End with a closing line, then the sender's first name alone on its own line"
                       + (" (from « " + name + " »)" if name else "") + ", never their address.")
            rules = ("Write in the sender's name, as them (never sign Ornis, never mention an assistant). "
                     "Use the recipient's real first name when it is known (from the beginning, the email "
                     "answered or the address), otherwise a greeting without a name. Never a placeholder or a "
                     "note in brackets: when a detail is not given, write around it. No subject line. " + closing)
            if beginning:
                lang = "the language of the beginning"
                task = ("The sender already wrote the beginning of the message:\n<<<\n" + beginning + "\n>>>\n"
                        "Continue it from there, following this instruction: " + data.get("instruction", "")
                        + "\nKeep their register (tu or vous, formal or casual) and their greeting. Answer with "
                        "the whole message, starting with the beginning exactly as written, word for word, then "
                        "what follows (when it stops in the middle of a sentence, complete that sentence). "
                        "Never say that you continue or complete anything. "
                        "Write in " + lang + ". " + rules)
            else:
                lang = "the language of that email" if data.get("context") else "the language of the instruction"
                task = ("Write the body of an email following this instruction, in " + lang + ", "
                        "with a greeting: " + data.get("instruction", "") + "\nUse « vous » (or the formal form "
                        "of the language) unless the instruction or the email answered uses « tu». " + rules)
            parts.append(task)
            return "\n\n".join(parts)
        if kind in ("event", "mailEvent"):
            now = datetime.now().astimezone()
            today = now.strftime("%A %d %B %Y, %H:%M (UTC%z)")
            schema = ('{"title": "short title", "start": "YYYY-MM-DDTHH:MM", "end": "YYYY-MM-DDTHH:MM", '
                      '"allDay": false, "location": "", "notes": ""}')
            rules = ("Times are local. Without an end, an event lasts one hour; an all-day event uses "
                     "\"YYYY-MM-DD\" dates with an end on the last day. A weekday means the next one to come. "
                     "Title and notes in the language of the text.")
            if kind == "event":
                return (f"Now is {today}. Turn this description into a calendar event. {rules} "
                        f"Answer with JSON only: {schema}\n\nDescription: {data.get('text', '')}")
            return (f"Now is {today}. If this email proposes or confirms a meeting, an appointment, a trip or a "
                    f"deadline, turn it into a calendar event ({rules} Put useful references, such as a booking "
                    f"number, in notes). Answer with JSON only: {schema}, or {{\"none\": true}} if there is no "
                    f"event.\n\n" + self._mail_block(data))
        if kind == "question":
            return ("Answer this question about the email below in " + ui + ", briefly and only from what it "
                    "says (say so if it does not tell).\n\nQuestion: " + data.get("question", "")
                    + "\n\n" + self._mail_block(data))
        if kind == "contact":
            # only what the person wrote about themselves (a signature): never guessed
            return ("Below is the end of an email written by " + (data.get("name") or "someone") + " <"
                    + data.get("email", "") + ">. From its signature only, give what it says about the sender. "
                    'Answer with JSON only: {"org": "", "title": "", "phones": [{"type": "cell|work|home|fax", '
                    '"value": ""}], "url": "", "address": {"street": "", "code": "", "city": "", "country": ""}}. '
                    "Leave a field empty when the signature does not say it; never invent a value.\n\n"
                    + (data.get("text") or "")[:4000])
        return data.get("text", "")

    def _parse(self, kind, answer, data=None):
        data = data or {}
        answer = _clean(answer)
        if not answer:
            return None
        if kind == "replies":
            found = _json_in(answer, _replies_like)
            if isinstance(found, dict):
                found = next((v for v in found.values() if _replies_like(v)), None)
            if not isinstance(found, list):
                return None
            replies = []
            for r in found:
                if isinstance(r, str) and r.strip():
                    r = {"text": r}
                if not isinstance(r, dict):
                    continue
                text = str(r.get("text") or r.get("reply") or r.get("body") or r.get("message") or "").strip()
                if text:
                    label = str(r.get("label") or r.get("title") or "").strip() or text[:30]
                    replies.append({"label": label[:40], "text": _unsigned(text)})
            return replies[:3] or None
        if kind in ("event", "mailEvent"):
            found = _json_in(answer, lambda v: isinstance(v, dict))
            if not isinstance(found, dict):
                return None
            if found.get("none"):
                return {"none": True}
            start = str(found.get("start", ""))
            if not re.match(r"^\d{4}-\d{2}-\d{2}", start):
                return None
            all_day = bool(found.get("allDay")) or len(start) == 10
            end = str(found.get("end") or "")
            if not re.match(r"^\d{4}-\d{2}-\d{2}", end):
                end = start
            return {"title": str(found.get("title", "")).strip(), "start": start[:16], "end": end[:16],
                    "allDay": all_day, "location": str(found.get("location") or "").strip(),
                    "notes": str(found.get("notes") or "").strip()}
        if kind == "contact":
            found = _json_in(answer, lambda v: isinstance(v, dict))
            if not isinstance(found, dict):
                return None
            source = data.get("text") or ""
            digits = re.sub(r"\D", "", source)
            phones = []
            for p in found.get("phones") or []:
                value = str((p or {}).get("value") or "").strip() if isinstance(p, dict) else str(p).strip()
                # a number the model did not read in the text is dropped
                if value and re.sub(r"\D", "", value)[-8:] in digits:
                    kind_ = str(p.get("type") or "work") if isinstance(p, dict) else "work"
                    phones.append({"type": kind_ if kind_ in ("cell", "work", "home", "fax") else "work", "value": value})
            address = found.get("address") if isinstance(found.get("address"), dict) else {}
            address = {k: str(address.get(k) or "").strip() for k in ("street", "code", "city", "country")}
            url = str(found.get("url") or "").strip()
            out = {"org": str(found.get("org") or "").strip(), "title": str(found.get("title") or "").strip(),
                   "phones": phones, "url": url if url and url.split("//")[-1].split("/")[0].lower() in source.lower() else "",
                   "address": address if any(address.values()) else {}}
            return out if any((out["org"], out["title"], out["phones"], out["url"], out["address"])) else {"none": True}
        if kind == "draft":
            return _continued(data.get("beginning") or "", _unsigned(answer)) or None
        if kind == "rewrite":
            return _unsigned(answer) or None
        return answer

    # ---- the cloud --------------------------------------------------------------------------------------
    def _run_task(self, account, prompt):
        """(answer, error): error is "", "quota", "failed" or "offline"."""
        server, user, password = account
        payload = {"type": TASK, "appId": "orneos-plume", "customId": "plume",
                   "input": {"input": prompt, "system_prompt": SYSTEM, "history": []}}
        status, body = cloud.ocs(server, user, password, "/ocs/v2.php/taskprocessing/schedule?format=json",
                                 method="POST", body=payload)
        data = ((body or {}).get("ocs") or {}).get("data") if isinstance(body, dict) else None
        task = (data or {}).get("task") if isinstance(data, dict) else None
        if status == 0:
            return "", "offline"
        if status == 429 or (isinstance(body, dict) and "quota" in json.dumps(body).lower() and not task):
            return "", "quota"
        if not isinstance(task, dict) or task.get("id") is None:
            return "", "failed"
        path = f"/ocs/v2.php/taskprocessing/task/{quote(str(task['id']), safe='')}?format=json"
        try:
            deadline = time.time() + 120
            pause = 0.5
            while time.time() < deadline:
                time.sleep(pause)
                pause = min(2.0, pause * 1.3)
                status, body = cloud.ocs(server, user, password, path)
                if status not in (200, 100) or not isinstance(body, dict):
                    continue
                current = ((body.get("ocs") or {}).get("data") or {}).get("task") or {}
                state = str(current.get("status") or "")
                if state in ("STATUS_SUCCESSFUL", "3"):
                    out = current.get("output") or {}
                    return str(out.get("output") or out.get("text") or ""), ""
                if state in ("STATUS_FAILED", "4", "STATUS_CANCELLED", "5"):
                    message = str(current.get("errorMessage") or "").lower()
                    return "", "quota" if "quota" in message else "failed"
            return "", "failed"
        finally:
            # the text asked about (a mail, a note) is not kept in the cloud once answered (privacy page, #plume);
            # the usage counted for the quota stays
            cloud.ocs(server, user, password, path, method="DELETE")

    def _refresh_quota(self, account):
        server, user, password = account
        quota = None
        status, body = cloud.rest(server, user, password, "/apps/integration_openai/quota-info")
        if status in (200, 100) and isinstance(body, dict):
            usage = body.get("quota_usage") or ((body.get("ocs") or {}).get("data") or {}).get("quota_usage")
            slot = usage[0] if isinstance(usage, list) and usage else (
                (usage.get(0) or usage.get("0")) if isinstance(usage, dict) else None)
            if isinstance(slot, dict) and int(slot.get("limit") or 0) > 0:
                limit, used = int(slot["limit"]), max(0, int(slot.get("used") or 0))
                quota = {"percent": min(100, round(100 * used / limit))}
        self._quotaRead.emit(quota)

    def _set_quota(self, quota):
        self._quota = quota
        self.changed.emit()
