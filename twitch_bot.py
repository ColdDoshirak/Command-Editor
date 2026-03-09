import asyncio
import json
import os
import time
import pygame
import concurrent.futures  # Добавляем необходимый импорт
from twitchio.ext import commands
from twitchio.ext.commands import errors
from config_manager import ConfigManager
from pathlib import Path
import traceback
import requests
from currency_manager import CurrencyManager
from datetime import datetime, timezone
from typing import Union

class TwitchBot(commands.Bot):
    
    def __init__(self, channel, message_callback=None, commands_data=None, sound_channel=None, config_manager=None, currency_manager=None, **kwargs):
        # Загружаем настройки Twitch
        if not config_manager:
            from config_manager import ConfigManager
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
            # Загружаем настройки прерывания звуков СРАЗУ при инициализации
            self.allow_sound_interruption = self.config_manager.get_sound_interruption()
            self.show_interruption_message = self.config_manager.get_interruption_message()
            
            # Инициализация для проигрывания звуков
            self.loaded_sounds = {}
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
            self.message_callback = message_callback
            
            # Аудио и статус
            self.player = None
            self.last_heartbeat = time.time()
            self.paused = False
            
            # Отслеживание соединения
            self.reconnect_task = None
            self.connection_check_task = None
            self.reconnect_attempts = 0
            self.max_reconnect_attempts = 5
            
            # Отслеживание пользователей
            self.active_users = set([channel.lower()])  # Инициализируем с владельцем канала
            
            # Сигнал-хэндлер (будет установлен извне)
            self.signal_handler = None
            
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
            
            # Получаем broadcaster_id
            try:
                resp = requests.get(
                    "https://api.twitch.tv/helix/users",
                    headers=self._helix_headers,
                    params={"login": channel}
                )
                data = resp.json()
                self.broadcaster_id = data["data"][0]["id"]
                self.moderator_id = self.broadcaster_id
            except Exception as e:
                print(f"Error fetching broadcaster ID: {e}")
                self.broadcaster_id = None
                self.moderator_id = None
            
            print(f"Bot initialized with channel: {channel}")
            
            # Для отслеживания кулдаунов команд
            self.global_cooldowns = {}  # {команда: время_использования}
            self.user_cooldowns = {}    # {команда: {пользователь: время_использования}}
            
            # Отслеживание активных звуков по каналам для изменения громкости во время воспроизведения
            self.active_sounds = {}  # {channel_id: sound_object}

            # Command queue initialization
            self.command_queues = {}  # {group_name: asyncio.Queue}
            self.queue_workers = {}   # {group_name: asyncio.Task}
            self.queue_processing = {} # {group_name: bool}
            self.queue_semaphores = {}  # {group_name: asyncio.Semaphore} для ограничения размера очереди

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
    
    def update_commands(self, commands_list):
        """Вызывается из CommandEditor после каждой правки таблицы"""
        self._commands_list = commands_list or []
        self.init_queues() # Re-initialize queues to pick up new groups

    def init_queues(self):
        """Initialize queues for all command groups"""
        print(f"DEBUG: init_queues called. Commands count: {len(self._commands_list)}")
        groups = set()
        for cmd in self._commands_list:
            groups.add(cmd.get("Group", "GENERAL"))
        
        categories = self.config_manager.get_audio_categories()
        print(f"DEBUG: Categories loaded: {list(categories.keys())}")
        
        # Try to get the right loop
        current_loop = None
        try:
            current_loop = asyncio.get_event_loop()
        except RuntimeError:
            pass
            
        if not current_loop:
            current_loop = getattr(self, 'loop', None)

        print(f"DEBUG: init_queues groups: {groups}. Loop: {current_loop} (Running: {current_loop.is_running() if current_loop else 'N/A'})")
        
        for group in groups:
            is_enabled = categories.get(group, {}).get("queue_enabled", False)
            max_size = categories.get(group, {}).get("max_queue_size", 0)
            print(f"DEBUG: Group '{group}' queue_enabled: {is_enabled}, max_size: {max_size}")
            
            if is_enabled:
                # Создаем queue и semaphore если их еще нет
                if group not in self.command_queues:
                    self.command_queues[group] = asyncio.Queue()
                    # Semaphore для ограничения размера очереди (max_size=0 означает неограниченно)
                    if max_size > 0:
                        self.queue_semaphores[group] = asyncio.Semaphore(max_size)
                    else:
                        self.queue_semaphores[group] = None  # Нет ограничения
                    self.queue_processing[group] = True
                    print(f"Created new queue for group: {group}")
                
                # Start/Check worker
                if current_loop and current_loop.is_running():
                    if group not in self.queue_workers or self.queue_workers[group].done():
                        print(f"Starting/Restarting queue worker task for group: {group}")
                        self.queue_workers[group] = current_loop.create_task(self.process_queue(group))
                    else:
                        print(f"Queue worker for group {group} is already running.")
                else:
                    print(f"Loop not running yet (status: {current_loop.is_running() if current_loop else 'No Loop'}). Worker for {group} will start later.")
            else:
                # If queue was disabled, stop processing (queue will remain but won't be used)
                if self.queue_processing.get(group, False):
                    print(f"Disabling queue processing for group: {group}")
                    self.queue_processing[group] = False
                if group in self.queue_workers:
                    print(f"Cancelling worker for group: {group}")
                    self.queue_workers[group].cancel()
                    del self.queue_workers[group]

    async def process_queue(self, group):
        """Sequential processing for a specific command group"""
        print(f"Starting queue worker for group: {group}")
        semaphore = self.queue_semaphores.get(group)
        try:
            while self.queue_processing.get(group, False):
                try:
                    # Wait for next command in queue
                    queue_item = await self.command_queues[group].get()
                    message, cmd_data = queue_item
                    
                    try:
                        # Execute the command
                        await self.execute_queued_command(message, cmd_data)
                    finally:
                        # Mark as done - всегда вызываем task_done после get()
                        self.command_queues[group].task_done()
                        # Освобождаем semaphore после завершения обработки
                        if semaphore is not None:
                            semaphore.release()
                        
                except asyncio.CancelledError:
                    # Python 3.8+ совместимая обработка отмены
                    raise
                except Exception as e:
                    print(f"Error processing queue item for {group}: {e}")
                    traceback.print_exc()
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            print(f"Queue worker for {group} cancelled")
        finally:
            print(f"Queue worker for {group} stopped")

    async def execute_queued_command(self, message, cmd):
        """Execute a single command from the queue and wait for completion if it has sound"""
        username = message.author.name.lower()
        content = message.content.strip()
        cmd_name = cmd.get("Command", "unknown")
        group = cmd.get("Group", "GENERAL")
        
        print(f"--- Starting execution of queued command: !{cmd_name} (Group: {group}) ---")
        
        try:
            # 1. Handle Cost
            cost = int(cmd.get("Cost", 0))
            if cost > 0:
                if not self.currency_manager.pay_for_command(username, cost):
                    await message.channel.send(f"@{username}, you don't have enough points ({cost}) for !{cmd['Command']}")
                    print(f"Execution cancelled: user {username} doesn't have enough points.")
                    return

            # 2. Handle Volume
            cmd_volume = int(cmd.get("Volume", 100))
            
            # Check if there's a saved group volume that should override the command volume
            # Only use group volume if command volume is default (100) or not explicitly set
            group_volume = self.config_manager.get_group_volume(group)
            if group_volume > 0:
                final_volume = group_volume
            else:
                final_volume = float(cmd_volume) / 100.0

            # 3. Handle Sound
            sound_file = cmd.get("SoundFile", "")
            if sound_file:
                categories = self.config_manager.get_audio_categories()
                channel_id = categories.get(group, {}).get("audio_channel", 0)
                
                print(f"Playing queued sound: {sound_file} (Channel: {channel_id}, Volume: {final_volume})")
                await self.play_sound_sequentially(sound_file, final_volume, channel_id)

            # 4. Handle Response
            response = cmd.get("Response", "")
            if response:
                await self.send_multiline_response(message.channel, response, username)
                print(f"Sent response for queued command !{cmd_name}")

            print(f"--- Finished execution of queued command: !{cmd_name} ---")

        except Exception as e:
            print(f"Error executing queued command !{cmd_name}: {e}")
            traceback.print_exc()

    async def play_sound_sequentially(self, sound_file, volume, channel_id=0):
        """Play sound and wait for it to finish on the specified channel"""
        sound_path = Path(sound_file)
        if not sound_path.is_absolute():
            sound_path = Path(self.config_manager.get_sound_config().get("sound_dir", "")) / sound_file

        if sound_path.exists():
            try:
                # Выполняем блокирующие операции pygame в executor
                def play_sound_blocking():
                    # Load sound
                    sound = pygame.mixer.Sound(str(sound_path))
                    sound.set_volume(volume)
                    
                    # Select channel
                    if channel_id > 0:
                        channel = pygame.mixer.Channel(channel_id)
                    else:
                        channel = self.sound_channel
                    
                    print(f"--- PLAYING on channel {channel_id} (Internal: {channel}) ---")
                    # Play on selected channel
                    channel.play(sound)
                    
                    # Track active sound for real-time volume control
                    if channel_id > 0:
                        self.active_sounds[channel_id] = sound
                    else:
                        self.active_sounds[0] = sound
                    
                    # Wait for playback to finish
                    while channel.get_busy():
                        # Используем time.sleep вместо asyncio.sleep для блокирующего контекста
                        time.sleep(0.1)
                    
                    # Clean up active sound tracking
                    if channel_id > 0:
                        self.active_sounds.pop(channel_id, None)
                    else:
                        self.active_sounds.pop(0, None)
                    
                    return True
                
                # Запускаем блокирующую функцию в executor
                await self.loop.run_in_executor(None, play_sound_blocking)
                    
            except Exception as e:
                print(f"Error playing queued sound {sound_file}: {e}")
                traceback.print_exc()
        else:
            print(f"Sound file not found: {sound_path}")

    async def event_ready(self):
        print(f"Bot is ready! Connected to {self.channel}")
        # Ensure self.loop references the correct asyncio loop for run_coroutine_threadsafe
        self.loop = asyncio.get_event_loop()
        try:
            # Загрузка списка зрителей сразу при первом подключении
            viewers = await self.get_all_viewers()
            print(f"Initial viewers loaded: {len(viewers)} viewers")
            
            # Получаем и обновляем список модераторов канала
            print("Getting channel moderators...")
            mods = await self.get_channel_moderators()
            print(f"Retrieved {len(mods)} moderators")
            
            # Отправляем список зрителей в интерфейс через сигналы
            if hasattr(self, 'signal_handler') and self.signal_handler:
                self.signal_handler.all_viewers_signal.emit(viewers)
                self.signal_handler.chat_signal.emit(f"Connected to {self.channel}. Loaded {len(viewers)} viewers.")
                
                # Также обновляем активных зрителей (первоначально это тот же список)
                # self.active_users уже был инициализирован в __init__, обновляем его
                self.active_users = set(viewers)
                self.signal_handler.active_viewers_signal.emit(list(self.active_users))
            
            # Проверка статуса стрима
            is_live = await self.check_if_live()
            # Сигналим UI о статусе стрима
            self.is_live = is_live
            if hasattr(self, 'signal_handler') and self.signal_handler:
                self.signal_handler.stream_status_signal.emit(is_live)
            
            # Запускаем периодическую проверку соединения, если не запущена
            if not self.connection_check_task or self.connection_check_task.done():
                self.connection_check_task = asyncio.create_task(self._check_connection())
            
            # Start queue workers now that we have a running loop
            print("Initializing command queues and workers...")
            self.init_queues()
            
        except Exception as e:
            print(f"CRITICAL ERROR in event_ready: {e}")
            import traceback; traceback.print_exc()

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
        # When we receive a message, we know the connection is active
        # Reset the heartbeat and reconnection attempt counters
        self.last_heartbeat = time.time()
        self.reconnect_attempts = 0
        
        # Игнорируем эхо собственного бота
        if message.echo:
            return
            
        # Выводим сообщение в UI
        if self.message_callback:
            self.message_callback(f"{message.author.name}: {message.content}")
            
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
            
        # Queue Management Commands
        if key in ["queue", "skip", "clear", "volume"]:
            await self.handle_queue_commands(message, key, content)
            return
        


        # Check for system commands from the sys_commands tab
        system_commands = self.config_manager.load_system_commands()
        for sys_cmd in system_commands:
            # Skip disabled commands
            if not sys_cmd.get("enabled", False):
                continue
                
            # Get the command name (original or custom name for duplicates)
            cmd_name = sys_cmd.get("command_name", sys_cmd["command"])
            cmd_key = self.normalize_command_key(cmd_name.lstrip('!'))
            
            # Check if the message matches this system command
            if key == cmd_key:
                # Check permissions
                required_permission = sys_cmd.get("permission", "Everyone").lower()
                user_is_mod = await self.is_user_moderator(username)
                
                if required_permission == "moderator" and not user_is_mod:
                    await message.channel.send(f"@{username}: You don't have permission to use this command.")
                    return
                elif required_permission == "admin" and not user_is_mod:  # Simplified admin check
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
                
                # Execute the command based on its type
                await self.execute_system_command(message, username, sys_cmd, content)
                
                # Update cooldowns after successful execution
                if cooldown_sec > 0:
                    self.global_cooldowns[cmd_key] = current_time
                if user_cooldown_sec > 0:
                    self.user_cooldowns.setdefault(cmd_key, {})[username] = current_time
                
                return  # Command processed, exit the event_message method

        # Далее обрабатываем кастомные команды как раньше

        # Далее обрабатываем кастомные команды как раньше
        for cmd in getattr(self, "_commands_list", []):
            if not cmd.get("Enabled", False):
                continue

            # Сравниваем тоже без "!" и в lowercase, удаляем невидимые символы
            raw_cmd_key = cmd["Command"].lstrip(self.prefix).lower()
            cmd_key = self.normalize_command_key(raw_cmd_key)
            
            # Если ключи не совпадают, пропускаем команду
            if cmd_key != key:
                continue
                
            # Для отладки
            print(f"Command matched: '{key}' with command configuration key '{cmd_key}'")
            if raw_cmd_key != cmd_key:
                print(f"  Command normalized in config: '{raw_cmd_key}' -> '{cmd_key}'")
            print(f"  Command cost: {cmd.get('Cost', 0)}")

            # теперь Cooldown измеряется в минутах
            cooldown_min = int(cmd.get("Cooldown", 0))
            cooldown_sec = cooldown_min * 60
            
            # Используем нормализованный ключ для проверки кулдауна
            normalized_key = self.normalize_command_key(cmd_key)
            last_used = self.global_cooldowns.get(normalized_key, 0)
            elapsed = current_time - last_used
            
            if cooldown_sec > 0 and elapsed < cooldown_sec:
                remaining = int((cooldown_sec - elapsed))
                await message.channel.send(
                    f"@{username}: command is on cooldown. Try in {remaining} sec."
                )
                return

            # UserCooldown тоже в минутах
            user_cd_min = int(cmd.get("UserCooldown", 0))
            user_cd_sec = user_cd_min * 60
            if user_cd_sec > 0:
                # Используем тот же нормализованный ключ для проверки пользовательского кулдауна
                user_last = self.user_cooldowns.get(normalized_key, {}).get(username, 0)
                u_elapsed = current_time - user_last
                if u_elapsed < user_cd_sec:
                    u_rem = int(user_cd_sec - u_elapsed)
                    await message.channel.send(
                        f"@{username}: you can use this command in {u_rem} sec."
                    )
                    return
                
            # Проверка стоимости ПЕРЕД фиксацией времени кулдауна
            cost = int(cmd.get("Cost", 0))
            points_deducted = False
            
            if cost > 0:
                # Проверяем баланс перед списанием
                current_points = self.currency_manager.get_points(username)
                print(f"User {username} has {current_points} points, command costs {cost}")
                
                if current_points < cost:
                    formatted_points = f"{float(current_points):.2f}"
                    await message.channel.send(
                        f"@{username}: Not enough points. Cost: {cost} (you have {formatted_points})"
                    )
                    return

                # Списываем поинты только если достаточно средств
                if self.currency_manager.pay_for_command(username, cost):
                    points_deducted = True
                    print(f"Deducted {cost} points from {username}")
                else:
                    # Этого не должно происходить, но на всякий случай
                    print(f"Failed to deduct points from {username}")
                    current_points = self.currency_manager.get_points(username)
                    formatted_points = f"{float(current_points):.2f}"
                    await message.channel.send(
                        f"@{username}: Payment error. Cost: {cost} (you have {formatted_points})"
                    )
                    return
                
            # Выполняем саму команду
            # Флаги для отслеживания выполнения частей команды
            command_executed = False
            has_response = False
            has_sound = False
            sound_played = False
            
            # Команда считается выполненной если либо был отправлен ответ,
            # либо успешно проигран звук, либо оба действия
            
            # Check if this group has queueing enabled
            group = cmd.get("Group", "GENERAL")
            categories = self.config_manager.get_audio_categories()
            if categories.get(group, {}).get("queue_enabled", False):
                # Ensure queue and worker are initialized
                if group not in self.command_queues or group not in self.queue_workers or self.queue_workers[group].done():
                    print(f"Lazy initializing queue/worker for group: {group}")
                    self.init_queues()

                # CHECK QUEUE LIMITS using semaphore
                semaphore = self.queue_semaphores.get(group)
                if semaphore is not None and semaphore._value <= 0:
                    print(f"Queue full for group '{group}' (max queue size reached). Rejecting command.")
                    
                    # Refund if points were deducted
                    if points_deducted and cost > 0:
                        self.currency_manager.add_points(username, cost)
                        self.currency_manager.save_users()
                        await message.channel.send(f"@{username}: Queue for {group} is full. {cost} points refunded.")
                    else:
                        await message.channel.send(f"@{username}: Queue for {group} is full. Try again later.")
                    return

                # ENQUEUE COMMAND
                print(f"Enqueuing command '{cmd_key}' to group '{group}'")
                # We skip status checks/refunds here because the queue worker will handle it
                # However, we still want to apply cooldowns now to prevent spamming the queue
                
                # Apply cooldowns before enqueuing
                normalized_key = self.normalize_command_key(cmd_key)
                if cooldown_sec > 0:
                    self.global_cooldowns[normalized_key] = current_time
                if user_cd_sec > 0:
                    self.user_cooldowns.setdefault(normalized_key, {})[username] = current_time
                
                # Put in queue with semaphore acquisition
                try:
                    if semaphore is not None:
                        await semaphore.acquire()
                    await self.command_queues[group].put((message, cmd))
                except Exception as e:
                    print(f"Error enqueuing command: {e}")
                    if points_deducted and cost > 0:
                        self.currency_manager.add_points(username, cost)
                        self.currency_manager.save_users()
                        await message.channel.send(f"@{username}: Error adding to queue. {cost} points refunded.")
                    return
                
                # Notify user it's enqueued
                # await message.channel.send(f"@{username}: Command !{cmd['Command']} added to {group} queue.")
                return

            # NORMAL EXECUTION
            # ... existing execution logic ...
            # Отправка текста-ответа (многострочного)
            resp = cmd.get("Response", "")
            if resp and resp.strip():
                has_response = True
                await self.send_multiline_response(message.channel, resp, message.author.name)
                command_executed = True
                print(f"Sent multiline response for command '{cmd_key}'")
                
            # Проигрывание звука
            sf = cmd.get("SoundFile", "").strip()
            if sf:
                has_sound = True
                volume = int(cmd.get("Volume", 100))
                
                # Get group audio channel
                group = cmd.get("Group", "GENERAL")
                categories = self.config_manager.get_audio_categories()
                channel_id = categories.get(group, {}).get("audio_channel", 0)
                
                sound_played = self.play_sound(sf, volume, channel_id)
                if sound_played:
                    print(f"Successfully played sound for command '{cmd_key}'")
                    command_executed = True
                else:
                    print(f"Failed to play sound for command '{cmd_key}'")
                    
            # Применяем кулдауны и увеличиваем счетчик ТОЛЬКО если команда была успешно выполнена
            if command_executed:
                print(f"Command '{cmd_key}' was successfully executed by {username}")
                # Фиксируем время кулдаунов, используя нормализованный ключ
                normalized_key = self.normalize_command_key(cmd_key)
                if cooldown_sec > 0:
                    self.global_cooldowns[normalized_key] = current_time
                    print(f"Set global cooldown for '{normalized_key}', {cooldown_sec}s")
                if user_cd_sec > 0:
                    self.user_cooldowns.setdefault(normalized_key, {})[username] = current_time
                    print(f"Set user cooldown for '{normalized_key}' and user {username}, {user_cd_sec}s")
                    
                # Увеличиваем счетчик использований команды
                cmd["Count"] += 1
                print(f"Incremented usage count for '{cmd_key}': {cmd['Count']}")
            else:
                # Если команда не выполнена (например, из-за блокировки звука)
                print(f"Command '{cmd_key}' by {username} did not execute properly")
                
                # Определяем причину неисполнения команды для более понятного сообщения
                reason = "Command could not be executed"
                
                # Детализируем причину в зависимости от типа команды и ситуации
                if has_sound and not sound_played:
                    if self.sound_channel.get_busy():
                        reason = "Sound blocked: another sound is already playing"
                    else:
                        reason = "Sound file could not be played"
                        
                # Если команда имеет и текст и звук, и текст отправился, но звук заблокирован
                if has_response and has_sound and not sound_played:
                    reason = "Text response sent, but sound was blocked"
                
                # Возвращаем стоимость команды пользователю, если она была списана
                if points_deducted and cost > 0:
                    self.currency_manager.add_points(username, cost)
                    print(f"Refunded {cost} points to {username} because {reason.lower()}")
                    
                    # Сохраняем изменения сразу после возврата
                    self.currency_manager.save_users()
                    print(f"Points refund saved to currency file for {username}")
                    
                    # Подготовка сообщения пользователю
                    response_message = f"@{username}: {reason}. {cost} points refunded."
                    
                    # Специальный случай для звуковых команд без текста
                    if has_sound and not has_response and not sound_played:
                        # Проверяем, нужно ли вообще показывать сообщение о блокировке
                        show_message = getattr(self, 'show_interruption_message', False)
                        if show_message:
                            await message.channel.send(response_message)
                    else:
                        # Для всех остальных случаев всегда показываем сообщение
                        await message.channel.send(response_message)
            
            return  # Команда обработана
            
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
            
            # Отключаемся от канала
            if hasattr(self, 'loop') and self.loop:
                # Cancel the reconnect and connection tasks first if they exist
                if self.reconnect_task and not self.reconnect_task.done():
                    self.reconnect_task.cancel()
                if self.connection_check_task and not self.connection_check_task.done():
                    self.connection_check_task.cancel()
                
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
    
    def reload_audio_categories(self):
        """Reload audio categories from config and restart queue workers"""
        print("Reloading audio categories...")
        
        # Stop all existing queue workers
        for group, worker in list(self.queue_workers.items()):
            print(f"Stopping queue worker for {group}")
            self.queue_processing[group] = False
            worker.cancel()
        
        # Clear workers dict
        self.queue_workers.clear()
        
        # Reinitialize queues with new settings
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

            # Определяем канал
            if channel_id > 0:
                channel = pygame.mixer.Channel(channel_id)
                # Для выделенных каналов (>0) мы не применяем логику прерывания,
                # они играют параллельно.
            else:
                channel = self.sound_channel
                # Проверка активного воспроизведения ТОЛЬКО для дефолтного канала (0)
                if channel.get_busy():
                    allow_interrupt = getattr(self, 'allow_sound_interruption', False)
                    print(f"Checking interruption in play_sound. Allowed: {allow_interrupt}")
                    
                    if allow_interrupt:
                        print("Interrupting sound on shared channel...")
                        channel.fadeout(100)
                    else:
                        print("Blocking sound on shared channel...")
                        return False

            # Загрузка и воспроизведение звука
            snd = self.loaded_sounds.get(filepath)
            if snd is None:
                snd = pygame.mixer.Sound(filepath)
                self.loaded_sounds[filepath] = snd

            # Применяем громкость команды (из параметра volume)
            vol = float(volume) / 100.0
            print(f"Setting sound volume to: {vol} (from command volume: {volume})")
            snd.set_volume(vol)

            # Воспроизводим на выбранном канале
            channel.play(snd)
            print(f"Playing sound: {filepath} on channel {channel_id}")
            return True  # Звук успешно запущен
            
        except Exception as e:
            print(f"CRITICAL ERROR in play_sound: {e}")
            traceback.print_exc()
            return False  # В случае ошибки

    async def get_all_viewers(self) -> list:
        """Get chatters via Helix API /chat/chatters"""
        viewers = []
        if self.broadcaster_id and self.moderator_id:
            try:
                resp = requests.get(
                    "https://api.twitch.tv/helix/chat/chatters",
                    headers=self._helix_headers,
                    params={
                        "broadcaster_id": self.broadcaster_id,
                        "moderator_id": self.moderator_id
                    },
                    timeout=5
                )
                data = resp.json()
                for user in data.get("data", []):
                    viewers.append(user.get("user_login", "").lower())
            except Exception as e:
                print(f"Error getting chatters via Helix: {e}")
        # fallback на активных, если Helix не сработал
        if not viewers:
            viewers = list(getattr(self, "active_users", [self.channel.lower()]))
        self.all_viewers = viewers
        return viewers

    async def check_if_live(self, *args) -> bool:
        """Проверяем, идет ли стрим в текущий момент через Helix API."""
        try:
            if not self.broadcaster_id or not self._helix_headers:
                print("Cannot check stream status: missing broadcaster_id or API headers")
                return False
                
            # Запрашиваем данные о стриме
            response = requests.get(
                "https://api.twitch.tv/helix/streams",
                headers=self._helix_headers,
                params={"user_id": self.broadcaster_id},
                timeout=5
            )
            
            # Если запрос успешен
            if response.status_code == 200:
                data = response.json()
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
                    
                    # Убрали отправку сообщения в чат при начале стрима
                    
                return is_live
            else:
                print(f"Error checking stream status: API returned {response.status_code}")
                # В случае ошибки API сохраняем текущий статус
                return self.is_live
                
        except Exception as e:
            print(f"Error checking stream status: {e}")
            # В случае ошибки сохраняем текущий статус
            return self.is_live

    async def get_user_id(self, login: str) -> Union[str, None]:
        """Вернуть user_id пользователя по его логину через Twitch API."""
        try:
            cfg = self.config_manager.get_twitch_config()
            cid = cfg.get('client_id')
            token = cfg.get('access_token')
            if token.startswith('oauth:'):
                token = token.split(':',1)[1]
            if not cid or not token:
                return None
            headers = {
                'Client-ID': cid,
                'Authorization': f'Bearer {token}'
            }
            url = f'https://api.twitch.tv/helix/users?login={login}'
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json().get('data',[])
                if data:
                    return data[0]['id']
            return None
        except Exception as e:
            print(f"CRITICAL ERROR in get_user_id: {e}")
            import traceback
            traceback.print_exc()

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
                response = requests.get(
                    "https://api.twitch.tv/helix/moderation/moderators",
                    headers=self._helix_headers,
                    params={"broadcaster_id": self.broadcaster_id},
                    timeout=5
                )
                
                # Если запрос успешен
                if response.status_code == 200:
                    data = response.json()
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
                    print(f"Error fetching moderators: API returned {response.status_code}")
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
            
            # Отправляем сигнал с обновленным списком модераторов, если есть signal_handler
            if hasattr(self, 'signal_handler') and self.signal_handler:
                self.signal_handler.moderators_signal.emit(mods)
                
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
            moderators = await self.get_channel_moderators()
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
            
    async def _check_connection(self):
        """Check and maintain connection"""
        try:
            connection_check_failures = 0  # Счётчик неудачных проверок
            last_successful_check = time.time()  # Время последней успешной проверки
            
            while self.is_running:
                try:
                    await asyncio.sleep(10)  # Проверка каждые 10 секунд
                    
                    # Периодически очищаем кулдауны
                    if time.time() % 300 < 10:  # Примерно каждые 5 минут
                        self.cleanup_cooldowns()
                    
                    # Активная проверка соединения с Twitch IRC
                    connection_alive = False
                    
                    # 1. Попытка активной проверки - отправка PING команды
                    try:
                        if hasattr(self, '_ws') and self._ws and self._ws.socket and not self._ws.socket.closed:
                            # Если есть подключенные каналы, считаем что соединение активно
                            if len(self.connected_channels) > 0:
                                # Но проверяем это отправкой PING
                                ping_future = asyncio.run_coroutine_threadsafe(
                                    self._ws.send("PING :tmi.twitch.tv"),
                                    self.loop
                                )
                                # Ожидаем завершения отправки PING в течение 3 секунд
                                try:
                                    ping_future.result(timeout=3)
                                    # Если PING отправлен успешно, соединение живо
                                    connection_alive = True
                                    last_successful_check = time.time()
                                    connection_check_failures = 0  # Сбрасываем счётчик неудач
                                except (concurrent.futures.TimeoutError, RuntimeError) as e:
                                    print(f"PING check failed: {e}")
                                    connection_check_failures += 1
                    except Exception as ws_error:
                        print(f"WebSocket check error: {ws_error}")
                        connection_check_failures += 1
                    
                    # 2. Проверка API Twitch (но не блокируем на ошибках API)
                    try:
                        if self._helix_headers:
                            response = requests.get(
                                "https://api.twitch.tv/helix/users",
                                headers=self._helix_headers,
                                params={"login": self.channel},
                                timeout=3  # Короткий таймаут
                            )
                            
                            # Если API доступен и ответ успешен, это хороший признак
                            if response.status_code == 200:
                                if not connection_alive:  # Если основная проверка не прошла
                                    connection_alive = True
                                    last_successful_check = time.time()
                                    connection_check_failures = 0  # Сбрасываем счётчик неудач
                            else:
                                print(f"API check returned status code: {response.status_code}")
                                connection_check_failures += 1
                    except Exception as api_error:
                        print(f"API check error: {api_error}")
                        # Не считаем это критической ошибкой для IRC соединения
                    
                    # Проверяем время с момента последней успешной проверки
                    time_since_last_success = time.time() - last_successful_check
                    
                    # Выводим информацию о состоянии
                    print(f"Connection check: Connected={connection_alive}, " + 
                          f"Failures={connection_check_failures}, " +
                          f"Time since last success={time_since_last_success:.1f}s")
                    
                    # Принимаем решение о необходимости переподключения
                    # - Если накопилось 3+ неудачных проверки подряд
                    # - ИЛИ прошло больше 30 секунд с последней успешной проверки
                    if connection_check_failures >= 3 or time_since_last_success > 30:
                        print(f"Connection lost: failures={connection_check_failures}, " +
                              f"last_success={time_since_last_success:.1f}s ago")
                        
                        # Уведомляем интерфейс о потере соединения
                        if hasattr(self, 'signal_handler') and self.signal_handler:
                            self.signal_handler.chat_signal.emit("Connection lost, attempting to reconnect...")
                        
                        # Инициируем переподключение
                        if not self.reconnect_task or self.reconnect_task.done():
                            self.reconnect_task = asyncio.create_task(self._reconnect())
                        
                        # Сбрасываем счётчики для следующей серии проверок после переподключения
                        connection_check_failures = 0
                    else:
                        # Обновляем время последнего хартбита, даже если текущая проверка не удалась
                        # (но была успешная проверка недавно)
                        self.last_heartbeat = time.time()
                        
                except asyncio.CancelledError:
                    raise  # Пробрасываем отмену задачи дальше
                except Exception as e:
                    print(f"Error in connection check: {e}")
                    connection_check_failures += 1
                    await asyncio.sleep(3)  # Короткая пауза перед повторной попыткой
                    
        except asyncio.CancelledError:
            print("Connection check task cancelled")
        except Exception as e:
            print(f"CRITICAL ERROR in _check_connection: {e}")
            traceback.print_exc()
            # Пытаемся восстановить соединение при критической ошибке
            if not self.reconnect_task or self.reconnect_task.done():
                self.reconnect_task = asyncio.create_task(self._reconnect())
            
    async def _create_new_loop_and_reconnect(self):
        """Создать новый event loop и переподключиться"""
        try:
            # Создаем новый event loop
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            self.loop = new_loop
            
            print("Created new event loop for reconnection")
            
            # Запускаем переподключение
            await self._reconnect()
            
        except Exception as e:
            print(f"Error creating new event loop: {e}")
            traceback.print_exc()
            
    async def _reconnect(self):
        """Attempt to reconnect"""
        try:
            # IMPROVED CHECK FOR ACTIVE CONNECTION: If we have a working WebSocket and channels, abort reconnect
            if (hasattr(self, '_ws') and self._ws and hasattr(self._ws, 'socket') and 
                    self._ws.socket and not self._ws.socket.closed and 
                    len(getattr(self, 'connected_channels', [])) > 0):
                print("Connection already established - canceling reconnect attempt")
                self.reconnect_attempts = 0  # Reset counter
                self.last_heartbeat = time.time()  # Update last heartbeat
                
                # Signal to UI that connection is already good
                if hasattr(self, 'signal_handler') and self.signal_handler:
                    self.signal_handler.chat_signal.emit("Connection is already established and working")
                    
                # Make sure connection check task is running
                if not self.connection_check_task or self.connection_check_task.done():
                    self.connection_check_task = asyncio.create_task(self._check_connection())
                    
                return  # Exit and don't attempt reconnection
            
            # Increment attempt counter
            self.reconnect_attempts += 1
            
            if self.reconnect_attempts >= self.max_reconnect_attempts:
                print(f"Failed to reconnect after {self.max_reconnect_attempts} attempts")
                self.is_running = False
                
                # Signal to UI about reconnection failure
                if hasattr(self, 'signal_handler') and self.signal_handler:
                    self.signal_handler.chat_signal.emit("Reconnection failed after multiple attempts. Please reconnect manually.")
                return
                
            print(f"Reconnect attempt {self.reconnect_attempts}/{self.max_reconnect_attempts}")
            
            # Signal to UI about reconnection attempt
            if hasattr(self, 'signal_handler') and self.signal_handler:
                self.signal_handler.chat_signal.emit(f"Attempting to reconnect... (try {self.reconnect_attempts}/{self.max_reconnect_attempts})")
            
            # Close existing connection if present
            try:
                if hasattr(self, '_ws') and self._ws and hasattr(self._ws, 'socket') and self._ws.socket and not self._ws.socket.closed:
                    await self.close()
                    await asyncio.sleep(1)  # Brief pause after closing connection
            except Exception as e:
                print(f"Error closing connection during reconnect: {e}")
                # Continue reconnection attempt even if closing fails
            
            await asyncio.sleep(3)  # Pause before new connection attempt
            
            try:
                # Update token before reconnection (may resolve expired token issues)
                config = self.config_manager.get_twitch_config()
                token = config.get('access_token')
                if token:
                    if not token.startswith('oauth:'):
                        token = f'oauth:{token}'
                    self._token = token
                
                # Connect
                print("Starting connection sequence...")
                await self.connect()
                
                # Check connection success
                if hasattr(self, '_ws') and self._ws and hasattr(self._ws, 'socket') and self._ws.socket and not self._ws.socket.closed:
                    print("Connection established, joining channel...")
                    await self.join_channels([self.channel])
                    
                    # Verify successful channel join
                    if len(self.connected_channels) > 0:
                        print(f"Successfully joined channel {self.channel} - reconnection complete")
                        # Update last heartbeat
                        print("Join successful, updating heartbeat...")
                        self.last_heartbeat = time.time()
                        self.reconnect_attempts = 0  # Reset attempt counter
                        
                        # Signal to UI about successful reconnection
                        if hasattr(self, 'signal_handler') and self.signal_handler:
                            self.signal_handler.chat_signal.emit("Reconnected successfully!")
                        
                        # Reset any pending reconnect tasks to avoid multiple attempts
                        if self.reconnect_task and not self.reconnect_task.done():
                            self.reconnect_task.cancel()
                            self.reconnect_task = None
                        
                        # Restart connection check if not running
                        print("Restarting connection check task...")
                        if not self.connection_check_task or self.connection_check_task.done():
                            self.connection_check_task = asyncio.create_task(self._check_connection())
                        
                        # НОВЫЙ КОД: Запрашиваем обновление списка зрителей после успешного переподключения
                        print("Fetching viewers after reconnection...")
                        try:
                            # Получаем список зрителей
                            viewers = await self.get_all_viewers()
                            print(f"Retrieved {len(viewers)} viewers after reconnection")
                            
                            # Если есть сигнал-хэндлер, обновляем список
                            if hasattr(self, 'signal_handler') and self.signal_handler:
                                self.signal_handler.all_viewers_signal.emit(viewers)
                                self.signal_handler.chat_signal.emit(f"Updated viewer list: {len(viewers)} viewers")
                        except Exception as viewers_error:
                            print(f"Error fetching viewers after reconnection: {viewers_error}")
                        
                        # Также проверяем статус стрима после переподключения
                        try:
                            is_live = await self.check_if_live()
                            self.is_live = is_live
                            if hasattr(self, 'signal_handler') and self.signal_handler:
                                self.signal_handler.stream_status_signal.emit(is_live)
                                self.signal_handler.chat_signal.emit(f"Stream status updated: {'LIVE' if is_live else 'OFFLINE'}")
                        except Exception as stream_error:
                            print(f"Error updating stream status after reconnection: {stream_error}")
                                
                        # Successfully connected, exit method
                        return
                    else:
                        # If no connected channels after join, raise exception
                        raise ConnectionError("Failed to join channel after connection")
                else:
                    # If connection failed, plan another attempt
                    raise ConnectionError("WebSocket connection was not properly established")
                    
            except Exception as e:
                print(f"Error during reconnect: {e}")
                # If connection failed, try again after delay
                if self.is_running:
                    retry_delay = min(10 * self.reconnect_attempts, 30)  # Increasing delay, max 30 seconds
                    print(f"Will retry in {retry_delay} seconds...")
                    
                    if hasattr(self, 'signal_handler') and self.signal_handler:
                        self.signal_handler.chat_signal.emit(f"Reconnection failed. Retrying in {retry_delay} seconds...")
                    
                    await asyncio.sleep(retry_delay)
                    # Use create_task but store the reference to avoid multiple reconnection attempts
                    if not self.reconnect_task or self.reconnect_task.done():
                        self.reconnect_task = asyncio.create_task(self._reconnect())
            
        except Exception as e:
            print(f"CRITICAL ERROR in _reconnect: {e}")
            traceback.print_exc()
            
            # If critical error during reconnection, try again
            if self.is_running:
                # Increased delay after critical error
                retry_delay = 15
                if hasattr(self, 'signal_handler') and self.signal_handler:
                    self.signal_handler.chat_signal.emit(f"Critical connection error. Retrying in {retry_delay} seconds...")
                
                await asyncio.sleep(retry_delay)
                # Use create_task but store the reference
                if not self.reconnect_task or self.reconnect_task.done():
                    self.reconnect_task = asyncio.create_task(self._reconnect())
    
    async def event_raid(self, raider):
        """Вызывается при рейде на канал"""
        try:
            print(f"RAID EVENT RECEIVED: {raider.name} with {raider.viewers} viewers")
            
            # Проверяем наличие currency_manager
            if not hasattr(self, 'currency_manager'):
                print("Currency manager not available, can't process raid rewards")
                return
                
            # Получаем настройки для рейдов из валютной системы
            raid_points_base = self.currency_manager.settings.get('raid_points', 10)
            raid_points_per_viewer = self.currency_manager.settings.get('raid_points_per_viewer', 1)
            
            # Вычисляем количество очков за рейд
            viewers = raider.viewers
            points_to_award = raid_points_base + (viewers * raid_points_per_viewer)
            
            # Начисляем очки рейдеру
            self.currency_manager.add_points(raider.name.lower(), points_to_award)
            
            # Format points for display
            formatted_points = f"{float(points_to_award):.2f}"
            
            # Логируем событие
            print(f"Raid reward: {raider.name} получил {formatted_points} очков за рейд с {viewers} зрителями")
            
            # Отправляем сообщение в чат
            message = f"Спасибо за рейд, @{raider.name}! +{formatted_points} очков за рейд с {viewers} зрителями."
            
            if len(self.connected_channels) > 0:
                try:
                    channel = self.connected_channels[0]
                    await channel.send(message)
                except Exception as e:
                    print(f"Error sending raid message to chat: {e}")
            
            # Уведомляем UI если есть callback
            if self.message_callback:
                self.message_callback(f"Raid: {raider.name} получил {formatted_points} очков за рейд с {viewers} зрителями")
                
        except Exception as e:
            print(f"CRITICAL ERROR in event_raid: {e}")
            import traceback
            traceback.print_exc()

    async def event_subscription(self, subscription):
        """Вызывается при подписке на канал"""
        try:
            sub_points = self.currency_manager.settings.get("sub_points", 20)
            tier_multiplier = 1  # Tier 1
            
            # Разные множители для разных уровней подписки
            if subscription.tier == "2000":
                tier_multiplier = 2  # Tier 2
            elif subscription.tier == "3000":
                tier_multiplier = 5  # Tier 3
                
            points_to_award = sub_points * tier_multiplier
            
            # Добавляем очки подписчику
            self.currency_manager.add_points(subscription.user.name, points_to_award)
            
            # Format points for display
            formatted_points = f"{float(points_to_award):.2f}"
            
            # Отмечаем пользователя как подписчика
            if subscription.user.name in self.currency_manager.users:
                self.currency_manager.users[subscription.user.name]['is_subscriber'] = True
            
            # Сообщение в чат
            await self.connected_channels[0].send(
                f"Спасибо за подписку, {subscription.user.name}! Получено {formatted_points} очков."
            )
            
            if self.message_callback:
                self.message_callback(f"Sub: {subscription.user.name} получил {formatted_points} очков за подписку Tier {subscription.tier // 1000}")
        except Exception as e:
            print(f"CRITICAL ERROR in event_subscription: {e}")
            import traceback
            traceback.print_exc()

    async def event_follow(self, follower):
        """Вызывается при подписке пользователя на канал"""
        try:
            # Получаем количество очков за подписку из настроек
            follow_points = self.currency_manager.settings.get("follow_points", 5)
            
            # Добавляем очки пользователю
            self.currency_manager.add_points(follower.name, follow_points)
            
            # Format points for display
            formatted_points = f"{float(follow_points):.2f}"
            
            # Логируем событие
            print(f"[Follow] {follower.name} получил {formatted_points} очков за подписку")
            
            # Сообщение в чат (опционально)
            if len(self.connected_channels) > 0:
                try:
                    channel = self.connected_channels[0]
                    asyncio.run_coroutine_threadsafe(
                        channel.send(f"Спасибо за подписку, {follower.name}! +{formatted_points} очков"),
                        self.loop
                    )
                except Exception as e:
                    print(f"Error sending follow message to chat: {e}")
                    
            # Уведомляем UI если есть callback
            if self.message_callback:
                self.message_callback(f"Follow: {follower.name} получил {formatted_points} очков за подписку")
                
        except Exception as e:
            print(f"CRITICAL ERROR in event_follow: {e}")
            import traceback
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
        """Handle queue management commands (!queue, !skip, !clear, !volume)"""
        username = message.author.name.lower()
        args = content.split()
        
        # !queue [group]
        if cmd_key == "queue":
            target_group = args[1] if len(args) > 1 else None
            
            if target_group:
                # Case-insensitive search for the group
                target_group_normalized = target_group.upper()
                found_group = None
                
                # Search for the group in command_queues (case-insensitive)
                for grp in self.command_queues:
                    if grp.upper() == target_group_normalized:
                        found_group = grp
                        break
                
                if found_group:
                    q_size = self.command_queues[found_group].qsize()
                    await message.channel.send(f"@{username}: Queue '{found_group}' has {q_size} pending commands.")
                else:
                    await message.channel.send(f"@{username}: Queue group '{target_group}' not found.")
            else:
                # Show all active queues
                active_queues = []
                for grp, q in self.command_queues.items():
                    if q.qsize() > 0:
                        active_queues.append(f"{grp}: {q.qsize()}")
                
                if active_queues:
                    await message.channel.send(f"@{username}: Active queues: {', '.join(active_queues)}")
                else:
                    await message.channel.send(f"@{username}: All queues are empty.")
            return

        # Moderator check for control commands
        is_mod = await self.is_user_moderator(username)
        if not is_mod:
             # Create a dummy sys_cmd dict to verify permissions if needed, 
             # but for now hardcoded mod check is safer for these control commands
             await message.channel.send(f"@{username}: You don't have permission to use this command.")
             return

        # !skip [group] (stops sound effectively)
        if cmd_key == "skip":
            # If a group is specified, stop that group's assigned channel
            target_group = args[1].upper() if len(args) > 1 else None
            
            if target_group:
                 categories = self.config_manager.get_audio_categories()
                 
                 # Check if this group exists in config
                 if target_group in categories or any(cmd.get("Group") == target_group for cmd in getattr(self, "_commands_list", [])):
                     channel_id = categories.get(target_group, {}).get("audio_channel", 0)
                     
                     if channel_id > 0:
                         # Dedicated channel
                         target_chan = pygame.mixer.Channel(channel_id)
                         if target_chan.get_busy():
                             target_chan.stop()
                             await message.channel.send(f"@{username}: Skipped sound for group '{target_group}' (Channel {channel_id}).")
                         else:
                             await message.channel.send(f"@{username}: No sound playing on channel {channel_id} (group '{target_group}').")
                     else:
                         # Shared channel (0)
                         if self.sound_channel.get_busy():
                             self.sound_channel.stop()
                             await message.channel.send(f"@{username}: Skipped sound on main channel (for group '{target_group}').")
                         else:
                             await message.channel.send(f"@{username}: No sound playing on main channel.")
                 else:
                      await message.channel.send(f"@{username}: Group '{target_group}' not found.")
            else:
                # No group specified = stop only the current sound on main channel
                if self.sound_channel.get_busy():
                    self.sound_channel.stop()
                    await message.channel.send(f"@{username}: Skipped current sound.")
                else:
                    await message.channel.send(f"@{username}: No sound is currently playing.")
            return

        # !clear [group]
        if cmd_key == "clear":
            target_group = args[1].upper() if len(args) > 1 else None
            
            if target_group:
                if target_group in self.command_queues:
                    q = self.command_queues[target_group]
                    # Используем get_nowait() без task_done(), так как элементы не будут обрабатываться
                    # Просто сбрасываем очередь
                    count = 0
                    while True:
                        try:
                            q.get_nowait()
                            count += 1
                        except asyncio.QueueEmpty:
                            break
                    # Освобождаем semaphore если он есть
                    semaphore = self.queue_semaphores.get(target_group)
                    if semaphore is not None:
                        # Возвращаем все захваченные семафоры обратно
                        for _ in range(count):
                            try:
                                semaphore.release()
                            except RuntimeError:
                                # Семафор не был захвачен
                                pass
                    await message.channel.send(f"@{username}: Cleared {count} commands from '{target_group}' queue.")
                else:
                    await message.channel.send(f"@{username}: Queue group '{target_group}' not found.")
            else:
                 await message.channel.send(f"@{username}: Usage: !clear <group_name>")
            return

        # !volume [group] [0-100] (Targeting specific group or default group)
        if cmd_key == "volume":
            try:
                categories = self.config_manager.get_audio_categories()
                
                # Get default group from system command config if available
                default_group = "SONG"  # Fallback default
                if sys_cmd and "default_group" in sys_cmd:
                    default_group = sys_cmd["default_group"]
                
                # Parse arguments: !volume [group] [volume]
                # If only one argument, it's volume for default group
                # If two arguments, first is group, second is volume
                if len(args) == 1:
                    # No group specified, use default group from config
                    target_group = default_group
                    vol_arg = int(args[0])
                elif len(args) == 2:
                    # Group and volume specified
                    target_group = args[0].upper()
                    vol_arg = int(args[1])
                else:
                    await message.channel.send(f"@{username}: Usage: !volume [group] <0-100>")
                    return
                
                # Validate volume
                if not (0 <= vol_arg <= 100):
                    await message.channel.send(f"@{username}: Volume must be between 0 and 100.")
                    return
                
                # Find the group's channel
                if target_group not in categories:
                    await message.channel.send(f"@{username}: Group '{target_group}' not found in audio categories.")
                    return
                
                channel_id = categories.get(target_group, {}).get("audio_channel", 0)
                new_vol = vol_arg / 100.0
                
                # Get the channel and update its volume
                target_channel = pygame.mixer.Channel(channel_id)
                
                # Apply volume change to currently playing sound if any
                # This allows real-time volume adjustment during playback
                if channel_id in self.active_sounds:
                    try:
                        self.active_sounds[channel_id].set_volume(new_vol)
                        await message.channel.send(f"@{username}: Volume for group '{target_group}' set to {vol_arg}% (applied to current track)")
                        print(f"Volume for group '{target_group}' updated to {new_vol} (applied to active sound)")
                    except Exception as vol_error:
                        print(f"Warning: Could not apply volume to active sound: {vol_error}")
                        await message.channel.send(f"@{username}: Volume for group '{target_group}' set to {vol_arg}% (will apply to next track)")
                else:
                    # No active sound, just set volume for next track
                    target_channel.set_volume(new_vol)
                    await message.channel.send(f"@{username}: Volume for group '{target_group}' set to {vol_arg}%")
                    print(f"Volume for group '{target_group}' (Channel {channel_id}) updated to {new_vol}")
                
                # Save the volume to config so it persists for future tracks
                self.config_manager.set_group_volume(target_group, new_vol)
                
            except (ValueError, IndexError):
                await message.channel.send(f"@{username}: Usage: !volume [group] <0-100>")
            except Exception as e:
                print(f"Error setting volume: {e}")
            return

    async def execute_system_command(self, message, username, sys_cmd, full_content):
        """Execute a system command based on its type and configuration"""
        command_type = sys_cmd.get("command", "").lower()
        command_name = sys_cmd.get("command_name", sys_cmd["command"]).lower()
        

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
            is_mod = await self.is_user_moderator(username)
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
            is_mod = await self.is_user_moderator(username)
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
                
            # Perform transfer
            self.currency_manager.remove_points(username, amount)
            self.currency_manager.add_points(target_user, amount)
            
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

        # Process the selected command as if it was triggered directly
        # We need to simulate the command execution with the selected command's settings
        cmd_key = self.normalize_command_key(selected_cmd["Command"].lstrip('!'))

        # Check cooldowns for the selected command
        cooldown_min = int(selected_cmd.get("Cooldown", 0))
        user_cooldown_min = int(selected_cmd.get("UserCooldown", 0))
        cooldown_sec = cooldown_min * 60
        user_cooldown_sec = user_cooldown_min * 60
        current_time = time.time()

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
        cost = int(selected_cmd.get("Cost", 0))
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

        # Show picked command if enabled
        if sys_cmd.get("show_picked_command", True):
            response_template = sys_cmd.get("picked_command_response", "Picked {command}.")
            formatted_response = response_template.replace("{command}", selected_cmd['Command'])
            await message.channel.send(formatted_response)

        # Execute the command's response
        resp = selected_cmd.get("Response", "")
        if resp and resp.strip():
            await self.send_multiline_response(message.channel, resp, username)

        # Execute the command's sound if any
        sf = selected_cmd.get("SoundFile", "").strip()
        if sf:
            volume = int(selected_cmd.get("Volume", 100))
            sound_played = self.play_sound(sf, volume)
            if sound_played:
                print(f"Successfully played sound for random command '{cmd_key}'")

        # Update cooldowns after successful execution
        if cooldown_sec > 0:
            self.global_cooldowns[cmd_key] = current_time
        if user_cooldown_sec > 0:
            self.user_cooldowns.setdefault(cmd_key, {})[username] = current_time

        print(f"Random command executed: {selected_cmd['Command']} from group '{group_name}' by {username}")
