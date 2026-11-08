"""The objects of Meet, made once: for its own window (meet.py) or for its module in Plume. Calls ring and
messages notify as long as the app (or Plume) runs, window or not."""
import os
from pathlib import Path

from PySide6.QtQml import QQmlEngine

import cloud
from module import Bundle
from meet_core.app import App
from meet_core.calls import Calls
from meet_core.desktop import Count, Notifier, dock_count
from meet_core.images import Provider, trim
from meet_core.library import Library
from meet_core.ornis import Ornis
from meet_core.sounds import Sounds
from meet_core.theme import Theme
from meet_core.voice import Voice

QML = Path(__file__).resolve().parent.parent / "qml"


def add_images(engine: QQmlEngine, library):
    """image://meet/… for an engine (the window's, or Plume's)."""
    if engine.imageProvider("meet") is None:
        engine.addImageProvider("meet", Provider(library.talk))


def prepare_engine(engine, built):
    """Plume's engine, before Meet's view is made in it (suite.py)."""
    add_images(engine, built.context["meet"])


def build(qt):
    theme = Theme(qt)
    app = App()
    library = Library(app)
    calls = Calls(app, library, theme)
    trim()

    notifier = Notifier()
    badge = dock_count()
    count = Count()                             # the conversations waiting, for Plume's rail

    sounds = Sounds(app, library)

    def notify(m):
        # a new message while the window is behind: told as the conversation asks (« Tous les messages »: each
        # one; by default, one-to-one and mentions), never when it is muted; « Ne pas déranger »: important only
        if not app.pref("notify") or m.get("muted"):
            return
        if library.dnd and not m.get("important"):
            return
        if not m.get("oneToOne") and not m.get("mention") and not m.get("always"):
            return
        title = m["name"] if m.get("oneToOne") else f'{m["name"]} · {m["room"]}'
        notifier.notify(title, m.get("text") or app.t["new_message"], m["token"], app.t["open"])

    def ring(info):
        # an incoming call: the card in the window (IncomingCall.qml), the ring, and a notification with its
        # answers; during another call too (answering it leaves the one in progress)
        sounds.ring(info["token"])
        body = app.t["incoming_video"] if info.get("video") else app.t["incoming_audio"]
        if info.get("elsewhere"):
            body += " · " + app.t["answer_ends_call"]
        notifier.notify(info["name"], body, "call:" + info["token"], app.t["answer_audio"], urgent=True,
                        actions=[("video", app.t["answer_video"]), ("decline", app.t["decline"])])

    def missed(info):
        # a one-to-one call nobody answered: told once, with « Rappeler » (the conversation open in front: no)
        if not app.pref("notify") or info.get("open"):
            return
        notifier.notify(info["name"], app.t["missed_call"], "callback:" + info["token"], app.t["call_back"],
                        actions=[("write", app.t["write_back"])])

    def call_event(e):
        if e.get("type") == "joinedCall":
            sounds.play("join")
        elif e.get("type") == "leftCall":
            sounds.play("leave")

    def call_changed():
        if calls.active:                # answered (here, or a call started): the ring stops
            sounds.ring("")

    def clicked(key):
        kind, _, token = key.rpartition(":")
        if kind.startswith("decline"):
            library.declineRing(token)                    # the card of the window and the ring go too
            return
        app.raiseRequested.emit()
        if kind.endswith("callback"):
            app.actionRequested.emit("room" if kind.startswith("write") else "call", token)
        elif kind.endswith("call"):
            app.actionRequested.emit("answer_video" if kind.startswith("video") else "answer", token)
        else:
            app.actionRequested.emit("room", token)
    library.ringing.connect(ring)
    library.ringStopped.connect(sounds.stop_ring)
    library.missedCall.connect(missed)
    calls.changed.connect(call_changed)
    calls.event.connect(call_event)
    notifier.clicked.connect(clicked)
    library.arrived.connect(notify)
    library.badge.connect(lambda n: badge(n if app.pref("badge") else 0))
    library.badge.connect(count.badgeChanged)
    # Talk's chats and calls are told here while Meet runs: orneos-notify leaves them (Orneos OS)
    cloud.talk_owner(os.getpid())
    qt.aboutToQuit.connect(lambda: cloud.talk_owner(None))
    qt.aboutToQuit.connect(library.shutdown)
    qt.aboutToQuit.connect(calls.shutdown)

    def on_active():
        library.set_active(True)

    voice = Voice(library)
    voice.recorded.connect(library.sendVoice)
    context = {"app": app, "theme": theme, "meet": library, "calls": calls, "ornis": Ornis(app), "voice": voice}
    return Bundle("meet", app, context, QML / "MeetView.qml", QML / "Main.qml", on_active, keep=[notifier, count, sounds])
