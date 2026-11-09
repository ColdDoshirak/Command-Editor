"""Tests for sound_paths: re-linking sounds after the sound folder moved.

Py3.8 compatible.
"""
import os

from harness import new_tmpdir, drop_tmpdir

from core import sound_paths as sp


def _touch(path):
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "wb") as f:
        f.write(b"RIFF")
    return path


def _cmd(name, sound, fk=""):
    return {"Command": name, "SoundFile": sound, "FKSoundFile": fk}


async def test_find_missing_ignores_empty_and_existing():
    tmp = new_tmpdir()
    try:
        ok = _touch(os.path.join(tmp, "ok.wav"))
        cmds = [_cmd("!a", ok), _cmd("!b", ""), _cmd("!c", os.path.join(tmp, "gone.wav"), fk="")]
        missing = sp.find_missing(cmds)
        assert missing == [(2, "SoundFile", os.path.join(tmp, "gone.wav"))], missing
    finally:
        drop_tmpdir(tmp)


async def test_relink_after_folder_moved_including_subfolders():
    tmp = new_tmpdir()
    try:
        old = os.path.join(tmp, "Old", "Sounds")
        new = os.path.join(tmp, "New", "Stream", "Sounds")
        a = _touch(os.path.join(new, "memes", "a.mp3"))
        b = _touch(os.path.join(new, "B.WAV"))
        cmds = [_cmd("!a", os.path.join(old, "memes", "a.mp3")),
                _cmd("!b", os.path.join(old, "b.wav")),
                _cmd("!c", os.path.join(old, "nothere.wav"))]
        plan = sp.plan_from_folders(cmds, [os.path.join(tmp, "New")])
        by_row = dict((p["row"], p) for p in plan)
        assert by_row[0]["new"] == a, by_row[0]
        assert by_row[1]["new"] == b, "file names are matched case-insensitively"
        assert by_row[2]["new"] is None
        changes = sp.plan_to_changes(plan)
        assert changes == {0: {"SoundFile": a}, 1: {"SoundFile": b}}, changes
    finally:
        drop_tmpdir(tmp)


async def test_same_name_in_two_folders_picks_matching_parent():
    tmp = new_tmpdir()
    try:
        _touch(os.path.join(tmp, "lib", "music", "intro.wav"))
        memes = _touch(os.path.join(tmp, "lib", "memes", "intro.wav"))
        cmds = [_cmd("!intro", "C:/gone/memes/intro.wav")]
        plan = sp.plan_from_folders(cmds, [tmp])
        assert plan[0]["new"] == memes and not plan[0]["ambiguous"], plan
        # no folder hint at all -> still picks one, but flags it
        cmds = [_cmd("!intro", "C:/gone/intro.wav")]
        plan = sp.plan_from_folders(cmds, [tmp])
        assert plan[0]["new"] and plan[0]["ambiguous"], plan
    finally:
        drop_tmpdir(tmp)


async def test_prefix_replace_only_when_target_exists():
    tmp = new_tmpdir()
    try:
        new_root = os.path.join(tmp, "E")
        x = _touch(os.path.join(new_root, "sub", "x.wav"))
        cmds = [_cmd("!x", "D:/Old/sub/x.wav"), _cmd("!y", "D:/Old/y.wav"),
                _cmd("!z", "D:/Other/z.wav")]
        plan = sp.plan_prefix_replace(cmds, "D:/Old", new_root)
        assert [p["row"] for p in plan] == [0, 1], plan
        assert os.path.normcase(plan[0]["new"]) == os.path.normcase(x), plan[0]
        assert plan[1]["new"] is None, "missing target must not be applied"
    finally:
        drop_tmpdir(tmp)


async def test_fk_sound_is_relinked_too():
    tmp = new_tmpdir()
    try:
        fk = _touch(os.path.join(tmp, "fk.wav"))
        cmds = [_cmd("!a", "", fk="X:/gone/fk.wav")]
        changes = sp.plan_to_changes(sp.plan_from_folders(cmds, [tmp]))
        assert changes == {0: {"FKSoundFile": fk}}, changes
    finally:
        drop_tmpdir(tmp)


async def test_remember_folder_dedup_and_cap():
    f = sp.remember_folder(["D:/a", "D:/b"], "d:/A")
    assert f == ["d:/A", "D:/b"] or os.name != "nt", f
    many = sp.remember_folder(["1", "2", "3", "4", "5"], "6")
    assert len(many) == sp.MAX_REMEMBERED and many[0] == "6"


async def test_common_folder():
    assert os.path.normpath(sp.common_folder(["D:/s/a/x.wav", "D:/s/b/y.wav"])) == os.path.normpath("D:/s")
    assert sp.common_folder([]) == ""
