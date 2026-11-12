"""Placeholders in command responses (2.0).

    {user}          who called the command
    {target}        the first argument without "@" (the caller if none)
    {args}          everything after the command
    {1} ... {9}     one argument
    {count}         how many times the command has run, this time included
    {points}        the caller's points
    {currency}      the currency name
    {channel}       the channel
    {random:1-100}  a whole number in that range

Names are case-insensitive. Anything else in braces - an unknown name, a
broken range, JSON - is left exactly as written, so old responses do not
change.

Python 3.8 compatible. No Qt.
"""
import random as _random
import re

_PLACEHOLDER = re.compile(r"\{([A-Za-z_]+|[1-9])(?::([^{}]*))?\}")
_RANGE = re.compile(r"^\s*(-?\d+)\s*-\s*(-?\d+)\s*$")


def render(template, values, rng=None):
    """Fill the placeholders of `template` from `values` (name -> value or a
    callable that returns it; looked up only when used)."""
    if not template or "{" not in template:
        return template
    rng = rng or _random
    lower = {str(k).lower(): v for k, v in (values or {}).items()}

    def fill(m):
        name, arg = m.group(1).lower(), m.group(2)
        if name == "random":
            r = _RANGE.match(arg or "")
            if not r:
                return m.group(0)
            lo, hi = int(r.group(1)), int(r.group(2))
            if lo > hi:
                lo, hi = hi, lo
            return str(rng.randint(lo, hi))
        if arg is not None or name not in lower:
            return m.group(0)
        value = lower[name]
        if callable(value):
            try:
                value = value()
            except Exception:
                return m.group(0)
        return "" if value is None else str(value)
    return _PLACEHOLDER.sub(fill, template)


def command_values(username, content, channel="", count=None, points=None, currency=None):
    """The values for one call: content is the whole chat message."""
    parts = str(content or "").split()
    args = parts[1:]
    values = {
        "user": username,
        "target": args[0].lstrip("@") if args else username,
        "args": " ".join(args),
        "channel": channel,
    }
    for i, a in enumerate(args[:9], start=1):
        values[str(i)] = a
    if count is not None:
        values["count"] = count
    if points is not None:
        values["points"] = points
    if currency is not None:
        values["currency"] = currency
    return values


def format_points(points):
    """12.0 -> "12", 12.5 -> "12.5", 12.345 -> "12.35"."""
    try:
        p = round(float(points), 2)
    except (TypeError, ValueError):
        return str(points)
    return str(int(p)) if p == int(p) else ("%.2f" % p).rstrip("0").rstrip(".")


def alias_names(text):
    """"!music, tune  !Track" -> ["music", "tune", "track"]."""
    return [a.lstrip("!").lower() for a in re.split(r"[\s,;]+", str(text or "")) if a.lstrip("!")]
