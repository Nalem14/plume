"""The objects of Tâches, made once: for its own window (tasks.py) or for its module in Plume. The reminders
come with them: they run as long as the app (or Plume) does, window or not."""
import json
from pathlib import Path

from module import Bundle
from tasks_core.app import App
from tasks_core.library import Library
from tasks_core.ornis import Ornis
from tasks_core.reminders import Reminders
from tasks_core.theme import Theme

QML = Path(__file__).resolve().parent.parent / "qml"


def build(qt):
    theme = Theme(qt)
    app = App()
    library = Library(app)
    ornis = Ornis(app)

    def open_task(key):
        app.raiseRequested.emit()                # first: the view exists for what follows
        app.showRequested.emit(key)

    reminders = Reminders(app, library, open_task)

    # tasks given on the command line (Notes, KRunner, Plume): added without the window
    def act(action, value):
        if action == "addjson":
            try:
                items = json.loads(value)
            except json.JSONDecodeError:
                items = []
            library.add_from_outside(items if isinstance(items, list) else [items])
        elif action == "add":
            library.quickAdd(value, [])
        elif action == "refresh":
            library.refresh()
    app.actionRequested.connect(act)
    qt.aboutToQuit.connect(library.shutdown)

    def on_active():
        if library.stale(60):
            library.refresh()

    context = {"app": app, "theme": theme, "tasks": library, "ornis": ornis}
    return Bundle("tasks", app, context, QML / "TasksView.qml", QML / "Main.qml", on_active, keep=[reminders])
