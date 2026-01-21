from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QHBoxLayout, QMessageBox, QCheckBox, QSpinBox
from PyQt5.QtCore import Qt

class GroupSettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = parent.config_manager
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Table for group settings
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Group Name", "Queue Enabled", "Max Queue Size", "Audio Channel"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Groups")
        self.refresh_btn.clicked.connect(self.refresh_groups)
        btn_layout.addWidget(self.refresh_btn)

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)
        
        self.refresh_groups()

    def refresh_groups(self):
        # Get unique groups from commands
        groups = set()
        for cmd in self.parent.commands:
            groups.add(cmd.get("Group", "GENERAL"))
        
        # Load current settings
        categories = self.config_manager.get_audio_categories()
        
        self.table.setRowCount(len(groups))
        for i, group in enumerate(sorted(list(groups))):
            self.table.setItem(i, 0, QTableWidgetItem(group))
            
            check = QCheckBox()
            is_enabled = categories.get(group, {}).get("queue_enabled", False)
            check.setChecked(is_enabled)
            
            # Center the checkbox
            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.addWidget(check)
            cell_layout.setAlignment(Qt.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            
            self.table.setCellWidget(i, 1, cell_widget)
            # Store the checkbox reference in the item's data or just use cellWidget
            self.table.item(i, 0).setData(Qt.UserRole, check)

            # Max Queue Size SpinBox
            spin = QSpinBox()
            spin.setRange(0, 1000)
            spin.setValue(categories.get(group, {}).get("max_queue_size", 0))
            spin.setToolTip("0 = Unlimited")
            
            # Center the spinbox
            spin_widget = QWidget()
            spin_layout = QHBoxLayout(spin_widget)
            spin_layout.addWidget(spin)
            spin_layout.setAlignment(Qt.AlignCenter)
            spin_layout.setContentsMargins(0, 0, 0, 0)
            
            self.table.setCellWidget(i, 2, spin_widget)
            # Store spinbox reference
            self.table.item(i, 0).setData(Qt.UserRole + 1, spin)

            # Audio Channel SpinBox
            channel_spin = QSpinBox()
            channel_spin.setRange(0, 32)
            channel_spin.setValue(categories.get(group, {}).get("audio_channel", 0))
            channel_spin.setToolTip("0 = Default Channel. Assign unique IDs (1-32) for parallel playback.")
            
            # Center the spinbox
            channel_widget = QWidget()
            channel_layout = QHBoxLayout(channel_widget)
            channel_layout.addWidget(channel_spin)
            channel_layout.setAlignment(Qt.AlignCenter)
            channel_layout.setContentsMargins(0, 0, 0, 0)
            
            self.table.setCellWidget(i, 3, channel_widget)
            # Store channel spinbox reference
            self.table.item(i, 0).setData(Qt.UserRole + 2, channel_spin)

    def save_settings(self):
        categories = self.config_manager.get_audio_categories()
        
        for i in range(self.table.rowCount()):
            group = self.table.item(i, 0).text()
            check = self.table.item(i, 0).data(Qt.UserRole)
            spin = self.table.item(i, 0).data(Qt.UserRole + 1)
            channel_spin = self.table.item(i, 0).data(Qt.UserRole + 2)
            
            if group not in categories:
                categories[group] = {}
            
            categories[group]["queue_enabled"] = check.isChecked()
            categories[group]["max_queue_size"] = spin.value()
            categories[group]["audio_channel"] = channel_spin.value()
            
        self.config_manager.save_audio_categories(categories)
        QMessageBox.information(self, "Success", "Group settings saved successfully!")
        
        # Notify bot if running
        if hasattr(self.parent, 'twitch_tab') and self.parent.twitch_tab.bot:
            # We will implement this update method in TwitchBot later
            pass
