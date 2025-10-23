import json
import os
import configparser
import logging
from datetime import datetime
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                           QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                           QLabel, QLineEdit, QSpinBox, QComboBox, QCheckBox,
                           QFileDialog, QMessageBox, QSlider, QGroupBox, QTabWidget,
                           QDialog, QHeaderView, QMenu, QScrollArea)
from PyQt5.QtCore import Qt, QTimer, QDateTime
import PyQt5.QtCore as QtCore
from PyQt5.QtGui import QPixmap, QFont, QTextCursor  # Add QTextCursor here
import pygame
from twitch_bot import TwitchBot
from twitch_auth import TwitchAuthDialog
from twitch_tab import TwitchTab
from config_manager import ConfigManager
from about_tab import AboutTab
from history_manager import HistoryManager
from pathlib import Path
import threading
import time
from currency_tab import CurrencyTab
from user_currency_tab import UserCurrencyTab
from ranks_tab import RanksTab
from currency_manager import CurrencyManager
from PyQt5 import sip  # правильный импорт
from PyQt5.QtCore import QMetaType
import webbrowser

# Вместо sip.registerMetaType используем:
QMetaType.type("QTextCursor")

class UpdateNotificationWidget(QLabel):
    """A notification widget that appears in the top-right corner when an update is available"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.download_url = ""
        self.new_version = ""
          # Setup the widget
        self.setup_ui()
        self.hide()  # Initially hidden
        
    def setup_ui(self):
        """Setup the notification UI"""
        self.setFixedSize(180, 35)  # Сделаем меньше: 180x35 вместо 220x50
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        
        # Style the notification
        self.setStyleSheet("""
            QLabel {
                background-color: #4CAF50;
                color: white;
                border: 2px solid #45a049;
                border-radius: 6px;
                font-weight: bold;
                font-size: 10px;
                padding: 4px;
            }
            QLabel:hover {
                background-color: #45a049;
                border-color: #3d8b40;
            }
        """)
          # Set initial text
        self.setText("🔄 Update available")  # Более короткий начальный текст
          # Enable word wrap
        self.setWordWrap(True)
        
    def show_notification(self, new_version, download_url):
        """Show the notification with version info"""
        self.new_version = new_version
        self.download_url = download_url
        self.setText(f"🔄 v{new_version} available")  # Более короткий текст
        
        # Position in top-right corner
        self.update_position()
        
        # Show the notification
        self.show()
        self.raise_()
        
        # Auto-hide after 8 seconds (уменьшим время)
        QTimer.singleShot(8000, self.hide)
        
    def update_position(self):
        """Update position to stay in top-right corner"""
        if self.parent_widget:
            parent_rect = self.parent_widget.rect()
            x = parent_rect.width() - self.width() - 10
            y = 10
            self.move(x, y)
            
    def mousePressEvent(self, event):
        """Handle click events"""
        if event.button() == Qt.LeftButton:
            if self.download_url:
                webbrowser.open(self.download_url)
            self.hide()
        super().mousePressEvent(event)
        
    def resizeEvent(self, event):
        """Handle parent widget resize"""
        super().resizeEvent(event)
        if self.isVisible():
            self.update_position()
            
    def enterEvent(self, event):
        """Handle mouse enter - show tooltip"""
        self.setToolTip(f"New version {self.new_version} is available!\nClick to open download page")
        super().enterEvent(event)

class CommandEditor(QMainWindow):
    def __init__(self):
        # ⚠️ ПЕРЕД pygame.init() делаем pre_init с небольшим буфером
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=256)
        pygame.init()
        pygame.mixer.init()

        super().__init__()
        self.setWindowTitle("Command Editor")
        self.setGeometry(100, 100, 1200, 800)
        
        # Initialize config manager
        self.config_manager = ConfigManager()
        
        # Load settings BEFORE creating widgets
        self.allow_sound_interruption = self.config_manager.get_sound_interruption()
        self.show_interruption_message = self.config_manager.get_interruption_message()
        
        # Initialize commands list
        self.commands = []

        # Add an attribute to track original command order
        self.original_commands = []

        # Initialize volume from config BEFORE creating widgets
        self.volume = self.config_manager.get_volume()

        # Initialize system backup settings
        system_auto_backup = self.config_manager.get_system_auto_backup()
        self.system_auto_backup_enabled = system_auto_backup['enabled']
        self.system_backup_interval = system_auto_backup['interval']

        # Initialize currency auto-save settings
        self.currency_auto_save_enabled = True  # Default to enabled
        self.currency_backup_interval = 300  # Default 5 minutes
        
        # Create tab widget as the main container
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)
        
        # Create main tab for commands
        main_tab = QWidget()
        main_layout = QVBoxLayout()
        
        # Search functionality
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to search commands...")
        self.search_input.textChanged.connect(self.filter_commands)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        main_layout.addLayout(search_layout)
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(14)
        self.table.setHorizontalHeaderLabels([
            "Command", "Permission", "Info", "Group", "Response",
            "Cooldown", "UserCooldown", "Cost", "Count", "Usage",
            "Enabled", "SoundFile", "FKSoundFile", "Volume"
        ])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.itemChanged.connect(self.table_item_changed)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.itemSelectionChanged.connect(self.on_command_selected)
        
        # Disable sorting
        self.table.setSortingEnabled(False)
        
        main_layout.addWidget(self.table)
        
        # Create buttons layout
        buttons_layout = QHBoxLayout()
        
        # Add buttons
        self.add_btn = QPushButton("Add Command")
        self.add_btn.clicked.connect(self.add_command)
        buttons_layout.addWidget(self.add_btn)
        
        self.remove_btn = QPushButton("Remove Command")
        self.remove_btn.clicked.connect(self.delete_command)
        buttons_layout.addWidget(self.remove_btn)
        
        self.load_btn = QPushButton("Load File")
        self.load_btn.clicked.connect(self.load_file)
        buttons_layout.addWidget(self.load_btn)
        
        self.save_btn = QPushButton("Save File")
        self.save_btn.clicked.connect(self.save_file)
        buttons_layout.addWidget(self.save_btn)
        
        self.save_legacy_btn = QPushButton("Save Legacy Format")
        self.save_legacy_btn.clicked.connect(self.save_legacy_format)
        buttons_layout.addWidget(self.save_legacy_btn)
        
        # Add Auto-Assign button
        self.auto_assign_btn = QPushButton("Auto-Assign Sounds")
        self.auto_assign_btn.clicked.connect(self.auto_assign_sounds)
        buttons_layout.addWidget(self.auto_assign_btn)
        
        main_layout.addLayout(buttons_layout)
        
        # Create command details group
        details_group = QGroupBox("Command Details")
        details_layout = QHBoxLayout()
        
        # Left column - Basic settings
        left_column = QVBoxLayout()
        self.command_edit = QLineEdit()
        self.permission_combo = QComboBox()
        self.permission_combo.addItems(["Everyone", "Moderator", "Admin"])
        self.info_edit = QLineEdit()
        self.group_edit = QLineEdit()
        self.response_edit = QLineEdit()
        
        left_column.addWidget(QLabel("Command:"))
        left_column.addWidget(self.command_edit)
        left_column.addWidget(QLabel("Permission:"))
        left_column.addWidget(self.permission_combo)
        left_column.addWidget(QLabel("Info:"))
        left_column.addWidget(self.info_edit)
        left_column.addWidget(QLabel("Group:"))
        left_column.addWidget(self.group_edit)
        left_column.addWidget(QLabel("Response:"))
        left_column.addWidget(self.response_edit)
        
        # Middle column - Cooldown and cost settings
        middle_column = QVBoxLayout()
        self.cooldown_spin = QSpinBox()
        self.user_cooldown_spin = QSpinBox()
        self.cost_spin = QSpinBox()
        self.count_spin = QSpinBox()
        self.usage_combo = QComboBox()
        self.usage_combo.addItems(["SC", "Chat", "Both"])
        self.enabled_check = QCheckBox("Enabled")
        
        middle_column.addWidget(QLabel("Cooldown:"))
        middle_column.addWidget(self.cooldown_spin)
        middle_column.addWidget(QLabel("User Cooldown:"))
        middle_column.addWidget(self.user_cooldown_spin)
        middle_column.addWidget(QLabel("Cost:"))
        middle_column.addWidget(self.cost_spin)
        middle_column.addWidget(QLabel("Count:"))
        middle_column.addWidget(self.count_spin)
        middle_column.addWidget(QLabel("Usage:"))
        middle_column.addWidget(self.usage_combo)
        middle_column.addWidget(self.enabled_check)
        
        # Right column - Sound files and volume
        right_column = QVBoxLayout()
        self.sound_file_edit = QLineEdit()
        self.sound_file_btn = QPushButton("Browse")
        self.fk_sound_file_edit = QLineEdit()
        self.fk_sound_file_btn = QPushButton("Browse")
        
        self.sound_file_btn.clicked.connect(lambda: self.browse_file(self.sound_file_edit))
        self.fk_sound_file_btn.clicked.connect(lambda: self.browse_file(self.fk_sound_file_edit))
        
        right_column.addWidget(QLabel("Sound File:"))
        sound_file_layout = QHBoxLayout()
        sound_file_layout.addWidget(self.sound_file_edit)
        sound_file_layout.addWidget(self.sound_file_btn)
        right_column.addLayout(sound_file_layout)
        
        # Add Play/Stop button for sound
        self.play_sound_btn = QPushButton("Play Sound")
        self.play_sound_btn.clicked.connect(self.play_or_stop_sound)
        sound_file_layout.addWidget(self.play_sound_btn)
        
        right_column.addWidget(QLabel("FK Sound File:"))
        right_column.addWidget(self.fk_sound_file_edit)
        right_column.addWidget(self.fk_sound_file_btn)
        
        # Add volume control layout with value display
        volume_layout = QHBoxLayout()
        volume_label = QLabel("Volume:")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.valueChanged.connect(self.update_volume)

        # Add label to display the current volume value
        self.volume_value_label = QLabel("50%")  # Default value
        self.volume_value_label.setMinimumWidth(40)  # Set minimum width to prevent layout shifts

        volume_layout.addWidget(volume_label)
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_value_label)
        right_column.addLayout(volume_layout)

        # Set initial volume value
        self.volume_slider.setValue(int(self.volume * 100))
        self.volume_value_label.setText(f"{int(self.volume * 100)}%")
        
        # Add sound interruption toggle
        self.allow_interruption_check = QCheckBox("Allow sounds to interrupt each other")
        self.allow_interruption_check.setToolTip("When enabled, new commands will interrupt currently playing sounds")
        self.allow_interruption_check.stateChanged.connect(self.on_interruption_toggle)
        right_column.addWidget(self.allow_interruption_check)

        # Add show message toggle
        self.show_interruption_message_check = QCheckBox("Show message when sound is blocked")
        self.show_interruption_message_check.setToolTip("When enabled, a message will be sent in chat when a command's sound is blocked")
        self.show_interruption_message_check.stateChanged.connect(self.on_show_message_toggle)
        right_column.addWidget(self.show_interruption_message_check)
        
        # Add auto-save controls
        auto_save_group = QGroupBox("Auto-Save")
        auto_save_layout = QVBoxLayout()

        # Command auto-save
        command_save_layout = QHBoxLayout()
        self.auto_save_checkbox = QCheckBox("Enable Auto-Save")
        self.auto_save_checkbox.stateChanged.connect(self.on_auto_save_toggle)
        self.auto_save_interval_input = QSpinBox()
        self.auto_save_interval_input.setMinimum(60)
        self.auto_save_interval_input.setMaximum(3600)
        self.auto_save_interval_input.setSingleStep(60)
        self.auto_save_interval_input.setSuffix(" seconds")
        self.auto_save_interval_input.valueChanged.connect(self.on_auto_save_interval_changed)

        command_save_layout.addWidget(self.auto_save_checkbox)
        command_save_layout.addWidget(QLabel("Interval:"))
        command_save_layout.addWidget(self.auto_save_interval_input)
        command_save_layout.addStretch()

        auto_save_layout.addLayout(command_save_layout)

        # Full system backup
        system_backup_layout = QHBoxLayout()
        self.system_auto_backup_checkbox = QCheckBox("Enable Automatic Full System Backups")
        self.system_auto_backup_checkbox.setToolTip("Automatically create comprehensive system backups (commands + currency + settings)")
        self.system_auto_backup_checkbox.setChecked(self.system_auto_backup_enabled)
        self.system_auto_backup_checkbox.stateChanged.connect(self.on_system_auto_backup_toggle)
        self.system_backup_interval_input = QSpinBox()
        self.system_backup_interval_input.setMinimum(300)  # 5 minutes minimum
        self.system_backup_interval_input.setMaximum(86400)  # 24 hours maximum
        self.system_backup_interval_input.setSingleStep(300)  # 5 minute steps
        self.system_backup_interval_input.setValue(self.system_backup_interval)
        self.system_backup_interval_input.setSuffix(" seconds")
        self.system_backup_interval_input.valueChanged.connect(self.on_system_backup_interval_changed)

        system_backup_layout.addWidget(self.system_auto_backup_checkbox)
        system_backup_layout.addWidget(QLabel("Interval:"))
        system_backup_layout.addWidget(self.system_backup_interval_input)
        system_backup_layout.addStretch()

        auto_save_layout.addLayout(system_backup_layout)

        # Currency auto-save
        currency_save_layout = QHBoxLayout()
        self.currency_auto_save_checkbox = QCheckBox("Auto-Save Currency Users")
        self.currency_auto_save_checkbox.setToolTip("Automatically save currency user data (points, hours, ranks)")
        self.currency_auto_save_checkbox.setChecked(self.currency_auto_save_enabled)
        self.currency_auto_save_checkbox.stateChanged.connect(self.on_currency_auto_save_toggle)
        self.currency_backup_interval_input = QSpinBox()
        self.currency_backup_interval_input.setMinimum(60)  # 1 minute minimum
        self.currency_backup_interval_input.setMaximum(3600)  # 1 hour maximum
        self.currency_backup_interval_input.setSingleStep(60)  # 1 minute steps
        self.currency_backup_interval_input.setValue(self.currency_backup_interval)
        self.currency_backup_interval_input.setSuffix(" seconds")
        self.currency_backup_interval_input.valueChanged.connect(self.on_currency_backup_interval_changed)

        currency_save_layout.addWidget(self.currency_auto_save_checkbox)
        currency_save_layout.addWidget(QLabel("Interval:"))
        currency_save_layout.addWidget(self.currency_backup_interval_input)
        currency_save_layout.addStretch()

        auto_save_layout.addLayout(currency_save_layout)

        auto_save_group.setLayout(auto_save_layout)
        right_column.addWidget(auto_save_group)
        
        # Add columns to details layout
        details_layout.addLayout(left_column)
        details_layout.addLayout(middle_column)
        details_layout.addLayout(right_column)
        details_group.setLayout(details_layout)
        main_layout.addWidget(details_group)
        
        # Set main tab layout
        main_tab.setLayout(main_layout)
        
        # Initialize history manager BEFORE creating history tab
        self.history_manager = HistoryManager(max_backups=self.config_manager.get_max_backups())
        
        # Add tabs to tab widget
        self.tab_widget.addTab(main_tab, "Commands")
        self.twitch_tab = TwitchTab(parent=self, commands_data=self.commands)
        self.tab_widget.addTab(self.twitch_tab, "Twitch")


        # Add tabs for currency management
        self.currency_manager = CurrencyManager()
        if hasattr(self.currency_manager, 'load_settings'):
            self.currency_manager.load_settings()  # Загружаем настройки при запуске
            print("Currency settings loaded in CommandEditor")

        self.currency_tab = CurrencyTab(parent=self)
        self.tab_widget.addTab(self.currency_tab, "Currency Settings")
        self.user_currency_tab = UserCurrencyTab(parent=self)
        self.tab_widget.addTab(self.user_currency_tab, "Currency Users")
        self.ranks_tab = RanksTab(parent=self)
        self.tab_widget.addTab(self.ranks_tab, "Ranks")
        self.ranks_tab.load_ranks()

        self.about_tab = AboutTab(parent=self)
        self.tab_widget.addTab(self.about_tab, "About")
        self.history_tab = self.create_history_tab()
        self.tab_widget.addTab(self.history_tab, "History")

        # Create comprehensive backup tab
        self.backup_tab = self.create_comprehensive_backup_tab()
        self.tab_widget.addTab(self.backup_tab, "Backups")
        
        # Load saved commands and configuration
        self.load_saved_data()
        
        # Set sound interruption setting from config
        self.allow_interruption_check.setChecked(self.allow_sound_interruption)

        # Set show interruption message setting from config
        self.show_interruption_message_check.setChecked(self.show_interruption_message)
        
        # Set up auto-save timer
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self.auto_save)
        auto_save_config = self.config_manager.get_auto_save()
        if auto_save_config['enabled']:
            self.auto_save_timer.start(auto_save_config['interval'] * 1000)

        # Set up system auto-backup timer
        self.system_auto_backup_timer = QTimer()
        self.system_auto_backup_timer.timeout.connect(self.create_comprehensive_backup_auto)

        # Set up currency auto-save timer
        self.currency_auto_backup_timer = QTimer()
        self.currency_auto_backup_timer.timeout.connect(self.currency_auto_save_auto)

        self.current_file = None
        self.config = configparser.ConfigParser()
        
        # Set volume from config
        self.volume = self.config_manager.get_volume()
        self.volume_slider.setValue(int(self.volume * 100))
        
        # Set auto-save settings from config
        auto_save = self.config_manager.get_auto_save()
        self.auto_save_enabled = auto_save['enabled']
        self.auto_save_interval = auto_save['interval']
        self.auto_save_checkbox.setChecked(self.auto_save_enabled)
        self.auto_save_interval_input.setValue(self.auto_save_interval)

        # Set currency auto-save settings from config
        currency_auto_save = self.config_manager.get_currency_auto_save()
        if currency_auto_save and 'enabled' in currency_auto_save and 'interval' in currency_auto_save:
            self.currency_auto_save_enabled = currency_auto_save['enabled']
            self.currency_backup_interval = currency_auto_save['interval']

            # Update UI elements
            self.currency_auto_save_checkbox.setChecked(self.currency_auto_save_enabled)
            self.currency_backup_interval_input.setValue(self.currency_backup_interval)

            # Update timer
            if self.currency_auto_save_enabled:
                self.currency_auto_backup_timer.start(self.currency_backup_interval * 1000)
        
        # Apply global scrollbar settings
        app = QApplication.instance()
        if app:
            app.setStyleSheet("""
            QScrollBar:vertical {
                width: 16px;
                background: rgba(0, 0, 0, 0.1);
            }
            QScrollBar:horizontal {
                height: 16px;
                background: rgba(0, 0, 0, 0.1);
            }
            """)        # Словарь загруженных звуков
        self.loaded_sounds = {}
        # Один канал для всех воспроизведений
        self.sound_channel = pygame.mixer.Channel(0)
        
        # Create update notification widget
        self.update_notification = UpdateNotificationWidget(self)
          # Auto-check for updates on startup (silent check)
        self.auto_check_updates()
            
    def auto_check_updates(self):
        """Automatically check for updates on startup"""
        try:
            if hasattr(self, 'about_tab') and self.about_tab.update_checker:
                # Set the notification widget
                self.about_tab.update_checker.set_notification_widget(self.update_notification)
                # Start silent update check after a short delay
                QTimer.singleShot(3000, lambda: self.about_tab.update_checker.check_for_updates(silent=True))
        except Exception as e:
            print(f"Error during auto update check: {e}")
            
    def show_auth_dialog(self):
        dialog = TwitchAuthDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            QMessageBox.information(self, "Success", "Twitch credentials saved successfully!")
            
    def load_commands(self):
        """Load commands from file"""
        try:
            if os.path.exists('commands.json'):
                with open('commands.json', 'r', encoding='utf-8') as f:
                    self.commands = json.load(f)
                    # Ensure all commands have Enabled field
                    for cmd in self.commands:
                        if "Enabled" not in cmd:
                            cmd["Enabled"] = True
            else:
                self.commands = []
            self.update_table()
        except Exception as e:
            print(f"Error loading commands: {e}")
            self.commands = []
            
    def update_table(self):
        """Update the commands table"""
        self.table.blockSignals(True)  # Блокируем сигналы, чтобы избежать лишних обновлений
        self.table.setRowCount(0)  # Очищаем таблицу

        for cmd in self.commands:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # Устанавливаем элементы для строки
            self.table.setItem(row, 0, QTableWidgetItem(cmd["Command"]))
            self.table.setItem(row, 1, QTableWidgetItem(cmd["Permission"]))
            self.table.setItem(row, 2, QTableWidgetItem(cmd["Info"]))
            self.table.setItem(row, 3, QTableWidgetItem(cmd["Group"]))
            self.table.setItem(row, 4, QTableWidgetItem(cmd["Response"]))
            self.table.setItem(row, 5, QTableWidgetItem(str(cmd["Cooldown"])))
            self.table.setItem(row, 6, QTableWidgetItem(str(cmd["UserCooldown"])))
            self.table.setItem(row, 7, QTableWidgetItem(str(cmd["Cost"])))
            self.table.setItem(row, 8, QTableWidgetItem(str(cmd["Count"])))
            self.table.setItem(row, 9, QTableWidgetItem(cmd["Usage"]))
            self.table.setItem(row, 10, QTableWidgetItem("✓" if cmd["Enabled"] else "✗"))  # Для отображения состояния
            self.table.setItem(row, 11, QTableWidgetItem(cmd["SoundFile"]))
            self.table.setItem(row, 12, QTableWidgetItem(str(cmd.get("FKSoundFile", ""))))
            self.table.setItem(row, 13, QTableWidgetItem(str(cmd["Volume"])))

        self.table.blockSignals(False)  # Разблокируем сигналы
        
    def populate_table(self):
        """Populate the table with commands"""
        self.table.setRowCount(len(self.commands))
        
        for row, cmd in enumerate(self.commands):
            # Command column (0)
            self.table.setItem(row, 0, QTableWidgetItem(cmd["Command"]))
            
            # Permission column (1)
            self.table.setItem(row, 1, QTableWidgetItem(cmd["Permission"]))
            
            # Info column (2)
            self.table.setItem(row, 2, QTableWidgetItem(cmd.get("Info", "")))
            
            # Group column (3)
            self.table.setItem(row, 3, QTableWidgetItem(cmd.get("Group", "GENERAL")))
            
            # Response column (4)
            self.table.setItem(row, 4, QTableWidgetItem(cmd["Response"]))
            
            # Cooldown column (5)
            self.table.setItem(row, 5, QTableWidgetItem(str(cmd.get("Cooldown", 0))))
            
            # UserCooldown column (6)
            self.table.setItem(row, 6, QTableWidgetItem(str(cmd.get("UserCooldown", 0))))
            
            # Cost column (7)
            self.table.setItem(row, 7, QTableWidgetItem(str(cmd.get("Cost", 0))))
            
            # Count column (8)
            self.table.setItem(row, 8, QTableWidgetItem(str(cmd.get("Count", 0))))
            
            # Usage column (9)
            self.table.setItem(row, 9, QTableWidgetItem(cmd.get("Usage", "SC")))
            
            # Enabled column (10)
            enabled = "✓" if cmd["Enabled"] else "✗"
            self.table.setItem(row, 10, QTableWidgetItem(enabled))
            
            # SoundFile column (11)
            self.table.setItem(row, 11, QTableWidgetItem(cmd["SoundFile"]))
            
            # FKSoundFile column (12)
            self.table.setItem(row, 12, QTableWidgetItem(str(cmd.get("FKSoundFile", ""))))
            
            # Volume column (13)
            self.table.setItem(row, 13, QTableWidgetItem(str(cmd.get("Volume", 100))))
            
    def refresh_table(self):
        """Refresh the table with current commands"""
        # Remember search filter
        search_text = self.search_input.text()
        
        # Block signals to prevent unintended changes
        self.table.blockSignals(True)
        
        # Clear and repopulate the table
        self.table.setRowCount(0)
        self.populate_table()
        
        # Reapply search filter
        self.filter_commands()
        
        # Unblock signals
        self.table.blockSignals(False)
        
    def update_details(self, current_row, current_col, previous_row, previous_col):
        if current_row >= 0 and current_row < len(self.commands):
            cmd = self.commands[current_row]
            self.command_edit.setText(cmd["Command"])
            self.permission_combo.setCurrentText(cmd["Permission"])
            self.info_edit.setText(cmd["Info"])
            self.group_edit.setText(cmd["Group"])
            self.response_edit.setText(cmd["Response"])
            self.cooldown_spin.setValue(cmd["Cooldown"])
            self.user_cooldown_spin.setValue(cmd["UserCooldown"])
            self.cost_spin.setValue(cmd["Cost"])
            self.count_spin.setValue(cmd["Count"])
            self.usage_combo.setCurrentText(cmd["Usage"])
            self.enabled_check.setChecked(cmd["Enabled"])
            self.sound_file_edit.setText(cmd["SoundFile"])
            self.fk_sound_file_edit.setText(str(cmd["FKSoundFile"]))
            
    def table_item_changed(self, item):
        try:
            row = item.row()
            col = item.column()
            
            if row < len(self.commands):
                cmd = self.commands[row]
                
                if col == 2:  # Info column
                    cmd["Info"] = item.text()
                elif col == 0:  # Command name column
                    cmd["Command"] = item.text()
                elif col == 1:  # Permission column
                    cmd["Permission"] = item.text()
                elif col == 3:  # Group column
                    cmd["Group"] = item.text()
                elif col == 4:  # Response column
                    cmd["Response"] = item.text()
                elif col == 5:  # Cooldown column
                    try:
                        cmd["Cooldown"] = int(item.text() or 0)
                    except ValueError:
                        cmd["Cooldown"] = 0
                elif col == 6:  # UserCooldown column
                    try:
                        cmd["UserCooldown"] = int(item.text() or 0)
                    except ValueError:
                        cmd["UserCooldown"] = 0
                elif col == 7:  # Cost column
                    try:
                        cmd["Cost"] = int(item.text() or 0)
                    except ValueError:
                        cmd["Cost"] = 0
                elif col == 8:  # Count column
                    try:
                        cmd["Count"] = int(item.text() or 0)
                    except ValueError:
                        cmd["Count"] = 0
                elif col == 9:  # Usage column
                    cmd["Usage"] = item.text()
                elif col == 10:  # Enabled column
                    cmd["Enabled"] = item.text() == "✓"
                elif col == 11:  # SoundFile column
                    cmd["SoundFile"] = item.text()
                elif col == 12:  # FKSoundFile column
                    cmd["FKSoundFile"] = item.text()
                elif col == 13:  # Volume column
                    try:
                        cmd["Volume"] = int(item.text() or 100)
                    except ValueError:
                        cmd["Volume"] = 100
                        
                # Save changes
                self.save_commands()
                
        except Exception as e:
            print(f"Error updating command: {e}")
            
    def load_config(self):
        try:
            self.config.read('config.ini')
            self.current_file = self.config.get('Settings', 'last_file', fallback=None)
            volume = self.config.getint('Settings', 'volume', fallback=50)
            self.volume_slider.setValue(volume)
        except:
            pass
            
    def save_config(self):
        if not self.config.has_section('Settings'):
            self.config.add_section('Settings')
        if self.current_file:
            self.config.set('Settings', 'last_file', self.current_file)
        self.config.set('Settings', 'volume', str(self.volume_slider.value()))
        with open('config.ini', 'w') as f:
            self.config.write(f)
            
    def update_volume(self, value):
        """Update volume setting"""
        self.volume = value / 100  # Convert to 0-1 range
        
        # Update the volume display label
        self.volume_value_label.setText(f"{value}%")
        
        # Update the selected command's volume if any
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            if row < len(self.commands):
                self.commands[row]["Volume"] = value
                self.table.item(row, 13).setText(str(value))
                    
    def auto_assign_sounds(self):
        """Auto-assign sound files to commands based on filename matching"""
        # Ask user to select the sounds directory
        sound_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Sounds Directory",
            "",
            QFileDialog.ShowDirsOnly
        )
        
        if not sound_dir:
            return
            
        # Convert to Path object
        sound_dir = Path(sound_dir)
        
        # Get all sound files (wav, mp3)
        sound_files = []
        for ext in ['*.wav', '*.mp3']:
            sound_files.extend(sound_dir.glob(ext))
            
        if not sound_files:
            QMessageBox.warning(self, "Warning", "No sound files found in the selected directory!")
            return
            
        # Create a dictionary of command names to sound files
        sound_dict = {}
        for sound_file in sound_files:
            name_without_ext = sound_file.stem
            sound_dict[name_without_ext] = str(sound_file)
            if name_without_ext.startswith('!'):
                sound_dict[name_without_ext[1:]] = str(sound_file)
        
        # Update commands with matching sound files
        updated = False
        self.table.blockSignals(True)  # Block signals before updating the table
        for i in range(self.table.rowCount()):
            command_item = self.table.item(i, 0)
            if command_item:
                command = command_item.text()
                command_without_bang = command.lstrip('!')
                
                if command in sound_dict:
                    # Update the commands data structure
                    self.commands[i]["SoundFile"] = sound_dict[command]
                    self.commands[i]["Enabled"] = True  # Set Enabled to True
                    
                    # Update table cells with correct column indices
                    # Column 11 is the SoundFile column according to your table header setup
                    self.table.setItem(i, 11, QTableWidgetItem(sound_dict[command]))
                    # Column 10 is the Enabled column (showing "✓" or "✗")
                    self.table.setItem(i, 10, QTableWidgetItem("✓"))
                    updated = True
                elif command_without_bang in sound_dict:
                    # Update the commands data structure
                    self.commands[i]["SoundFile"] = sound_dict[command_without_bang]
                    self.commands[i]["Enabled"] = True  # Set Enabled to True
                    
                    # Update table cells with correct column indices
                    self.table.setItem(i, 11, QTableWidgetItem(sound_dict[command_without_bang]))
                    self.table.setItem(i, 10, QTableWidgetItem("✓"))
                    updated = True

        self.table.blockSignals(False)  # Unblock signals after updating the table

        if updated:
            self.save_commands()  # Save changes
            self.update_table()  # Refresh the table
            QMessageBox.information(self, "Success", "Sound files assigned automatically!")
        else:
            QMessageBox.information(self, "Info", "No new sound files to assign.")

    def play_or_stop_sound(self):
        """Play or stop the sound file of the selected command"""
        # Если кнопка в режиме остановки, значит звук уже играет и его надо остановить
        if self.play_sound_btn.text() == "Stop Sound":
            self.sound_channel.fadeout(100)  # Плавно останавливаем звук
            self.play_sound_btn.setText("Play Sound")
            return
            
        # Иначе - проигрываем звук
        selected = self.table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Warning", "No command selected.")
            return

        fn = self.commands[selected[0].row()]["SoundFile"]
        if not fn or not os.path.exists(fn):
            QMessageBox.warning(self, "Warning", f"Sound file not found: {fn}")
            return

        # Прерываем текущий звук через fadeout если включена опция прерывания
        if self.sound_channel.get_busy():
            if self.allow_sound_interruption:
                self.sound_channel.fadeout(100)  # 100 мс плавного угасания
            else:
                if self.show_interruption_message:
                    QMessageBox.information(self, "Info", "Interruption disabled.")
                return

        # Загружаем Sound один раз
        snd = self.loaded_sounds.get(fn)
        if snd is None:
            snd = pygame.mixer.Sound(fn)
            self.loaded_sounds[fn] = snd

        # Устанавливаем громкость из вашей колонки Volume
        vol = float(self.commands[selected[0].row()].get("Volume", 100)) / 100.0
        snd.set_volume(vol)

        # Воспроизводим на нашем канале
        self.sound_channel.play(snd)
        self.play_sound_btn.setText("Stop Sound")

        # Отслеживаем конец и сбрасываем кнопку
        def watch_end():
            while self.sound_channel.get_busy():
                time.sleep(0.05)
            if self.play_sound_btn.text() == "Stop Sound":
                self.play_sound_btn.setText("Play Sound")

        threading.Thread(target=watch_end, daemon=True).start()

    def closeEvent(self, event):
        try:
            # First, stop any playing sounds
            if pygame.mixer.get_busy():
                pygame.mixer.stop()
            
            # Disconnect any running Twitch bot
            if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
                print("Stopping Twitch bot before closing…")
                self.twitch_tab.bot.stop()   # ← вызываем .stop(), а не .disconnect()
                time.sleep(0.2)

            # Deduplicate commands before saving
            if self.commands and self.original_commands:
                print("Deduplicating and reordering commands before saving...")
                
                # Create a mapping of commands by their command names
                command_map = {}
                for cmd in self.commands:
                    # Use command name as the key
                    key = cmd["Command"]
                    command_map[key] = cmd
                
                # Track fed commands to prevent duplicates
                processed_commands = set()
                ordered_commands = []
                
                # First pass: add commands that match by name from original order
                for orig_cmd in self.original_commands:
                    key = orig_cmd["Command"]
                    if key in command_map:
                        # Use current data for this command
                        ordered_commands.append(command_map[key])
                        processed_commands.add(key)
                    else:
                        # If command name changed, try to find by other properties
                        found = False
                        for cmd_name, current_cmd in command_map.items():
                            if cmd_name not in processed_commands and (
                                current_cmd.get("SoundFile") == orig_cmd.get("SoundFile") and
                                current_cmd.get("Response") == orig_cmd.get("Response")
                            ):
                                ordered_commands.append(current_cmd)
                                processed_commands.add(cmd_name)
                                found = True
                                break
                
                # Add any commands that weren't in the original list but exist now
                for cmd_name, cmd in command_map.items():
                    if cmd_name not in processed_commands:
                        ordered_commands.append(cmd)
                
                # Update commands to ordered list before saving
                self.commands = ordered_commands

            # Save current commands before closing
            if self.commands:
                print("Saving commands before closing...")
                self.config_manager.save_commands(self.commands)
                
                # Always create a backup when closing
                print("Creating backup before closing...")
                self.history_manager.save_backup(self.commands)
            
            # Save volume setting
            self.config_manager.set_volume(self.volume)
            
            # Save interruption settings
            self.config_manager.set_sound_interruption(self.allow_sound_interruption)
            self.config_manager.set_interruption_message(self.show_interruption_message)
            
            # Save auto-save settings
            self.config_manager.set_auto_save(
                self.auto_save_enabled,
                self.auto_save_interval
            )
            
            # Save backup settings
            if hasattr(self, 'history_manager'):
                self.config_manager.set_max_backups(self.history_manager.max_backups)
            
            # Save currency settings
            if hasattr(self, 'currency_tab'):
                self.currency_tab.save_settings()

            # Save ranks settings
            if hasattr(self, 'ranks_tab'):
                self.ranks_tab.save_ranks()

            # Save currency auto-save settings
            try:
                self.config_manager.set_currency_auto_save(
                    self.currency_auto_save_enabled,
                    self.currency_backup_interval
                )
            except Exception as e:
                print(f"Error saving currency auto-save settings: {e}")
            
            print("Application shutdown complete.")
            event.accept()
        except Exception as e:
            print(f"Error during shutdown: {e}")
            # Let the application close even if there was an error
            event.accept()

    def load_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open File", "", "ABCOMG Files (*.abcomg)")
        if file_name:
            try:
                with open(file_name, "r", encoding="utf-8") as f:
                    loaded_commands = json.load(f)
                    
                    # Convert old format to new format
                    self.commands = []
                    for cmd in loaded_commands:
                        new_cmd = {
                            "Command": cmd["Command"],
                            "SoundFile": cmd.get("SoundFile", ""),
                            "Enabled": True,  # Set all commands as enabled by default
                            "Permission": cmd.get("Permission", "Everyone"),
                            "Response": cmd.get("Response", ""),
                            "Info": cmd.get("Info", ""),
                            "Group": cmd.get("Group", "GENERAL"),
                            "Cooldown": cmd.get("Cooldown", 0),
                            "UserCooldown": cmd.get("UserCooldown", 0),
                            "Cost": cmd.get("Cost", 0),
                            "Count": cmd.get("Count", 0),
                            "Usage": cmd.get("Usage", "SC"),
                            "FKSoundFile": cmd.get("FKSoundFile", ""),
                            "Volume": cmd.get("Volume", 100)  # Default volume is 100
                        }
                        self.commands.append(new_cmd)
                    
                    # Save converted commands
                    self.save_commands()
                    
                    # Update UI
                    self.update_table()
                    
                    # Update commands in Twitch tab if it exists
                    if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
                        self.twitch_tab.bot.update_commands(self.commands)
                        
                    QMessageBox.information(self, "Success", "Commands loaded and converted successfully!")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to load file: {str(e)}")
        
    def save_file(self):
        if not self.commands:
            QMessageBox.warning(self, "Error", "No commands to save!")
            return
            
        # Save to the commands file
        if self.config_manager.save_commands(self.commands):
            # Always create a backup when manually saving
            if self.history_manager.save_backup(self.commands):
                # Refresh the backup list
                self.refresh_backup_list()
                QMessageBox.information(self, "Success", "Commands saved and backup created successfully!")
            else:
                QMessageBox.information(self, "Success", "Commands saved successfully, but backup creation failed.")
        else:
            QMessageBox.warning(self, "Error", "Failed to save commands!")
                
    def add_command(self):
        """Add a new command"""
        # Create a new command
        new_command = {
            "Command": "!new",
            "Permission": "Everyone",
            "Response": "",
            "SoundFile": "",
            "Enabled": True,
            "Info": "",
            "Group": "GENERAL",
            "Cooldown": 0,
            "UserCooldown": 0,
            "Cost": 0,
            "Count": 0,
            "Usage": "SC",
            "Volume": 100
        }
        
        # Add to both current commands and original commands list
        self.commands.append(new_command)
        self.original_commands.append(new_command.copy())
        
        self.refresh_table()
        
        # Select the new command
        self.table.selectRow(self.table.rowCount() - 1)
        
        # Update Twitch bot if running
        self.update_commands()

    def check_command_cost(self, username, command_cost):
        """Check if the user has enough currency to execute the command"""
        if command_cost <= 0:
            return True
        return self.currency_manager.pay_for_command(username, command_cost)

    def delete_command(self):
        current_row = self.table.currentRow()
        if current_row >= 0 and current_row < len(self.commands):
            # Get the command being deleted
            cmd_to_delete = self.commands[current_row]
            
            # Remove from commands list
            self.commands.pop(current_row)
            
            # Remove from original commands list (find by Command name)
            for i, cmd in enumerate(self.original_commands):
                if cmd["Command"] == cmd_to_delete["Command"]:
                    self.original_commands.pop(i)
                    break
            
            # Remove row from table
            self.table.removeRow(current_row)
            
            # Save changes
            self.save_commands()

    def browse_file(self, line_edit):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Sound File", "", "Sound Files (*.mp3 *.wav *.ogg)")
        if file_name:
            line_edit.setText(file_name)

    def start_bot(self):
        if not self.bot:
            channel = self.channel_edit.text().strip()
            if not channel:
                QMessageBox.warning(self, "Error", "Please enter a channel name")
                return
                
            try:
                # создаём бота
                self.bot = TwitchBot(
                    channel,
                    message_callback=self.twitch_tab.add_to_chat_safe,  # Используем безопасный метод
                    currency_manager=self.currency_manager
                )
                self.twitch_tab.bot = self.bot  # Передаем ссылку на бота в TwitchTab

                self.bot.update_commands(self.commands)

                # Используем значения, загруженные в __init__
                initial_interruption = self.allow_sound_interruption
                initial_show_message = self.show_interruption_message

                # Используем обновленные логи для ясности
                print(f"Setting initial interruption from CommandEditor attribute: {initial_interruption}")
                print(f"Setting initial show message from CommandEditor attribute: {initial_show_message}")

                self.bot.set_interruption(initial_interruption)
                self.bot.set_show_interruption_message(initial_show_message)

                # Регистрация команд бота
                try:
                    self.bot.register_commands()
                    print("Bot commands registered successfully")
                except Exception as e:
                    print(f"Error registering bot commands: {e}")

                # запускаем в потоке
                self.bot_thread = threading.Thread(target=self.bot.run)
                self.bot_thread.daemon = True
                self.bot_thread.start()
                
                self.start_bot_btn.setEnabled(False)
                self.stop_bot_btn.setEnabled(True)
                QMessageBox.information(self, "Success", "Bot started successfully!")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to start bot: {str(e)}")
                if self.bot:
                    self.bot = None
                
    def stop_bot(self):
        if self.bot:
            try:
                self.bot.stop()
                self.bot = None
                self.start_bot_btn.setEnabled(True)
                self.stop_bot_btn.setEnabled(False)
                QMessageBox.information(self, "Success", "Bot stopped successfully!")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error stopping bot: {str(e)}")
                
    def update_commands(self):
        """Update commands in Twitch tab"""
        # No need to get commands from UI since self.commands is already updated
        if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
            self.twitch_tab.bot.update_commands(self.commands)

    def save_legacy_format(self):
        """Save commands in the original format for compatibility"""
        if not self.commands:
            QMessageBox.warning(self, "Error", "No commands to save!")
            return
            
        file_name, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Legacy Format", 
            "", 
            "ABCOMG Files (*.abcomg)"
        )
        
        if file_name:
            if self.config_manager.save_legacy_format(self.commands, file_name):
                QMessageBox.information(self, "Success", "File saved in legacy format successfully!")
            else:
                QMessageBox.warning(self, "Error", "Failed to save file in legacy format!")

    def load_saved_data(self):
        """Load saved commands and configuration"""
        # Load commands from the commands file
        self.commands = self.config_manager.load_commands()
        
        # Load the last used file if specified in config
        current_file = self.config_manager.get_current_file()
        if current_file and os.path.exists(current_file):
            try:
                with open(current_file, "r", encoding="utf-8") as f:
                    self.commands = json.load(f)
                    # Save loaded commands to the separate commands file
                    self.config_manager.save_commands(self.commands)
            except Exception as e:
                print(f"Error loading last used file: {e}")
                
        # Store the original order of commands
        self.original_commands = self.commands.copy()
                
        # Update the table with loaded commands
        self.update_table()
        
        # Update commands in Twitch tab if it exists
        if hasattr(self, 'twitch_tab'):
            self.twitch_tab.commands_data = self.commands
            if self.twitch_tab.bot:
                self.twitch_tab.bot.update_commands(self.commands)

    def auto_save(self):
        """Automatically save commands and configuration"""
        try:
            print("Running auto-save...")

            # Save commands
            if self.commands:
                # Get existing commands for comparison
                existing_commands = []
                try:
                    if os.path.exists('commands.json'):
                        with open('commands.json', 'r', encoding='utf-8') as f:
                            existing_commands = json.load(f)
                except Exception as e:
                    print(f"Error reading existing commands for comparison: {e}")
                    existing_commands = []

                # Save the commands first
                print("Saving commands...")
                with open('commands.json', 'w', encoding='utf-8') as f:
                    json.dump(self.commands, f, indent=4, ensure_ascii=False)

                # Always create backup on auto-save, don't check for significant changes
                print("Creating command backup during auto-save...")
                backup_successful = self.history_manager.save_backup(self.commands)

                if backup_successful:
                    print("Auto-save command backup created successfully")
                    # Always refresh the backup list when a new backup is created
                    self.refresh_backup_list()
                    print("Command backup list refreshed")
                else:
                    print("Failed to create auto-save command backup")

                # Create comprehensive system backup if enabled
                if self.system_auto_backup_enabled:
                    print("Creating comprehensive system backup during auto-save...")
                    system_backup_path = self.create_comprehensive_backup()
                    if system_backup_path:
                        print(f"Auto-save comprehensive backup created: {system_backup_path}")
                        self.refresh_comprehensive_backups()
                    else:
                        print("Failed to create auto-save comprehensive backup")

                # Update commands in Twitch tab if it exists
                if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
                    self.twitch_tab.bot.update_commands(self.commands)

            # Save other settings
            self.config_manager.set_volume(self.volume)
            self.config_manager.set_sound_interruption(self.allow_sound_interruption)
            self.config_manager.set_interruption_message(self.show_interruption_message)
            self.config_manager.set_auto_save(
                self.auto_save_enabled,
                self.auto_save_interval
            )

            print("Auto-save completed successfully")

        except Exception as e:
            print(f"Error during auto-save: {e}")

    def on_command_selected(self):
        """Handle command selection in the table"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            return
            
        row = selected_items[0].row()
        if row < len(self.commands):
            command = self.commands[row]
            
            # Update fields with command data
            self.command_edit.setText(command["Command"])
            self.sound_file_edit.setText(command["SoundFile"])
            
            # Update enabled checkbox without triggering stateChanged signal
            self.enabled_check.blockSignals(True)
            self.enabled_check.setChecked(command["Enabled"])
            self.enabled_check.blockSignals(False)
            
            # Update permission combo without triggering currentIndexChanged signal
            self.permission_combo.blockSignals(True)
            self.permission_combo.setCurrentText(command["Permission"])
            self.permission_combo.blockSignals(False)
            
            self.response_edit.setText(command["Response"])
            self.info_edit.setText(command.get("Info", ""))
            self.group_edit.setText(command.get("Group", "GENERAL"))
            
            # Update cooldown spin without triggering valueChanged signal
            self.cooldown_spin.blockSignals(True)
            self.cooldown_spin.setValue(command.get("Cooldown", 0))
            self.cooldown_spin.blockSignals(False)
            
            # Update user cooldown spin without triggering valueChanged signal
            self.user_cooldown_spin.blockSignals(True)
            self.user_cooldown_spin.setValue(command.get("UserCooldown", 0))
            self.user_cooldown_spin.blockSignals(False)
            
            # Update cost spin without triggering valueChanged signal
            self.cost_spin.blockSignals(True)
            self.cost_spin.setValue(command.get("Cost", 0))
            self.cost_spin.blockSignals(False)
            
            # Update count spin without triggering valueChanged signal
            self.count_spin.blockSignals(True)
            self.count_spin.setValue(command.get("Count", 0))
            self.count_spin.blockSignals(False)
            
            # Update usage combo without triggering currentIndexChanged signal
            self.usage_combo.blockSignals(True)
            self.usage_combo.setCurrentText(command.get("Usage", "SC"))
            self.usage_combo.blockSignals(False)
            
            self.fk_sound_file_edit.setText(str(command.get("FKSoundFile", "")))
            
            # Update volume slider without triggering valueChanged signal
            volume_value = command.get("Volume", 100)
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(volume_value)
            self.volume_slider.blockSignals(False)
            
            # Also update the volume label text to match the current command's volume
            self.volume_value_label.setText(f"{volume_value}%")

    def update_command_field(self, value, column):
        """Update a specific field in the table and command data"""
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            if row < len(self.commands):
                # Update command data
                if column == 0:  # Command
                    self.commands[row]["Command"] = value
                elif column == 1:  # Permission
                    self.commands[row]["Permission"] = value
                elif column == 2:  # Info
                    self.commands[row]["Info"] = value
                elif column == 3:  # Group
                    self.commands[row]["Group"] = value
                elif column == 4:  # Response
                    self.commands[row]["Response"] = value
                elif column == 5:  # Cooldown
                    self.commands[row]["Cooldown"] = value
                elif column == 6:  # UserCooldown
                    self.commands[row]["UserCooldown"] = value
                elif column == 7:  # Cost
                    self.commands[row]["Cost"] = value
                elif column == 8:  # Count
                    self.commands[row]["Count"] = value
                elif column == 9:  # Usage
                    self.commands[row]["Usage"] = value
                elif column == 10:  # Enabled
                    self.commands[row]["Enabled"] = value
                elif column == 11:  # SoundFile
                    self.commands[row]["SoundFile"] = value
                elif column == 12:  # FKSoundFile
                    self.commands[row]["FKSoundFile"] = value
                elif column == 13:  # Volume
                    self.commands[row]["Volume"] = value
                
                # Update table
                item = QTableWidgetItem(str(value))
                self.table.setItem(row, column, item)
                
                # Save changes
                self.save_commands()
                
                # Update commands in Twitch bot if it exists
                if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
                    self.twitch_tab.bot.update_commands(self.commands)
                    
    def on_enabled_changed(self, state):
        self.update_command_field(state == Qt.Checked, 10)  # Corrected column index
        
    def on_permission_changed(self, text):
        self.update_command_field(text, 1)  # Corrected column index
        
    def on_response_changed(self, text):
        self.update_command_field(text, 4)  # Corrected column index
        
    def on_info_changed(self, text):
        self.update_command_field(text, 2)  # Corrected column index
        
    def on_group_changed(self, text):
        self.update_command_field(text, 3)  # Corrected column index
        
    def on_cooldown_changed(self, value):
        self.update_command_field(value, 5)  # Corrected column index
        
    def on_user_cooldown_changed(self, value):
        self.update_command_field(value, 6)  # Corrected column index
        
    def on_cost_changed(self, value):
        self.update_command_field(value, 7)  # Corrected column index
        
    def on_count_changed(self, value):
        self.update_command_field(value, 8)  # Corrected column index
        
    def on_usage_changed(self, text):
        self.update_command_field(text, 9)  # Corrected column index
        
    def on_fk_sound_file_changed(self, text):
        self.update_command_field(text, 12)  # Corrected column index
        
    def on_volume_changed(self, value):
        self.update_command_field(value, 13)  # Corrected column index

    def save_commands(self):
        """Save commands to file"""
        try:
            # Update commands from table
            for i in range(self.table.rowCount()):
                if i >= len(self.commands):  # Safety check
                    continue
                    
                cmd = self.commands[i]
                
                # Get items from table, with None checks
                command_item = self.table.item(i, 0)
                permission_item = self.table.item(i, 1)
                info_item = self.table.item(i, 2)
                group_item = self.table.item(i, 3)
                response_item = self.table.item(i, 4)
                cooldown_item = self.table.item(i, 5)
                user_cooldown_item = self.table.item(i, 6)
                cost_item = self.table.item(i, 7)
                count_item = self.table.item(i, 8)
                usage_item = self.table.item(i, 9)
                enabled_item = self.table.item(i, 10)
                sound_file_item = self.table.item(i, 11)
                fk_sound_file_item = self.table.item(i, 12)
                volume_item = self.table.item(i, 13)
                
                # Update command data only if items exist
                if command_item:
                    cmd["Command"] = command_item.text()
                if permission_item:
                    cmd["Permission"] = permission_item.text()
                if info_item:
                    cmd["Info"] = info_item.text()
                if group_item:
                    cmd["Group"] = group_item.text()
                if response_item:
                    cmd["Response"] = response_item.text()
                if cooldown_item:
                    try:
                        cmd["Cooldown"] = int(cooldown_item.text() or 0)
                    except ValueError:
                        cmd["Cooldown"] = 0
                if user_cooldown_item:
                    try:
                        cmd["UserCooldown"] = int(user_cooldown_item.text() or 0)
                    except ValueError:
                        cmd["UserCooldown"] = 0
                if cost_item:
                    try:
                        cmd["Cost"] = int(cost_item.text() or 0)
                    except ValueError:
                        cmd["Cost"] = 0
                if count_item:
                    try:
                        cmd["Count"] = int(count_item.text() or 0)
                    except ValueError:
                        cmd["Count"] = 0
                if usage_item:
                    cmd["Usage"] = usage_item.text()
                if enabled_item:
                    cmd["Enabled"] = enabled_item.text() == "✓"
                if sound_file_item:
                    cmd["SoundFile"] = sound_file_item.text()
                if fk_sound_file_item:
                    cmd["FKSoundFile"] = fk_sound_file_item.text()
                if volume_item:
                    try:
                        cmd["Volume"] = int(volume_item.text() or 100)
                    except ValueError:
                        cmd["Volume"] = 100
                
            # Save to file
            with open('commands.json', 'w', encoding='utf-8') as f:
                json.dump(self.commands, f, indent=4, ensure_ascii=False)
                
            # Update commands in Twitch tab if it exists
            if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
                self.twitch_tab.bot.update_commands(self.commands)
                
        except Exception as e:
            print(f"Error saving commands: {e}")

    def disconnect_bot(self):
        if self.bot:
            # Сохраняем статистику команд перед отключением
            self.save_commands()
            # ... остальной код отключения

    def _has_significant_changes(self, old_commands, new_commands):
        """Determine if changes are significant enough to warrant a backup
        
        Returns:
            bool: True if significant changes detected, False otherwise
        """
        # If no previous commands, this is significant
        if not old_commands:
            return True
            
        # If command count changed by more than 1, it's significant
        if abs(len(old_commands) - len(new_commands)) > 1:
            return True
        
        # Check for changes in command names, sound files, or responses
        old_map = {cmd["Command"]: cmd for cmd in old_commands}
        new_map = {cmd["Command"]: cmd for cmd in new_commands}
        
        # If any commands were added or removed
        if set(old_map.keys()) != set(new_map.keys()):
            return True
        
        # Check for significant changes in existing commands
        for cmd_name, new_cmd in new_map.items():
            if cmd_name in old_map:
                old_cmd = old_map[cmd_name]
                
                # Check if sound file changed
                if old_cmd.get("SoundFile", "") != new_cmd.get("SoundFile", ""):
                    return True
                    
                # Check if response changed
                if old_cmd.get("Response", "") != new_cmd.get("Response", ""):
                    return True
        
        return False

    def set_editing_enabled(self, enabled):
        """Enable or disable command editing buttons"""
        self.add_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)
        # Also disable the table if editing is disabled
        self.table.setEnabled(enabled)

    def on_interruption_toggle(self, state):
        """Handle interruption toggle change"""
        self.allow_sound_interruption = (state == Qt.Checked)
        self.config_manager.set_sound_interruption(self.allow_sound_interruption)
        
        # Update the setting in Twitch bot if it exists
        if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
            self.twitch_tab.bot.set_interruption(self.allow_sound_interruption)
            self.twitch_tab.add_to_chat_safe(
                f"Sound interruption setting changed: {'Enabled' if self.allow_sound_interruption else 'Disabled'}"
            )

    def on_show_message_toggle(self, state):
        """Handle show message toggle change"""
        self.show_interruption_message = (state == Qt.Checked)
        self.config_manager.set_interruption_message(self.show_interruption_message)
        
        # Update the setting in Twitch bot if it exists
        if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
            self.twitch_tab.bot.set_show_interruption_message(self.show_interruption_message)
            self.twitch_tab.add_to_chat_safe(
                f"Interruption message: {'Enabled' if self.show_interruption_message else 'Disabled'}"
            )

    def on_auto_save_toggle(self, state):
        self.auto_save_enabled = (state == Qt.Checked)
        
        # Update timer
        if self.auto_save_enabled:
            self.auto_save_timer.start(self.auto_save_interval * 1000)
        else:
            self.auto_save_timer.stop()
            
        # Save setting
        self.config_manager.set_auto_save(self.auto_save_enabled, self.auto_save_interval)

    def on_auto_save_interval_changed(self, value):
        self.auto_save_interval = value

        # Update timer if already running
        if self.auto_save_enabled and self.auto_save_timer.isActive():
            self.auto_save_timer.stop()
            self.auto_save_timer.start(value * 1000)

        # Save setting
        self.config_manager.set_auto_save(self.auto_save_enabled, self.auto_save_interval)

    def on_system_auto_backup_toggle(self, state):
        """Handle system auto-backup toggle change"""
        self.system_auto_backup_enabled = (state == Qt.Checked)

        # Update timer
        if self.system_auto_backup_enabled:
            self.system_auto_backup_timer.start(self.system_backup_interval * 1000)
            print(f"System auto-backup enabled with interval: {self.system_backup_interval} seconds")
        else:
            self.system_auto_backup_timer.stop()
            print("System auto-backup disabled")

        # Save the setting to config
        self.config_manager.set_system_auto_backup(self.system_auto_backup_enabled, self.system_backup_interval)

    def on_system_backup_interval_changed(self, value):
        """Handle system backup interval change"""
        self.system_backup_interval = value

        # Update timer if already running
        if self.system_auto_backup_enabled and self.system_auto_backup_timer.isActive():
            self.system_auto_backup_timer.stop()
            self.system_auto_backup_timer.start(value * 1000)

        # Save the interval to config
        self.config_manager.set_system_auto_backup(self.system_auto_backup_enabled, self.system_backup_interval)

        print(f"System backup interval changed to: {value} seconds")

    def on_currency_auto_save_toggle(self, state):
        """Handle currency auto-save toggle change"""
        self.currency_auto_save_enabled = (state == Qt.Checked)

        # Update timer
        if self.currency_auto_save_enabled:
            self.currency_auto_backup_timer.start(self.currency_backup_interval * 1000)
            print(f"Currency auto-save enabled with interval: {self.currency_backup_interval} seconds")
        else:
            self.currency_auto_backup_timer.stop()
            print("Currency auto-save disabled")

    def on_currency_backup_interval_changed(self, value):
        """Handle currency backup interval change"""
        self.currency_backup_interval = value

        # Update timer if already running
        if self.currency_auto_save_enabled and self.currency_auto_backup_timer.isActive():
            self.currency_auto_backup_timer.stop()
            self.currency_auto_backup_timer.start(value * 1000)

        print(f"Currency backup interval changed to: {value} seconds")

    def currency_auto_save_auto(self):
        """Automatically save currency user data at scheduled intervals"""
        try:
            print("Running automatic currency auto-save...")

            # Only save if currency manager exists and has users
            if hasattr(self, 'currency_manager') and hasattr(self.currency_manager, 'users'):
                if self.currency_manager.users:
                    success = self.currency_manager.enhanced_save_users(force_backup=False)
                    if success:
                        print("Automatic currency auto-save completed successfully")
                        users_saved = len(self.currency_manager.users)
                        print(f"Saved {users_saved} currency users automatically")
                    else:
                        print("Failed to save currency users automatically")
                else:
                    print("No currency users to save automatically")
            else:
                print("Currency manager not available for auto-save")

        except Exception as e:
            print(f"Error during automatic currency auto-save: {e}")

    def create_comprehensive_backup_auto(self):
        """Automatically create comprehensive backup at scheduled intervals"""
        try:
            print("Running automatic comprehensive backup...")

            # Create the backup
            backup_path = self.create_comprehensive_backup()

            if backup_path:
                print(f"Automatic comprehensive backup created: {backup_path}")
                # Refresh the backup list
                self.refresh_comprehensive_backups()
            else:
                print("Failed to create automatic comprehensive backup")

        except Exception as e:
            print(f"Error during automatic comprehensive backup: {e}")

    def filter_commands(self):
        """Filter displayed commands based on search text"""
        search_text = self.search_input.text().lower()
        
        # Show all commands if search is empty
        if not search_text:
            for row in range(self.table.rowCount()):
                self.table.setRowHidden(row, False)
            return
                
        # Hide rows that don't match the search
        for row in range(self.table.rowCount()):
            match_found = False
            
            # Search through all columns
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and search_text in item.text().lower():
                    match_found = True
                    break
                    
            # Hide/show the row based on match
            self.table.setRowHidden(row, not match_found)  # Fixed: not_match_found -> not match_found

    def create_history_tab(self):
        """Create the History tab for command backups"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Command History")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        header_label.setFont(font)
        
        # Create backup button
        create_backup_btn = QPushButton("Create Backup Now")
        create_backup_btn.clicked.connect(self.create_backup)
        
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        header_layout.addWidget(create_backup_btn)
        layout.addLayout(header_layout)
        
        # Description
        description = QLabel("The system automatically saves backups when you make significant changes. You can restore previous versions from here.")
        description.setWordWrap(True)
        layout.addWidget(description)
        
        # Create table for backups
        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(4)
        self.backup_table.setHorizontalHeaderLabels(["Date & Time", "Size (KB)", "Actions", ""])
        self.backup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.backup_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        # Load backup list
        self.refresh_backup_list();
        
        layout.addWidget(self.backup_table)
        
        # Auto-backup settings
        backup_settings = QGroupBox("Backup Settings")
        backup_settings_layout = QHBoxLayout()
        
        # Max backups setting
        max_backups_label = QLabel("Maximum number of backups:")
        self.max_backups_spin = QSpinBox()
        self.max_backups_spin.setMinimum(1)
        self.max_backups_spin.setMaximum(100)
        self.max_backups_spin.setValue(self.history_manager.max_backups)
        self.max_backups_spin.valueChanged.connect(self.update_max_backups)
        
        backup_settings_layout.addWidget(max_backups_label)
        backup_settings_layout.addWidget(self.max_backups_spin)
        backup_settings_layout.addStretch()
        
        backup_settings.setLayout(backup_settings_layout)
        layout.addWidget(backup_settings)
        
        tab.setLayout(layout)
        return tab

    def refresh_backup_list(self):
        """Refresh the list of backups in the table"""
        self.backup_table.setRowCount(0)
        
        backups = self.history_manager.get_backups()
        
        for i, backup in enumerate(backups):
            self.backup_table.insertRow(i)
            
            # Date & Time
            self.backup_table.setItem(i, 0, QTableWidgetItem(backup["readable_time"]))
            
            # Size
            self.backup_table.setItem(i, 1, QTableWidgetItem(f"{backup['size']} KB"))
            
            # Restore button
            restore_btn = QPushButton("Restore")
            restore_btn.clicked.connect(lambda checked, path=backup["path"]: self.restore_backup(path))
            
            # View button
            view_btn = QPushButton("View")
            view_btn.clicked.connect(lambda checked, path=backup["path"]: self.view_backup(path))
            
            # Add buttons to table
            self.backup_table.setCellWidget(i, 2, restore_btn)
            self.backup_table.setCellWidget(i, 3, view_btn)

    def create_backup(self):
        """Create a backup of current commands"""
        if not self.commands:
            QMessageBox.warning(self, "Warning", "No commands to backup.")
            return
            
        if self.history_manager.save_backup(self.commands):
            self.refresh_backup_list()
            QMessageBox.information(self, "Success", "Backup created successfully!")
        else:
            QMessageBox.warning(self, "Error", "Failed to create backup.")
            
    def restore_backup(self, backup_path):
        """Restore commands from a backup file"""
        if not backup_path:
            return
            
        reply = QMessageBox.question(
            self,
            "Confirm Restore",
            "Restoring will replace your current commands. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            commands = self.history_manager.restore_backup(backup_path)
            
            if commands:
                # Update commands
                self.commands = commands
                
                # Also update original_commands for sorting reset
                self.original_commands = self.commands.copy()
                
                # Refresh the table
                self.refresh_table()
                
                # Update Twitch bot if running
                self.update_commands()
                
                QMessageBox.information(self, "Success", "Commands restored successfully!")
            else:
                QMessageBox.warning(self, "Error", "Failed to restore backup.")

    def view_backup(self, backup_path):
        """View contents of a backup file"""
        if not backup_path:
            return
            
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                commands = json.load(f)
                
            # Create a dialog to show the backup contents
            dialog = QDialog(self)
            dialog.setWindowTitle("Backup Contents")
            dialog.setMinimumSize(800, 600)
            
            dialog_layout = QVBoxLayout()
            
            # Create a table to show commands
            backup_view = QTableWidget()
            backup_view.setColumnCount(7)  # Increased to 7 columns to include Cooldown
            backup_view.setHorizontalHeaderLabels([
                "Command", "Sound File", "Response", "Group", 
                "Enabled", "Volume", "Cooldown"  # Added Cooldown column
            ])
            backup_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            
            # Populate table
            backup_view.setRowCount(len(commands))
            for i, cmd in enumerate(commands):
                backup_view.setItem(i, 0, QTableWidgetItem(cmd["Command"]))
                backup_view.setItem(i, 1, QTableWidgetItem(cmd["SoundFile"]))
                backup_view.setItem(i, 2, QTableWidgetItem(cmd["Response"]))
                backup_view.setItem(i, 3, QTableWidgetItem(cmd.get("Group", "")))
                backup_view.setItem(i, 4, QTableWidgetItem("✓" if cmd["Enabled"] else "✗"))
                backup_view.setItem(i, 5, QTableWidgetItem(str(cmd.get("Volume", 100))))
                backup_view.setItem(i, 6, QTableWidgetItem(str(cmd.get("Cooldown", 0))))  # Added Cooldown value
                
            dialog_layout.addWidget(backup_view)
            
            # Add close button
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.close)
            dialog_layout.addWidget(close_btn)
            
            dialog.setLayout(dialog_layout)
            dialog.exec_()
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to view backup: {str(e)}")

    def update_max_backups(self, value):
        """Update the maximum number of backups to keep"""
        self.history_manager.max_backups = value
        # Save this setting to config file
        self.config_manager.set_max_backups(value)

    def update_max_comprehensive_backups(self, value):
        """Update the maximum number of comprehensive backups to keep"""
        try:
            self.config_manager.set_max_comprehensive_backups(value)
            self._cleanup_old_comprehensive_backups()
            print(f"Updated max comprehensive backups to: {value}")
        except Exception as e:
            print(f"Error updating max comprehensive backups: {e}")

    def handle_no_users_data(self, users_data):
        if not users_data:
            print("No currency users data available")
            # Обновить метку времени последнего обновления
            now = QDateTime.currentDateTime().toString("HH:mm:ss")
            self.last_update.setText(f"Last update: {now}")
            return

    def create_comprehensive_backup_tab(self):
        """Create a comprehensive backup tab for full system backups"""
        tab = QWidget()
        layout = QVBoxLayout()

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Comprehensive System Backups")
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        header_label.setFont(font)

        header_layout.addWidget(header_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Description
        description = QLabel(
            "Create and manage full system backups that include all commands, moderator settings, "
            "currency user data, and application settings. This allows you to restore the entire "
            "application state in case of major issues."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Backup creation section
        create_group = QGroupBox("Create Backup")
        create_layout = QVBoxLayout()

        create_info = QLabel(
            "A comprehensive backup includes:\n"
            "• All commands and their settings\n"
            "• Currency users and points\n"
            "• Moderator settings\n"
            "• Application configuration\n"
            "• Rank settings"
        )
        create_info.setStyleSheet("color: gray;")
        create_layout.addWidget(create_info)

        # Create backup button
        self.create_system_backup_btn = QPushButton("Create Full System Backup")
        self.create_system_backup_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                font-size: 12px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.create_system_backup_btn.clicked.connect(self.create_comprehensive_backup)
        create_layout.addWidget(self.create_system_backup_btn)

        create_group.setLayout(create_layout)
        layout.addWidget(create_group)

        # Backup settings section
        settings_group = QGroupBox("Backup Settings")
        settings_layout = QVBoxLayout()

        # Max comprehensive backups setting
        max_backups_layout = QHBoxLayout()
        max_backups_label = QLabel("Maximum Backups:")
        self.max_comprehensive_backups_spin = QSpinBox()
        self.max_comprehensive_backups_spin.setMinimum(1)
        self.max_comprehensive_backups_spin.setMaximum(50)
        self.max_comprehensive_backups_spin.setValue(self.config_manager.get_max_comprehensive_backups())
        self.max_comprehensive_backups_spin.valueChanged.connect(self.update_max_comprehensive_backups)
        max_backups_layout.addWidget(max_backups_label)
        max_backups_layout.addWidget(self.max_comprehensive_backups_spin)
        max_backups_layout.addStretch()
        settings_layout.addLayout(max_backups_layout)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Backup list section
        list_group = QGroupBox("Available Backups")
        list_layout = QVBoxLayout()

        # Controls
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("Status:"))
        self.system_backup_status_label = QLabel("Loading...")
        controls_layout.addWidget(self.system_backup_status_label)

        refresh_btn = QPushButton("Refresh List")
        refresh_btn.clicked.connect(self.refresh_comprehensive_backups)
        controls_layout.addWidget(refresh_btn)

        controls_layout.addStretch()
        list_layout.addLayout(controls_layout)

        # Backup list container
        self.system_backup_list_layout = QVBoxLayout()
        self.system_backup_list_widget = QWidget()
        self.system_backup_list_widget.setLayout(self.system_backup_list_layout)
        list_layout.addWidget(self.system_backup_list_widget)

        list_group.setLayout(list_layout)
        layout.addWidget(list_group)

        # Load initial backup list
        QTimer.singleShot(500, self.refresh_comprehensive_backups)

        # Add spacer
        layout.addStretch()

        tab.setLayout(layout)
        return tab

    def create_comprehensive_backup(self):
        """Create a comprehensive backup of the entire system"""
        try:
            self.create_system_backup_btn.setEnabled(False)
            self.create_system_backup_btn.setText("Creating Backup...")

            # Create backup directory
            backup_dir = Path("backups") / "comprehensive"
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Generate timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"system_backup_{timestamp}"
            backup_path = backup_dir / backup_name

            backup_data = {
                "backup_info": {
                    "timestamp": datetime.now().isoformat(),
                    "version": "1.0",
                    "description": "Comprehensive system backup"
                },
                "commands": self.commands.copy() if self.commands else [],
                "currency_users": {},
                "moderators": {},
                "config": {},
                "ranks": []
            }

            # Add currency data if available
            if hasattr(self, 'currency_manager') and self.currency_manager.users:
                backup_data["currency_users"] = self.currency_manager.users.copy()

            # Add moderator data
            try:
                backup_data["moderators"] = {
                    "manual": self.config_manager.get_manual_moderators(),
                    "excluded": self.config_manager.get_excluded_moderators()
                }
            except:
                backup_data["moderators"] = {"manual": [], "excluded": []}

            # Add configuration
            try:
                backup_data["config"] = {
                    "volume": self.config_manager.get_volume(),
                    "sound_interruption": self.config_manager.get_sound_interruption(),
                    "interruption_message": self.config_manager.get_interruption_message(),
                    "auto_save": self.config_manager.get_auto_save(),
                    "max_backups": self.config_manager.get_max_backups(),
                    "twitch_config": self.config_manager.get_twitch_config()
                }
            except:
                backup_data["config"] = {}

            # Add ranks data
            try:
                if hasattr(self, 'currency_manager') and hasattr(self.currency_manager, 'ranks'):
                    backup_data["ranks"] = self.currency_manager.ranks.copy()
                else:
                    backup_data["ranks"] = []
            except:
                backup_data["ranks"] = []

            # Save backup data
            with open(backup_path.with_suffix('.json'), 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)

            # Create metadata
            metadata = {
                "backup_time": time.time(),
                "backup_name": backup_name,
                "commands_count": len(backup_data["commands"]),
                "users_count": len(backup_data["currency_users"]),
                "moderators_count": len(backup_data["moderators"].get("manual", [])),
                "total_size": backup_path.with_suffix('.json').stat().st_size
            }

            with open(backup_path.with_suffix('.json.meta'), 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)

            # Clean up old comprehensive backups
            self._cleanup_old_comprehensive_backups()

            # Refresh the list
            self.refresh_comprehensive_backups()

            QMessageBox.information(
                self,
                "Backup Created",
                f"Comprehensive system backup created successfully!\n\n"
                f"Backup file: {backup_name}.json\n"
                f"Includes {len(backup_data['commands'])} commands, "
                f"{len(backup_data['currency_users'])} users, "
                f"and all system settings."
            )

        except Exception as e:
            print(f"Error creating comprehensive backup: {e}")
            QMessageBox.critical(
                self,
                "Backup Failed",
                f"Failed to create comprehensive backup:\n\n{str(e)}"
            )
        finally:
            self.create_system_backup_btn.setEnabled(True)
            self.create_system_backup_btn.setText("Create Full System Backup")

    def refresh_comprehensive_backups(self):
        """Refresh the list of comprehensive backups"""
        try:
            from PyQt5.QtWidgets import QFrame

            # Clear existing items
            layout = self.system_backup_list_layout
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            # Get backup directory
            backup_dir = Path("backups") / "comprehensive"
            if not backup_dir.exists():
                self.system_backup_status_label.setText("No backups found")
                self.system_backup_status_label.setStyleSheet("color: gray;")
                return

            # Get backup files
            backup_files = list(backup_dir.glob("system_backup_*.json"))
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            if not backup_files:
                no_backups_label = QLabel("No comprehensive backups found.")
                no_backups_label.setStyleSheet("color: gray; font-style: italic;")
                layout.addWidget(no_backups_label)
                self.system_backup_status_label.setText("No backups")
                self.system_backup_status_label.setStyleSheet("color: gray;")
                return

            # Update status
            self.system_backup_status_label.setText(f"{len(backup_files)} backups available")
            self.system_backup_status_label.setStyleSheet("color: blue;")

            # Add each backup
            for i, backup_file in enumerate(backup_files):
                try:
                    # Load metadata
                    meta_file = backup_file.with_suffix('.json.meta')
                    metadata = {}
                    if meta_file.exists():
                        with open(meta_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)

                    # Create backup frame
                    frame = QFrame()
                    frame.setFrameStyle(QFrame.Box)
                    frame.setLineWidth(1)
                    frame_layout = QVBoxLayout()

                    # Header with backup info
                    header_layout = QHBoxLayout()
                    backup_name = backup_file.stem

                    time_label = QLabel(f"📦 {backup_name}")
                    time_label.setStyleSheet("font-weight: bold;")
                    header_layout.addWidget(time_label)

                    # Size info
                    size_bytes = metadata.get('total_size', backup_file.stat().st_size)
                    if size_bytes < 1024:
                        size_str = f"{size_bytes} B"
                    elif size_bytes < 1024 * 1024:
                        size_str = f"{size_bytes / 1024:.1f} KB"
                    else:
                        size_str = f"{size_bytes / (1024 * 1024):.1f} MB"

                    size_label = QLabel(f"💾 {size_str}")
                    header_layout.addWidget(size_label)

                    # Content info
                    content_info = (f"📋 {metadata.get('commands_count', '?')} cmds, "
                                  f"👥 {metadata.get('users_count', '?')} users, "
                                  f"🛡️ {metadata.get('moderators_count', '?')} mods")
                    content_label = QLabel(content_info)
                    header_layout.addWidget(content_label)

                    # Timestamp if available
                    if 'backup_time' in metadata:
                        timestamp = datetime.fromtimestamp(metadata['backup_time'])
                        time_str = timestamp.strftime("%H:%M %d/%m/%Y")
                        time_info_label = QLabel(f"⏰ {time_str}")
                        time_info_label.setStyleSheet("color: gray;")
                        header_layout.addWidget(time_info_label)

                    header_layout.addStretch()
                    frame_layout.addLayout(header_layout)

                    # Action buttons
                    buttons_layout = QHBoxLayout()
                    buttons_layout.addSpacing(10)

                    # Restore button
                    restore_btn = QPushButton("Restore System")
                    restore_btn.setToolTip("Restore the entire system from this backup")
                    restore_btn.clicked.connect(lambda checked, path=backup_file: self.restore_comprehensive_backup(path))
                    buttons_layout.addWidget(restore_btn)

                    # View info button
                    info_btn = QPushButton("Details")
                    info_btn.setToolTip("Show detailed backup information")
                    info_btn.clicked.connect(lambda checked, b=backup_file: self.show_comprehensive_backup_info(b))
                    buttons_layout.addWidget(info_btn)

                    buttons_layout.addStretch()
                    frame_layout.addLayout(buttons_layout)

                    frame.setLayout(frame_layout)

                    # Style the frame (latest backup in green)
                    if i == 0:
                        frame.setStyleSheet("""
                            QFrame {
                                border: 2px solid #4CAF50;
                                border-radius: 5px;
                                background-color: #f9fff9;
                            }
                        """)

                    layout.addWidget(frame)
                    layout.addSpacing(5)

                except Exception as e:
                    print(f"Error loading backup {backup_file}: {e}")
                    # Add error item
                    error_label = QLabel(f"⚠️ Error loading backup: {backup_file.name}")
                    error_label.setStyleSheet("color: red;")
                    layout.addWidget(error_label)

        except Exception as e:
            print(f"Error refreshing comprehensive backups: {e}")
            self.system_backup_status_label.setText("Error loading backups")
            self.system_backup_status_label.setStyleSheet("color: red;")

    def restore_comprehensive_backup(self, backup_file):
        """Restore the entire system from a comprehensive backup"""
        try:
            reply = QMessageBox.question(
                self,
                "⚠️ Dangerous Operation",
                "This will REPLACE your entire current system state with the backup data.\n\n"
                "This includes:\n"
                "• All commands\n"
                "• All user points and hours\n"
                "• Moderator settings\n"
                "• Application configuration\n\n"
                "Are you ABSOLUTELY sure you want to continue?\n\n"
                "It is recommended to create a manual backup first!",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply != QMessageBox.Yes:
                return

            # Additional confirmation
            reply2 = QMessageBox.question(
                self,
                "Final Confirmation",
                "This action cannot be undone easily.\n\n"
                "Do you really want to restore the entire system?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply2 != QMessageBox.Yes:
                return

            # Load backup data
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)

            # Restore commands
            if 'commands' in backup_data:
                self.commands = backup_data['commands']
                self.original_commands = self.commands.copy()
                self.refresh_table()
                self.config_manager.save_commands(self.commands)

            # Restore currency users
            if 'currency_users' in backup_data and hasattr(self, 'currency_manager'):
                self.currency_manager.users = backup_data['currency_users']
                self.currency_manager.save_users()

                # Refresh currency tabs
                if hasattr(self, 'user_currency_tab'):
                    self.user_currency_tab.populate_table()

            # Restore moderators
            if 'moderators' in backup_data:
                try:
                    manual_mods = backup_data['moderators'].get('manual', [])
                    excluded_mods = backup_data['moderators'].get('excluded', [])

                    # Save to config
                    for mod in manual_mods:
                        self.config_manager.add_manual_moderator(mod)
                    for mod in excluded_mods:
                        self.config_manager.add_excluded_moderator(mod)

                    # Refresh moderator display
                    if hasattr(self, 'twitch_tab') and hasattr(self.twitch_tab, 'update_moderators_display_only'):
                        self.twitch_tab.update_moderators_display_only()

                except Exception as e:
                    print(f"Error restoring moderators: {e}")

            # Restore ranks
            if 'ranks' in backup_data and hasattr(self, 'currency_manager'):
                self.currency_manager.ranks = backup_data['ranks']
                self.currency_manager.save_ranks()

                # Refresh ranks tab
                if hasattr(self, 'ranks_tab'):
                    self.ranks_tab.load_ranks()

            # Restore config settings
            if 'config' in backup_data:
                config_data = backup_data['config']
                try:
                    if 'volume' in config_data:
                        self.config_manager.set_volume(config_data['volume'])
                    if 'sound_interruption' in config_data:
                        self.config_manager.set_sound_interruption(config_data['sound_interruption'])
                    if 'interruption_message' in config_data:
                        self.config_manager.set_interruption_message(config_data['interruption_message'])
                    if 'auto_save' in config_data:
                        auto_save = config_data['auto_save']
                        self.config_manager.set_auto_save(auto_save.get('enabled', True), auto_save.get('interval', 300))
                    if 'max_backups' in config_data:
                        self.config_manager.set_max_backups(config_data['max_backups'])
                    if 'twitch_config' in config_data:
                        # Merge twitch config carefully
                        twitch_config = config_data['twitch_config']
                        # Only update non-sensitive fields
                        if 'channel' in twitch_config:
                            self.config_manager.set_twitch_channel(twitch_config['channel'])
                except Exception as e:
                    print(f"Error restoring config: {e}")

            # Update bot commands if running
            if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
                self.twitch_tab.bot.update_commands(self.commands)

            QMessageBox.information(
                self,
                "Restoration Complete",
                "System has been successfully restored from backup!\n\n"
                "Please restart the application to ensure all changes take effect."
            )

        except Exception as e:
            print(f"Error during comprehensive restoration: {e}")
            QMessageBox.critical(
                self,
                "Restoration Failed",
                f"Failed to restore system from backup:\n\n{str(e)}"
            )

    def show_comprehensive_backup_info(self, backup_file):
        """Show detailed information about a comprehensive backup"""
        try:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QGroupBox

            # Load backup data
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)

            dialog = QDialog(self)
            dialog.setWindowTitle("Comprehensive Backup Details")
            dialog.setModal(True)
            dialog.setMinimumSize(600, 400)

            layout = QVBoxLayout()

            # Backup info
            info_group = QGroupBox("Backup Information")
            info_layout = QVBoxLayout()

            backup_info = backup_data.get('backup_info', {})
            info_text = f"""
            <b>Timestamp:</b> {backup_info.get('timestamp', 'Unknown')}
            <b>Version:</b> {backup_info.get('version', 'Unknown')}
            <b>Description:</b> {backup_info.get('description', 'Unknown')}
            """
            info_label = QLabel(info_text)
            info_label.setTextFormat(1)  # Rich text
            info_layout.addWidget(info_label)

            info_group.setLayout(info_layout)
            layout.addWidget(info_group)

            # Content summary
            content_group = QGroupBox("Content Summary")
            content_layout = QVBoxLayout()

            commands_count = len(backup_data.get('commands', []))
            users_count = len(backup_data.get('currency_users', {}))
            moderators_count = len(backup_data.get('moderators', {}).get('manual', []))
            ranks_count = len(backup_data.get('ranks', []))

            content_text = f"""
            <b>Commands:</b> {commands_count}
            <b>Currency Users:</b> {users_count}
            <b>Moderators:</b> {moderators_count}
            <b>Ranks:</b> {ranks_count}
            """
            content_label = QLabel(content_text)
            content_label.setTextFormat(1)  # Rich text
            content_layout.addWidget(content_label)

            content_group.setLayout(content_layout)
            layout.addWidget(content_group)

            # Buttons
            buttons = QDialogButtonBox(QDialogButtonBox.Ok)
            buttons.accepted.connect(dialog.accept)
            layout.addWidget(buttons)

            dialog.setLayout(layout)
            dialog.exec_()

        except Exception as e:
            print(f"Error showing comprehensive backup info: {e}")
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to show backup details:\n\n{str(e)}"
            )

    def resizeEvent(self, event):
        """Handle window resize and update notification position"""
        super().resizeEvent(event)
        if hasattr(self, 'update_notification') and self.update_notification.isVisible():
            self.update_notification.update_position()

    def create_comprehensive_backup_method(self):
        """Create a comprehensive backup of the entire application state"""
        return self.create_comprehensive_backup()

    def create_comprehensive_backup(self):
        """Create a comprehensive backup of the entire system"""
        try:
            # Create backup directory
            backup_dir = Path("backups") / "comprehensive"
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Generate timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"system_backup_{timestamp}"
            backup_path = backup_dir / backup_name

            backup_data = {
                "backup_info": {
                    "timestamp": datetime.now().isoformat(),
                    "version": "1.0",
                    "description": "Comprehensive system backup created during operation"
                },
                "commands": self.commands.copy() if self.commands else [],
                "currency_users": {},
                "moderators": {},
                "config": {},
                "ranks": [],
                "command_history": {},
                "currency_settings": {}
            }

            # Add currency data if available
            if hasattr(self, 'currency_manager') and self.currency_manager.users:
                backup_data["currency_users"] = self.currency_manager.users.copy()
                backup_data["ranks"] = getattr(self.currency_manager, 'ranks', [])

            # Add currency settings
            if hasattr(self, 'currency_manager'):
                backup_data["currency_settings"] = {
                    "settings": getattr(self.currency_manager, 'settings', {}),
                    "backup_dir": str(getattr(self.currency_manager, 'backup_dir', '')),
                    "max_backups": getattr(self.currency_manager, 'max_currency_backups', 10)
                }

            # Add moderator data
            try:
                backup_data["moderators"] = {
                    "manual": self.config_manager.get_manual_moderators() if hasattr(self.config_manager, 'get_manual_moderators') else [],
                    "excluded": self.config_manager.get_excluded_moderators() if hasattr(self.config_manager, 'get_excluded_moderators') else []
                }
            except:
                backup_data["moderators"] = {"manual": [], "excluded": []}

            # Add configuration
            try:
                backup_data["config"] = {
                    "volume": self.config_manager.get_volume(),
                    "sound_interruption": self.config_manager.get_sound_interruption(),
                    "interruption_message": self.config_manager.get_interruption_message(),
                    "auto_save": self.config_manager.get_auto_save(),
                    "max_backups": self.config_manager.get_max_backups(),
                    "twitch_config": self.config_manager.get_twitch_config() if hasattr(self.config_manager, 'get_twitch_config') else {}
                }
            except Exception as e:
                print(f"Error backing up config: {e}")
                backup_data["config"] = {}

            # Add command history if available
            try:
                if hasattr(self, 'history_manager'):
                    backup_data["command_history"] = {
                        "max_backups": self.history_manager.max_backups,
                        "backup_dir": str(self.history_manager.backup_dir)
                    }
            except Exception as e:
                print(f"Error backing up command history metadata: {e}")

            # Save backup data
            with open(backup_path.with_suffix('.json'), 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)

            # Create metadata
            metadata = {
                "backup_time": time.time(),
                "backup_name": backup_name,
                "commands_count": len(backup_data["commands"]),
                "users_count": len(backup_data["currency_users"]),
                "moderators_count": len(backup_data["moderators"].get("manual", [])),
                "total_size": backup_path.with_suffix('.json').stat().st_size,
                "version": backup_data["backup_info"]["version"]
            }

            with open(backup_path.with_suffix('.json.meta'), 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)

            print(f"[COMPREHENSIVE BACKUP] Created backup: {backup_path.name}")
            return backup_path

        except Exception as e:
            print(f"Error creating comprehensive backup: {e}")
            return None

    def _cleanup_old_comprehensive_backups(self):
        """Remove old comprehensive backups keeping only the most recent ones"""
        try:
            from pathlib import Path

            # Get backup directory
            backup_dir = Path("backups") / "comprehensive"
            if not backup_dir.exists():
                return

            # Get backup files
            backup_files = list(backup_dir.glob("system_backup_*.json"))

            # Get max comprehensive backups setting
            max_backups = self.config_manager.get_max_comprehensive_backups()

            if len(backup_files) <= max_backups:
                return

            # Sort by modification time (newest first)
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

            # Remove old backups
            for old_backup in backup_files[max_backups:]:
                try:
                    old_backup.unlink()
                    # Also remove metadata file if it exists
                    meta_file = old_backup.with_suffix('.json.meta')
                    if meta_file.exists():
                        meta_file.unlink()
                    print(f"[COMPREHENSIVE BACKUP] Removed old backup: {old_backup.name}")
                except Exception as e:
                    print(f"[COMPREHENSIVE BACKUP] Error removing old backup {old_backup}: {e}")

        except Exception as e:
            print(f"[COMPREHENSIVE BACKUP] Error during cleanup: {e}")

    def restore_comprehensive_backup_method(self, backup_path):
        """Restore from a comprehensive backup (wrapper for the method)"""
        return self.restore_comprehensive_backup(backup_path)

if __name__ == "__main__":
    app = QApplication([])
    window = CommandEditor()
    window.show()
    app.exec_()  # Note: в PyQt5 используется exec_() вместо exec()
