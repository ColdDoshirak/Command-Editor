"""Rewards for Twitch chat events (USERNOTICE): raid, sub, resub, gifted subs.

twitchio 2.x has no event_raid / event_subscription / event_follow - those
handlers never ran, so nobody ever got these rewards (S7). Twitch sends the
events as USERNOTICE messages; twitchio hands their tags to
event_raw_usernotice(channel, tags), and usernotice_rewards() turns the tags
into rewards using the currency settings (keys from step 1.5).

Follows do not come through chat at all; they need EventSub (decision 3).

Pure functions, Python 3.8, no twitchio / Qt.
"""

# points multiplier per sub tier ("Prime" counts as tier 1)
TIER_MULTIPLIER = {"1000": 1, "2000": 2, "3000": 5, "Prime": 1}
TIER_NAME = {"1000": "Tier 1", "2000": "Tier 2", "3000": "Tier 3", "Prime": "Prime"}


class Reward(object):
    __slots__ = ("user", "points", "kind", "chat", "ui", "subscriber")

    def __init__(self, user, points, kind, chat, ui, subscriber=False):
        self.user = user
        self.points = points
        self.kind = kind
        self.chat = chat          # thank-you line for the Twitch chat, or None
        self.ui = ui              # line for the app's chat window
        self.subscriber = subscriber  # mark the user as a subscriber

    def __repr__(self):
        return "Reward(%r, %r, %r)" % (self.user, self.points, self.kind)


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _fmt(points):
    return "%.2f" % float(points)


def _user(tags, key="login"):
    return str(tags.get(key) or "").strip().lower()


def usernotice_rewards(tags, settings):
    """[Reward] for one USERNOTICE (empty for events without a reward)."""
    tags = tags or {}
    kind = str(tags.get("msg-id") or "")
    user = _user(tags)
    display = tags.get("display-name") or user

    if kind == "raid":
        viewers = int(_num(tags.get("msg-param-viewerCount"), 0))
        raider = _user(tags, "msg-param-login") or user
        points = _num(settings.get("raid_points", 10)) + \
            viewers * _num(settings.get("raid_points_per_viewer", 1))
        if not raider or points <= 0:
            return []
        return [Reward(raider, points, "raid",
                       "Спасибо за рейд, @%s! +%s очков за рейд с %d зрителями."
                       % (display, _fmt(points), viewers),
                       "Raid: %s получил %s очков за рейд с %d зрителями" % (raider, _fmt(points), viewers))]

    if kind in ("sub", "resub"):
        plan = str(tags.get("msg-param-sub-plan") or "1000")
        points = _num(settings.get("sub_points", 20)) * TIER_MULTIPLIER.get(plan, 1)
        if not user or points <= 0:
            return []
        return [Reward(user, points, kind,
                       "Спасибо за подписку, %s! Получено %s очков." % (display, _fmt(points)),
                       "Sub: %s получил %s очков за подписку %s"
                       % (user, _fmt(points), TIER_NAME.get(plan, plan)),
                       subscriber=True)]

    if kind in ("subgift", "anonsubgift"):
        # Twitch sends one subgift per gifted sub (a mass gift is a
        # submysterygift notice followed by N of these), so rewards go here.
        out = []
        recipient = _user(tags, "msg-param-recipient-user-name")
        recipient_display = tags.get("msg-param-recipient-display-name") or recipient
        to_recipient = _num(settings.get("gift_sub_points", 15))
        if recipient and to_recipient > 0:
            out.append(Reward(recipient, to_recipient, "subgift_recipient",
                              "%s, тебе подарили подписку! +%s очков." % (recipient_display, _fmt(to_recipient)),
                              "Gift sub: %s получил %s очков" % (recipient, _fmt(to_recipient)),
                              subscriber=True))
        to_gifter = _num(settings.get("mass_sub_points", 0))
        if kind == "subgift" and user and to_gifter > 0:
            out.append(Reward(user, to_gifter, "subgift_gifter", None,
                              "Gift sub: %s получил %s очков за подарок" % (user, _fmt(to_gifter))))
        return out

    return []
