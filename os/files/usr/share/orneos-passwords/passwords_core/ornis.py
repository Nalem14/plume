"""Ornis in Mots de passe: where to start to make the account safer, and how to turn on two-factor
authentication on a given site.

Ornis never sees a password, a username or a note: only the names of the sites and what is wrong with them
(compromised, reused, weak). Each request is a task of the cloud's AI (core:text2text:chat), in the same
24 h allowance as Plume and the top-bar applet. Answers stay in memory for the session, never on disk.
"""
import json
import re
import threading
import time
from urllib.parse import quote

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

import cloud

TASK = "core:text2text:chat"
LANGS = {"fr": "French", "en": "English", "de": "German"}
SYSTEM = ("You are Ornis, the assistant of Orneos, built into Mots de passe, its password manager. You never ask "
          "for and never repeat a password. Answer in light Markdown (short paragraphs, numbered steps, bold for "
          "the buttons to click), no headings, no preamble. Be concrete and brief; when you are not sure how a "
          "site's menus are named today, say where to look rather than inventing.")


def _clean(text):
    text = re.sub(r"(?s)^\s*<think>.*?</think>", "", text or "").strip()
    return re.sub(r"(?s)^```[a-z]*\n(.*)\n```$", r"\1", text).strip()


class Ornis(QObject):
    answered = Signal(int, str, str)
    failed = Signal(int, str, str)
    changed = Signal()
    _done = Signal(int, str, str, str)
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

    @Slot(str, result=str)
    def cached(self, key):
        return self._cache.get(key, "")

    @Slot(str, "QVariantMap", result=int)
    def ask(self, kind, data):
        """kind: "twofa" {site, label} or "plan" {issues: [{site, kinds}]}."""
        data = {k: (v.toVariant() if hasattr(v, "toVariant") else v) for k, v in dict(data).items()}
        self._next += 1
        request = self._next
        key = kind + ":" + json.dumps(data, sort_keys=True)
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
            self._refresh_quota(account)
        threading.Thread(target=run, daemon=True).start()
        return request

    def _prompt(self, kind, data):
        lang = LANGS.get(self._app.lang, "French")
        t = self._app.t
        if kind == "twofa":
            return (f"In {lang}: explain how to turn on two-factor authentication with an authenticator app (TOTP) "
                    f"on the site {data.get('site', '')} ({data.get('label', '')}). Give the path in the site's settings "
                    "in 3 to 6 numbered steps. Then say that when the site shows a QR code, the person clicks "
                    f"**{t['otp_setup']}** in this app and then **{t['otp_scan']}** (or pastes the setup key), and "
                    "types the 6-digit code shown back into the site to finish. End with one line on keeping the "
                    "recovery codes the site gives (for example in the notes of this entry). If the site does not offer "
                    "authenticator codes, say so and suggest what it offers instead.")
        issues = data.get("issues") or []
        lines = "\n".join(f"- {i.get('site') or i.get('label')}: {', '.join(i.get('kinds') or [])}" for i in issues[:40])
        return (f"In {lang}: here is what the security review of a person's passwords found (site: problems; "
                "\"breached\" = the password appeared in a known data leak, \"reused\" = the same password on several "
                "sites, \"weak\" = easy to guess, \"twofa\" = the site offers two-factor authentication and it is not set up "
                "here). Write a short plan: which 3 to 5 sites to fix first and why (e-mail, banks, the accounts that "
                "reset the others come first; a leaked password reused elsewhere is the most urgent), then one line on "
                f"how: open the entry, **{t['change_on_site']}** opens the site's page, and this app suggests a "
                "strong one.\n\n" + lines)

    def _finish(self, request, kind, answer, error):
        if request in self._busy:
            self._busy.discard(request)
            self.changed.emit()
        if error:
            self.failed.emit(request, kind, error)
        else:
            self.answered.emit(request, kind, answer)

    def _run_task(self, account, prompt):
        server, user, password = account
        payload = {"type": TASK, "appId": "orneos-passwords", "customId": "passwords",
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
        deadline, pause = time.time() + 120, 0.5
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
