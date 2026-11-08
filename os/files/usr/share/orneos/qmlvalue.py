"""Dicts and lists for QML, converted once rather than at every read.

A QVariantMap or QVariantList property reaches QML as a reference to the property: each `app.t.save`, or each
`room.name` after `property var room: meet.room`, reads the property again and converts the whole value (1.5 ms
for the 900 texts of Plume). With hundreds of such reads in a view, switching modules, opening a message or a
conversation, even hovering the rail, stalled the window. A JS object made by the engine reads in a few µs.

    @js_property(notify=changed)        # or constant=True
    def rooms(self): return [...]

QML gets one JS object per value (made again only when the getter returns something else); Python still reads
the plain dict or list. Without an engine (use() not called), QML gets the plain value as before.
⚠️ QML must not change what it gets (sort, push, assign): the same object is handed to every reader.
"""
import copy

from PySide6.QtCore import Property

_engine = [None]


def use(engine):
    """The QML engine of the app (one per process), right after making it."""
    _engine[0] = engine


class _JsProperty(Property):
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self._plain(obj)


def js_property(notify=None, constant=False):
    def wrap(fget):
        slot = "_js_" + fget.__name__

        def read(self):
            value = fget(self)
            engine = _engine[0]
            if engine is None:
                return value
            hit = self.__dict__.get(slot)
            if hit is not None and hit[0] is engine and (constant or hit[1] == value):
                return hit[2]
            js = engine.toScriptValue(value)
            try:
                kept = None if constant else copy.deepcopy(value)
            except Exception:           # noqa: BLE001 - not copyable: converted at every read, as before
                return js
            self.__dict__[slot] = (engine, kept, js)
            return js

        prop = _JsProperty("QVariant", read, constant=True) if constant else _JsProperty("QVariant", read, notify=notify)
        prop._plain = fget
        return prop
    return wrap
