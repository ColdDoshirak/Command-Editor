"""Deleted commands are kept here and can be put back (2.0).

command_trash.json next to commands.json: the newest first, at most LIMIT,
each with the row it had and when it was deleted.

Python 3.8 compatible. No Qt.
"""
import copy
import json
import os
import time

from core import storage

LIMIT = 50


class CommandTrash(object):
    def __init__(self, path, limit=LIMIT):
        self.path = str(path)
        self.limit = limit
        self.items = self._load()

    def _load(self):
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return [d for d in data if isinstance(d, dict) and isinstance(d.get("command"), dict)]
        except Exception as e:
            print(f"Command trash not read: {e}")
        return []

    def _save(self):
        storage.atomic_write_json(self.path, self.items)

    def add(self, cmd, row):
        self.items.insert(0, {"command": copy.deepcopy(cmd), "row": int(row), "deleted": time.time()})
        del self.items[self.limit:]
        self._save()

    def take(self, index=0):
        """Remove entry `index` (0 = the newest) and return (command, row), or None."""
        if not (0 <= index < len(self.items)):
            return None
        entry = self.items.pop(index)
        self._save()
        return entry["command"], entry["row"]

    def clear(self):
        self.items = []
        self._save()

    def __len__(self):
        return len(self.items)
