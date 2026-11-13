# -*- coding: utf-8 -*-
"""Themed frame around an original tab.

Python 3.8 / PyQt5.
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel
from ui.i18n import tr
from ui.theme.style import (palette_for)
from ui.theme.widgets import (_scroll_wrap)


class ThemedTabView(QWidget):
    """Themed frame around an original tab widget (topbar + content).

    With `content`, that widget is shown instead of the original tab (which
    is kept, hidden, so switching back to classic can restore it)."""

    def __init__(self, parent, tab_widget, original_tab, title, subtitle="", content=None):
        super(ThemedTabView, self).__init__(parent)
        self.editor = parent
        self.tab_widget = tab_widget
        self.original_tab = original_tab
        self.content = content
        self.pal = palette_for(self.editor.theme)
        self._build(title, subtitle)

    def _build(self, title, subtitle):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(54)
        th = QHBoxLayout(top)
        th.setContentsMargins(18, 0, 18, 0)
        th.setSpacing(12)
        t = QLabel(tr(title))
        t.setObjectName("topTitle")
        th.addWidget(t)
        if subtitle:
            c = QLabel(tr(subtitle))
            c.setObjectName("crumb")
            th.addWidget(c)
        th.addStretch(1)
        if self.content is not None and hasattr(self.content, "topbar_widgets"):
            for w in self.content.topbar_widgets():
                th.addWidget(w)
        root.addWidget(top)

        body = QWidget()
        body.setObjectName("themedBody")
        body.setStyleSheet("QWidget#themedBody{background:%s;}" % self.pal["bg"])
        bv = QVBoxLayout(body)
        bv.setSpacing(0)
        # Re-parent the original tab into the themed body. No blanket
        # "QWidget{background}" on it any more: that painted every label and
        # input of the tab and survived theme switches.
        self.original_tab.setParent(body)
        self.original_tab.setStyleSheet("")
        if self.content is not None:
            bv.setContentsMargins(0, 0, 0, 0)
            self.original_tab.hide()
            bv.addWidget(self.content, 1)
        else:
            bv.setContentsMargins(16, 14, 16, 14)
            self.original_tab.show()
            bv.addWidget(self.original_tab, 1)
        root.addWidget(_scroll_wrap(body), 1)

    def highlight_tab(self, idx):
        pass
