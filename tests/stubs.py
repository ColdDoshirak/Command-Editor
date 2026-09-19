"""Offline stubs for pygame / twitchio / requests.

Install via install_stubs() BEFORE importing twitch_bot.
Py3.8 compatible (no walrus, no PEP 585/604).
"""
import sys
import time
import types

# Sound durations are controlled by tests, not by file contents.
SOUND_DURATIONS = {}


def set_sound_duration(path, seconds):
    SOUND_DURATIONS[str(path)] = seconds


class PygameError(Exception):
    pass


class _FakeSound(object):
    def __init__(self, path):
        self.path = str(path)
        self._volume = 1.0
        self.duration = SOUND_DURATIONS.get(self.path, 0.05)

    def set_volume(self, v):
        self._volume = v


class _FakeChannel(object):
    def __init__(self, index):
        self.index = index
        self._busy_until = 0.0
        self.last_sound = None
        self.play_log = []  # list of (monotonic_time, sound_path)

    def play(self, sound):
        self.last_sound = sound
        self._busy_until = time.monotonic() + sound.duration
        self.play_log.append((time.monotonic(), sound.path))

    def get_busy(self):
        return time.monotonic() < self._busy_until

    def stop(self):
        self._busy_until = 0.0

    def fadeout(self, ms):
        self._busy_until = min(self._busy_until, time.monotonic() + ms / 1000.0)

    def set_volume(self, v):
        pass


class _FakeMixer(object):
    def __init__(self):
        self._channels = {}
        self.num_channels = 16

    def Channel(self, index):
        if index not in self._channels:
            self._channels[index] = _FakeChannel(index)
        return self._channels[index]

    def set_num_channels(self, n):
        self.num_channels = n

    def get_busy(self):
        return any(c.get_busy() for c in self._channels.values())

    def stop(self):
        for c in self._channels.values():
            c.stop()

    def get_init(self):
        return (44100, -16, 2)

    def init(self):
        pass

    def pre_init(self, **kwargs):
        pass


def _make_sound(path):
    if not str(path):
        raise PygameError("empty sound path")
    return _FakeSound(path)


PYGAME = None


def reset_stub_state():
    """Reset mixer channels between tests.

    Sound durations are NOT cleared: tests set them via set_sound_duration()
    (often before make_bot), and paths are unique per temp dir, so nothing
    leaks between tests.
    """
    global PYGAME
    if PYGAME is not None:
        PYGAME.mixer._channels = {}


def install_stubs():
    """Register fake pygame / twitchio / requests modules in sys.modules."""
    global PYGAME

    # --- pygame ---
    pygame_mod = types.ModuleType("pygame")
    mixer = _FakeMixer()
    mixer.Sound = _make_sound
    pygame_mod.mixer = mixer
    pygame_mod.error = PygameError
    pygame_mod.init = lambda: 0
    PYGAME = pygame_mod
    sys.modules["pygame"] = pygame_mod

    # --- twitchio ---
    twitchio_mod = types.ModuleType("twitchio")
    ext_mod = types.ModuleType("twitchio.ext")
    commands_mod = types.ModuleType("twitchio.ext.commands")
    errors_mod = types.ModuleType("twitchio.ext.commands.errors")

    class CommandNotFound(Exception):
        pass

    errors_mod.CommandNotFound = CommandNotFound

    class _FakeBot(object):
        def __init__(self, token=None, prefix="!", initial_channels=None,
                     reconnect=False, capabilities=None, **kwargs):
            self.token = token
            self.prefix = prefix
            self.initial_channels = initial_channels or []
            self.connected_channels = []
            self._commands = {}

        def command(self, name=None, **kwargs):
            def decorator(fn):
                self._commands[name or fn.__name__] = fn
                return fn
            return decorator

        async def handle_commands(self, message):
            raise CommandNotFound()

    commands_mod.Bot = _FakeBot
    commands_mod.errors = errors_mod
    commands_mod.error_handler = lambda *a, **k: None

    twitchio_mod.ext = ext_mod
    ext_mod.commands = commands_mod
    ext_mod.errors = errors_mod

    sys.modules["twitchio"] = twitchio_mod
    sys.modules["twitchio.ext"] = ext_mod
    sys.modules["twitchio.ext.commands"] = commands_mod
    sys.modules["twitchio.ext.commands.errors"] = errors_mod

    # --- requests (network disabled in tests) ---
    requests_mod = types.ModuleType("requests")

    class NoNetwork(Exception):
        pass

    def _no_get(*args, **kwargs):
        raise NoNetwork("network disabled in tests")

    requests_mod.get = _no_get
    requests_mod.post = _no_get
    requests_mod.NoNetwork = NoNetwork
    sys.modules["requests"] = requests_mod

    return pygame_mod