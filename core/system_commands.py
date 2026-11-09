"""System commands (!points, !queue, ...): defaults and merging with the file.

Used by the Sys.Commands tab and by the bot (which must work even without a
system_commands.json, e.g. in tests or before the tab ever saved one).
A duplicate ("is_duplicate", own "command_name") runs the handler of its
original ("command").

Python 3.8 compatible, no Qt.
"""
import copy

DEFAULT_SYSTEM_COMMANDS = [
    {"command": "!points", "permission": "Everyone", "response": "", "enabled": True,
     "info": "Show user's points balance", "group": "SYSTEM", "cooldown": 5, "user_cooldown": 5,
     "cost": 0, "usage": "Chat", "is_original": True},
    {"command": "!add_points", "permission": "Moderator", "response": "", "enabled": True,
     "info": "Add points to a user", "group": "SYSTEM", "cooldown": 0, "user_cooldown": 0,
     "cost": 0, "usage": "Chat", "is_original": True},
    {"command": "!remove_points", "permission": "Moderator", "response": "", "enabled": True,
     "info": "Remove points from a user", "group": "SYSTEM", "cooldown": 0, "user_cooldown": 0,
     "cost": 0, "usage": "Chat", "is_original": True},
    {"command": "!top", "permission": "Everyone", "response": "", "enabled": True,
     "info": "Show top players by points", "group": "SYSTEM", "cooldown": 10, "user_cooldown": 30,
     "cost": 0, "usage": "Chat", "is_original": True},
    {"command": "!give", "permission": "Everyone", "response": "", "enabled": True,
     "info": "Transfer points to another user", "group": "SYSTEM", "cooldown": 0, "user_cooldown": 5,
     "cost": 0, "usage": "Chat", "is_original": True},
    {"command": "!uptime", "permission": "Everyone", "response": "", "enabled": True,
     "info": "Show stream uptime", "group": "SYSTEM", "cooldown": 5, "user_cooldown": 10,
     "cost": 0, "usage": "Chat", "is_original": True},
    {"command": "!queue", "permission": "Everyone", "response": "", "enabled": True,
     "info": "Show pending commands in queue", "group": "SYSTEM", "cooldown": 0, "user_cooldown": 0,
     "cost": 0, "usage": "Chat", "is_original": True},
    {"command": "!skip", "permission": "Moderator", "response": "", "enabled": True,
     "info": "Skip current sound (global or group)", "group": "SYSTEM", "cooldown": 0,
     "user_cooldown": 0, "cost": 0, "usage": "Chat", "is_original": True},
    {"command": "!clear", "permission": "Moderator", "response": "", "enabled": True,
     "info": "Clear all commands from a group queue", "group": "SYSTEM", "cooldown": 0,
     "user_cooldown": 0, "cost": 0, "usage": "Chat", "is_original": True},
    {"command": "!volume", "permission": "Moderator", "response": "", "enabled": True,
     "info": "Set volume for audio group (usage: !volume [GROUP] <0-100>)", "group": "SYSTEM",
     "cooldown": 0, "user_cooldown": 0, "cost": 0, "usage": "Chat", "default_group": "SONG",
     "is_original": True},
    {"command": "!random", "permission": "Everyone", "response": "", "enabled": False,
     "info": "Execute a random command from the configured group", "group": "SYSTEM",
     "cooldown": 10, "user_cooldown": 10, "cost": 0, "usage": "Chat", "random_group": "ALL",
     "show_picked_command": True, "is_original": True, "is_default_disabled": True},
]

# Queue control commands. Their Sys.Commands settings were ignored before
# 2.0 (S8); the cooldowns stored for them never applied, so they are reset
# once instead of suddenly limiting !queue to once per 5 minutes.
QUEUE_COMMANDS = ("!queue", "!skip", "!clear", "!volume")
_MIGRATION_FLAG = "settings_apply_since_2_0"


def original_of(sys_cmd):
    """The original command whose handler runs (duplicates included)."""
    return str(sys_cmd.get("command", "")).strip().lower()


def name_of(sys_cmd):
    """What viewers type: the duplicate's own name or the original."""
    return str(sys_cmd.get("command_name") or sys_cmd.get("command", "")).strip()


def migrate(commands):
    """One-time reset of the never-applied queue command cooldowns.
    Changes the dicts in place; returns True if anything changed."""
    changed = False
    for cmd in commands:
        if original_of(cmd) in QUEUE_COMMANDS and not cmd.get(_MIGRATION_FLAG):
            cmd["cooldown"] = 0
            cmd["user_cooldown"] = 0
            cmd[_MIGRATION_FLAG] = True
            changed = True
    return changed


def merge_with_defaults(loaded):
    """Every original exactly once (the stored settings win), then all
    duplicates. Returns (commands, changed): changed means the result differs
    from what was stored and should be saved."""
    loaded = loaded or []
    if not loaded:
        commands = copy.deepcopy(DEFAULT_SYSTEM_COMMANDS)
        migrate(commands)
        return commands, True
    originals, duplicates = {}, []
    for cmd in loaded:
        if not isinstance(cmd, dict) or "command" not in cmd:
            continue
        if cmd.get("is_duplicate", False):
            duplicates.append(cmd)
        elif cmd["command"] not in originals:
            originals[cmd["command"]] = cmd
    result = []
    for default in DEFAULT_SYSTEM_COMMANDS:
        existing = originals.get(default["command"])
        if existing is None:
            result.append(copy.deepcopy(default))
            continue
        existing = dict(existing)
        existing["is_original"] = True
        if default.get("is_default_disabled") and not existing.get("was_manually_enabled", False):
            existing["enabled"] = False
        result.append(existing)
    result.extend(dict(d) for d in duplicates)
    migrate(result)
    return result, result != loaded
