# -*- coding: utf-8 -*-
"""Re-linking of sound files that were moved or renamed folders.

Commands store absolute sound paths. When the user moves the sound folder,
every command breaks. This module finds the missing files and re-links them:

  * by folder search — index a folder (recursively) and match missing files
    by file name; when several files share a name the one whose parent
    folders match the old path best wins (ties are reported as ambiguous);
  * by prefix replace — "D:/Old/Sounds" -> "E:/Stream/Sounds".

Folders used successfully are remembered in config.json ("sound_folders"),
and on start-up missing sounds are re-linked from them automatically.

The pure functions below have no Qt dependency (tested in
tests/test_sound_paths.py). Python 3.8 compatible.
"""
import os

SOUND_KEYS = ("SoundFile", "FKSoundFile")
SOUND_EXTS = (".wav", ".mp3", ".ogg", ".flac")
MAX_REMEMBERED = 5


def _norm(p):
    return os.path.normcase(os.path.normpath(p))


def _parts(p):
    p = os.path.normpath(p).replace("\\", "/")
    return [x.lower() for x in p.split("/") if x]


def find_missing(commands, exists=os.path.exists):
    """[(row, key, path)] for every non-empty sound path that does not exist."""
    out = []
    for row, cmd in enumerate(commands):
        for key in SOUND_KEYS:
            path = str(cmd.get(key, "") or "").strip()
            if path and not exists(path):
                out.append((row, key, path))
    return out


def index_folder(folder, exts=SOUND_EXTS):
    """{lower-case file name: [full paths]} for sound files under folder."""
    idx = {}
    for root, _dirs, files in os.walk(folder):
        for name in files:
            if os.path.splitext(name)[1].lower() in exts:
                idx.setdefault(name.lower(), []).append(os.path.join(root, name))
    return idx


def _tail_score(old, new):
    """How many trailing path components (after the file name) match."""
    a, b = _parts(old)[:-1], _parts(new)[:-1]
    n = 0
    while n < len(a) and n < len(b) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def best_match(old_path, candidates):
    """(path, ambiguous) — the candidate whose folders match old_path best."""
    if not candidates:
        return None, False
    if len(candidates) == 1:
        return candidates[0], False
    scored = sorted(((_tail_score(old_path, c), c) for c in candidates),
                    key=lambda t: (-t[0], t[1].lower()))
    ambiguous = scored[0][0] == scored[1][0]
    return scored[0][1], ambiguous


def plan_from_folders(commands, folders, exists=os.path.exists, index_cache=None):
    """Plan re-links of missing sounds from one or more folders.

    Returns a list of dicts: row, key, old, new (None if not found),
    ambiguous (bool). Earlier folders win over later ones.
    """
    missing = find_missing(commands, exists)
    if not missing:
        return []
    indexes = []
    for f in folders:
        if not f or not os.path.isdir(f):
            continue
        if index_cache is not None and f in index_cache:
            indexes.append(index_cache[f])
            continue
        idx = index_folder(f)
        if index_cache is not None:
            index_cache[f] = idx
        indexes.append(idx)
    plan = []
    for row, key, old in missing:
        name = os.path.basename(old.replace("\\", "/")).lower()
        new, ambiguous = None, False
        for idx in indexes:
            new, ambiguous = best_match(old, idx.get(name, []))
            if new:
                break
        plan.append({"row": row, "key": key, "old": old, "new": new, "ambiguous": ambiguous})
    return plan


def plan_prefix_replace(commands, old_prefix, new_prefix, only_missing=True,
                        exists=os.path.exists):
    """Plan replacing a folder prefix. Only targets that exist are accepted."""
    if not old_prefix:
        return []
    op = _norm(old_prefix).rstrip("\\/")
    plan = []
    for row, cmd in enumerate(commands):
        for key in SOUND_KEYS:
            path = str(cmd.get(key, "") or "").strip()
            if not path:
                continue
            if only_missing and exists(path):
                continue
            np_ = _norm(path)
            if np_ != op and not np_.startswith(op + os.sep):
                continue
            rest = os.path.normpath(path)[len(op):].lstrip("\\/")
            new = os.path.join(new_prefix, rest) if rest else new_prefix
            plan.append({"row": row, "key": key, "old": path,
                         "new": new if exists(new) else None, "ambiguous": False})
    return plan


def common_folder(paths):
    """Deepest folder shared by all paths ('' if none)."""
    dirs = [os.path.dirname(os.path.normpath(p)) for p in paths if p]
    if not dirs:
        return ""
    try:
        return os.path.commonpath(dirs)
    except ValueError:  # different drives
        return dirs[0]


def plan_to_changes(plan):
    """{row: {key: new}} for the plan entries that have a target."""
    changes = {}
    for p in plan:
        if p.get("new"):
            changes.setdefault(p["row"], {})[p["key"]] = p["new"]
    return changes


def remember_folder(folders, folder):
    """New list with folder first (deduplicated, capped)."""
    out = [folder]
    for f in folders or []:
        if f and _norm(f) != _norm(folder):
            out.append(f)
    return out[:MAX_REMEMBERED]


# ---------------------------------------------------------------------------
# Qt dialog
# ---------------------------------------------------------------------------

def _qt():
    from PyQt5 import QtWidgets, QtCore, QtGui
    return QtWidgets, QtCore, QtGui


def make_relink_dialog(editor):
    """Build the "Fix sound paths" dialog (Qt is imported lazily so the pure
    functions above stay importable in tests without a display)."""
    QtWidgets, QtCore, QtGui = _qt()
    Qt = QtCore.Qt

    class _Dialog(QtWidgets.QDialog):
        def __init__(self, editor):
            super(_Dialog, self).__init__(editor)
            self.editor = editor
            self.plan = []
            self.used_folder = None
            self.setWindowTitle("Fix sound paths")
            self.resize(900, 520)
            v = QtWidgets.QVBoxLayout(self)

            self.summary = QtWidgets.QLabel("")
            self.summary.setWordWrap(True)
            v.addWidget(self.summary)

            row = QtWidgets.QHBoxLayout()
            b_search = QtWidgets.QPushButton("Search in folder…")
            b_search.setToolTip("Pick the folder the sounds were moved to. "
                                "Sub-folders are searched too; files are matched by name.")
            b_search.clicked.connect(self.search_folder)
            row.addWidget(b_search)
            row.addSpacing(16)
            row.addWidget(QtWidgets.QLabel("Replace folder:"))
            self.old_prefix = QtWidgets.QLineEdit()
            self.old_prefix.setPlaceholderText("old folder, e.g. D:/Sounds")
            row.addWidget(self.old_prefix, 1)
            row.addWidget(QtWidgets.QLabel("→"))
            self.new_prefix = QtWidgets.QLineEdit()
            self.new_prefix.setPlaceholderText("new folder")
            row.addWidget(self.new_prefix, 1)
            b_browse = QtWidgets.QPushButton("…")
            b_browse.setToolTip("Choose the new folder")
            b_browse.clicked.connect(self._browse_new_prefix)
            row.addWidget(b_browse)
            b_prev = QtWidgets.QPushButton("Preview")
            b_prev.clicked.connect(self.preview_prefix)
            row.addWidget(b_prev)
            v.addLayout(row)

            self.table = QtWidgets.QTableWidget(0, 4)
            self.table.setHorizontalHeaderLabels(["Command", "Field", "Old path", "New path"])
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
                self.summary.setText("All sound files of all commands exist. Nothing to fix.")
            else:
                self.summary.setText(
                    "%d sound path(s) point to files that do not exist (moved or renamed folder?). "
                    "Use “Search in folder…” to find them by name, or replace the old folder "
                    "with the new one." % len(missing))
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
                        it.setToolTip("Several files with this name were found; "
                                      "the one in the most similar folder was picked.")
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
                self.status.setText("Enter both the old and the new folder.")
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
