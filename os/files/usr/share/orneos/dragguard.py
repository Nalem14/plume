"""What a drop does (move notes or a folder, move or reorder tasks or a list) waits for the end of the drag that brought
it, when that drag started in the app itself (Drag.Automatic: a drag of the platform, QDrag.exec).

Why: on macOS the drop is delivered inside the native drag loop, which runs a little longer after it. A drop that
changes the model there rebuilds the rows, and the row being dragged (the drag's source) is deleted while QDrag.exec has
not returned: Qt then uses the deleted Drag object and the app crashes (05/11/2026: a folder moved in Notes, a list in
Tâches, Plume for macOS). Linux (xcb) leaves the loop at once, which hid it.

The QML source calls dragStarted() (Drag.onDragStarted) and dragEnded() (Drag.onDragFinished); a drop calls
afterDrag("method", [args]) instead of the method. Outside such a drag, the method runs at once."""
import time

from PySide6.QtCore import QTimer

STALE = 120                      # seconds: a drag whose end never came (its source gone) holds nothing back after that


class DragGuard:
    def __init__(self, owner, allowed):
        self._owner = owner
        self._allowed = set(allowed)
        self._since = 0.0
        self._queue = []

    def started(self):
        self._since = time.monotonic()

    def ended(self):
        self._since = 0.0
        queue, self._queue = self._queue, []
        if queue:                                # after QQuickDrag's own code has returned: the next turn of the loop
            QTimer.singleShot(0, lambda: self._run(queue))

    def call(self, method, args):
        method = str(method)
        if method not in self._allowed:
            return
        args = list(args.toVariant() if hasattr(args, "toVariant") else args or [])
        if self._since and time.monotonic() - self._since < STALE:
            self._queue.append((method, args))
            return
        self._since = 0.0
        self._run([(method, args)])

    def _run(self, queue):
        for method, args in queue:
            getattr(self._owner, method)(*args)
