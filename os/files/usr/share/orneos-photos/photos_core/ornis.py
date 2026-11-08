"""Ornis in Photos: a search in plain words (« Inès à Biarritz l'été dernier ») turned into filters, and titles
for the memories.

Ornis reads text only: it never sees a photo. For a search it gets the sentence and the names the library
knows (people, places, themes, albums); for titles, the dates, the number of photos and the place of each
memory. Each request is a task of the cloud's AI (core:text2text:chat), in the same 24 h allowance as the
other apps. Nothing is sent before the person asks, and each task is deleted from the cloud once read.
"""
import json
import re
import threading
import time
from datetime import date
from urllib.parse import quote

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

import cloud
from photos_core.api import Api, ApiError

TASK = "core:text2text:chat"
LANGS = {"fr": "French", "en": "English", "de": "German"}
SYSTEM = ("You are Ornis, the assistant of Orneos, built into Photos, its photo library. You only ever read "
          "text about the photos (names, dates, places), never the photos. Answer with JSON only, no comment.")


def _unthink(text):
    return re.sub(r"(?s)^\s*<think>.*?</think>", "", text or "").strip()


def first_json(text, opener):
    text = re.sub(r"(?s)```(?:json)?(.*?)```", r"\1", _unthink(text))
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == opener:
            try:
                value = decoder.raw_decode(text, i)[0]
            except json.JSONDecodeError:
                continue
            return value
    return None


def clean_plan(value, known):
    """Only what the library knows survives (a name Ornis made up is dropped)."""
    plan = value if isinstance(value, dict) else {}
    out = {}
    for key in ("people", "places", "tags", "albums"):
        names = {n.lower(): n for n in known.get(key, [])}
        out[key] = [names[str(v).lower()] for v in (plan.get(key) or []) if str(v).lower() in names][:2]
    for key in ("from", "to"):
        text = str(plan.get(key) or "")[:10]
        try:
            out[key] = date.fromisoformat(text).isoformat() if text else ""
        except ValueError:
            out[key] = ""
    out["favorites"] = bool(plan.get("favorites"))
    out["videos"] = bool(plan.get("videos"))
    return out


class Ornis(QObject):
    planned = Signal(str, "QVariantMap")      # the sentence, the filters
    titled = Signal("QVariantMap")            # memory key → title
    failed = Signal(str, str)                 # kind, message
    changed = Signal()
    _done = Signal(str, object, str, str)
    _quotaRead = Signal(object)

    def __init__(self, app, library):
        super().__init__()
        self._app = app
        self._library = library
        self._busy = set()
        self._quota = None
        self._done.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        self._quotaRead.connect(self._set_quota)

    @Property(bool, notify=changed)
    def busy(self):
        return bool(self._busy)

    @Property(bool, notify=changed)
    def titling(self):
        return "titles" in self._busy

    @Property("QVariantMap", notify=changed)
    def quota(self):
        return self._quota or {}

    @Slot(str)
    def search(self, sentence):
        sentence = " ".join(str(sentence).split())
        account = self._app.account()
        if not sentence:
            return
        if account is None:
            self._done.emit("search", None, self._app.t["ornis_offline"], sentence)
            return
        known = self._library.search_context()
        lang = LANGS.get(self._app.lang, "French")
        prompt = ("Turn this search of a photo library into search filters. Today is "
                  f"{date.today().isoformat()} ({date.today().strftime('%A')}). The person writes in {lang}.\n"
                  "Answer with one JSON object only: {\"from\": \"YYYY-MM-DD\" or \"\", \"to\": \"YYYY-MM-DD\" or \"\", "
                  "\"people\": [], \"places\": [], \"tags\": [], \"albums\": [], \"favorites\": false, \"videos\": false}. "
                  "Use only names from these lists, written exactly as here; tags are in English (Beach, Cat, Mountains…), "
                  "pick the tag that means what the person asks. A season or a month without a year means the last one "
                  "that has passed. Leave out what the sentence does not ask.\n"
                  f"People: {json.dumps(known['people'], ensure_ascii=False)}\n"
                  f"Places: {json.dumps(known['places'], ensure_ascii=False)}\n"
                  f"Tags: {json.dumps(known['tags'], ensure_ascii=False)}\n"
                  f"Albums: {json.dumps(known['albums'], ensure_ascii=False)}\n\n"
                  f"Search: {sentence}")
        self._start("search", account, prompt, sentence, known)

    @Slot()
    def titleMemories(self):
        facts = self._library.memory_facts()
        account = self._app.account()
        if not facts or account is None or "titles" in self._busy:
            return
        lang = LANGS.get(self._app.lang, "French")

        def run():
            api = Api(account)
            try:
                for fact in facts[:12]:
                    try:
                        info = api.info(fact["cover"])
                    except ApiError:
                        info = {}
                    fact["place"] = str(info.get("address_short") or "")
                    fact.pop("cover", None)
            finally:
                api.close()
            prompt = (f"Give each of these memories of a photo library a short, warm title in {lang} (2 to 5 words, "
                      "like « Week-end à Biarritz » or « Fin d'été en famille »), from their dates, place and number of "
                      "photos only. Never invent a person or an event. Answer with a JSON array only: "
                      '[{"key": "…", "title": "…"}].\n\n' + json.dumps(facts, ensure_ascii=False))
            self._run("titles", account, prompt, "", {})
        self._busy.add("titles")
        self.changed.emit()
        threading.Thread(target=run, daemon=True).start()

    def _start(self, kind, account, prompt, sentence, known):
        self._busy.add(kind)
        self.changed.emit()
        threading.Thread(target=self._run, args=(kind, account, prompt, sentence, known), daemon=True).start()

    def _run(self, kind, account, prompt, sentence, known):
        answer, error = self._task(account, prompt)
        result = None
        if not error:
            if kind == "search":
                value = first_json(answer, "{")
                result = clean_plan(value, known) if isinstance(value, dict) else None
            else:
                value = first_json(answer, "[")
                if isinstance(value, list):
                    result = {str(i.get("key")): str(i.get("title") or "").strip()[:60]
                              for i in value if isinstance(i, dict) and i.get("key")}
            if result is None:
                error = "failed"
        message = "" if not error else self._app.t["ornis_quota" if error == "quota" else
                                                     "ornis_offline" if error == "offline" else "ornis_failed"]
        self._done.emit(kind, result, message, sentence)
        self._refresh_quota(account)

    def _finish(self, kind, result, error, sentence):
        self._busy.discard(kind)
        self.changed.emit()
        if error:
            self.failed.emit(kind, error)
        elif kind == "search":
            plan = dict(result)
            plan.update(query=sentence, ornis=True)
            self.planned.emit(sentence, plan)
        else:
            self.titled.emit(result)

    def _task(self, account, prompt):
        server, user, password = account
        payload = {"type": TASK, "appId": "orneos-photos", "customId": "photos",
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
            return self._wait(account, path)
        finally:
            cloud.ocs(server, user, password, path, method="DELETE")      # nothing of it kept in the cloud

    @staticmethod
    def _wait(account, path):
        server, user, password = account
        deadline, pause = time.time() + 90, 0.4
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
                return _unthink(str(out.get("output") or out.get("text") or "")), ""
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
