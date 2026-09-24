"""Offline test harness for Command-Editor queue logic.

Run the real TwitchBot / ConfigManager code without Twitch, network, or audio.
Py3.8 compatible.

Usage (from a test module):
    from harness import (make_bot, make_command, make_config_manager,
                         FakeMessage, FakeChannel, FakeCurrencyManager,
                         wait_until, set_sound_duration)
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

from stubs import install_stubs, reset_stub_state, set_sound_duration  # noqa: E402

install_stubs()

# Silence the bot's debug print() spam (it prints on every message/command).
# Tests never need it; restore with CE_TEST_VERBOSE=1 to debug.
import builtins  # noqa: E402
import os as _os  # noqa: E402
if not _os.environ.get("CE_TEST_VERBOSE"):
    builtins.__ce_real_print__ = builtins.print  # keep the original for the runner
    builtins.print = lambda *a, **k: None

from config_manager import ConfigManager  # noqa: E402
from twitch_bot import TwitchBot  # noqa: E402

# Track repo-dir files created by ConfigManager.__init__ (it writes defaults
# next to config_manager.py). Cleaned up by cleanup_repo_dir().
_REPO_FILES = ("config.json", "twitch_config.json", "moderators.json")
_preexisting = set()
for _f in _REPO_FILES:
    if os.path.exists(os.path.join(REPO_DIR, _f)):
        _preexisting.add(_f)


def cleanup_repo_dir():
    """Remove config files that ConfigManager.__init__ created in the repo dir."""
    for _f in _REPO_FILES:
        p = os.path.join(REPO_DIR, _f)
        if _f not in _preexisting and os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


class FakeCurrencyManager(object):
    """In-memory stand-in for CurrencyManager (points + is_mod flags)."""

    def __init__(self, users=None):
        self.users = users if users is not None else {}
        self.save_count = 0

    def get_points(self, username):
        return self.users.get(username, {}).get("points", 0)

    def add_points(self, username, amount):
        data = self.users.setdefault(username, {})
        data["points"] = data.get("points", 0) + amount
        return data["points"]

    def remove_points(self, username, amount):
        data = self.users.setdefault(username, {})
        data["points"] = max(0, data.get("points", 0) - amount)
        return data["points"]

    def pay_for_command(self, username, cost):
        if self.get_points(username) < cost:
            return False
        self.add_points(username, -cost)
        return True

    def save_users(self):
        self.save_count += 1


def make_command(name, group="GENERAL", **kw):
    """Build a full command dict (all keys the UI/bot expect)."""
    cmd = {
        "Command": name,
        "Permission": "Everyone",
        "Info": "",
        "Group": group,
        "Response": "",
        "Cooldown": 0,
        "UserCooldown": 0,
        "Cost": 0,
        "Count": 0,
        "Usage": "SC",
        "Enabled": True,
        "SoundFile": "",
        "FKSoundFile": "",
        "Volume": 100,
    }
    cmd.update(kw)
    return cmd


def make_config_manager(tmpdir, audio_categories=None, sound_dir=None):
    """Real ConfigManager with all paths redirected to tmpdir."""
    cfg = {
        "format_version": "2.0",
        "volume": 0.5,
        "twitch": {"channel": "testchan"},
        "audio_categories": audio_categories if audio_categories is not None else {},
        "sound": {"volume": 1.0, "sound_dir": sound_dir if sound_dir is not None else tmpdir},
    }
    with open(os.path.join(tmpdir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)

    cm = ConfigManager()
    # Redirect every path to the temp dir and reload config from there.
    cm.program_dir = type(cm.program_dir)(tmpdir)
    cm.config_file = cm.program_dir / "config.json"
    cm.twitch_file = cm.program_dir / "twitch_config.json"
    cm.commands_file = cm.program_dir / "commands.json"
    cm.moderators_file = cm.program_dir / "moderators.json"
    cm.backup_dir = cm.program_dir / "backups"
    with open(cm.config_file, "r", encoding="utf-8") as f:
        cm.config = json.load(f)
    return cm


def make_sound_file(tmpdir, name):
    """Create an (empty) sound file in tmpdir; returns its name.

    The fake pygame never reads the file, it only needs to exist so
    play_sound_sequentially's existence check passes.
    """
    path = os.path.join(tmpdir, name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(b"")
    return name


class FakeChannel(object):
    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


class FakeMessage(object):
    def __init__(self, author, content, channel=None):
        self.author = SimpleNamespace(name=author)
        self.content = content
        self.channel = channel if channel is not None else FakeChannel()
        self.echo = False


def make_bot(tmpdir, commands, audio_categories=None, currency=None,
             channel="testchan"):
    """Build a real TwitchBot (stubs) with redirected config.

    Must be called from inside a running event loop so queue workers start.
    Returns (bot, config_manager, currency_manager).
    """
    reset_stub_state()
    cm = make_config_manager(tmpdir, audio_categories)
    cur = currency if currency is not None else FakeCurrencyManager()
    bot = TwitchBot(
        channel,
        message_callback=None,
        config_manager=cm,
        currency_manager=cur,
    )
    bot.update_commands(commands)
    bot.initialized_event.set()
    return bot, cm, cur


async def wait_until(cond, timeout=5.0, interval=0.02):
    """Poll cond() until true or timeout. Returns True if cond became true."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        await asyncio.sleep(interval)
    return False


def new_tmpdir():
    return tempfile.mkdtemp(prefix="ce_test_")


def drop_tmpdir(tmpdir):
    shutil.rmtree(tmpdir, ignore_errors=True)


def make_real_currency(tmpdir):
    """Real CurrencyManager with all paths redirected to tmpdir.

    The real class derives data_dir from its own file location, so we
    construct it, then re-point every path into the sandbox and reload.
    This is what lets the reliability suite exercise the REAL locking,
    validation, checksum and backup logic (not the FakeCurrencyManager).
    """
    from pathlib import Path
    from currency_manager import CurrencyManager

    d = Path(tmpdir)
    (d / "backups" / "currency").mkdir(parents=True, exist_ok=True)
    cm = CurrencyManager()
    cm.data_dir = d
    cm.users_file = d / "users_currency.json"
    cm.currency_file = d / "users_currency.json"
    cm.backup_dir = d / "backups" / "currency"
    cm.users = {}
    cm.load_data()
    return cm