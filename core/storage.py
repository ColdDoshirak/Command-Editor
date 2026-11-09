"""Crash-safe file writes.

A file is written to a temporary neighbour, flushed to disk and then moved
over the target with os.replace(), so a reader (or the next start after a
crash / power loss) sees either the old file or the new one, never half of
it. One lock per target path keeps two writers from interleaving.

Python 3.8 compatible, no Qt.
"""
import json
import os
import threading
import time

_locks = {}
_locks_guard = threading.Lock()


def lock_for(path):
    """The lock that serialises writes to `path` (same object for the same file)."""
    key = os.path.normcase(os.path.abspath(str(path)))
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.RLock()
        return lock


def _replace(src, dst, attempts=10):
    # On Windows os.replace fails while another process (antivirus, a viewer)
    # holds the target open; that is usually over within milliseconds.
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.05)


def atomic_write_text(path, text, encoding="utf-8"):
    path = str(path)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    with lock_for(path):
        tmp = "%s.%d.%d.tmp" % (path, os.getpid(), threading.get_ident())
        try:
            with open(tmp, "w", encoding=encoding) as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            _replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass


def atomic_write_json(path, data, indent=4, ensure_ascii=False):
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=ensure_ascii))
