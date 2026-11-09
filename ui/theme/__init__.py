# -*- coding: utf-8 -*-
"""Theme system for Command Editor.

Themes:
  * classic     - native Qt look (no QSS, the original appearance)
  * sidebar     - Design 1: Linear/Notion sidebar + master-detail Commands
  * spreadsheet - Design 9: dense inline-edit table + toolbar + status bar
  * midnight    - dark "stream desk": sidebar layout on a dark palette plus a
                  persistent Now-Playing bar (queues controllable from any tab)

The theme is stored in config.json under the "theme" key. Switching themes
re-styles the whole app via QSS and swaps the Commands/Twitch tabs for themed
views. Other tabs keep their widgets and are only re-styled.

Data rule: themed views never write the hidden classic table themselves —
every edit goes through CommandEditor.apply_command_edit(), which updates the
command dict, the classic table, commands.json and the running bot together.

Python 3.8 / PyQt5 (Qt5) only. No walrus, no PEP 585/604 generics.

Package layout (step 4.1): style, widgets, commands_view, settings_view, now_playing, twitch_view, sys_view, tab_view.
"""
from ui.theme.style import (  # noqa: F401
    FONT_FAMILY,
    NOW_PLAYING_THEMES,
    PALETTES,
    PERMISSIONS,
    THEMES,
    THEME_LABELS,
    USAGES,
    _LAYOUTS,
    _arrow_qss,
    _base_qss,
    _layout_qss,
    is_dark,
    layout_of,
    palette_for,
    qss_for,
)
from ui.theme.widgets import (  # noqa: F401
    LogoBadge,
    MasterDelegate,
    SidebarNav,
    ToggleSwitch,
    _ComboDelegate,
    _SpinDelegate,
    _held,
    _known_groups,
    _matches,
    _mono_font,
    _more_menu,
    _overflow_toolbar,
    _scroll_wrap,
    _shrinkable,
    _toolbar_stretch,
    _ui_font,
    cmd_volume,
    connection_state,
    group_pill_kind,
    make_icon,
    make_pill_label,
    pill_colors,
    rgba_color,
)
from ui.theme.commands_view import (  # noqa: F401
    CommandDetailEditor,
    SidebarCommandsView,
    SpreadsheetCommandsView,
)
from ui.theme.settings_view import (  # noqa: F401
    SettingsPanel,
)
from ui.theme.now_playing import (  # noqa: F401
    NowPlayingBar,
)
from ui.theme.twitch_view import (  # noqa: F401
    SidebarTwitchView,
    SpreadsheetTwitchView,
    TwitchThemedBase,
    _Segment,
)
from ui.theme.sys_view import (  # noqa: F401
    SysCommandsView,
)
from ui.theme.tab_view import (  # noqa: F401
    ThemedTabView,
)
