import json
import os
import configparser
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QCheckBox,
                             QFileDialog, QMessageBox, QTabWidget, QDialog)
from PyQt5.QtCore import Qt, QTimer, QMetaType
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
from core.app_log import setup_logging, install_print_bridge
from core import paths
from core.commands import CommandRepository
from ui.backups_tab import HistoryTab, FullBackupsTab
from ui.timers_tab import TimersTab
from bot.audio import SoundCache, SoundPreview, ensure_channels, PREVIEW_CHANNEL
from ui.update_notification import UpdateNotificationWidget
from ui.theme_switch import ThemeSwitchMixin
from ui.classic_commands import ClassicCommandsMixin
from ui.hotkeys import GlobalHotkeys, ACTIONS as HOTKEY_ACTIONS, DEFAULTS as HOTKEY_DEFAULTS
from core.overlay import OverlayServer, snapshot_from_bot, RECENT_MAX as OVERLAY_RECENT
from core.overlay_page import PAGE as OVERLAY_PAGE

# регистрируем QTextCursor для передачи в сигналах
QMetaType.type("QTextCursor")

class CommandEditor(ClassicCommandsMixin, ThemeSwitchMixin, QMainWindow):
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
        
        main_tab = self._build_commands_tab()
        
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

        # таймеры (2.0): сообщения бота в чат по расписанию
        self.timers_tab = TimersTab(self)
        self.tab_widget.addTab(self.timers_tab, "Timers")
        
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
        
        # глобальные горячие клавиши (ui/hotkeys.py): работают и в свёрнутом окне
        self.hotkeys = GlobalHotkeys(self)
        self.hotkeys.triggered.connect(self._on_hotkey)
        self.hotkey_problems = self.hotkeys.apply(self.hotkey_settings())

        # оверлей для OBS (core/overlay.py): своя нить, только 127.0.0.1
        self.overlay = OverlayServer(OVERLAY_PAGE)
        self._overlay_recent = []
        self.twitch_tab.bridge.command_ran_by.connect(self._on_command_ran_by)
        self._overlay_timer = QTimer(self)
        self._overlay_timer.setInterval(500)
        self._overlay_timer.timeout.connect(self._push_overlay)
        self.apply_overlay_settings()

        # Apply the selected UI theme (classic / sidebar / spreadsheet)
        self.apply_theme(self.theme)
        
        # Загруженные звуки: кэш с ограничением (bot/audio.py)
        self.loaded_sounds = SoundCache(limit=32)
        # Один канал для всех воспроизведений
        # свой канал предпросмотра: раньше это был общий канал 0 бота, и
        # Play Sound обрывал звук зрителя или упирался в него
        ensure_channels()
        self.sound_channel = pygame.mixer.Channel(PREVIEW_CHANNEL)
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

    # -- global hotkeys -----------------------------------------------------------
    _HOTKEY_BOT = {"skip": "hotkey_skip", "pause": "hotkey_toggle_pause", "stop": "hotkey_stop_all"}

    def hotkey_settings(self):
        settings = dict(HOTKEY_DEFAULTS)
        settings.update(self.config_manager.get_hotkeys())
        return settings

    def set_hotkey_settings(self, settings):
        """Save and re-register. Returns {action: problem}."""
        self.config_manager.set_hotkeys(settings)
        self.hotkey_problems = self.hotkeys.apply(self.hotkey_settings())
        return self.hotkey_problems

    def _on_hotkey(self, name):
        """A global hotkey was pressed (UI thread): the action runs in the bot
        loop; without a bot, Skip / Stop at least silence the editor."""
        label = dict((n, l) for n, l, _d in HOTKEY_ACTIONS).get(name, name)
        sent = self.twitch_tab.bridge.call(self._HOTKEY_BOT.get(name, ""))
        if not sent and name in ("skip", "stop"):
            self.preview.stop()
            pygame.mixer.stop()
        self.twitch_tab.add_to_chat_safe(f"[Hotkey] {label}")

    # -- OBS overlay ------------------------------------------------------------------
    def overlay_settings(self):
        return self.config_manager.get_overlay()

    def apply_overlay_settings(self, settings=None):
        """Save (if given) and start / stop the overlay. Returns its URL, or
        None (off, or the port is taken: self.overlay.error)."""
        if settings is not None:
            self.config_manager.set_overlay(settings)
        s = self.overlay_settings()
        self.overlay.stop()
        self._overlay_timer.stop()
        if not s.get("enabled"):
            return None
        if not self.overlay.start(int(s.get("port", 8765) or 8765)):
            return None
        self._push_overlay()
        self._overlay_timer.start()
        return self.overlay_url()

    def overlay_url(self):
        return "http://127.0.0.1:%d/" % self.overlay.port if self.overlay.running() else ""

    def _on_command_ran_by(self, command, user):
        self._overlay_recent.append({"command": command, "user": user})
        del self._overlay_recent[:-OVERLAY_RECENT]

    def _push_overlay(self):
        self.overlay.update(snapshot_from_bot(self.twitch_tab.bot, self._overlay_recent))

    def closeEvent(self, event):
        try:
            self.hotkeys.clear()
            self.overlay.stop()
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

                # A history backup only when the commands changed since the
                # newest one (identical copies pushed real versions out)
                backup_successful = self.history_manager.save_backup_if_changed(self.commands)
                if backup_successful:
                    print("Auto-save command backup created")
                    self.history_tab.refresh()
                elif backup_successful is None:
                    print("Commands unchanged since the last backup - no new history backup")
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
        "Timers": ("timers_tab", "Timers", "chat messages", 11),
    }

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

    # Одна программа на одну папку данных: две копии над одними файлами
    # перезаписывают сохранения друг друга.
    from ui.single_instance import acquire
    _instance_lock = acquire(paths.app_dir())
    if _instance_lock is None:
        QMessageBox.warning(
            None, "Command Editor is already running",
            "Command Editor is already running with this data folder:\n%s\n\n"
            "Use the window that is already open." % paths.app_dir())
        sys.exit(1)

    # Create and show the main window
    window = CommandEditor()
    window.show()
    
    # Start the event loop
    sys.exit(app.exec_())
