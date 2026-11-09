"""One pipeline for running a custom command (step 3.1).

    permission -> cooldowns -> cost -> queue or play/answer -> refund -> count

Used for a command typed in chat and for the command !random picked, so both
behave the same (group queue, group channel and volume, refunds, counter).

The cooldown is taken when the command is accepted - before any await - so a
second call cannot slip in while the first one is still sending its reply;
if the command then fails, the cooldown is given back with the points.

CommandDispatcher is a mixin of TwitchBot (it uses the bot's chat, queue,
audio and currency); Python 3.8 compatible.
"""
import asyncio
import time


class CommandDispatcher(object):

    def _cooldown_seconds(self, cmd):
        def minutes(key):
            try:
                return max(0, int(cmd.get(key, 0) or 0))
            except (TypeError, ValueError):
                return 0
        return minutes("Cooldown") * 60, minutes("UserCooldown") * 60

    def _take_cooldown(self, key, username, cooldown_sec, user_cd_sec, now):
        """Set both cooldowns; returns what to restore if the command fails."""
        previous = (self.global_cooldowns.get(key),
                    self.user_cooldowns.get(key, {}).get(username))
        if cooldown_sec > 0:
            self.global_cooldowns[key] = now
        if user_cd_sec > 0:
            self.user_cooldowns.setdefault(key, {})[username] = now
        return previous

    def _give_back_cooldown(self, key, username, previous, cooldown_sec, user_cd_sec):
        old_global, old_user = previous
        if cooldown_sec > 0:
            if old_global is None:
                self.global_cooldowns.pop(key, None)
            else:
                self.global_cooldowns[key] = old_global
        if user_cd_sec > 0:
            users = self.user_cooldowns.get(key, {})
            if old_user is None:
                users.pop(username, None)
            else:
                users[username] = old_user

    def _refund(self, username, cost):
        self.currency_manager.add_points(username, cost)
        self.currency_manager.save_users()

    async def run_command(self, message, cmd):
        """Run custom command `cmd` (a dict from the bot's snapshot) for the
        author of `message`. Returns True if it ran or was queued."""
        username = message.author.name.lower()
        key = self.normalize_command_key(str(cmd.get("Command", "")).lstrip(self.prefix).lower())
        now = time.time()

        # 1. permission - a refusal costs nothing and starts no cooldown
        if not await self.has_permission(message, cmd.get("Permission")):
            await message.channel.send(f"@{username}: You don't have permission to use this command.")
            return False

        # 2. cooldowns (minutes in the settings)
        cooldown_sec, user_cd_sec = self._cooldown_seconds(cmd)
        if cooldown_sec > 0:
            elapsed = now - self.global_cooldowns.get(key, 0)
            if elapsed < cooldown_sec:
                await message.channel.send(
                    f"@{username}: command is on cooldown. Try in {int(cooldown_sec - elapsed)} sec.")
                return False
        if user_cd_sec > 0:
            elapsed = now - self.user_cooldowns.get(key, {}).get(username, 0)
            if elapsed < user_cd_sec:
                await message.channel.send(
                    f"@{username}: you can use this command in {int(user_cd_sec - elapsed)} sec.")
                return False

        # 3. cost (checked and paid without an await in between)
        try:
            cost = int(cmd.get("Cost", 0) or 0)
        except (TypeError, ValueError):
            cost = 0
        paid = False
        if cost > 0:
            points = self.currency_manager.get_points(username)
            if points < cost:
                await message.channel.send(
                    f"@{username}: Not enough points. Cost: {cost} (you have {float(points):.2f})")
                return False
            if not self.currency_manager.pay_for_command(username, cost):
                points = self.currency_manager.get_points(username)
                await message.channel.send(
                    f"@{username}: Payment error. Cost: {cost} (you have {float(points):.2f})")
                return False
            paid = True

        # accepted: take the cooldown now, before anything awaits
        previous = self._take_cooldown(key, username, cooldown_sec, user_cd_sec, now)

        group = self._normalize_group(cmd.get("Group", "GENERAL"))
        cat = self._category(group)
        if cat.get("queue_enabled", False):
            ok = await self._enqueue(message, cmd, group, cat, username, key, cost if paid else 0)
        else:
            ok = await self._run_now(message, cmd, group, username, key, cost if paid else 0)
        if not ok:
            self._give_back_cooldown(key, username, previous, cooldown_sec, user_cd_sec)
        return ok

    async def _enqueue(self, message, cmd, group, cat, username, key, cost):
        """4a. queued group: the queue worker plays it later (and counts it)."""
        if group not in self.command_queues:
            print(f"Lazy initializing queue/worker for group: {group}")
            self.init_queues()
        if group not in self.command_queues:
            self.command_queues[group] = asyncio.Queue()
        self.queue_processing[group] = True
        self._ensure_worker(group)

        # Limit check and put_nowait in the same tick (no await in between),
        # so two viewers can never take the last slot.
        free = self.queue_free_slots(group)
        if free is not None and free <= 0:
            print(f"Queue full for group '{group}'. Rejecting command.")
            if cost > 0:
                self._refund(username, cost)
                await message.channel.send(f"@{username}: Queue for {group} is full. {cost} points refunded.")
            else:
                await message.channel.send(f"@{username}: Queue for {group} is full. Try again later.")
            return False
        try:
            self.command_queues[group].put_nowait((message, cmd))
        except Exception as e:
            print(f"Error enqueuing command: {e}")
            if cost > 0:
                self._refund(username, cost)
                await message.channel.send(f"@{username}: Error adding to queue. {cost} points refunded.")
            return False

        self._persist_queue_snapshot(group)
        print(f"Enqueued command '{key}' to group '{group}'")
        if cat.get("announce_enqueue", False):
            position = self.queue_pending_count(group)
            if position > 1:
                await message.channel.send(self._fit_chat(
                    f"@{username}: !{key} queued in {group}, position {position}."))
        return True

    async def _run_now(self, message, cmd, group, username, key, cost):
        """4b. no queue: answer and/or play at once; refund if nothing ran."""
        executed = has_response = has_sound = sound_played = False

        sound = str(cmd.get("SoundFile", "") or "").strip()
        if sound:
            has_sound = True
            try:
                volume = float(cmd.get("Volume", 100))
            except (TypeError, ValueError):
                volume = 100.0
            override = self._group_volume_override(group)  # !volume works without a queue (S9)
            if override is not None:
                volume = override * 100.0
            channel_id = self._category(group).get("audio_channel", 0)
            sound_played = self.play_sound(sound, volume, channel_id)
            executed = executed or sound_played
            print(f"{'Played' if sound_played else 'Could not play'} sound for '{key}'")

        response = cmd.get("Response", "")
        if response and response.strip():
            has_response = True
            await self.send_multiline_response(message.channel, response, message.author.name)
            executed = True

        if executed:
            self._count_use(cmd)
            print(f"Command '{key}' executed by {username} (count {cmd.get('Count')})")
            return True

        # nothing ran (sound blocked or missing): refund and explain
        reason = "Command could not be executed"
        if has_sound and not sound_played:
            busy = self.sound_channel.get_busy() if getattr(self, "sound_channel", None) else False
            reason = ("Sound blocked: another sound is already playing" if busy
                      else "Sound file could not be played")
        if cost > 0:
            self._refund(username, cost)
            text = f"@{username}: {reason}. {cost} points refunded."
            if has_sound and not has_response:
                if getattr(self, 'show_interruption_message', False):
                    await message.channel.send(text)
            else:
                await message.channel.send(text)
        return False
