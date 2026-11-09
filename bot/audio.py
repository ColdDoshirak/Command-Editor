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
