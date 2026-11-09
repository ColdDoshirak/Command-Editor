"""Step 3.6: bot/audio.py - sound cache and one interruption rule.

Py3.8 compatible.
"""
import os
import sys
import time

from harness import make_bot, make_command, make_sound_file, FakeMessage, FakeChannel, new_tmpdir, drop_tmpdir
from stubs import set_sound_duration

from bot.audio import SoundCache


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
