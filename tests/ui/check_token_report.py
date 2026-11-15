"""The token check reaches the Twitch tab (2.0): chat lines, the Client ID
from the token is saved, a rejected token resets the connect buttons."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)


def body(k):
    from PyQt5.QtWidgets import QMessageBox
    from bot import token_check
    w, check, pump = k.w, k.check, k.pump
    tab = w.twitch_tab
    tab.bot_params = {"channel": "streamer"}
    chat = tab.chat_display

    def lines_after(fn):
        before = chat.toPlainText()
        fn()
        pump(100)
        return chat.toPlainText()[len(before):]

    good = token_check.analyze(200, {"client_id": "cid-from-token", "login": "streamer",
                                     "scopes": [s for s, _ in token_check.SCOPES],
                                     "expires_in": 30 * 86400}, "streamer")
    text = lines_after(lambda: tab.bridge.token_report(good))
    check("whose token and when it expires", "streamer" in text and "30 d" in text, text)
    check("no warnings for the streamer's full token",
          "Missing scope" not in text and "not of the channel owner" not in text, text)
    cfg = w.config_manager.get_twitch_config()
    check("the Client ID comes from the token", cfg.get("client_id") == "cid-from-token", cfg.get("client_id"))
    again = lines_after(lambda: tab.bridge.token_report(good))
    check("the same Client ID is not saved twice", "Client ID taken" not in again, again)

    bot_token = token_check.analyze(200, {"client_id": "cid-from-token", "login": "mybot",
                                          "scopes": ["chat:read", "chat:edit"],
                                          "expires_in": 3 * 3600}, "streamer")
    text = lines_after(lambda: tab.bridge.token_report(bot_token))
    check("another account's token is explained", "not of the channel owner" in text, text)
    check("missing scopes are named", "moderator:read:chatters" in text and "moderation:read" in text, text)
    check("expiring soon is said", "expires soon" in text and "3 h" in text, text)

    text = lines_after(lambda: tab.bridge.token_report({"state": "unknown"}))
    check("no answer from Twitch is said, nothing else", "Could not check the token" in text, text)

    warned = []
    orig = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *a, **kw: warned.append(a[2]) or QMessageBox.Ok)
    try:
        tab.connect_button.setEnabled(False)
        tab.disconnect_button.setEnabled(True)
        text = lines_after(lambda: tab.bridge.token_report({"state": "invalid"}))
    finally:
        QMessageBox.warning = orig
    check("a rejected token is reported", "rejected the token" in text and warned, (text, warned))
    check("and Connect is available again", tab.connect_button.isEnabled()
          and not tab.disconnect_button.isEnabled())

    # the real Connect with a rejected token: no bot is created
    import ui.twitch_tab as tt
    orig_check = tt.token_check.check

    async def rejected(token, channel, fetch=None):
        return {"state": "invalid"}
    tt.token_check.check = rejected
    QMessageBox.warning = staticmethod(lambda *a, **kw: QMessageBox.Ok)
    created = []
    orig_bot = tt.TwitchBot
    tt.TwitchBot = lambda *a, **kw: created.append(1)
    try:
        w.config_manager.save_twitch_config(access_token="expired")
        tab.channel_input.setText("streamer")
        before = chat.toPlainText()
        tab.connect_bot()
        tab.bot_thread.join(10)
        pump(300)
        text = chat.toPlainText()[len(before):]
    finally:
        tt.token_check.check = orig_check
        tt.TwitchBot = orig_bot
        QMessageBox.warning = orig
    check("Connect with a rejected token creates no bot", not created and tab.bridge.bot is None, created)
    check("it says why, not 'reconnect manually'",
          "rejected the token" in text and "reconnect manually" not in text, text)
    check("the buttons are back", tab.connect_button.isEnabled())


kit.start(body, delay_ms=400)
