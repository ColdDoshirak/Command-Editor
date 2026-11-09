"""System commands (Sys.Commands tab): one handler per command (stage 6.1).

Before, execute_system_command was a 250-line if/elif in twitch_bot.py and
the queue commands another 160-line function. Now SYSTEM_HANDLERS maps the
original command (a renamed copy - "!pay" for "!give" - runs the
original's handler) to a method. Permissions, cooldowns and cost are checked
by the bot before a handler runs (S8); add/remove points additionally
require a moderator, as before.

The chat answers are unchanged (tests/test_sys_handlers.py).

Python 3.8 compatible. Mixed into TwitchBot.
"""
import random
import time
from datetime import datetime, timezone

from core.currency_manager import CurrencyManager

SYSTEM_HANDLERS = {
    "!points": "_sys_points",
    "!add_points": "_sys_add_points",
    "!remove_points": "_sys_remove_points",
    "!top": "_sys_top",
    "!give": "_sys_give",
    "!uptime": "_sys_uptime",
    "!random": "execute_random_command",
    "!queue": "_queue_list",
    "!skip": "_queue_skip",
    "!clear": "_queue_clear",
    "!volume": "_queue_volume",
}


class SystemCommandsMixin(object):

    async def execute_system_command(self, message, username, sys_cmd, full_content):
        """Run a system command: the handler of its original command."""
        original = str(sys_cmd.get("command", "")).lower()
        own_name = str(sys_cmd.get("command_name") or original).lower()
        handler = SYSTEM_HANDLERS.get(original) or SYSTEM_HANDLERS.get(own_name)
        if handler is not None:
            await getattr(self, handler)(message, username, sys_cmd, full_content)
            return
        # (every default system command has a handler; kept for safety)
        response = sys_cmd.get("response", "")
        if response:
            await message.channel.send(response.replace("{user}", username))

    async def handle_queue_commands(self, message, cmd_key, content):
        """!queue / !skip / !clear / !volume by key ("queue", ...)."""
        handler = SYSTEM_HANDLERS.get("!" + str(cmd_key).lower())
        if handler is not None:
            await getattr(self, handler)(message, message.author.name.lower(), {}, content)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    async def _reply(self, message, username, text):
        """Queue commands answer in one line, trimmed to Twitch's limit."""
        await message.channel.send(self._fit_chat(f"@{username}: {text}"))

    async def _target_and_amount(self, message, username, content, usage, invalid):
        """Parse "!cmd @user amount": (user, amount) or None (already answered)."""
        args = content.split(maxsplit=2)[1:]
        if len(args) < 2:
            await message.channel.send(f"@{username}: Usage: {usage}")
            return None
        target = args[0].lstrip('@').lower()
        try:
            amount = round(float(args[1]), 2)
        except ValueError:
            await message.channel.send(f"@{username}: {invalid}")
            return None
        if amount <= 0:
            await message.channel.send(f"@{username}: Amount must be greater than 0")
            return None
        return target, amount

    async def _require_moderator(self, message, username):
        if await self.has_permission(message, "moderator"):
            return True
        await message.channel.send(f"@{username}: You don't have permission to use this command.")
        return False

    # ------------------------------------------------------------------
    # currency
    # ------------------------------------------------------------------
    async def _sys_points(self, message, username, sys_cmd, content):
        # own cooldown from the currency settings (on top of the Sys.Commands one)
        cooldown_sec = self.currency_manager.settings.get('cooldown', 5)
        key = self.normalize_command_key("points")
        now = time.time()
        elapsed = now - self.user_cooldowns.get(key, {}).get(username, 0)
        if cooldown_sec > 0 and elapsed < cooldown_sec:
            await message.channel.send(
                f"@{username}: command is on cooldown. Try in {int(cooldown_sec - elapsed)} sec.")
            return
        await message.channel.send(self.currency_manager.format_currency_message(username))
        if cooldown_sec > 0:
            self.user_cooldowns.setdefault(key, {})[username] = now

    async def _sys_add_points(self, message, username, sys_cmd, content):
        if not await self._require_moderator(message, username):
            return
        parsed = await self._target_and_amount(message, username, content, "!add_points @username amount",
                                               "Invalid amount format. Use numbers only.")
        if parsed is None:
            return
        target, amount = parsed
        old = self.currency_manager.get_points(target)
        new = self.currency_manager.add_points(target, amount)
        if new == old:      # the currency manager refused it (validation)
            await message.channel.send(
                f"@{username}: Failed to add points. Possible reasons: amount too large, "
                f"would exceed maximum balance, or suspicious balance change detected.")
            return
        await message.channel.send(
            f"@{target} received {amount:.2f} points from @{username}. New balance: {float(new):.2f}")
        limit = CurrencyManager.MAX_BALANCE
        if new >= limit:
            await message.channel.send(
                f"@{username}: Warning: @{target} has reached or exceeded the maximum balance limit "
                f"({limit:.0f} points). Further additions may be blocked by validation.")

    async def _sys_remove_points(self, message, username, sys_cmd, content):
        if not await self._require_moderator(message, username):
            return
        parsed = await self._target_and_amount(message, username, content, "!remove_points @username amount",
                                               "Invalid amount format. Use numbers only.")
        if parsed is None:
            return
        target, amount = parsed
        old = self.currency_manager.get_points(target)
        if old < amount:
            await message.channel.send(
                f"@{username}: User @{target} only has {old:.2f} points, cannot remove {amount:.2f}")
            return
        new = self.currency_manager.remove_points(target, amount)
        if new == old:      # refused by validation: say why, by the same limits
            if amount > CurrencyManager.MAX_OPERATION:
                why = f"Amount too large: {amount:.2f} (max: {CurrencyManager.MAX_OPERATION})"
            elif amount < CurrencyManager.MIN_AMOUNT:
                why = f"Amount too small: {amount:.2f} (min: {CurrencyManager.MIN_AMOUNT})"
            else:
                why = "Validation error occurred"
            await message.channel.send(f"@{username}: Failed to remove points. {why}")
            return
        await message.channel.send(
            f"@{username} removed {amount:.2f} points from @{target}. New balance: {new:.2f}")

    async def _sys_top(self, message, username, sys_cmd, content):
        cm = self.currency_manager
        # copy under the lock: the window adds watch-time points meanwhile
        with cm.users_lock:
            users = [(name, (data or {}).get('points', 0)) for name, data in cm.users.items()]
        top = sorted(users, key=lambda x: x[1], reverse=True)[:5]
        if not top:
            await message.channel.send(f"@{username}: No users found in currency system.")
            return
        entries = [f"{i + 1}. {name} ({points:.0f})" for i, (name, points) in enumerate(top)]
        await message.channel.send("Top 5 users: " + " | ".join(entries))

    async def _sys_give(self, message, username, sys_cmd, content):
        parsed = await self._target_and_amount(message, username, content, "!give @username amount",
                                               "Invalid amount format.")
        if parsed is None:
            return
        target, amount = parsed
        have = self.currency_manager.get_points(username)
        if have < amount:
            await message.channel.send(f"@{username}: You don't have enough points ({have:.2f})")
            return
        ok, reason = self.currency_manager.transfer_points(username, target, amount)
        if not ok:
            if reason == "user not found":
                text = f"@{username}: User @{target} not found."
            elif reason == "cannot give points to yourself":
                text = f"@{username}: You can't give points to yourself."
            else:
                text = f"@{username}: Transfer failed, no points were moved."
            await message.channel.send(text)
            return
        await message.channel.send(f"@{username} gave {amount:.2f} points to @{target}!")

    # ------------------------------------------------------------------
    # stream
    # ------------------------------------------------------------------
    async def _sys_uptime(self, message, username, sys_cmd, content):
        if not self.is_live or not self.stream_start_time:
            await message.channel.send(f"@{username}: Stream is currently offline.")
            return
        try:
            start = datetime.fromisoformat(self.stream_start_time.replace('Z', '+00:00'))
            hours, rest = divmod(int((datetime.now(timezone.utc) - start).total_seconds()), 3600)
            minutes, seconds = divmod(rest, 60)
            parts = []
            if hours > 0:
                parts.append(f"{hours}h")
            if minutes > 0:
                parts.append(f"{minutes}m")
            parts.append(f"{seconds}s")
            await message.channel.send(f"@{username}: Stream uptime: {' '.join(parts)}")
        except Exception as e:
            print(f"Error calculating uptime: {e}")
            await message.channel.send(f"@{username}: Error calculating uptime.")

    async def execute_random_command(self, message, username, sys_cmd, full_content):
        """!random: a random enabled command of the configured group (or ALL)."""
        group_name = sys_cmd.get("random_group", "GENERAL").upper()
        pool = [cmd for cmd in getattr(self, "_commands_list", [])
                if cmd.get("Enabled", False)
                and (group_name == "ALL" or cmd.get("Group", "GENERAL").upper() == group_name)]
        if not pool:
            if group_name == "ALL":
                await message.channel.send(f"@{username}: No enabled commands found")
            else:
                await message.channel.send(f"@{username}: No commands found in group '{group_name}'")
            return
        selected = random.choice(pool)
        if sys_cmd.get("show_picked_command", True):
            template = sys_cmd.get("picked_command_response", "Picked {command}.")
            await message.channel.send(template.replace("{command}", selected['Command']))
        # the picked command goes through the same pipeline as a typed one:
        # permission, cooldowns, cost, the group's queue/channel/volume,
        # refund, usage count
        await self.run_command(message, selected)
        print(f"Random command executed: {selected['Command']} from group '{group_name}' by {username}")

    # ------------------------------------------------------------------
    # queues (group names are case-insensitive everywhere)
    # ------------------------------------------------------------------
    async def _queue_list(self, message, username, sys_cmd, content):
        """!queue [group]"""
        args = content.split()
        if len(args) <= 1:
            active = [f"{grp}: {n}" for grp in self.command_queues
                      for n in [self.queue_pending_count(grp)] if n > 0]
            await self._reply(message, username,
                              f"Active queues: {', '.join(active)}" if active else "All queues are empty.")
            return
        group = self._find_queue_group(args[1])
        if group is None:
            await self._reply(message, username, f"Queue group '{args[1]}' not found.")
            return
        snap = self.queue_snapshot(group)
        parts = []
        if snap['current']:
            cur = snap['current']
            parts.append(f"now: !{cur['command']} ({cur['user']})")
        pending = snap['pending']
        if pending:
            listed = ", ".join(f"{pos}. !{p['command']} ({p['user']})"
                               for pos, p in enumerate(pending[:15], start=1))
            if len(pending) > 15:
                listed += f" … +{len(pending) - 15} more"
            parts.append(f"next ({len(pending)}): {listed}")
        if not parts:
            await self._reply(message, username, f"Queue '{group}' is empty.")
        else:
            paused = " [paused]" if snap['paused'] else ""
            await self._reply(message, username, f"Queue '{group}'{paused} — " + " | ".join(parts))

    async def _queue_skip(self, message, username, sys_cmd, content):
        """!skip            - what is playing (the only active queue, else channel 0)
        !skip GROUP      - the group's current item
        !skip COMMAND    - that command's last pending entry"""
        args = content.split()
        if len(args) > 1:
            target = args[1]
            group = self._find_queue_group(target)
            if group is not None:
                ok = self.skip_queue_current(group)
                await self._reply(message, username, f"Skipped current item in '{group}'." if ok
                                  else f"Nothing is playing in '{group}'.")
                return
            name = target.lstrip('!').strip()
            for grp in list(self.command_queues):
                if self.remove_from_queue_by_name(grp, name):
                    await self._reply(message, username, f"Removed '!{name}' from queue '{grp}'.")
                    return
            await self._reply(message, username, f"'{target}' not found in any queue.")
            return
        playing = list(self.queue_current)
        if len(playing) == 1:
            self.skip_queue_current(playing[0])
            await self._reply(message, username, f"Skipped current item in '{playing[0]}'.")
        elif len(playing) > 1:
            await self._reply(message, username,
                              "Several queues are playing, use !skip <group>: " + ", ".join(playing))
        elif self.sound_channel is not None and self.sound_channel.get_busy():
            self.sound_channel.stop()
            await self._reply(message, username, "Skipped current sound.")
        else:
            await self._reply(message, username, "No sound is currently playing.")

    async def _queue_clear(self, message, username, sys_cmd, content):
        """!clear <group>"""
        args = content.split()
        if len(args) < 2:
            await self._reply(message, username, "Usage: !clear <group_name>")
            return
        group = self._find_queue_group(args[1])
        if group is None:
            await self._reply(message, username, f"Queue group '{args[1]}' not found.")
            return
        count = self.clear_queue(group)
        await self._reply(message, username, f"Cleared {count} commands from '{group}' queue.")

    def _volume_default_group(self):
        try:
            for sc in self.config_manager.load_system_commands():
                if sc.get("command", "").lower() == "!volume" and sc.get("default_group"):
                    return sc["default_group"]
        except Exception:
            pass
        return "SONG"

    async def _queue_volume(self, message, username, sys_cmd, content):
        """!volume [group] <0-100>"""
        args = content.split()
        usage = "Usage: !volume [group] <0-100>"
        try:
            if len(args) == 2:
                target_group, vol_arg = self._volume_default_group(), int(args[1])
            elif len(args) == 3:
                target_group, vol_arg = args[1], int(args[2])
            else:
                await self._reply(message, username, usage)
                return
        except ValueError:
            await self._reply(message, username, usage)
            return
        if not (0 <= vol_arg <= 100):
            await self._reply(message, username, "Volume must be between 0 and 100.")
            return
        try:
            categories = self.config_manager.get_audio_categories() or {}
            canonical = next((name for name in categories
                              if str(name).upper() == str(target_group).upper()), None)
            if canonical is None:
                await self._reply(message, username, f"Group '{target_group}' not found in audio categories.")
                return
            channel_id = categories.get(canonical, {}).get("audio_channel", 0)
            new_vol = vol_arg / 100.0
            # NEVER await while holding active_sounds_lock: it is a
            # threading.Lock and the queue worker takes it in this same
            # thread when a track ends - the whole bot used to freeze.
            applied = False
            with self.active_sounds_lock:
                sound_obj = self.active_sounds.get(channel_id)
                if sound_obj is not None:
                    try:
                        sound_obj.set_volume(new_vol)
                        applied = True
                    except Exception as vol_error:
                        print(f"Warning: Could not apply volume to active sound: {vol_error}")
            self.config_manager.set_group_volume(canonical, new_vol)
            when = "applied to current track" if applied else "will apply to next track"
            await self._reply(message, username, f"Volume for group '{canonical}' set to {vol_arg}% ({when})")
        except Exception as e:
            print(f"Error setting volume: {e}")
