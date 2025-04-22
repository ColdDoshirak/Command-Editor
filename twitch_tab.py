from PyQt5 import sip
from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QMetaType, Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QGroupBox, QMessageBox, QDialog, QListWidget, QSplitter,
    QGridLayout, QSizePolicy, QTabWidget, QComboBox
)
import threading
import asyncio
import time
import webbrowser
import requests
import concurrent.futures
from datetime import datetime

from twitch_bot import TwitchBot
from twitch_auth import TwitchAuthDialog
from config_manager import ConfigManager

# регистрируем QTextCursor для передачи в сигналах
QMetaType.type("QTextCursor")

class ChatSignalHandler(QObject):
    chat_signal = pyqtSignal(str)
    active_viewers_signal = pyqtSignal(list)
    all_viewers_signal = pyqtSignal(list)
    stream_status_signal = pyqtSignal(bool)
    currency_updated = pyqtSignal()
    moderators_signal = pyqtSignal(list)  # Новый сигнал для списка модераторов

class TwitchTab(QWidget):
    def __init__(self, parent=None, commands_data=None):
        super().__init__(parent)
        self.parent = parent
        self.commands_data = commands_data or []
        self.bot = None
        self.bot_thread = None
        self.active_users = []
        self.currently_live = False
        self.moderators_list = []  # Список модераторов канала

        self.signal_handler = ChatSignalHandler()
        self.signal_handler.chat_signal.connect(self.add_to_chat_safe)
        self.signal_handler.active_viewers_signal.connect(self.update_active_viewers)
        self.signal_handler.all_viewers_signal.connect(self.update_all_viewers)
        self.signal_handler.stream_status_signal.connect(self.update_stream_status)
        self.signal_handler.currency_updated.connect(self.update_currency)
        self.signal_handler.moderators_signal.connect(self.update_moderators_list)  # Подключаем новый сигнал

        self.config_manager = ConfigManager()
        self.initUI()
        self.load_settings()

    def initUI(self):
        layout = QVBoxLayout(self)

        # Authentication
        auth_group = QGroupBox("Authentication")
        auth_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        auth_layout = QGridLayout()
        auth_layout.addWidget(QLabel("Status:"), 0, 0)
        self.auth_status = QLabel("Not authenticated")
        auth_layout.addWidget(self.auth_status, 0, 1)
        self.auth_button = QPushButton("Authenticate with Twitch")
        self.auth_button.clicked.connect(self.show_auth_dialog)
        auth_layout.addWidget(self.auth_button, 0, 2)
        self.token_button = QPushButton("Get Access Token")
        self.token_button.clicked.connect(self.open_token_generator)
        auth_layout.addWidget(self.token_button, 0, 3)
        auth_group.setLayout(auth_layout)
        layout.addWidget(auth_group)

        # Connection
        conn_group = QGroupBox("Connection Settings")
        conn_group.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        conn_layout = QHBoxLayout()
        conn_layout.addWidget(QLabel("Channel:"))
        self.channel_input = QLineEdit()
        conn_layout.addWidget(self.channel_input)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_bot)
        conn_layout.addWidget(self.connect_button)
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.clicked.connect(self.disconnect)
        conn_layout.addWidget(self.disconnect_button)
        self.check_connection_button = QPushButton("Check Connection")
        self.check_connection_button.clicked.connect(self.check_connection)
        conn_layout.addWidget(self.check_connection_button)
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)

        # Chat & Viewers splitter
        splitter = QSplitter(Qt.Horizontal)

        # Chat
        chat_group = QGroupBox("Chat")
        chat_layout = QVBoxLayout()
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        chat_layout.addWidget(self.chat_display)
        input_layout = QHBoxLayout()
        self.message_input = QLineEdit()
        self.message_input.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.message_input)
        self.send_button = QPushButton("Send")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)
        chat_layout.addLayout(input_layout)
        chat_group.setLayout(chat_layout)
        splitter.addWidget(chat_group)

        # Viewers
        viewer_group = QGroupBox("Viewers")
        viewer_layout = QVBoxLayout()
        self.viewers_tabs = QTabWidget()
        # All viewers
        all_tab = QWidget()
        all_layout = QVBoxLayout()
        self.all_viewers_list = QListWidget()
        all_layout.addWidget(self.all_viewers_list)
        all_tab.setLayout(all_layout)
        self.viewers_tabs.addTab(all_tab, "All Viewers")
        # Active chatters
        active_tab = QWidget()
        active_layout = QVBoxLayout()
        self.active_viewers_list = QListWidget()
        active_layout.addWidget(self.active_viewers_list)
        active_tab.setLayout(active_layout)
        self.viewers_tabs.addTab(active_tab, "Active Chatters")
        # Moderators
        moderators_tab = QWidget()
        moderators_layout = QVBoxLayout()
        self.moderators_list_widget = QListWidget()
        moderators_layout.addWidget(self.moderators_list_widget)
        moderators_tab.setLayout(moderators_layout)
        self.viewers_tabs.addTab(moderators_tab, "Moderators")
        viewer_layout.addWidget(self.viewers_tabs)
        # Refresh controls
        refresh_layout = QHBoxLayout()
        self.refresh_viewers_button = QPushButton("Refresh")
        self.refresh_viewers_button.clicked.connect(self.refresh_viewers)
        refresh_layout.addWidget(self.refresh_viewers_button)
        self.update_frequency = QComboBox()
        self.update_frequency.addItems(["10 sec","30 sec","60 sec","2 min","5 min"])
        self.update_frequency.setCurrentIndex(1)
        self.update_frequency.currentIndexChanged.connect(self.save_update_frequency)
        refresh_layout.addWidget(self.update_frequency)
        self.last_update_label = QLabel("Last: Never")
        refresh_layout.addWidget(self.last_update_label)
        viewer_layout.addLayout(refresh_layout)
        viewer_group.setLayout(viewer_layout)
        splitter.addWidget(viewer_group)

        splitter.setSizes([700,300])
        layout.addWidget(splitter, 1)

        # Status bar
        status_layout = QHBoxLayout()
        self.connection_status = QLabel("Not connected")
        status_layout.addWidget(self.connection_status)
        status_layout.addStretch()
        self.stream_status = QLabel("Stream: Unknown")
        status_layout.addWidget(self.stream_status)
        status_layout.addStretch()
        self.active_viewers_count = QLabel("Active: 0")
        status_layout.addWidget(self.active_viewers_count)
        self.all_viewers_count = QLabel("All: 0")
        status_layout.addWidget(self.all_viewers_count)
        layout.addLayout(status_layout)

    def load_settings(self):
        cfg = self.config_manager.get_twitch_config()
        self.channel_input.setText(cfg.get('channel',''))
        if cfg.get('access_token'):
            self.auth_status.setText("Authenticated")
            self.auth_status.setStyleSheet("color: green;")
        else:
            self.auth_status.setText("Not authenticated")
            self.auth_status.setStyleSheet("color: red;")

    def save_settings(self):
        try:
            channel = self.channel_input.text().strip()
            self.config_manager.set_twitch_channel(channel)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def show_auth_dialog(self):
        dlg = TwitchAuthDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self.load_settings()

    def connect_bot(self):
        channel = self.channel_input.text().strip()
        if not channel:
            QMessageBox.warning(self, "Error","Please enter a channel.")
            return False
        cfg = self.config_manager.get_twitch_config()
        if not cfg.get('access_token'):
            QMessageBox.warning(self, "Auth Required","Authenticate first.")
            self.show_auth_dialog()
            return False

        # Store parameters for bot initialization in the run_bot thread
        self.bot_params = {
            'channel': channel,
            'message_callback': self.signal_handler.chat_signal.emit,
            'currency_manager': self.parent.currency_manager,
            'commands_data': self.commands_data.copy() if self.commands_data else [],
            'signal_handler': self.signal_handler
        }
        self.bot = None  # Will be created in the run_bot thread

        self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
        self.bot_thread.start()

        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.send_button.setEnabled(True)
        self.connection_status.setText(f"Connected to: {channel}")
        self.connection_status.setStyleSheet("color: green;")
        self.start_viewer_updates()
        self.refresh_viewers()
        self.signal_handler.chat_signal.emit(f"Connected to {channel}")
        return True

    def run_bot(self):
        # Создаём event loop только один раз для этого потока
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Initialize the bot in the same thread as the event loop
            channel = self.bot_params['channel']
            self.bot = TwitchBot(
                channel=channel,
                message_callback=self.bot_params['message_callback'],
                currency_manager=self.bot_params['currency_manager']
            )
            if self.bot_params['commands_data']:
                self.bot.update_commands(self.bot_params['commands_data'])
            self.bot.signal_handler = self.bot_params['signal_handler']
            
            # Регистрируем обработчик события, который будет вызываться при обновлении event loop
            def update_loop_reference(new_loop):
                print("Event loop reference updated in twitch_tab")
                loop = new_loop
                
            # Сохраняем оригинальный метод _create_new_loop_and_reconnect
            original_create_new_loop = self.bot._create_new_loop_and_reconnect
            
            # Заменяем его на нашу версию с обновлением ссылки
            async def enhanced_create_new_loop(*args, **kwargs):
                result = await original_create_new_loop(*args, **kwargs)
                # Получаем текущий event loop после переподключения
                current_loop = asyncio.get_event_loop()
                # Обновляем ссылку в twitch_tab
                update_loop_reference(current_loop)
                return result
                
            # Заменяем метод на улучшенную версию
            self.bot._create_new_loop_and_reconnect = enhanced_create_new_loop
            
            # Now run the bot (it will use the current thread's event loop)
            loop.run_until_complete(self.bot.start())
        except Exception as e:
            print(f"Bot run error: {e}")
            self.signal_handler.chat_signal.emit(f"Connection error: {e}")
            
            # В случае ошибки пытаемся остановить бота корректно
            if hasattr(self, 'bot') and self.bot:
                try:
                    loop.run_until_complete(self.bot.close())
                except Exception as close_error:
                    print(f"Error closing bot after run error: {close_error}")
        finally:
            # Даже после закрытия event loop сохраняем ссылку на бота
            # чтобы была возможность повторного подключения
            if not self.bot.is_running and hasattr(self, 'connect_button'):
                # Выполняем в главном потоке
                self.signal_handler.chat_signal.emit("Bot disconnected, reconnect manually")
            
            # Закрываем loop только если он не закрыт и программа завершается
            if not loop.is_closed():
                loop.close()

    def disconnect(self):
        self.stop_viewer_updates()
        if self.bot:
            try:
                self.bot.stop()
            except Exception as e:
                print(f"Error stopping bot: {e}")
                self.signal_handler.chat_signal.emit(f"Error disconnecting: {e}")
            self.bot = None
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.send_button.setEnabled(False)
        self.connection_status.setText("Disconnected")
        self.connection_status.setStyleSheet("color: red;")
        self.all_viewers_list.clear()
        self.active_viewers_list.clear()
        self.active_viewers_count.setText("Active: 0")
        self.all_viewers_count.setText("All: 0")
        self.signal_handler.chat_signal.emit("Disconnected from Twitch chat")

    def add_to_chat_safe(self, message):
        self.chat_display.append(message)
        self.chat_display.moveCursor(QTextCursor.End)
        self.chat_display.ensureCursorVisible()

    def send_to_twitch_chat(self, message):
        self.signal_handler.chat_signal.emit(message)
        if self.bot and self.bot.connected_channels:
            chan = self.bot.connected_channels[0]
            asyncio.run_coroutine_threadsafe(chan.send(message), self.bot.loop)

    def send_message(self):
        text = self.message_input.text().strip()
        if not text or not self.bot or not self.bot.connected_channels:
            return
        
        # Проверяем, что event loop еще жив
        if not hasattr(self.bot, 'loop') or not self.bot.loop or self.bot.loop.is_closed():
            self.signal_handler.chat_signal.emit("Cannot send message: connection is being established or lost")
            return
        
        chan = self.bot.connected_channels[0]
        try:
            asyncio.run_coroutine_threadsafe(chan.send(text), self.bot.loop)
            self.message_input.clear()
            self.signal_handler.chat_signal.emit(f"{self.bot.nick}: {text}")
        except RuntimeError as e:
            error_msg = f"Error sending message: {str(e)}"
            self.signal_handler.chat_signal.emit(error_msg)
            print(error_msg)
            
            # Если loop закрыт во время отправки, отключаем кнопки отправки
            if "loop is closed" in str(e).lower():
                self.send_button.setEnabled(False)
                self.connection_status.setText("Disconnected (reconnecting...)")
                self.connection_status.setStyleSheet("color: orange;")

    def open_token_generator(self):
        webbrowser.open("https://twitchtokengenerator.com/quick/FWj06omw7e")

    def update_connection_status(self):
        connected = bool(self.bot and getattr(self.bot, 'is_running', False))
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.send_button.setEnabled(connected)
        color = "green" if connected else "red"
        status = f"Connected to: {self.bot.channel}" if connected else "Not connected"
        self.connection_status.setText(status)
        self.connection_status.setStyleSheet(f"color: {color};")

    def check_connection(self):
        if not self.bot:
            self.signal_handler.chat_signal.emit("Not connected")
            return
        
        # Проверяем, что event loop еще жив
        if not hasattr(self.bot, 'loop') or not self.bot.loop or self.bot.loop.is_closed():
            self.signal_handler.chat_signal.emit("Cannot check connection: event loop is closed or disconnected")
            self.connection_status.setText("Disconnected (reconnecting...)")
            self.connection_status.setStyleSheet("color: orange;")
            return
        
        try:
            asyncio.run_coroutine_threadsafe(self._check_stream_status(), self.bot.loop)
        except RuntimeError as e:
            error_msg = f"Error checking connection: {str(e)}"
            self.signal_handler.chat_signal.emit(error_msg)
            print(error_msg)
            # Если loop закрыт, обновим индикатор состояния
            if "closed" in str(e).lower():
                self.connection_status.setText("Connection lost (reconnecting...)")
                self.connection_status.setStyleSheet("color: orange;")

    async def _check_stream_status(self):
        if hasattr(self.bot, 'check_if_live'):
            is_live = await self.bot.check_if_live()
            self.signal_handler.stream_status_signal.emit(is_live)
            self.bot.is_live = is_live
            self.signal_handler.chat_signal.emit(
                f"Stream status: {'LIVE' if is_live else 'OFFLINE'}"
            )

    async def get_all_viewers(self):
        if not self.bot or not hasattr(self.bot, 'get_all_viewers'):
            return []
        return await self.bot.get_all_viewers()

    def start_viewer_updates(self):
        self.viewer_update_frequency = getattr(self, 'viewer_update_frequency', 30)
        self.viewer_update_timer = QTimer(self)
        self.viewer_update_timer.timeout.connect(self.update_viewers_and_status)
        self.viewer_update_timer.start(self.viewer_update_frequency * 1000)
        QTimer.singleShot(100, self.update_viewers_and_status)

    def stop_viewer_updates(self):
        if hasattr(self, 'viewer_update_timer'):
            self.viewer_update_timer.stop()

    def update_viewers_and_status(self):
        now = time.time()
        if not hasattr(self, 'last_viewers_update') or now - self.last_viewers_update > self.viewer_update_frequency:
            self.refresh_viewers()
            self.last_viewers_update = now

        # Проверяем статус стрима при каждом обновлении зрителей
        if self.bot and hasattr(self.bot, 'is_live'):
            # Проверяем состояние event loop
            if not hasattr(self.bot, 'loop') or not self.bot.loop or self.bot.loop.is_closed():
                return
                
            try:
                # Проверяем статус стрима
                future = asyncio.run_coroutine_threadsafe(
                    self.bot.check_if_live(), self.bot.loop
                )
                is_live = future.result(timeout=5)
                # Эмитим сигнал независимо от изменения
                self.bot.is_live = is_live
                self.signal_handler.stream_status_signal.emit(is_live)
                
                # Периодически (каждые 10 минут) обновляем список модераторов
                if hasattr(self, 'last_mod_check'):
                    if now - self.last_mod_check > 600:  # 600 секунд = 10 минут
                        # Обновляем список модераторов
                        print("Updating moderators list...")
                        asyncio.run_coroutine_threadsafe(
                            self.bot.get_channel_moderators(), self.bot.loop
                        )
                        self.last_mod_check = now
                else:
                    # Первая проверка
                    self.last_mod_check = now
                    
            except (RuntimeError, concurrent.futures.TimeoutError) as e:
                error_msg = f"Error checking stream status: {str(e)}"
                print(error_msg)
                # Если loop закрыт, обновим индикатор состояния
                if isinstance(e, RuntimeError) and "closed" in str(e).lower():
                    self.connection_status.setText("Connection lost (reconnecting...)")
                    self.connection_status.setStyleSheet("color: orange;")
                    
        self.last_update_label.setText(f"Last: {time.strftime('%H:%M:%S')}")

    def refresh_viewers(self):
        if not self.bot:
            return
            
        # Проверяем, что event loop еще жив
        if not hasattr(self.bot, 'loop') or not self.bot.loop or self.bot.loop.is_closed():
            self.signal_handler.chat_signal.emit("Cannot refresh viewers: connection is being established or lost")
            return
            
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.bot.get_all_viewers(), self.bot.loop
            )
            viewers = future.result(timeout=10)
        except (RuntimeError, concurrent.futures.TimeoutError) as e:
            error_msg = f"Error refreshing viewers: {str(e)}"
            self.signal_handler.chat_signal.emit(error_msg)
            print(error_msg)
            viewers = list(getattr(self.bot, 'active_users', []))

        self.all_viewers_list.clear()
        for v in sorted(viewers):
            self.all_viewers_list.addItem(v)
        self.all_viewers_count.setText(f"All: {len(viewers)}")

        self.parent.currency_manager.process_currency_update(
            is_live=self.currently_live,
            active_viewers=self.active_users,
            all_viewers=viewers
        )

    @pyqtSlot(list)
    def update_active_viewers(self, viewers):
        self.active_viewers_list.blockSignals(True)
        self.active_viewers_list.clear()
        for v in sorted(viewers):
            self.active_viewers_list.addItem(v)
        self.active_viewers_list.blockSignals(False)
        self.active_viewers_count.setText(f"Active: {self.active_viewers_list.count()}")

    @pyqtSlot(list)
    def update_all_viewers(self, viewers):
        self.all_viewers_list.blockSignals(True)
        self.all_viewers_list.clear()
        for v in sorted(viewers):
            self.all_viewers_list.addItem(v)
        self.all_viewers_list.blockSignals(False)
        self.all_viewers_count.setText(f"All: {self.all_viewers_list.count()}")

    @pyqtSlot(bool)
    def update_stream_status(self, is_live):
        self.currently_live = is_live
        text = "LIVE" if is_live else "OFFLINE"
        color = "green" if is_live else "gray"
        self.stream_status.setText(f"Stream: {text}")
        self.stream_status.setStyleSheet(f"color: {color};")

    @pyqtSlot(list)
    def update_moderators_list(self, moderators):
        self.moderators_list_widget.blockSignals(True)
        self.moderators_list_widget.clear()
        for mod in sorted(moderators):
            self.moderators_list_widget.addItem(mod)
        self.moderators_list_widget.blockSignals(False)

    def save_update_frequency(self):
        idx = self.update_frequency.currentIndex()
        freqs = [10,30,60,120,300]
        self.viewer_update_frequency = freqs[idx]
        self.last_update_label.setText(f"Update every: {self.viewer_update_frequency}s")
        if hasattr(self, 'viewer_update_timer'):
            self.stop_viewer_updates()
            self.start_viewer_updates()

    def update_currency(self):
        if self.parent and hasattr(self.parent, 'user_currency_tab'):
            self.parent.user_currency_tab.populate_table()