# -*- coding: utf-8 -*-
"""Theme switching for the main window (mixin of CommandEditor).

Swaps the Commands/Twitch tabs for themed views, wraps the other tabs,
the sidebar nav and the Now-Playing bar. Moved out of command_editor.py
unchanged (step 4.3); it works on the window's own attributes.

Python 3.8 / PyQt5.
"""
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt
from ui import theme as _theme
from ui.i18n import tr, N_


class ThemeSwitchMixin(object):
    def apply_theme(self, theme_name):
        """Apply a UI theme: classic (native), sidebar, or spreadsheet."""
        if theme_name not in _theme.THEMES:
            theme_name = "classic"
        self.theme = theme_name
        self.config_manager.set_theme(theme_name)

        # Запоминаем активную вкладку: rebuild-функции ниже сбрасывают
        # индекс (removeTab/insertTab + setCurrentIndex(0)), в конце
        # apply_theme вернём пользователя на его вкладку.
        current_index = self.tab_widget.currentIndex() if self.tab_widget is not None else 0

        layout = _theme.layout_of(theme_name)

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(_theme.qss_for(theme_name))

        # In the sidebar layout the left nav IS the navigation — hide the
        # top tab bar so it doesn't duplicate it (content stays visible).
        try:
            self.tab_widget.tabBar().setVisible(layout != "sidebar")
        except Exception:
            pass

        # Every theme has a Settings tab (classic also keeps the same settings
        # in the Commands tab; both drive the same widgets). Added before the
        # nav so its button is shown.
        self._update_settings_tab(True)
        self._update_sidebar(theme_name)
        self._update_now_playing_bar(theme_name)

        # Fit all 11 tabs into the bar (avoid clipped labels)
        try:
            self.tab_widget.setUsesScrollButtons(True)
            if theme_name != "classic":
                self.tab_widget.tabBar().setElideMode(Qt.ElideRight)
            else:
                self.tab_widget.tabBar().setElideMode(Qt.ElideNone)
        except Exception:
            pass

        self._rebuild_commands_view()
        self._rebuild_twitch_view()
        self._rebuild_generic_tab_views()

        # Вернуть пользователя на ту вкладку, где он был (rebuild-функции
        # делают removeTab/insertTab и setCurrentIndex(0), сбивая выбор —
        # при смене темы из About логично остаться на About).
        try:
            if current_index >= self.tab_widget.count():
                current_index = 0
            self.tab_widget.setCurrentIndex(current_index)
            if self.sidebar_nav is not None:
                self.sidebar_nav.highlight_tab(current_index)
        except Exception:
            pass

        # Keep the About tab's theme combo in sync when switched elsewhere
        combo = getattr(getattr(self, "about_tab", None), "theme_combo", None)
        if combo is not None:
            i = combo.findData(theme_name)
            if i >= 0 and combo.currentIndex() != i:
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)

    def _update_sidebar(self, theme_name):
        """Show the persistent left nav rail in sidebar-layout themes, hide it
        otherwise. The rail is a sibling of the tab widget in the central
        container, so it stays visible on every tab. Rebuilt on every theme
        change so it picks up the new palette."""
        if self.sidebar_nav is not None:
            try:
                self.tab_widget.currentChanged.disconnect(self.sidebar_nav.highlight_tab)
            except (TypeError, RuntimeError):
                pass
            self.sidebar_nav.hide()
            self.sidebar_nav.setParent(None)
            self.sidebar_nav.deleteLater()
            self.sidebar_nav = None
        if _theme.layout_of(theme_name) == "sidebar":
            self.sidebar_nav = _theme.SidebarNav(
                self, self.tab_widget, _theme.palette_for(theme_name))
            self._central_layout.insertWidget(0, self.sidebar_nav, 0)
            self.sidebar_nav.show()
            self.sidebar_nav.highlight_tab(self.tab_widget.currentIndex())

    def _update_now_playing_bar(self, theme_name):
        """Persistent queue strip under the tabs (Midnight theme)."""
        bar = getattr(self, "now_playing_bar", None)
        if bar is not None:
            bar.setParent(None)
            bar.deleteLater()
            self.now_playing_bar = None
        if theme_name in _theme.NOW_PLAYING_THEMES:
            if not hasattr(self, "_content_column"):
                # Wrap the tab widget in a column so the bar sits below it.
                self._content_column = QWidget()
                col = QVBoxLayout(self._content_column)
                col.setContentsMargins(0, 0, 0, 0)
                col.setSpacing(0)
                idx = self._central_layout.indexOf(self.tab_widget)
                self._central_layout.removeWidget(self.tab_widget)
                col.addWidget(self.tab_widget, 1)
                self._central_layout.insertWidget(max(0, idx), self._content_column, 1)
            self.now_playing_bar = _theme.NowPlayingBar(self)
            self._content_column.layout().addWidget(self.now_playing_bar, 0)

    def _update_settings_tab(self, show):
        """Add (themed layouts) or remove (classic) the Settings tab. It is
        always the last tab so the fixed nav indices stay valid."""
        tab = getattr(self, "settings_tab", None)
        if tab is not None:
            idx = self.tab_widget.indexOf(tab)
            if idx >= 0:
                self.tab_widget.removeTab(idx)
            tab.setParent(None)
            tab.deleteLater()
            self.settings_tab = None
        if show:
            panel = _theme.SettingsPanel(self)
            if _theme.layout_of(self.theme) == "classic":
                # native look: no themed frame around it
                self.settings_tab = panel
            else:
                self.settings_tab = _theme.ThemedTabView(
                    self, self.tab_widget, panel,
                    N_("Settings"), N_("sound · auto-save · appearance"))
            self.tab_widget.addTab(self.settings_tab, tr("Settings"))

    def set_theme(self, theme_name):
        """Public entry point for the theme switcher (About tab)."""
        self.apply_theme(theme_name)

    def _make_commands_view(self):
        """Build the themed Commands view for the current theme."""
        if _theme.layout_of(self.theme) == "sidebar":
            return _theme.SidebarCommandsView(
                self, self.main_tab, self.table, self.commands,
                self.search_input,
                on_add=self.add_command, on_remove=self.delete_command,
                on_load=self.load_file, on_save=self.save_file,
            )
        return _theme.SpreadsheetCommandsView(
            self, self.main_tab, self.table, self.commands,
            self.search_input,
            on_add=self.add_command, on_remove=self.delete_command,
            on_load=self.load_file, on_save=self.save_file,
        )

    def _rebuild_commands_view(self):
        """Swap the Commands tab content between classic and themed views."""
        tab_widget = self.tab_widget
        if tab_widget is None:
            return
        # The classic Commands tab is always index 0
        cmd_idx = 0

        if self.theme == "classic":
            # Restore the original classic Commands tab if it was replaced
            if self.themed_commands_view is not None:
                idx = tab_widget.indexOf(self.themed_commands_view)
                if idx >= 0:
                    tab_widget.removeTab(idx)
                self.themed_commands_view.setParent(None)
                self.themed_commands_view.deleteLater()
                self.themed_commands_view = None
            # main_tab was unparented when a theme was applied; restore it
            if tab_widget.indexOf(self.main_tab) < 0:
                tab_widget.insertTab(0, self.main_tab, tr("Commands"))
            return

        # (Re)create the themed view, destroying any previous one
        first_apply = tab_widget.widget(cmd_idx) is self.main_tab
        if self.themed_commands_view is not None:
            idx = tab_widget.indexOf(self.themed_commands_view)
            if idx >= 0:
                tab_widget.removeTab(idx)
            self.themed_commands_view.setParent(None)
            self.themed_commands_view.deleteLater()
            self.themed_commands_view = None
        self.themed_commands_view = self._make_commands_view()
        # Insert the themed view at the Commands position
        if first_apply:
            # Classic tab still occupies index 0: remove it, insert themed view
            tab_widget.removeTab(cmd_idx)
            tab_widget.insertTab(cmd_idx, self.themed_commands_view, tr("Commands"))
        else:
            # A themed view already occupied index 0 (now shifted): insert at 0
            tab_widget.insertTab(cmd_idx, self.themed_commands_view, tr("Commands"))
        tab_widget.setCurrentIndex(cmd_idx)
        self.themed_commands_view.highlight_tab(cmd_idx)

    def refresh_themed_commands(self):
        """Refresh the themed Commands view after the data changed."""
        if self.themed_commands_view is not None:
            self.themed_commands_view.refresh()

    def _make_twitch_view(self):
        """Build the themed Twitch view for the current theme."""
        if _theme.layout_of(self.theme) == "sidebar":
            return _theme.SidebarTwitchView(self, self.tab_widget, self.twitch_tab)
        return _theme.SpreadsheetTwitchView(self, self.tab_widget, self.twitch_tab)

    def _rebuild_twitch_view(self):
        """Swap the Twitch tab content between classic and themed views.

        The themed view re-parents the original TwitchTab widgets into a new
        layout; switching back to classic restores the original layout via
        TwitchTab.restore_classic_layout().
        """
        tab_widget = self.tab_widget
        if tab_widget is None or not hasattr(self, "twitch_tab"):
            return
        tw_idx = tab_widget.indexOf(self.twitch_tab)
        if tw_idx < 0:
            tw_idx = 2  # Twitch is the 3rd tab (0-indexed)

        if self.theme == "classic":
            if self.themed_twitch_view is not None:
                idx = tab_widget.indexOf(self.themed_twitch_view)
                if idx >= 0:
                    tab_widget.removeTab(idx)
                self.themed_twitch_view.setParent(None)
                self.themed_twitch_view.deleteLater()
                self.themed_twitch_view = None
            if tab_widget.indexOf(self.twitch_tab) < 0:
                self.twitch_tab.restore_classic_layout()
                tab_widget.insertTab(tw_idx, self.twitch_tab, tr("Twitch"))
            return

        # (Re)create the themed view, destroying any previous one
        first_apply = tab_widget.widget(tw_idx) is self.twitch_tab
        if self.themed_twitch_view is not None:
            idx = tab_widget.indexOf(self.themed_twitch_view)
            if idx >= 0:
                tab_widget.removeTab(idx)
            self.themed_twitch_view.setParent(None)
            self.themed_twitch_view.deleteLater()
            self.themed_twitch_view = None
        self.themed_twitch_view = self._make_twitch_view()
        if first_apply:
            tab_widget.removeTab(tw_idx)
            tab_widget.insertTab(tw_idx, self.themed_twitch_view, tr("Twitch"))
        else:
            tab_widget.insertTab(tw_idx, self.themed_twitch_view, tr("Twitch"))
        tab_widget.setCurrentIndex(tw_idx)
        self.themed_twitch_view.highlight_tab(tw_idx)

    def _rebuild_generic_tab_views(self):
        """Wrap (or unwrap) the 9 generic tabs in a themed frame, preserving
        their positions in the tab bar."""
        tab_widget = self.tab_widget
        if tab_widget is None:
            return

        if self.theme == "classic":
            for name, view in list(self.themed_tab_views.items()):
                idx = tab_widget.indexOf(view)
                if idx >= 0:
                    tab_widget.removeTab(idx)
                view.setParent(None)
                view.deleteLater()
            self.themed_tab_views = {}
            # Re-insert the original tabs at their canonical positions
            for name, (attr, _t, _s, cidx) in self._GENERIC_TABS.items():
                orig = getattr(self, attr, None)
                if orig is None:
                    continue
                if tab_widget.indexOf(orig) < 0:
                    # drop the themed background the wrapper put on it
                    orig.setStyleSheet("")
                    tab_widget.insertTab(min(cidx, tab_widget.count()), orig, tr(name))
            return

        for name, (attr, title, subtitle, _cidx) in self._GENERIC_TABS.items():
            orig = getattr(self, attr, None)
            if orig is None:
                continue
            existing = self.themed_tab_views.pop(name, None)
            idx = tab_widget.indexOf(orig)
            if idx < 0 and existing is not None:
                # Themed -> themed switch: the tab sits inside the previous
                # wrapper. Re-wrap it so it gets the new palette (it used to
                # keep the old theme's colours, e.g. white panels in Midnight).
                idx = tab_widget.indexOf(existing)
            if idx < 0:
                continue
            tab_widget.removeTab(idx)
            if existing is not None:
                orig.setParent(None)
                existing.setParent(None)
                existing.deleteLater()
            content = None
            if name == "Sys.Commands" and _theme.layout_of(self.theme) == "sidebar":
                # same master/detail editor as the themed Commands view
                content = _theme.SysCommandsView(self, orig)
            view = _theme.ThemedTabView(self, tab_widget, orig, title, subtitle, content=content)
            tab_widget.insertTab(idx, view, tr(name))
            self.themed_tab_views[name] = view
