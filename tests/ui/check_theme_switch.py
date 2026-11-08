"""Switching themes through the Settings combo (wide and narrow window)
must not delete or hide the Twitch tab's widgets."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)

NAMES = ("auth_button", "token_button", "check_connection_button", "channel_input",
         "connect_button", "disconnect_button", "send_button", "message_input", "chat_display",
         "viewers_tabs", "refresh_viewers_button", "update_frequency", "last_update_label")


def body(k):
    import sip
    w, check, pump = k.w, k.check, k.pump
    seq = ("spreadsheet", "midnight", "spreadsheet", "classic",
           "spreadsheet", "sidebar", "spreadsheet", "classic")
    for i, t in enumerate(seq):
        w.resize(*((700, 480) if i % 2 else (1360, 820)))  # narrow: toolbar overflow
        w.tab_widget.setCurrentIndex(2); pump(250)
        panel = getattr(w.settings_tab, "original_tab", w.settings_tab)
        j = panel.theme_combo.findData(t)
        panel.theme_combo.setCurrentIndex(j)
        panel.theme_combo.activated.emit(j); pump(400)
        dead = [n for n in NAMES if sip.isdeleted(getattr(w.twitch_tab, n))]
        check("switch #%d to %s: twitch widgets alive" % (i + 1, t), not dead, dead)
    w.tab_widget.setCurrentIndex(2); pump(200)
    hidden = [n for n in NAMES if getattr(w.twitch_tab, n).isHidden()]
    check("classic: twitch widgets visible", not hidden, hidden)
    k.shot("switch_classic_twitch")


kit.start(body, delay_ms=400)
