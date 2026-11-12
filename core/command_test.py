"""Test a command without Twitch (2.0): what would happen if a viewer with a
given role wrote this message. A dry run - no points are taken, no cooldown
starts, nothing is counted - built on the same rules the bot uses
(core/permissions, core/variables, the alias matching).

Python 3.8 compatible. No Qt.
"""
import os
import re

from core import permissions, variables

_INVISIBLE = re.compile(r"[\s​-‏⁠﻿]+")


def _key(name):
    return _INVISIBLE.sub("", str(name or "").lstrip("!").lower())


def simulate(cmd, text, user="viewer", role="Everyone", points=0, currency="points",
             channel="yourchannel", exists=os.path.exists):
    """{"matches", "enabled", "allowed", "cost", "enough_points", "lines",
    "sound", "sound_ok", "problems"} for one message."""
    words = str(text or "").split()
    first = _key(words[0]) if words and words[0].startswith("!") else ""
    names = [_key(cmd.get("Command", ""))] + [_key(a) for a in variables.alias_names(cmd.get("Aliases", ""))]
    out = {"matches": bool(first) and first in names, "enabled": bool(cmd.get("Enabled", True)),
           "problems": []}
    if not out["matches"]:
        out["problems"].append("The message does not call this command (it starts with %s)"
                               % (words[0] if words else "nothing"))
    if not out["enabled"]:
        out["problems"].append("The command is disabled")

    need = permissions.name_of(cmd.get("Permission", "Everyone"))
    out["allowed"] = permissions.rank(role) >= permissions.rank(need)
    if not out["allowed"]:
        out["problems"].append("%s may not use it: it needs %s" % (permissions.name_of(role), need))

    try:
        cost = int(cmd.get("Cost", 0) or 0)
    except (TypeError, ValueError):
        cost = 0
    out["cost"] = cost
    out["enough_points"] = float(points or 0) >= cost
    if not out["enough_points"]:
        out["problems"].append("Not enough points: costs %d, has %s" % (cost, variables.format_points(points)))

    try:
        count = int(cmd.get("Count", 0) or 0) + 1
    except (TypeError, ValueError):
        count = 1
    values = variables.command_values(user, text, channel=channel, count=count,
                                      points=variables.format_points(points), currency=currency)
    lines = []
    for line in str(cmd.get("Response", "") or "").split("\n"):
        if not line.strip():
            if lines:
                lines.append(None)             # a pause between messages
            continue
        lines.append(variables.render(line, values))
    while lines and lines[-1] is None:
        lines.pop()
    out["lines"] = lines

    sound = str(cmd.get("SoundFile", "") or "")
    out["sound"] = sound
    out["sound_ok"] = bool(sound) and bool(exists(sound))
    if sound and not out["sound_ok"]:
        out["problems"].append("Sound file not found: %s" % sound)
    if not lines and not sound:
        out["problems"].append("The command has neither a response nor a sound")
    return out
