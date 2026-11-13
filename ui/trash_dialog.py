"""The Trash dialog (2.0): deleted commands, put back or emptied.

Python 3.8 / PyQt5.
"""
from datetime import datetime

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel,
                             QMessageBox)
from ui.i18n import tr


class TrashDialog(QDialog):
    def __init__(self, editor):
        super(TrashDialog, self).__init__(editor)
        self.editor = editor
        self.setWindowTitle(tr("Trash - deleted commands"))
        self.resize(460, 380)
        v = QVBoxLayout(self)
        v.addWidget(QLabel(tr("Deleted commands, the newest first (at most 50). "
                           "Restore puts one back where it was.")))
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self.restore())
        v.addWidget(self.list, 1)
        h = QHBoxLayout()
        self.restore_btn = QPushButton(tr("Restore"))
        self.restore_btn.clicked.connect(self.restore)
        self.empty_btn = QPushButton(tr("Empty the trash"))
        self.empty_btn.clicked.connect(self.empty)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.accept)
        h.addWidget(self.restore_btn)
        h.addWidget(self.empty_btn)
        h.addStretch(1)
        h.addWidget(close)
        v.addLayout(h)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for e in self.editor.command_trash.items:
            cmd = e["command"]
            when = datetime.fromtimestamp(e.get("deleted", 0)).strftime("%H:%M %d.%m.%Y")
            extra = cmd.get("Response", "") or cmd.get("SoundFile", "")
            extra = (" - " + extra.splitlines()[0][:40]) if extra else ""
            self.list.addItem("%s%s   (deleted %s)" % (cmd.get("Command", "?"), extra, when))
        has = self.list.count() > 0
        if has:
            self.list.setCurrentRow(0)
        self.restore_btn.setEnabled(has)
        self.empty_btn.setEnabled(has)

    def restore(self):
        i = self.list.currentRow()
        if i >= 0:
            self.editor.undo_delete(i)
            self.refresh()

    def empty(self):
        if QMessageBox.question(self, tr("Empty the trash"),
                                tr("Delete these commands for good?"),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.editor.command_trash.clear()
            self.refresh()
