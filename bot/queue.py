"""The per-group command queue of the bot (step 3.7), moved out of
twitch_bot.py without changing its behaviour.

QueueMixin is mixed into TwitchBot; it uses the bot's config_manager,
currency_manager, _commands_list, sound_channel, loop, active_sounds and
the chat helpers. The invariants that keep it correct are listed in
docs/refactor-plan.md, section 2 (polling workers, limit counted as pending +
current, reload never cancels workers, entries addressed by id(item),
asyncio objects only touched in the bot's loop thread).

Python 3.8 compatible.
"""
import asyncio
import time
import traceback
from pathlib import Path

import pygame


class _PersistedMessage:
    """Lightweight stand-in for a twitchio message, used to rehydrate queued
    commands from persistence after a restart. It carries just enough surface
    (author.name, content, channel.send) for execute_queued_command to run the
    command's response/cost logic without a live Twitch connection.
    """

    def __init__(self, author_name, content, channel=None):
        self.author = _PersistedAuthor(author_name)
        self.content = content
        self.channel = channel

    async def send(self, text):
        # No live channel to deliver to after a restart; log only.
        print(f"[persisted-queue] (no live channel) {self.author.name}: {text}")


class _PersistedAuthor:
    def __init__(self, name):
        self.name = name


class _QueueSlots(object):
    """Read-only view of a group's free queue slots.

    Keeps the old ``asyncio.Semaphore``-style ``_value`` attribute for code
    and tests that inspect it, but the number is computed from the real
    queue state (pending + currently executing), so it can never leak.
    """

    def __init__(self, bot, group):
        self._bot = bot
        self._group = group

    @property
    def _value(self):
        free = self._bot.queue_free_slots(self._group)
        return 0 if free is None else free


class QueueMixin(object):
    # ------------------------------------------------------------------
    # Queue core
    # ------------------------------------------------------------------
    def _loop_is_running(self):
        loop = getattr(self, 'loop', None)
        return loop is not None and not loop.is_closed() and loop.is_running()

    def _in_loop_thread(self):
        """True if we are executing inside the bot's own event loop."""
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            return False
        return running is getattr(self, 'loop', None)

    def _category(self, group):
        """Group settings dict, looked up case-insensitively."""
        categories = self.config_manager.get_audio_categories() or {}
        cat = categories.get(group)
        if cat is None and group:
            for name, value in categories.items():
                if str(name).upper() == str(group).upper():
                    cat = value
                    break
        return cat if isinstance(cat, dict) else {}

    def _queue_max(self, group):
        try:
            return max(0, int(self._category(group).get('max_queue_size', 0) or 0))
        except (TypeError, ValueError):
            return 0

    def queue_pending_count(self, group):
        """Pending items + the one being executed right now."""
        q = self.command_queues.get(group)
        pending = q.qsize() if q is not None else 0
        return pending + (1 if group in self.queue_current else 0)

    def queue_free_slots(self, group):
        """Free slots in the group's queue, or None if unlimited."""
        max_size = self._queue_max(group)
        if max_size <= 0:
            return None
        return max(0, max_size - self.queue_pending_count(group))

    def _find_queue_group(self, name):
        """Existing queue group by name, case-insensitive."""
        if not name:
            return None
        if name in self.command_queues:
            return name
        for g in self.command_queues:
            if str(g).upper() == str(name).upper():
                return g
        return None

    def init_queues(self):
        """Create queues/workers for every group with queue_enabled=true.

        Idempotent and cheap: called on startup, after every command edit and
        after Group Settings are saved. Must run in the bot loop thread
        (asyncio objects in Python 3.8 bind to the loop of the creating
        thread), so calls from the UI thread are forwarded there.

        Disabling a queue does NOT cancel its worker: it stops accepting new
        items and the worker finishes what was already paid for, then exits.
        """
        if self._loop_is_running() and not self._in_loop_thread():
            self.loop.call_soon_threadsafe(self.init_queues)
            return

        categories = self.config_manager.get_audio_categories() or {}
        groups = set(str(name) for name in categories)
        for cmd in self._commands_list:
            groups.add(cmd.get("Group", "GENERAL"))

        loop_ready = self._loop_is_running()
        for group in groups:
            cat = categories.get(group, {})
            if not isinstance(cat, dict):
                cat = {}
            enabled = bool(cat.get("queue_enabled", False))
            if enabled:
                if group not in self.command_queues:
                    self.command_queues[group] = asyncio.Queue()
                    print(f"Created new queue for group: {group}")
                    # Rehydrate items saved from a previous session
                    # (only if this group has persistence enabled).
                    self._restore_persisted_queue(group)
                self.queue_processing[group] = True
            elif group in self.command_queues:
                if self.queue_processing.get(group):
                    print(f"Queue disabled for group {group}: draining remaining items")
                self.queue_processing[group] = False

            if group in self.command_queues:
                self.queue_semaphores[group] = (
                    _QueueSlots(self, group) if self._queue_max(group) > 0 else None)
                self._ensure_worker(group, loop_ready)

    def _ensure_worker(self, group, loop_ready=None):
        if loop_ready is None:
            loop_ready = self._loop_is_running()
        if not loop_ready:
            return  # event_ready will start it
        q = self.command_queues.get(group)
        if q is None:
            return
        if not self.queue_processing.get(group) and q.empty():
            return  # disabled and nothing left to play
        worker = self.queue_workers.get(group)
        if worker is None or worker.done():
            self.queue_workers[group] = self.loop.create_task(self.process_queue(group))

    def _persist_queue_snapshot(self, group):
        """Save the group's queue to config (only if persistence is enabled).

        The snapshot contains the item being executed right now followed by
        the pending ones, so a crash mid-track does not lose a paid command.
        Reads the deque without draining it.
        """
        try:
            if not self._category(group).get('persist_queue', False):
                return
            q = self.command_queues.get(group)
            if q is None:
                return
            entries = []
            cur = self.queue_current.get(group)
            if cur is not None and not cur.get('skipped'):
                entries.append((cur.get('message'), cur.get('cmd')))
            entries.extend(list(q._queue))
            items = []
            for msg, cmd in entries:
                author = msg.author.name if (msg is not None and getattr(msg, 'author', None)) else ''
                content = msg.content if (msg is not None and getattr(msg, 'content', None)) else ''
                # B8: already paid at enqueue time — never charge again.
                items.append((author, content, cmd, True))
            self.config_manager.save_persisted_queue(group, items)
        except Exception as e:
            print(f"Error persisting queue snapshot for {group}: {e}")

    def _restore_persisted_queue(self, group):
        """Rehydrate a group's queue from config on startup (only if the group
        has persistence enabled). Items are wrapped in a lightweight message
        stand-in so the worker can execute them without a live Twitch message.
        Restored items count against the queue limit; extra ones are dropped.
        """
        try:
            if not self._category(group).get('persist_queue', False):
                return
            items = self.config_manager.load_persisted_queue(group)
            if not items:
                return
            q = self.command_queues.get(group)
            if q is None:
                return
            max_size = self._queue_max(group)
            if max_size > 0 and len(items) > max_size:
                print(f"Persisted queue for {group} has {len(items)} items "
                      f"> max {max_size}; dropping {len(items) - max_size}")
                items = items[:max_size]
            for (author, content, cmd, already_deducted) in items:
                msg = _PersistedMessage(author, content)
                msg.already_deducted = already_deducted
                q.put_nowait((msg, cmd))
            print(f"Restored {len(items)} persisted queue items for group {group}")
        except Exception as e:
            print(f"Error restoring persisted queue for {group}: {e}")

    async def process_queue(self, group):
        """Sequential worker for one group.

        Polls the queue instead of awaiting ``Queue.get()``: no future is
        bound to a particular loop, pause never has to "put back" an item
        (which used to move it to the END of the queue), and the worker
        exits cleanly once the group is disabled and drained.
        """
        print(f"Starting queue worker for group: {group}")
        try:
            while True:
                q = self.command_queues.get(group)
                if q is None:
                    break
                if q.empty():
                    if not self.queue_processing.get(group, False):
                        break
                    await asyncio.sleep(0.05)
                    continue
                if group in self.queue_paused:
                    await asyncio.sleep(0.1)
                    continue

                item = q.get_nowait()
                message, cmd_data = item
                # No await between get_nowait() and this line: the slot count
                # (pending + current) never drops for a moment.
                self.queue_current[group] = {
                    'message': message, 'cmd': cmd_data, 'item': item,
                    'started': time.time(), 'channel': None, 'sound': None,
                    'skipped': False,
                }
                try:
                    self._persist_queue_snapshot(group)
                    await self.execute_queued_command(message, cmd_data)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"Error processing queue item for {group}: {e}")
                    traceback.print_exc()
                finally:
                    self.queue_current.pop(group, None)
                    q.task_done()
                    self._persist_queue_snapshot(group)
        except asyncio.CancelledError:
            print(f"Queue worker for {group} cancelled")
        finally:
            print(f"Queue worker for {group} stopped")

    # ------------------------------------------------------------------
    # Queue control. All of these must run in the bot loop: the UI calls
    # them through loop.call_soon_threadsafe, chat commands run there anyway.
    # ------------------------------------------------------------------
    def queue_snapshot(self, group):
        """Thread-tolerant read of a group's state for the UI.

        Returns dict(current=..., pending=[...], paused, max, free) where each
        entry is dict(id, user, command). ``id`` identifies the queue entry
        for remove/reorder calls (it is id() of the stored tuple).
        """
        q = self.command_queues.get(group)
        if q is None:
            return None
        pending = []
        for _attempt in range(3):
            try:
                pending = list(q._queue)
                break
            except RuntimeError:  # deque mutated by the bot thread
                continue

        def describe(item):
            msg, cmd = item
            author = getattr(getattr(msg, 'author', None), 'name', None) or '?'
            name = str((cmd or {}).get('Command', '?')).lstrip('!')
            return {'id': id(item), 'user': author, 'command': name}

        cur = self.queue_current.get(group)
        current = None
        if cur is not None:
            current = describe(cur['item'])
            current['started'] = cur.get('started')
            current['skipped'] = cur.get('skipped', False)
        return {
            'current': current,
            'pending': [describe(it) for it in pending],
            'paused': group in self.queue_paused,
            'max': self._queue_max(group),
            'free': self.queue_free_slots(group),
            'enabled': bool(self.queue_processing.get(group)),
        }

    def skip_queue_current(self, group):
        """Skip what the group is executing right now (sound + response).

        Only stops the channel if it is still playing OUR sound, so a skip
        never cuts an unrelated sound on the shared channel 0.
        Returns True if there was something to skip.
        """
        cur = self.queue_current.get(group)
        if cur is None:
            return False
        cur['skipped'] = True
        channel = cur.get('channel')
        sound = cur.get('sound')
        if channel is not None:
            try:
                get_sound = getattr(channel, 'get_sound', None)
                if sound is None or get_sound is None or get_sound() is sound:
                    channel.stop()
            except Exception as e:
                print(f"Error stopping sound for {group}: {e}")
        print(f"Queue: skipped current item for group {group}")
        return True

    def set_queue_paused(self, group, paused):
        if paused:
            self.queue_paused.add(group)
        else:
            self.queue_paused.discard(group)

    # -- global hotkeys (ui/hotkeys.py; called in the bot loop via the bridge) --
    def hotkey_skip(self):
        """Skip what every queue is playing; without one, stop the shared
        channel's sound. Returns how many queue items were skipped."""
        skipped = sum(1 for g in list(self.queue_current) if self.skip_queue_current(g))
        if not skipped and self.sound_channel is not None:
            try:
                if self.sound_channel.get_busy():
                    self.sound_channel.stop()
            except Exception:
                pass
        return skipped

    def hotkey_toggle_pause(self):
        """Pause every queue (or resume them all if all are paused).
        Returns True when the queues are paused now."""
        groups = list(self.command_queues)
        pause = any(g not in self.queue_paused for g in groups)
        for g in groups:
            self.set_queue_paused(g, pause)
        return pause

    def hotkey_stop_all(self):
        """The panic button: stop every sound now and pause the queues
        (resume with the pause hotkey)."""
        for g in list(self.command_queues):
            self.set_queue_paused(g, True)
        for g in list(self.queue_current):
            self.skip_queue_current(g)
        try:
            pygame.mixer.stop()
        except Exception:
            pass

    def _remove_queue_item(self, group, item):
        q = self.command_queues.get(group)
        try:
            q._queue.remove(item)
        except (ValueError, AttributeError):
            return False
        # put() incremented unfinished_tasks for this item; balance it.
        try:
            q.task_done()
        except ValueError:
            pass
        self._persist_queue_snapshot(group)
        return True

    def remove_from_queue_by_id(self, group, item_id):
        """Remove one pending entry (as identified by queue_snapshot)."""
        q = self.command_queues.get(group)
        if q is None:
            return False
        for item in list(q._queue):
            if id(item) == item_id:
                return self._remove_queue_item(group, item)
        return False

    def remove_from_queue_by_name(self, group, name):
        """Remove the LAST pending entry of a command (by name, without '!').

        Does not touch what is playing right now — that is what skip is for.
        (The old version also stopped the current track.)
        """
        q = self.command_queues.get(group)
        if q is None or not name:
            return False
        target = str(name).lstrip('!').strip().lower()
        for item in reversed(list(q._queue)):
            cmd = item[1] if len(item) > 1 else {}
            if str(cmd.get('Command', '')).lstrip('!').strip().lower() == target:
                return self._remove_queue_item(group, item)
        return False

    def clear_queue(self, group):
        """Drop every pending entry of the group. Returns how many."""
        q = self.command_queues.get(group)
        if q is None:
            return 0
        removed = 0
        while True:
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                break
            q.task_done()
            removed += 1
        print(f"Queue: cleared {removed} items from group {group}")
        self._persist_queue_snapshot(group)
        return removed

    def reorder_queue_by_ids(self, group, ids):
        """Reorder pending entries to match ``ids`` (from queue_snapshot).
        Entries not listed keep their relative order at the end."""
        q = self.command_queues.get(group)
        if q is None:
            return
        items = list(q._queue)
        by_id = dict((id(it), it) for it in items)
        new_items = []
        for i in ids:
            it = by_id.pop(i, None)
            if it is not None:
                new_items.append(it)
        new_items.extend(it for it in items if id(it) in by_id)
        q._queue.clear()
        q._queue.extend(new_items)  # same items: unfinished_tasks unchanged
        self._persist_queue_snapshot(group)

    def move_queue_item(self, group, item_id, delta):
        """Move one pending entry up (delta<0) or down (delta>0)."""
        q = self.command_queues.get(group)
        if q is None:
            return
        ids = [id(it) for it in q._queue]
        if item_id not in ids:
            return
        i = ids.index(item_id)
        j = max(0, min(len(ids) - 1, i + delta))
        if i == j:
            return
        ids.insert(j, ids.pop(i))
        self.reorder_queue_by_ids(group, ids)

    def _group_volume_override(self, group):
        """Saved !volume for the group: float 0..1, or None if not set.

        0 used to mean "not set", so "!volume 0" silently played at the
        command's own volume. Mute is now stored explicitly.
        """
        cat = self._category(group)
        if cat.get('muted'):
            return 0.0
        try:
            vol = float(cat.get('volume', 0) or 0)
        except (TypeError, ValueError):
            return None
        return vol if vol > 0 else None

    async def execute_queued_command(self, message, cmd):
        """Execute a single command from the queue and wait for completion if it has sound"""
        username = message.author.name.lower()
        cmd_name = str(cmd.get("Command", "unknown")).lstrip('!')
        group = cmd.get("Group", "GENERAL")

        print(f"--- Starting execution of queued command: !{cmd_name} (Group: {group}) ---")

        try:
            # NOTE: Cost is NOT charged here. The command was already charged in
            # the main handler (event_message) at enqueue time.
            try:
                cmd_volume = float(cmd.get("Volume", 100))
            except (TypeError, ValueError):
                cmd_volume = 100.0
            override = self._group_volume_override(group)
            final_volume = override if override is not None else cmd_volume / 100.0
            final_volume = max(0.0, min(1.0, final_volume))

            sound_file = cmd.get("SoundFile", "")
            if sound_file:
                channel_id = self._category(group).get("audio_channel", 0)
                print(f"Playing queued sound: {sound_file} (Channel: {channel_id}, Volume: {final_volume})")
                await self.play_sound_sequentially(sound_file, final_volume, channel_id, group=group)

            cur = self.queue_current.get(group)
            if cur is not None and cur.get('skipped'):
                print(f"Queued command !{cmd_name} was skipped")
                return

            response = cmd.get("Response", "")
            if response:
                await self.send_multiline_response(message.channel, response, username,
                                                   values=self._response_values(message, cmd))
                print(f"Sent response for queued command !{cmd_name}")

            self._count_use(cmd, username)

            print(f"--- Finished execution of queued command: !{cmd_name} ---")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Error executing queued command !{cmd_name}: {e}")
            traceback.print_exc()

    async def play_sound_sequentially(self, sound_file, volume, channel_id=0, group=None):
        """Play sound and wait for it to finish on the specified channel.

        Decode + play run in an executor; completion is polled in the loop.
        Finishes early if the item is skipped or another sound takes over the
        channel (e.g. an interrupting sound on the shared channel 0).
        """
        sound_path = Path(sound_file)
        if not sound_path.is_absolute():
            sound_path = Path(self.config_manager.get_sound_config().get("sound_dir", "")) / sound_file

        if sound_path.is_dir():                    # a folder: a random sound from it
            from bot.audio import pick_sound
            picked = pick_sound(str(sound_path), self.__dict__.setdefault("_sound_picks", {}))
            sound_path = Path(picked) if picked else sound_path / "__no_sound__"
        if not sound_path.exists():
            print(f"Sound file not found: {sound_path}")
            return

        cur = self.queue_current.get(group) if group is not None else None
        if cur is not None and cur.get('skipped'):
            return

        sound = None
        try:
            def start_sound_blocking():
                sound = pygame.mixer.Sound(str(sound_path))
                sound.set_volume(volume)
                channel = pygame.mixer.Channel(channel_id) if channel_id > 0 else self.sound_channel
                print(f"--- PLAYING on channel {channel_id} (Internal: {channel}) ---")
                channel.play(sound)
                # Store the Sound (not the channel) so !volume can change
                # the volume during playback.
                with self.active_sounds_lock:
                    self.active_sounds[channel_id] = sound
                return sound, channel

            sound, channel = await self.loop.run_in_executor(None, start_sound_blocking)

            if cur is not None:
                cur['channel'] = channel
                cur['sound'] = sound
                if cur.get('skipped'):  # skipped while the file was loading
                    channel.stop()

            get_sound = getattr(channel, 'get_sound', None)
            while channel.get_busy():
                if cur is not None and cur.get('skipped'):
                    break
                if get_sound is not None:
                    try:
                        playing = get_sound()
                    except Exception:
                        playing = sound
                    if playing is not None and playing is not sound:
                        break  # someone else took over the channel
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Error playing queued sound {sound_file}: {e}")
            traceback.print_exc()
        finally:
            with self.active_sounds_lock:
                if sound is not None and self.active_sounds.get(channel_id) is sound:
                    self.active_sounds.pop(channel_id, None)
