# -*- coding: utf-8 -*-
"""Group Settings tab: per-group queue / audio channel settings.

Python 3.8 / PyQt5.
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QPushButton, QHBoxLayout, QMessageBox,
                             QCheckBox, QSpinBox, QLabel)
from PyQt5.QtCore import Qt


# (header, tooltip)
_COLUMNS = [
    ("Group", "Command group (the Group field of commands)"),
    ("Queue", "Play this group's commands one after another instead of at once"),
    ("Max size", "How many commands may wait (including the one playing). 0 = unlimited.\n"
                 "When full, new commands are rejected and points refunded."),
    ("Channel", "Audio channel. 0 = shared channel (sounds may cut each other).\n"
                "1-32 = own channel: plays in parallel with other groups."),
    ("Persist", "Keep waiting commands after a restart of the program"),
    ("Announce", "Tell the viewer their position when a command is queued\n"
                 "(only if something is already waiting)"),
]


class GroupSettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.config_manager = parent.config_manager
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        hint = QLabel(
            "Queued groups play one command at a time. Give music its own group "
            "(e.g. SONG) with its own channel so it never cuts other sounds. "
            "Changes apply to the running bot immediately — a playing track is not interrupted.")
        hint.setWordWrap(True)
        hint.setObjectName("statusLabel")
        layout.addWidget(hint)

        self.table = QTableWidget()
        self.table.setColumnCount(len(_COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in _COLUMNS])
        for i, (_h, tip) in enumerate(_COLUMNS):
            self.table.horizontalHeaderItem(i).setToolTip(tip)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Reload")
        self.refresh_btn.setToolTip("Discard unsaved edits and reload groups")
        self.refresh_btn.clicked.connect(self.refresh_groups)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch(1)
        self.status = QLabel("")
        self.status.setObjectName("statusLabel")
        btn_layout.addWidget(self.status)
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("primaryBtn")
        self.save_btn.clicked.connect(self.save_settings)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.refresh_groups()

    @staticmethod
    def _centered(widget):
        cell = QWidget()
        lay = QHBoxLayout(cell)
        lay.addWidget(widget)
        lay.setAlignment(Qt.AlignCenter)
        lay.setContentsMargins(0, 0, 0, 0)
        return cell

    def _all_groups(self):
        """Groups from commands plus configured categories (case-insensitive
        merge: the configured spelling wins)."""
        categories = self.config_manager.get_audio_categories() or {}
        by_upper = {}
        for name in categories:
            by_upper[str(name).upper()] = name
        for cmd in self.parent.commands:
            g = cmd.get("Group", "GENERAL") or "GENERAL"
            by_upper.setdefault(str(g).upper(), g)
        return sorted(by_upper.values(), key=lambda s: str(s).upper())

    def refresh_groups(self):
        categories = self.config_manager.get_audio_categories() or {}
        groups = self._all_groups()
        self._rows = []
        self.table.setRowCount(len(groups))
        for i, group in enumerate(groups):
            cat = categories.get(group, {})
            if not isinstance(cat, dict):
                cat = {}
            name_item = QTableWidgetItem(group)
            name_item.setFlags(Qt.ItemIsEnabled)
            n_cmds = sum(1 for c in self.parent.commands
                         if str(c.get("Group", "")).upper() == str(group).upper())
            name_item.setToolTip("%d command(s)" % n_cmds)
            self.table.setItem(i, 0, name_item)

            queue = QCheckBox()
            queue.setChecked(bool(cat.get("queue_enabled", False)))
            size = QSpinBox()
            size.setRange(0, 1000)
            size.setSpecialValueText("unlimited")
            size.setValue(int(cat.get("max_queue_size", 0) or 0))
            channel = QSpinBox()
            channel.setRange(0, 32)
            channel.setSpecialValueText("shared")
            channel.setValue(int(cat.get("audio_channel", 0) or 0))
            persist = QCheckBox()
            persist.setChecked(bool(cat.get("persist_queue", False)))
            announce = QCheckBox()
            announce.setChecked(bool(cat.get("announce_enqueue", False)))

            widgets = (queue, size, channel, persist, announce)
            for col, w in enumerate(widgets, start=1):
                w.setToolTip(_COLUMNS[col][1])
                self.table.setCellWidget(i, col, self._centered(w))

            # Queue-only options make no sense without a queue
            def sync(_=None, q=queue, deps=(size, persist, announce)):
                for d in deps:
                    d.setEnabled(q.isChecked())
            queue.toggled.connect(sync)
            sync()
            self._rows.append((group, widgets))
        self.status.setText("")

    def save_settings(self):
        categories = self.config_manager.get_audio_categories() or {}
        for group, (queue, size, channel, persist, announce) in getattr(self, "_rows", []):
            entry = categories.setdefault(group, {})
            entry["queue_enabled"] = queue.isChecked()
            entry["max_queue_size"] = size.value()
            entry["audio_channel"] = channel.value()
            entry["persist_queue"] = persist.isChecked()
            entry["announce_enqueue"] = announce.isChecked()

        # Two queued groups on the same dedicated channel would cut each other.
        used = {}
        for group, (queue, size, channel, persist, announce) in getattr(self, "_rows", []):
            if channel.value() > 0:
                used.setdefault(channel.value(), []).append(group)
        clashes = ["channel %d: %s" % (ch, ", ".join(gs)) for ch, gs in sorted(used.items()) if len(gs) > 1]

        self.config_manager.save_audio_categories(categories)

        # Apply to the running bot without a restart (no-op if not connected)
        if hasattr(self.parent, "twitch_tab") and self.parent.twitch_tab:
            self.parent.twitch_tab.reload_bot_audio_categories()
        qc = getattr(self.parent, "queue_control_tab", None)
        if qc is not None:
            qc.refresh_groups()

        if clashes:
            QMessageBox.warning(
                self, "Shared audio channel",
                "Saved. Note: these groups share a dedicated channel and will cut "
                "each other off:\n\n" + "\n".join(clashes))
            self.status.setText("Saved (channel clash)")
        else:
            self.status.setText("Saved ✓ — applied to the running bot")
