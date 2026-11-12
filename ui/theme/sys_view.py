# -*- coding: utf-8 -*-
"""The themed Sys.Commands tab.

Python 3.8 / PyQt5.
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QLabel,
                             QPushButton, QLineEdit, QListWidget, QListWidgetItem, QComboBox,
                             QSpinBox, QScrollArea, QCheckBox)
from PyQt5.QtCore import Qt, QSize, QTimer
from core.permissions import name_of as permission_name
from ui.theme.style import (PERMISSIONS, USAGES, palette_for)
from ui.theme.widgets import (MasterDelegate, ToggleSwitch, _known_groups, _shrinkable, make_icon)


# ---------------------------------------------------------------------------
# Generic themed tab wrapper (Design 1 / Design 9)
#
# For the tabs that don't have a bespoke themed layout yet, this wraps the
# ORIGINAL tab widget in a themed frame (topbar with title + the original
# content). The original tab is re-parented into the wrapper; its internal
# widgets and logic are untouched, so everything keeps working. Switching back
# to classic re-parents the original tab into the tab widget.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Sys.Commands in the sidebar layouts: master list + detail editor, like the
# themed Commands view (it used to be the classic table in a themed frame).
# All changes go through SysCommandsTab.set_field / duplicate_at / remove_at,
# so the classic tab, system_commands.json and the bot stay in sync.
# ---------------------------------------------------------------------------

class SysCommandsView(QWidget):
    TEXT_FIELDS = ("command_name", "info", "group", "random_group",
                   "picked_command_response", "default_group")

    def __init__(self, editor, sys_tab):
        super(SysCommandsView, self).__init__(editor)
        self.editor = editor
        self.tab = sys_tab
        self.pal = palette_for(getattr(editor, "theme", "sidebar"))
        self._row = -1
        self._guard = False
        self._pending = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._flush)
        self._make_top()
        self._build()
        self.refresh()

    @property
    def cmds(self):
        return self.tab.system_commands

    # -- topbar buttons (placed by ThemedTabView) ------------------------
    def topbar_widgets(self):
        return [self.search_edit, self.dup_btn]

    def _make_top(self):
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchBox")
        self.search_edit.setPlaceholderText("Search…")
        self.search_edit.setClearButtonEnabled(True)
        _shrinkable(self.search_edit, 200, 90)
        self.search_edit.textChanged.connect(lambda _t: self.refresh())
        self.dup_btn = QPushButton("Duplicate")
        self.dup_btn.setToolTip("Create a copy of this command under another name "
                                "(e.g. !money as an alias of !points)")
        self.dup_btn.clicked.connect(self._duplicate)

    # -- construction -----------------------------------------------------
    def _build(self):
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("masterPanel")
        panel.setMinimumWidth(200)
        panel.setMaximumWidth(300)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)
        self.list = QListWidget()
        self.list.setObjectName("masterList")
        self.list.setMouseTracking(True)
        self.list.setUniformItemSizes(True)
        self.list.setItemDelegate(MasterDelegate(self.pal, self.list))
        self.list.itemSelectionChanged.connect(self._on_selected)
        pv.addWidget(self.list, 1)
        h.addWidget(panel, 0)

        scroll = QScrollArea()
        scroll.setObjectName("detailScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        d = QFrame()
        d.setObjectName("detailPanel")
        v = QVBoxLayout(d)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        tt = QVBoxLayout()
        tt.setSpacing(2)
        self.d_title = QLabel("")
        self.d_title.setObjectName("dTitle")
        self.d_sub = QLabel("")
        self.d_sub.setObjectName("dSub")
        tt.addWidget(self.d_title)
        tt.addWidget(self.d_sub)
        head.addLayout(tt)
        head.addStretch(1)
        lab = QLabel("Enabled")
        lab.setObjectName("switchDesc")
        head.addWidget(lab)
        self.f_enabled = ToggleSwitch(self.pal)
        self.f_enabled.toggled.connect(lambda on: self._edit("enabled", bool(on), now=True))
        head.addWidget(self.f_enabled)
        self.rm_btn = QPushButton()
        self.rm_btn.setObjectName("dangerBtn")
        self.rm_btn.setIcon(make_icon("trash", self.pal["red"]))
        self.rm_btn.setToolTip("Remove this duplicate (originals can't be removed)")
        self.rm_btn.clicked.connect(self._remove)
        head.addWidget(self.rm_btn)
        v.addLayout(head)

        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(6)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)

        def lab_(t):
            x = QLabel(t)
            x.setObjectName("fieldLabel")
            return x

        self.f_name = QLineEdit()
        self.f_name.textChanged.connect(lambda t: self._edit("command_name", t))
        self.f_group = QLineEdit()
        self.f_group.textChanged.connect(lambda t: self._edit("group", t))
        g.addWidget(lab_("Command"), 0, 0)
        g.addWidget(lab_("Group"), 0, 1)
        g.addWidget(self.f_name, 1, 0)
        g.addWidget(self.f_group, 1, 1)

        self.f_perm = QComboBox()
        self.f_perm.addItems(PERMISSIONS)
        self.f_perm.currentTextChanged.connect(lambda t: self._edit("permission", t, now=True))
        self.f_usage = QComboBox()
        self.f_usage.addItems(USAGES)
        self.f_usage.currentTextChanged.connect(lambda t: self._edit("usage", t, now=True))
        g.addWidget(lab_("Permission"), 2, 0)
        g.addWidget(lab_("Usage"), 2, 1)
        g.addWidget(self.f_perm, 3, 0)
        g.addWidget(self.f_usage, 3, 1)

        self.f_cd = QSpinBox()
        self.f_cd.setRange(0, 3600)
        self.f_cd.setSuffix(" min")
        self.f_cd.setSpecialValueText("none")
        self.f_cd.setToolTip("Global cooldown in MINUTES")
        self.f_cd.valueChanged.connect(lambda val: self._edit("cooldown", int(val)))
        self.f_ucd = QSpinBox()
        self.f_ucd.setRange(0, 3600)
        self.f_ucd.setSuffix(" min")
        self.f_ucd.setSpecialValueText("none")
        self.f_ucd.setToolTip("Per-viewer cooldown in MINUTES")
        self.f_ucd.valueChanged.connect(lambda val: self._edit("user_cooldown", int(val)))
        g.addWidget(lab_("Cooldown"), 4, 0)
        g.addWidget(lab_("User cooldown"), 4, 1)
        g.addWidget(self.f_cd, 5, 0)
        g.addWidget(self.f_ucd, 5, 1)

        self.f_cost = QSpinBox()
        self.f_cost.setRange(0, 1000000)
        self.f_cost.setSpecialValueText("free")
        self.f_cost.valueChanged.connect(lambda val: self._edit("cost", int(val)))
        g.addWidget(lab_("Cost (points)"), 6, 0)
        g.addWidget(self.f_cost, 7, 0)

        self.f_info = QLineEdit()
        self.f_info.textChanged.connect(lambda t: self._edit("info", t))
        g.addWidget(lab_("Info"), 8, 0, 1, 2)
        g.addWidget(self.f_info, 9, 0, 1, 2)
        v.addLayout(g)

        # !random / !volume specific settings
        self.extra_card = QFrame()
        self.extra_card.setObjectName("settingsCard")
        ev = QGridLayout(self.extra_card)
        ev.setContentsMargins(16, 12, 16, 12)
        ev.setHorizontalSpacing(14)
        ev.setVerticalSpacing(6)
        self.extra_title = QLabel("")
        self.extra_title.setObjectName("sectionTitle")
        ev.addWidget(self.extra_title, 0, 0, 1, 2)
        self.l_random = lab_("Random group (ALL = any group)")
        self.f_random = QComboBox()
        self.f_random.setEditable(True)
        self.f_random.setInsertPolicy(QComboBox.NoInsert)
        self.f_random.editTextChanged.connect(lambda t: self._edit("random_group", t))
        self.f_show_picked = QCheckBox("Show the picked command in chat")
        self.f_show_picked.toggled.connect(lambda on: self._edit("show_picked_command", bool(on), now=True))
        self.l_picked = lab_("Picked command message ({command} = picked command)")
        self.f_picked = QLineEdit()
        self.f_picked.setPlaceholderText("Picked {command}.")
        self.f_picked.textChanged.connect(lambda t: self._edit("picked_command_response", t))
        self.l_default = lab_("Default group (when !volume is used without a group)")
        self.f_default = QComboBox()
        self.f_default.setEditable(True)
        self.f_default.setInsertPolicy(QComboBox.NoInsert)
        self.f_default.editTextChanged.connect(lambda t: self._edit("default_group", t))
        ev.addWidget(self.l_random, 1, 0)
        ev.addWidget(self.f_random, 2, 0)
        ev.addWidget(self.f_show_picked, 2, 1)
        ev.addWidget(self.l_picked, 3, 0, 1, 2)
        ev.addWidget(self.f_picked, 4, 0, 1, 2)
        ev.addWidget(self.l_default, 5, 0, 1, 2)
        ev.addWidget(self.f_default, 6, 0)
        v.addWidget(self.extra_card)

        self.error = QLabel("")
        self.error.setStyleSheet("color: %s;" % self.pal["red"])
        self.error.setWordWrap(True)
        v.addWidget(self.error)
        hint = QLabel("Originals are built into the bot: their name is fixed, everything else can "
                      "be changed. Use Duplicate to add the same command under another name.")
        hint.setObjectName("switchDesc")
        hint.setWordWrap(True)
        v.addWidget(hint)
        v.addStretch(1)
        scroll.setWidget(d)
        h.addWidget(scroll, 1)
        self.fields = [self.f_name, self.f_group, self.f_perm, self.f_usage, self.f_cd,
                       self.f_ucd, self.f_cost, self.f_info, self.f_enabled, self.rm_btn]

    # -- list ---------------------------------------------------------------
    def _row_data(self, cmd):
        dup = cmd.get("is_duplicate", False)
        meta = [cmd.get("permission", "")]
        if cmd.get("cooldown"):
            meta.append("%s min" % cmd.get("cooldown"))
        if cmd.get("cost"):
            meta.append("%s pts" % cmd.get("cost"))
        meta.append(("copy of " + cmd.get("command", "")) if dup else (cmd.get("info", "") or ""))
        return {"Command": self.tab.display_name(cmd), "Group": "COPY" if dup else "ORIGINAL",
                "Enabled": bool(cmd.get("enabled", True)),
                "_meta": " · ".join(m for m in meta if m)}

    def refresh(self, select_row=None):
        self._flush()
        if select_row is None:
            select_row = self._row
        needle = self.search_edit.text().strip().lower()
        self.list.blockSignals(True)
        self.list.clear()
        for i, cmd in enumerate(self.cmds):
            hay = " ".join(str(cmd.get(k, "")) for k in
                           ("command", "command_name", "info", "group", "permission")).lower()
            if needle and needle not in hay:
                continue
            it = QListWidgetItem(self.tab.display_name(cmd))
            it.setData(Qt.UserRole, self._row_data(cmd))
            it.setData(Qt.UserRole + 1, i)
            it.setSizeHint(QSize(0, 54))
            self.list.addItem(it)
        self.list.blockSignals(False)
        groups = _known_groups(getattr(self.editor, "commands", []), self.editor)
        for combo, first in ((self.f_random, ["ALL"]), (self.f_default, [])):
            combo.blockSignals(True)
            text = combo.currentText()
            combo.clear()
            combo.addItems(first + [x for x in groups if x != "ALL"])
            combo.setEditText(text)
            combo.blockSignals(False)
        if not self.cmds:
            self._populate(-1)
            return
        if select_row is None or not (0 <= select_row < len(self.cmds)):
            select_row = 0
        self._select(select_row)
        self._populate(select_row)

    def _select(self, row):
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole + 1) == row:
                self.list.setCurrentRow(i)
                self.list.scrollToItem(self.list.item(i))
                break
        else:
            self.list.clearSelection()
        self.list.blockSignals(False)

    def _update_item(self, row):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole + 1) == row:
                it.setData(Qt.UserRole, self._row_data(self.cmds[row]))
                it.setText(self.tab.display_name(self.cmds[row]))
                break

    def _on_selected(self):
        items = self.list.selectedItems()
        if not items:
            return
        row = items[0].data(Qt.UserRole + 1)
        if isinstance(row, int) and row != self._row:
            self._flush()
            self._populate(row)

    # -- detail ---------------------------------------------------------------
    def _populate(self, row):
        ok = 0 <= row < len(self.cmds)
        self._row = row if ok else -1
        for w in self.fields:
            w.setEnabled(ok)
        self.error.setText("")
        if not ok:
            self.d_title.setText("No command selected")
            self.d_sub.setText("")
            self.extra_card.hide()
            self.dup_btn.setEnabled(False)
            return
        cmd = self.cmds[row]
        dup = cmd.get("is_duplicate", False)
        self._guard = True
        try:
            self.f_name.setText(self.tab.display_name(cmd))
            self.f_name.setReadOnly(not dup)
            self.f_name.setToolTip("" if dup else "The name of an original command is fixed. "
                                   "Duplicate it to use another name.")
            self.f_group.setText(cmd.get("group", ""))
            for combo, value in ((self.f_perm, permission_name(cmd.get("permission", "Everyone"))),
                                 (self.f_usage, cmd.get("usage", "Chat"))):
                if combo.findText(value) < 0:
                    combo.addItem(value)
                combo.setCurrentText(value)
            self.f_cd.setValue(int(cmd.get("cooldown", 0) or 0))
            self.f_ucd.setValue(int(cmd.get("user_cooldown", 0) or 0))
            self.f_cost.setValue(int(cmd.get("cost", 0) or 0))
            self.f_info.setText(cmd.get("info", ""))
            self.f_enabled.setChecked(bool(cmd.get("enabled", True)))
            base = cmd.get("command", "")
            name = self.tab.display_name(cmd)
            is_random = base == "!random" or name.startswith("!random")
            is_volume = base == "!volume" or name.startswith("!volume")
            for w in (self.l_random, self.f_random, self.f_show_picked, self.l_picked, self.f_picked):
                w.setVisible(is_random)
            for w in (self.l_default, self.f_default):
                w.setVisible(is_volume)
            self.extra_card.setVisible(is_random or is_volume)
            self.extra_title.setText("!random settings" if is_random else "!volume settings")
            self.f_random.setEditText(cmd.get("random_group", "ALL"))
            self.f_show_picked.setChecked(bool(cmd.get("show_picked_command", True)))
            self.f_picked.setText(cmd.get("picked_command_response", "Picked {command}."))
            self.f_default.setEditText(cmd.get("default_group", "SONG"))
        finally:
            self._guard = False
        self.rm_btn.setVisible(dup)
        self.dup_btn.setEnabled(not dup)
        self._update_header()

    def _update_header(self):
        if self._row < 0:
            return
        cmd = self.cmds[self._row]
        self.d_title.setText(self.tab.display_name(cmd))
        if cmd.get("is_duplicate", False):
            sub = "copy of %s" % cmd.get("command", "")
        else:
            sub = "built-in command"
        if not cmd.get("enabled", True):
            sub += " · disabled"
        self.d_sub.setText(sub)

    # -- edits ----------------------------------------------------------------
    def _edit(self, field, value, now=False):
        if self._guard or self._row < 0:
            return
        self._pending[field] = value
        if now or field not in self.TEXT_FIELDS:
            self._flush()
        else:
            self._timer.start()

    def _flush(self):
        self._timer.stop()
        if not self._pending or self._row < 0:
            self._pending = {}
            return
        pending, self._pending = self._pending, {}
        errors = []
        for field, value in pending.items():
            err = self.tab.set_field(self._row, field, value)
            if err:
                errors.append(err)
        self.error.setText(" ".join(errors))
        self._update_item(self._row)
        self._update_header()

    def _duplicate(self):
        self._flush()
        res = self.tab.duplicate_at(self._row)
        if isinstance(res, str):
            self.error.setText(res)
            return
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self.refresh(select_row=res)
        self.f_name.setFocus()
        self.f_name.selectAll()

    def _remove(self):
        self._flush()
        if self.tab.remove_at(self._row, self):
            self.refresh(select_row=max(0, self._row - 1))

    def showEvent(self, event):
        # data may have been changed in the classic tab / by a restore
        self.refresh()
        super(SysCommandsView, self).showEvent(event)

    def highlight_tab(self, idx):
        pass
