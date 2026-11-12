"""Who may run a command: one ladder of permission levels.

    Everyone < Regular < Subscriber < VIP < Moderator < Admin

Each level includes the ones below it (a moderator may run a Subscriber
command). Where each level comes from:

    Regular     the viewer's Regular status in the currency system
    Subscriber  the subscriber badge on the chat message
    VIP         the VIP badge
    Moderator   the moderator badge, the channel's moderators from Twitch,
                the manual moderators (moderators.json); "excluded" removes it
    Admin       the channel owner and the names in moderators.json "admins"

Before 2.0 only Everyone / Moderator / Admin existed and Admin was the same
as Moderator; Regular / Subscriber (from Streamlabs exports) were open to all.

Python 3.8 compatible. No Qt.
"""

LEVELS = ["Everyone", "Regular", "Subscriber", "VIP", "Moderator", "Admin"]
EVERYONE, REGULAR, SUBSCRIBER, VIP, MODERATOR, ADMIN = range(len(LEVELS))

_RANK = {name.lower(): i for i, name in enumerate(LEVELS)}
# other spellings from Streamlabs exports and old files
_ALIASES = {"": 0, "all": 0, "viewer": 0, "regulars": 1, "sub": 2, "subscribers": 2,
            "vips": 3, "mod": 4, "mods": 4, "moderators": 4, "editor": 4,
            "caster": 5, "broadcaster": 5, "streamer": 5, "owner": 5, "admins": 5}


def rank(level):
    """Position of a permission name on the ladder (unknown -> Everyone)."""
    key = str(level or "").strip().lower()
    if key in _RANK:
        return _RANK[key]
    return _ALIASES.get(key, 0)


def name_of(level):
    """The canonical name ("mod" -> "Moderator")."""
    return LEVELS[rank(level)]
