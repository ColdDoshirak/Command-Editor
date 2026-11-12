"""One running Command Editor per data folder.

Two copies over the same commands.json / users_currency.json overwrite each
other's saves. The lock lives in the data folder, so two copies with
different data folders (COMMAND_EDITOR_HOME) can still run side by side.
A lock left by a crashed copy is stale (its process is gone) and is taken
over.

Python 3.8 / PyQt5 (QLockFile needs no QApplication).
"""
import os

from PyQt5.QtCore import QLockFile

LOCK_NAME = "command_editor.lock"


def acquire(folder):
    """The held lock, or None if another live program uses `folder`."""
    os.makedirs(str(folder), exist_ok=True)
    lock = QLockFile(os.path.join(str(folder), LOCK_NAME))
    # stale only when its process is gone, never by age (we run for hours)
    lock.setStaleLockTime(0)
    if lock.tryLock(200):
        return lock
    return None
