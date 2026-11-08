"""What Ornis's tools are, for people: the tool names of the agent (ornis/agent, upstream context_agent and the
Orneos overlay) by family, each with its words (strings.py tool_*) and its icon (components/icons.js).

The arguments of an action to confirm come with their raw names: ARGS gives the word to show, HIDDEN the ones
that mean nothing to a person (ids, tokens)."""
import json
import re

FAMILIES = {
    "agenda": ("calendar", ("list_calendars", "schedule_event", "find_free_time_slot_in_calendar", "search_calendar_events")),
    "tasks": ("done", ("add_task", "list_tasks", "complete_task", "update_task", "delete_task")),
    "mail": ("mail", ("send_email", "save_mail_draft", "get_mail_account_list", "get_mail_folder_list", "list_mails")),
    "contacts": ("contacts", ("find_person_in_users", "find_person_in_contacts", "find_details_of_current_user")),
    "files": ("folder", ("get_file_content", "get_file_content_by_file_link", "get_file_tree", "get_folder_tree", "upload_file",
                         "create_folder", "move_file", "copy_file", "get_file_id_by_path", "get_file_path_by_id",
                         "convert_file", "delete_file")),
    "shares": ("share", ("create_public_sharing_link", "list_shares", "share_with_user", "share_with_group",
                         "update_share_permissions", "delete_share", "list_user_groups", "get_share_info")),
    "meet": ("video", ("list_talk_conversations", "create_public_conversation", "send_message_to_conversation", "send_direct_message",
                       "list_messages_in_conversation", "add_reaction", "remove_reaction", "list_reactions", "reply_to_message",
                       "create_poll", "get_poll", "vote_on_poll", "close_poll", "share_file_to_conversation",
                       "list_shared_items", "list_shared_items_overview")),
    "notes": ("note", ("list_notes", "read_note", "create_note", "append_to_note", "replace_note_text")),
    "deck": ("checklist", ("list_boards", "list_board_cards", "add_card", "add_card_label", "assign_card_to_user", "delete_card",
                           "list_card_comments", "add_card_comment", "update_card_comment", "delete_card_comment")),
    "bookmarks": ("star", ("list_bookmarks", "search_bookmarks", "create_bookmark", "update_bookmark", "delete_bookmark",
                           "list_bookmark_folders", "create_bookmark_folder", "list_bookmark_tags")),
    "web": ("globe", ("web_search", "read_web_page", "research_search", "research_read")),
    "account": ("user", ("get_orneos_account", "add_mail_alias", "remove_mail_alias")),
    "weather": ("sun", ("get_current_weather_for_coordinates",)),
    "maps": ("location", ("get_coordinates_for_address", "get_osm_route", "get_osm_link")),
    "memory": ("history", ("list_memory_tree", "load_memory", "store_memory", "delete_memory", "delete_memory_folder",
                           "search_memories", "load_skill", "store_skill")),
    "computer": ("devices", ("computer_status", "computer_open", "computer_volume", "computer_brightness", "computer_appearance",
                             "computer_copy_to_clipboard", "computer_timer", "computer_lock", "computer_power",
                             "computer_find_files", "computer_grep_files", "computer_move_files", "computer_create_folder",
                             "computer_find_app", "computer_install_app", "computer_remove_app", "computer_run_command",
                             "computer_command_status", "computer_open_terminal", "computer_list_folder",
                             "computer_read_file", "computer_write_file", "computer_edit_file", "computer_trash_files",
                             "computer_processes", "computer_quit_app", "computer_setting", "computer_screenshot",
                             "computer_extensions", "computer_skill_read", "computer_mcp_tools", "computer_mcp_call")),
    "scheduled": ("repeat", ("create_scheduled_task", "list_scheduled_tasks", "update_scheduled_task", "delete_scheduled_task")),
    "work": ("sparkle", ("work_progress", "work_write_file")),
    "ask": ("chat", ("ask_user",)),
}
FAMILY_OF = {tool: family for family, (_icon, tools) in FAMILIES.items() for tool in tools}

ARGS = {
    "subject": "subject", "body": "body", "to_emails": "to", "to": "to", "from_email": "from", "title": "title",
    "content": "content", "text": "content", "category": "category", "local_part": "address", "description": "description",
    "location": "location", "start_date": "start", "start_time": "start", "start": "start", "end_date": "end",
    "end_time": "end", "end": "end", "attendees": "people", "message": "message", "prompt": "prompt",
    "recurrence_rule": "repeat", "starts_at": "when", "due_date": "due", "name": "name", "summary": "title",
    "path": "path", "file_path": "path", "source_path": "path", "destination_path": "destination", "share_with": "with",
    "user_id": "with", "user": "with", "group": "with", "url": "address",
}
# the order a person reads an action in: who, then what, then when and where
ORDER = ("to", "with", "people", "from", "title", "subject", "name", "start", "end", "when", "due", "repeat", "location",
         "address", "path", "destination", "category", "body", "content", "message", "description", "prompt")
LONG = {"body", "content", "text", "message", "description", "prompt"}      # changed in a box of several lines
HIDDEN = re.compile(r"(^|_)(id|ids|token|uri|calendar_name|account_id|folder_id)$")


def family(tool):
    if tool in FAMILY_OF:
        return FAMILY_OF[tool]
    if tool.startswith("search_"):          # one tool per unified search provider of the cloud
        return "cloud"
    if tool.startswith("mcp_"):
        return "cloud"
    return "cloud"


def icon(tool):
    fam = family(tool)
    return FAMILIES[fam][0] if fam in FAMILIES else "search"


def families(tools, t):
    """The words for the tools a reply used, in order, each family once: [{key, label, icon}]."""
    out, seen = [], set()
    for tool in tools or []:
        fam = family(tool)
        if fam in seen:
            continue
        seen.add(fam)
        out.append({"key": fam, "label": t.get("tool_" + fam, fam), "icon": FAMILIES[fam][0] if fam in FAMILIES else "search"})
    return out


def step_rows(steps, t):
    """The steps of an answer as shown: [{icon, label, detail}], the family's words, capitalised."""
    rows = []
    for step in steps or []:
        fam = family(step.get("tool") or "")
        label = t.get("tool_" + fam, fam) if fam in FAMILIES else t.get("tool_other", fam)
        rows.append({"icon": FAMILIES[fam][0] if fam in FAMILIES else "search", "label": label[:1].upper() + label[1:],
                     "detail": step.get("detail") or ""})
    return rows


def _value(value):
    if isinstance(value, list):
        return ", ".join(_value(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "✓" if value else "✗"
    return str(value)


def questions(raw):
    """The questions of ask_user as the form shows them: [{question, header, multi, options: [{label, description}]}]."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = []
    out = []
    for q in raw if isinstance(raw, list) else []:
        if not isinstance(q, dict) or not str(q.get("question") or "").strip():
            continue
        options = []
        for o in q.get("options") or []:
            label = str((o.get("label") if isinstance(o, dict) else o) or "").strip()
            if label and label.lower() not in ("autre", "other", "andere", "sonstiges") and len(options) < 6:
                options.append({"label": label[:120],
                                "description": str(o.get("description") or "").strip()[:300] if isinstance(o, dict) else ""})
        out.append({"question": str(q["question"]).strip()[:500], "header": str(q.get("header") or "").strip()[:24],
                    "multi": bool(q.get("multiSelect") or q.get("multi_select") or q.get("multiple")), "options": options})
    return out[:4]


def action(item, t):
    """An action to confirm as shown: {title, icon, args: [{label, value}], ask}; ask_user (Ornis's questions) comes
    with `questions` instead, shown as a form above the message box."""
    name = item.get("name") or ""
    if name == "ask_user":
        return {"title": t["act_ask_user"], "icon": "chat", "args": [], "ask": True,
                "questions": questions((item.get("args") or {}).get("questions"))}
    raw_title = item.get("title") or name
    # the cloud translates the names it knows; ours and the rest get ours
    title = t.get("act_" + name) or (raw_title if raw_title != name else name.replace("_", " ").capitalize() or t["act_other"])
    args = []
    for key, value in (item.get("args") or {}).items():
        if HIDDEN.search(key) or value in (None, "", []):
            continue
        label = t.get("arg_" + ARGS[key]) if key in ARGS else key.replace("_", " ").capitalize()
        rank = ORDER.index(ARGS[key]) if key in ARGS else len(ORDER)
        # text, a number or a list of words can be changed before confirming (the agent applies it: ornis.apply_edits)
        editable = isinstance(value, (str, int, float)) and not isinstance(value, bool) or (
            isinstance(value, list) and all(isinstance(v, (str, int, float)) for v in value))
        if ARGS.get(key) == "from":
            editable = False     # the sender is the account's own box (another address is refused by the mail server)
        args.append({"label": label, "value": _value(value), "rank": rank, "key": key, "editable": editable,
                     "long": key in LONG or len(_value(value)) > 80 or "\n" in _value(value)})
    args.sort(key=lambda a: a["rank"])
    return {"title": title, "icon": icon(name), "ask": False,
            "args": [{k: a[k] for k in ("label", "value", "key", "editable", "long")} for a in args]}
