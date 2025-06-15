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
            self.sound_channel = sound_channel or pygame.mixer.Channel(1)  # Канал 1, чтобы не конфликтовать с CommandEditor
            
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
        except Exception as e:
            print(f"CRITICAL ERROR in event_ready: {e}")
            import traceback; traceback.print_exc()

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
        
        # Проверка на команду !add_points (только для модераторов)
        if key == "add_points" and hasattr(self, 'currency_manager'):
            # Проверяем, является ли пользователь модератором
            is_mod = await self.is_user_moderator(username)
            if not is_mod:
                await message.channel.send(f"@{username}: You don't have permission to use this command.")
                return
                
            # Парсим сообщение для получения параметров (имя пользователя и количество очков)
            args = content.split(maxsplit=2)[1:]
            if len(args) < 2:
                await message.channel.send(f"@{username}: Usage: !add_points @username amount")
                return
                
            # Получаем имя пользователя (удаляем @ если есть)
            target_user = args[0]
            if target_user.startswith('@'):
                target_user = target_user[1:]
            target_user = target_user.lower()
                
            # Парсим количество очков
            try:
                points_amount = float(args[1])
                # Округляем до двух знаков после запятой
                points_amount = round(points_amount, 2)
                if points_amount <= 0:
                    await message.channel.send(f"@{username}: Amount must be greater than 0")
                    return
            except ValueError:
                await message.channel.send(f"@{username}: Invalid amount format. Use numbers only.")
                return
                
            # Добавляем очки
            current_points = self.currency_manager.add_points(target_user, points_amount)
            self.currency_manager.save_users()
            
            # Отправляем ответ
            formatted_points = f"{float(current_points):.2f}"
            await message.channel.send(
                f"@{target_user} received {points_amount:.2f} points from @{username}. New balance: {formatted_points}"
            )
            return
            
        # Проверка на команду !remove_points (только для модераторов)
        if key == "remove_points" and hasattr(self, 'currency_manager'):
            # Проверяем, является ли пользователь модератором
            is_mod = await self.is_user_moderator(username)
            if not is_mod:
                await message.channel.send(f"@{username}: You don't have permission to use this command.")
                return
                
            # Парсим сообщение для получения параметров (имя пользователя и количество очков)
            args = content.split(maxsplit=2)[1:]
            if len(args) < 2:
                await message.channel.send(f"@{username}: Usage: !remove_points @username amount")
                return
                
            # Получаем имя пользователя (удаляем @ если есть)
            target_user = args[0]
            if target_user.startswith('@'):
                target_user = target_user[1:]
            target_user = target_user.lower()
                
            # Парсим количество очков
            try:
                points_amount = float(args[1])
                # Округляем до двух знаков после запятой
                points_amount = round(points_amount, 2)
                if points_amount <= 0:
                    await message.channel.send(f"@{username}: Amount must be greater than 0")
                    return
            except ValueError:
                await message.channel.send(f"@{username}: Invalid amount format. Use numbers only.")
                return
                
            # Получаем текущие очки пользователя
            current_points = self.currency_manager.get_points(target_user)
            
            # Проверяем, хватает ли очков
            if current_points < points_amount:
                await message.channel.send(
                    f"@{username}: User @{target_user} only has {current_points:.2f} points, cannot remove {points_amount:.2f}"
                )
                return
                
            # Снимаем очки
            self.currency_manager.remove_points(target_user, points_amount)
            new_balance = self.currency_manager.get_points(target_user)
            self.currency_manager.save_users()
            
            # Отправляем ответ
            await message.channel.send(
                f"@{username} removed {points_amount:.2f} points from @{target_user}. New balance: {new_balance:.2f}"
            )
            return
        
        # Проверка на специальную команду !points до проверки custom команд
        if key == "points" and hasattr(self, 'currency_manager'):
            # Проверяем cooldown для points команды
            cmd_key = "points"
            cooldown_sec = self.currency_manager.settings.get('cooldown', 5)  # в секундах
            
            # Нормализуем ключ команды и проверяем, не содержит ли он невидимые символы
            normalized_key = self.normalize_command_key(cmd_key)
            
            # Используем нормалованный ключ для проверки кулдауна
            last_used = self.user_cooldowns.get(normalized_key, {}).get(username, 0)
            elapsed = current_time - last_used
            
            if cooldown_sec > 0 and elapsed < cooldown_sec:
                remaining = int(cooldown_sec - elapsed)
                await message.channel.send(
                    f"@{username}: command is on cooldown. Try in {remaining} sec."
                )
                return
            
            # Команда выполняется - формируем и отправляем ответ
            response = self.currency_manager.format_currency_message(username)
            await message.channel.send(response)
            
            # Обновляем время последнего использования только ПОСЛЕ успешного выполнения
            if cooldown_sec > 0:  # Проверяем, что кулдаун активен
                self.user_cooldowns.setdefault(normalized_key, {})[username] = current_time
            
            # Логируем выполнение команды
            print(f"Points command executed by {username}")
            return

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
            
            # Отправка текста-ответа
            resp = cmd.get("Response", "").replace("{user}", message.author.name)
            if resp and resp.strip():
                has_response = True
                await message.channel.send(resp)
                command_executed = True
                print(f"Sent text response for command '{cmd_key}'")
                
            # Проигрывание звука
            sf = cmd.get("SoundFile", "").strip()
            if sf:
                has_sound = True
                volume = int(cmd.get("Volume", 100))
                sound_played = self.play_sound(sf, volume)
                if sound_played:
                    print(f"Successfully played sound for command '{cmd_key}'")
                    command_executed = True
                else:
                    print(f"Failed to play sound for command '{cmd_key}'")
                    
            # Команда считается выполненной если либо был отправлен ответ,
            # либо успешно проигран звук, либо оба действия
            
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
    
    def play_sound(self, filepath, volume=100):
        """Проигрывание звукового файла с учетом настроек прерывания и громкости
        Возвращает True, если звук был успешно запущен, False в противном случае"""
        try:
            # Проверка существования файла
            if not os.path.exists(filepath):
                print(f"Sound file not found: {filepath}")
                return False

            # Проверка активного воспроизведения
            if self.sound_channel.get_busy():
                allow_interrupt = getattr(self, 'allow_sound_interruption', False)
                print(f"Checking interruption in play_sound. Allowed: {allow_interrupt}")
                
                if allow_interrupt:
                    print("Interrupting sound...")
                    self.sound_channel.fadeout(100)
                else:
                    print("Blocking sound...")
                    # Важно: не отправляем сообщение здесь, так как оно будет дублироваться с сообщением
                    # о возврате очков. Вместо этого просто логируем блокировку
                    show_message = getattr(self, 'show_interruption_message', False)
                    if show_message and self.connected_channels:
                        # Мы теперь отправляем более подробное сообщение о блокировке в основном коде
                        # так что здесь просто логируем это событие
                        print("Sound blocked because another sound is playing")
                    return False  # Не проигрываем новый звук

            # Загрузка и воспроизведение звука
            snd = self.loaded_sounds.get(filepath)
            if snd is None:
                snd = pygame.mixer.Sound(filepath)
                self.loaded_sounds[filepath] = snd

            # Применяем громкость команды (из параметра volume)
            vol = float(volume) / 100.0
            print(f"Setting sound volume to: {vol} (from command volume: {volume})")
            snd.set_volume(vol)

            # Воспроизводим на нашем канале
            self.sound_channel.play(snd)
            print(f"Playing sound: {filepath}")
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
                # Если есть данные, значит стрим идёт
                is_live = len(data.get("data", [])) > 0
                
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
        """Получает список модераторов канала через API"""
        try:
            if not self.broadcaster_id or not self._helix_headers:
                print("Cannot fetch moderators: missing broadcaster_id or API headers")
                return []
                
            # Запрашиваем данные о модераторах
            response = requests.get(
                "https://api.twitch.tv/helix/moderation/moderators",
                headers=self._helix_headers,
                params={"broadcaster_id": self.broadcaster_id},
                timeout=5
            )
            
            mods = []
            # Если запрос успешен
            if response.status_code == 200:
                data = response.json()
                # Перебираем всех модераторов
                for mod in data.get("data", []):
                    mod_name = mod.get("user_login", "").lower()
                    mods.append(mod_name)
                    
                    # Обновляем статус модератора в системе валюты
                    if hasattr(self, 'currency_manager') and mod_name in self.currency_manager.users:
                        self.currency_manager.users[mod_name]['is_mod'] = True
                        print(f"User {mod_name} marked as moderator")
                
                # Дополнительно добавляем владельца канала как модератора
                if self.channel.lower() not in mods:
                    mods.append(self.channel.lower())
                    if hasattr(self, 'currency_manager') and self.channel.lower() in self.currency_manager.users:
                        self.currency_manager.users[self.channel.lower()]['is_mod'] = True
                        print(f"Channel owner {self.channel} marked as moderator")
                
                # Сохраняем изменения в системе валюты
                self.currency_manager.save_users()
                
                # Отправляем сигнал с обновленным списком модераторов, если есть signal_handler
                if hasattr(self, 'signal_handler') and self.signal_handler:
                    self.signal_handler.moderators_signal.emit(mods)
                    
                return mods
            else:
                print(f"Error fetching moderators: API returned {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Error fetching moderators: {e}")
            return []

    async def is_user_moderator(self, username):
        """Проверяет, является ли пользователь модератором канала"""
        # Нормализуем имя пользователя
        username = username.lower()
        
        # Владелец канала всегда считается модератором
        if username == self.channel.lower():
            return True
            
        # Проверяем, есть ли у пользователя флаг модератора в системе валюты
        if hasattr(self, 'currency_manager') and username in self.currency_manager.users:
            if self.currency_manager.users[username].get('is_mod', False):
                return True
                
        # Используем get_channel_moderators для получения актуального списка модераторов
        try:
            moderators = await self.get_channel_moderators()
            return username in moderators
        except Exception as e:
            print(f"Error checking moderator status: {e}")
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
                if not (ctx.author.is_mod or ctx.author.is_broadcaster):
                    await ctx.send(f"@{ctx.author.name}: You don't have permission to use this command")
                    return

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
                if not (ctx.author.is_mod or ctx.author.is_broadcaster):
                    await ctx.send(f"@{ctx.author.name}: You don't have permission to use this command")
                    return

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
            
        except Exception as e:
            print(f"Error cleaning up cooldowns: {e}")
            import traceback
            traceback.print_exc()