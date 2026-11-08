"""The cloud's Talk (spreed) API, as Meet uses it: conversations, chat, calls, the signaling settings.

Every call is blocking (urllib, the app password of Orneos Connect): run them off the UI thread. They return
(status, data) like cloud.ocs, data being the `ocs.data` part; status 0 means no network. The Talk version is
read once from the capabilities (`features`), so newer calls are only made when the server has them.
Reference: https://nextcloud-talk.readthedocs.io/en/latest/ (API v4 for conversations and calls, v1 for chat).

Each Talk keeps its cookies: Talk finds the conversation session of a request (joining a call, leaving it) in
the PHP session, not in the request, so the session cookie must follow (the Android app does the same).
"""
import http.cookiejar
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import cloud

BASE = "/ocs/v2.php/apps/spreed/api"

# conversation types (`type`)
ONE_TO_ONE, GROUP, PUBLIC, CHANGELOG, FORMER_ONE_TO_ONE, NOTE_TO_SELF = 1, 2, 3, 4, 5, 6
# call flags (`inCall`, `participantFlags`)
IN_CALL, WITH_AUDIO, WITH_VIDEO, WITH_PHONE = 1, 2, 4, 8
# notification levels
NOTIFY_DEFAULT, NOTIFY_ALWAYS, NOTIFY_MENTION, NOTIFY_NEVER = 0, 1, 2, 3
# participant types
OWNER, MODERATOR, USER, GUEST, USER_SELF_JOINED, GUEST_MODERATOR = 1, 2, 3, 4, 5, 6


def local_zone():
    """This computer's time zone, as an IANA name (Europe/Paris), UTC when unknown."""
    tz = os.environ.get("TZ", "").lstrip(":")
    if "/" in tz:
        return tz
    path = os.path.realpath("/etc/localtime")
    if "zoneinfo/" in path:
        return path.split("zoneinfo/", 1)[1]
    try:                                    # Windows, macOS: Qt knows the IANA name
        from PySide6.QtCore import QTimeZone  # noqa: PLC0415
        key = bytes(QTimeZone.systemTimeZoneId().data()).decode()
    except ImportError:
        key = ""
    return key if "/" in key else "UTC"


class Talk:
    """One account's door to Talk. Cheap to make; holds the capabilities once read."""

    def __init__(self, server, user, password):
        self.server, self.user, self.password = server.rstrip("/"), user, password
        self._features = None
        self._config = {}
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _call(self, url, method="GET", data=None, headers=None, timeout=20):
        hdrs = {"Authorization": cloud.auth_header(self.user, self.password), "User-Agent": "Orneos Meet",
                "OCS-APIRequest": "true", "Accept": "application/json"}
        hdrs.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with self._opener.open(req, timeout=timeout) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
        except (urllib.error.URLError, OSError, TimeoutError):
            return 0, b""

    # ---- plumbing ----------------------------------------------------------------------------------------
    def _req(self, method, path, body=None, query=None, timeout=20, headers=None):
        url = self.server + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
        data = None
        hdrs = dict(headers or {})
        if body is not None:
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
        status, raw = self._call(url, method, data, hdrs, timeout=timeout)
        parsed = cloud._parse(raw)
        ocs = parsed.get("ocs") if isinstance(parsed, dict) else None
        if isinstance(ocs, dict):
            return status, ocs.get("data")
        return status, parsed

    def get(self, path, **query):
        return self._req("GET", path, query=query)

    # ---- capabilities ------------------------------------------------------------------------------------
    def features(self):
        """The `spreed` features of the server (a set), read once. Empty when offline."""
        if self._features is None:
            status, data = self._req("GET", "/ocs/v2.php/cloud/capabilities")
            spreed = ((data or {}).get("capabilities") or {}).get("spreed") or {}
            if status == 200:
                self._features = set(spreed.get("features") or [])
                self._config = spreed.get("config") or {}
            else:
                return set()
        return self._features

    def has(self, feature):
        return feature in self.features()

    def config(self, section, key, default=None):
        self.features()
        return (self._config.get(section) or {}).get(key, default)

    # ---- presence ----------------------------------------------------------------------------------------
    def heartbeat(self, status):
        """Tell the cloud we are here (« online ») or the window is behind (« away »), like Talk web every
        5 min: without it the cloud shows us offline 15 min after our last one. A status chosen by hand stays."""
        return self._req("PUT", "/ocs/v2.php/apps/user_status/api/v1/heartbeat", {"status": status})

    def my_status(self):
        return self._req("GET", "/ocs/v2.php/apps/user_status/api/v1/user_status")

    def set_status(self, status):
        """online, away, dnd, busy or invisible: chosen by hand, the heartbeat no longer changes it."""
        return self._req("PUT", "/ocs/v2.php/apps/user_status/api/v1/user_status/status", {"statusType": status})

    def set_status_message(self, icon, message, clear_at=None):
        """A message with its emoji (clear_at: a Unix time, or None to keep it); both empty: none."""
        if not icon and not message:
            return self._req("DELETE", "/ocs/v2.php/apps/user_status/api/v1/user_status/message")
        return self._req("PUT", "/ocs/v2.php/apps/user_status/api/v1/user_status/message/custom",
                         {"statusIcon": icon or None, "message": message or None, "clearAt": clear_at})

    # ---- conversations -----------------------------------------------------------------------------------
    def rooms(self, modified_since=0):
        """All conversations of the account (with `includeStatus`: the presence of one-to-one partners)."""
        return self._req("GET", f"{BASE}/v4/room", query={"includeStatus": "true",
                                                          "modifiedSince": modified_since or None})

    def room(self, token):
        return self._req("GET", f"{BASE}/v4/room/{token}")

    def create_room(self, room_type, name="", invite="", source="users", obj_type=None, obj_id=None):
        """A one-to-one (invite = the user id), a group or a public conversation."""
        body = {"roomType": room_type, "roomName": name}
        if invite:
            body["invite"] = invite
            body["source"] = source
        if obj_type:
            body["objectType"], body["objectId"] = obj_type, obj_id
        return self._req("POST", f"{BASE}/v4/room", body)

    def rename(self, token, name):
        return self._req("PUT", f"{BASE}/v4/room/{token}", {"roomName": name})

    def set_description(self, token, text):
        return self._req("PUT", f"{BASE}/v4/room/{token}/description", {"description": text})

    def delete_room(self, token):
        return self._req("DELETE", f"{BASE}/v4/room/{token}")

    def leave_room(self, token):
        """Leave the conversation for good (not the same as leaving the chat view)."""
        return self._req("DELETE", f"{BASE}/v4/room/{token}/participants/self")

    def favorite(self, token, on):
        return self._req("POST" if on else "DELETE", f"{BASE}/v4/room/{token}/favorite")

    def archive(self, token, on):
        return self._req("POST" if on else "DELETE", f"{BASE}/v4/room/{token}/archive")

    def notify_level(self, token, level):
        return self._req("POST", f"{BASE}/v4/room/{token}/notify", {"level": level})

    def notify_calls(self, token, on):
        return self._req("POST", f"{BASE}/v4/room/{token}/notify-calls", {"level": 1 if on else 0})

    def make_public(self, token, on):
        return self._req("POST" if on else "DELETE", f"{BASE}/v4/room/{token}/public")

    def set_password(self, token, password):
        return self._req("PUT", f"{BASE}/v4/room/{token}/password", {"password": password})

    def set_lobby(self, token, on, timer=0):
        body = {"state": 1 if on else 0}
        if timer:
            body["timer"] = int(timer)
        return self._req("PUT", f"{BASE}/v4/room/{token}/webinar/lobby", body)

    def set_read_only(self, token, on):
        return self._req("PUT", f"{BASE}/v4/room/{token}/read-only", {"state": 1 if on else 0})

    def set_permissions(self, token, mode, permissions):
        """mode: "default" | "call"; permissions: the bit field of the API."""
        return self._req("PUT", f"{BASE}/v4/room/{token}/permissions/{mode}", {"permissions": permissions})

    def set_message_expiration(self, token, seconds):
        return self._req("POST", f"{BASE}/v4/room/{token}/message-expiration", {"seconds": int(seconds)})

    def set_listable(self, token, scope):
        """Who finds it without an invitation: 0 nobody, 1 the accounts of the cloud, 2 them and the guests app."""
        return self._req("PUT", f"{BASE}/v4/room/{token}/listable", {"scope": int(scope)})

    def set_mention_permissions(self, token, moderators_only):
        return self._req("PUT", f"{BASE}/v4/room/{token}/mention-permissions",
                         {"mentionPermissions": 1 if moderators_only else 0})

    def set_attendee_permissions(self, token, attendee_id, method, permissions):
        """method: set | add | remove (one person: what the conversation's permissions give no longer counts)."""
        return self._req("PUT", f"{BASE}/v4/room/{token}/attendees/permissions",
                         {"attendeeId": attendee_id, "method": method, "permissions": int(permissions)})

    def set_important(self, token, on):
        """Notified even in « Ne pas déranger »."""
        return self._req("POST" if on else "DELETE", f"{BASE}/v4/room/{token}/important")

    def set_sensitive(self, token, on):
        """No last message in the list, no text in the notifications."""
        return self._req("POST" if on else "DELETE", f"{BASE}/v4/room/{token}/sensitive")

    def preserve(self, token, on):
        """Owners: never cleared by the retention of meetings (event, instant meeting)."""
        return self._req("POST" if on else "DELETE", f"{BASE}/v4/room/{token}/preserve")

    def clear_history(self, token):
        """Every message of the conversation, for everyone (moderators)."""
        return self._req("DELETE", f"{BASE}/v1/chat/{token}")

    def avatar_emoji(self, token, emoji, color=None):
        return self._req("POST", f"{BASE}/v1/room/{token}/avatar/emoji", {"emoji": emoji, "color": color})

    def delete_avatar(self, token):
        return self._req("DELETE", f"{BASE}/v1/room/{token}/avatar")

    def _upload(self, path, local, fields=None):
        """A multipart POST of one file (field `file`): a picture, a CSV."""
        boundary = "orneos" + os.urandom(12).hex()
        name = os.path.basename(local)
        with open(local, "rb") as f:
            content = f.read()
        mime = "text/csv" if name.lower().endswith(".csv") else \
            "image/png" if name.lower().endswith(".png") else "image/jpeg"
        parts = []
        for key, value in (fields or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                     f'Content-Type: {mime}\r\n\r\n'.encode() + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        status, raw = self._call(self.server + path, "POST", b"".join(parts),
                                 {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=60)
        parsed = cloud._parse(raw)
        ocs = parsed.get("ocs") if isinstance(parsed, dict) else None
        return status, ocs.get("data") if isinstance(ocs, dict) else parsed

    def upload_avatar(self, token, local):
        return self._upload(f"{BASE}/v1/room/{token}/avatar", local)

    def import_emails(self, token, local, test_run=False):
        """A CSV of addresses (columns email, name): each one invited by e-mail. test_run: only counted."""
        return self._upload(f"{BASE}/v4/room/{token}/import-emails", local, {"testRun": "true" if test_run else "false"})

    def resend_invitations(self, token, attendee_id=None):
        """The e-mail invitations again: one person, or every one invited by e-mail."""
        return self._req("POST", f"{BASE}/v4/room/{token}/participants/resend-invitations",
                         {"attendeeId": attendee_id} if attendee_id else {})

    # ---- tags (the account's own, Talk 22+: `conversation-tags`) ------------------------------------------
    def tags(self):
        status, data = self._req("GET", f"{BASE}/v4/tags")
        return status, data if isinstance(data, list) else []

    def create_tag(self, name):
        return self._req("POST", f"{BASE}/v4/tags", {"name": name})

    def rename_tag(self, tag_id, name):
        return self._req("PUT", f"{BASE}/v4/tags/{tag_id}", {"name": name})

    def delete_tag(self, tag_id):
        return self._req("DELETE", f"{BASE}/v4/tags/{tag_id}")

    def set_room_tags(self, token, tag_ids):
        return self._req("POST", f"{BASE}/v4/room/{token}/tags", {"tagIds": [str(t) for t in tag_ids]})

    # ---- bots --------------------------------------------------------------------------------------------
    def bots(self, token):
        """The bots a moderator can turn on here (state 0 off, 1 on, 2 always on)."""
        status, data = self._req("GET", f"{BASE}/v1/bot/{token}")
        return status, data if isinstance(data, list) else []

    def set_bot(self, token, bot_id, on):
        return self._req("POST" if on else "DELETE", f"{BASE}/v1/bot/{token}/{int(bot_id)}")

    def mark_read(self, token, last_id=None):
        body = {"lastReadMessage": last_id} if last_id else {}
        return self._req("POST", f"{BASE}/v1/chat/{token}/read", body)

    def mark_unread(self, token):
        return self._req("DELETE", f"{BASE}/v1/chat/{token}/read")

    # ---- participants ------------------------------------------------------------------------------------
    def participants(self, token):
        return self._req("GET", f"{BASE}/v4/room/{token}/participants", query={"includeStatus": "true"})

    def add_participant(self, token, new, source="users"):
        """source: users | groups | circles (teams) | emails | federated_users"""
        return self._req("POST", f"{BASE}/v4/room/{token}/participants", {"newParticipant": new, "source": source})

    def remove_participant(self, token, attendee_id):
        return self._req("DELETE", f"{BASE}/v4/room/{token}/attendees", {"attendeeId": attendee_id})

    def set_moderator(self, token, attendee_id, on, owner=False):
        """on: moderator (owner=True: owner, Talk 22+ `promote-demote-owner`); off: back to a participant."""
        body = {"attendeeId": attendee_id}
        if on and owner:
            body["participantType"] = OWNER
        return self._req("POST" if on else "DELETE", f"{BASE}/v4/room/{token}/moderators", body)

    def ban(self, token, actor_type, actor_id, note=""):
        """Moderators: out of the conversation, and cannot come back (Talk 20+: `ban-v1`)."""
        return self._req("POST", f"{BASE}/v1/ban/{token}",
                         {"actorType": actor_type, "actorId": actor_id, "internalNote": note})

    def bans(self, token):
        status, data = self._req("GET", f"{BASE}/v1/ban/{token}")
        return status, data if isinstance(data, list) else []

    def unban(self, token, ban_id):
        return self._req("DELETE", f"{BASE}/v1/ban/{token}/{int(ban_id)}")

    def join(self, token, password="", force=True):
        """Enter the conversation (a Nextcloud session, needed for the signaling and the call): data.sessionId."""
        body = {"force": force}
        if password:
            body["password"] = password
        return self._req("POST", f"{BASE}/v4/room/{token}/participants/active", body)

    def leave(self, token):
        return self._req("DELETE", f"{BASE}/v4/room/{token}/participants/active")

    def autocomplete(self, search, item_type="", item_id="", limit=12):
        """People to invite: accounts of the cloud, groups, teams, emails (core autocomplete, like Talk)."""
        shares = ["0", "1", "4", "7"]   # user, group, email, team
        return self._req("GET", "/ocs/v2.php/core/autocomplete/get",
                         query={"search": search, "itemType": item_type or "call", "itemId": item_id or "new",
                                "shareTypes[]": shares, "limit": limit})

    # ---- chat --------------------------------------------------------------------------------------------
    def messages(self, token, last_known=0, future=False, limit=100, timeout=30, include_last=False, thread=0):
        """History (future=False: older than last_known) or the long poll for new messages (future=True).

        The long poll answers 304 after `timeout` seconds without anything new."""
        query = {"lookIntoFuture": 1 if future else 0, "limit": limit, "setReadMarker": 0,
                 "includeLastKnown": 1 if include_last else 0}
        if last_known:
            query["lastKnownMessageId"] = last_known
        if future:
            query["timeout"] = timeout
        if thread:
            query["threadId"] = int(thread)
        status, data = self._req("GET", f"{BASE}/v1/chat/{token}", query=query,
                                 timeout=(timeout + 15) if future else 25)
        return status, data if isinstance(data, list) else []

    def context(self, token, message_id, limit=50):
        """The messages around one (a search result, a link to a message)."""
        return self._req("GET", f"{BASE}/v1/chat/{token}/{message_id}/context", query={"limit": limit})

    def send(self, token, text, reply_to=0, silent=False, reference_id="", thread_title="", thread=0):
        body = {"message": text, "actorDisplayName": "", "silent": silent}
        if reply_to:
            body["replyTo"] = reply_to
        elif thread:
            body["threadId"] = int(thread)
        if reference_id:
            body["referenceId"] = reference_id
        if thread_title:
            body["threadTitle"] = thread_title
        return self._req("POST", f"{BASE}/v1/chat/{token}", body)

    def edit(self, token, message_id, text):
        return self._req("PUT", f"{BASE}/v1/chat/{token}/{message_id}", {"message": text})

    def delete_message(self, token, message_id):
        return self._req("DELETE", f"{BASE}/v1/chat/{token}/{message_id}")

    def react(self, token, message_id, emoji, on=True):
        return self._req("POST" if on else "DELETE", f"{BASE}/v1/reaction/{token}/{message_id}",
                         {"reaction": emoji})

    def reactions(self, token, message_id):
        return self._req("GET", f"{BASE}/v1/reaction/{token}/{message_id}")

    def schedule(self, token, text, send_at, reply_to=0, silent=False):
        """A message sent later by the server (`scheduled-messages`)."""
        body = {"message": text, "sendAt": int(send_at), "silent": bool(silent)}
        if reply_to:
            body["replyTo"] = reply_to
        return self._req("POST", f"{BASE}/v1/chat/{token}/schedule", body)

    def scheduled(self, token):
        status, data = self._req("GET", f"{BASE}/v1/chat/{token}/schedule")
        return status, data if isinstance(data, list) else []

    def edit_scheduled(self, token, message_id, text, send_at, silent=False):
        return self._req("POST", f"{BASE}/v1/chat/{token}/schedule/{message_id}",
                         {"message": text, "sendAt": int(send_at), "silent": bool(silent)})

    def delete_scheduled(self, token, message_id):
        return self._req("DELETE", f"{BASE}/v1/chat/{token}/schedule/{message_id}")

    def upcoming_reminders(self):
        status, data = self._req("GET", f"{BASE}/v1/chat/upcoming-reminders")
        return status, data if isinstance(data, list) else []

    # ---- pinned messages, threads (Talk 25) ----------------------------------------------------------------
    def pin(self, token, message_id, on=True, until=0):
        if on:
            return self._req("POST", f"{BASE}/v1/chat/{token}/{message_id}/pin", {"pinUntil": int(until)} if until else {})
        return self._req("DELETE", f"{BASE}/v1/chat/{token}/{message_id}/pin")

    def hide_pin(self, token, message_id):
        """Hide the pinned message for oneself only."""
        return self._req("DELETE", f"{BASE}/v1/chat/{token}/{message_id}/pin/self")

    def threads(self, token, limit=50):
        status, data = self._req("GET", f"{BASE}/v1/chat/{token}/threads/recent", query={"limit": limit})
        return status, data if isinstance(data, list) else []

    def subscribed_threads(self, limit=100):
        """The threads followed in every conversation (Talk 25, « Fils de discussion » of Talk web)."""
        status, data = self._req("GET", f"{BASE}/v1/chat/subscribed-threads", query={"limit": limit})
        return status, data if isinstance(data, list) else []

    def remind(self, token, message_id, timestamp, on=True):
        if on:
            return self._req("POST", f"{BASE}/v1/chat/{token}/{message_id}/reminder", {"timestamp": int(timestamp)})
        return self._req("DELETE", f"{BASE}/v1/chat/{token}/{message_id}/reminder")

    def share_file(self, token, path, reply_to=0, caption="", meta=None):
        """Share a file of the cloud into the conversation (a share of type 10, like Talk)."""
        meta = dict({"messageType": "comment"}, **(meta or {}))
        if caption:
            meta["caption"] = caption
        if reply_to:
            meta["replyTo"] = reply_to
        body = {"shareType": 10, "shareWith": token, "path": path, "talkMetaData": json.dumps(meta)}
        return self._req("POST", "/ocs/v2.php/apps/files_sharing/api/v1/shares", body)

    def shared_items(self, token, item_type="", limit=50):
        if item_type:
            return self._req("GET", f"{BASE}/v1/chat/{token}/share", query={"objectType": item_type, "limit": limit})
        return self._req("GET", f"{BASE}/v1/chat/{token}/share/overview", query={"limit": min(limit, 20)})

    def search(self, token, term, limit=25):
        """Messages of one conversation (the unified search's `talk-message-current` provider)."""
        status, data = self._req("GET", "/ocs/v2.php/search/providers/talk-message-current/search",
                                 query={"term": term, "limit": limit, "from": f"/call/{token}"})
        return status, (data or {}).get("entries") or []

    def typing(self, token, on):
        """Typing is relayed by the signaling (HPB) only: kept here for the internal signaling (no-op)."""
        return 0, None

    # ---- polls -------------------------------------------------------------------------------------------
    def create_poll(self, token, question, options, multiple=False, anonymous=False):
        return self._req("POST", f"{BASE}/v1/poll/{token}", {
            "question": question, "options": list(options), "resultMode": 1 if anonymous else 0,
            "maxVotes": 0 if multiple else 1})

    def poll(self, token, poll_id):
        return self._req("GET", f"{BASE}/v1/poll/{token}/{poll_id}")

    def vote(self, token, poll_id, option_ids):
        return self._req("POST", f"{BASE}/v1/poll/{token}/{poll_id}", {"optionIds": list(option_ids)})

    def close_poll(self, token, poll_id):
        return self._req("DELETE", f"{BASE}/v1/poll/{token}/{poll_id}")

    # ---- calls -------------------------------------------------------------------------------------------
    def signaling_settings(self, token):
        """Where and how to reach the signaling server (HPB), the STUN/TURN servers and the hello ticket."""
        return self._req("GET", f"{BASE}/v3/signaling/settings", query={"token": token})

    def join_call(self, token, flags=IN_CALL | WITH_AUDIO | WITH_VIDEO, silent=False):
        return self._req("POST", f"{BASE}/v4/call/{token}", {"flags": flags, "silent": silent})

    def update_call(self, token, flags):
        return self._req("PUT", f"{BASE}/v4/call/{token}", {"flags": flags})

    def leave_call(self, token, for_all=False):
        return self._req("DELETE", f"{BASE}/v4/call/{token}", {"all": for_all} if for_all else None)

    def ring_attendee(self, token, attendee_id):
        """Ring one participant again (`send-call-notification`)."""
        return self._req("POST", f"{BASE}/v4/call/{token}/ring/{attendee_id}")

    def call_peers(self, token):
        return self._req("GET", f"{BASE}/v4/call/{token}")

    # ---- breakout rooms ----------------------------------------------------------------------------------
    # mode: 1 automatic (Talk shares the people out), 2 manual (attendeeMap), 3 free (each one chooses)
    def breakout_rooms(self, token):
        status, data = self._req("GET", f"{BASE}/v4/room/{token}/breakout-rooms")
        return status, data if isinstance(data, list) else []

    def breakout_participants(self, token):
        return self._req("GET", f"{BASE}/v4/room/{token}/breakout-rooms/participants")

    def configure_breakout(self, token, mode, amount, attendee_map=None):
        body = {"mode": int(mode), "amount": int(amount)}
        if attendee_map:
            body["attendeeMap"] = json.dumps({str(k): int(v) for k, v in attendee_map.items()})
        return self._req("POST", f"{BASE}/v1/breakout-rooms/{token}", body)

    def remove_breakout(self, token):
        return self._req("DELETE", f"{BASE}/v1/breakout-rooms/{token}")

    def start_breakout(self, token, on=True):
        return self._req("POST" if on else "DELETE", f"{BASE}/v1/breakout-rooms/{token}/rooms")

    def broadcast(self, token, text):
        return self._req("POST", f"{BASE}/v1/breakout-rooms/{token}/broadcast", {"message": text})

    def ask_assistance(self, token, on=True):
        return self._req("POST" if on else "DELETE", f"{BASE}/v1/breakout-rooms/{token}/request-assistance")

    def switch_breakout(self, token, target):
        return self._req("POST", f"{BASE}/v1/breakout-rooms/{token}/switch", {"target": target})

    # ---- the calendar (Talk 21+) -------------------------------------------------------------------------
    def upcoming_events(self):
        """The meetings of the next days that have a conversation (dashboard events)."""
        status, data = self._req("GET", f"{BASE}/v4/dashboard/events")
        return status, data if isinstance(data, list) else []

    def schedule_meeting(self, token, calendar, start, end=0, title="", description="", attendees=None):
        """An event in the calendar `calendar` (its last URI part) for this conversation; everyone invited."""
        body = {"calendarUri": calendar, "start": int(start)}
        if end:
            body["end"] = int(end)
        if title:
            body["title"] = title
        if description:
            body["description"] = description
        if attendees is not None:
            body["attendeeIds"] = list(attendees)
        status, data = self._req("POST", f"{BASE}/v4/room/{token}/meeting", body)
        # Talk 25 fails (500) for an account with no time zone yet (never signed in to the cloud in a browser:
        # Talk does new DateTimeZone(null)). Nextcloud then reads the calendar's: give it this computer's, once.
        if status == 500 and self._calendar_timezone(calendar):
            status, data = self._req("POST", f"{BASE}/v4/room/{token}/meeting", body)
        return status, data

    def _calendar_timezone(self, calendar):
        """Set the calendar's time zone when it has none. True when it was set."""
        url = f"{self.server}/remote.php/dav/calendars/{urllib.parse.quote(self.user)}/{urllib.parse.quote(calendar)}/"
        ask = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
               '<d:prop><c:calendar-timezone/></d:prop></d:propfind>')
        status, raw = self._call(url, "PROPFIND", ask.encode(), {"Depth": "0", "Content-Type": "application/xml"})
        if status != 207 or b"BEGIN:VTIMEZONE" in raw:
            return False
        zone = local_zone()
        vtimezone = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Orneos//Meet//EN\r\nBEGIN:VTIMEZONE\r\n"
                     f"TZID:{zone}\r\nEND:VTIMEZONE\r\nEND:VCALENDAR\r\n")
        body = ('<?xml version="1.0"?><d:propertyupdate xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
                f'<d:set><d:prop><c:calendar-timezone><![CDATA[{vtimezone}]]></c:calendar-timezone></d:prop></d:set>'
                '</d:propertyupdate>')
        status, _ = self._call(url, "PROPPATCH", body.encode(), {"Content-Type": "application/xml"})
        return status == 207

    # ---- avatars -----------------------------------------------------------------------------------------
    def avatar(self, token, dark=False):
        """The picture of a conversation (bytes), as the cloud draws it."""
        url = f"{self.server}{BASE}/v1/room/{token}/avatar" + ("/dark" if dark else "")
        return self._call(url, headers={"Accept": "image/*"})

    def user_avatar(self, user_id, size=128, dark=False):
        url = f"{self.server}/index.php/avatar/{urllib.parse.quote(user_id)}/{size}" + ("/dark" if dark else "")
        return self._call(url, headers={"Accept": "image/*"})
