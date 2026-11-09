"""Step 1.3: core/storage.py - crash-safe, serialised JSON writes.

Py3.8 compatible.
"""
import json
import os
import threading

from harness import new_tmpdir, drop_tmpdir

from core import storage


async def test_storage_failed_write_keeps_old_file_and_no_tmp():
    tmp = new_tmpdir()
    try:
        target = os.path.join(tmp, "commands.json")
        storage.atomic_write_json(target, [{"Command": "!new"}])
        orig = os.fsync

        def failing_fsync(fd):
            raise OSError("disk gone")
        os.fsync = failing_fsync
        try:
            storage.atomic_write_json(target, [{"Command": "!lost"}])
            raise AssertionError("write should have failed")
        except OSError:
            pass
        finally:
            os.fsync = orig
        with open(target, encoding="utf-8") as f:
            assert json.load(f) == [{"Command": "!new"}]
        assert [n for n in os.listdir(tmp) if n.endswith(".tmp")] == [], os.listdir(tmp)
    finally:
        drop_tmpdir(tmp)


async def test_storage_concurrent_writers_leave_valid_json():
    tmp = new_tmpdir()
    try:
        target = os.path.join(tmp, "users_currency.json")
        errors = []

        def writer(n):
            try:
                for i in range(25):
                    storage.atomic_write_json(target, {"writer": n, "i": i, "pad": "x" * 2000})
            except Exception as e:  # pragma: no cover - reported below
                errors.append(repr(e))

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [], errors
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
        assert data["i"] == 24, data["i"]
        assert [n for n in os.listdir(tmp) if n.endswith(".tmp")] == [], os.listdir(tmp)
    finally:
        drop_tmpdir(tmp)


async def test_storage_one_lock_per_file():
    a = storage.lock_for("some/dir/../dir/file.json")
    b = storage.lock_for(os.path.abspath("some/dir/file.json"))
    c = storage.lock_for("some/dir/other.json")
    assert a is b
    assert a is not c
