import json
import os
import configparser
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QTableView, QAbstractItemView,
                             QLabel, QLineEdit, QSpinBox, QComboBox, QCheckBox,
                             QFileDialog, QMessageBox, QSlider, QGroupBox, QTabWidget,
                             QDialog, QHeaderView, QTextEdit)
from PyQt5.QtCore import Qt, QTimer, QDateTime, QMetaType
import pygame
from ui.twitch_auth import TwitchAuthDialog
from ui.twitch_tab import TwitchTab
from core.config_manager import ConfigManager
from ui.about_tab import AboutTab
from core.history_manager import HistoryManager
from pathlib import Path
import time
from ui.currency_tab import CurrencyTab
from ui.user_currency_tab import UserCurrencyTab
from ui.ranks_tab import RanksTab
from ui.sys_commands_tab import SysCommandsTab
from ui.group_settings_tab import GroupSettingsTab
from ui.queue_control_tab import QueueControlTab  # Live queue management tab
from core.currency_manager import CurrencyManager
import webbrowser
from ui import theme as _theme
from core.app_log import setup_logging, install_print_bridge
from core import paths
from core.commands import CommandRepository, FIELDS as COMMAND_FIELDS
from ui.commands_model import CommandsTableModel, display_text
from ui.backups_tab import HistoryTab, FullBackupsTab
from bot.audio import SoundCache, SoundPreview

# регистрируем QTextCursor для передачи в сигналах
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
        
        # Старые версии писали часть данных в текущую рабочую папку.
        # Копируем недостающее рядом с программой ДО чтения конфигов
        # (только копирование, ничего не перезаписывается и не удаляется).
        try:
            migrated = paths.migrate_from_cwd()
        except Exception as _e:
            migrated = []
            print("Data migration from working directory failed: %s" % _e)

        # Initialize config manager
        self.config_manager = ConfigManager()

        # Лог работы программы: command_editor.log рядом с config.json.
        # Перезаписывается при каждом запуске, ограничен по размеру,
        # токены/секреты маскируются (app_log._SensitiveDataFilter).
        try:
            setup_logging(self.config_manager.program_dir)
            install_print_bridge()
        except Exception as _e:
            print("Logging setup failed (continuing without logs): %s" % _e)
        for _src, _dst in migrated:
            print("Migrated %s -> %s" % (_src, _dst))
        
        # Theme state (classic / sidebar / spreadsheet)
        self.theme = self.config_manager.get_theme()
        self.themed_commands_view = None
        self.themed_twitch_view = None
        self.themed_tab_views = {}
        
        # Load settings BEFORE creating widgets
        self.allow_sound_interruption = self.config_manager.get_sound_interruption()
        self.show_interruption_message = self.config_manager.get_interruption_message()
        
        # Команды: единственный владелец - CommandRepository (этап 2).
        # self.commands - тот же объект списка, его identity не меняется.
        self.command_repo = CommandRepository(paths.commands_file())
        self.commands = self.command_repo.items

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
        # Central container: optional left nav rail (sidebar theme) + tab widget
        self._central = QWidget()
        self._central_layout = QHBoxLayout(self._central)
        self._central_layout.setContentsMargins(0, 0, 0, 0)
        self._central_layout.setSpacing(0)
        self.sidebar_nav = None
        self._central_layout.addWidget(self.tab_widget, 1)
        self.setCentralWidget(self._central)
        
        # Create main tab for commands
        main_tab = QWidget()
        self.main_tab = main_tab
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
        
        # Классическая таблица - вид над CommandRepository (шаг 4.4): своей
        # копии команд у неё нет, правка ячейки идёт в репозиторий.
        self.commands_model = CommandsTableModel(self.command_repo, self)
        self.commands_model.edited.connect(self._on_cell_edited)
        self.table = QTableView()
        self.table.setModel(self.commands_model)
        # после загрузки/добавления/удаления модель сбрасывается - и скрытые
        # поиском строки тоже: фильтр заново. Подключать после setModel:
        # таблица сама сбрасывает скрытые строки в своём обработчике.
        self.commands_model.modelReset.connect(self.filter_commands)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self.on_command_selected())
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

        self.fix_paths_btn = QPushButton("Fix Sound Paths")
        self.fix_paths_btn.setToolTip("Sound folder moved? Find the files again and update all commands")
        self.fix_paths_btn.clicked.connect(self.fix_sound_paths)
        buttons_layout.addWidget(self.fix_paths_btn)

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
        self.response_edit = QTextEdit()
        self.response_edit.setMaximumHeight(80)  # Ограничиваем высоту для компактности
        self.response_edit.setPlaceholderText("Введите текст ответа...\nShift+Enter - новая строка\nEnter - сохранить изменения")
        self.response_edit.textChanged.connect(self.on_response_changed)
        
        # Устанавливаем обработчик клавиш для поддержки Shift+Enter
        self.response_edit.keyPressEvent = self.response_key_press_event
        
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
        self.volume_slider.sliderReleased.connect(self.save_commands)

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

        # S12: поля панели сохраняют правки (раньше были только для показа).
        # Текстовые - по окончании ввода, остальные - сразу.
        for spin in (self.cooldown_spin, self.user_cooldown_spin, self.cost_spin, self.count_spin):
            spin.setRange(0, 1000000)  # QSpinBox по умолчанию ограничен 99
        self.command_edit.editingFinished.connect(
            lambda: self.update_command_field(self.command_edit.text(), 0))
        self.permission_combo.currentTextChanged.connect(self.on_permission_changed)
        self.info_edit.editingFinished.connect(
            lambda: self.update_command_field(self.info_edit.text(), 2))
        self.group_edit.editingFinished.connect(
            lambda: self.update_command_field(self.group_edit.text(), 3))
        self.cooldown_spin.valueChanged.connect(self.on_cooldown_changed)
        self.user_cooldown_spin.valueChanged.connect(self.on_user_cooldown_changed)
        self.cost_spin.valueChanged.connect(self.on_cost_changed)
        self.count_spin.valueChanged.connect(self.on_count_changed)
        self.usage_combo.currentTextChanged.connect(self.on_usage_changed)
        self.enabled_check.stateChanged.connect(self.on_enabled_changed)
        self.sound_file_edit.editingFinished.connect(
            lambda: self.update_command_field(self.sound_file_edit.text(), 11))
        self.fk_sound_file_edit.editingFinished.connect(
            lambda: self.update_command_field(self.fk_sound_file_edit.text(), 12))
        main_layout.addWidget(details_group)
        
        # Set main tab layout
        main_tab.setLayout(main_layout)
        
        # Initialize history manager BEFORE creating history tab
        self.history_manager = HistoryManager(max_backups=self.config_manager.get_max_backups())
        
        # Add tabs to tab widget
        self.tab_widget.addTab(main_tab, "Commands")

        # Add system commands tab right after Commands
        self.sys_commands_tab = SysCommandsTab(parent=self)
        self.tab_widget.addTab(self.sys_commands_tab, "Sys.Commands")

        self.twitch_tab = TwitchTab(parent=self, commands_data=self.commands, config_manager=self.config_manager)
        self.tab_widget.addTab(self.twitch_tab, "Twitch")


        # Add tabs for currency management
        self.currency_manager = CurrencyManager(config_manager=self.config_manager)
        if hasattr(self.currency_manager, 'load_settings'):
            self.currency_manager.load_settings() # Загружаем настройки при запуске
            print("Currency settings loaded in CommandEditor")

        self.currency_tab = CurrencyTab(parent=self)
        self.tab_widget.addTab(self.currency_tab, "Currency Settings")
        self.user_currency_tab = UserCurrencyTab(parent=self)
        self.tab_widget.addTab(self.user_currency_tab, "Currency Users")
        self.ranks_tab = RanksTab(parent=self)
        self.tab_widget.addTab(self.ranks_tab, "Ranks")
        self.ranks_tab.load_ranks()

        # Add Group Settings tab
        self.group_settings_tab = GroupSettingsTab(parent=self)
        self.tab_widget.addTab(self.group_settings_tab, "Group Settings")

        # Add Queue Control tab (live queue management)
        self.queue_control_tab = QueueControlTab(parent=self)
        self.tab_widget.addTab(self.queue_control_tab, "Queue Control")

        self.about_tab = AboutTab(parent=self)
        self.tab_widget.addTab(self.about_tab, "About")
        self.history_tab = HistoryTab(self)
        self.tab_widget.addTab(self.history_tab, "History")
        
        # Connect tab change signal
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        # Create comprehensive backup tab
        self.backup_tab = FullBackupsTab(self)
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
        self.system_auto_backup_timer.timeout.connect(lambda: self.backup_tab.create_auto())

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
        
        # Apply the selected UI theme (classic / sidebar / spreadsheet)
        self.apply_theme(self.theme)
        
        # Загруженные звуки: кэш с ограничением (bot/audio.py)
        self.loaded_sounds = SoundCache(limit=32)
        # Один канал для всех воспроизведений
        self.sound_channel = pygame.mixer.Channel(0)
        # Кнопка Play Sound (bot/audio.SoundPreview); конец звука замечает
        # таймер в UI-потоке
        self.preview = SoundPreview(self.sound_channel, self.loaded_sounds)
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(100)
        self._preview_timer.timeout.connect(self._sync_preview_button)
        
        # Create update notification widget
        self.update_notification = UpdateNotificationWidget(self)
          # Auto-check for updates on startup (silent check)
        self.auto_check_updates()

        # Moved sound folder? Re-link from remembered folders / tell the user.
        QTimer.singleShot(1500, self._startup_sound_check)

    def _startup_sound_check(self):
        try:
            warn = self.config_manager.config.get('sound_check_on_start', True)
            self.auto_relink_sounds(quiet=not warn)
        except Exception as e:
            print(f"Sound path check failed: {e}")

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
            self.command_repo.load()  # заполняет недостающие поля (Enabled и т.д.)
        except Exception as e:
            print(f"Error loading commands: {e}")
            self.command_repo.replace_all([])
            
    def update_table(self):
        """Перерисовать классическую таблицу и тематические виды (после
        прямой правки словарей команд, мимо репозитория)."""
        self.commands_model.beginResetModel()
        self.commands_model.endResetModel()
        self.refresh_themed_commands()

    def refresh_table(self):
        self.update_table()

    def _selected_row(self):
        """Строка, выбранная в классической таблице, или -1."""
        sm = self.table.selectionModel()
        rows = sorted(set(i.row() for i in sm.selectedIndexes())) if sm is not None else []
        return rows[0] if rows else -1

    def _current_row(self):
        idx = self.table.currentIndex()
        return idx.row() if idx.isValid() else -1

    def response_key_press_event(self, event):
        """Обработка клавиш в поле Response для поддержки Shift+Enter"""
        if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
            # Enter без Shift - сохраняем изменения
            self.save_commands()
            return
        # В остальных случаях используем стандартную обработку
        QTextEdit.keyPressEvent(self.response_edit, event)
            
    def on_response_changed(self):
        """Обработка изменений в поле Response"""
        row = self._selected_row()
        if row >= 0:
            if row < len(self.commands) and not getattr(self, "_populating_details", False):
                if self.command_repo.update(row, {"Response": self.response_edit.toPlainText()}):
                    self.save_commands()
                    self.refresh_themed_commands()
            
                
    def update_details(self, current_row, current_col, previous_row, previous_col):
        if current_row >= 0 and current_row < len(self.commands):
            cmd = self.commands[current_row]
            self.command_edit.setText(cmd["Command"])
            self.permission_combo.setCurrentText(cmd["Permission"])
            self.info_edit.setText(cmd["Info"])
            self.group_edit.setText(cmd["Group"])
            self.response_edit.setPlainText(cmd["Response"])
            self.cooldown_spin.setValue(cmd["Cooldown"])
            self.user_cooldown_spin.setValue(cmd["UserCooldown"])
            self.cost_spin.setValue(cmd["Cost"])
            self.count_spin.setValue(cmd["Count"])
            self.usage_combo.setCurrentText(cmd["Usage"])
            self.enabled_check.setChecked(cmd["Enabled"])
            self.sound_file_edit.setText(cmd["SoundFile"])
            self.fk_sound_file_edit.setText(str(cmd["FKSoundFile"]))
            
    def _on_cell_edited(self, row, done):
        """Ячейка классической таблицы сохранена в репозиторий (модель):
        записать файл, передать боту, обновить виды. Недопустимое значение
        (буквы в Cost) модель не сохраняет - ячейка показывает прежнее."""
        try:
            self.save_commands()
            self.refresh_themed_commands()
            if "Group" in done and hasattr(self, "group_settings_tab"):
                self.group_settings_tab.refresh_groups()
        except Exception as e:
            print(f"Error updating command: {e}")

    def load_config(self):
        try:
            self.config.read(str(paths.legacy_ini_file()))
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
        with open(paths.legacy_ini_file(), 'w') as f:
            self.config.write(f)
            
    def update_volume(self, value):
        """Update volume setting"""
        self.volume = value / 100  # Convert to 0-1 range
        
        # Update the volume display label
        self.volume_value_label.setText(f"{value}%")
        
        # Громкость выбранной команды. Пока ползунок тянут - только в память,
        # на диск при отпускании (sliderReleased -> save_commands).
        row = self._selected_row()
        if row >= 0 and not getattr(self, "_populating_details", False):
            if row < len(self.commands):
                if self.command_repo.update(row, {"Volume": value}) and \
                        not self.volume_slider.isSliderDown():
                    self.save_commands()
                    
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
        changes = {}
        for i, cmd in enumerate(self.commands):
            command = cmd.get("Command", "")
            match = sound_dict.get(command) or sound_dict.get(command.lstrip('!'))
            if match:
                changes[i] = {"SoundFile": match, "Enabled": True}
        updated = bool(self.command_repo.update_many(changes)) if changes else False

        if updated:
            self.save_commands()  # Save changes
            self.refresh_themed_commands()
            QMessageBox.information(self, "Success", "Sound files assigned automatically!")
        else:
            QMessageBox.information(self, "Info", "No new sound files to assign.")

    def play_or_stop_sound(self):
        """Play Sound / Stop Sound для выбранной команды.

        Раньше конец звука ждал отдельный поток и сам менял текст кнопки -
        виджет Qt из чужого потока (тот же класс багов, что C4)."""
        row = self._selected_row()
        if not self.preview.is_playing() and not (0 <= row < len(self.commands)):
            QMessageBox.warning(self, "Warning", "No command selected.")
            return
        cmd = self.commands[row] if 0 <= row < len(self.commands) else {}
        fn = cmd.get("SoundFile", "")
        state = self.preview.toggle(fn, cmd.get("Volume", 100), self.allow_sound_interruption)
        if state == "missing":
            QMessageBox.warning(self, "Warning", f"Sound file not found: {fn}")
        elif state == "blocked" and self.show_interruption_message:
            QMessageBox.information(self, "Info", "Interruption disabled.")
        if state == "playing":
            self._preview_timer.start()
        self._sync_preview_button()

    def _sync_preview_button(self):
        playing = self.preview.is_playing()
        self.play_sound_btn.setText("Stop Sound" if playing else "Play Sound")
        if not playing:
            self._preview_timer.stop()

    def closeEvent(self, event):
        try:
            # First, stop any playing sounds
            if pygame.mixer.get_busy():
                pygame.mixer.stop()
            
            # Disconnect any running Twitch bot
            if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
                print("Stopping Twitch bot before closing…")
                self.twitch_tab.disconnect()
                time.sleep(0.2)

            # Команды сохраняются ровно в том виде и порядке, что на экране.
            # Раньше здесь была "дедупликация" по имени: вторая команда с
            # тем же именем молча удалялась при выходе (C5).

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
                    converted = []
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
                        converted.append(new_cmd)

                    self.replace_commands(converted)

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
                self.history_tab.refresh()
                QMessageBox.information(self, "Success", "Commands saved and backup created successfully!")
            else:
                QMessageBox.information(self, "Success", "Commands saved successfully, but backup creation failed.")
        else:
            QMessageBox.warning(self, "Error", "Failed to save commands!")
                
    def add_command(self):
        """Add a new command (defaults from core.commands)."""
        row = self.command_repo.add({"Command": "!new"})
        self.original_commands.append(dict(self.commands[row]))
        self.filter_commands()
        self.table.selectRow(row)
        self.refresh_themed_commands()
        self.save_commands()  # раньше новая команда не сохранялась до первой правки

    def check_command_cost(self, username, command_cost):
        """Check if the user has enough currency to execute the command"""
        if command_cost <= 0:
            return True
        return self.currency_manager.pay_for_command(username, command_cost)

    def delete_command(self):
        current_row = self._current_row()
        if current_row >= 0 and current_row < len(self.commands):
            cmd_to_delete = self.command_repo.remove(current_row)
            # Remove from original commands list (find by Command name)
            for i, cmd in enumerate(self.original_commands):
                if cmd["Command"] == cmd_to_delete["Command"]:
                    self.original_commands.pop(i)
                    break
            self.refresh_themed_commands()
            self.save_commands()

    def browse_file(self, line_edit):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Sound File", "", "Sound Files (*.mp3 *.wav *.ogg)")
        if file_name:
            line_edit.setText(file_name)
            # setText не даёт editingFinished: сохраняем явно (S12)
            column = 11 if line_edit is self.sound_file_edit else 12
            self.update_command_field(file_name, column)

    def update_commands(self):
        """Update commands in Twitch tab"""
        # Бот получает копии (снимок), а не словари редактора (шаг 2.3)
        if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
            self.twitch_tab.push_commands(self.command_repo.snapshot())

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
        # Load commands from the commands file (fills the table via the listener)
        try:
            self.command_repo.load()
        except Exception as e:
            print(f"Error loading commands: {e}")

        # Load the last used file if specified in config
        current_file = self.config_manager.get_current_file()
        if current_file and os.path.exists(current_file):
            try:
                self.command_repo.load(current_file)
                self.command_repo.save()  # into the separate commands file
            except Exception as e:
                print(f"Error loading last used file: {e}")

        # Store the original order of commands
        self.original_commands = self.commands.copy()

        # Update commands in Twitch tab if it exists
        if hasattr(self, 'twitch_tab'):
            self.twitch_tab.commands_data = self.commands
        self.update_commands()

    def auto_save(self):
        """Automatically save commands and configuration"""
        try:
            print("Running auto-save...")

            # Save commands
            if self.commands:
                # Save the commands first
                print("Saving commands...")
                self.command_repo.save()

                # Always create backup on auto-save, don't check for significant changes
                print("Creating command backup during auto-save...")
                backup_successful = self.history_manager.save_backup(self.commands)

                if backup_successful:
                    print("Auto-save command backup created successfully")
                    self.history_tab.refresh()
                    print("Command backup list refreshed")
                else:
                    print("Failed to create auto-save command backup")

                # Create comprehensive system backup if enabled
                if self.system_auto_backup_enabled:
                    print("Creating comprehensive system backup during auto-save...")
                    system_backup_path = self.backup_tab.create()   # keeps the newest N
                    if system_backup_path:
                        print(f"Auto-save comprehensive backup created: {system_backup_path}")
                        self.backup_tab.refresh()
                    else:
                        print("Failed to create auto-save comprehensive backup")

                # Update commands in Twitch tab if it exists
                self.update_commands()

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
        """Handle command selection in the table.

        Заполнение полей панели не должно записывать их обратно (поля теперь
        подключены к сохранению, S12) - флаг _populating_details."""
        self._populating_details = True
        try:
            self._show_selected_details()
        finally:
            self._populating_details = False

    def _show_selected_details(self):
        row = self._selected_row()
        if row < 0:
            return

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

            # Keep the themed Commands view (sidebar detail) in sync
            if self.themed_commands_view is not None and hasattr(self.themed_commands_view, "select_from_table"):
                self.themed_commands_view.select_from_table(row)

    def update_command_field(self, value, column):
        """Поле панели Command Details -> репозиторий (S12: раньше эти поля
        не были подключены и правки в них терялись)."""
        if getattr(self, "_populating_details", False):
            return
        row = self._selected_row()
        if not (0 <= row < len(self.commands)) or not (0 <= column < len(COMMAND_FIELDS)):
            return
        key = COMMAND_FIELDS[column]
        if self.command_repo.update(row, {key: value}):
            self.save_commands()
            self.refresh_themed_commands()
            if key == "Group" and hasattr(self, 'group_settings_tab'):
                self.group_settings_tab.refresh_groups()

    def on_enabled_changed(self, state):
        self.update_command_field(state == Qt.Checked, 10)  # Corrected column index
        
    def on_permission_changed(self, text):
        self.update_command_field(text, 1)  # Corrected column index
        
        
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
        """Записать команды на диск и передать боту.

        Таблица больше НЕ читается: данные живут в CommandRepository, таблица
        и виды тем только показывают их (этап 2). Раньше здесь каждое
        сохранение переписывало словари из ячеек классической таблицы.
        """
        try:
            self.command_repo.save()
            self.update_commands()
        except Exception as e:
            print(f"Error saving commands: {e}")

    def replace_commands(self, new_commands):
        """Заменить все команды (загрузка файла, восстановление бэкапа).

        Список меняется на месте: тематические виды, вкладка Twitch и
        редактор держат один и тот же объект (S10). Таблица перестраивается
        ДО сохранения, потому что save_commands() читает её (S11).
        """
        self.command_repo.replace_all(new_commands)  # таблица и вид - через слушателя
        self.original_commands = self.commands.copy()
        self.filter_commands()
        if hasattr(self, 'twitch_tab'):
            self.twitch_tab.commands_data = self.commands
        self.save_commands()  # пишет файл и передаёт команды боту

    def apply_command_edit(self, row, changes):
        """Single entry point for edits made in the themed views.
        Values are coerced by the repository (Volume 0-100, ints >= 0)."""
        if not (0 <= row < len(self.commands)) or not changes:
            return
        done = self.command_repo.update(row, changes)
        if done:
            self.save_commands()  # writes commands.json + pushes to the bot
            if "Group" in done and hasattr(self, "group_settings_tab"):
                self.group_settings_tab.refresh_groups()

    def apply_bulk_command_edits(self, changes_by_row):
        """Apply {row: {key: value}} in one go (one save, one bot push).
        Returns the number of changed fields."""
        before = dict((r, dict(self.commands[r])) for r in changes_by_row
                      if 0 <= r < len(self.commands))
        rows = self.command_repo.update_many(changes_by_row)
        n = sum(1 for r in rows for k in changes_by_row[r]
                if self.commands[r].get(k) != before[r].get(k))
        if rows:
            self.save_commands()
            try:
                if self._current_row() in rows:
                    self.on_command_selected()
            except Exception:
                pass
            self.refresh_themed_commands()
        return n

    def fix_sound_paths(self):
        """Open the "Fix sound paths" dialog (moved / renamed sound folders)."""
        from ui.sound_relink import make_relink_dialog
        dlg = make_relink_dialog(self)
        dlg.exec_()

    def auto_relink_sounds(self, quiet=False):
        """Re-link missing sounds from folders remembered by the fixer.

        Only unambiguous matches are applied. Returns (fixed, still_missing).
        """
        from core import sound_paths
        folders = self.config_manager.get_sound_folders()
        missing = sound_paths.find_missing(self.commands)
        if not missing:
            return 0, 0
        fixed = 0
        if folders:
            plan = sound_paths.plan_from_folders(self.commands, folders)
            plan = [p for p in plan if p["new"] and not p["ambiguous"]]
            fixed = self.apply_bulk_command_edits(sound_paths.plan_to_changes(plan))
        still = len(sound_paths.find_missing(self.commands))
        if not quiet and (fixed or still):
            box = QMessageBox(self)
            box.setWindowTitle("Sound files")
            lines = []
            if fixed:
                lines.append("%d moved sound file(s) were found and re-linked automatically." % fixed)
            if still:
                lines.append("%d sound file(s) are missing (moved or renamed folder?)." % still)
            box.setText("\n".join(lines))
            fix_btn = None
            if still:
                fix_btn = box.addButton("Fix sound paths…", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Close)
            mute = QCheckBox("Don't warn about missing sounds on start-up")
            box.setCheckBox(mute)
            box.exec_()
            if mute.isChecked():
                self.config_manager.config['sound_check_on_start'] = False
                self.config_manager.save_config()
            if fix_btn is not None and box.clickedButton() is fix_btn:
                self.fix_sound_paths()
        return fixed, still

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
            self.twitch_tab.push_interruption(self.allow_sound_interruption)
            self.twitch_tab.add_to_chat_safe(
                f"Sound interruption setting changed: {'Enabled' if self.allow_sound_interruption else 'Disabled'}"
            )

    def on_show_message_toggle(self, state):
        """Handle show message toggle change"""
        self.show_interruption_message = (state == Qt.Checked)
        self.config_manager.set_interruption_message(self.show_interruption_message)
        
        # Update the setting in Twitch bot if it exists
        if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
            self.twitch_tab.push_show_interruption_message(self.show_interruption_message)
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

    def filter_commands(self):
        """Filter displayed commands based on search text"""
        search_text = self.search_input.text().lower()
        
        # Show all commands if search is empty
        if not search_text:
            for row in range(self.commands_model.rowCount()):
                self.table.setRowHidden(row, False)
            return

        # Hide rows that don't match the search (any column, as shown)
        for row, cmd in enumerate(self.commands):
            match_found = any(search_text in display_text(cmd, key).lower()
                              for key in COMMAND_FIELDS)
            self.table.setRowHidden(row, not match_found)
        self.refresh_themed_commands()

    def handle_no_users_data(self, users_data):
        if not users_data:
            print("No currency users data available")
            # Обновить метку времени последнего обновления
            now = QDateTime.currentDateTime().toString("HH:mm:ss")
            self.last_update.setText(f"Last update: {now}")
            return

    def resizeEvent(self, event):
        """Handle window resize and update notification position"""
        super().resizeEvent(event)
        if hasattr(self, 'update_notification') and self.update_notification.isVisible():
            self.update_notification.update_position()

    def on_tab_changed(self, index):
        """Handle tab changes to refresh data if needed"""
        current_widget = self.tab_widget.widget(index)
        # In themed layouts the tab is wrapped in a ThemedTabView, so compare
        # against the wrapped widget too (the refresh never ran there and the
        # Group Settings table stayed empty).
        inner = getattr(current_widget, "original_tab", current_widget)
        if hasattr(self, 'group_settings_tab') and inner is self.group_settings_tab:
            self.group_settings_tab.refresh_groups()
        if hasattr(self, 'queue_control_tab') and inner is self.queue_control_tab:
            self.queue_control_tab.refresh_groups()
        # Keep the sidebar nav highlight in sync
        if self.sidebar_nav is not None and self.sidebar_nav.isVisible():
            self.sidebar_nav.highlight_tab(index)

    # ------------------------------------------------------------------
    # Theme switching
    # ------------------------------------------------------------------
    def apply_theme(self, theme_name):
        """Apply a UI theme: classic (native), sidebar, or spreadsheet."""
        if theme_name not in _theme.THEMES:
            theme_name = "classic"
        self.theme = theme_name
        self.config_manager.set_theme(theme_name)

        # Запоминаем активную вкладку: rebuild-функции ниже сбрасывают
        # индекс (removeTab/insertTab + setCurrentIndex(0)), в конце
        # apply_theme вернём пользователя на его вкладку.
        current_index = self.tab_widget.currentIndex() if self.tab_widget is not None else 0

        layout = _theme.layout_of(theme_name)

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(_theme.qss_for(theme_name))

        # In the sidebar layout the left nav IS the navigation — hide the
        # top tab bar so it doesn't duplicate it (content stays visible).
        try:
            self.tab_widget.tabBar().setVisible(layout != "sidebar")
        except Exception:
            pass

        # Every theme has a Settings tab (classic also keeps the same settings
        # in the Commands tab; both drive the same widgets). Added before the
        # nav so its button is shown.
        self._update_settings_tab(True)
        self._update_sidebar(theme_name)
        self._update_now_playing_bar(theme_name)

        # Fit all 11 tabs into the bar (avoid clipped labels)
        try:
            self.tab_widget.setUsesScrollButtons(True)
            if theme_name != "classic":
                self.tab_widget.tabBar().setElideMode(Qt.ElideRight)
            else:
                self.tab_widget.tabBar().setElideMode(Qt.ElideNone)
        except Exception:
            pass

        self._rebuild_commands_view()
        self._rebuild_twitch_view()
        self._rebuild_generic_tab_views()

        # Вернуть пользователя на ту вкладку, где он был (rebuild-функции
        # делают removeTab/insertTab и setCurrentIndex(0), сбивая выбор —
        # при смене темы из About логично остаться на About).
        try:
            if current_index >= self.tab_widget.count():
                current_index = 0
            self.tab_widget.setCurrentIndex(current_index)
            if self.sidebar_nav is not None:
                self.sidebar_nav.highlight_tab(current_index)
        except Exception:
            pass

        # Keep the About tab's theme combo in sync when switched elsewhere
        combo = getattr(getattr(self, "about_tab", None), "theme_combo", None)
        if combo is not None:
            i = combo.findData(theme_name)
            if i >= 0 and combo.currentIndex() != i:
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)

    def _update_sidebar(self, theme_name):
        """Show the persistent left nav rail in sidebar-layout themes, hide it
        otherwise. The rail is a sibling of the tab widget in the central
        container, so it stays visible on every tab. Rebuilt on every theme
        change so it picks up the new palette."""
        if self.sidebar_nav is not None:
            try:
                self.tab_widget.currentChanged.disconnect(self.sidebar_nav.highlight_tab)
            except (TypeError, RuntimeError):
                pass
            self.sidebar_nav.hide()
            self.sidebar_nav.setParent(None)
            self.sidebar_nav.deleteLater()
            self.sidebar_nav = None
        if _theme.layout_of(theme_name) == "sidebar":
            self.sidebar_nav = _theme.SidebarNav(
                self, self.tab_widget, _theme.palette_for(theme_name))
            self._central_layout.insertWidget(0, self.sidebar_nav, 0)
            self.sidebar_nav.show()
            self.sidebar_nav.highlight_tab(self.tab_widget.currentIndex())

    def _update_now_playing_bar(self, theme_name):
        """Persistent queue strip under the tabs (Midnight theme)."""
        bar = getattr(self, "now_playing_bar", None)
        if bar is not None:
            bar.setParent(None)
            bar.deleteLater()
            self.now_playing_bar = None
        if theme_name in _theme.NOW_PLAYING_THEMES:
            if not hasattr(self, "_content_column"):
                # Wrap the tab widget in a column so the bar sits below it.
                self._content_column = QWidget()
                col = QVBoxLayout(self._content_column)
                col.setContentsMargins(0, 0, 0, 0)
                col.setSpacing(0)
                idx = self._central_layout.indexOf(self.tab_widget)
                self._central_layout.removeWidget(self.tab_widget)
                col.addWidget(self.tab_widget, 1)
                self._central_layout.insertWidget(max(0, idx), self._content_column, 1)
            self.now_playing_bar = _theme.NowPlayingBar(self)
            self._content_column.layout().addWidget(self.now_playing_bar, 0)

    def _update_settings_tab(self, show):
        """Add (themed layouts) or remove (classic) the Settings tab. It is
        always the last tab so the fixed nav indices stay valid."""
        tab = getattr(self, "settings_tab", None)
        if tab is not None:
            idx = self.tab_widget.indexOf(tab)
            if idx >= 0:
                self.tab_widget.removeTab(idx)
            tab.setParent(None)
            tab.deleteLater()
            self.settings_tab = None
        if show:
            panel = _theme.SettingsPanel(self)
            if _theme.layout_of(self.theme) == "classic":
                # native look: no themed frame around it
                self.settings_tab = panel
            else:
                self.settings_tab = _theme.ThemedTabView(
                    self, self.tab_widget, panel,
                    "Settings", "sound · auto-save · appearance")
            self.tab_widget.addTab(self.settings_tab, "Settings")

    def set_theme(self, theme_name):
        """Public entry point for the theme switcher (About tab)."""
        self.apply_theme(theme_name)

    def _make_commands_view(self):
        """Build the themed Commands view for the current theme."""
        if _theme.layout_of(self.theme) == "sidebar":
            return _theme.SidebarCommandsView(
                self, self.main_tab, self.table, self.commands,
                self.search_input,
                on_add=self.add_command, on_remove=self.delete_command,
                on_load=self.load_file, on_save=self.save_file,
            )
        return _theme.SpreadsheetCommandsView(
            self, self.main_tab, self.table, self.commands,
            self.search_input,
            on_add=self.add_command, on_remove=self.delete_command,
            on_load=self.load_file, on_save=self.save_file,
        )

    def _rebuild_commands_view(self):
        """Swap the Commands tab content between classic and themed views."""
        tab_widget = self.tab_widget
        if tab_widget is None:
            return
        # The classic Commands tab is always index 0
        cmd_idx = 0

        if self.theme == "classic":
            # Restore the original classic Commands tab if it was replaced
            if self.themed_commands_view is not None:
                idx = tab_widget.indexOf(self.themed_commands_view)
                if idx >= 0:
                    tab_widget.removeTab(idx)
                self.themed_commands_view.setParent(None)
                self.themed_commands_view.deleteLater()
                self.themed_commands_view = None
            # main_tab was unparented when a theme was applied; restore it
            if tab_widget.indexOf(self.main_tab) < 0:
                tab_widget.insertTab(0, self.main_tab, "Commands")
            return

        # (Re)create the themed view, destroying any previous one
        first_apply = tab_widget.widget(cmd_idx) is self.main_tab
        if self.themed_commands_view is not None:
            idx = tab_widget.indexOf(self.themed_commands_view)
            if idx >= 0:
                tab_widget.removeTab(idx)
            self.themed_commands_view.setParent(None)
            self.themed_commands_view.deleteLater()
            self.themed_commands_view = None
        self.themed_commands_view = self._make_commands_view()
        # Insert the themed view at the Commands position
        if first_apply:
            # Classic tab still occupies index 0: remove it, insert themed view
            tab_widget.removeTab(cmd_idx)
            tab_widget.insertTab(cmd_idx, self.themed_commands_view, "Commands")
        else:
            # A themed view already occupied index 0 (now shifted): insert at 0
            tab_widget.insertTab(cmd_idx, self.themed_commands_view, "Commands")
        tab_widget.setCurrentIndex(cmd_idx)
        self.themed_commands_view.highlight_tab(cmd_idx)

    def refresh_themed_commands(self):
        """Refresh the themed Commands view after the data changed."""
        if self.themed_commands_view is not None:
            self.themed_commands_view.refresh()

    def _make_twitch_view(self):
        """Build the themed Twitch view for the current theme."""
        if _theme.layout_of(self.theme) == "sidebar":
            return _theme.SidebarTwitchView(self, self.tab_widget, self.twitch_tab)
        return _theme.SpreadsheetTwitchView(self, self.tab_widget, self.twitch_tab)

    def _rebuild_twitch_view(self):
        """Swap the Twitch tab content between classic and themed views.

        The themed view re-parents the original TwitchTab widgets into a new
        layout; switching back to classic restores the original layout via
        TwitchTab.restore_classic_layout().
        """
        tab_widget = self.tab_widget
        if tab_widget is None or not hasattr(self, "twitch_tab"):
            return
        tw_idx = tab_widget.indexOf(self.twitch_tab)
        if tw_idx < 0:
            tw_idx = 2  # Twitch is the 3rd tab (0-indexed)

        if self.theme == "classic":
            if self.themed_twitch_view is not None:
                idx = tab_widget.indexOf(self.themed_twitch_view)
                if idx >= 0:
                    tab_widget.removeTab(idx)
                self.themed_twitch_view.setParent(None)
                self.themed_twitch_view.deleteLater()
                self.themed_twitch_view = None
            if tab_widget.indexOf(self.twitch_tab) < 0:
                self.twitch_tab.restore_classic_layout()
                tab_widget.insertTab(tw_idx, self.twitch_tab, "Twitch")
            return

        # (Re)create the themed view, destroying any previous one
        first_apply = tab_widget.widget(tw_idx) is self.twitch_tab
        if self.themed_twitch_view is not None:
            idx = tab_widget.indexOf(self.themed_twitch_view)
            if idx >= 0:
                tab_widget.removeTab(idx)
            self.themed_twitch_view.setParent(None)
            self.themed_twitch_view.deleteLater()
            self.themed_twitch_view = None
        self.themed_twitch_view = self._make_twitch_view()
        if first_apply:
            tab_widget.removeTab(tw_idx)
            tab_widget.insertTab(tw_idx, self.themed_twitch_view, "Twitch")
        else:
            tab_widget.insertTab(tw_idx, self.themed_twitch_view, "Twitch")
        tab_widget.setCurrentIndex(tw_idx)
        self.themed_twitch_view.highlight_tab(tw_idx)

    # Tabs (besides Commands and Twitch) that get the generic themed frame.
    # name -> (attribute, title, subtitle, canonical_index)
    _GENERIC_TABS = {
        "Sys.Commands": ("sys_commands_tab", "Sys.Commands", "system commands", 1),
        "Currency Settings": ("currency_tab", "Currency Settings", "economy", 3),
        "Currency Users": ("user_currency_tab", "Currency Users", "economy", 4),
        "Ranks": ("ranks_tab", "Ranks", "stream ranks", 5),
        "Group Settings": ("group_settings_tab", "Group Settings", "audio queues", 6),
        "Queue Control": ("queue_control_tab", "Queue Control", "live queue", 7),
        "About": ("about_tab", "About", "info", 8),
        "History": ("history_tab", "History", "command log", 9),
        "Backups": ("backup_tab", "Backups", "safety", 10),
    }

    def _rebuild_generic_tab_views(self):
        """Wrap (or unwrap) the 9 generic tabs in a themed frame, preserving
        their positions in the tab bar."""
        tab_widget = self.tab_widget
        if tab_widget is None:
            return

        if self.theme == "classic":
            for name, view in list(self.themed_tab_views.items()):
                idx = tab_widget.indexOf(view)
                if idx >= 0:
                    tab_widget.removeTab(idx)
                view.setParent(None)
                view.deleteLater()
            self.themed_tab_views = {}
            # Re-insert the original tabs at their canonical positions
            for name, (attr, _t, _s, cidx) in self._GENERIC_TABS.items():
                orig = getattr(self, attr, None)
                if orig is None:
                    continue
                if tab_widget.indexOf(orig) < 0:
                    # drop the themed background the wrapper put on it
                    orig.setStyleSheet("")
                    tab_widget.insertTab(min(cidx, tab_widget.count()), orig, name)
            return

        for name, (attr, title, subtitle, _cidx) in self._GENERIC_TABS.items():
            orig = getattr(self, attr, None)
            if orig is None:
                continue
            existing = self.themed_tab_views.pop(name, None)
            idx = tab_widget.indexOf(orig)
            if idx < 0 and existing is not None:
                # Themed -> themed switch: the tab sits inside the previous
                # wrapper. Re-wrap it so it gets the new palette (it used to
                # keep the old theme's colours, e.g. white panels in Midnight).
                idx = tab_widget.indexOf(existing)
            if idx < 0:
                continue
            tab_widget.removeTab(idx)
            if existing is not None:
                orig.setParent(None)
                existing.setParent(None)
                existing.deleteLater()
            content = None
            if name == "Sys.Commands" and _theme.layout_of(self.theme) == "sidebar":
                # same master/detail editor as the themed Commands view
                content = _theme.SysCommandsView(self, orig)
            view = _theme.ThemedTabView(self, tab_widget, orig, title, subtitle, content=content)
            tab_widget.insertTab(idx, view, name)
            self.themed_tab_views[name] = view

if __name__ == "__main__":
    import sys
    from core import app_log
    # Журнал падений - до создания окна, чтобы ловить и ошибки запуска.
    try:
        app_log.install_crash_handlers(paths.app_dir())
    except Exception as _e:
        print("Crash log setup failed: %s" % _e)
    # Initialize the application
    app = QApplication(sys.argv)
    from ui.qt_log import install_qt_message_handler
    install_qt_message_handler()

    # Create and show the main window
    window = CommandEditor()
    window.show()
    
    # Start the event loop
    sys.exit(app.exec_())
