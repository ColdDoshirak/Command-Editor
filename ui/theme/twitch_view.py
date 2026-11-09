# -*- coding: utf-8 -*-
"""The themed Twitch tab (sidebar and spreadsheet layouts).

Python 3.8 / PyQt5.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton)
from PyQt5.QtCore import Qt, QTimer
from ui.theme.style import (palette_for)
from ui.theme.widgets import (LogoBadge, _held, _overflow_toolbar, _scroll_wrap, _toolbar_stretch)


# ---------------------------------------------------------------------------
# Themed Twitch views (Design 1 sidebar / Design 9 spreadsheet)
#
# These re-parent the ORIGINAL TwitchTab widgets into a new themed layout, so
# every method on TwitchTab (chat, viewers, moderators, status, connect) keeps
# working unchanged. The classic TwitchTab is swapped out of the tab widget and
# re-parented back to the main window when the theme changes.
# ---------------------------------------------------------------------------

class TwitchThemedBase(QWidget):
    """Shared helpers for the two themed Twitch layouts."""

    def __init__(self, parent, tab_widget, twitch_tab):
        super(TwitchThemedBase, self).__init__(parent)
        self.editor = parent
        self.tab_widget = tab_widget
        self.twitch_tab = twitch_tab
        self.pal = palette_for(getattr(parent, "theme", "sidebar"))
        # Status labels (re-parented from the original tab into the status bar)
        self.connection_status = twitch_tab.connection_status
        self.stream_status = twitch_tab.stream_status
        self.active_viewers_count = twitch_tab.active_viewers_count
        self.all_viewers_count = twitch_tab.all_viewers_count

    # -- auth pill -------------------------------------------------------
    def _build_auth_pill(self):
        pill = QFrame()
        pill.setObjectName("authPill")
        h = QHBoxLayout(pill)
        h.setContentsMargins(11, 5, 11, 5)
        h.setSpacing(7)
        dot = QLabel("\u25cf")
        dot.setObjectName("authDot")
        text = QLabel("Not authenticated")
        text.setObjectName("authText")
        h.addWidget(dot)
        h.addWidget(text)
        self._auth_pill = pill
        self._auth_dot = dot
        self._auth_text = text
        self._apply_auth_state()
        return pill

    def _apply_auth_state(self):
        tt = self.twitch_tab
        authed = bool(tt.config_manager.get_twitch_config().get("access_token"))
        if authed:
            bg = "rgba(22,163,74,0.10)"
            fg = self.pal["green"]
            self._auth_text.setText("Authenticated")
        else:
            bg = "rgba(220,38,38,0.08)"
            fg = self.pal["red"]
            self._auth_text.setText("Not authenticated")
        self._auth_pill.setStyleSheet(
            "QFrame#authPill{background:%s;border:none;}"
            "QLabel{color:%s;font-size:12px;font-weight:500;}" % (bg, fg))
        self._auth_dot.setStyleSheet("color:%s;font-size:9px;" % fg)

    # -- stat strip ------------------------------------------------------
    def _build_stat_strip(self):
        strip = QFrame()
        strip.setObjectName("statStrip")
        strip.setFixedHeight(58)
        h = QHBoxLayout(strip)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(0)
        boxes = [
            ("\u25cf Live", "Stream status", "statLive"),
            ("0", "Active viewers", "statActive"),
            ("0", "All viewers", "statAll"),
            ("0", "Moderators", "statMods"),
        ]
        self._stat_live = self._stat_active = self._stat_all = self._stat_mods = None
        for i, (val, lab, key) in enumerate(boxes):
            box = QFrame()
            box.setObjectName("statBoxLast" if i == len(boxes) - 1 else "statBox")
            boxv = QVBoxLayout(box)
            boxv.setContentsMargins(16, 0, 16, 0)
            boxv.setSpacing(2)
            v = QLabel(val)
            v.setObjectName("statVal")
            l = QLabel(lab)
            boxv.addWidget(v)
            boxv.addWidget(l)
            h.addWidget(box, 1)
            if key == "statLive":
                self._stat_live = v
            elif key == "statActive":
                self._stat_active = v
            elif key == "statAll":
                self._stat_all = v
            elif key == "statMods":
                self._stat_mods = v
        self._stat_strip = strip
        self._update_stat_strip()
        return strip

    def _update_stat_strip(self):
        if getattr(self, "_stat_live", None) is None:
            return
        tt = self.twitch_tab
        live = getattr(tt, "currently_live", False)
        self._stat_live.setText("\u25cf Live" if live else "\u25cb Offline")
        self._stat_live.setStyleSheet(
            "color:%s;font-size:16px;font-weight:600;" %
            (self.pal["green"] if live else self.pal["text3"]))
        self._stat_active.setText(str(len(getattr(tt, "active_users", []) or [])))
        self._stat_all.setText(str(self.all_viewers_count.text().split(":")[-1].strip()))
        self._stat_mods.setText(str(len(getattr(tt, "moderators_list", []) or [])))

    # -- status bar ------------------------------------------------------
    def _build_status_bar(self):
        bar = QFrame()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(30)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(16)
        self.connection_status.setObjectName("statusLabel")
        self.stream_status.setObjectName("statusLabel")
        self.active_viewers_count.setObjectName("statusLabel")
        self.all_viewers_count.setObjectName("statusLabel")
        h.addWidget(self.connection_status)
        h.addWidget(self.stream_status)
        h.addStretch(1)
        h.addWidget(self.active_viewers_count)
        h.addWidget(self.all_viewers_count)
        self._status_bar = bar
        self._update_statusbar()
        return bar

    def _update_statusbar(self):
        tt = self.twitch_tab
        connected = bool(tt.bot and getattr(tt.bot, "is_running", False))
        self.connection_status.setText("connected" if connected else "not connected")
        self.connection_status.setStyleSheet(
            "color:%s;font-size:11.5px;" %
            (self.pal["green"] if connected else self.pal["text3"]))
        self.stream_status.setStyleSheet("color:%s;font-size:11.5px;" % self.pal["text2"])
        self.active_viewers_count.setStyleSheet("color:%s;font-size:11.5px;" % self.pal["text2"])
        self.all_viewers_count.setStyleSheet("color:%s;font-size:11.5px;" % self.pal["text2"])
        self._update_stat_strip()

    # -- panel helpers ---------------------------------------------------
    def _panel(self, title, hint):
        panel = QFrame()
        panel.setObjectName("panel")
        v = QVBoxLayout(panel)
        v.setContentsMargins(14, 12, 14, 14)
        v.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("panelHead")
        head.addWidget(t)
        if hint:
            hh = QLabel(hint)
            hh.setObjectName("panelHint")
            head.addWidget(hh)
        head.addStretch(1)
        v.addLayout(head)
        return panel, v

    def _sync_viewers_tabs(self, idx):
        labels = {0: "All Viewers", 1: "Active Chatters", 2: "Moderators"}
        want = labels.get(idx)
        for i in range(self.twitch_tab.viewers_tabs.count()):
            if self.twitch_tab.viewers_tabs.tabText(i) == want:
                self.twitch_tab.viewers_tabs.setCurrentIndex(i)
                break

    def _build_moderator_controls(self):
        tt = self.twitch_tab
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(tt.add_moderator_input)
        row1.addWidget(tt.add_moderator_button)
        row1.addWidget(tt.remove_moderator_button)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(tt.open_moderators_file_button)
        row2.addWidget(tt.refresh_moderators_button)
        row2.addStretch(1)
        return row1, row2

    def _build_legend(self):
        row = QHBoxLayout()
        row.setSpacing(14)
        for color, label in [
            (self.pal["text3"], "API"),
            (self.pal["green"], "manual"),
            (self.pal["accent"], "both"),
            (self.pal["red"], "excluded"),
        ]:
            li = QHBoxLayout()
            li.setSpacing(5)
            sw = QLabel("\u25cf")
            sw.setStyleSheet("color:%s;font-size:8px;" % color)
            tx = QLabel(label)
            tx.setStyleSheet("color:%s;font-size:11px;" % self.pal["text3"])
            li.addWidget(sw)
            li.addWidget(tx)
            row.addLayout(li)
        row.addStretch(1)
        return row

    def refresh(self):
        self._apply_auth_state()
        self._update_statusbar()

    def highlight_tab(self, idx):
        pass

    def _start_status_timer(self):
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_statusbar)
        self._status_timer.start(1000)


class _Segment(QWidget):
    """All / Active / Moderators segmented control (syncs a QTabWidget)."""

    def __init__(self, tab_widget, pal):
        super(_Segment, self).__init__()
        self._tabs = tab_widget
        self._pal = pal
        tab_widget.setObjectName("viewersTabs")
        h = QHBoxLayout(self)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(2)
        self._btns = []
        for i, label in enumerate(["All", "Active", "Moderators"]):
            b = QPushButton(label)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self._pick(i))
            self._btns.append(b)
            h.addWidget(b, 1)
        self._paint()
        tab_widget.currentChanged.connect(self._on_tab_changed)
        # The segment control replaces the native tab bar — hide it so the
        # two don't duplicate. The tab pages themselves stay functional.
        tab_widget.tabBar().setVisible(False)

    def _pick(self, i):
        self._tabs.setCurrentIndex(i)

    def _on_tab_changed(self, i):
        self._paint()

    def _paint(self):
        cur = self._tabs.currentIndex()
        for i, b in enumerate(self._btns):
            if i == cur:
                b.setStyleSheet(
                    "QPushButton{background:%s;color:%s;font-weight:600;"
                    "border:1px solid transparent;border-radius:6px;padding:5px 4px;}"
                    % (self._pal["surface"], self._pal["text"]))
            else:
                b.setStyleSheet(
                    "QPushButton{background:transparent;color:%s;font-weight:500;"
                    "border:1px solid transparent;border-radius:6px;padding:5px 4px;}"
                    "QPushButton:hover{color:%s;}"
                    % (self._pal["text2"], self._pal["text"]))


class SidebarTwitchView(TwitchThemedBase):
    """Design 1: topbar + stat strip + two-column (chat | viewers) + status bar."""

    def __init__(self, parent, tab_widget, twitch_tab):
        super(SidebarTwitchView, self).__init__(parent, tab_widget, twitch_tab)
        self.pal = palette_for(getattr(parent, "theme", "sidebar"))
        self._build()

    def _build(self):
        tt = self.twitch_tab
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # topbar
        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(54)
        th = QHBoxLayout(top)
        th.setContentsMargins(18, 0, 18, 0)
        th.setSpacing(12)
        title = QLabel("Twitch")
        title.setObjectName("topTitle")
        th.addWidget(title)
        crumb = QLabel("/ connection \u00b7 chat \u00b7 viewers")
        crumb.setObjectName("crumb")
        th.addWidget(crumb)
        th.addStretch(1)
        th.addWidget(tt.disconnect_button)
        tt.connect_button.setObjectName("primaryBtn")
        th.addWidget(tt.connect_button)
        root.addWidget(top)

        # stat strip
        content = QWidget()
        cv = QVBoxLayout(content)
        cv.setContentsMargins(18, 16, 18, 0)
        cv.setSpacing(14)
        cv.addWidget(self._build_stat_strip())

        # two columns
        cols = QWidget()
        ch = QHBoxLayout(cols)
        ch.setContentsMargins(0, 0, 0, 0)
        ch.setSpacing(14)

        colL = QWidget()
        lv = QVBoxLayout(colL)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(14)

        # auth panel
        ap, av = self._panel("Authentication", "Twitch OAuth")
        arow = QHBoxLayout()
        arow.setSpacing(10)
        arow.addWidget(self._build_auth_pill())
        arow.addStretch(1)
        tt.auth_button.setObjectName("primaryBtn")
        arow.addWidget(tt.auth_button)
        arow.addWidget(tt.token_button)
        av.addLayout(arow)
        lv.addWidget(ap)

        # connection panel
        cp, cvv = self._panel("Connection", "chat channel")
        crow = QHBoxLayout()
        crow.setSpacing(10)
        tt.channel_input.setMinimumWidth(220)
        crow.addWidget(tt.channel_input)
        crow.addWidget(tt.check_connection_button)
        crow.addStretch(1)
        cvv.addLayout(crow)
        lv.addWidget(cp)

        # chat panel
        chp, chv = self._panel("Chat", "live preview")
        chv.addWidget(tt.chat_display, 1)
        comp = QHBoxLayout()
        comp.setSpacing(8)
        comp.addWidget(tt.message_input, 1)
        tt.send_button.setObjectName("primaryBtn")
        comp.addWidget(tt.send_button)
        chv.addLayout(comp)
        lv.addWidget(chp, 1)

        colR = QWidget()
        rv = QVBoxLayout(colR)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        # viewers panel
        vp, vv = self._panel("Viewers", "total")
        self._seg = _Segment(tt.viewers_tabs, self.pal)
        vv.addWidget(self._seg)
        vv.addWidget(tt.viewers_tabs, 1)
        vv.addLayout(self._build_legend())
        rrow = QHBoxLayout()
        rrow.setSpacing(10)
        rrow.addWidget(tt.refresh_viewers_button)
        auto = QLabel("Auto:")
        auto.setStyleSheet("color:%s;font-size:12px;" % self.pal["text3"])
        rrow.addWidget(auto)
        rrow.addWidget(tt.update_frequency)
        rrow.addStretch(1)
        rrow.addWidget(tt.last_update_label)
        vv.addLayout(rrow)
        rv.addWidget(vp, 1)

        ch.addWidget(colL, 155)
        ch.addWidget(colR, 100)
        cv.addWidget(cols, 1)
        root.addWidget(_scroll_wrap(content), 1)

        root.addWidget(self._build_status_bar())

        self._start_status_timer()


class SpreadsheetTwitchView(TwitchThemedBase):
    """Design 9: brand topbar + toolbar (auth/channel/actions) + chat|viewers + status bar."""

    def __init__(self, parent, tab_widget, twitch_tab):
        super(SpreadsheetTwitchView, self).__init__(parent, tab_widget, twitch_tab)
        self.pal = palette_for(getattr(parent, "theme", "spreadsheet"))
        self._build()

    def _build(self):
        tt = self.twitch_tab
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # topbar (brand + connect/disconnect)
        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(56)
        th = QHBoxLayout(top)
        th.setContentsMargins(18, 0, 18, 0)
        th.setSpacing(10)
        th.addWidget(LogoBadge(self.pal))
        name = QLabel("Command Editor")
        name.setStyleSheet("font-size:14px;font-weight:600;color:%s;" % self.pal["text"])
        th.addWidget(name)
        th.addStretch(1)
        th.addWidget(tt.disconnect_button)
        tt.connect_button.setObjectName("primaryBtn")
        th.addWidget(tt.connect_button)
        root.addWidget(top)

        # toolbar
        tb = _overflow_toolbar(46)
        tbh = tb
        tbh.addWidget(self._build_auth_pill())
        chan = QLabel("channel")
        chan.setStyleSheet("color:%s;font-size:12px;" % self.pal["text2"])
        tbh.addWidget(chan)
        tt.channel_input.setFixedWidth(150)
        tbh.addWidget(_held(tt.channel_input))
        sep = QFrame()
        sep.setFixedSize(1, 22)
        sep.setStyleSheet("background:%s;" % self.pal["border"])
        tbh.addWidget(sep)
        tbh.addWidget(_held(tt.check_connection_button))
        tbh.addWidget(_held(tt.auth_button))
        tbh.addWidget(_held(tt.token_button))
        _toolbar_stretch(tb)
        self._tb_stats = QLabel("")
        self._tb_stats.setStyleSheet("color:%s;font-size:11.5px;" % self.pal["text3"])
        tbh.addWidget(self._tb_stats)
        root.addWidget(tb)

        # body: chat | viewers
        body = QWidget()
        bh = QHBoxLayout(body)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(0)

        chatcol = QWidget()
        chcv = QVBoxLayout(chatcol)
        chcv.setContentsMargins(0, 0, 0, 0)
        chcv.setSpacing(0)
        chatcol.setStyleSheet("border-right:1px solid %s;" % self.pal["border"])
        chcv.addWidget(tt.chat_display, 1)
        comp = QFrame()
        comp.setStyleSheet("background:%s;border-top:1px solid %s;" % (self.pal["surface2"], self.pal["border"]))
        compv = QHBoxLayout(comp)
        compv.setContentsMargins(14, 10, 14, 10)
        compv.setSpacing(8)
        compv.addWidget(tt.message_input, 1)
        tt.send_button.setObjectName("primaryBtn")
        compv.addWidget(tt.send_button)
        chcv.addWidget(comp)
        bh.addWidget(chatcol, 155)

        viewcol = QWidget()
        vcv = QVBoxLayout(viewcol)
        vcv.setContentsMargins(0, 0, 0, 0)
        vcv.setSpacing(0)
        self._seg = _Segment(tt.viewers_tabs, self.pal)
        self._seg.setContentsMargins(14, 10, 14, 10)
        vcv.addWidget(self._seg)
        vcv.addWidget(tt.viewers_tabs, 1)
        vcv.addLayout(self._build_legend())
        foot = QFrame()
        foot.setStyleSheet("background:%s;border-top:1px solid %s;" % (self.pal["surface2"], self.pal["border"]))
        footv = QHBoxLayout(foot)
        footv.setContentsMargins(14, 8, 14, 8)
        footv.setSpacing(8)
        footv.addWidget(tt.refresh_viewers_button)
        auto = QLabel("Auto:")
        auto.setStyleSheet("color:%s;font-size:11.5px;" % self.pal["text3"])
        footv.addWidget(auto)
        footv.addWidget(tt.update_frequency)
        footv.addStretch(1)
        footv.addWidget(tt.last_update_label)
        vcv.addWidget(foot)
        bh.addWidget(viewcol, 100)

        root.addWidget(_scroll_wrap(body), 1)
        root.addWidget(self._build_status_bar())

        self._start_status_timer()

    def _update_statusbar(self):
        super(SpreadsheetTwitchView, self)._update_statusbar()
        tt = self.twitch_tab
        live = getattr(tt, "currently_live", False)
        self._tb_stats.setText(
            "%s \u00b7 %s active \u00b7 %s all \u00b7 %s mods" % (
                "Live" if live else "Offline",
                len(getattr(tt, "active_users", []) or []),
                self.all_viewers_count.text().split(":")[-1].strip(),
                len(getattr(tt, "moderators_list", []) or [])))
