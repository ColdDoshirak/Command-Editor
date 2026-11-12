"""Global hotkeys (2.0): Settings -> Global hotkeys, real RegisterHotKey,
a press simulated by posting WM_HOTKEY to the window."""
import ctypes
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)

# unusual combinations, unlikely to be taken on the test machine
COMBOS = {"skip": "Ctrl+Alt+Shift+F9", "pause": "Ctrl+Alt+Shift+F10", "stop": "Ctrl+Alt+Shift+F11"}


def body(k):
    from PyQt5.QtGui import QKeySequence
    from ui import hotkeys as hk
    w, check, pump = k.w, k.check, k.pump
    check("off by default", w.hotkeys.registered() == [] and not w.hotkey_settings()["enabled"])

    w.apply_theme("sidebar"); pump(300)
    panel = getattr(w.settings_tab, "original_tab", w.settings_tab)   # themed: wrapped
    check("settings page has the hotkeys card", hasattr(panel, "hotkey_switch"))
    for name, combo in COMBOS.items():
        panel.hotkey_edits[name].setKeySequence(QKeySequence(combo))
    panel.hotkey_switch.setChecked(True); pump()
    check("enabled: all three registered", w.hotkeys.registered() == ["pause", "skip", "stop"],
          (w.hotkeys.registered(), w.hotkey_problems))
    with open(os.path.join(DATA, "config.json"), encoding="utf-8") as f:
        saved = json.load(f).get("hotkeys", {})
    check("saved to config.json", saved.get("enabled") is True and saved.get("skip") == COMBOS["skip"], saved)

    sent = []
    w.twitch_tab.bridge.call = lambda name, *a: sent.append(name) or True
    user32 = ctypes.windll.user32
    hwnd = int(w.winId())
    for hotkey_id, name in sorted(w.hotkeys._ids.items()):
        user32.PostMessageW(hwnd, hk.WM_HOTKEY, hotkey_id, 0)
    pump(300)
    check("presses reach the bot actions",
          sorted(sent) == ["hotkey_skip", "hotkey_stop_all", "hotkey_toggle_pause"], sent)
    check("presses are shown in the chat panel",
          "[Hotkey] Skip what is playing" in w.twitch_tab.chat_display.toPlainText())

    # a combination another program holds
    mods, vk = hk.to_native(COMBOS["skip"])
    w.hotkeys.clear()
    taken = user32.RegisterHotKey(None, 0xBEEF, mods | hk.MOD_NOREPEAT, vk)
    try:
        problems = w.set_hotkey_settings(dict(w.hotkey_settings()))
        pump()
        check("a taken combination is reported", taken and "skip" in problems
              and "pause" in w.hotkeys.registered(), (taken, problems))
        panel._show_hotkey_problems(problems)
        check("and shown on the card", "taken" in panel.hotkey_status.text(), panel.hotkey_status.text())
    finally:
        user32.UnregisterHotKey(None, 0xBEEF)

    check("keys that cannot be global are refused", hk.to_native("Ctrl+Alt+Shift+F9") is not None
          and hk.to_native("") is None and hk.to_native("Ctrl+Ä") is None)
    panel.hotkey_switch.setChecked(False); pump()
    check("disabled: nothing registered", w.hotkeys.registered() == [])
    w.apply_theme("classic"); pump(200)


kit.start(body, delay_ms=400)
