"""Ornis in Notes: summarize a note, tidy it up, correct it, shorten or translate it, turn a list into a
checklist, find the tasks it holds (they go to Tâches), and answer a question from the notes themselves.

Each request is a task of the cloud's AI (core:text2text:chat), in the same 24 h allowance as Plume and the
top-bar applet. Nothing is sent before the person asks: the note they work on, or, for a question, only the
few notes that share its words (the window says which). Answers stay in memory, never on disk.
"""
import json
import re
import threading
import time
from datetime import date
from urllib.parse import quote

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

import cloud

TASK = "core:text2text:chat"
LIMIT = 14000
LANGS = {"fr": "French", "en": "English", "de": "German", "es": "Spanish", "it": "Italian"}
SYSTEM = ("You are Ornis, the assistant of Orneos, built into Notes, its notes app. Notes are Markdown. "
          "Answer with the requested content only: no preamble, no comment, no code fences around it. "
          "Never invent facts that are not in the text you were given.")
STYLE = {
    "proofread": "Correct spelling, grammar and punctuation. Change nothing else: same words, tone, Markdown and layout.",
    "tidy": ("Tidy up this note: a clear first line as its title, short sections with ## headings where it helps, "
             "lists for enumerations, checklists (- [ ]) for things to do. Keep every piece of information, the "
             "language, the links, the images (![...](...)) and the #tags."),
    "concise": "Make it shorter and clearer, keeping every piece of information, the Markdown and the language.",
    "checklist": ("Turn the things to do or to buy in this text into a Markdown checklist (- [ ] item), one item per "
                  "line. Keep the first line (the title) and the language. Keep items already checked as - [x]."),
}

# the same requests for a passage chosen in the note (it goes back in its place: no title, no whole note)
PART = {
    "proofread": "Correct spelling, grammar and punctuation of this passage of a note. Change nothing else: same words, "
                 "tone, Markdown and layout.",
    "tidy": ("Tidy up this passage of a note: lists for enumerations, checklists (- [ ]) for things to do, short "
             "paragraphs. No title. Keep every piece of information, the language, the links and the #tags."),
    "concise": "Make this passage of a note shorter and clearer, keeping every piece of information, the Markdown and "
               "the language.",
    "checklist": ("Turn the things to do or to buy in this passage into a Markdown checklist (- [ ] item), one item per "
                  "line, in its language. Keep items already checked as - [x]."),
}


def _unthink(text):
    return re.sub(r"(?s)^\s*<think>.*?</think>", "", text or "").strip()


def _clean(text):
    text = _unthink(text)
    return re.sub(r"(?s)^```[a-z]*\n(.*)\n```$", r"\1", text).strip()


def _json_list(text):
    text = re.sub(r"(?s)```(?:json)?(.*?)```", r"\1", _unthink(text))
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "[":
            try:
                value = decoder.raw_decode(text, i)[0]
            except json.JSONDecodeError:
                continue
            if isinstance(value, list):
                return value
    return None


class Ornis(QObject):
    answered = Signal(int, str, "QVariant")
    failed = Signal(int, str, str)
    changed = Signal()
    _done = Signal(int, str, object, str)
    _quotaRead = Signal(object)

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._next = 0
        self._busy = set()
        self._cache = {}
        self._quota = None
        self._done.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self._quotaRead.connect(self._set_quota)

    @Property(bool, notify=changed)
    def busy(self):
        return bool(self._busy)

    @Property("QVariantMap", notify=changed)
    def quota(self):
        return self._quota or {}

    @Slot(str, "QVariantMap", result=int)
    def ask(self, kind, data):
        """kind: summary | proofread | tidy | concise | checklist | translate {lang} | tasks | continue {before} |
        question {question, notes: [{title, content}]}. data.text is the note, or the passage chosen (part: true)."""
        data = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(data).items()}
        self._next += 1
        request = self._next
        key = kind + ":" + json.dumps(data, sort_keys=True, ensure_ascii=False)
        if key in self._cache:
            self._done.emit(request, kind, self._cache[key], "")
            return request
        account = self._app.account()
        if account is None:
            self._done.emit(request, kind, "", self._app.t["ornis_offline"])
            return request
        prompt = self._prompt(kind, data)
        self._busy.add(request)
        self.changed.emit()

        def run():
            answer, error = self._run_task(account, prompt)
            result = answer
            if not error and kind == "tasks":
                items = _json_list(answer)
                result = [{"title": str(i.get("title") or "").strip(), "due": str(i.get("due") or "")[:10]}
                          for i in (items or []) if isinstance(i, dict) and str(i.get("title") or "").strip()]
                if items is None:
                    error = "failed"
            if not error and result:
                self._cache[key] = result
            message = "" if not error else self._app.t["ornis_quota" if error == "quota" else
                                                         "ornis_offline" if error == "offline" else "ornis_failed"]
            self._done.emit(request, kind, result, message)
            self._refresh_quota(account)
        threading.Thread(target=run, daemon=True).start()
        return request

    def _prompt(self, kind, data):
        lang = LANGS.get(self._app.lang, "French")
        text = str(data.get("text") or "")[:LIMIT]
        if data.get("part"):
            # a passage chosen in the note: the same request, for it alone (it goes back in its place)
            if kind == "summary":
                return (f"Summarize this passage of a note in {lang} in 1 to 4 short Markdown bullet points, nothing "
                        "else.\n\n" + text)
            if kind in PART:
                return PART[kind] + " Answer with the new passage only.\n\n" + text
            if kind == "translate":
                target = LANGS.get(str(data.get("lang") or "en"), "English")
                return (f"Translate this passage of a note into {target}. Keep the Markdown, the links and the #tags "
                        "as they are. Answer with the translated passage only.\n\n" + text)
        if kind == "continue":
            before = str(data.get("before") or text)[-LIMIT:]
            return ("Continue writing this note from where the text stops (marked ⟨here⟩), in its language, tone and "
                    "Markdown: 1 to 3 short paragraphs or list items that follow naturally. Do not repeat what is "
                    "already written. Answer with the new text only.\n\n" + before + "⟨here⟩")
        if kind == "summary":
            return (f"Summarize this note in {lang} as 2 to 5 short Markdown bullet points (the essentials, decisions "
                    "and what remains to do), nothing else.\n\n" + text)
        if kind in STYLE:
            return STYLE[kind] + " Answer with the whole new note only.\n\n" + text
        if kind == "translate":
            target = LANGS.get(str(data.get("lang") or "en"), "English")
            return (f"Translate this note into {target}. Keep the Markdown, the links, the images and the #tags as they "
                    "are. Answer with the translated note only.\n\n" + text)
        if kind == "tasks":
            return ("Find the tasks in this note: things the person (or someone named) has to do. Answer with a JSON "
                    'array only, like [{"title": "Call the plumber", "due": "2026-10-22"}]. The title is short, in the '
                    "language of the note, starts with a verb and names who does it when it is someone else. due is "
                    f"YYYY-MM-DD when the note gives a date (today is {date.today().isoformat()}), else \"\". Leave out "
                    "what is already checked (- [x]). [] if there are none.\n\n" + text)
        notes = data.get("notes") or []
        sources = "\n\n".join(f"[{i + 1}] {n.get('title', '')}\n{str(n.get('content', ''))[:2400]}"
                              for i, n in enumerate(notes[:6]))
        return (f"Answer this question in {lang} using only these notes of the person, numbered. Cite the notes you "
                "use as [1], [2] after the sentence. Short answer, light Markdown. If the notes do not say, say so in "
                f"one sentence.\n\nQuestion: {data.get('question', '')}\n\nNotes:\n{sources}")

    def _finish(self, request, kind, result, error):
        if request in self._busy:
            self._busy.discard(request)
            self.changed.emit()
        if error:
            self.failed.emit(request, kind, error)
        else:
            self.answered.emit(request, kind, result)

    def _run_task(self, account, prompt):
        server, user, password = account
        payload = {"type": TASK, "appId": "orneos-notes", "customId": "notes",
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
        deadline, pause = time.time() + 120, 0.4
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
                return _clean(str(out.get("output") or out.get("text") or "")), ""
            if state in ("STATUS_FAILED", "4", "STATUS_CANCELLED", "5"):
                return "", "quota" if "quota" in str(current.get("errorMessage") or "").lower() else "failed"
        return "", "failed"

    @Slot()
    def loadQuota(self):
        account = self._app.account()
        if account is not None:
            threading.Thread(target=self._refresh_quota, args=(account,), daemon=True).start()

    def _refresh_quota(self, account):
        server, user, password = account
        quota = None
        status, body = cloud.rest(server, user, password, "/apps/integration_openai/quota-info")
        if status in (200, 100) and isinstance(body, dict):
            usage = body.get("quota_usage") or ((body.get("ocs") or {}).get("data") or {}).get("quota_usage")
            slot = usage[0] if isinstance(usage, list) and usage else (
                (usage.get(0) or usage.get("0")) if isinstance(usage, dict) else None)
            if isinstance(slot, dict) and int(slot.get("limit") or 0) > 0:
                quota = {"percent": min(100, round(100 * max(0, int(slot.get("used") or 0)) / int(slot["limit"])))}
        self._quotaRead.emit(quota)

    def _set_quota(self, quota):
        self._quota = quota
        self.changed.emit()
