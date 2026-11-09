# -*- coding: utf-8 -*-
"""The classic Commands tab of the main window (mixin of CommandEditor).

Builds the tab (search, the table over CommandsTableModel, buttons, the
Command Details panel) and handles the panel's fields. Moved out of
command_editor.py unchanged (step 4.3); it works on the window's own
attributes, which the themed views and the checks use.

Python 3.8 / PyQt5.
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableView,
                             QAbstractItemView, QLabel, QLineEdit, QSpinBox, QComboBox, QCheckBox,
                             QFileDialog, QMessageBox, QSlider, QGroupBox, QHeaderView, QTextEdit)
from PyQt5.QtCore import Qt
from core.commands import FIELDS as COMMAND_FIELDS
from ui.commands_model import CommandsTableModel, display_text


class ClassicCommandsMixin(object):
    def _build_commands_tab(self):
        """The classic Commands tab: search, table, buttons, details panel."""
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
        return main_tab

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

    def add_command(self):
        """Add a new command (defaults from core.commands)."""
        row = self.command_repo.add({"Command": "!new"})
        self.original_commands.append(dict(self.commands[row]))
        self.filter_commands()
        self.table.selectRow(row)
        self.refresh_themed_commands()
        self.save_commands()  # раньше новая команда не сохранялась до первой правки

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

    def set_editing_enabled(self, enabled):
        """Enable or disable command editing buttons"""
        self.add_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)
        # Also disable the table if editing is disabled
        self.table.setEnabled(enabled)
