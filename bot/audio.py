"""Sound helpers shared by the bot and the editor's preview (step 3.6).

- SoundCache: decoded pygame Sounds, at most `limit` of them (least recently
  used are dropped), reloaded when the file on disk was replaced. The old
  dict grew without bound and kept playing the old file after it changed.
- may_start(): one interruption rule for every channel. Before, only the
  shared channel 0 respected "Allow sounds to interrupt each other"; on a
  group channel without a queue a new sound always cut the playing one.

Python 3.8 compatible. pygame is imported lazily (tests swap in a stub).
"""
import os
from collections import OrderedDict


def _stamp(path):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


class SoundCache(object):
    def __init__(self, limit=32, loader=None):
        self.limit = max(1, int(limit))
        self._loader = loader
        self._items = OrderedDict()  # path -> (stamp, Sound)

    def _load(self, path):
        if self._loader is not None:
            return self._loader(path)
        import pygame
        return pygame.mixer.Sound(path)

    def get(self, path):
        """The decoded Sound for `path` (raises like pygame.mixer.Sound)."""
        path = str(path)
        stamp = _stamp(path)
        hit = self._items.get(path)
        if hit is not None and hit[0] == stamp:
            self._items.move_to_end(path)
            return hit[1]
        sound = self._load(path)
        self._items[path] = (stamp, sound)
        self._items.move_to_end(path)
        while len(self._items) > self.limit:
            self._items.popitem(last=False)
        return sound

    def forget(self, path=None):
        if path is None:
            self._items.clear()
        else:
            self._items.pop(str(path), None)

    def __len__(self):
        return len(self._items)

    def __contains__(self, path):
        return str(path) in self._items


def may_start(channel, allow_interrupt):
    """Can a new sound start on `channel` now? Busy + no interrupting -> no.
    When interrupting is allowed the playing sound is faded out."""
    if not channel.get_busy():
        return True
    if not allow_interrupt:
        return False
    try:
        channel.fadeout(100)
    except Exception:
        pass
    return True


class SoundPreview(object):
    """The editor's "Play Sound" button: one sound at a time on one channel.

    No threads: the window asks is_playing() from a timer in its own thread
    (before, a helper thread polled the channel and changed the button text
    itself - a Qt widget touched outside the UI thread).
    """

    def __init__(self, channel, cache):
        self.channel = channel
        self.cache = cache
        self._mine = False      # this preview started what the channel plays
        self._picks = {}

    def is_playing(self):
        if self._mine and not self.channel.get_busy():
            self._mine = False
        return self._mine

    def stop(self):
        if self.is_playing():
            try:
                self.channel.fadeout(100)
            except Exception:
                pass
        self._mine = False

    def toggle(self, path, volume, allow_interrupt):
        """Press of the button. Returns "stopped" (it was playing), "missing"
        (no such file), "blocked" (the channel is busy and interrupting is
        off) or "playing"."""
        if self.is_playing():
            self.stop()
            return "stopped"
        path = pick_sound(path, self._picks)          # a folder: a random sound
        if not path or not os.path.exists(path):
            return "missing"
        if not may_start(self.channel, allow_interrupt):
            return "blocked"
        snd = self.cache.get(path)
        try:
            snd.set_volume(max(0.0, min(1.0, float(volume) / 100.0)))
        except (TypeError, ValueError):
            snd.set_volume(1.0)
        self.channel.play(snd)
        self._mine = True
        return "playing"


# ---- mixer channels -----------------------------------------------------------
# Group Settings lets a group use channel 0..32 (0 = the shared channel). The
# bot used to create only 32 channels (0..31), so a group on 32 never played.
# The editor's Play Sound used channel 0 - the bot's shared channel - and so
# cut or was blocked by stream sounds; it has a channel of its own now.
GROUP_CHANNELS = 33                 # channels 0..32 for the groups
PREVIEW_CHANNEL = GROUP_CHANNELS    # the editor's Play Sound only
MIXER_CHANNELS = GROUP_CHANNELS + 1


def ensure_channels():
    """Make sure the mixer has MIXER_CHANNELS channels (never fewer than now:
    the editor and the bot both call this)."""
    import pygame
    try:
        have = pygame.mixer.get_num_channels()
    except Exception:
        have = 0
    if have < MIXER_CHANNELS:
        pygame.mixer.set_num_channels(MIXER_CHANNELS)


# ---- a folder as the sound (2.0): a random file from it ------------------------
SOUND_EXTS = (".wav", ".mp3", ".ogg", ".flac")


def pick_sound(path, last=None, rng=None):
    """`path` itself if it is a file; for a folder a random sound file from it
    (never the one picked last time from that folder, when there is a choice);
    "" for a folder without sounds. `last` is a dict the caller keeps."""
    import random
    path = str(path or "")
    if not os.path.isdir(path):
        return path
    try:
        files = sorted(os.path.join(path, n) for n in os.listdir(path)
                       if n.lower().endswith(SOUND_EXTS) and os.path.isfile(os.path.join(path, n)))
    except OSError:
        files = []
    if not files:
        return ""
    if last is not None and len(files) > 1 and last.get(path) in files:
        files = [f for f in files if f != last.get(path)]
    choice = (rng or random).choice(files)
    if last is not None:
        last[path] = choice
    return choice
