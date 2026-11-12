import asyncio
import os
import time
import pygame
import threading
from twitchio.ext import commands
from twitchio.ext.commands import errors
import traceback
from core.currency_manager import CurrencyManager
from typing import Union

from core.system_commands import merge_with_defaults, name_of as sys_cmd_name
from bot.dispatcher import CommandDispatcher
from bot.audio import SoundCache, may_start, ensure_channels, pick_sound
from bot.helix import HelixClient, logins as helix_logins
from bot.ui_port import BotUi, CallbackUi
from core import permissions
from core import variables
from core.timers import TimerClock
from bot.queue import QueueMixin
from bot.system_handlers import SystemCommandsMixin


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


class TwitchBot(QueueMixin, SystemCommandsMixin, CommandDispatcher, commands.Bot):
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
            self._sound_picks = {}      # папка -> последний выбранный файл
            if sound_channel:
                self.sound_channel = sound_channel
            else:
                # Initialize multiple channels
                ensure_channels()   # 0..32 for the groups + the editor's preview
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
            # таймеры (core/timers.py): сообщения бота в чат по расписанию
            self.timer_task = None
            self._timer_clock = None
            self._chat_lines = 0
            self.stream_status_interval = 30
            
            # Активные в чате: кто писал за последние ACTIVE_SECONDS (вкладка
            # Active Chatters; Active Bonus считает CurrencyManager.note_chat).
            # Раньше здесь был список всех зрителей на момент подключения.
            self.active_users = set()
            self._chat_times = {}
            
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
            
            self._notify("all_viewers", viewers)
            self._notify("chat", f"Connected to {self.channel}. Loaded {len(viewers)} viewers.")
            self._notify("active_viewers", sorted(self.active_users))
            
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
            if self._timer_clock is None:
                self._timer_clock = TimerClock(time.time(), self._chat_lines)
            if not self.timer_task or self.timer_task.done():
                self.timer_task = asyncio.create_task(self._timers_loop())
            
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

    def _response_values(self, message, cmd):
        """Placeholders of a command response (core/variables.py)."""
        name = getattr(getattr(message, "author", None), "name", "") or ""
        cm = getattr(self, "currency_manager", None)
        try:
            count = int(cmd.get("Count", 0) or 0) + 1      # this use included
        except (TypeError, ValueError):
            count = 1

        def points():
            return variables.format_points(cm.get_points(name.lower())) if cm is not None else "0"

        def currency():
            try:
                return cm.get_currency_name()
            except Exception:
                return "points"
        # a queue entry restored after a restart has no message text
        return variables.command_values(name, getattr(message, "content", "") or "", channel=self.channel,
                                        count=count, points=points, currency=currency)

    async def send_multiline_response(self, channel, response_text, username, values=None):
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

            # {user}, {target}, {count}, {random:1-6}... (core/variables.py)
            formatted_line = variables.render(line, values or {"user": username})
            
            # Отправляем непустую строку как отдельное сообщение
            if formatted_line.strip():
                await channel.send(formatted_line)
                # Небольшая задержка между сообщениями для избежания rate limit
                await asyncio.sleep(0.1)

    TIMER_TICK = 10

    def _timer_channel(self):
        chans = getattr(self, "connected_channels", None) or []
        return chans[0] if chans else None

    async def _timers_tick(self, now=None):
        """Post the timers that are due (core/timers.py)."""
        now = time.time() if now is None else now
        if self._timer_clock is None:
            self._timer_clock = TimerClock(now, self._chat_lines)
        try:
            timers = self.config_manager.get_timers()
        except Exception:
            return
        due = self._timer_clock.due(timers, now, self._chat_lines, bool(self.is_live))
        if not due:
            return
        channel = self._timer_channel()
        if channel is None:
            return
        for key, timer in due:
            text = _fit_chat(variables.render(timer["message"], {"channel": self.channel}))
            try:
                await channel.send(text)
            except Exception as e:
                print(f"Timer message failed: {e}")
                continue
            self._timer_clock.sent(key, now, self._chat_lines)
            self._ui_message(f"[Timer] {text}")

    async def _timers_loop(self):
        while self.is_running:
            try:
                await self._timers_tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"Error in timers: {e}")
            await asyncio.sleep(self.TIMER_TICK)

    ACTIVE_SECONDS = 600

    def _note_chatter(self, name):
        """Someone wrote in chat: Active Bonus (currency) and the Active
        Chatters list (reported only when it changes)."""
        name = str(name or "").lower()
        if not name:
            return
        cm = getattr(self, "currency_manager", None)
        if cm is not None and hasattr(cm, "note_chat"):
            cm.note_chat(name)
        now = time.time()
        self._chat_times[name] = now
        cutoff = now - self.ACTIVE_SECONDS
        for old in [n for n, t in self._chat_times.items() if t < cutoff]:
            del self._chat_times[old]
        active = set(self._chat_times)
        if active != self.active_users:
            self.active_users = active
            self._notify("active_viewers", sorted(active))

    async def event_message(self, message):
        # Игнорируем эхо собственного бота
        if message.echo:
            return
        self._note_chatter(getattr(message.author, "name", ""))
        self._chat_lines += 1

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
            if cmd_key != key and key not in [self.normalize_command_key(a)
                                             for a in variables.alias_names(cmd.get("Aliases", ""))]:
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
                for task in (self.connection_check_task, getattr(self, 'stream_status_task', None),
                             getattr(self, 'timer_task', None)):
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
            # папка вместо файла: случайный звук из неё (2.0)
            filepath = pick_sound(filepath, self._sound_picks)
            # Проверка существования файла
            if not filepath or not os.path.exists(filepath):
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
            viewers = list(getattr(self, "active_users", None) or [self.channel.lower()])
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
    def _badge(self, author, attr):
        try:
            return getattr(author, attr, False) is True
        except Exception:
            return False

    async def has_permission(self, message, required):
        """Может ли автор сообщения вызвать команду с правом `required`.

        Лестница Everyone < Regular < Subscriber < VIP < Moderator < Admin
        (core/permissions.py): каждый уровень включает нижние. Бейджи из
        тегов IRC решают сразу; модератор без бейджа - через
        is_user_moderator (кэш на 5 минут). Admin - владелец канала и список
        admins в moderators.json (раньше Admin был равен модератору).
        Исключённые модераторы теряют только права модератора.
        """
        need = permissions.rank(required)
        if need == 0:
            return True
        author = message.author
        username = str(getattr(author, "name", "") or "").lower()
        if username == str(self.channel).lower() or self._badge(author, "is_broadcaster"):
            return True
        try:
            if username in self.config_manager.get_admins():
                return True
        except Exception:
            pass
        if need >= permissions.ADMIN:
            return False
        try:
            excluded = username in self.config_manager.get_excluded_moderators()
        except Exception:
            excluded = False
        if not excluded and self._badge(author, "is_mod"):
            return True
        if need >= permissions.MODERATOR:
            return (not excluded) and await self.is_user_moderator(username)
        if self._badge(author, "is_vip"):
            return True
        if need <= permissions.SUBSCRIBER and self._badge(author, "is_subscriber"):
            return True
        if need <= permissions.REGULAR:
            cm = getattr(self, "currency_manager", None)
            users = getattr(cm, "users", None) or {}
            if isinstance(users.get(username), dict) and users[username].get("is_regular"):
                return True
        # a moderator without the badge (manual list / Twitch API)
        return (not excluded) and await self.is_user_moderator(username)

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
            
    def _count_use(self, cmd, username=None):
        """+1 к счётчику своей копии и сообщение редактору (счётчик и, для
        оверлея OBS, кто вызвал)."""
        try:
            cmd["Count"] = int(cmd.get("Count", 0) or 0) + 1
        except (TypeError, ValueError):
            pass
        self._notify("command_used", cmd)
        self._notify("command_run", str(cmd.get("Command", "")), str(username or ""))
        stats = getattr(getattr(self, "currency_manager", None), "stats", None)
        if stats is not None:
            stats.record("command", name=str(cmd.get("Command", "")))

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
                if getattr(currency, "stats", None) is not None:
                    currency.stats.record("rewards", r.points)
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
