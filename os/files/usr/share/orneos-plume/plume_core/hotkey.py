"""Plume's global shortcuts on Windows and macOS (as ChatGPT's Alt+Space): Alt+Space, else Ctrl+Alt+Space when another
app holds it, brings Plume up on a new conversation with Ornis; Ctrl+Alt+N opens a Quick Note (key="n"). Orneos OS has its own (Super+O, the top-bar panel);
other Linux desktops have no common way, so nothing there. Nothing is read from the keyboard: the system calls back
only for this one combination. A failure is never fatal (the shortcut is simply not there)."""
import ctypes
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

_kept = []        # what must outlive the call (the filter, the Carbon callback)


def install(callback, space="Espace", key="space"):
    """The shortcut, or "" when none could be had. Returns its name, for the tooltip of the tray.
    key: "space" (Alt+Space, else Ctrl+Alt+Space) or "n" (Ctrl+Alt+N)."""
    try:
        if sys.platform == "win32":
            return _windows(callback, space, key)
        if sys.platform == "darwin":
            return _macos(callback, space, key)
    except Exception as error:  # noqa: BLE001 - no shortcut rather than no Plume
        print("plume: global shortcut", error, file=sys.stderr)
    return ""


# ---- Windows: RegisterHotKey, WM_HOTKEY read in the thread's messages (Qt's native event filter) --------------
WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
VK_SPACE = 0x20
HOTKEY_ID = 0x0E1A


class _Msg(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint), ("wParam", ctypes.c_size_t),
                ("lParam", ctypes.c_ssize_t), ("time", ctypes.c_uint), ("x", ctypes.c_long), ("y", ctypes.c_long)]


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, callback, hotkey_id=HOTKEY_ID):
        super().__init__()
        self._callback = callback
        self._id = hotkey_id

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = _Msg.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self._id:
                self._callback()
                return True, 0
        return False, 0


def _windows(callback, space, key="space"):
    user32 = ctypes.windll.user32
    if key == "n":
        hotkey_id, vk, choices = HOTKEY_ID + 1, 0x4E, ((MOD_CONTROL | MOD_ALT, "Ctrl+Alt+N"),)
    else:
        hotkey_id, vk, choices = HOTKEY_ID, VK_SPACE, ((MOD_ALT, "Alt+" + space), (MOD_CONTROL | MOD_ALT, "Ctrl+Alt+" + space))
    for mods, name in choices:
        if user32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk):
            event_filter = _Filter(callback, hotkey_id)
            QCoreApplication.instance().installNativeEventFilter(event_filter)
            _kept.append(event_filter)
            QCoreApplication.instance().aboutToQuit.connect(lambda: user32.UnregisterHotKey(None, hotkey_id))
            return name
    return ""


# ---- macOS: Carbon's RegisterEventHotKey (still the way for a global shortcut, no permission asked) ------------
class _HotKeyId(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


def _fourcc(text):
    return int.from_bytes(text.encode(), "big")


def _macos(callback, space, key="space"):
    carbon = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
    carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
    target = carbon.GetApplicationEventTarget()
    handler_type = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)

    hotkey_id = 2 if key == "n" else 1
    carbon.GetEventParameter.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_ulong,
                                         ctypes.c_void_p, ctypes.c_void_p]

    def on_event(_call, event, _data):
        # every shortcut of the app comes to every handler: each takes only its own (else the next one does)
        pressed = _HotKeyId()
        if carbon.GetEventParameter(event, _fourcc("----"), _fourcc("hkid"), None, ctypes.sizeof(pressed), None,
                                    ctypes.byref(pressed)) == 0 and pressed.id != hotkey_id:
            return -9874                                  # eventNotHandledErr
        callback()
        return 0
    handler = handler_type(on_event)
    spec = _EventTypeSpec(_fourcc("keyb"), 5)            # kEventClassKeyboard, kEventHotKeyPressed
    carbon.InstallEventHandler.argtypes = [ctypes.c_void_p, handler_type, ctypes.c_uint32, ctypes.POINTER(_EventTypeSpec),
                                           ctypes.c_void_p, ctypes.c_void_p]
    if carbon.InstallEventHandler(target, handler, 1, ctypes.byref(spec), None, None) != 0:
        return ""
    _kept.extend([handler, spec])
    carbon.RegisterEventHotKey.argtypes = [ctypes.c_uint32, ctypes.c_uint32, _HotKeyId, ctypes.c_void_p, ctypes.c_uint32,
                                           ctypes.POINTER(ctypes.c_void_p)]
    option, control = 0x0800, 0x1000                     # optionKey, controlKey
    if key == "n":
        code, choices = 45, ((option | control, "⌃⌥ N"),)   # kVK_ANSI_N
    else:
        code, choices = 49, ((option, "⌥ " + space), (option | control, "⌃⌥ " + space))   # kVK_Space
    for mods, name in choices:
        ref = ctypes.c_void_p()
        if carbon.RegisterEventHotKey(code, mods, _HotKeyId(_fourcc("ORNS"), hotkey_id), target, 0, ctypes.byref(ref)) == 0:
            _kept.append(ref)
            return name
    return ""
