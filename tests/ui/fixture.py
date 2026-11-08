"""Test data for the UI checks: commands, config and generated WAV files.

Everything is synthetic, nothing is taken from the developer's own data.
Py3.8 compatible.
"""
import json
import math
import os
import struct
import wave


def make_wav(path, seconds=0.3, freq=440):
    rate = 22050
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(
            struct.pack("<h", int(3000 * math.sin(2 * math.pi * freq * i / rate)))
            for i in range(int(rate * seconds))))


def command(name, group="GENERAL", response="", sound="", **extra):
    cmd = {"Command": name, "Permission": "Everyone", "Info": "", "Group": group,
           "Response": response, "Cooldown": 0, "UserCooldown": 0, "Cost": 0,
           "Count": 0, "Usage": "SC", "Enabled": True, "SoundFile": sound,
           "FKSoundFile": "", "Volume": 100}
    cmd.update(extra)
    return cmd


def base_config(**extra):
    cfg = {
        "format_version": "2.0",
        "current_file": None,
        "volume": 0.5,
        "twitch": {"channel": ""},
        "auto_save": {"enabled": True, "interval": 300},
        "recent_files": [],
        "sound": {"volume": 1.0, "sound_dir": "", "allow_interruption": True,
                  "show_interruption_message": True},
        "commands": {},
        "backup": {"max_backups": 10},
        "currency_auto_save": {"enabled": True, "interval": 300},
        "theme": "classic",
        # no modal "sounds not found" box in an automated run
        "sound_check_on_start": False,
    }
    cfg.update(extra)
    return cfg


def write_json(data_dir, name, data):
    with open(os.path.join(data_dir, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def editor_set(data_dir, moved_sounds=False):
    """Six mixed commands (Cyrillic names, multiline responses, 4 x SONG).

    moved_sounds=True: the WAV files live in snd_moved/deeper while the
    commands still point at the old snd/ folder; snd_moved is remembered
    in config.json, so the start-up check must re-link them silently.
    """
    sound_dir = os.path.join(data_dir, "snd_moved", "deeper") if moved_sounds \
        else os.path.join(data_dir, "snd")
    old_dir = os.path.join(data_dir, "snd")
    os.makedirs(sound_dir, exist_ok=True)
    files = ["teleport.wav", "return.wav", "sci.wav", "bell.wav"]
    for i, f in enumerate(files):
        make_wav(os.path.join(sound_dir, f), freq=300 + 90 * i)

    def snd(f):
        return os.path.join(old_dir if moved_sounds else sound_dir, f)

    cmds = [
        command("!hello", "SONG", "Hello {user}!\n \nWelcome", snd("teleport.wav")),
        command("!multiline", "EXAMPLES", "This is the first line\nand the second"),
        command("!new", "SONG", "line1\nline2", snd("return.wav")),
        command("!да", "SONG", "Привет всем", snd("sci.wav")),
        command("!MORE", "GENERAL", "Ещё звук", snd("bell.wav")),
        command("!пусто", "SONG", "Нет"),
    ]
    write_json(data_dir, "commands.json", cmds)
    extra = {"sound_folders": [os.path.join(data_dir, "snd_moved")]} if moved_sounds else {}
    write_json(data_dir, "config.json", base_config(**extra))
    return cmds


def queue_set(data_dir, names=("alpha", "bravo", "charlie", "delta", "echo"), seconds=4.0):
    """Five 4-second SONG commands, SONG queued on audio channel 1."""
    sound_dir = os.path.join(data_dir, "snd")
    os.makedirs(sound_dir, exist_ok=True)
    cmds = []
    for i, n in enumerate(names):
        p = os.path.join(sound_dir, n + ".wav")
        make_wav(p, seconds, 300 + 80 * i)
        cmds.append(command("!" + n, "SONG", "", p, Volume=80))
    write_json(data_dir, "commands.json", cmds)
    write_json(data_dir, "config.json", base_config(
        theme="midnight",
        audio_categories={
            "SONG": {"queue_enabled": True, "max_queue_size": 0, "audio_channel": 1},
            "GENERAL": {"queue_enabled": False, "audio_channel": 0},
        }))
    return list(names)
