"""The 👍 / 👎 on Ornis's answers, and the « Was it useful? » card now and then (Chat, Code, Bots).

The cloud keeps one row per answer, no account named (OrnisFeedback of the orneos app, page « Avis d'Ornis » of
Orneos's admin). Sent: the vote and facts of the turn without content (version, number of tools…); the exchange only
when the person ticks « Joindre cet échange » under a 👎. The card: at most once a day per agent, after a real
exchange; closed without a vote (✕), none for a week on that agent.
"""
import sys
import threading
import time
from datetime import date

CHAT_REASONS = ["wrong", "not_asked", "didnt_act", "too_long", "other"]
AGENT_REASONS = ["wrong", "not_asked", "didnt_act", "stuck", "broke", "too_long", "other"]
CALM_DAYS = 7


def version() -> str:
    """Plume's version (plume.py's VERSION), or « os » for the apps of Orneos OS."""
    try:
        import plume_core  # noqa: PLC0415 (Plume; absent from the apps of Orneos OS)
        return str(plume_core.VERSION)[:24]
    except (ImportError, AttributeError):
        main = sys.modules.get("__main__")
        return str(getattr(main, "VERSION", "") or "os")[:24]


def should_ask(app, product: str, enough: bool) -> bool:
    """The card on this answer? Once a day per agent at most, never in the week after it was closed; records it."""
    if not enough:
        return False
    seen = dict(app.pref("feedback_card") or {})
    mine = dict(seen.get(product) or {})
    if mine.get("day") == date.today().isoformat() or time.time() < float(mine.get("calm") or 0):
        return False
    mine["day"] = date.today().isoformat()
    seen[product] = mine
    app.setPref("feedback_card", seen)
    return True


def calm(app, product: str) -> None:
    seen = dict(app.pref("feedback_card") or {})
    seen[product] = dict(seen.get(product) or {}, calm=time.time() + CALM_DAYS * 86400)
    app.setPref("feedback_card", seen)


def send(app, **body) -> None:
    """To the cloud, in the background, in the order given; a vote lost is not worth a message."""
    account = app.account()
    if not account:
        return
    queue = _QUEUE
    with _LOCK:
        queue.append((account, body))
        if len(queue) > 1:
            return

    def work():
        from ornis_chat import Chat as Client, Error  # noqa: PLC0415 (the cloud's client, as the conversations)
        while True:
            with _LOCK:
                if not queue:
                    return
                acc, item = queue[0]
            try:
                Client(*acc).vote(**item)
            except (Error, OSError, ValueError):
                pass
            with _LOCK:
                queue.pop(0)
    threading.Thread(target=work, daemon=True, name="ornis-feedback").start()


_QUEUE: list = []
_LOCK = threading.Lock()
