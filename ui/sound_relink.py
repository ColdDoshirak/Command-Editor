# -*- coding: utf-8 -*-
"""The "Fix sound paths" dialog (logic: core/sound_paths.py).

Python 3.8 compatible.
"""
from core.sound_paths import (common_folder, find_missing, plan_from_folders,
                              plan_prefix_replace, plan_to_changes, remember_folder)
from ui.i18n import tr


# ---------------------------------------------------------------------------

def _qt():
    from PyQt5 import QtWidgets, QtCore, QtGui
    return QtWidgets, QtCore, QtGui


def make_relink_dialog(editor):
    """Build the "Fix sound paths" dialog."""
    QtWidgets, QtCore, QtGui = _qt()
    Qt = QtCore.Qt

    class _Dialog(QtWidgets.QDialog):
        def __init__(self, editor):
            super(_Dialog, self).__init__(editor)
            self.editor = editor
            self.plan = []
            self.used_folder = None
            self.setWindowTitle(tr("Fix sound paths"))
            self.resize(900, 520)
            v = QtWidgets.QVBoxLayout(self)

            self.summary = QtWidgets.QLabel("")
            self.summary.setWordWrap(True)
            v.addWidget(self.summary)

            row = QtWidgets.QHBoxLayout()
            b_search = QtWidgets.QPushButton("Search in folder…")
            b_search.setToolTip(tr("Pick the folder the sounds were moved to. "
                                "Sub-folders are searched too; files are matched by name."))
            b_search.clicked.connect(self.search_folder)
            row.addWidget(b_search)
            row.addSpacing(16)
            row.addWidget(QtWidgets.QLabel("Replace folder:"))
            self.old_prefix = QtWidgets.QLineEdit()
            self.old_prefix.setPlaceholderText(tr("old folder, e.g. D:/Sounds"))
            row.addWidget(self.old_prefix, 1)
            row.addWidget(QtWidgets.QLabel("→"))
            self.new_prefix = QtWidgets.QLineEdit()
            self.new_prefix.setPlaceholderText(tr("new folder"))
            row.addWidget(self.new_prefix, 1)
            b_browse = QtWidgets.QPushButton("…")
            b_browse.setToolTip(tr("Choose the new folder"))
            b_browse.clicked.connect(self._browse_new_prefix)
            row.addWidget(b_browse)
            b_prev = QtWidgets.QPushButton("Preview")
            b_prev.clicked.connect(self.preview_prefix)
            row.addWidget(b_prev)
            v.addLayout(row)

            self.table = QtWidgets.QTableWidget(0, 4)
            self.table.setHorizontalHeaderLabels([tr("Command"), tr("Field"), tr("Old path"), tr("New path")])
            hh = self.table.horizontalHeader()
            hh.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            hh.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            hh.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
            hh.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
            self.table.verticalHeader().setVisible(False)
            self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            v.addWidget(self.table, 1)

            bottom = QtWidgets.QHBoxLayout()
            self.status = QtWidgets.QLabel("")
            bottom.addWidget(self.status, 1)
            self.apply_btn = QtWidgets.QPushButton("Apply")
            self.apply_btn.setEnabled(False)
            self.apply_btn.clicked.connect(self.apply)
            bottom.addWidget(self.apply_btn)
            close = QtWidgets.QPushButton("Close")
            close.clicked.connect(self.reject)
            bottom.addWidget(close)
            v.addLayout(bottom)
            self.show_missing()

        # -- data ---------------------------------------------------------
        def show_missing(self):
            missing = find_missing(self.editor.commands)
            if not missing:
                self.summary.setText(tr("All sound files of all commands exist. Nothing to fix."))
            else:
                self.summary.setText(
                    tr("%d sound path(s) point to files that do not exist (moved or renamed folder?). "
                    "Use “Search in folder…” to find them by name, or replace the old folder "
                    "with the new one.") % len(missing))
                self.old_prefix.setText(common_folder([m[2] for m in missing]))
            self.set_plan([{"row": r, "key": k, "old": p, "new": None, "ambiguous": False}
                           for r, k, p in missing])

        def set_plan(self, plan):
            self.plan = plan
            self.table.setRowCount(len(plan))
            found = 0
            red, amber = QtGui.QColor("#DC2626"), QtGui.QColor("#D97706")
            for i, p in enumerate(plan):
                cmd = self.editor.commands[p["row"]] if p["row"] < len(self.editor.commands) else {}
                self.table.setItem(i, 0, QtWidgets.QTableWidgetItem(cmd.get("Command", "")))
                self.table.setItem(i, 1, QtWidgets.QTableWidgetItem(
                    "Sound" if p["key"] == "SoundFile" else "FK sound"))
                self.table.setItem(i, 2, QtWidgets.QTableWidgetItem(p["old"]))
                if p["new"]:
                    found += 1
                    it = QtWidgets.QTableWidgetItem(p["new"])
                    if p["ambiguous"]:
                        it.setForeground(amber)
                        it.setToolTip(tr("Several files with this name were found; "
                                      "the one in the most similar folder was picked."))
                else:
                    it = QtWidgets.QTableWidgetItem("not found")
                    it.setForeground(red)
                self.table.setItem(i, 3, it)
            amb = sum(1 for p in plan if p["new"] and p["ambiguous"])
            text = "%d of %d can be fixed" % (found, len(plan)) if plan else ""
            if amb:
                text += " · %d ambiguous (orange) — check them" % amb
            self.status.setText(text)
            self.apply_btn.setEnabled(found > 0)

        # -- actions ------------------------------------------------------
        def search_folder(self):
            start = ""
            folders = self.editor.config_manager.get_sound_folders()
            if folders:
                start = folders[0]
            folder = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Folder with the moved sounds", start, QtWidgets.QFileDialog.ShowDirsOnly)
            if not folder:
                return
            QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                plan = plan_from_folders(self.editor.commands, [folder])
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
            self.used_folder = folder
            self.set_plan(plan)

        def _browse_new_prefix(self):
            folder = QtWidgets.QFileDialog.getExistingDirectory(
                self, "New sound folder", self.new_prefix.text(), QtWidgets.QFileDialog.ShowDirsOnly)
            if folder:
                self.new_prefix.setText(folder)
                self.preview_prefix()

        def preview_prefix(self):
            old, new = self.old_prefix.text().strip(), self.new_prefix.text().strip()
            if not old or not new:
                self.status.setText(tr("Enter both the old and the new folder."))
                return
            self.used_folder = new
            self.set_plan(plan_prefix_replace(self.editor.commands, old, new))

        def apply(self):
            changes = plan_to_changes(self.plan)
            if not changes:
                return
            n = self.editor.apply_bulk_command_edits(changes)
            if self.used_folder:
                cm = self.editor.config_manager
                cm.set_sound_folders(remember_folder(cm.get_sound_folders(), self.used_folder))
            QtWidgets.QMessageBox.information(
                self, "Fix sound paths",
                "%d path(s) updated and saved.\n\nThe folder is remembered: next time the "
                "program starts, sounds moved inside it are re-linked automatically." % n)
            self.show_missing()

    return _Dialog(editor)
