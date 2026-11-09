"""The classic Commands table as a Qt model over CommandRepository (step 4.4).

Before, the classic tab was a QTableWidget: a second copy of every command
as text cells, kept in sync by hand (update_table / populate_table /
_write_row_to_table). Now the table view reads the repository directly:

- repository events -> model signals (dataChanged for edited rows, a reset
  for loads / inserts / removals);
- an edited cell -> repo.update(); a value the repository rejects (letters
  in Cost) is simply not stored, so the cell shows the stored value again;
- ``edited(row, changes)`` tells the editor what was stored, so it can save
  commands.json and push the new snapshot to the bot.

Python 3.8 / PyQt5.
"""
from PyQt5.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal

from core.commands import FIELDS


def display_text(cmd, key):
    """Text of one cell, as the classic table always showed it."""
    value = cmd.get(key, "")
    if key == "Enabled":
        return "✓" if value else "✗"
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


class CommandsTableModel(QAbstractTableModel):
    edited = pyqtSignal(int, dict)      # row, {field: stored value}

    def __init__(self, repo, parent=None):
        super(CommandsTableModel, self).__init__(parent)
        self.repo = repo
        repo.subscribe(self._on_repo_event)

    def detach(self):
        self.repo.unsubscribe(self._on_repo_event)

    # -- repository -> views ----------------------------------------------------
    def _on_repo_event(self, event, rows):
        if event == "changed" and rows:
            last = self.columnCount() - 1
            for row in rows:
                if 0 <= row < self.rowCount():
                    self.dataChanged.emit(self.index(row, 0), self.index(row, last))
            return
        # loads, inserts and removals: the repository has already changed,
        # so a reset (not begin/endInsertRows) is the honest notification
        self.beginResetModel()
        self.endResetModel()

    # -- QAbstractTableModel --------------------------------------------------------
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.repo.items)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(FIELDS)

    def field(self, column):
        return FIELDS[column] if 0 <= column < len(FIELDS) else None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        cmd = self.repo.get(index.row())
        key = self.field(index.column())
        if cmd is None or key is None:
            return None
        return display_text(cmd, key)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.field(section)
        return str(section + 1)

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole:
            return False
        key = self.field(index.column())
        if key is None:
            return False
        done = self.repo.update(index.row(), {key: value})
        if not done:
            # rejected or unchanged: show the stored value again
            self.dataChanged.emit(index, index)
            return False
        self.edited.emit(index.row(), dict(done))
        return True
