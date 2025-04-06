import os
import json
import asyncio
import pygame
import time
from twitchio.ext import commands
import threading
from PyQt6.QtCore import QObject, pyqtSignal
from config_manager import ConfigManager

class TwitchBot(commands.Bot):
    def __init__(self, channel, message_callback):
        self.channel = channel
        self.message_callback = message_callback
        self.custom_commands = []
        self.volume = 1.0
        self.is_running = False
        self.connected_channel = None
        
        # Структуры данных для отслеживания cooldown
        self.last_command_usage = {}  # Для глобального кулдауна: {command: timestamp}
        self.user_command_usage = {}  # Для пользовательского кулдауна: {command: {user_id: timestamp}}
        
        # Initialize pygame mixer
        pygame.mixer.init()
        
        # Get credentials from config
        config_manager = ConfigManager()
        twitch_config = config_manager.get_twitch_config()
        
        # Проверяем наличие токенов
        if not twitch_config.get('access_token') or not twitch_config.get('client_id'):
            if message_callback:
                message_callback("Twitch credentials not found. Please configure them first.")
            print("Warning: Twitch credentials not found. Bot will not be able to connect.")
            return
        
        # Если токены есть, инициализируем бота
        try:
            super().__init__(
                token=twitch_config['access_token'],
                prefix='!',
                initial_channels=[channel] if channel else []
            )
            print(f"Bot initialized with channel: {channel}")
        except Exception as e:
            error_msg = f"Error initializing bot: {str(e)}"
            print(error_msg)
            if message_callback:
                message_callback(error_msg)
        
    async def event_ready(self):
        """Called once when the bot goes online"""
        print(f'Bot is ready! Username: {self.nick}')
        self.is_running = True
        
        # Wait a bit for channels to be ready
        await asyncio.sleep(2)
        
        # Get the channel object after connection is established
        self.connected_channel = self.get_channel(self.channel)
        if self.connected_channel:
            print(f'Connected to channel: {self.channel}')
            if self.message_callback:
                self.message_callback(f"Connected to {self.channel}")
        else:
            print(f'Failed to get channel object for: {self.channel}')
            if self.message_callback:
                self.message_callback(f"Failed to connect to {self.channel}")
            
    async def event_message(self, message):
        """Called when a message is received in the chat"""
        if message.echo:
            return
            
        # Log the message
        print(f'Message from {message.author.name}: {message.content}')
        
        # Emit message to UI
        if self.message_callback:
            self.message_callback(f'{message.author.name}: {message.content}')
        
        # Check if it's a command
        if message.content.startswith('!'):
            command = message.content.split()[0].lower()
            
            # Check if command exists and is enabled
            for cmd in self.custom_commands:
                cmd_name = cmd["Command"].lower()
                
                if command == cmd_name and cmd["Enabled"]:
                    # Проверка глобального кулдауна
                    current_time = time.time()
                    cooldown_minutes = int(cmd.get("Cooldown", 0))
                    cooldown_seconds = cooldown_minutes * 60  # Преобразуем минуты в секунды
                    
                    if cooldown_minutes > 0 and cmd_name in self.last_command_usage:
                        last_usage = self.last_command_usage[cmd_name]
                        elapsed = current_time - last_usage
                        
                        if elapsed < cooldown_seconds:
                            remaining_seconds = int(cooldown_seconds - elapsed)
                            remaining_minutes = remaining_seconds // 60
                            remaining_seconds_mod = remaining_seconds % 60
                            
                            # Формируем строку для отображения (минуты и секунды)
                            if remaining_minutes > 0:
                                time_str = f"{remaining_minutes} min. {remaining_seconds_mod} sec."
                            else:
                                time_str = f"{remaining_seconds_mod} sec."
                                
                            # Отправляем сообщение о кулдауне
                            await message.channel.send(f"Command {cmd_name} in cooldown. Try in {time_str}")
                            
                            # Записываем в UI
                            if self.message_callback:
                                self.message_callback(f"Cooldown: {cmd_name} ({time_str} remaining)")
                                
                            return  # Прерываем обработку команды
                    
                    # Проверка пользовательского кулдауна
                    user_id = str(message.author.id)
                    user_cooldown_minutes = int(cmd.get("UserCooldown", 0))
                    user_cooldown_seconds = user_cooldown_minutes * 60  # Преобразуем минуты в секунды
                    
                    if user_cooldown_minutes > 0:
                        if cmd_name in self.user_command_usage and user_id in self.user_command_usage[cmd_name]:
                            user_last_usage = self.user_command_usage[cmd_name][user_id]
                            user_elapsed = current_time - user_last_usage
                            
                            if user_elapsed < user_cooldown_seconds:
                                user_remaining_seconds = int(user_cooldown_seconds - user_elapsed)
                                user_remaining_minutes = user_remaining_seconds // 60
                                user_remaining_seconds_mod = user_remaining_seconds % 60
                                
                                # Формируем строку для отображения (минуты и секунды)
                                if user_remaining_minutes > 0:
                                    user_time_str = f"{user_remaining_minutes} min. {user_remaining_seconds_mod} sec."
                                else:
                                    user_time_str = f"{user_remaining_seconds_mod} sec."
                                
                                # Отправляем личное сообщение о кулдауне
                                await message.channel.send(f"@{message.author.name}, you can use {cmd_name} after {user_time_str}")
                                
                                # Записываем в UI
                                if self.message_callback:
                                    self.message_callback(f"User Cooldown: {message.author.name} for {cmd_name} ({user_time_str} remaining)")
                                    
                                return  # Прерываем обработку команды
                    
                    # Если прошли все проверки, обновляем время использования
                    self.last_command_usage[cmd_name] = current_time
                    
                    if cmd_name not in self.user_command_usage:
                        self.user_command_usage[cmd_name] = {}
                    self.user_command_usage[cmd_name][user_id] = current_time
                    
                    # Play sound if file exists
                    if cmd.get("SoundFile") and os.path.exists(cmd["SoundFile"]):
                        try:
                            # Get volume from command settings
                            volume = float(cmd.get("Volume", 100)) / 100.0
                            self.play_sound(cmd["SoundFile"], volume * 100)
                        except Exception as e:
                            error_msg = f'Error playing sound: {str(e)}'
                            print(error_msg)
                            if self.message_callback:
                                self.message_callback(error_msg)
                            
                    # Send response if exists
                    if cmd.get("Response"):
                        try:
                            # Используем только один метод отправки сообщений
                            await message.channel.send(cmd["Response"])
                            
                            # Логируем в UI
                            if self.message_callback:
                                self.message_callback(f'{self.nick}: {cmd["Response"]}')
                        except Exception as e:
                            error_msg = f'Error sending response: {str(e)}'
                            print(error_msg)
                            if self.message_callback:
                                self.message_callback(error_msg)
                            
                    # Увеличиваем счетчик использования команды
                    cmd["Count"] = cmd.get("Count", 0) + 1
                    
                    break
            
    def play_sound(self, sound_file, volume=100):
        """Play a sound file with specified volume"""
        try:
            if not sound_file or not os.path.exists(sound_file):
                if self.message_callback:
                    self.message_callback(f"Sound file not found: {sound_file}")
                return
                
            if self.message_callback:
                self.message_callback(f"Playing sound: {sound_file} at volume {volume}%")
            
            # Stop any currently playing sounds
            pygame.mixer.stop()
            
            # Load and play the sound with specified volume
            sound = pygame.mixer.Sound(sound_file)
            sound.set_volume(volume / 100.0)  # Convert percentage to 0-1 range
            sound.play()
            
        except Exception as e:
            error_msg = f"Error playing sound: {str(e)}"
            print(error_msg)
            if self.message_callback:
                self.message_callback(error_msg)
            
    def update_commands(self, commands):
        """Update the list of commands"""
        self.custom_commands = commands
        # Only show total number of commands
        enabled_commands = [cmd for cmd in commands if cmd["Enabled"] and cmd.get("SoundFile")]
        print(f"Commands updated. Total commands: {len(commands)}, Enabled with sound: {len(enabled_commands)}")
        
    def clear_cooldowns(self, command=None):
        """Clear cooldowns for a specific command or all commands"""
        if command:
            if command in self.last_command_usage:
                del self.last_command_usage[command]
            if command in self.user_command_usage:
                del self.user_command_usage[command]
            if self.message_callback:
                self.message_callback(f"Cooldown cleared for command: {command}")
        else:
            self.last_command_usage = {}
            self.user_command_usage = {}
            if self.message_callback:
                self.message_callback("All cooldowns cleared")
                
    async def send_message(self, message):
        """Send a message to the connected channel"""
        if not self.connected_channel:
            # Try to get channel again
            self.connected_channel = self.get_channel(self.channel)
            
        if self.connected_channel:
            await self.connected_channel.send(message)
            # Display sent message in UI
            if self.message_callback:
                self.message_callback(f'{self.nick}: {message}')
        else:
            print(f'Cannot send message: channel not connected')
            if self.message_callback:
                self.message_callback(f"Failed to send message: channel not connected")
                
    def run(self):
        """Run the bot"""
        try:
            # Проверяем, был ли бот правильно инициализирован
            if not hasattr(self, 'loop'):
                if self.message_callback:
                    self.message_callback("Bot was not properly initialized. Cannot run.")
                print("Bot was not properly initialized. Cannot run.")
                return
                
            self.loop.run_until_complete(self.start())
            self.is_running = True
        except Exception as e:
            error_msg = f"Error in bot: {str(e)}"
            print(error_msg)
            if self.message_callback:
                self.message_callback(error_msg)
            self.is_running = False
            
    def stop(self):
        """Stop the bot"""
        if not hasattr(self, 'loop'):
            # Если бот не был инициализирован правильно, нечего останавливать
            return
            
        if self.is_running:
            self.loop.stop()
            self.is_running = False