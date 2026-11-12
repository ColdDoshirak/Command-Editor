"""Timers (2.0): messages the bot posts to chat by itself.

A timer posts its message every `interval` minutes, but only after at least
`min_lines` chat messages since its last post (so it does not talk to an
empty chat), and - with `live_only` - only while the stream is live. The
first post comes one interval after the bot connects, not at once.

Stored in config.json "timers": a list of
    {"enabled": bool, "message": str, "interval": minutes, "min_lines": int,
     "live_only": bool}

Python 3.8 compatible. No Qt.
"""

DEFAULT_TIMER = {"enabled": True, "message": "", "interval": 15, "min_lines": 5, "live_only": True}


def normalize(timer):
    t = dict(DEFAULT_TIMER)
    if isinstance(timer, dict):
        t.update(timer)
    t["enabled"] = bool(t.get("enabled"))
    t["live_only"] = bool(t.get("live_only"))
    t["message"] = str(t.get("message") or "")
    for key, low in (("interval", 1), ("min_lines", 0)):
        try:
            t[key] = max(low, int(t.get(key) or 0))
        except (TypeError, ValueError):
            t[key] = DEFAULT_TIMER[key]
    return t


def key_of(index, timer):
    """Identity of a timer for its schedule: editing the message restarts it."""
    return "%d:%s" % (index, timer.get("message", ""))


class TimerClock(object):
    """When each timer last posted and how many chat lines there were then."""

    def __init__(self, now, lines=0):
        self.started = now
        self.start_lines = lines
        self.last = {}            # key -> (time, lines)

    def due(self, timers, now, lines, is_live):
        """Keys of the timers that should post now."""
        out = []
        for i, raw in enumerate(timers or []):
            t = normalize(raw)
            if not t["enabled"] or not t["message"].strip():
                continue
            if t["live_only"] and not is_live:
                continue
            key = key_of(i, t)
            when, at_lines = self.last.get(key, (self.started, self.start_lines))
            if now - when < t["interval"] * 60:
                continue
            if lines - at_lines < t["min_lines"]:
                continue
            out.append((key, t))
        return out

    def sent(self, key, now, lines):
        self.last[key] = (now, lines)
