import asyncio
import json
import os
import time
import pygame
import concurrent.futures
import threading
from twitchio.ext import commands
from twitchio.ext.commands import errors
from core.config_manager import ConfigManager
from pathlib import Path
import traceback
from core.currency_manager import CurrencyManager
from datetime import datetime, timezone
from typing import Union

from core.system_commands import merge_with_defaults, name_of as sys_cmd_name, QUEUE_COMMANDS
from bot.dispatcher import CommandDispatcher
from bot.audio import SoundCache, may_start
from bot.helix import HelixClient, logins as helix_logins
from bot.ui_port import BotUi, CallbackUi
from bot.queue import QueueMixin, _PersistedMessage, _QueueSlots  # noqa: F401


def _patch_twitchio_keep_alive():
    """Обход бага twitchio 2.x: переподключение после штатного закрытия.

    Когда Twitch закрывает WebSocket кадром close, aiohttp отдаёт сообщение
    типа CLOSE с числовым кодом (1000) в msg.data. WSConnection._keep_alive
    проверяет только CLOSED и вызывает data.split(...) у числа - задача
    падает с AttributeError, до _connect() дело не доходит, бот молчит
    навсегда (воспроизведено: tests/ui/check_twitch_reconnect.py).

    Здесь - тот же цикл, но любое закрывающее сообщение (CLOSE, CLOSING,
    CLOSED, ERROR) завершает его, после чего, как и в оригинале, вызывается
    _connect() с его экспоненциальной задержкой.
    """
    try:
        import aiohttp
        import twitchio
        from functools import partial
        from twitchio import websocket as tw_ws
    except Exception:
        return False  # нет настоящего twitchio (офлайн-тесты со заглушками)
    if not str(getattr(twitchio, "__version__", "")).startswith("2."):
        return False
    conn_cls = getattr(tw_ws, "WSConnection", None)
    if conn_cls is None or getattr(conn_cls, "_ce_keep_alive_patched", False):
        return False
    closing = (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING,
               aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR)

    async def _keep_alive(self):
        await self._ws_ready_event.wait()
        self._ws_ready_event.clear()

        if not self._last_ping:
            self._last_ping = time.time()
        while not self._websocket.closed and not self._reconnect_requested:
            msg = await self._websocket.receive()
            if msg.type in closing:
                tw_ws.log.error(f"Websocket connection was closed: {msg.type} {msg.data} {msg.extra}")
                break
            data = msg.data
            if data and isinstance(data, str):
                tw_ws.log.debug(f" < {data}")
                self.dispatch("raw_data", data)
                for event in data.split("\r\n"):
                    if not event:
                        continue
                    task = asyncio.create_task(self._process_data(event))
                    task.add_done_callback(partial(self._task_callback, event))
                    self._background_tasks.append(task)

        if not self._reconnect_requested:  # RECONNECT уже запустил _connect сам
            self._background_tasks.append(asyncio.create_task(self._connect()))

    conn_cls._keep_alive = _keep_alive
    conn_cls._ce_keep_alive_patched = True
    return True


_patch_twitchio_keep_alive()


# Twitch rejects chat messages longer than 500 characters.
_TWITCH_MSG_LIMIT = 480


def _fit_chat(text, limit=_TWITCH_MSG_LIMIT):
    """Single line, trimmed to Twitch's message length limit."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[:limit - 1].rstrip() + "…"


class TwitchBot(QueueMixin, CommandDispatcher, commands.Bot):
    _fit_chat = staticmethod(_fit_chat)  # для bot/dispatcher.py

    def __init__(self, channel, message_callback=None, commands_data=None, sound_channel=None, config_manager=None, currency_manager=None, ui=None, **kwargs):
        # Загружаем настройки Twitch
        if not config_manager:
            from core.config_manager import ConfigManager
            config_manager = ConfigManager()
        self.config_manager = config_manager
        
        config = self.config_manager.get_twitch_config()
        token = config.get('access_token')
        if token:
            if not token.startswith('oauth:'):
                token = f'oauth:{token}'
        
        # Set custom prefix for commands (change from ! to whatever you want)
        prefix = '!'
        
        # Initialize command bot
        super().__init__(
            token=token,
            prefix=prefix,
            initial_channels=[channel],
            # Добавляем важные capabilities для получения рейдов и других событий
            reconnect=True,
            capabilities=['tags', 'commands', 'membership'],
            **kwargs
        )

        # Инициализируем остальные параметры
        try:
            self.initialized_event = asyncio.Event()
            self.active_sounds_lock = threading.Lock()
            # Загружаем настройки прерывания звуков СРАЗУ при инициализации
            self.allow_sound_interruption = self.config_manager.get_sound_interruption()
            self.show_interruption_message = self.config_manager.get_interruption_message()
            
            # Инициализация для проигрывания звуков
            self.loaded_sounds = SoundCache(limit=32)
            if sound_channel:
                self.sound_channel = sound_channel
            else:
                # Initialize multiple channels
                pygame.mixer.set_num_channels(32)
                self.sound_channel = pygame.mixer.Channel(0)  # Канал 0 — дефолтный (общий)
            
            # Отладочное сообщение
            print(f"TwitchBot initialized with sound channel and interruption settings: allow_sound_interruption={self.allow_sound_interruption}")
            
            # Печатаем начальные значения для отладки
            print(f"TwitchBot initialized with interrupt settings: allow_sound_interruption={self.allow_sound_interruption}, show_interruption_message={self.show_interruption_message}")
            
            self.prefix = prefix
            
            # ⚠️ Важно использовать другое имя для списка команд, чтобы избежать конфликта
            self._commands_list = commands_data or []  # Вместо self.commands
            
            # Основные настройки
            self.channel = channel.lower()
            self.is_live = False
            self.is_running = True
            self.volume = 0.5
            # Всё, что бот сообщает окну программы, идёт через self.ui
            # (bot/ui_port.py; в окне это BotBridge - сигналы Qt, шаг 4.2).
            # О каждом срабатывании команды - ui.command_used(копия из
            # снимка); окно передаёт это в CommandRepository.record_use.
            if ui is None:
                ui = CallbackUi(message_callback) if message_callback else BotUi()
            self.ui = ui
            
            # Аудио и статус
            self.player = None
            self.paused = False
            
            # Наблюдение за соединением (переподключается сам twitchio, C2)
            self.connection_check_task = None
            # B7: фоновая проверка статуса стрима в loop бота — UI больше
            # не блокируется на future.result(timeout=5) каждые 10-300 с.
            self.stream_status_task = None
            self.stream_status_interval = 30
            
            # Отслеживание пользователей
            self.active_users = set([channel.lower()])  # Инициализируем с владельцем канала
            
            # ⚠️ Используем переданный currency_manager или создаем новый если не передан
            self.currency_manager = currency_manager or CurrencyManager()
            if hasattr(self.currency_manager, 'load_settings'):
                self.currency_manager.load_settings()
            
            # Инициализируем словарь для отслеживания кулдаунов
            self.global_cooldowns = {}  # {нормализованная_команда: время_последнего_использования}
            self.user_cooldowns = {}    # {нормализованная_команда: {пользователь: время_последнего_использования}
            
            # Заголовки для Helix
            client_id = config.get("client_id")
            bare_token = token[6:] if token.startswith("oauth:") else token
            self._helix_headers = {
                "Client-ID": client_id,
                "Authorization": f"Bearer {bare_token}"
            }
            
            # broadcaster_id запрашивается асинхронно в event_ready
            # (_ensure_broadcaster_id). Раньше - синхронный requests.get здесь,
            # без таймаута.
            self.broadcaster_id = None
            self.moderator_id = None
            self._helix = HelixClient(lambda: self._helix_headers)
            # список модераторов из Helix кэшируется (шаг 3.3)
            self._mods_cache = []
            self._mods_cache_time = 0.0

            print(f"Bot initialized with channel: {channel}")
            
            # Для отслеживания кулдаунов команд
            self.global_cooldowns = {}  # {команда: время_использования}
            self.user_cooldowns = {}    # {команда: {пользователь: время_использования}}
            
            # Отслеживание активных звуков по каналам для изменения громкости во время воспроизведения
            self.active_sounds = {}  # {channel_id: sound_object}

            # Command queue initialization
            self.command_queues = {}  # {group_name: asyncio.Queue} — только ожидающие
            self.queue_workers = {}   # {group_name: asyncio.Task}
            self.queue_processing = {} # {group_name: bool} — принимать/обрабатывать
            # {group_name: _QueueSlots|None} — совместимый с прежним API вид
            # «свободных мест» (._value). Лимит считается по факту:
            # ожидающие + текущий элемент, без семафоров, которые раньше
            # «утекали» при отмене воркера/перезагрузке настроек.
            self.queue_semaphores = {}
            # {group_name: dict} — что исполняется прямо сейчас
            # (message, cmd, started, channel, sound, skipped)
            self.queue_current = {}
            # Queue Control tab: группы на паузе
            self.queue_paused = set()

            # Stream status
            self.is_live = False
            self.stream_start_time = None
            
            # Инициализируем event loop, но НЕ запускаем workers пока loop не запущен
            self.loop = asyncio.get_event_loop()
            # init_queues() вызывается в event_ready после запуска loop

        except Exception as e:
            print(f"CRITICAL ERROR in __init__: {e}")
            import traceback
            traceback.print_exc()
    
    # Свойство для безопасного доступа к commands через _commands_list
    @property
    def commands(self):
        return self._commands_list
    
    def _normalize_group(self, group):
        """Return the canonical group name from audio_categories (case-insensitive).

        Commands may carry 'song' while the category is 'SONG'; without this
        mapping the command silently falls back to the shared channel 0.
        """
        if not group:
            return group
        categories = self.config_manager.get_audio_categories()
        if group in categories:
            return group
        for name in categories:
            if str(name).upper() == str(group).upper():
                return name
        return group

    def update_commands(self, commands_list):
        """Вызывается из CommandEditor после каждой правки таблицы.

        Может прийти из UI-потока: init_queues сам перенаправит себя в loop
        бота (asyncio-объекты нельзя трогать из чужого потока).
        """
        old_commands_count = len(self._commands_list)
        self._commands_list = commands_list or []
        # Normalize group names to the canonical audio_categories keys so that
        # 'song' / 'Song' / 'SONG' all resolve to the same category.
        for cmd in self._commands_list:
            g = cmd.get("Group")
            if g:
                cmd["Group"] = self._normalize_group(g)
        print(f"DEBUG: update_commands called. Old count: {old_commands_count}, New count: {len(self._commands_list)}")
        self.init_queues()  # Re-initialize queues to pick up new groups

    async def event_ready(self):
        print(f"Bot is ready! Connected to {self.channel}")
        # Ensure self.loop references the correct asyncio loop for run_coroutine_threadsafe
        self.loop = asyncio.get_event_loop()
        try:
            await self._ensure_broadcaster_id()
            # Загрузка списка зрителей сразу при первом подключении
            viewers = await self.get_all_viewers()
            print(f"Initial viewers loaded: {len(viewers)} viewers")
            
            # Получаем и обновляем список модераторов канала
            print("Getting channel moderators...")
            mods = await self.get_channel_moderators()
            print(f"Retrieved {len(mods)} moderators")
            
            # первоначально активные зрители - тот же список
            self.active_users = set(viewers)
            self._notify("all_viewers", viewers)
            self._notify("chat", f"Connected to {self.channel}. Loaded {len(viewers)} viewers.")
            self._notify("active_viewers", list(self.active_users))
            
            # Проверка статуса стрима
            is_live = await self.check_if_live()
            # Сигналим UI о статусе стрима
            self.is_live = is_live
            self._notify("stream_status", is_live)

            # Запускаем периодическую проверку соединения, если не запущена
            if not self.connection_check_task or self.connection_check_task.done():
                self.connection_check_task = asyncio.create_task(self._check_connection())

            # B7: фоновая проверка статуса стрима в loop бота. UI-поток больше
            # не делает future.result(timeout=5) — статус приходит по сигналу.
            if not self.stream_status_task or self.stream_status_task.done():
                self.stream_status_task = asyncio.create_task(self._stream_status_loop())
            
            # Start queue workers now that we have a running loop
            print("Initializing command queues and workers...")
            self.init_queues()

            # Unblock waiting event_message coro routines
            self.initialized_event.set()

        except Exception as e:
            print(f"CRITICAL ERROR in event_ready: {e}")
            import traceback; traceback.print_exc()

    async def send_chat(self, text):
        """Сообщение в чат канала из окна программы. False - канал ещё не
        подключён (connected_channels читается здесь, в loop бота)."""
        chans = self.connected_channels
        if not chans:
            return False
        await chans[0].send(_fit_chat(text))
        return True

    async def send_multiline_response(self, channel, response_text, username):
        """
        Отправляет многострочный ответ, где каждая строка отправляется отдельным сообщением.
        Строки, содержащие только пробелы, создают задержку в 1 секунду.
        """
        if not response_text or not response_text.strip():
            return
            
        # Разбиваем ответ на строки
        lines = response_text.split('\n')
        
        for line in lines:
            # Проверяем, содержит ли строка только пробелы (задержка)
            if line.isspace() or line == '':
                # Создаем задержку в 0.2 секунды
                await asyncio.sleep(0.2)
                continue

            # Заменяем {user} на имя пользователя
            formatted_line = line.replace("{user}", username)
            
            # Отправляем непустую строку как отдельное сообщение
            if formatted_line.strip():
                await channel.send(formatted_line)
                # Небольшая задержка между сообщениями для избежания rate limit
                await asyncio.sleep(0.1)

    async def event_message(self, message):
        # Игнорируем эхо собственного бота
        if message.echo:
            return

        # Wait for bot to be initialized
        await self.initialized_event.wait()

        # Выводим сообщение в UI
        self._notify("chat", f"{message.author.name}: {message.content}")

        # Получаем только первое слово в нижнем регистре как ключ команды
        content = message.content.strip()
        if not content.startswith("!"):
            return

        # Нормализуем ключ команды без префикса и в lowercase
        raw_key = content[1:].split(maxsplit=1)[0].lower()
        # Удаляем невидимые символы и пробелы для нормализации команды
        key = self.normalize_command_key(raw_key)
        username = message.author.name.lower()
        current_time = time.time()
        
        # Для отладки
        if raw_key != key:
            print(f"Command normalized: '{raw_key}' -> '{key}'")
        
        if not key:  # Проверка на пустую команду после нормализации
            print("Empty command after normalization, ignoring")
            return
            
        # Системные команды. !queue/!skip/!clear/!volume - такие же, как
        # остальные: Enabled, права, кулдаун и цена из Sys.Commands (S8;
        # раньше они перехватывались здесь до настроек). Без файла настроек
        # действуют значения по умолчанию (core.system_commands).
        system_commands, _ = merge_with_defaults(self.config_manager.load_system_commands())
        for sys_cmd in system_commands:
            # Skip disabled commands
            if not sys_cmd.get("enabled", False):
                continue

            # Get the command name (original or custom name for duplicates)
            cmd_name = sys_cmd_name(sys_cmd)
            cmd_key = self.normalize_command_key(cmd_name.lstrip('!'))
            
            # Check if the message matches this system command
            if key == cmd_key:
                if not await self.has_permission(message, sys_cmd.get("permission")):
                    await message.channel.send(f"@{username}: You don't have permission to use this command.")
                    return
                
                # Check cooldowns
                cooldown_min = int(sys_cmd.get("cooldown", 0))
                user_cooldown_min = int(sys_cmd.get("user_cooldown", 0))
                cooldown_sec = cooldown_min * 60
                user_cooldown_sec = user_cooldown_min * 60
                
                # Global cooldown check
                if cooldown_sec > 0:
                    last_used = self.global_cooldowns.get(cmd_key, 0)
                    elapsed = current_time - last_used
                    if elapsed < cooldown_sec:
                        remaining = int(cooldown_sec - elapsed)
                        await message.channel.send(
                            f"@{username}: command is on cooldown. Try in {remaining} sec."
                        )
                        return
                
                # User cooldown check
                if user_cooldown_sec > 0:
                    last_used = self.user_cooldowns.get(cmd_key, {}).get(username, 0)
                    elapsed = current_time - last_used
                    if elapsed < user_cooldown_sec:
                        remaining = int(user_cooldown_sec - elapsed)
                        await message.channel.send(
                            f"@{username}: you can use this command in {remaining} sec."
                        )
                        return
                
                # Check command cost
                cost = int(sys_cmd.get("cost", 0))
                if cost > 0:
                    # Check if user has enough points
                    current_points = self.currency_manager.get_points(username)
                    if current_points < cost:
                        formatted_points = f"{float(current_points):.2f}"
                        await message.channel.send(
                            f"@{username}: Not enough points. Cost: {cost} (you have {formatted_points})"
                        )
                        return
                    
                    # Deduct points
                    if not self.currency_manager.pay_for_command(username, cost):
                        formatted_points = f"{float(current_points):.2f}"
                        await message.channel.send(
                            f"@{username}: Payment error. Cost: {cost} (you have {formatted_points})"
                        )
                        return
                
                # Кулдаун - ДО выполнения: пока ответ отправляется (await),
                # второй вызов той же команды уже видит кулдаун.
                if cooldown_sec > 0:
                    self.global_cooldowns[cmd_key] = current_time
                if user_cooldown_sec > 0:
                    self.user_cooldowns.setdefault(cmd_key, {})[username] = current_time

                # Execute the command based on its type
                await self.execute_system_command(message, username, sys_cmd, content)

                return  # Command processed, exit the event_message method

        # Обычные команды: один конвейер (bot/dispatcher.py, шаг 3.1)
        for cmd in getattr(self, "_commands_list", []):
            if not cmd.get("Enabled", False):
                continue
            cmd_key = self.normalize_command_key(cmd["Command"].lstrip(self.prefix).lower())
            if cmd_key != key:
                continue
            print(f"Command matched: '{key}' (cost {cmd.get('Cost', 0)})")
            await self.run_command(message, cmd)
            return

        # Если не нашли команду среди своих - пробуем встроенные
        try:
            await self.handle_commands(message)
        except errors.CommandNotFound:
            pass  # игнорируем, если и тут не найдено

    async def event_command_error(self, ctx, error):
        if isinstance(error, errors.CommandNotFound):
            return
        # остальное бросаем дальше
        raise error

    def set_interruption(self, enabled):
        """Установить, разрешено ли прерывание звуков."""
        self.allow_sound_interruption = enabled
        print(f"Bot interruption attribute set to: {self.allow_sound_interruption}")

    def set_show_interruption_message(self, enabled):
        """Установить, показывать ли сообщение о блокировке звука."""
        self.show_interruption_message = enabled
        print(f"Bot show interruption message attribute set to: {self.show_interruption_message}")
    
    def set_volume(self, volume):
        """Устарело: общая громкость не используется, у каждой команды своя громкость"""
        try:
            print(f"Note: set_volume({volume:.2f}) called but individual command volumes are used instead")
            # Сохраним значение для совместимости со старым кодом
            self.volume = volume
        except Exception as e:
            print(f"CRITICAL ERROR in set_volume: {e}")
            import traceback
            traceback.print_exc()
    
    def stop(self):
        """Stop the bot gracefully"""
        try:
            print("Stopping Twitch bot...")
            self.is_running = False

            # Unblock any waiting event_message coroutines
            self.initialized_event.set()

            # Отключаемся от канала
            if hasattr(self, 'loop') and self.loop:
                # stop() вызывается из UI-потока: задачи asyncio отменяем
                # через loop бота, а не напрямую (инвариант потоков).
                for task in (self.connection_check_task, getattr(self, 'stream_status_task', None)):
                    if task is not None and not task.done():
                        try:
                            self.loop.call_soon_threadsafe(task.cancel)
                        except RuntimeError:
                            pass  # loop уже закрыт
                
                # Now disconnect
                try:
                    asyncio.run_coroutine_threadsafe(self.close(), self.loop)
                    # Give a moment for the disconnect to process
                    time.sleep(0.5)
                except Exception as e:
                    print(f"Error during disconnect: {e}")
            
            # Останавливаем аудио
            if pygame.mixer and pygame.mixer.get_init():
                pygame.mixer.stop()
                
            print("Bot stopped successfully")
        except Exception as e:
            print(f"CRITICAL ERROR in stop: {e}")
            import traceback
            traceback.print_exc()
    
    async def reload_audio_categories(self):
        """Apply new Group Settings to the running bot.

        Workers are NOT cancelled any more: the old code cancelled them and
        reset the "processing" flag, which (1) cut the playing track short and
        (2) left every queue dead until restart, because init_queues never
        turned the flag back on for an existing queue. Settings (limit,
        channel, persistence) are read live, so re-running init_queues is
        enough: it starts queues for newly enabled groups and lets disabled
        ones drain.
        """
        print("Reloading audio categories...")
        self.init_queues()
        print("Audio categories reloaded successfully")
    
    def play_sound(self, filepath, volume=100, channel_id=0):
        """Проигрывание звукового файла с учетом настроек прерывания и громкости
        Возвращает True, если звук был успешно запущен, False в противном случае"""
        try:
            # Проверка существования файла
            if not os.path.exists(filepath):
                print(f"Sound file not found: {filepath}")
                return False

            # Канал группы (>0) или общий (0). Правило прерывания - одно для
            # всех каналов (bot/audio.py): раньше на канале группы без очереди
            # новый звук всегда обрывал старый, настройку не спрашивая.
            channel = pygame.mixer.Channel(channel_id) if channel_id > 0 else self.sound_channel
            allow_interrupt = getattr(self, 'allow_sound_interruption', False)
            if not may_start(channel, allow_interrupt):
                print(f"Blocking sound on channel {channel_id}: another sound is playing")
                return False

            # Кэш с ограничением, замечает замену файла (bot/audio.py)
            snd = self.loaded_sounds.get(filepath)

            # Применяем громкость команды (из параметра volume)
            vol = float(volume) / 100.0
            print(f"Setting sound volume to: {vol} (from command volume: {volume})")
            snd.set_volume(vol)

            # Воспроизводим на выбранном канале
            channel.play(snd)
            print(f"Playing sound: {filepath} on channel {channel_id}")
            
            # Track active sound for real-time volume control
            # IMPORTANT: Store the sound object, not the channel!
            # This allows !volume to change volume during playback
            with self.active_sounds_lock:
                self.active_sounds[channel_id] = snd
            
            return True  # Звук успешно запущен

        except Exception as e:
            print(f"CRITICAL ERROR in play_sound: {e}")
            traceback.print_exc()
            return False  # В случае ошибки

    # ------------------------------------------------------------------
    # Twitch API (Helix over aiohttp, bot/helix.py)
    # ------------------------------------------------------------------
    MODS_CACHE_SECONDS = 300

    async def _ensure_broadcaster_id(self):
        if self.broadcaster_id:
            return self.broadcaster_id
        status, data = await self._helix.get("users", login=self.channel)
        try:
            if status == 200 and data.get("data"):
                self.broadcaster_id = str(data["data"][0]["id"])
                self.moderator_id = self.broadcaster_id
        except Exception as e:
            print(f"Error reading broadcaster ID: {e}")
        if not self.broadcaster_id:
            print(f"Could not get broadcaster ID for {self.channel} (status {status})")
        return self.broadcaster_id

    async def close(self):
        try:
            await self._helix.close()
        except Exception:
            pass
        await super().close()

    async def get_all_viewers(self) -> list:
        """Chatters via Helix /chat/chatters; falls back to the active users."""
        viewers = []
        if self.broadcaster_id and self.moderator_id:
            status, data = await self._helix.get(
                "chat/chatters", broadcaster_id=self.broadcaster_id, moderator_id=self.moderator_id)
            if status == 200:
                viewers = helix_logins(data)
            elif status:
                print(f"Error getting chatters via Helix: status {status}")
        if not viewers:
            viewers = list(getattr(self, "active_users", [self.channel.lower()]))
        self.all_viewers = viewers
        return viewers

    async def _stream_status_loop(self):
        """B7: фоновая проверка статуса стрима в loop бота.

        Раньше UI-поток сам вызывал check_if_live через
        run_coroutine_threadsafe(...).result(timeout=5) — интерфейс
        блокировался на время запроса к Helix. Теперь статус обновляется
        здесь, в loop, и сообщается UI по stream_status_signal.
        """
        while self.is_running:
            try:
                is_live = await self.check_if_live()
                self.is_live = is_live
                self._notify("stream_status", is_live)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"Error in stream status loop: {e}")
            await asyncio.sleep(self.stream_status_interval)

    async def check_if_live(self, *args) -> bool:
        """Проверяем, идет ли стрим в текущий момент через Helix API
        (aiohttp, bot/helix.py - loop бота не блокируется)."""
        try:
            if not self.broadcaster_id or not self._helix_headers:
                print("Cannot check stream status: missing broadcaster_id or API headers")
                return False

            status, data = await self._helix.get("streams", user_id=self.broadcaster_id)

            # Если запрос успешен
            if status == 200 and data is not None:
                stream_info = data.get("data", [])
                # Если есть данные, значит стрим идёт
                is_live = len(stream_info) > 0

                if is_live:
                    self.stream_start_time = stream_info[0].get("started_at")
                else:
                    self.stream_start_time = None

                # Если статус изменился, логируем это
                if is_live != self.is_live:
                    status_msg = "LIVE" if is_live else "OFFLINE"
                    print(f"Stream status changed to: {status_msg}")

                return is_live
            else:
                print(f"Error checking stream status: API returned {status}")
                # В случае ошибки API сохраняем текущий статус
                return self.is_live

        except Exception as e:
            print(f"Error checking stream status: {e}")
            # В случае ошибки сохраняем текущий статус
            return self.is_live

    async def get_user_id(self, login: str) -> Union[str, None]:
        """user_id by login via Helix (None if unknown or the API failed)."""
        status, data = await self._helix.get("users", login=login)
        try:
            if status == 200 and data.get("data"):
                return data["data"][0]["id"]
        except Exception as e:
            print(f"Error reading user id for {login}: {e}")
        return None

    async def get_channel_moderators(self):
        """Получает список модераторов канала через API и объединяет с ручным списком"""
        try:
            # Получаем ручной список модераторов
            manual_mods = []
            excluded_mods = []
            if hasattr(self, 'config_manager'):
                manual_mods = self.config_manager.get_manual_moderators()
                excluded_mods = self.config_manager.get_excluded_moderators()
            
            api_mods = []
            # Пытаемся получить модераторов через API
            if self.broadcaster_id and self._helix_headers:
                # Запрашиваем данные о модераторах
                status, data = await self._helix.get(
                    "moderation/moderators", broadcaster_id=self.broadcaster_id)
                if status == 200 and data is not None:
                    # Перебираем всех модераторов
                    for mod in data.get("data", []):
                        mod_name = mod.get("user_login", "").lower()
                        
                        # Пропускаем исключенных модераторов
                        if mod_name in excluded_mods:
                            print(f"User {mod_name} excluded from moderators list")
                            continue
                            
                        api_mods.append(mod_name)
                        
                        # Обновляем статус модератора в системе валюты
                        if hasattr(self, 'currency_manager') and mod_name in self.currency_manager.users:
                            self.currency_manager.users[mod_name]['is_mod'] = True
                            print(f"User {mod_name} marked as moderator (API)")
                else:
                    print(f"Error fetching moderators: API returned {status}")
            else:
                print("Cannot fetch moderators: missing broadcaster_id or API headers")
            
            # Объединяем списки (API + ручные), исключая заблокированных
            all_mods = set(api_mods + manual_mods)
            mods = [mod for mod in all_mods if mod not in excluded_mods]
            
            # Дополнительно добавляем владельца канала как модератора
            if self.channel.lower() not in mods:
                mods.append(self.channel.lower())
            
            # Обновляем статус модераторов в системе валюты для всех
            if hasattr(self, 'currency_manager'):
                for mod_name in mods:
                    if mod_name in self.currency_manager.users:
                        self.currency_manager.users[mod_name]['is_mod'] = True
                        print(f"User {mod_name} marked as moderator")
                
                # Убираем статус модератора у исключенных пользователей
                for excluded_mod in excluded_mods:
                    if excluded_mod in self.currency_manager.users:
                        self.currency_manager.users[excluded_mod]['is_mod'] = False
                        print(f"User {excluded_mod} excluded from moderators")
                
                # Отмечаем владельца канала (если он не в исключенных)
                if self.channel.lower() not in excluded_mods and self.channel.lower() in self.currency_manager.users:
                    self.currency_manager.users[self.channel.lower()]['is_mod'] = True
                    print(f"Channel owner {self.channel} marked as moderator")
                
                # Сохраняем изменения в системе валюты
                self.currency_manager.save_users()
            
            self._notify("moderators", mods)

            self._mods_cache = list(mods)
            self._mods_cache_time = time.time()
            return mods
                
        except Exception as e:
            print(f"Error fetching moderators: {e}")
            # В случае ошибки возвращаем хотя бы ручной список
            manual_mods = []
            if hasattr(self, 'config_manager'):
                manual_mods = self.config_manager.get_manual_moderators()
            
            # Добавляем владельца канала
            if self.channel.lower() not in manual_mods:
                manual_mods.append(self.channel.lower())
            
            return manual_mods

    # Уровни прав, для которых нужен модератор. "Admin" пока равен
    # модератору (docs/refactor-plan.md, решение 1). Прочие уровни из
    # бэкапов Streamlabs (Regular, Subscriber, ...) открыты всем, как раньше.
    _MOD_PERMISSIONS = ("moderator", "admin", "editor", "caster")

    async def has_permission(self, message, required):
        """Может ли автор сообщения вызвать команду с правом `required`.

        Для "Everyone" ничего не проверяется. Бейдж модератора/владельца из
        тегов IRC решает сразу, без запроса к Twitch API; иначе - прежняя
        проверка is_user_moderator. Исключённые модераторы - всегда нет.
        """
        level = str(required or "everyone").strip().lower()
        if level not in self._MOD_PERMISSIONS:
            return True
        author = message.author
        username = author.name.lower()
        try:
            if username in self.config_manager.get_excluded_moderators():
                return False
        except Exception:
            pass
        if username == str(self.channel).lower():
            return True
        for attr in ("is_broadcaster", "is_mod"):
            try:
                if getattr(author, attr, False) is True:
                    return True
            except Exception:
                pass
        return await self.is_user_moderator(username)

    async def is_user_moderator(self, username):
        """Проверяет, является ли пользователь модератором канала"""
        # Нормализуем имя пользователя
        username = username.lower()
        
        print(f"DEBUG: Checking moderator status for user: {username}")
        
        # Сначала проверяем, не исключен ли пользователь
        if hasattr(self, 'config_manager'):
            excluded_mods = self.config_manager.get_excluded_moderators()
            print(f"DEBUG: Excluded moderators: {excluded_mods}")
            if username in excluded_mods:
                print(f"DEBUG: User {username} is in excluded moderators list - DENYING ACCESS")
                return False
        
        # Владелец канала всегда считается модератором (если не исключен)
        if username == self.channel.lower():
            print(f"DEBUG: User {username} is channel owner - GRANTING ACCESS")
            return True
            
        # Проверяем, есть ли у пользователя флаг модератора в системе валюты
        if hasattr(self, 'currency_manager') and username in self.currency_manager.users:
            is_mod_in_currency = self.currency_manager.users[username].get('is_mod', False)
            print(f"DEBUG: User {username} is_mod in currency_manager: {is_mod_in_currency}")
            if is_mod_in_currency:
                print(f"DEBUG: User {username} has mod flag in currency manager - GRANTING ACCESS")
                return True
                
        # Используем get_channel_moderators для получения актуального списка модераторов
        try:
            # Список модераторов кэшируется на MODS_CACHE_SECONDS: раньше
            # каждая команда зрителя-не-модератора шла в Twitch API (C3).
            if time.time() - self._mods_cache_time > self.MODS_CACHE_SECONDS:
                await self.get_channel_moderators()
            moderators = self._mods_cache
            is_in_mod_list = username in moderators
            print(f"DEBUG: User {username} in channel moderators list: {is_in_mod_list}")
            if is_in_mod_list:
                print(f"DEBUG: User {username} found in channel moderators - GRANTING ACCESS")
            else:
                print(f"DEBUG: User {username} NOT found in channel moderators - DENYING ACCESS")
            return is_in_mod_list
        except Exception as e:
            print(f"DEBUG: Error checking moderator status: {e}")
            print(f"DEBUG: User {username} - error occurred, DENYING ACCESS by default")
            # По умолчанию не модератор при ошибке
            return False
            
    def _count_use(self, cmd):
        """+1 к счётчику своей копии и сообщение редактору."""
        try:
            cmd["Count"] = int(cmd.get("Count", 0) or 0) + 1
        except (TypeError, ValueError):
            pass
        self._notify("command_used", cmd)

    def _notify(self, what, *args):
        """Сообщить окну (self.ui). Окно не может сломать бота: ошибки
        только печатаются."""
        try:
            getattr(self.ui, what)(*args)
        except Exception as e:
            print(f"UI report {what} failed: {e}")

    def _ui_message(self, text):
        """Служебное сообщение в окно чата программы (не в Twitch)."""
        self._notify("chat", text)

    def _connection_alive(self):
        conn = getattr(self, '_connection', None)
        if conn is None:
            return False
        try:
            # Только открытый сокет: is_ready twitchio 2.10 после повторного
            # входа больше не выставляет (его логика 353 - для первого входа).
            return bool(conn.is_alive)
        except Exception:
            return False

    async def _check_connection(self):
        """Следить за соединением и сообщать интерфейсу (C2, решение 4).

        Переподключается сам twitchio: heartbeat aiohttp замечает обрыв,
        WSConnection._keep_alive вызывает _connect() с экспоненциальной
        задержкой, после входа снова приходит event_ready. Здесь только
        статус для UI и периодическая уборка кулдаунов. Раньше тут было
        самописное переподключение: оно сбрасывало initialized_event и не
        всегда возвращало его, искало self._ws (в twitchio 2.10 его нет) -
        и бот замолкал насовсем.
        """
        was_alive = self._connection_alive()
        lost_at = None
        last_cleanup = time.time()
        try:
            while self.is_running:
                await asyncio.sleep(getattr(self, '_watch_interval', 10))
                now = time.time()
                if now - last_cleanup >= 300:
                    last_cleanup = now
                    self.cleanup_cooldowns()
                alive = self._connection_alive()
                if was_alive and not alive:
                    lost_at = now
                    print("Connection to Twitch lost - twitchio is reconnecting")
                    self._ui_message("Connection to Twitch lost, reconnecting automatically...")
                elif alive and not was_alive and lost_at is not None:
                    print(f"Connection to Twitch restored after {now - lost_at:.0f}s")
                    self._ui_message("Connection to Twitch restored.")
                    lost_at = None
                was_alive = alive
        except asyncio.CancelledError:
            print("Connection watch task cancelled")

    async def event_reconnect(self):
        """Twitch попросил переподключиться (RECONNECT) - twitchio делает это
        сам; обработку сообщений не останавливаем."""
        print("Twitch requested a reconnect - twitchio is reconnecting")
        self._ui_message("Twitch asked to reconnect, reconnecting automatically...")

    async def event_raw_usernotice(self, channel, tags):
        """Рейды и подписки приходят из чата как USERNOTICE (S7).

        Раньше здесь были event_raid / event_subscription / event_follow -
        в twitchio 2.x таких событий нет, они не вызывались ни разу. Награды
        считает bot.events.usernotice_rewards по настройкам валюты; фолловы
        через чат не приходят (будут через EventSub, решение 3).
        """
        try:
            from bot.events import usernotice_rewards
            currency = getattr(self, 'currency_manager', None)
            if currency is None:
                return
            rewards = usernotice_rewards(tags, currency.settings)
            for r in rewards:
                currency.add_points(r.user, r.points)
                if r.subscriber and r.user in currency.users:
                    currency.users[r.user]['is_subscriber'] = True
                print(r.ui)
                self._notify("chat", r.ui)
                if r.chat:
                    try:
                        await channel.send(_fit_chat(r.chat))
                    except Exception as e:
                        print(f"Could not send thank-you message: {e}")
            if rewards:
                currency.save_users(force=True)
        except Exception as e:
            print(f"Error handling USERNOTICE {tags.get('msg-id') if tags else None}: {e}")
            traceback.print_exc()

    def register_commands(self):
        """Регистрация встроенных команд бота"""
        try:
            @self.command(name="points")
            async def cmd_points(ctx):
                """Показать баланс пользователя"""
                user = ctx.author.name.lower()
                currency_name = self.currency_manager.get_currency_name()
                points = self.currency_manager.get_points(user)
                hours = self.currency_manager.get_hours(user)
                rank = self.currency_manager.get_rank(user)
                
                # Format points with 2 decimal places and hours in the format "1h15m"
                formatted_points = f"{float(points):.2f}"
                formatted_hours = self.currency_manager.format_hours(hours)
                
                rank_text = f" [{rank}]" if rank else ""
                await ctx.send(f"{ctx.author.name}{rank_text} - Hours: {formatted_hours} - {currency_name}: {formatted_points}")

            @self.command(name="points_add")
            async def cmd_points_add(ctx, target: str = None, amount: int = None):
                """Добавить очки пользователю (только для модераторов)"""
                username = ctx.author.name.lower()
                print(f"DEBUG: Command !points_add called by user: {username}")
                
                is_mod = await self.is_user_moderator(username)
                print(f"DEBUG: is_user_moderator returned {is_mod} for user {username}")
                
                if not is_mod:
                    print(f"DEBUG: DENYING command access to {username}")
                    await ctx.send(f"@{ctx.author.name}: You don't have permission to use this command")
                    return
                
                print(f"DEBUG: GRANTING command access to {username}")
                
                if not target or not amount:
                    await ctx.send("Usage: !points_add <username> <amount>")
                    return

                try:
                    target = target.lower()
                    # Убираем @ если есть
                    if target.startswith("@"):
                        target = target[1:]

                    amount = int(amount)
                    self.currency_manager.add_points(target, amount)
                    await ctx.send(f"Successfully given {target} {amount} {self.currency_manager.get_currency_name()}")
                except ValueError:
                    await ctx.send("Amount must be a number")

            @self.command(name="points_remove")
            async def cmd_points_remove(ctx, target: str = None, amount: int = None):
                """Удалить очки у пользователя (только для модераторов)"""
                username = ctx.author.name.lower()
                print(f"DEBUG: Command !points_remove called by user: {username}")
                
                is_mod = await self.is_user_moderator(username)
                print(f"DEBUG: is_user_moderator returned {is_mod} for user {username}")
                
                if not is_mod:
                    print(f"DEBUG: DENYING command access to {username}")
                    await ctx.send(f"@{ctx.author.name}: You don't have permission to use this command")
                    return
                
                print(f"DEBUG: GRANTING command access to {username}")

                if not target or not amount:
                    await ctx.send("Usage: !points_remove <username> <amount>")
                    return

                try:
                    target = target.lower()
                    # Убираем @ если есть
                    if target.startswith("@"):
                        target = target[1:]

                    amount = int(amount)
                    self.currency_manager.add_points(target, -amount)
                    await ctx.send(f"Successfully removed {amount} {self.currency_manager.get_currency_name()} from {target}")
                except ValueError:
                    await ctx.send("Amount must be a number")

            print("Built-in bot commands registered successfully.")
        except Exception as e:
            print(f"Error registering built-in commands: {e}")
            traceback.print_exc()

    def normalize_command_key(self, key):
        """Нормализует ключ команды, удаляя невидимые символы и пробелы"""
        if not key:
            return ""
            
        # Превращаем в нижний регистр
        key = key.lower()
        
        # Сначала удаляем все невидимые символы (Unicode категории C)
        # и символы-разделители пробельного типа
        normalized = ''
        for c in key:
            if c.isprintable() and not c.isspace():
                normalized += c
                
        # Для дополнительной безопасности обрабатываем вариации имен команд
        normalized = normalized.replace('!', '')  # Удаляем префиксы команд если они остались
        
        # Логирование при обнаружении изменений
        if normalized != key and key:
            print(f"Command key normalized: '{key}' -> '{normalized}'")
            
        return normalized
    
    def cleanup_cooldowns(self):
        """Очищает кулдауны от устаревших записей и нормализует ключи команд"""
        try:
            current_time = time.time()
            max_age = 3600  # удаляем кулдауны старше 1 часа
            
            # Временные словари для нормализованных ключей
            new_global_cooldowns = {}
            new_user_cooldowns = {}
            
            # Очищаем и нормализуем global_cooldowns
            for cmd, timestamp in list(self.global_cooldowns.items()):
                # Пропускаем устаревшие записи
                if current_time - timestamp > max_age:
                    continue
                    
                # Нормализуем ключ команды
                normalized_cmd = self.normalize_command_key(cmd)
                if normalized_cmd:  # Пропускаем пустые ключи
                    new_global_cooldowns[normalized_cmd] = timestamp
            
            # Очищаем и нормализуем user_cooldowns
            for cmd, users in list(self.user_cooldowns.items()):
                normalized_cmd = self.normalize_command_key(cmd)
                if not normalized_cmd:  # Пропускаем пустые ключи
                    continue
                    
                new_users = {}
                for username, timestamp in users.items():
                    # Пропускаем устаревшие записи
                    if current_time - timestamp > max_age:
                        continue
                        
                    # Добавляем актуальные записи
                    new_users[username] = timestamp
            
                if new_users:  # Только если есть актуальные записи
                    new_user_cooldowns[normalized_cmd] = new_users
            
            # Заменяем словари на новые, нормализованные
            self.global_cooldowns = new_global_cooldowns
            self.user_cooldowns = new_user_cooldowns
            
            print(f"Cooldowns cleaned up: {len(self.global_cooldowns)} global, {len(self.user_cooldowns)} user commands")
            
            # Заменяем словари на новые, нормализованные
            self.global_cooldowns = new_global_cooldowns
            self.user_cooldowns = new_user_cooldowns
            
            print(f"Cooldowns cleaned up: {len(self.global_cooldowns)} global, {len(self.user_cooldowns)} user commands")
            
        except Exception as e:
            print(f"Error cleaning up cooldowns: {e}")
            import traceback
            traceback.print_exc()

    async def handle_queue_commands(self, message, cmd_key, content):
        """Handle queue management commands (!queue, !skip, !clear, !volume).

        Group names are case-insensitive everywhere. Replies are single-line
        and trimmed to Twitch's length limit (a newline inside one IRC
        message used to break the reply).
        """
        username = message.author.name.lower()
        args = content.split()

        async def reply(text):
            await message.channel.send(_fit_chat(f"@{username}: {text}"))

        # !queue [group]
        if cmd_key == "queue":
            if len(args) > 1:
                group = self._find_queue_group(args[1])
                if group is None:
                    await reply(f"Queue group '{args[1]}' not found.")
                    return
                snap = self.queue_snapshot(group)
                parts = []
                if snap['current']:
                    cur = snap['current']
                    parts.append(f"now: !{cur['command']} ({cur['user']})")
                pending = snap['pending']
                if pending:
                    listed = ", ".join(
                        f"{pos}. !{p['command']} ({p['user']})"
                        for pos, p in enumerate(pending[:15], start=1))
                    if len(pending) > 15:
                        listed += f" … +{len(pending) - 15} more"
                    parts.append(f"next ({len(pending)}): {listed}")
                if not parts:
                    await reply(f"Queue '{group}' is empty.")
                else:
                    paused = " [paused]" if snap['paused'] else ""
                    await reply(f"Queue '{group}'{paused} — " + " | ".join(parts))
            else:
                active = []
                for grp in self.command_queues:
                    n = self.queue_pending_count(grp)
                    if n > 0:
                        active.append(f"{grp}: {n}")
                if active:
                    await reply(f"Active queues: {', '.join(active)}")
                else:
                    await reply("All queues are empty.")
            return

        # Права проверены по настройкам Sys.Commands до вызова (S8).

        # !skip            - skip what is playing (the only active queue, else channel 0)
        # !skip GROUP      - skip the group's current item
        # !skip COMMAND    - remove that command's last pending entry
        if cmd_key == "skip":
            if len(args) > 1:
                target = args[1]
                group = self._find_queue_group(target)
                if group is not None:
                    if self.skip_queue_current(group):
                        await reply(f"Skipped current item in '{group}'.")
                    else:
                        await reply(f"Nothing is playing in '{group}'.")
                    return
                name = target.lstrip('!').strip()
                for grp in list(self.command_queues):
                    if self.remove_from_queue_by_name(grp, name):
                        await reply(f"Removed '!{name}' from queue '{grp}'.")
                        return
                await reply(f"'{target}' not found in any queue.")
                return

            playing = list(self.queue_current)
            if len(playing) == 1:
                self.skip_queue_current(playing[0])
                await reply(f"Skipped current item in '{playing[0]}'.")
            elif len(playing) > 1:
                await reply("Several queues are playing, use !skip <group>: " + ", ".join(playing))
            elif self.sound_channel is not None and self.sound_channel.get_busy():
                self.sound_channel.stop()
                await reply("Skipped current sound.")
            else:
                await reply("No sound is currently playing.")
            return

        # !clear <group>
        if cmd_key == "clear":
            if len(args) < 2:
                await reply("Usage: !clear <group_name>")
                return
            group = self._find_queue_group(args[1])
            if group is None:
                await reply(f"Queue group '{args[1]}' not found.")
                return
            count = self.clear_queue(group)
            await reply(f"Cleared {count} commands from '{group}' queue.")
            return

        # !volume [group] <0-100>
        if cmd_key == "volume":
            try:
                default_group = "SONG"
                try:
                    for _sc in self.config_manager.load_system_commands():
                        if _sc.get("command", "").lower() == "!volume" and _sc.get("default_group"):
                            default_group = _sc["default_group"]
                            break
                except Exception:
                    pass

                if len(args) == 2:
                    target_group, vol_arg = default_group, int(args[1])
                elif len(args) == 3:
                    target_group, vol_arg = args[1], int(args[2])
                else:
                    await reply("Usage: !volume [group] <0-100>")
                    return

                if not (0 <= vol_arg <= 100):
                    await reply("Volume must be between 0 and 100.")
                    return

                categories = self.config_manager.get_audio_categories() or {}
                canonical = None
                for name in categories:
                    if str(name).upper() == str(target_group).upper():
                        canonical = name
                        break
                if canonical is None:
                    await reply(f"Group '{target_group}' not found in audio categories.")
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
                await reply(f"Volume for group '{canonical}' set to {vol_arg}% ({when})")
            except (ValueError, IndexError):
                await reply("Usage: !volume [group] <0-100>")
            except Exception as e:
                print(f"Error setting volume: {e}")
            return

    async def execute_system_command(self, message, username, sys_cmd, full_content):
        """Execute a system command based on its type and configuration"""
        command_type = sys_cmd.get("command", "").lower()
        command_name = sys_cmd.get("command_name", sys_cmd["command"]).lower()

        # Обработчик выбирается по исходной команде: копии (!next -> !skip)
        # работают так же, как оригинал.
        if command_type in QUEUE_COMMANDS:
            await self.handle_queue_commands(message, command_type.lstrip('!'), full_content)
            return

        # Special handling for different system commands
        if command_name == "!random" or command_type == "!random":
            await self.execute_random_command(message, username, sys_cmd, full_content)
        elif command_name == "!points" or command_type == "!points":
            # Handle points command
            cmd_key = "points"
            cooldown_sec = self.currency_manager.settings.get('cooldown', 5)  # in seconds
            
            # Normalize the command key and check if it contains invisible characters
            normalized_key = self.normalize_command_key(cmd_key)
            
            # Use the normalized key for cooldown check
            last_used = self.user_cooldowns.get(normalized_key, {}).get(username, 0)
            current_time = time.time()
            elapsed = current_time - last_used
            
            if cooldown_sec > 0 and elapsed < cooldown_sec:
                remaining = int(cooldown_sec - elapsed)
                await message.channel.send(
                    f"@{username}: command is on cooldown. Try in {remaining} sec."
                )
                return
            
            # Command executes - format and send response
            response = self.currency_manager.format_currency_message(username)
            await message.channel.send(response)
            
            # Update the last usage time only AFTER successful execution
            if cooldown_sec > 0:  # Check if cooldown is active
                self.user_cooldowns.setdefault(normalized_key, {})[username] = current_time
        elif command_name == "!add_points" or command_type == "!add_points":
            # Handle add_points command
            # Check if user is moderator
            is_mod = await self.has_permission(message, "moderator")
            if not is_mod:
                await message.channel.send(f"@{username}: You don't have permission to use this command.")
                return
                
            # Parse message for parameters (target user and amount)
            args = full_content.split(maxsplit=2)[1:]
            if len(args) < 2:
                await message.channel.send(f"@{username}: Usage: !add_points @username amount")
                return
                
            # Get target user (remove @ if present)
            target_user = args[0]
            if target_user.startswith('@'):
                target_user = target_user[1:]
            target_user = target_user.lower()
                
            # Parse amount
            try:
                points_amount = float(args[1])
                # Round to two decimal places
                points_amount = round(points_amount, 2)
                if points_amount <= 0:
                    await message.channel.send(f"@{username}: Amount must be greater than 0")
                    return
            except ValueError:
                await message.channel.send(f"@{username}: Invalid amount format. Use numbers only.")
                return
                
            # Add points with validation
            # Сначала запоминаем баланс до операции
            old_points = self.currency_manager.get_points(target_user)
            new_points = self.currency_manager.add_points(target_user, points_amount)

            # Если баланс не изменился, считаем, что валидация не прошла
            if new_points == old_points and points_amount > 0:
                await message.channel.send(
                    f"@{username}: Failed to add points. Possible reasons: amount too large, "
                    f"would exceed maximum balance, or suspicious balance change detected."
                )
                return

            # Если мы здесь — операция прошла успешно, но проверим, не превысили ли мы максимальный баланс
            max_balance = 50000000  # Должен совпадать с max_balance в CurrencyManager._validate_points_operation
            formatted_points = f"{float(new_points):.2f}"

            # Основное сообщение об успешном добавлении
            await message.channel.send(
                f"@{target_user} received {points_amount:.2f} points from @{username}. New balance: {formatted_points}"
            )

            # Дополнительное предупреждение, если баланс достиг или превысил максимум
            if new_points >= max_balance:
                await message.channel.send(
                    f"@{username}: Warning: @{target_user} has reached or exceeded the maximum balance limit "
                    f"({max_balance:.0f} points). Further additions may be blocked by validation."
                )
        elif command_name == "!remove_points" or command_type == "!remove_points":
            # Handle remove_points command
            # Check if user is moderator
            is_mod = await self.has_permission(message, "moderator")
            if not is_mod:
                await message.channel.send(f"@{username}: You don't have permission to use this command.")
                return
                
            # Parse message for parameters (target user and amount)
            args = full_content.split(maxsplit=2)[1:]
            if len(args) < 2:
                await message.channel.send(f"@{username}: Usage: !remove_points @username amount")
                return
                
            # Get target user (remove @ if present)
            target_user = args[0]
            if target_user.startswith('@'):
                target_user = target_user[1:]
            target_user = target_user.lower()
                
            # Parse amount
            try:
                points_amount = float(args[1])
                # Round to two decimal places
                points_amount = round(points_amount, 2)
                if points_amount <= 0:
                    await message.channel.send(f"@{username}: Amount must be greater than 0")
                    return
            except ValueError:
                await message.channel.send(f"@{username}: Invalid amount format. Use numbers only.")
                return

            # Get current points of the user BEFORE removal
            old_balance = self.currency_manager.get_points(target_user)

            # Check if user has enough points
            if old_balance < points_amount:
                await message.channel.send(
                    f"@{username}: User @{target_user} only has {old_balance:.2f} points, cannot remove {points_amount:.2f}"
                )
                return

            # Remove points with validation
            new_balance = self.currency_manager.remove_points(target_user, points_amount)

            # Если баланс не изменился, считаем, что валидация не прошла
            # (remove_points в случае фейла возвращает текущий баланс без изменений)
            if new_balance == old_balance:
                # Определяем тип ошибки по тем же правилам, что и в CurrencyManager
                if points_amount > 5000000:
                    error_msg = f"Amount too large: {points_amount:.2f} (max: 5000000)"
                elif points_amount < 0.01:
                    error_msg = f"Amount too small: {points_amount:.2f} (min: 0.01)"
                elif points_amount > old_balance:
                    error_msg = f"Cannot remove more than current balance: current={old_balance:.2f}, removing={points_amount:.2f}"
                else:
                    error_msg = "Validation error occurred"

                await message.channel.send(f"@{username}: Failed to remove points. {error_msg}")
                return

            # Если мы здесь — операция прошла успешно, баланс изменился
            await message.channel.send(
                f"@{username} removed {points_amount:.2f} points from @{target_user}. New balance: {new_balance:.2f}"
            )
        elif command_name == "!top" or command_type == "!top":
            # Handle top command
            users = self.currency_manager.users
            # Sort users by points
            sorted_users = sorted(users.items(), key=lambda x: x[1].get('points', 0), reverse=True)
            top_5 = sorted_users[:5]
            
            if not top_5:
                await message.channel.send(f"@{username}: No users found in currency system.")
                return
                
            response = "Top 5 users: "
            entries = []
            for i, (uname, data) in enumerate(top_5):
                points = data.get('points', 0)
                entries.append(f"{i+1}. {uname} ({points:.0f})")
            
            await message.channel.send(response + " | ".join(entries))

        elif command_name == "!give" or command_type == "!give":
            # Handle give points command: !give @username amount
            args = full_content.split(maxsplit=2)[1:]
            if len(args) < 2:
                await message.channel.send(f"@{username}: Usage: !give @username amount")
                return
                
            target_user = args[0].lower().lstrip('@')
            try:
                amount = float(args[1])
                amount = round(amount, 2)
                if amount <= 0:
                    await message.channel.send(f"@{username}: Amount must be greater than 0")
                    return
            except ValueError:
                await message.channel.send(f"@{username}: Invalid amount format.")
                return
                
            # Check if sender has enough points
            sender_points = self.currency_manager.get_points(username)
            if sender_points < amount:
                await message.channel.send(f"@{username}: You don't have enough points ({sender_points:.2f})")
                return
                
            ok, reason = self.currency_manager.transfer_points(username, target_user, amount)
            if not ok:
                if reason == "user not found":
                    text = f"@{username}: User @{target_user} not found."
                elif reason == "cannot give points to yourself":
                    text = f"@{username}: You can't give points to yourself."
                else:
                    text = f"@{username}: Transfer failed, no points were moved."
                await message.channel.send(text)
                return

            await message.channel.send(f"@{username} gave {amount:.2f} points to @{target_user}!")

        elif command_name == "!uptime" or command_type == "!uptime":
            # Handle uptime command
            if not self.is_live or not self.stream_start_time:
                await message.channel.send(f"@{username}: Stream is currently offline.")
                return
                
            try:
                start_time = datetime.fromisoformat(self.stream_start_time.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                uptime = now - start_time
                
                hours, remainder = divmod(int(uptime.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                
                parts = []
                if hours > 0: parts.append(f"{hours}h")
                if minutes > 0: parts.append(f"{minutes}m")
                parts.append(f"{seconds}s")
                
                await message.channel.send(f"@{username}: Stream uptime: {' '.join(parts)}")
            except Exception as e:
                print(f"Error calculating uptime: {e}")
                await message.channel.send(f"@{username}: Error calculating uptime.")
        else:
            # For any other system commands that might have custom responses
            response = sys_cmd.get("response", "")
            if response:
                # Replace placeholders in the response
                formatted_response = response.replace("{user}", username)
                await message.channel.send(formatted_response)

    async def execute_random_command(self, message, username, sys_cmd, full_content):
        """Execute the random command functionality"""
        # Get the configured group name from the system command settings
        group_name = sys_cmd.get("random_group", "GENERAL").upper()

        # Find all enabled commands in the specified group (or ALL groups if "ALL" is specified)
        commands_in_group = []
        for cmd in getattr(self, "_commands_list", []):
            if cmd.get("Enabled", False):
                if group_name == "ALL":
                    # Include commands from all groups when "ALL" is specified
                    commands_in_group.append(cmd)
                else:
                    # Include only commands from the specific group
                    cmd_group = cmd.get("Group", "GENERAL").upper()
                    if cmd_group == group_name:
                        commands_in_group.append(cmd)

        if not commands_in_group:
            if group_name == "ALL":
                await message.channel.send(f"@{username}: No enabled commands found")
            else:
                await message.channel.send(f"@{username}: No commands found in group '{group_name}'")
            return

        # Select a random command from the group
        import random
        selected_cmd = random.choice(commands_in_group)

        # Show picked command if enabled
        if sys_cmd.get("show_picked_command", True):
            response_template = sys_cmd.get("picked_command_response", "Picked {command}.")
            formatted_response = response_template.replace("{command}", selected_cmd['Command'])
            await message.channel.send(formatted_response)

        # Выбранная команда идёт тем же конвейером, что набранная в чате:
        # права, кулдауны, цена, очередь/канал/громкость группы, возврат
        # очков, счётчик (раньше !random играл мимо очереди и не считался).
        await self.run_command(message, selected_cmd)

        print(f"Random command executed: {selected_cmd['Command']} from group '{group_name}' by {username}")
