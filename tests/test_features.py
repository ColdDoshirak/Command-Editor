"""2.0 features (stage 7), the parts that run without a window.

Py3.8 compatible.
"""
import os
import subprocess
import sys

from harness import new_tmpdir, drop_tmpdir, REPO_DIR

# The lock is tried in separate processes: another test module replaces
# PyQt5 with a stub inside this process.
_PROBE = r'''
import sys, time, os
sys.path.insert(0, %r)
from ui.single_instance import acquire
lock = acquire(sys.argv[1])
print("LOCKED" if lock is not None else "BUSY", flush=True)
mode = sys.argv[2]
if mode == "crash":
    os._exit(0)          # dies without unlocking (a crash)
if mode == "hold":
    time.sleep(30)
'''


def _start(tmp, folder, mode):
    script = os.path.join(tmp, "probe.py")
    if not os.path.exists(script):
        with open(script, "w", encoding="utf-8") as f:
            f.write(_PROBE % REPO_DIR)
    p = subprocess.Popen([sys.executable, script, folder, mode], stdout=subprocess.PIPE)
    return p, p.stdout.readline().decode().strip()


def _probe(tmp, folder):
    p, state = _start(tmp, folder, "probe")
    p.wait(30)
    return state


async def test_second_instance_on_the_same_data_is_refused():
    tmp = new_tmpdir()
    data = os.path.join(tmp, "data")
    other = os.path.join(tmp, "other")
    holder = None
    try:
        holder, state = _start(tmp, data, "hold")
        assert state == "LOCKED", state
        assert _probe(tmp, data) == "BUSY", "another live program uses this data folder"
        assert _probe(tmp, other) == "LOCKED", "a different data folder is fine"
    finally:
        if holder is not None:
            holder.kill()
            holder.wait()
        drop_tmpdir(tmp)


async def test_lock_left_by_a_crash_does_not_block_the_next_start():
    tmp = new_tmpdir()
    data = os.path.join(tmp, "data")
    try:
        p, state = _start(tmp, data, "crash")
        p.wait(30)
        assert state == "LOCKED"
        assert os.path.exists(os.path.join(data, "command_editor.lock")), "the crash left its lock"
        assert _probe(tmp, data) == "LOCKED", "the owner is gone: its lock is stale"
    finally:
        drop_tmpdir(tmp)
