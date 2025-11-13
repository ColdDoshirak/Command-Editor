import json
import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
                           QGroupBox, QLabel, QLineEdit, QSpinBox, QComboBox,
                           QMenu, QMessageBox)
from PyQt5.QtCore import Qt
from config_manager import ConfigManager


class SysCommandsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.config_manager = ConfigManager()
        
        # Define original system commands with their default settings
        self.original_commands = [
            {
                "command": "!points",
                "permission": "Everyone",
                "response": "",
                "enabled": True,
                "info": "Show user's points balance",
                "group": "SYSTEM",
                "cooldown": 5,
                "user_cooldown": 5,
                "cost": 0,
                "usage": "Chat",
                "is_original": True
            },
            {
                "command": "!add_points",
                "permission": "Moderator",
                "response": "",
                "enabled": True,
                "info": "Add points to a user",
                "group": "SYSTEM",
                "cooldown": 0,
                "user_cooldown": 0,
                "cost": 0,
                "usage": "Chat",
                "is_original": True
            },
            {
                "command": "!remove_points",
                "permission": "Moderator",
                "response": "",
                "enabled": True,
                "info": "Remove points from a user",
                "group": "SYSTEM",
                "cooldown": 0,
                "user_cooldown": 0,
                "cost": 0,
                "usage": "Chat",
                "is_original": True
            },
            {
                "command": "!random",
                "permission": "Everyone",
                "response": "",
                "enabled": False,  # Default disabled as requested
                "info": "Execute a random command from the configured group",
                "group": "SYSTEM",
                "cooldown": 10,
                "user_cooldown": 10,
                "cost": 0,
                "usage": "Chat",
                "random_group": "ALL",  # Default group for random command
                "show_picked_command": True,  # Show which command was picked
                "is_original": True,
                "is_default_disabled": True  # Mark this as default disabled
            }
        ]
        
        # Load system commands from config
        self.system_commands = self.load_system_commands()
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create table for system commands
        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "Type", "Original Name", "Command", "Permission", "Info", "Group",
            "Cooldown", "UserCooldown", "Cost", "Usage", "Enabled"
        ])

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
        
        self.add_duplicate_btn = QPushButton("Duplicate Command")
        self.add_duplicate_btn.clicked.connect(self.duplicate_command)
        buttons_layout.addWidget(self.add_duplicate_btn)
        
        self.remove_btn = QPushButton("Remove Duplicate")
        self.remove_btn.clicked.connect(self.remove_command)
        buttons_layout.addWidget(self.remove_btn)
        
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        # Create command details group
        details_group = QGroupBox("Command Details")
        details_layout = QHBoxLayout()
        
        # Left column - Basic settings
        left_column = QVBoxLayout()
        self.original_name_label = QLabel("Original Name:")
        self.original_name_display = QLabel("")
        self.original_name_display.setStyleSheet("color: gray; font-style: italic;")
        self.command_edit = QLineEdit()
        self.permission_combo = QComboBox()
        self.permission_combo.addItems(["Everyone", "Moderator", "Admin"])
        self.info_edit = QLineEdit()
        self.group_edit = QLineEdit()
        
        left_column.addWidget(self.original_name_label)
        left_column.addWidget(self.original_name_display)
        left_column.addWidget(QLabel("Command:"))
        left_column.addWidget(self.command_edit)
        left_column.addWidget(QLabel("Permission:"))
        left_column.addWidget(self.permission_combo)
        left_column.addWidget(QLabel("Info:"))
        left_column.addWidget(self.info_edit)
        left_column.addWidget(QLabel("Group:"))
        left_column.addWidget(self.group_edit)
        
        # Right column - Settings
        right_column = QVBoxLayout()
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setMinimum(0)
        self.cooldown_spin.setMaximum(3600)
        self.user_cooldown_spin = QSpinBox()
        self.user_cooldown_spin.setMinimum(0)
        self.user_cooldown_spin.setMaximum(3600)
        self.cost_spin = QSpinBox()
        self.cost_spin.setMinimum(0)
        self.cost_spin.setMaximum(1000000)
        self.usage_combo = QComboBox()
        self.usage_combo.addItems(["SC", "Chat", "Both"])
        self.enabled_check = QCheckBox("Enabled")

        # Random group setting (only for !random commands)
        self.random_group_label = QLabel("Random Group:")
        self.random_group_edit = QLineEdit()
        self.random_group_edit.setPlaceholderText("GENERAL")

        # Show picked command setting (only for !random commands)
        self.show_picked_command_check = QCheckBox("Show picked command")

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

        right_column.addWidget(QLabel("Cooldown:"))
        right_column.addWidget(self.cooldown_spin)
        right_column.addWidget(QLabel("User Cooldown:"))
        right_column.addWidget(self.user_cooldown_spin)
        right_column.addWidget(QLabel("Cost:"))
        right_column.addWidget(self.cost_spin)
        right_column.addWidget(QLabel("Usage:"))
        right_column.addWidget(self.usage_combo)
        right_column.addWidget(self.enabled_check)

        # Add random group setting
        right_column.addWidget(self.random_group_label)
        right_column.addWidget(self.random_group_edit)

        # Add show picked command setting
        right_column.addWidget(self.show_picked_command_check)
        
        details_layout.addLayout(left_column)
        details_layout.addLayout(right_column)
        details_group.setLayout(details_layout)
        layout.addWidget(details_group)
        
        self.setLayout(layout)
        
        # Update the table with current commands
        self.update_table()
        
        # Disable editing for original commands (non-duplicates)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        # But allow editing for specific cells that should be editable
        self.table.setEditTriggers(QTableWidget.DoubleClicked)
        
    def load_system_commands(self):
        """Load system commands from config, initializing with original commands if needed"""
        system_commands = self.config_manager.load_system_commands()

        # If no system commands exist in config, initialize with original commands
        if not system_commands:
            system_commands = self.original_commands.copy()
            self.save_system_commands(system_commands)
        else:
            # Clean the loaded commands first - remove any duplicates by command name
            cleaned_commands = {}
            duplicates = []

            # Separate originals and duplicates, keeping only one of each original command
            for cmd in system_commands:
                cmd_key = cmd["command"]
                if cmd.get("is_duplicate", False):
                    # Always keep duplicates
                    duplicates.append(cmd)
                elif cmd_key not in cleaned_commands:
                    # Keep the first original command we find
                    cleaned_commands[cmd_key] = cmd
                # Skip additional originals with the same name

            # Now merge with required original commands
            final_commands = []

            # Add all required original commands, using existing settings if available
            for orig_cmd in self.original_commands:
                cmd_key = orig_cmd["command"]
                if cmd_key in cleaned_commands:
                    # Use existing command but ensure it's marked as original
                    existing_cmd = cleaned_commands[cmd_key].copy()
                    existing_cmd["is_original"] = True
                    # If this command should be disabled by default and hasn't been explicitly enabled, keep it disabled
                    if orig_cmd.get("is_default_disabled", False) and not existing_cmd.get("was_manually_enabled", False):
                        existing_cmd["enabled"] = False
                    final_commands.append(existing_cmd)
                else:
                    # Add new original command
                    final_commands.append(orig_cmd.copy())

            # Add all duplicate commands
            final_commands.extend(duplicates)

            system_commands = final_commands
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
            from PyQt5.QtGui import QColor, QFont

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
                    QMessageBox.warning(self, "Error", "Command name cannot be empty.")
                    self.update_table()
                    self.table.blockSignals(False)
                    return

                # Check for duplicate names
                for i, existing_cmd in enumerate(self.system_commands):
                    if i != row:  # Don't check against itself
                        existing_name = existing_cmd.get("command_name", existing_cmd["command"])
                        if existing_name == new_name:
                            QMessageBox.warning(
                                self, "Error",
                                f"Command name '{new_name}' already exists. Please choose a different name."
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
            self.permission_combo.setCurrentText(cmd["permission"])
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

            if is_random_command:
                self.random_group_edit.blockSignals(True)
                self.random_group_edit.setText(cmd.get("random_group", "GENERAL"))
                self.random_group_edit.blockSignals(False)

                self.show_picked_command_check.blockSignals(True)
                self.show_picked_command_check.setChecked(cmd.get("show_picked_command", True))
                self.show_picked_command_check.blockSignals(False)

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

        # Update the table to reflect changes
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
                    QMessageBox.warning(self, "Error", "Cannot modify original system commands. Create a duplicate to customize.")
                    return
                
                cmd[field_name] = value
                self.save_system_commands()
                self.update_table()
                
                # Update the parent's command list if it exists
                if self.parent and hasattr(self.parent, 'update_system_commands'):
                    self.parent.update_system_commands(self.system_commands)

    def duplicate_command(self):
        """Create a duplicate of the selected original command"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "Please select an original command to duplicate.")
            return

        row = selected_items[0].row()
        if row >= len(self.system_commands):
            return

        original_cmd = self.system_commands[row]

        # Only allow duplicating original commands (that are not duplicates themselves)
        if not original_cmd.get("is_original", False) or original_cmd.get("is_duplicate", False):
            QMessageBox.warning(self, "Error", "You can only duplicate original commands, not existing duplicates.")
            return

        import copy
        # Create a duplicate with a unique name
        duplicate_cmd = copy.deepcopy(original_cmd)

        # Generate a unique name for the duplicate
        base_name = original_cmd["command"]
        counter = 1
        new_name = f"{base_name}_copy"

        # Check if the name already exists and increment counter if needed
        existing_names = [cmd.get("command_name", cmd["command"]) for cmd in self.system_commands]
        while new_name in existing_names:
            counter += 1
            new_name = f"{base_name}_copy{counter}"

        duplicate_cmd["command_name"] = new_name
        duplicate_cmd["is_duplicate"] = True
        duplicate_cmd["enabled"] = False # Start disabled by default

        # Add to system commands
        self.system_commands.append(duplicate_cmd)

        # Save and update UI
        self.save_system_commands()
        self.update_table()

        # Select the new duplicate
        self.table.selectRow(len(self.system_commands) - 1)
        


    def remove_command(self):
        """Remove the selected duplicate command"""
        selected_items = self.table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "Please select a duplicate command to remove.")
            return
            
        row = selected_items[0].row()
        if row >= len(self.system_commands):
            return
            
        cmd = self.system_commands[row]
        
        # Only allow removing duplicates, not original commands
        # A command is considered a duplicate if it has is_duplicate=True
        if not cmd.get("is_duplicate", False):
            QMessageBox.warning(self, "Error", "Cannot remove original system commands.")
            return
        
        reply = QMessageBox.question(
            self, 
            "Confirm Removal", 
            f"Are you sure you want to remove the duplicate command '{cmd.get('command_name', cmd['command'])}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Remove from system commands
            del self.system_commands[row]
            
            # Save and update UI
            self.save_system_commands()
            self.update_table()

    def show_context_menu(self, position):
        """Show context menu for the table"""
        menu = QMenu()
        
        duplicate_action = menu.addAction("Duplicate Command")
        duplicate_action.triggered.connect(self.duplicate_command)
        
        remove_action = menu.addAction("Remove Duplicate")
        remove_action.triggered.connect(self.remove_command)
        
        menu.exec_(self.table.viewport().mapToGlobal(position))

    def get_system_commands(self):
        """Return the current system commands list"""
        return self.system_commands

    def set_system_commands(self, commands):
        """Set the system commands list"""
        self.system_commands = commands
        self.update_table()
