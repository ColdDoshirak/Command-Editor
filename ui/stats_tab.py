"""The Stats tab (2.0): popular commands, the points economy, the viewers.

Counts by day come from core/stats.py (CurrencyManager.stats); all-time use
counts from the commands, balances and hours from the currency users.

Python 3.8 / PyQt5.
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox,
                             QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
                             QAbstractItemView)

from core import variables

PERIODS = (("Today", 1), ("Last 7 days", 7), ("Last 30 days", 30), ("Last 90 days", 90))
TOP = 10


def _table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    for c in range(1, len(headers)):
        t.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.NoSelection)
    return t


def _fill(table, rows):
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            it = QTableWidgetItem(str(value))
            if c:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(r, c, it)


class StatsTab(QWidget):
    def __init__(self, editor):
        super(StatsTab, self).__init__()
        self.editor = editor
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Period:"))
        self.period = QComboBox()
        for label, days in PERIODS:
            self.period.addItem(label, days)
        self.period.setCurrentIndex(1)
        self.period.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.period)
        top.addStretch(1)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        top.addWidget(self.refresh_btn)
        v.addLayout(top)

        eco = QGroupBox("Points")
        g = QGridLayout(eco)
        self.values = {}
        items = (("earned", "Earned by watching"), ("rewards", "Raid / sub rewards"),
                 ("spent", "Spent on commands"), ("given", "Given between viewers"),
                 ("circulation", "Held by viewers now"), ("viewers", "Viewers in the system"),
                 ("active", "Chatting now (10 min)"))
        for i, (key, label) in enumerate(items):
            g.addWidget(QLabel(label), i // 4 * 2, i % 4)
            val = QLabel("-")
            val.setObjectName("statValue")
            f = val.font()
            f.setPointSize(f.pointSize() + 4)
            f.setBold(True)
            val.setFont(f)
            g.addWidget(val, i // 4 * 2 + 1, i % 4)
            self.values[key] = val
        v.addWidget(eco)

        tables = QHBoxLayout()
        box = QGroupBox("Commands")
        bl = QVBoxLayout(box)
        self.commands_table = _table(["Command", "In the period", "All time"])
        bl.addWidget(self.commands_table)
        tables.addWidget(box, 2)
        box = QGroupBox("Top by points")
        bl = QVBoxLayout(box)
        self.points_table = _table(["Viewer", "Points"])
        bl.addWidget(self.points_table)
        tables.addWidget(box, 1)
        box = QGroupBox("Top by watch time")
        bl = QVBoxLayout(box)
        self.hours_table = _table(["Viewer", "Hours"])
        bl.addWidget(self.hours_table)
        tables.addWidget(box, 1)
        v.addLayout(tables, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(30000)
        self._timer.timeout.connect(self.refresh)

    def showEvent(self, event):
        super(StatsTab, self).showEvent(event)
        self.refresh()
        self._timer.start()

    def hideEvent(self, event):
        super(StatsTab, self).hideEvent(event)
        self._timer.stop()

    def refresh(self, *_):
        e = self.editor
        cm = getattr(e, "currency_manager", None)
        days = self.period.currentData() or 7
        s = cm.stats.summary(days) if cm is not None and getattr(cm, "stats", None) else {}
        fmt = variables.format_points
        for key in ("earned", "rewards", "spent", "given"):
            self.values[key].setText(fmt(s.get(key, 0)))
        users = []
        if cm is not None:
            with cm.users_lock:
                users = [(n, float(d.get("points", 0) or 0), float(d.get("hours", 0) or 0))
                         for n, d in cm.users.items() if isinstance(d, dict)]
        self.values["circulation"].setText(fmt(sum(u[1] for u in users)))
        self.values["viewers"].setText(str(len(users)))
        active = getattr(getattr(e, "twitch_tab", None), "active_users", []) or []
        self.values["active"].setText(str(len(active)))

        period = (s.get("commands") or {})
        all_time = {c.get("Command", ""): int(c.get("Count", 0) or 0) for c in getattr(e, "commands", [])}
        names = set(period) | {n for n, c in all_time.items() if c}
        rows = sorted(((n, period.get(n, 0), all_time.get(n, 0)) for n in names),
                      key=lambda r: (-r[1], -r[2], r[0]))
        _fill(self.commands_table, rows[:50])
        _fill(self.points_table, [(n, fmt(p)) for n, p, _h in sorted(users, key=lambda u: -u[1])[:TOP]])
        _fill(self.hours_table, [(n, fmt(h)) for n, _p, h in sorted(users, key=lambda u: -u[2])[:TOP]])
