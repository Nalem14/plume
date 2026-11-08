"""Ornis in Tâches: break a task down into subtasks, plan the day (in what order, what can wait), and turn
a text (a mail, minutes, a message) into tasks.

Each request is a task of the cloud's AI (core:text2text:chat), in the same 24 h allowance as Plume, Notes
and the top-bar applet. Nothing is sent before the person asks: the task, the titles of the day's tasks, or
the text pasted. Answers stay in memory, never on disk.
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
SYSTEM = ("You are Ornis, the assistant of Orneos, built into Tâches, its tasks and reminders app. "
          "Answer with the requested content only: no preamble, no comment, no code fences around it. "
          "Never invent facts that are not in the text you were given.")


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
        """kind: breakdown {title, notes} | plan {tasks: [{title, due, priority, list, flagged}]} | extract {text}."""
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
            if not error and kind in ("extract", "breakdown"):
                items = _json_list(answer)
                if items is None:
                    error = "failed"
                elif kind == "breakdown":
                    result = [str(i.get("title") if isinstance(i, dict) else i).strip() for i in items
                              if str(i.get("title") if isinstance(i, dict) else i).strip()][:12]
                else:
                    result = [{"title": str(i.get("title") or "").strip(), "due": str(i.get("due") or "")[:16]}
                              for i in items if isinstance(i, dict) and str(i.get("title") or "").strip()]
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
        today = date.today().isoformat()
        if kind == "breakdown":
            return (f"Break this task down into 3 to 7 concrete subtasks, in {lang}, in the order to do them, each "
                    "short and starting with a verb. Answer with a JSON array of strings only.\n\nTask: "
                    f"{data.get('title', '')}\nNotes: {str(data.get('notes') or '')[:2000]}")
        if kind == "plan":
            lines = "\n".join(f"- {t.get('title', '')}" + (f" (due {t['due']})" if t.get("due") else "") +
                               (" [high priority]" if t.get("priority") == 3 else "") + (" [flagged]" if t.get("flagged") else "") +
                               (f" [list: {t['list']}]" if t.get("list") else "") for t in (data.get("tasks") or [])[:40])
            return (f"Today is {today}. Here are the person's tasks for today and the late ones. In {lang}, propose a "
                    "plan for the day: a numbered list in the order to do them (late and urgent first, quick ones "
                    "grouped), with **the task** then a few words of why; then one line on what can wait until "
                    f"tomorrow. Short, light Markdown, no headings.\n\n{lines}")
        return ("Find the tasks in this text: things the person has to do (or someone named). Answer with a JSON array "
                'only, like [{"title": "Call the plumber", "due": "2026-10-22"}]. The title is short, in the language '
                f"of the text, starts with a verb. due is YYYY-MM-DD (or YYYY-MM-DDTHH:MM with a time) when the text "
                f"gives one (today is {today}), else \"\". [] if there are none.\n\n" + str(data.get("text") or "")[:LIMIT])

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
        payload = {"type": TASK, "appId": "orneos-tasks", "customId": "tasks",
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
