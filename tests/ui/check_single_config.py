"""Step 1.2: the whole app shares one ConfigManager. Extra instances read
config.json once and then drift: a setting saved through one was not seen
by the others until the next start."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)

sys.path.insert(0, uikit.REPO)
import config_manager  # noqa: E402
created = []
_orig_init = config_manager.ConfigManager.__init__


def _counting_init(self, *a, **kw):
    import traceback
    created.append("".join(traceback.format_stack(limit=4)[:-1]))
    _orig_init(self, *a, **kw)


config_manager.ConfigManager.__init__ = _counting_init
kit = uikit.boot(DATA, OUT)


def body(k):
    w, check, pump = k.w, k.check, k.pump
    pump(300)
    check("one ConfigManager created at start", len(created) == 1,
          "%d created:\n%s" % (len(created), "\n---\n".join(created)))
    for name, obj in (("Sys.Commands tab", w.sys_commands_tab),
                      ("Twitch tab", w.twitch_tab)):
        check("%s shares the app's ConfigManager" % name, obj.config_manager is w.config_manager)
    # a setting changed through the app is what the currency backups use
    w.config_manager.set_max_currency_backups(3)
    w.currency_manager._load_backup_settings()
    check("currency reads the shared config", w.currency_manager.max_currency_backups == 3,
          w.currency_manager.max_currency_backups)
    w.apply_theme("midnight"); pump(200)
    w.apply_theme("classic"); pump(200)
    check("no new ConfigManager on theme switch", len(created) == 1, len(created))


kit.start(body, delay_ms=400)
