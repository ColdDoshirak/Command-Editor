import json
import os
import configparser
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                           QLabel, QLineEdit, QSpinBox, QComboBox, QCheckBox,
                           QFileDialog, QMessageBox, QSlider, QGroupBox, QTabWidget,
                           QDialog, QHeaderView)
from PyQt6.QtCore import Qt, QTimer
import pygame
from twitch_bot import TwitchBot
from twitch_auth import TwitchAuthDialog
from twitch_tab import TwitchTab
from config_manager import ConfigManager
from about_tab import AboutTab
from pathlib import Path
import threading

class CommandEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Command Editor")
        self.setGeometry(100, 100, 1200, 800)
        
        # Initialize commands list
        self.commands = []
        
        # Initialize config manager
        self.config_manager = ConfigManager()
        
        # Create tab widget as the main container
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)
        
        # Create main tab for commands
        main_tab = QWidget()
        main_layout = QVBoxLayout()
        
        # Create table
        self.table = QTableWidget()
        self.table.setColumnCount(14)
        self.table.setHorizontalHeaderLabels([
            "Command", "Permission", "Info", "Group", "Response",
            "Cooldown", "UserCooldown", "Cost", "Count", "Usage",
            "Enabled", "SoundFile", "FKSoundFile", "Volume"
        ])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self.table_item_changed)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self.on_command_selected)
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
        right_column.addWidget(self.sound_file_edit)
        right_column.addWidget(self.sound_file_btn)
        right_column.addWidget(QLabel("FK Sound File:"))
        right_column.addWidget(self.fk_sound_file_edit)
        right_column.addWidget(self.fk_sound_file_btn)
        
        # Add volume control
        volume_layout = QHBoxLayout()
        volume_label = QLabel("Volume:")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.valueChanged.connect(self.update_volume)
        volume_layout.addWidget(volume_label)
        volume_layout.addWidget(self.volume_slider)
        right_column.addLayout(volume_layout)
        
        # Add auto-save controls
        auto_save_group = QGroupBox("Auto-Save")
        auto_save_layout = QHBoxLayout()
        
        self.auto_save_checkbox = QCheckBox("Enable Auto-Save")
        self.auto_save_interval_input = QSpinBox()
        self.auto_save_interval_input.setMinimum(60)
        self.auto_save_interval_input.setMaximum(3600)
        self.auto_save_interval_input.setSingleStep(60)
        self.auto_save_interval_input.setSuffix(" seconds")
        
        auto_save_layout.addWidget(self.auto_save_checkbox)
        auto_save_layout.addWidget(QLabel("Interval:"))
        auto_save_layout.addWidget(self.auto_save_interval_input)
        
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
        
        # Add tabs to tab widget
        self.tab_widget.addTab(main_tab, "Commands")
        self.twitch_tab = TwitchTab(parent=self, commands_data=self.commands)
        self.tab_widget.addTab(self.twitch_tab, "Twitch")
        self.about_tab = AboutTab(parent=self)
        self.tab_widget.addTab(self.about_tab, "About")
        
        # Load saved commands and configuration
        self.load_saved_data()
        
        # Set up auto-save timer
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self.auto_save)
        auto_save_config = self.config_manager.get_auto_save()
        if auto_save_config['enabled']:
            self.auto_save_timer.start(auto_save_config['interval'] * 1000)
        
        # Initialize pygame mixer for sound playback
        pygame.mixer.init()
        
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
        
    def show_auth_dialog(self):
        dialog = TwitchAuthDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
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
        """Update volume for the selected command"""
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            if row < len(self.commands):
                # Update command data
                self.commands[row]["Volume"] = value
                
                # Update volume in table
                volume_item = QTableWidgetItem(str(value))
                self.table.setItem(row, 13, volume_item)
                
                # Save changes
                self.save_commands()
                
                # Update volume in Twitch bot if it exists
                if hasattr(self, 'twitch_tab') and self.twitch_tab.bot:
                    self.twitch_tab.bot.update_commands(self.commands)
                    
    def auto_assign_sounds(self):
        """Auto-assign sound files to commands based on filename matching"""
        # Ask user to select the sounds directory
        sound_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Sounds Directory",
            "",
            QFileDialog.Option.ShowDirsOnly
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

    def closeEvent(self, event):
        # Save current commands before closing
        if self.commands:
            self.config_manager.save_commands(self.commands)
            
        # Save volume setting
        self.config_manager.set_volume(self.volume)
        
        # Save auto-save settings
        self.config_manager.set_auto_save(
            self.auto_save_enabled,
            self.auto_save_interval
        )
        
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
            
        # Save to the separate commands file
        if self.config_manager.save_commands(self.commands):
            QMessageBox.information(self, "Success", "Commands saved successfully!")
        else:
            QMessageBox.warning(self, "Error", "Failed to save commands!")
                
    def add_command(self):
        """Add a new command"""
        new_command = {
            "Command": "!new_command",
            "SoundFile": "",
            "Enabled": True,
            "Permission": "Everyone",
            "Response": "",
            "Info": "",
            "Group": "GENERAL",
            "Cooldown": 0,
            "UserCooldown": 0,
            "Cost": 0,
            "Count": 0,
            "Usage": "SC",
            "FKSoundFile": "",
            "Volume": 100
        }
        
        # Add to commands list
        self.commands.append(new_command)
        
        # Add new row to table
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # Set items for new row
        self.table.setItem(row, 0, QTableWidgetItem(new_command["Command"]))
        self.table.setItem(row, 1, QTableWidgetItem(new_command["Permission"]))
        self.table.setItem(row, 2, QTableWidgetItem(new_command["Info"]))
        self.table.setItem(row, 3, QTableWidgetItem(new_command["Group"]))
        self.table.setItem(row, 4, QTableWidgetItem(new_command["Response"]))
        self.table.setItem(row, 5, QTableWidgetItem(str(new_command["Cooldown"])))
        self.table.setItem(row, 6, QTableWidgetItem(str(new_command["UserCooldown"])))
        self.table.setItem(row, 7, QTableWidgetItem(str(new_command["Cost"])))
        self.table.setItem(row, 8, QTableWidgetItem(str(new_command["Count"])))
        self.table.setItem(row, 9, QTableWidgetItem(new_command["Usage"]))
        self.table.setItem(row, 10, QTableWidgetItem("✓"))  # Enabled column
        self.table.setItem(row, 11, QTableWidgetItem(new_command["SoundFile"]))
        self.table.setItem(row, 12, QTableWidgetItem(new_command["FKSoundFile"]))
        self.table.setItem(row, 13, QTableWidgetItem(str(new_command["Volume"])))
        
        # Save only the new command
        self.save_commands()
        
    def delete_command(self):
        current_row = self.table.currentRow()
        if current_row >= 0 and current_row < len(self.commands):
            # Remove from commands list
            self.commands.pop(current_row)
            
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
                # Initialize bot with proper event loop
                self.bot = TwitchBot(channel)
                self.bot.update_commands(self.commands)
                self.bot.set_volume(self.volume_slider.value() / 100.0)
                
                # Start bot in a separate thread
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
        # Update commands in both main tab and Twitch tab
        self.commands = self.get_commands_from_ui()
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
            # Save commands
            if self.commands:
                self.config_manager.save_commands(self.commands)
                print("Auto-saved commands")
            
            # Save volume setting
            self.config_manager.set_volume(self.volume)
            
            # Save auto-save settings
            self.config_manager.set_auto_save(
                self.auto_save_enabled,
                self.auto_save_interval
            )
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
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(command.get("Volume", 100))
            self.volume_slider.blockSignals(False)
            
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
        self.update_command_field(state == Qt.CheckState.Checked, 10)  # Corrected column index
        
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

    def set_editing_enabled(self, enabled):
        """Enable or disable command editing buttons"""
        self.add_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)
        # Also disable the table if editing is disabled
        self.table.setEnabled(enabled)

if __name__ == "__main__":
    app = QApplication([])
    window = CommandEditor()
    window.show()
    app.exec()