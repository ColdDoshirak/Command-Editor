"""The commands list and the only code allowed to change it.

CommandRepository owns `items`, a plain list of command dicts in the
Streamlabs-compatible format. Everything that edits commands - the classic
table, the detail panel, the themed views, file import, backup restore,
auto-assigned sounds, usage counters from the bot - goes through it, and
listeners (the views) are told what changed. The list object never changes
identity, so views that keep a reference always see the current data.

The bot never touches these dicts: it gets snapshot() copies and reports
usage back through record_use().

Python 3.8 compatible, no Qt.
"""
import copy
import json
import os
import threading

from core import storage

# Column order of the classic table (also the order of the legacy format).
FIELDS = ("Command", "Permission", "Info", "Group", "Response", "Cooldown",
          "UserCooldown", "Cost", "Count", "Usage", "Enabled", "SoundFile",
          "FKSoundFile", "Volume")

DEFAULTS = {
    "Command": "!new",
    "Permission": "Everyone",
    "Info": "",
    "Group": "GENERAL",
    "Response": "",
    "Cooldown": 0,
    "UserCooldown": 0,
    "Cost": 0,
    "Count": 0,
    "Usage": "SC",
    "Enabled": True,
    "SoundFile": "",
    "FKSoundFile": "",
    "Volume": 100,
}

_INT_FIELDS = ("Cooldown", "UserCooldown", "Cost", "Count")
_TRUE = ("1", "true", "yes", "on", "✓")  # ✓ as shown in the classic table


def coerce(key, value):
    """Value for `key` in the stored type. Raises ValueError if it can't be."""
    if key in _INT_FIELDS:
        if isinstance(value, bool):
            raise ValueError(key)
        text = str(value).strip() if value is not None else ""
        return max(0, int(float(text))) if text else 0
    if key == "Volume":
        text = str(value).strip().rstrip("%") if value is not None else ""
        return int(max(0, min(100, round(float(text))))) if text else 100
    if key == "Enabled":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return str(value).strip().lower() in _TRUE
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def normalize(cmd):
    """A complete command dict: every field present, in the stored type.
    Unknown keys are kept (other tools may have added them)."""
    out = dict(cmd) if isinstance(cmd, dict) else {}
    for key, default in DEFAULTS.items():
        if key not in out:
            out[key] = default
            continue
        try:
            out[key] = coerce(key, out[key])
        except (TypeError, ValueError):
            out[key] = default
    return out


class CommandRepository(object):
    # listener(event, rows): event is "reset" (rows=None), "changed",
    # "inserted" or "removed" (rows = list of row indexes)

    def __init__(self, path=None):
        self.path = path
        self.items = []
        self._listeners = []
        self._lock = threading.RLock()
        self._generations = []  # snapshot() bookkeeping for record_use()

    # -- listeners --------------------------------------------------------------
    def subscribe(self, listener):
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener):
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify(self, event, rows=None):
        for listener in list(self._listeners):
            try:
                listener(event, rows)
            except Exception as e:  # a broken view must not break the data
                print("Command listener failed on %s: %s" % (event, e))

    # -- file -----------------------------------------------------------------
    def load(self, path=None):
        path = path or self.path
        data = []
        if path and os.path.exists(str(path)):
            with open(str(path), "r", encoding="utf-8") as f:
                data = json.load(f)
        self.replace_all(data if isinstance(data, list) else [])
        return self.items

    def save(self, path=None):
        path = path or self.path
        with self._lock:
            data = copy.deepcopy(self.items)
        storage.atomic_write_json(path, data)

    # -- edits ----------------------------------------------------------------
    def __len__(self):
        return len(self.items)

    def get(self, row):
        return self.items[row] if 0 <= row < len(self.items) else None

    def replace_all(self, commands):
        with self._lock:
            self.items[:] = [normalize(c) for c in commands or []]
        self._notify("reset")

    def add(self, cmd=None, row=None):
        new = normalize(cmd or {})
        with self._lock:
            if row is None or not (0 <= row <= len(self.items)):
                row = len(self.items)
            self.items.insert(row, new)
        self._notify("inserted", [row])
        return row

    def remove(self, row):
        with self._lock:
            if not (0 <= row < len(self.items)):
                return None
            cmd = self.items.pop(row)
        self._notify("removed", [row])
        return cmd

    def update(self, row, changes):
        """Apply {field: value}; values are coerced, invalid ones skipped.
        Returns {field: stored value} of what actually changed."""
        done = self._apply(row, changes)
        if done:
            self._notify("changed", [row])
        return done

    def update_many(self, changes_by_row):
        """{row: {field: value}} with one notification. Returns the rows changed."""
        rows = [r for r, ch in sorted(changes_by_row.items()) if self._apply(r, ch)]
        if rows:
            self._notify("changed", rows)
        return rows

    def _apply(self, row, changes):
        done = {}
        with self._lock:
            if not (0 <= row < len(self.items)) or not changes:
                return done
            cmd = self.items[row]
            for key, value in changes.items():
                try:
                    value = coerce(key, value) if key in DEFAULTS else value
                except (TypeError, ValueError):
                    continue
                if cmd.get(key) != value:
                    cmd[key] = value
                    done[key] = value
        return done

    # -- the bot ---------------------------------------------------------------
    def snapshot(self):
        """Deep copies for the bot. record_use(copy) finds the original."""
        with self._lock:
            copies = [copy.deepcopy(c) for c in self.items]
            # id(copy) -> (copy, original). The copy is kept alive so its id
            # can't be reused; only the last few generations are remembered
            # (a queued command from an older snapshot still counts).
            gen = dict((id(dup), (dup, original)) for original, dup in zip(self.items, copies))
            self._generations = (getattr(self, "_generations", []) + [gen])[-self.KEEP_SNAPSHOTS:]
        return copies

    KEEP_SNAPSHOTS = 3

    def _original_of(self, snapshot_cmd):
        for gen in reversed(getattr(self, "_generations", [])):
            hit = gen.get(id(snapshot_cmd))
            if hit is not None and hit[0] is snapshot_cmd:
                return hit[1]
        return None

    def record_use(self, snapshot_cmd):
        """The bot ran `snapshot_cmd` (a copy from snapshot()): count it on
        the original. Returns its row, or None if it was deleted meanwhile."""
        with self._lock:
            original = self._original_of(snapshot_cmd)
            row = next((i for i, c in enumerate(self.items) if c is original), None)
            if row is None:
                return None
            original["Count"] = int(original.get("Count", 0) or 0) + 1
        self._notify("changed", [row])
        return row
