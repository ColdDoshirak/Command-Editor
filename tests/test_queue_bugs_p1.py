"""Regression tests for B6-B9 (P1 queue bugs).

B6: queued command volume must be honored (group volume default 0 = "use
    the command's Volume column").
B7: stream-status / viewers checks must not block the bot loop (sync
    requests in executor) and must not block the UI thread (no
    future.result in update_viewers_and_status).
B8: persisted queue items are not re-charged after a restart; restored
    items are counted against the queue limit (semaphore accounting).
B9: semaphore race closed (check + acquire in one tick, no unbounded
    acquire); permits are never leaked when a worker is cancelled.

Py3.8 compatible.
"""
import asyncio
import os
import sys
import time
import types

from harness import (
    make_bot, make_command, make_sound_file, make_config_manager,
    FakeMessage, FakeChannel, FakeCurrencyManager, wait_until,
    new_tmpdir, drop_tmpdir,
)
from stubs import set_sound_duration, PYGAME

SONG = "SONG"


def _mixer():
    return sys.modules["pygame"].mixer


async def _stop_bot(bot):
    for group in list(bot.queue_processing):
        bot.queue_processing[group] = False
    for group, worker in list(bot.queue_workers.items()):
        if not worker.done():
            worker.cancel()
            try:
                await worker
            except BaseException:
                pass


def _no_get(*args, **kwargs):
    raise RuntimeError("network disabled in tests")


def _install_pyqt5_stub():
    """Minimal PyQt5 stub so twitch_tab/twitch_auth import without Qt.

    Widgets are magic objects (any attribute -> no-op callable); signals
    are plain slot lists; QMetaObject.invokeMethod delivers synchronously.
    """
    if "PyQt5" in sys.modules:
        return

    class _Signal(object):
        def __init__(self):
            self._slots = []

        def __call__(self, *a, **k):
            pass

        def connect(self, slot):
            self._slots.append(slot)

        def disconnect(self, *a):
            pass

        def emit(self, *args):
            for slot in list(self._slots):
                slot(*args)

    class _SignalDescriptor(object):
        # pyqtSignal(...) as a class attribute: each access gives a signal.
        def __get__(self, obj, owner):
            if obj is None:
                return _Signal()
            key = "_sig_" + self._name
            sig = obj.__dict__.get(key)
            if sig is None:
                sig = _Signal()
                obj.__dict__[key] = sig
            return sig

    def _pyqt_signal(*args, **kwargs):
        d = _SignalDescriptor()
        d._name = (args[0] if args and isinstance(args[0], str)
                   else "sig%d" % id(d))
        return d

    class QObject(object):
        def __init__(self, *args, **kwargs):
            pass

    def _pyqt_slot(*args, **kwargs):
        def deco(fn):
            return fn
        return deco

    class _Qt(object):
        QueuedConnection = 2
        DirectConnection = 1
        Horizontal = 1
        Vertical = 2
        AlignLeft = 1
        AlignRight = 2
        AlignCenter = 4

        def __getattr__(self, name):
            return 0

    class _QMetaObject(object):
        @staticmethod
        def invokeMethod(obj, name, mode=None, *args):
            # Synchronous delivery: run the slot in the calling thread.
            fn = getattr(obj, name, None)
            if fn is not None:
                fn(*args)

    def _q_arg(*args, **kwargs):
        return args[1] if len(args) > 1 else None

    class _QMetaType(object):
        @staticmethod
        def type(*a, **k):
            return 0

    class _QTimer(object):
        SingleShot = 1
        Repeating = 0

        def __init__(self, *a, **k):
            pass

        def start(self, *a):
            pass

        def stop(self):
            pass

        timeout = _Signal()

    class _Magic(object):
        """Any attribute access returns a no-op callable (or self for
        common widget APIs). Good enough for widget construction."""

        def __init__(self, *a, **k):
            self._children = []

        def __call__(self, *a, **k):
            return self

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)

            def _noop(*a, **k):
                return self

            # Widget "signals" (clicked, returnPressed, ...) must support
            # .connect() — return a signal-like object, not a bare function.
            sig = _Signal()
            sig.__call__ = _noop
            return sig

        def __iter__(self):
            return iter(())

        def __bool__(self):
            return True

    qtcore = types.ModuleType("PyQt5.QtCore")
    qtcore.QObject = QObject
    qtcore.pyqtSignal = _pyqt_signal
    qtcore.pyqtSlot = _pyqt_slot
    qtcore.QMetaObject = _QMetaObject
    qtcore.QMetaType = _QMetaType
    qtcore.Qt = _Qt()  # instance: Qt.<anything> resolves via __getattr__
    qtcore.Q_ARG = _q_arg
    qtcore.QTimer = _QTimer
    qtcore.QUrl = _Magic
    qtcore.QThread = _Magic
    qtcore.QObject = QObject

    qtwidgets = types.ModuleType("PyQt5.QtWidgets")
    for _name in (
        "QWidget", "QMainWindow", "QTabWidget", "QVBoxLayout", "QHBoxLayout",
        "QGridLayout", "QFormLayout", "QLabel", "QLineEdit", "QPushButton",
        "QTextEdit", "QGroupBox", "QMessageBox", "QDialog", "QListWidget",
        "QSplitter", "QSizePolicy", "QComboBox", "QMenu", "QAction",
        "QListWidgetItem", "QTableWidget", "QTableWidgetItem", "QHeaderView",
        "QScrollArea", "QCheckBox", "QSpinBox", "QApplication", "QAbstractItemView",
    ):
        cls = type(_name, (_Magic,), {})
        if _name == "QSizePolicy":
            cls.Preferred = 1
            cls.Fixed = 2
            cls.Expanding = 3
        if _name == "QMessageBox":
            cls.information = staticmethod(lambda *a, **k: 0)
            cls.warning = staticmethod(lambda *a, **k: 0)
            cls.question = staticmethod(lambda *a, **k: 0)
            cls.Ok = 1
            cls.Cancel = 2
        if _name == "QAbstractItemView":
            cls.SelectRows = 1
            cls.NoSelection = 0
            cls.SingleSelection = 2
        qtwidgets.__dict__[_name] = cls

    qtgui = types.ModuleType("PyQt5.QtGui")
    qtgui.QTextCursor = _Magic
    qtgui.QColor = _Magic
    qtgui.QFont = _Magic
    qtgui.QBrush = _Magic
    qtgui.QPen = _Magic
    qtgui.QPalette = _Magic
    qtgui.QDesktopServices = _Magic
    qtgui.QKeySequence = _Magic

    sip_mod = types.ModuleType("PyQt5.sip")
    sip_mod.voidptr = object

    pyqt5 = types.ModuleType("PyQt5")
    pyqt5.QtCore = qtcore
    pyqt5.QtWidgets = qtwidgets
    pyqt5.QtGui = qtgui
    pyqt5.sip = sip_mod

    sys.modules["PyQt5"] = pyqt5
    sys.modules["PyQt5.QtCore"] = qtcore
    sys.modules["PyQt5.QtWidgets"] = qtwidgets
    sys.modules["PyQt5.QtGui"] = qtgui
    sys.modules["PyQt5.sip"] = sip_mod


# ---------------------------------------------------------------- B6

async def test_b6_group_volume_default_is_zero():
    """[B6] get_group_volume must default to 0 (use command volume), not 0.5."""
    tmp = new_tmpdir()
    try:
        cm = make_config_manager(tmp, {SONG: {"queue_enabled": True,
                                              "max_queue_size": 0,
                                              "audio_channel": 1}})
        # No 'volume' key in the category at all.
        assert cm.get_group_volume(SONG) == 0, (
            "default group volume must be 0, got %s" % cm.get_group_volume(SONG))
        # Explicit 0 stays 0; explicit value is honored.
        cm.set_group_volume(SONG, 0)
        assert cm.get_group_volume(SONG) == 0
        cm.set_group_volume(SONG, 0.3)
        assert cm.get_group_volume(SONG) == 0.3
    finally:
        drop_tmpdir(tmp)


async def test_b6_queued_command_volume_honored():
    """[B6] A queued command with Volume=40 must play at 0.4, not 0.5."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 0.2)
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 0,
                       "audio_channel": 1}}  # no 'volume' key
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3", Volume=40)]
        bot, cm, cur = make_bot(tmp, cmds, cats)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1, timeout=5)
        assert ok, "sound was not played"
        played = _mixer().Channel(1).last_sound
        assert played is not None
        assert abs(played._volume - 0.4) < 1e-6, (
            "queued command Volume=40 ignored, played at %s (B6: group "
            "volume default 0.5 masks the command volume)" % played._volume)
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_b6_explicit_group_volume_still_overrides():
    """[B6] An explicitly saved group volume (e.g. 0.25) must still win."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 0.2)
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 0,
                       "audio_channel": 1, "volume": 0.25}}
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3", Volume=40)]
        bot, cm, cur = make_bot(tmp, cmds, cats)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1, timeout=5)
        assert ok, "sound was not played"
        played = _mixer().Channel(1).last_sound
        assert abs(played._volume - 0.25) < 1e-6, (
            "explicit group volume 0.25 not applied, played at %s" % played._volume)
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


# ---------------------------------------------------------------- B7

class _SlowResponse(object):
    status_code = 200

    def json(self):
        return {"data": []}


def _slow_requests_get(*args, **kwargs):
    # Simulate a slow Helix API: blocks the calling thread for 0.6 s.
    time.sleep(0.6)
    return _SlowResponse()


async def test_b7_check_if_live_does_not_block_loop():
    """[B7] check_if_live must run the sync HTTP call in an executor."""
    tmp = new_tmpdir()
    try:
        bot, cm, cur = make_bot(tmp, [])
        bot.broadcaster_id = "123"
        bot._helix_headers = {"Authorization": "Bearer x"}
        import requests as fake_requests
        fake_requests.get = _slow_requests_get
        try:
            gaps = []
            last = time.monotonic()
            check = asyncio.ensure_future(bot.check_if_live())
            for _ in range(10):
                await asyncio.sleep(0.1)
                gaps.append(time.monotonic() - last)
                last = time.monotonic()
            assert check.done(), "check_if_live did not finish in ~1s"
            is_live = check.result()
            assert is_live is False  # empty data -> offline
            max_gap = max(gaps)
            assert max_gap < 0.4, (
                "event loop blocked for %.2fs during check_if_live "
                "(sync requests.get must run in an executor)" % max_gap)
        finally:
            import requests as fake_requests2
            fake_requests2.get = _no_get
    finally:
        drop_tmpdir(tmp)


async def test_b7_update_viewers_and_status_does_not_block_ui():
    """[B7] The UI thread must not wait on the stream-status check.

    update_viewers_and_status() runs on the Qt UI thread. Before the fix it
    did future.result(timeout=5) on check_if_live, so the interface froze
    for the whole Helix round-trip. Now it schedules the callback and
    returns immediately.
    """
    _install_pyqt5_stub()
    from twitch_tab import TwitchTab

    tmp = new_tmpdir()
    try:
        bot, cm, cur = make_bot(tmp, [])
        bot.broadcaster_id = "123"
        bot._helix_headers = {"Authorization": "Bearer x"}
        bot.active_users = []
        import requests as fake_requests
        fake_requests.get = _slow_requests_get
        tab = TwitchTab(config_manager=cm)
        tab.bot = bot
        # The magic-widget stub makes hasattr() always true, so set the
        # real attributes the method reads explicitly.
        tab.last_viewers_update = 0
        tab.last_mod_check = 0
        tab.viewer_update_frequency = 30
        # Speed up the bot's background status loop for the test.
        bot.stream_status_interval = 0.1
        try:
            t0 = time.monotonic()
            tab.update_viewers_and_status()
            ui_time = time.monotonic() - t0
            assert ui_time < 0.2, (
                "UI thread blocked for %.2fs in update_viewers_and_status "
                "(must not wait on check_if_live)" % ui_time)
            # The result must arrive asynchronously via the callback
            # (bot.is_live is set by _apply_stream_status, tab.currently_live
            # by the stream_status_signal handler).
            ok = await wait_until(lambda: bot.is_live is False
                                  and tab.currently_live is False, timeout=5)
            assert ok, (
                "stream status was not delivered via callback "
                "(bot.is_live=%r, tab.currently_live=%r)"
                % (bot.is_live, tab.currently_live))
        finally:
            import requests as fake_requests2
            fake_requests2.get = _no_get
            await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


# ---------------------------------------------------------------- B8

async def test_b8_persisted_items_not_recharged():
    """[B8] Items restored from queue_persistence must not be charged again."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 0.2)
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 0,
                       "audio_channel": 1, "persist_queue": True}}
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3", Cost=10)]
        cur = FakeCurrencyManager({"alice": {"points": 100}})
        bot, cm, cur = make_bot(tmp, cmds, cats, currency=cur)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        ok = await wait_until(lambda: len(bot.command_queues[SONG]._queue) == 0, timeout=5)
        assert ok, "queue did not drain"
        assert cur.get_points("alice") == 90
        await _stop_bot(bot)

        # Simulate a restart: same config dir, new bot, queue restored.
        cur2 = FakeCurrencyManager({"alice": {"points": 90}})
        bot2, cm2, cur2 = make_bot(tmp, cmds, cats, currency=cur2)
        drained = await wait_until(lambda: len(bot2.command_queues[SONG]._queue) == 0,
                                   timeout=5)
        assert drained, "restored queue did not drain"
        assert cur2.get_points("alice") == 90, (
            "persisted item re-charged after restart: balance %s, expected 90"
            % cur2.get_points("alice"))
        await _stop_bot(bot2)
    finally:
        drop_tmpdir(tmp)


async def test_b8_restored_items_counted_against_queue_limit():
    """[B8] Restored items must hold semaphore permits (queue limit honored)."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        # Long sounds: the worker stays busy, so the queue keeps its items.
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 2.0)
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 5,
                       "audio_channel": 1, "persist_queue": True}}
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3", Cost=10)]
        cur = FakeCurrencyManager({"alice": {"points": 1000}})
        bot, cm, cur = make_bot(tmp, cmds, cats, currency=cur)
        ch = FakeChannel()
        # Enqueue 3 items (each acquires a permit before the put).
        for i in range(3):
            await bot.event_message(FakeMessage("alice", "!s1", ch))
        await asyncio.sleep(0.1)
        # The worker instantly takes the first item (2 s sound), so the
        # queue holds 2 and the snapshot persists exactly those 2.
        assert len(bot.command_queues[SONG]._queue) == 2, (
            "expected 2 queued items, got %d" % len(bot.command_queues[SONG]._queue))
        await _stop_bot(bot)

        # Restart: the 2 persisted items are restored.
        cur2 = FakeCurrencyManager({"alice": {"points": 970}})
        bot2, cm2, cur2 = make_bot(tmp, cmds, cats, currency=cur2)
        assert len(bot2.command_queues[SONG]._queue) == 2, (
            "restored queue must contain 2 items, got %d"
            % len(bot2.command_queues[SONG]._queue))
        sem = bot2.queue_semaphores[SONG]
        assert sem._value == 3, (
            "restored items must hold 2 of 5 permits, sem._value=%s" % sem._value)
        # 3 more items fit (sem has 3 permits); the worker meanwhile takes
        # one restored item (2 s sound), so the queue ends at 4.
        for i in range(3):
            await bot2.event_message(FakeMessage("alice", "!s1", ch))
        await asyncio.sleep(0.05)
        assert len(bot2.command_queues[SONG]._queue) == 4, (
            "expected 4 queued items, got %d" % len(bot2.command_queues[SONG]._queue))
        bal_before = cur2.get_points("alice")
        await bot2.event_message(FakeMessage("alice", "!s1", ch))
        assert cur2.get_points("alice") == bal_before, (
            "4th item must be rejected and refunded, balance %s -> %s"
            % (bal_before, cur2.get_points("alice")))
        await _stop_bot(bot2)
    finally:
        drop_tmpdir(tmp)


async def test_b8_legacy_persisted_items_not_recharged():
    """[B8] Old 3-field persistence entries must not be re-charged either."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 0.2)
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 0,
                       "audio_channel": 1, "persist_queue": True}}
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3", Cost=10)]
        # Write a LEGACY-format persistence entry (no already_deducted key).
        cm = make_config_manager(tmp, cats)
        cm.save_persisted_queue(SONG, [("alice", "!s1", cmds[0])])
        cur = FakeCurrencyManager({"alice": {"points": 90}})
        bot, cm2, cur = make_bot(tmp, cmds, cats, currency=cur)
        drained = await wait_until(lambda: len(bot.command_queues[SONG]._queue) == 0,
                                   timeout=5)
        assert drained, "restored queue did not drain"
        assert cur.get_points("alice") == 90, (
            "legacy persisted item re-charged: balance %s, expected 90"
            % cur.get_points("alice"))
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


# ---------------------------------------------------------------- B9

async def test_b9_full_queue_rejects_without_hang():
    """[B9] With the last permit held, a new command is rejected fast + refunded."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 5.0)  # long: worker busy
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 1,
                       "audio_channel": 1}}
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3", Cost=10)]
        cur = FakeCurrencyManager({"alice": {"points": 100}})
        bot, cm, cur = make_bot(tmp, cmds, cats, currency=cur)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1, timeout=5)
        assert ok, "first command did not start playing"
        # The worker is busy with the 5 s sound; the single permit is held.
        sem = bot.queue_semaphores[SONG]
        assert sem._value == 0, "permit should be held, sem._value=%s" % sem._value

        t0 = time.monotonic()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        reject_time = time.monotonic() - t0
        assert reject_time < 1.0, (
            "full-queue rejection took %.2fs (unbounded acquire hang?)" % reject_time)
        assert cur.get_points("alice") == 90, (
            "rejected command must be refunded, balance %s, expected 90"
            % cur.get_points("alice"))
        assert any("full" in m for m in ch.sent), (
            "no 'queue full' message: %r" % ch.sent)
        # No leak: after the long sound finishes, the permit is released.
        ok = await wait_until(lambda: sem._value == 1, timeout=8)
        assert ok, "permit leaked: sem._value=%s after sound finished" % sem._value
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_b9_cancelled_worker_releases_permit():
    """[B9] Cancelling a worker mid-processing must not leak its permit."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 5.0)
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 1,
                       "audio_channel": 1}}
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3")]
        bot, cm, cur = make_bot(tmp, cmds, cats)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1, timeout=5)
        assert ok, "command did not start playing"
        sem = bot.queue_semaphores[SONG]
        assert sem._value == 0

        # Cancel the worker WHILE it is processing the item.
        worker = bot.queue_workers[SONG]
        worker.cancel()
        try:
            await worker
        except BaseException:
            pass
        assert sem._value == 1, (
            "permit leaked after worker cancellation: sem._value=%s" % sem._value)
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)


async def test_b9_reload_resets_semaphores():
    """[B9] reload_audio_categories must reset semaphores (no stale permits)."""
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "s1.mp3")
        set_sound_duration(os.path.join(tmp, "s1.mp3"), 5.0)
        cats = {SONG: {"queue_enabled": True, "max_queue_size": 1,
                       "audio_channel": 1}}
        cmds = [make_command("!s1", SONG, SoundFile="s1.mp3")]
        bot, cm, cur = make_bot(tmp, cmds, cats)
        ch = FakeChannel()
        await bot.event_message(FakeMessage("alice", "!s1", ch))
        ok = await wait_until(lambda: len(_mixer().Channel(1).play_log) >= 1, timeout=5)
        assert ok, "command did not start playing"
        sem = bot.queue_semaphores[SONG]
        assert sem._value == 0

        await bot.reload_audio_categories()
        sem2 = bot.queue_semaphores[SONG]
        assert sem2._value == 1, (
            "semaphore not reset after reload: sem._value=%s" % sem2._value)
        await _stop_bot(bot)
    finally:
        drop_tmpdir(tmp)