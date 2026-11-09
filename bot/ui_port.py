"""What the bot reports to the program window (step 4.2).

The bot knows nothing about Qt. It holds one object with these methods and
calls them from its own thread; the window's BotBridge (ui/bot_bridge.py)
implements them by emitting Qt signals, which Qt delivers in the UI thread.
Without a window (tests, a headless run) the bot uses BotUi, which drops
everything.

Py3.8 compatible.
"""


class BotUi(object):
    """No window attached: every report is dropped."""

    def chat(self, text):
        """Service line for the program's chat panel (not sent to Twitch)."""

    def all_viewers(self, viewers):
        """Everyone in chat (list of logins)."""

    def active_viewers(self, viewers):
        """Viewers who wrote recently (list of logins)."""

    def stream_status(self, is_live):
        """The stream went live / offline (bool)."""

    def moderators(self, mods):
        """Channel moderators from Twitch (list of logins)."""

    def command_used(self, cmd):
        """A command ran; cmd is the bot's own copy from the snapshot."""


class CallbackUi(BotUi):
    """Compatibility: a bare message callback receives the chat lines."""

    def __init__(self, callback):
        self._callback = callback

    def chat(self, text):
        self._callback(text)
