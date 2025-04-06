from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QLineEdit, QPushButton, QTextEdit, QGroupBox,
                            QMessageBox, QDialog)
from PyQt6.QtCore import pyqtSignal, QObject, Qt
import threading
import json
import os
from twitch_bot import TwitchBot
from twitch_auth import TwitchAuthDialog
from config_manager import ConfigManager
import asyncio
import time
import webbrowser  # Импортируем модуль для открытия URL в браузере

class TwitchSignals(QObject):
    message_received = pyqtSignal(str)

class TwitchTab(QWidget):
    def __init__(self, parent=None, commands_data=None):
        super().__init__(parent)
        self.commands_data = commands_data
        self.bot = None
        self.bot_thread = None
        self.signals = TwitchSignals()
        self.signals.message_received.connect(self.add_to_chat)
        self.config_manager = ConfigManager()
        self.is_updating_commands = False  # Add flag to track command updates
        
        # Create main layout
        layout = QVBoxLayout()
        
        # Create Twitch auth group
        auth_group = QGroupBox("Twitch Authentication")
        auth_layout = QVBoxLayout()
        
        auth_btn = QPushButton("Configure Twitch Credentials")
        auth_btn.clicked.connect(self.show_auth_dialog)
        auth_layout.addWidget(auth_btn)
        
        # Добавляем кнопку для перехода на TwitchTokenGenerator
        token_gen_btn = QPushButton("Open Twitch Token Generator")
        token_gen_btn.clicked.connect(self.open_token_generator)  # Подключаем обработчик
        auth_layout.addWidget(token_gen_btn)  # Добавляем кнопку в layout
        
        auth_group.setLayout(auth_layout)
        layout.addWidget(auth_group)
        
        # Create chat connection group
        chat_group = QGroupBox("Chat Connection")
        chat_layout = QHBoxLayout()
        
        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("Enter channel name")
        self.connect_btn = QPushButton("Connect")
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.setEnabled(False)
        
        chat_layout.addWidget(QLabel("Channel:"))
        chat_layout.addWidget(self.channel_edit)
        chat_layout.addWidget(self.connect_btn)
        chat_layout.addWidget(self.disconnect_btn)
        
        chat_group.setLayout(chat_layout)
        layout.addWidget(chat_group)
        
        # Create chat display group
        display_group = QGroupBox("Chat")
        display_layout = QVBoxLayout()
        
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        display_layout.addWidget(self.chat_display)
        
        # Add chat input
        input_layout = QHBoxLayout()
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Type your message...")
        self.message_input.returnPressed.connect(self.send_message)
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_btn)
        display_layout.addLayout(input_layout)
        
        display_group.setLayout(display_layout)
        layout.addWidget(display_group)
        
        # Connect signals
        self.connect_btn.clicked.connect(self.connect)
        self.disconnect_btn.clicked.connect(self.disconnect)
        
        self.setLayout(layout)
        
        # Load saved settings
        self.load_settings()
        
    def load_settings(self):
        twitch_config = self.config_manager.get_twitch_config()
        self.channel_edit.setText(twitch_config.get('channel', ''))
            
    def save_settings(self):
        """Save Twitch settings to config file"""
        try:
            # Сохраняем только канал, не трогая токены
            channel = self.channel_edit.text().strip()
            self.config_manager.set_twitch_channel(channel)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save settings: {str(e)}")
            
    def show_auth_dialog(self):
        """Show Twitch authentication dialog"""
        dialog = TwitchAuthDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # The credentials are already saved by the dialog
            # No need to update anything here
            pass
            
    def connect(self):
        if not self.bot:
            channel = self.channel_edit.text().strip()
            if not channel:
                QMessageBox.warning(self, "Error", "Please enter a channel name")
                return
                
            # Проверяем наличие токенов перед подключением
            twitch_config = self.config_manager.get_twitch_config()
            if not twitch_config.get('access_token') or not twitch_config.get('client_id'):
                QMessageBox.warning(self, "Error", "Twitch credentials not found. Please configure them first.")
                self.show_auth_dialog()
                return
                
            try:
                # Сохраняем канал
                self.config_manager.set_twitch_channel(channel)
                
                # Initialize bot with proper event loop
                self.bot = TwitchBot(channel, self.signals.message_received.emit)
                
                # Check if bot was properly initialized
                if not hasattr(self.bot, 'loop'):
                    QMessageBox.warning(self, "Error", "Failed to initialize Twitch bot. Please check your credentials.")
                    self.bot = None
                    return
                    
                if self.commands_data:
                    self.bot.custom_commands = self.commands_data
                
                # Start bot in a separate thread
                self.bot_thread = threading.Thread(target=self.bot.run)
                self.bot_thread.daemon = True
                self.bot_thread.start()
                
                # Update button states
                self.connect_btn.setEnabled(False)
                self.disconnect_btn.setEnabled(True)
                self.add_to_chat(f"Connected to {channel}")
                
                # Disable command editing in command editor
                if hasattr(self.parent(), 'command_editor'):
                    self.parent().command_editor.set_editing_enabled(False)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to connect: {str(e)}")
                if self.bot:
                    self.bot = None
                    
    def disconnect(self):
        if self.bot:
            try:
                self.bot.stop()
                self.bot = None
                self.connect_btn.setEnabled(True)
                self.disconnect_btn.setEnabled(False)
                self.add_to_chat("Disconnected")
                
                # Enable command editing in command editor
                if hasattr(self.parent(), 'command_editor'):
                    self.parent().command_editor.set_editing_enabled(True)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error disconnecting: {str(e)}")
                
    def update_commands(self, commands):
        """Update commands in the bot if it's running"""
        # Store the new commands
        self.commands_data = commands
        
        # Check if bot was running
        was_connected = self.bot and self.bot.is_running
        
        # If bot was running, stop it and wait for it to fully stop
        if was_connected:
            self.disconnect()
            # Wait a bit for bot to fully stop
            time.sleep(0.5)
            
        # Create new bot instance with updated commands
        if was_connected:
            channel = self.channel_edit.text().strip()
            if channel:
                try:
                    self.bot = TwitchBot(channel, self.signals.message_received.emit)
                    
                    # Check if bot was properly initialized
                    if not hasattr(self.bot, 'loop'):
                        self.add_to_chat("Failed to reinitialize bot after command update")
                        return
                        
                    self.bot.custom_commands = commands
                    # Start bot in a separate thread
                    self.bot_thread = threading.Thread(target=self.bot.run)
                    self.bot_thread.daemon = True
                    self.bot_thread.start()
                    self.connect_btn.setEnabled(False)
                    self.disconnect_btn.setEnabled(True)
                    self.add_to_chat(f"Reconnected to {channel} with updated commands")
                except Exception as e:
                    self.add_to_chat(f"Failed to reconnect after command update: {str(e)}")
                    
    def add_to_chat(self, message):
        """Add a message to the chat display"""
        self.chat_display.append(message)
        # Scroll to bottom
        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )
        
    def send_message(self):
        """Send a message to the chat"""
        if not self.bot:
            QMessageBox.warning(self, "Error", "Not connected to chat")
            return
            
        # Check if bot was properly initialized and is running
        if not hasattr(self.bot, 'loop') or not self.bot.is_running:
            QMessageBox.warning(self, "Error", "Twitch bot is not properly connected")
            return
            
        message = self.message_input.text().strip()
        # Remove any non-printable characters
        message = ''.join(char for char in message if char.isprintable())
        
        if message:
            try:
                # Send message using bot's method
                asyncio.run_coroutine_threadsafe(
                    self.bot.send_message(message),
                    self.bot.loop
                )
                self.message_input.clear()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to send message: {str(e)}")

    def open_token_generator(self):
        """Открывает сайт Twitch Token Generator в браузере"""
        webbrowser.open("https://twitchtokengenerator.com/") 