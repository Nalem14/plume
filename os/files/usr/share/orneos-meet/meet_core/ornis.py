"""Ornis in Meet: sum up what was missed in a conversation, translate a message, write the minutes of a meeting
(for Notes), find the tasks in it (for Tâches), suggest replies, answer a question about the conversation.

Each request is a task of the cloud's AI (core:text2text:chat), in the same 24 h allowance as Plume, Notes and
the top-bar applet. Nothing is sent before the person asks: only the messages of the summary, or the one
message to translate. Answers stay in memory, never on disk.
"""
import json
import re
import threading
import time
from urllib.parse import quote

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

import cloud

TASK = "core:text2text:chat"
LIMIT = 14000
LANGS = {"fr": "French", "en": "English", "de": "German"}
SYSTEM = ("You are Ornis, the assistant of Orneos, built into Meet, its chat and video call app. "
          "Answer with the requested content only: no preamble, no comment, no code fences around it. "
          "Never invent facts that are not in the messages you were given.")


def _clean(text):
    text = re.sub(r"(?s)^\s*<think>.*?</think>", "", text or "").strip()
    return re.sub(r"(?s)^```[a-z]*\n(.*)\n```$", r"\1", text).strip()


class Ornis(QObject):
    answered = Signal(int, str, str)        # request, kind, text (Markdown)
    failed = Signal(int, str, str)          # request, kind, message
    changed = Signal()
    _done = Signal(int, str, str, str)

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._next = 0
        self._busy = set()
        self._cache = {}
        self._done.connect(self._finish, Qt.ConnectionType.QueuedConnection)

    @Property(bool, notify=changed)
    def busy(self):
        return bool(self._busy)

    @Slot(str, "QVariantMap", result=int)
    def ask(self, kind, data):
        """kind: summary | minutes | tasks | replies | ask {room, lines: ["Name (HH:MM): text"], question, me}
        | translate {text}. tasks and replies answer JSON (as text)."""
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
            if not error and answer:
                self._cache[key] = answer
            message = "" if not error else self._app.t["ornis_quota" if error == "quota" else
                                                         "ornis_offline" if error == "offline" else "ornis_failed"]
            self._done.emit(request, kind, answer, message)
        threading.Thread(target=run, daemon=True).start()
        return request

    def _prompt(self, kind, data):
        lang = LANGS.get(self._app.lang, "French")
        lines = "\n".join(str(line) for line in (data.get("lines") or []))[-LIMIT:]
        room = data.get("room", "")
        if kind == "minutes":
            return (f"Here are the messages of the conversation « {room} » (a meeting and its chat). In {lang}, write "
                    "its minutes in Markdown: a one-sentence summary, then the sections « Decisions », « Actions » "
                    "(who does what, by when if said) and « Open questions » (translated into the language), short "
                    "bullet points, nothing invented. No title at the top.\n\n" + lines)
        if kind == "tasks":
            return (f"Here are messages of the conversation « {room} ». Find the concrete tasks that someone must do "
                    f"(asked, promised or decided). Answer with a JSON array only: "
                    '[{"title": "...", "due": "YYYY-MM-DD or empty", "who": "name or empty"}], '
                    f"titles in {lang}, short and starting with a verb; [] if there is none.\n\n" + lines)
        if kind == "replies":
            return (f"Here are the last messages of the conversation « {room} »; the person is « {data.get('me', '')} ». "
                    f"Suggest three short replies they could send next, in the language of the conversation, different "
                    'in tone (yes, a question, later). Answer with a JSON array of three strings only.\n\n' + lines)
        if kind == "ask":
            return (f"Here are messages of the conversation « {room} ». Answer this question of the person in {lang}, "
                    "from these messages only (say so if they do not tell), short, light Markdown. Question: "
                    f"{data.get('question', '')}\n\n" + lines)
        if kind == "summary":
            return (f"Here are the messages of the conversation « {room} » the person has not read. "
                    f"In {lang}, sum them up for them in a few bullet points: what was said or decided, who asks "
                    "them something (with their name), and what is still open. Short, light Markdown, no headings.\n\n"
                    + lines)
        return (f"Translate this message into {lang}. If it is already in {lang}, translate it into English. "
                "Keep the tone, the names, the emojis and the Markdown.\n\n" + str(data.get("text") or "")[:LIMIT])

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
        payload = {"type": TASK, "appId": "orneos-meet", "customId": "meet",
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
                cloud.ocs(server, user, password, path, method="DELETE")     # nothing kept in the cloud
                return _clean(str(out.get("output") or out.get("text") or "")), ""
            if state in ("STATUS_FAILED", "4", "STATUS_CANCELLED", "5"):
                cloud.ocs(server, user, password, path, method="DELETE")
                return "", "quota" if "quota" in str(current.get("errorMessage") or "").lower() else "failed"
        cloud.ocs(server, user, password, path, method="DELETE")     # given up: not left waiting in the cloud
        return "", "failed"
