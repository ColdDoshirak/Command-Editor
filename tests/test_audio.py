"""Step 3.6: bot/audio.py - sound cache and one interruption rule.

Py3.8 compatible.
"""
import os
import sys
import time

from harness import make_bot, make_command, make_sound_file, FakeMessage, FakeChannel, new_tmpdir, drop_tmpdir
from stubs import set_sound_duration

from bot.audio import SoundCache


def _mixer():
    return sys.modules["pygame"].mixer


async def test_cache_is_bounded_lru():
    loads = []
    cache = SoundCache(limit=3, loader=lambda p: loads.append(p) or ("snd", p))
    tmp = new_tmpdir()
    try:
        paths = [os.path.join(tmp, "s%d.wav" % i) for i in range(5)]
        for p in paths:
            open(p, "wb").close()
            cache.get(p)
        assert len(cache) == 3 and paths[0] not in cache and paths[4] in cache
        cache.get(paths[2])            # recently used stays
        cache.get(paths[0])            # evicts the least recently used (s3)
        assert paths[2] in cache and paths[3] not in cache
    finally:
        drop_tmpdir(tmp)


async def test_cache_reloads_a_replaced_file():
    loads = []
    cache = SoundCache(limit=5, loader=lambda p: loads.append(p) or object())
    tmp = new_tmpdir()
    try:
        p = os.path.join(tmp, "s.wav")
        with open(p, "wb") as f:
            f.write(b"old")
        first = cache.get(p)
        assert cache.get(p) is first and len(loads) == 1
        with open(p, "wb") as f:
            f.write(b"new, longer content")
        os.utime(p, (time.time() + 5, time.time() + 5))
        assert cache.get(p) is not first and len(loads) == 2
    finally:
        drop_tmpdir(tmp)


async def test_group_channel_respects_no_interrupt():
    tmp = new_tmpdir()
    try:
        for n in ("a.mp3", "b.mp3"):
            make_sound_file(tmp, n)
            set_sound_duration(os.path.join(tmp, n), 5.0)
        cmds = [make_command("!a", "FX", SoundFile=os.path.join(tmp, "a.mp3")),
                make_command("!b", "FX", SoundFile=os.path.join(tmp, "b.mp3"))]
        cats = {"FX": {"queue_enabled": False, "audio_channel": 3}}
        bot, _cm, _ = make_bot(tmp, cmds, cats)
        bot.allow_sound_interruption = False
        await bot.event_message(FakeMessage("u1", "!a", FakeChannel()))
        await bot.event_message(FakeMessage("u2", "!b", FakeChannel()))
        played = [os.path.basename(str(p)) for _, p in sys.modules["pygame"].mixer.Channel(3).play_log]
        assert played == ["a.mp3"], "interruption is off: !b must not cut !a (%r)" % played
        bot.allow_sound_interruption = True
        await bot.event_message(FakeMessage("u3", "!b", FakeChannel()))
        played = [os.path.basename(str(p)) for _, p in sys.modules["pygame"].mixer.Channel(3).play_log]
        assert played == ["a.mp3", "b.mp3"], played
    finally:
        drop_tmpdir(tmp)


# ---- step 4.3: the editor's "Play Sound" button (bot/audio.SoundPreview) -----

class _Chan(object):
    def __init__(self):
        self.busy = False
        self.played = []
        self.faded = 0

    def play(self, snd):
        self.played.append(snd)
        self.busy = True

    def get_busy(self):
        return self.busy

    def fadeout(self, ms):
        self.faded += 1
        self.busy = False


class _Snd(object):
    def __init__(self, path):
        self.path = path
        self.volume = None

    def set_volume(self, v):
        self.volume = v


async def test_preview_plays_stops_and_reports():
    from bot.audio import SoundPreview
    tmp = new_tmpdir()
    try:
        p = os.path.join(tmp, "s.wav")
        open(p, "wb").close()
        ch = _Chan()
        prev = SoundPreview(ch, SoundCache(loader=_Snd))
        assert prev.toggle(os.path.join(tmp, "missing.wav"), 100, True) == "missing"
        assert prev.toggle(p, 40, True) == "playing" and prev.is_playing()
        assert ch.played[-1].volume == 0.4
        assert prev.toggle(p, 40, True) == "stopped", "second press stops"
        assert ch.faded == 1 and not prev.is_playing()
        ch.busy = True                         # someone else plays on the channel
        assert prev.toggle(p, 100, False) == "blocked", "no interrupting -> do not start"
        assert prev.toggle(p, 100, True) == "playing" and ch.faded == 2
        ch.busy = False                        # the sound ended by itself
        assert not prev.is_playing()
        assert prev.toggle(p, 100, True) == "playing", "after the end a press plays again"
    finally:
        drop_tmpdir(tmp)


# ---- stage 6: mixer channels ----------------------------------------------------

async def test_group_channel_32_exists_and_preview_has_its_own():
    """Group Settings lets you pick channel 0..32, the bot made only 0..31
    (Channel(32) -> IndexError: that group's sounds never played). The editor's
    Play Sound shared channel 0 with the bot's common sounds."""
    from bot import audio
    tmp = new_tmpdir()
    try:
        make_sound_file(tmp, "a.mp3")
        cmd = make_command("!a", "FX", SoundFile=os.path.join(tmp, "a.mp3"))
        bot, _cm, _ = make_bot(tmp, [cmd], {"FX": {"queue_enabled": False, "audio_channel": 32}})
        await bot.event_message(FakeMessage("u", "!a", FakeChannel()))
        assert len(_mixer().Channel(32).play_log) == 1, "a group on channel 32 must play"
        assert audio.PREVIEW_CHANNEL > 32 and audio.PREVIEW_CHANNEL < _mixer().get_num_channels()
        assert audio.GROUP_CHANNELS == 33
        _mixer().set_num_channels(64)            # someone asked for more
        audio.ensure_channels()
        assert _mixer().get_num_channels() == 64, "never lowers the number of channels"
    finally:
        drop_tmpdir(tmp)


# ---- 2.0: a folder as the sound -> a random file from it ---------------------

async def test_pick_from_folder():
    import random
    from bot.audio import pick_sound
    tmp = new_tmpdir()
    try:
        folder = os.path.join(tmp, "laughs")
        os.makedirs(folder)
        for n in ("a.wav", "b.mp3", "c.ogg", "notes.txt"):
            open(os.path.join(folder, n), "wb").close()
        last = {}
        rng = random.Random(3)
        picks = [pick_sound(folder, last, rng) for _ in range(60)]
        assert set(os.path.basename(p) for p in picks) == {"a.wav", "b.mp3", "c.ogg"}, set(picks)
        assert all(a != b for a, b in zip(picks, picks[1:])), "never the same sound twice in a row"
        single = os.path.join(tmp, "one")
        os.makedirs(single)
        open(os.path.join(single, "x.wav"), "wb").close()
        assert pick_sound(single, last) == os.path.join(single, "x.wav")
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        assert pick_sound(empty, last) == "", "an empty folder plays nothing"
        f = os.path.join(folder, "a.wav")
        assert pick_sound(f, last) == f, "a file stays a file"
    finally:
        drop_tmpdir(tmp)


async def test_command_with_a_folder_plays_one_of_its_sounds():
    tmp = new_tmpdir()
    try:
        folder = os.path.join(tmp, "fx")
        os.makedirs(folder)
        for n in ("1.mp3", "2.mp3"):
            open(os.path.join(folder, n), "wb").close()
        cmds = [make_command("!fx", SoundFile=folder),
                make_command("!q", "SONG", SoundFile=folder)]
        bot, _cm, _ = make_bot(tmp, cmds, {"SONG": {"queue_enabled": True, "audio_channel": 2}})
        bot.allow_sound_interruption = True
        await bot.event_message(FakeMessage("u", "!fx", FakeChannel()))
        played = [p for _t, p in _mixer().Channel(0).play_log]
        assert len(played) == 1 and os.path.dirname(played[0]) == folder, played
        await bot.event_message(FakeMessage("u", "!q", FakeChannel()))
        from harness import wait_until
        assert await wait_until(lambda: len(_mixer().Channel(2).play_log) == 1, 3)
        assert os.path.dirname(_mixer().Channel(2).play_log[0][1]) == folder
        for w in list(bot.queue_workers.values()):
            w.cancel()
    finally:
        drop_tmpdir(tmp)
