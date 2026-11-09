"""Stage 2.1: core/commands.py - CommandRepository.

Py3.8 compatible.
"""
import json
import os

from harness import new_tmpdir, drop_tmpdir

from core.commands import CommandRepository, normalize, coerce, FIELDS


def _repo(cmds=None):
    events = []
    repo = CommandRepository()
    repo.replace_all(cmds or [])
    repo.subscribe(lambda ev, rows: events.append((ev, rows)))
    return repo, events


async def test_normalize_fills_and_coerces():
    cmd = normalize({"Command": "!a", "Cooldown": "5", "Volume": "55%", "Enabled": "✓",
                     "Cost": "oops", "Extra": "kept"})
    assert set(FIELDS) <= set(cmd)
    assert (cmd["Cooldown"], cmd["Volume"], cmd["Enabled"], cmd["Cost"]) == (5, 55, True, 0), cmd
    assert cmd["Extra"] == "kept"
    assert coerce("Volume", 250) == 100 and coerce("Cost", -3) == 0


async def test_list_identity_is_kept():
    repo, _ = _repo([{"Command": "!a"}])
    items = repo.items
    repo.replace_all([{"Command": "!b"}, {"Command": "!c"}])
    repo.add({"Command": "!d"})
    repo.remove(0)
    assert repo.items is items
    assert [c["Command"] for c in items] == ["!c", "!d"]


async def test_update_coerces_skips_invalid_and_reports_changes():
    repo, events = _repo([{"Command": "!a", "Volume": 50}])
    done = repo.update(0, {"Cooldown": "7", "Volume": 300, "Cost": "x", "Info": "hi"})
    assert done == {"Cooldown": 7, "Volume": 100, "Info": "hi"}, done
    assert repo.items[0]["Cost"] == 0
    assert events == [("changed", [0])]
    events[:] = []
    assert repo.update(0, {"Cooldown": 7}) == {}
    assert events == [], "no notification when nothing changed"


async def test_add_remove_events():
    repo, events = _repo([{"Command": "!a"}])
    row = repo.add({"Command": "!b"})
    assert row == 1 and events[-1] == ("inserted", [1])
    assert repo.remove(0)["Command"] == "!a" and events[-1] == ("removed", [0])
    assert repo.remove(5) is None


async def test_save_and_load_roundtrip_atomic():
    tmp = new_tmpdir()
    try:
        path = os.path.join(tmp, "commands.json")
        repo = CommandRepository(path)
        repo.replace_all([{"Command": "!a", "Response": "привет"}])
        repo.save()
        with open(path, encoding="utf-8") as f:
            assert json.load(f)[0]["Response"] == "привет"
        other = CommandRepository(path)
        other.load()
        assert other.items[0]["Command"] == "!a" and other.items[0]["Volume"] == 100
        assert [n for n in os.listdir(tmp) if n.endswith(".tmp")] == []
    finally:
        drop_tmpdir(tmp)


async def test_snapshot_is_a_copy_and_record_use_counts_original():
    repo, events = _repo([{"Command": "!a"}, {"Command": "!b"}])
    snap = repo.snapshot()
    snap[1]["Group"] = "MANGLED BY BOT"
    assert repo.items[1]["Group"] == "GENERAL", "bot copies must not reach the editor"
    assert repo.record_use(snap[1]) == 1
    assert repo.items[1]["Count"] == 1 and events[-1] == ("changed", [1])
    # the command was moved: still the right one
    repo.remove(0)
    assert repo.record_use(snap[1]) == 0 and repo.items[0]["Count"] == 2
    # deleted meanwhile: ignored
    repo.remove(0)
    assert repo.record_use(snap[1]) is None


async def test_record_use_from_older_snapshot_generations():
    repo, _ = _repo([{"Command": "!a"}])
    old = repo.snapshot()
    repo.snapshot()
    assert repo.record_use(old[0]) == 0, "a queued command from the previous snapshot counts"
    for _ in range(CommandRepository.KEEP_SNAPSHOTS):
        repo.snapshot()
    assert repo.record_use(old[0]) is None, "very old snapshots are forgotten"
    assert repo.record_use({"Command": "!a"}) is None, "unknown dicts are ignored"
