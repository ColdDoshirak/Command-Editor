from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
                           QGroupBox, QLabel, QLineEdit, QSpinBox, QComboBox,
                           QMenu, QMessageBox)
from PyQt5.QtCore import Qt
from core import permissions
from core.config_manager import ConfigManager
import copy
from core.system_commands import DEFAULT_SYSTEM_COMMANDS, merge_with_defaults
from ui.i18n import tr


class SysCommandsTab(QWidget):
    def __init__(self, parent=None, config_manager=None):
        super().__init__()
        self.parent = parent
        # Общий ConfigManager программы (шаг 1.2); свой - только без родителя.
        shared = config_manager if config_manager is not None else getattr(parent, "config_manager", None)
        self.config_manager = shared if shared is not None else ConfigManager()
        
        # Define original system commands with their default settings
        # Значения по умолчанию - в core.system_commands (нужны и боту без Qt)
        self.original_commands = copy.deepcopy(DEFAULT_SYSTEM_COMMANDS)
        
        # Load system commands from config
        self.system_commands = self.load_system_commands()
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create table for system commands
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            tr("Type"), tr("Original Name"), tr("Command"), tr("Permission"), tr("Info"), tr("Group"),
            tr("Cooldown"), tr("UserCooldown"), tr("Cost"), tr("Usage"), tr("Enabled")
        ])
        
        # Track if table needs default_group column (for !volume command)
        self.has_default_group_column = False

        # Set column resize modes
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Type
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Original Name
        header.setSectionResizeMode(2, QHeaderView.Stretch)           # Command
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Permission
        header.setSectionResizeMode(4, QHeaderView.Stretch)           # Info
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Group
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Cooldown
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)  # UserCooldown
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)  # Cost
        header.setSectionResizeMode(9, QHeaderView.ResizeToContents)  # Usage
        header.setSectionResizeMode(10, QHeaderView.ResizeToContents) # Enabled
        
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemChanged.connect(self.table_item_changed)
        self.table.itemSelectionChanged.connect(self.on_command_selected)
        
        layout.addWidget(self.table)
        
        # Create buttons layout
        buttons_layout = QHBoxLayout()
        
        self.add_duplicate_btn = QPushButton(tr("Duplicate Command"))
        self.add_duplicate_btn.clicked.connect(self.duplicate_command)
        buttons_layout.addWidget(self.add_duplicate_btn)
        
        self.remove_btn = QPushButton(tr("Remove Duplicate"))
        self.remove_btn.clicked.connect(self.remove_command)
        buttons_layout.addWidget(self.remove_btn)
        
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        # Create command details group
        details_group = QGroupBox(tr("Command Details"))
        details_layout = QHBoxLayout()
        
        # Left column - Basic settings
        left_column = QVBoxLayout()
        self.original_name_label = QLabel(tr("Original Name:"))
        self.original_name_display = QLabel("")
        self.original_name_display.setStyleSheet("color: gray; font-style: italic;")
        self.command_edit = QLineEdit()
        self.permission_combo = QComboBox()
        self.permission_combo.addItems(permissions.LEVELS)
        self.info_edit = QLineEdit()
        self.group_edit = QLineEdit()
        
        left_column.addWidget(self.original_name_label)
        left_column.addWidget(self.original_name_display)
        left_column.addWidget(QLabel(tr("Command:")))
        left_column.addWidget(self.command_edit)
        left_column.addWidget(QLabel(tr("Permission:")))
        left_column.addWidget(self.permission_combo)
        left_column.addWidget(QLabel(tr("Info:")))
        left_column.addWidget(self.info_edit)
        left_column.addWidget(QLabel(tr("Group:")))
        left_column.addWidget(self.group_edit)
        
        # Right column - Settings
        right_column = QVBoxLayout()
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setMinimum(0)
        self.cooldown_spin.setMaximum(3600)
        self.cooldown_spin.setSuffix(" min")  # the bot counts minutes
        self.user_cooldown_spin = QSpinBox()
        self.user_cooldown_spin.setMinimum(0)
        self.user_cooldown_spin.setMaximum(3600)
        self.user_cooldown_spin.setSuffix(" min")
        self.cost_spin = QSpinBox()
        self.cost_spin.setMinimum(0)
        self.cost_spin.setMaximum(1000000)
        self.usage_combo = QComboBox()
        self.usage_combo.addItems(["SC", "Chat", "Both"])
        self.enabled_check = QCheckBox(tr("Enabled"))
 
        # Random group setting (only for !random commands)
        self.random_group_label = QLabel(tr("Random Group:"))
        self.random_group_edit = QLineEdit()
        self.random_group_edit.setPlaceholderText(tr("GENERAL"))
        
        # Default group setting (only for !volume commands)
        self.default_group_label = QLabel(tr("Default Group:"))
        self.default_group_edit = QLineEdit()
        self.default_group_edit.setPlaceholderText(tr("SONG"))

        # Show picked command setting (only for !random commands)
        self.show_picked_command_check = QCheckBox(tr("Show picked command"))
        
        # Picked command response setting (only for !random commands)
        self.picked_command_response_label = QLabel(tr("Picked Command Response:"))
        self.picked_command_response_edit = QLineEdit()
        self.picked_command_response_edit.setPlaceholderText(tr("Picked {command}."))

        # Connect signals for detail fields
        self.command_edit.textChanged.connect(lambda: self.on_detail_field_changed("command_name", self.command_edit.text()))
        self.permission_combo.currentTextChanged.connect(lambda: self.on_detail_field_changed("permission", self.permission_combo.currentText()))
        self.info_edit.textChanged.connect(lambda: self.on_detail_field_changed("info", self.info_edit.text()))
        self.group_edit.textChanged.connect(lambda: self.on_detail_field_changed("group", self.group_edit.text()))
        self.cooldown_spin.valueChanged.connect(lambda: self.on_detail_field_changed("cooldown", self.cooldown_spin.value()))
        self.user_cooldown_spin.valueChanged.connect(lambda: self.on_detail_field_changed("user_cooldown", self.user_cooldown_spin.value()))
        self.cost_spin.valueChanged.connect(lambda: self.on_detail_field_changed("cost", self.cost_spin.value()))
        self.usage_combo.currentTextChanged.connect(lambda: self.on_detail_field_changed("usage", self.usage_combo.currentText()))
        self.enabled_check.stateChanged.connect(lambda: self.on_detail_field_changed("enabled", self.enabled_check.isChecked()))
        self.random_group_edit.textChanged.connect(lambda: self.on_detail_field_changed("random_group", self.random_group_edit.text()))
        self.show_picked_command_check.stateChanged.connect(lambda: self.on_detail_field_changed("show_picked_command", self.show_picked_command_check.isChecked()))
        self.picked_command_response_edit.textChanged.connect(lambda: self.on_detail_field_changed("picked_command_response", self.picked_command_response_edit.text()))
        self.default_group_edit.textChanged.connect(lambda: self.on_detail_field_changed("default_group", self.default_group_edit.text()))

        right_column.addWidget(QLabel(tr("Cooldown:")))
        right_column.addWidget(self.cooldown_spin)
        right_column.addWidget(QLabel(tr("User Cooldown:")))
        right_column.addWidget(self.user_cooldown_spin)
        right_column.addWidget(QLabel(tr("Cost:")))
        right_column.addWidget(self.cost_spin)
        right_column.addWidget(QLabel(tr("Usage:")))
        right_column.addWidget(self.usage_combo)
        right_column.addWidget(self.enabled_check)

        # Add random group setting
        right_column.addWidget(self.random_group_label)
        right_column.addWidget(self.random_group_edit)
        
        # Add default group setting
        right_column.addWidget(self.default_group_label)
        right_column.addWidget(self.default_group_edit)

        # Add show picked command setting
        right_column.addWidget(self.show_picked_command_check)
        
        # Add picked command response setting
        right_column.addWidget(self.picked_command_response_label)
        right_column.addWidget(self.picked_command_response_edit)
        
        details_layout.addLayout(left_column)
        details_layout.addLayout(right_column)
        details_group.setLayout(details_layout)
        layout.addWidget(details_group)
        
        self.setLayout(layout)
        
        # !random / !volume fields are shown only for those commands (see
        # on_command_selected); hidden until something is selected, otherwise
        # all of them stacked up and inflated the window's minimum height.
        for w in (self.random_group_label, self.random_group_edit,
                  self.show_picked_command_check, self.picked_command_response_label,
                  self.picked_command_response_edit, self.default_group_label,
                  self.default_group_edit):
            w.setVisible(False)

        # Update the table with current commands
        self.update_table()
        
        # Disable editing for original commands (non-duplicates)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        # But allow editing for specific cells that should be editable
        self.table.setEditTriggers(QTableWidget.DoubleClicked)
        
    def load_system_commands(self):
        """Load system commands: every original once (stored settings win),
        then duplicates; one-time migration of queue command cooldowns
        (core.system_commands)."""
        system_commands, changed = merge_with_defaults(self.config_manager.load_system_commands())
        if changed:
            self.save_system_commands(system_commands)
        return system_commands
    
    def save_system_commands(self, commands=None):
        """Save system commands to config"""
        if commands is None:
            commands = self.system_commands
        return self.config_manager.save_system_commands(commands)
    
    def update_table(self):
        """Update the table with current system commands"""
        # Block signals to prevent recursion during table updates
        self.table.blockSignals(True)

        # Clear the table completely by setting row count to 0, then to the correct count
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.system_commands))

        for row, cmd in enumerate(self.system_commands):
            from PyQt5.QtGui import QColor

            # Type column - shows if it's Original or Duplicate
            if cmd.get("is_duplicate", False):
                type_text = "🔄 Duplicate"
                type_color = QColor(255, 165, 0)  # Orange for duplicates
            else:
                type_text = "⭐ Original"
                type_color = QColor(34, 139, 34)  # Green for originals

            type_item = QTableWidgetItem(type_text)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            type_item.setForeground(type_color)
            font = type_item.font()
            font.setBold(True)
            type_item.setFont(font)
            self.table.setItem(row, 0, type_item)

            # Original name (gray, non-editable)
            original_name_item = QTableWidgetItem(cmd["command"])
            original_name_item.setFlags(original_name_item.flags() & ~Qt.ItemIsEditable)
            original_name_item.setForeground(QColor(128, 128, 128))  # Gray color
            font = original_name_item.font()
            font.setItalic(True)
            original_name_item.setFont(font)
            self.table.setItem(row, 1, original_name_item)

            # Command name (always non-editable for originals, editable for duplicates)
            command_name = cmd.get("command_name", cmd["command"])
            command_item = QTableWidgetItem(command_name)
            if cmd.get("is_original", False) and not cmd.get("is_duplicate", False):
                command_item.setFlags(command_item.flags() & ~Qt.ItemIsEditable)
                command_item.setForeground(QColor(34, 139, 34))  # Green for originals
            else:
                # For duplicates, make the command name editable and highlight it
                command_item.setFlags(command_item.flags() | Qt.ItemIsEditable)
                command_item.setForeground(QColor(255, 165, 0))  # Orange for duplicates
                font = command_item.font()
                font.setBold(True)
                command_item.setFont(font)
            self.table.setItem(row, 2, command_item)

            # Permission (editable for all)
            permission_item = QTableWidgetItem(cmd["permission"])
            permission_item.setFlags(permission_item.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 3, permission_item)

            # Info (editable for all)
            info_item = QTableWidgetItem(cmd["info"])
            info_item.setFlags(info_item.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 4, info_item)

            # Group (editable for all)
            group_item = QTableWidgetItem(cmd["group"])
            group_item.setFlags(group_item.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 5, group_item)

            # Cooldown (editable for all)
            cooldown_item = QTableWidgetItem(str(cmd["cooldown"]))
            cooldown_item.setFlags(cooldown_item.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 6, cooldown_item)

            # User Cooldown (editable for all)
            user_cooldown_item = QTableWidgetItem(str(cmd["user_cooldown"]))
            user_cooldown_item.setFlags(user_cooldown_item.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 7, user_cooldown_item)

            # Cost (editable for all)
            cost_item = QTableWidgetItem(str(cmd["cost"]))
            cost_item.setFlags(cost_item.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 8, cost_item)

            # Usage (editable for all)
            usage_item = QTableWidgetItem(cmd["usage"])
            usage_item.setFlags(usage_item.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 9, usage_item)

            # Enabled (editable for all)
            enabled_text = "✓" if cmd["enabled"] else "✗"
            enabled_item = QTableWidgetItem(enabled_text)
            enabled_item.setFlags(enabled_item.flags() | Qt.ItemIsEditable)
            self.table.setItem(row, 10, enabled_item)

        # Unblock signals after table update is complete
        self.table.blockSignals(False)

    def table_item_changed(self, item):
        """Handle changes to table items"""
        # Temporarily block signals to prevent recursion
        self.table.blockSignals(True)

        row = item.row()
        col = item.column()

        if row < len(self.system_commands):
            cmd = self.system_commands[row]

            # Prevent editing command name for original commands
            if col == 2 and cmd.get("is_original", False) and not cmd.get("is_duplicate", False):
                # Revert the change for original command names
                self.update_table()
                # Unblock signals before returning
                self.table.blockSignals(False)
                return

            # Handle command name changes with validation
            if col == 2:  # Command name (only for duplicates)
                new_name = item.text().strip()
                if not new_name:
                    QMessageBox.warning(self, tr("Error"), tr("Command name cannot be empty."))
                    self.update_table()
                    self.table.blockSignals(False)
                    return

                # Check for duplicate names
                for i, existing_cmd in enumerate(self.system_commands):
                    if i != row:  # Don't check against itself
                        existing_name = existing_cmd.get("command_name", existing_cmd["command"])
                        if existing_name == new_name:
                            QMessageBox.warning(
                                self, tr("Error"),
                                tr("Command name '{0}' already exists. Please choose a different name.").format(new_name)
                            )
                            self.update_table()
                            self.table.blockSignals(False)
                            return

                cmd["command_name"] = new_name
            elif col == 3:  # Permission
                cmd["permission"] = item.text()
            elif col == 4:  # Info
                cmd["info"] = item.text()
            elif col == 5:  # Group
                cmd["group"] = item.text()
            elif col == 6:  # Cooldown
                try:
                    cmd["cooldown"] = int(item.text() or 0)
                except ValueError:
                    cmd["cooldown"] = 0
            elif col == 7:  # UserCooldown
                try:
                    cmd["user_cooldown"] = int(item.text() or 0)
                except ValueError:
                    cmd["user_cooldown"] = 0
            elif col == 8:  # Cost
                try:
                    cmd["cost"] = int(item.text() or 0)
                except ValueError:
                    cmd["cost"] = 0
            elif col == 9:  # Usage
                cmd["usage"] = item.text()
            elif col == 10:  # Enabled
                cmd["enabled"] = item.text() == "✓"

            # Save changes
            self.save_system_commands()

        # Always unblock signals before returning
        self.table.blockSignals(False)
    
    def on_command_selected(self):
        """Handle command selection in the table"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            return

        row = selected_items[0].row()
        if row < len(self.system_commands):
            cmd = self.system_commands[row]

            # Update original name display
            self.original_name_display.setText(cmd["command"])

            # Update fields with command data
            self.command_edit.setText(cmd.get("command_name", cmd["command"]))
            self.permission_combo.setCurrentText(permissions.name_of(cmd["permission"]))
            self.info_edit.setText(cmd["info"])
            self.group_edit.setText(cmd["group"])

            self.cooldown_spin.setValue(cmd["cooldown"])
            self.user_cooldown_spin.setValue(cmd["user_cooldown"])
            self.cost_spin.setValue(cmd["cost"])
            self.usage_combo.setCurrentText(cmd["usage"])

            # Update enabled checkbox
            self.enabled_check.blockSignals(True)
            self.enabled_check.setChecked(cmd["enabled"])
            self.enabled_check.blockSignals(False)

            # Show/hide random group field only for !random commands
            is_random_command = cmd["command"] == "!random" or cmd.get("command_name", "").startswith("!random")
            self.random_group_label.setVisible(is_random_command)
            self.random_group_edit.setVisible(is_random_command)
            self.show_picked_command_check.setVisible(is_random_command)
            self.picked_command_response_label.setVisible(is_random_command)
            self.picked_command_response_edit.setVisible(is_random_command)

            # Show/hide default group field only for !volume commands
            is_volume_command = cmd["command"] == "!volume" or cmd.get("command_name", "").startswith("!volume")
            self.default_group_label.setVisible(is_volume_command)
            self.default_group_edit.setVisible(is_volume_command)

            if is_random_command:
                self.random_group_edit.blockSignals(True)
                self.random_group_edit.setText(cmd.get("random_group", "GENERAL"))
                self.random_group_edit.blockSignals(False)

                self.show_picked_command_check.blockSignals(True)
                self.show_picked_command_check.setChecked(cmd.get("show_picked_command", True))
                self.show_picked_command_check.blockSignals(False)
                
                self.picked_command_response_edit.blockSignals(True)
                self.picked_command_response_edit.setText(cmd.get("picked_command_response", "Picked {command}."))
                self.picked_command_response_edit.blockSignals(False)

            if is_volume_command:
                self.default_group_edit.blockSignals(True)
                self.default_group_edit.setText(cmd.get("default_group", "SONG"))
                self.default_group_edit.blockSignals(False)

    def on_detail_field_changed(self, field_name, value):
        """Handle changes to detail fields"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            return

        row = selected_items[0].row()
        if row >= len(self.system_commands):
            return

        cmd = self.system_commands[row]

        # Prevent editing command name for original commands
        if field_name == "command_name" and cmd.get("is_original", False) and not cmd.get("is_duplicate", False):
            # Revert the field to original value
            self.on_command_selected()  # Refresh the fields
            return

        # Allow editing all other fields for both original and duplicate commands
        # Update the command data
        cmd[field_name] = value

        # Track if a default-disabled command was manually enabled
        if field_name == "enabled" and value == True and cmd.get("is_default_disabled", False):
            cmd["was_manually_enabled"] = True

        # Save changes
        self.save_system_commands()

        # Update the table to reflect changes, but avoid full table update for text fields
        # to prevent cursor jumping in text input fields
        if field_name not in ["info", "group", "random_group", "picked_command_response", "command_name"]:
            # Only update table for non-text fields to avoid cursor issues
            self.update_table()
            # Reselect the current row to maintain selection
            self.table.selectRow(row)

        # Update the parent's command list if it exists
        if self.parent and hasattr(self.parent, 'update_system_commands'):
            self.parent.update_system_commands(self.system_commands)

    def update_command_field(self, value, field_name):
        """Update a specific field in the selected command"""
        selected_items = self.table.selectedItems()
        if selected_items:
            row = selected_items[0].row()
            if row < len(self.system_commands):
                cmd = self.system_commands[row]
                
                # Only allow editing for duplicate commands (not originals)
                if cmd.get("is_original", False) and not cmd.get("is_duplicate", False):
                    QMessageBox.warning(self, tr("Error"), tr("Cannot modify original system commands. Create a duplicate to customize."))
                    return
                
                cmd[field_name] = value
                self.save_system_commands()
                self.update_table()
                
                # Update the parent's command list if it exists
                if self.parent and hasattr(self.parent, 'update_system_commands'):
                    self.parent.update_system_commands(self.system_commands)

    # -- API shared with the themed view (theme.SysCommandsView) ---------
    @staticmethod
    def display_name(cmd):
        return cmd.get("command_name", cmd.get("command", ""))

    def name_error(self, row, name):
        """Why `name` can't be used for the command at `row` (None if ok)."""
        name = (name or "").strip()
        if not name:
            return "Command name cannot be empty."
        for i, other in enumerate(self.system_commands):
            if i != row and self.display_name(other) == name:
                return "Command name '%s' already exists." % name
        return None

    def set_field(self, row, field_name, value):
        """Change one field, save and refresh the table. Returns an error
        message (nothing changed) or None."""
        if not (0 <= row < len(self.system_commands)):
            return "No command selected."
        cmd = self.system_commands[row]
        if field_name == "command_name":
            if not cmd.get("is_duplicate", False):
                return "Original command names can't be changed — duplicate the command instead."
            err = self.name_error(row, value)
            if err:
                return err
            value = value.strip()
        cmd[field_name] = value
        if field_name == "enabled" and value and cmd.get("is_default_disabled", False):
            cmd["was_manually_enabled"] = True
        self.save_system_commands()
        self.update_table()
        if self.parent and hasattr(self.parent, 'update_system_commands'):
            self.parent.update_system_commands(self.system_commands)
        return None

    def duplicate_at(self, row):
        """Duplicate the original command at `row`. Returns the new row or
        an error message (str)."""
        if not (0 <= row < len(self.system_commands)):
            return "Please select an original command to duplicate."
        original_cmd = self.system_commands[row]
        if not original_cmd.get("is_original", False) or original_cmd.get("is_duplicate", False):
            return "You can only duplicate original commands, not existing duplicates."
        import copy
        duplicate_cmd = copy.deepcopy(original_cmd)
        base_name = original_cmd["command"]
        counter = 1
        new_name = f"{base_name}_copy"
        existing_names = [self.display_name(c) for c in self.system_commands]
        while new_name in existing_names:
            counter += 1
            new_name = f"{base_name}_copy{counter}"
        duplicate_cmd["command_name"] = new_name
        duplicate_cmd["is_duplicate"] = True
        duplicate_cmd["enabled"] = False  # Start disabled by default
        self.system_commands.append(duplicate_cmd)
        self.save_system_commands()
        self.update_table()
        return len(self.system_commands) - 1

    def remove_at(self, row, parent_widget=None):
        """Remove the duplicate at `row` after confirmation. True if removed."""
        if not (0 <= row < len(self.system_commands)):
            return False
        cmd = self.system_commands[row]
        if not cmd.get("is_duplicate", False):
            QMessageBox.warning(parent_widget or self, tr("Error"), tr("Cannot remove original system commands."))
            return False
        reply = QMessageBox.question(
            parent_widget or self, tr("Confirm Removal"),
            tr("Are you sure you want to remove the duplicate command '{0}'?").format(self.display_name(cmd)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return False
        del self.system_commands[row]
        self.save_system_commands()
        self.update_table()
        return True

    def duplicate_command(self):
        """Create a duplicate of the selected original command"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, tr("Error"), tr("Please select an original command to duplicate."))
            return
        result = self.duplicate_at(selected_items[0].row())
        if isinstance(result, str):
            QMessageBox.warning(self, tr("Error"), result)
            return
        self.table.selectRow(result)

    def remove_command(self):
        """Remove the selected duplicate command"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, tr("Error"), tr("Please select a duplicate command to remove."))
            return
        self.remove_at(selected_items[0].row())

    def show_context_menu(self, position):
        """Show context menu for the table"""
        menu = QMenu()
        
        duplicate_action = menu.addAction(tr("Duplicate Command"))
        duplicate_action.triggered.connect(self.duplicate_command)
        
        remove_action = menu.addAction(tr("Remove Duplicate"))
        remove_action.triggered.connect(self.remove_command)
        
        menu.exec_(self.table.viewport().mapToGlobal(position))
