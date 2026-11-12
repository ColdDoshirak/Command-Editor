"""Global hotkeys (2.0): work while the window is minimised or a game has
the focus. Windows RegisterHotKey + WM_HOTKEY (available on Windows 7);
elsewhere nothing is registered.

The actions themselves run in the bot loop (bot/queue.py hotkey_*), sent
through the window's BotBridge.

Python 3.8 / PyQt5.
"""
import ctypes
import sys

from PyQt5.QtCore import QObject, Qt, QAbstractNativeEventFilter, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QApplication

# name, label, default combination
ACTIONS = (
    ("skip", "Skip what is playing", "Ctrl+Alt+S"),
    ("pause", "Pause / resume the queues", "Ctrl+Alt+P"),
    ("stop", "Stop all sounds and pause the queues", "Ctrl+Alt+M"),
)
DEFAULTS = dict({"enabled": False}, **{name: combo for name, _label, combo in ACTIONS})

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
_FIRST_ID = 0xC100

_SPECIAL_VK = {
    Qt.Key_Space: 0x20, Qt.Key_Pause: 0x13, Qt.Key_Insert: 0x2D, Qt.Key_Delete: 0x2E,
    Qt.Key_Home: 0x24, Qt.Key_End: 0x23, Qt.Key_PageUp: 0x21, Qt.Key_PageDown: 0x22,
    Qt.Key_Left: 0x25, Qt.Key_Up: 0x26, Qt.Key_Right: 0x27, Qt.Key_Down: 0x28,
    Qt.Key_ScrollLock: 0x91,
}


def available():
    return sys.platform.startswith("win")


def to_native(text):
    """"Ctrl+Alt+S" -> (modifiers, virtual key) for RegisterHotKey, or None."""
    seq = QKeySequence(str(text or ""))
    if seq.isEmpty():
        return None
    combo = int(seq[0])
    key = combo & ~int(Qt.KeyboardModifierMask)
    mods = 0
    if combo & int(Qt.ControlModifier):
        mods |= MOD_CONTROL
    if combo & int(Qt.AltModifier):
        mods |= MOD_ALT
    if combo & int(Qt.ShiftModifier):
        mods |= MOD_SHIFT
    if combo & int(Qt.MetaModifier):
        mods |= MOD_WIN
    if Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9:
        vk = key                                     # same codes as Windows
    elif Qt.Key_F1 <= key <= Qt.Key_F24:
        vk = 0x70 + (key - Qt.Key_F1)
    else:
        vk = _SPECIAL_VK.get(key)
    if vk is None:
        return None
    return mods, vk


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey):
        super(_Filter, self).__init__()
        self.on_hotkey = on_hotkey

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self.on_hotkey(int(msg.wParam))
                return True, 0
        return False, 0


class GlobalHotkeys(QObject):
    triggered = pyqtSignal(str)          # action name, in the UI thread

    def __init__(self, window):
        super(GlobalHotkeys, self).__init__(window)
        self.window = window
        self._ids = {}                   # id -> action name
        self._filter = None
        if available():
            self._filter = _Filter(self._on_native)
            QApplication.instance().installNativeEventFilter(self._filter)

    def _on_native(self, hotkey_id):
        name = self._ids.get(hotkey_id)
        if name:
            self.triggered.emit(name)

    def _hwnd(self):
        return int(self.window.winId())

    def clear(self):
        if available():
            for hotkey_id in list(self._ids):
                ctypes.windll.user32.UnregisterHotKey(self._hwnd(), hotkey_id)
        self._ids.clear()

    def apply(self, settings):
        """(Re)register from {"enabled": bool, "skip": "Ctrl+Alt+S", ...}.
        Returns {action: reason} for the ones that could not be registered
        (taken by another program, not a valid key)."""
        self.clear()
        problems = {}
        if not available() or not (settings or {}).get("enabled"):
            return problems
        for i, (name, _label, default) in enumerate(ACTIONS):
            text = (settings or {}).get(name, default)
            if not text:
                continue
            native = to_native(text)
            if native is None:
                problems[name] = "not a key that can be global"
                continue
            mods, vk = native
            hotkey_id = _FIRST_ID + i
            if ctypes.windll.user32.RegisterHotKey(self._hwnd(), hotkey_id, mods | MOD_NOREPEAT, vk):
                self._ids[hotkey_id] = name
            else:
                problems[name] = "taken by another program"
        return problems

    def registered(self):
        return sorted(self._ids.values())
