"""The "Test command" dialog (2.0): what would happen if a viewer wrote this
message - a dry run (core/command_test.py), nothing is charged or counted.

Python 3.8 / PyQt5.
"""
from html import escape

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
                             QDoubleSpinBox, QTextBrowser, QPushButton, QDialogButtonBox)

from core import permissions
from core.command_test import simulate
from core.currency_manager import CurrencyManager
from ui.i18n import tr


class CommandTestDialog(QDialog):
    def __init__(self, editor, row):
        super(CommandTestDialog, self).__init__(editor)
        self.editor = editor
        self.cmd = editor.commands[row]
        self.setWindowTitle(tr("Test %s") % self.cmd.get("Command", ""))
        self.resize(520, 420)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.message = QLineEdit("%s " % self.cmd.get("Command", ""))
        self.user = QLineEdit("viewer")
        self.role = QComboBox()
        self.role.addItems(permissions.LEVELS)
        self.points = QDoubleSpinBox()
        self.points.setDecimals(2)
        self.points.setRange(0, CurrencyManager.MAX_BALANCE)
        self.points.setValue(1000)
        form.addRow(tr("Message in chat"), self.message)
        form.addRow(tr("Viewer"), self.user)
        form.addRow(tr("Viewer is"), self.role)
        form.addRow(tr("Viewer's points"), self.points)
        v.addLayout(form)
        self.result = QTextBrowser()
        v.addWidget(self.result, 1)
        row_b = QHBoxLayout()
        self.play_btn = QPushButton(tr("Play the sound"))
        self.play_btn.clicked.connect(self._play)
        row_b.addWidget(self.play_btn)
        row_b.addStretch(1)
        v.addLayout(row_b)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        v.addWidget(box)
        for w in (self.message, self.user):
            w.textChanged.connect(self.run)
        self.role.currentIndexChanged.connect(self.run)
        self.points.valueChanged.connect(self.run)
        self.run()

    def _currency_name(self):
        try:
            return self.editor.currency_manager.get_currency_name()
        except Exception:
            return "points"

    def run(self, *_):
        bot = getattr(getattr(self.editor, "twitch_tab", None), "bot", None)
        channel = getattr(bot, "channel", "") or "yourchannel"
        self.last = r = simulate(self.cmd, self.message.text(), user=self.user.text().strip() or "viewer",
                                 role=self.role.currentText(), points=self.points.value(),
                                 currency=self._currency_name(), channel=channel)
        ok = not r["problems"]
        parts = ['<p><b style="color:%s">%s</b></p>' % (
            "#16a34a" if ok else "#dc2626",
            "It would run." if ok else "It would not run as expected:")]
        if r["problems"]:
            parts.append("<ul>%s</ul>" % "".join("<li>%s</li>" % escape(p) for p in r["problems"]))
        if r["cost"]:
            parts.append("<p>Cost: %d (taken only when it runs)</p>" % r["cost"])
        if r["lines"]:
            parts.append("<p><b>The bot answers in chat:</b></p>")
            for line in r["lines"]:
                parts.append("<p><i>(pause)</i></p>" if line is None else "<p>%s</p>" % escape(line))
        if r["sound"]:
            parts.append("<p>Sound: %s%s</p>" % (escape(r["sound"]), "" if r["sound_ok"] else " (missing)"))
        self.result.setHtml("".join(parts))
        self.play_btn.setEnabled(bool(r["sound_ok"]))
        return r

    def _play(self):
        r = self.last
        if r.get("sound_ok"):
            self.editor.preview.toggle(r["sound"], self.cmd.get("Volume", 100), True)
