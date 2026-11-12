"""The one place where the window and the bot meet (step 4.2).

The bot runs in its own thread with its own asyncio loop; Qt widgets may be
touched only in the UI thread. Before this module both rules were broken in
several places (C4: widgets changed from the bot thread; UI code poking the
bot's asyncio objects directly). Now:

- bot -> window: the bot calls the BotUi methods (bot/ui_port.py) on this
  object from its own thread; each one only emits a Qt signal. The bridge
  lives in the UI thread, so Qt queues the delivery there.
- window -> bot: ``call`` (a plain bot method) and ``submit`` (a coroutine,
  result handed back in the UI thread) are the only ways to run anything on
  the bot loop. Nothing else in the UI uses call_soon_threadsafe or
  run_coroutine_threadsafe (tests/test_bot_ui.py checks that).

Py3.8 compatible.
"""
import asyncio

from PyQt5.QtCore import QObject, pyqtSignal

from bot.ui_port import BotUi


class BotBridge(QObject):
    # bot -> window (delivered in the UI thread)
    chat_line = pyqtSignal(str)
    all_viewers_ready = pyqtSignal(list)
    active_viewers_ready = pyqtSignal(list)
    stream_status_ready = pyqtSignal(bool)
    moderators_ready = pyqtSignal(list)
    command_ran = pyqtSignal(object)
    command_ran_by = pyqtSignal(str, str)      # command, user
    # internal: a submitted coroutine finished -> (callback, result, error)
    _finished = pyqtSignal(object, object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bot = None
        self._finished.connect(self._deliver)

    # ------------------------------------------------------------------
    # BotUi: called by the bot in its own thread -> only emit
    # ------------------------------------------------------------------
    def chat(self, text):
        self.chat_line.emit(str(text))

    def all_viewers(self, viewers):
        self.all_viewers_ready.emit(list(viewers))

    def active_viewers(self, viewers):
        self.active_viewers_ready.emit(list(viewers))

    def stream_status(self, is_live):
        self.stream_status_ready.emit(bool(is_live))

    def moderators(self, mods):
        self.moderators_ready.emit(list(mods or []))

    def command_used(self, cmd):
        self.command_ran.emit(cmd)

    def command_run(self, command, user):
        self.command_ran_by.emit(str(command), str(user))

    # ------------------------------------------------------------------
    # the bot this window talks to
    # ------------------------------------------------------------------
    @property
    def bot(self):
        return self._bot

    def attach(self, bot):
        """Talk to this bot; it reports to this bridge from now on."""
        if self._bot is not None and self._bot is not bot:
            self.detach()
        self._bot = bot
        if bot is not None:
            try:
                bot.ui = self
            except Exception:
                pass

    def detach(self):
        """Forget the bot (it stops reporting here). Returns it."""
        bot, self._bot = self._bot, None
        if bot is not None and getattr(bot, "ui", None) is self:
            try:
                bot.ui = BotUi()
            except Exception:
                pass
        return bot

    def loop(self):
        """The bot's loop if work can still be scheduled on it, else None."""
        loop = getattr(self._bot, "loop", None) if self._bot is not None else None
        if loop is None or not isinstance(loop, asyncio.AbstractEventLoop) or loop.is_closed():
            return None
        return loop

    def available(self):
        return self.loop() is not None

    # ------------------------------------------------------------------
    # window -> bot
    # ------------------------------------------------------------------
    def _resolve(self, func):
        if isinstance(func, str):
            return getattr(self._bot, func, None) if self._bot is not None else None
        return func

    def call(self, func, *args):
        """Run a plain function in the bot loop (fire and forget).

        func is a bot method name or a callable. Returns False when there is
        no live bot loop (nothing is run then).
        """
        loop = self.loop()
        fn = self._resolve(func)
        if loop is None or fn is None:
            return False
        try:
            loop.call_soon_threadsafe(fn, *args)
            return True
        except RuntimeError:          # the loop closed in between
            return False

    def submit(self, func, *args, on_done=None):
        """Run a coroutine function in the bot loop.

        func is a bot method name or a coroutine function; it is called in the
        bot loop, so no coroutine object is created when there is no loop.
        on_done(result, error) runs later in the UI thread (error is None on
        success). Returns False when nothing could be scheduled - on_done is
        not called then.
        """
        loop = self.loop()
        fn = self._resolve(func)
        if loop is None or fn is None:
            return False

        async def _run():
            return await fn(*args)
        try:
            future = asyncio.run_coroutine_threadsafe(_run(), loop)
        except RuntimeError:
            return False
        if on_done is not None:
            future.add_done_callback(lambda f: self._finished.emit(on_done, *self._outcome(f)))
        return True

    @staticmethod
    def _outcome(future):
        try:
            return future.result(), None
        except BaseException as e:      # CancelledError included
            return None, e

    def _deliver(self, callback, result, error):
        try:
            callback(result, error)
        except Exception as e:
            print(f"BotBridge callback failed: {e}")
