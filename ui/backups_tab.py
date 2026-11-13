"""The History and Backups tabs (step 4.3: moved out of the main window).

History  - command-only backups (core/history_manager.py)
Backups  - full system backups (core/backups.py)

Both talk to the window only through what it already offers: its
commands, replace_commands(), update_commands() and the shared managers.

Python 3.8 / PyQt5.
"""
import json
from datetime import datetime

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
                             QSpinBox, QMessageBox, QDialog, QFrame, QDialogButtonBox)

from core import paths
from core.backups import FullBackups
from ui.i18n import tr, N_


def _header(text):
    label = QLabel(text)
    font = QFont()
    font.setPointSize(14)
    font.setBold(True)
    label.setFont(font)
    return label


class HistoryTab(QWidget):
    """Command backups: list, restore, view, create now, how many to keep."""

    def __init__(self, editor):
        super(HistoryTab, self).__init__()
        self.editor = editor
        self.history = editor.history_manager
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        create_backup_btn = QPushButton(tr("Create Backup Now"))
        create_backup_btn.clicked.connect(self.create_backup)
        header_layout.addWidget(_header(tr("Command History")))
        header_layout.addStretch()
        header_layout.addWidget(create_backup_btn)
        layout.addLayout(header_layout)

        description = QLabel(tr("The system automatically saves backups when you make significant "
                             "changes. You can restore previous versions from here."))
        description.setWordWrap(True)
        layout.addWidget(description)

        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(4)
        self.backup_table.setHorizontalHeaderLabels([tr("Date & Time"), tr("Size (KB)"), tr("Actions"), ""])
        self.backup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.backup_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.refresh()
        layout.addWidget(self.backup_table)

        backup_settings = QGroupBox(tr("Backup Settings"))
        backup_settings_layout = QHBoxLayout()
        self.max_backups_spin = QSpinBox()
        self.max_backups_spin.setMinimum(1)
        self.max_backups_spin.setMaximum(100)
        self.max_backups_spin.setValue(self.history.max_backups)
        self.max_backups_spin.valueChanged.connect(self.update_max_backups)
        backup_settings_layout.addWidget(QLabel(tr("Maximum number of backups:")))
        backup_settings_layout.addWidget(self.max_backups_spin)
        backup_settings_layout.addStretch()
        backup_settings.setLayout(backup_settings_layout)
        layout.addWidget(backup_settings)

    def refresh(self):
        self.backup_table.setRowCount(0)
        for i, backup in enumerate(self.history.get_backups()):
            self.backup_table.insertRow(i)
            self.backup_table.setItem(i, 0, QTableWidgetItem(backup["readable_time"]))
            self.backup_table.setItem(i, 1, QTableWidgetItem(f"{backup['size']} KB"))
            restore_btn = QPushButton(tr("Restore"))
            restore_btn.clicked.connect(lambda checked, path=backup["path"]: self.restore(path))
            view_btn = QPushButton(tr("View"))
            view_btn.clicked.connect(lambda checked, path=backup["path"]: self.view(path))
            self.backup_table.setCellWidget(i, 2, restore_btn)
            self.backup_table.setCellWidget(i, 3, view_btn)

    def create_backup(self):
        if not self.editor.commands:
            QMessageBox.warning(self, tr("Warning"), tr("No commands to backup."))
            return
        if self.history.save_backup(self.editor.commands):
            self.refresh()
            QMessageBox.information(self, tr("Success"), tr("Backup created successfully!"))
        else:
            QMessageBox.warning(self, tr("Error"), tr("Failed to create backup."))

    def restore(self, backup_path):
        if not backup_path:
            return
        reply = QMessageBox.question(
            self, tr("Confirm Restore"),
            tr("Restoring will replace your current commands. Continue?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        commands = self.history.restore_backup(backup_path)
        if commands:
            self.editor.replace_commands(commands)
            QMessageBox.information(self, tr("Success"), tr("Commands restored successfully!"))
        else:
            QMessageBox.warning(self, tr("Error"), tr("Failed to restore backup."))

    def view(self, backup_path):
        if not backup_path:
            return
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                commands = json.load(f)
            dialog = QDialog(self)
            dialog.setWindowTitle(tr("Backup Contents"))
            dialog.setMinimumSize(800, 600)
            dialog_layout = QVBoxLayout(dialog)
            view = QTableWidget()
            cols = [(N_("Command"), "Command", ""), (N_("Sound file"), "SoundFile", ""),
                    (N_("Response"), "Response", ""), (N_("Group"), "Group", ""),
                    (N_("Enabled"), "Enabled", True), (N_("Volume"), "Volume", 100),
                    (N_("Cooldown"), "Cooldown", 0)]
            view.setColumnCount(len(cols))
            view.setHorizontalHeaderLabels([tr(c[0]) for c in cols])
            view.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            view.setRowCount(len(commands))
            for i, cmd in enumerate(commands):
                for j, (_title, key, default) in enumerate(cols):
                    value = cmd.get(key, default)
                    if key == "Enabled":
                        value = "✓" if value else "✗"
                    view.setItem(i, j, QTableWidgetItem(str(value)))
            dialog_layout.addWidget(view)
            close_btn = QPushButton(tr("Close"))
            close_btn.clicked.connect(dialog.close)
            dialog_layout.addWidget(close_btn)
            dialog.exec_()
        except Exception as e:
            QMessageBox.warning(self, tr("Error"), tr('Failed to view backup: {0}').format(str(e)))

    def update_max_backups(self, value):
        self.history.max_backups = value
        self.editor.config_manager.set_max_backups(value)


class FullBackupsTab(QWidget):
    """Full system backups: create, list (latest highlighted), restore, details."""

    def __init__(self, editor):
        super(FullBackupsTab, self).__init__()
        self.editor = editor
        self.config_manager = editor.config_manager
        self.store = FullBackups(paths.comprehensive_backups_dir())
        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        header_layout.addWidget(_header(tr("Comprehensive System Backups")))
        header_layout.addStretch()
        layout.addLayout(header_layout)

        description = QLabel(
            tr("Create and manage full system backups that include all commands, moderator settings, "
            "currency user data, and application settings. This allows you to restore the entire "
            "application state in case of major issues."))
        description.setWordWrap(True)
        layout.addWidget(description)

        create_group = QGroupBox(tr("Create Backup"))
        create_layout = QVBoxLayout()
        create_info = QLabel(
            tr("A comprehensive backup includes:\n"
            "• All commands and their settings\n"
            "• Currency users and points\n"
            "• Moderator settings\n"
            "• Application configuration\n"
            "• Rank settings"))
        create_info.setStyleSheet("color: gray;")
        create_layout.addWidget(create_info)
        self.create_system_backup_btn = QPushButton(tr("Create Full System Backup"))
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
        self.create_system_backup_btn.clicked.connect(self.create_and_show)
        create_layout.addWidget(self.create_system_backup_btn)
        create_group.setLayout(create_layout)
        layout.addWidget(create_group)

        settings_group = QGroupBox(tr("Backup Settings"))
        settings_layout = QVBoxLayout()
        max_backups_layout = QHBoxLayout()
        self.max_comprehensive_backups_spin = QSpinBox()
        self.max_comprehensive_backups_spin.setMinimum(1)
        self.max_comprehensive_backups_spin.setMaximum(50)
        self.max_comprehensive_backups_spin.setValue(self.config_manager.get_max_comprehensive_backups())
        self.max_comprehensive_backups_spin.valueChanged.connect(self.update_max_backups)
        max_backups_layout.addWidget(QLabel(tr("Maximum Backups:")))
        max_backups_layout.addWidget(self.max_comprehensive_backups_spin)
        max_backups_layout.addStretch()
        settings_layout.addLayout(max_backups_layout)
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        list_group = QGroupBox(tr("Available Backups"))
        list_layout = QVBoxLayout()
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel(tr("Status:")))
        self.system_backup_status_label = QLabel(tr("Loading..."))
        controls_layout.addWidget(self.system_backup_status_label)
        refresh_btn = QPushButton(tr("Refresh List"))
        refresh_btn.clicked.connect(self.refresh)
        controls_layout.addWidget(refresh_btn)
        controls_layout.addStretch()
        list_layout.addLayout(controls_layout)
        self.system_backup_list_layout = QVBoxLayout()
        self.system_backup_list_widget = QWidget()
        self.system_backup_list_widget.setLayout(self.system_backup_list_layout)
        list_layout.addWidget(self.system_backup_list_widget)
        list_group.setLayout(list_layout)
        layout.addWidget(list_group)

        QTimer.singleShot(500, self.refresh)
        layout.addStretch()

    # -- data ------------------------------------------------------------------------
    def create(self):
        """Make a full backup now. Returns its path, or None."""
        try:
            ed = self.editor
            data = self.store.collect(ed.commands, currency=getattr(ed, "currency_manager", None),
                                      config=self.config_manager,
                                      history=getattr(ed, "history_manager", None))
            return self.store.create(data, keep=self.config_manager.get_max_comprehensive_backups())
        except Exception as e:
            print(f"Error creating comprehensive backup: {e}")
            return None

    def create_and_show(self):
        self.create()
        self.refresh()

    def create_auto(self):
        """Timer: scheduled full backup."""
        print("Running automatic comprehensive backup...")
        path = self.create()
        if path:
            print(f"Automatic comprehensive backup created: {path}")
            self.refresh()
        else:
            print("Failed to create automatic comprehensive backup")

    def update_max_backups(self, value):
        try:
            self.config_manager.set_max_comprehensive_backups(value)
            self.store.cleanup(value)
        except Exception as e:
            print(f"Error updating max comprehensive backups: {e}")

    # -- the list ----------------------------------------------------------------------
    def refresh(self):
        try:
            layout = self.system_backup_list_layout
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            entries = self.store.entries()
            if not entries:
                no_backups_label = QLabel(tr("No comprehensive backups found."))
                no_backups_label.setStyleSheet("color: gray; font-style: italic;")
                layout.addWidget(no_backups_label)
                self.system_backup_status_label.setText(tr("No backups"))
                self.system_backup_status_label.setStyleSheet("color: gray;")
                return
            self.system_backup_status_label.setText(tr('{0} backups available').format(len(entries)))
            self.system_backup_status_label.setStyleSheet("color: #3B82F6;")
            for i, entry in enumerate(entries):
                layout.addWidget(self._card(entry, latest=(i == 0)))
                layout.addSpacing(5)
        except Exception as e:
            print(f"Error refreshing comprehensive backups: {e}")
            self.system_backup_status_label.setText(tr("Error loading backups"))
            self.system_backup_status_label.setStyleSheet("color: red;")

    def _card(self, entry, latest):
        if entry["error"]:
            label = QLabel(tr('⚠️ Error loading backup: {0}').format(entry['path'].name))
            label.setStyleSheet("color: red;")
            return label
        meta = entry["meta"]
        frame = QFrame()
        frame.setFrameStyle(QFrame.Box)
        frame.setLineWidth(1)
        frame_layout = QVBoxLayout(frame)

        header_layout = QHBoxLayout()
        name_label = QLabel(f"📦 {entry['name']}")
        name_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(name_label)
        header_layout.addWidget(QLabel(f"💾 {entry['size_text']}"))
        header_layout.addWidget(QLabel(tr('📋 {0} cmds, 👥 {1} users, 🛡️ {2} mods').format(meta.get('commands_count', '?'), meta.get('users_count', '?'), meta.get('moderators_count', '?'))))
        if 'backup_time' in meta:
            when = datetime.fromtimestamp(meta['backup_time']).strftime("%H:%M %d/%m/%Y")
            time_label = QLabel(f"⏰ {when}")
            time_label.setStyleSheet("color: gray;")
            header_layout.addWidget(time_label)
        header_layout.addStretch()
        frame_layout.addLayout(header_layout)

        buttons_layout = QHBoxLayout()
        buttons_layout.addSpacing(10)
        restore_btn = QPushButton(tr("Restore System"))
        restore_btn.setToolTip(tr("Restore the entire system from this backup"))
        restore_btn.clicked.connect(lambda checked, p=entry["path"]: self.restore(p))
        buttons_layout.addWidget(restore_btn)
        info_btn = QPushButton(tr("Details"))
        info_btn.setToolTip(tr("Show detailed backup information"))
        info_btn.clicked.connect(lambda checked, p=entry["path"]: self.show_info(p))
        buttons_layout.addWidget(info_btn)
        buttons_layout.addStretch()
        frame_layout.addLayout(buttons_layout)

        # Latest backup in green. Selector by objectName: a bare "QFrame {}"
        # also matched every QLabel inside (QLabel is a QFrame) and the fixed
        # near-white background made the card white in the dark theme.
        if latest:
            frame.setObjectName("latestBackup")
            frame.setStyleSheet("""
                QFrame#latestBackup {
                    border: 2px solid #4CAF50;
                    border-radius: 5px;
                    background-color: rgba(76, 175, 80, 0.10);
                }
            """)
        return frame

    # -- restore / details ---------------------------------------------------------------
    def restore(self, backup_file):
        try:
            reply = QMessageBox.question(
                self, tr("⚠️ Dangerous Operation"),
                tr("This will REPLACE your entire current system state with the backup data.\n\n"
                "This includes:\n"
                "• All commands\n"
                "• All user points and hours\n"
                "• Moderator settings\n"
                "• Application configuration\n\n"
                "Are you ABSOLUTELY sure you want to continue?\n\n"
                "It is recommended to create a manual backup first!"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            reply2 = QMessageBox.question(
                self, tr("Final Confirmation"),
                tr("This action cannot be undone easily.\n\n"
                "Do you really want to restore the entire system?"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply2 != QMessageBox.Yes:
                return

            ed = self.editor
            out = self.store.restore(self.store.load(backup_file),
                                     currency=getattr(ed, "currency_manager", None),
                                     config=self.config_manager)
            if out["commands"] is not None:
                ed.replace_commands(out["commands"])
            if out["users"] is not None and hasattr(ed, 'user_currency_tab'):
                ed.user_currency_tab.populate_table()
            if out["moderators"] and hasattr(ed, 'twitch_tab'):
                ed.twitch_tab.update_moderators_display_only()
            if out["ranks"] and hasattr(ed, 'ranks_tab'):
                ed.ranks_tab.load_ranks()
            ed.update_commands()

            QMessageBox.information(
                self, tr("Restoration Complete"),
                tr("System has been successfully restored from backup!\n\n"
                "Please restart the application to ensure all changes take effect."))
        except Exception as e:
            print(f"Error during comprehensive restoration: {e}")
            QMessageBox.critical(self, tr("Restoration Failed"),
                                 tr('Failed to restore system from backup:\n\n{0}').format(str(e)))

    def show_info(self, backup_file):
        try:
            data = self.store.load(backup_file)
            dialog = QDialog(self)
            dialog.setWindowTitle(tr("Comprehensive Backup Details"))
            dialog.setModal(True)
            dialog.setMinimumSize(600, 400)
            layout = QVBoxLayout(dialog)

            info = data.get('backup_info', {})
            info_group = QGroupBox(tr("Backup Information"))
            info_layout = QVBoxLayout(info_group)
            info_label = QLabel(tr('\n            <b>Timestamp:</b> {0}\n            <b>Version:</b> {1}\n            <b>Description:</b> {2}\n            ').format(info.get('timestamp', 'Unknown'), info.get('version', 'Unknown'), info.get('description', 'Unknown')))
            info_label.setTextFormat(1)  # Rich text
            info_layout.addWidget(info_label)
            layout.addWidget(info_group)

            content_group = QGroupBox(tr("Content Summary"))
            content_layout = QVBoxLayout(content_group)
            content_label = QLabel(tr('\n            <b>Commands:</b> {0}\n            <b>Currency Users:</b> {1}\n            <b>Moderators:</b> {2}\n            <b>Ranks:</b> {3}\n            ').format(len(data.get('commands', [])), len(data.get('currency_users', {})), len(data.get('moderators', {}).get('manual', [])), len(data.get('ranks', []))))
            content_label.setTextFormat(1)  # Rich text
            content_layout.addWidget(content_label)
            layout.addWidget(content_group)

            buttons = QDialogButtonBox(QDialogButtonBox.Ok)
            buttons.accepted.connect(dialog.accept)
            layout.addWidget(buttons)
            dialog.exec_()
        except Exception as e:
            print(f"Error showing comprehensive backup info: {e}")
            QMessageBox.warning(self, tr("Error"), tr('Failed to show backup details:\n\n{0}').format(str(e)))
