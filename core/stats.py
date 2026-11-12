"""Statistics (2.0): what happened, by day.

stats.json next to the other data:
    {"days": {"2026-11-13": {"earned": 120.5, "rewards": 30, "spent": 45,
                             "given": 10, "commands": {"!hi": 4, ...}}, ...}}

    earned   watch-time payouts
    rewards  raid / sub rewards
    spent    command costs (refunds subtracted)
    given    points moved between viewers (!give)
    commands how many times each command ran

Days older than KEEP_DAYS are dropped. Thread-safe (the bot and the window
both record); written by flush(), which the window calls periodically.

Python 3.8 compatible. No Qt.
"""
import copy
import json
import os
import threading
from datetime import date, timedelta

from core import storage

KEEP_DAYS = 90
KINDS = ("earned", "rewards", "spent", "given")


def _today():
    return date.today()


class Stats(object):
    def __init__(self, path, keep_days=KEEP_DAYS, today=_today):
        self.path = str(path) if path else None
        self.keep_days = keep_days
        self._today = today
        self._lock = threading.Lock()
        self._dirty = False
        self.days = self._load()

    def _load(self):
        try:
            if self.path and os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                days = data.get("days") if isinstance(data, dict) else None
                if isinstance(days, dict):
                    return {k: v for k, v in days.items() if isinstance(v, dict)}
        except Exception as e:
            print(f"Statistics not read: {e}")
        return {}

    def _day(self):
        key = self._today().isoformat()
        day = self.days.get(key)
        if day is None:
            day = self.days[key] = {k: 0 for k in KINDS}
            day["commands"] = {}
            cutoff = (self._today() - timedelta(days=self.keep_days - 1)).isoformat()
            for old in [k for k in self.days if k < cutoff]:
                del self.days[old]
        return day

    def record(self, kind, amount=1.0, name=None):
        """kind: one of KINDS (amount of points) or "command" (name)."""
        with self._lock:
            day = self._day()
            if kind == "command":
                cmds = day.setdefault("commands", {})
                cmds[name] = cmds.get(name, 0) + 1
            elif kind in KINDS:
                day[kind] = round(day.get(kind, 0) + float(amount), 2)
            else:
                return
            self._dirty = True

    def summary(self, days=1):
        """Totals of the last `days` days (1 = today)."""
        out = {k: 0.0 for k in KINDS}
        out["commands"] = {}
        start = (self._today() - timedelta(days=days - 1)).isoformat()
        with self._lock:
            for key, day in self.days.items():
                if key < start:
                    continue
                for k in KINDS:
                    out[k] = round(out[k] + float(day.get(k, 0) or 0), 2)
                for name, n in (day.get("commands") or {}).items():
                    out["commands"][name] = out["commands"].get(name, 0) + n
        return out

    def flush(self):
        with self._lock:
            if not self._dirty or not self.path:
                return False
            data = {"days": copy.deepcopy(self.days)}
            self._dirty = False
        try:
            storage.atomic_write_json(self.path, data)
            return True
        except Exception as e:
            print(f"Statistics not saved: {e}")
            with self._lock:
                self._dirty = True
            return False
