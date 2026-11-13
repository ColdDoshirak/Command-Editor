"""The window in Russian (2.0): it starts, the tabs are translated, and the
English texts still visible are listed (shown with -v / in the details)."""
import os
import re
import sys

os.environ["COMMAND_EDITOR_LANG"] = "ru"           # before uikit (it defaults to en)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture  # noqa: E402
import uikit  # noqa: E402

DATA, OUT = uikit.args()
fixture.editor_set(DATA)
kit = uikit.boot(DATA, OUT)

# Latin words that are fine in the Russian interface (names, formats, codes)
ALLOWED = {"twitch", "obs", "sc", "chat", "both", "id", "client", "oauth", "streamlabs", "streamer",
           "bot", "github", "command", "editor", "fk", "json", "moderators", "commands", "admins",
           "admin", "api", "general", "song", "ctrl", "shift", "enter", "del", "z", "url", "show",
           "now", "queue", "recent", "size", "points", "random", "user", "target", "args", "count",
           "currency", "channel", "everyone", "regular", "subscriber", "vip", "moderator", "v",
           "kb", "mb", "b", "h", "wav", "mp3", "ogg", "flac", "live", "offline", "on", "off",
           "sidebar", "spreadsheet", "midnight", "classic", "design", "browser", "source", "x",
           "money", "music", "tune", "new", "hello", "multiline", "more", "examples", "points",
           "s", "min", "max", "ru", "en", "token", "refresh", "access", "dummy", "test",
           "windows"}


def _latin_words(text):
    return [w for w in re.findall(r"[A-Za-z][A-Za-z']+", text or "") if w.lower() not in ALLOWED]


def body(k):
    from PyQt5.QtWidgets import QLabel, QPushButton, QCheckBox, QGroupBox, QWidget
    w, check, pump = k.w, k.check, k.pump
    from ui import i18n
    check("the interface is Russian", i18n.language() == "ru")
    tabs = [w.tab_widget.tabText(i) for i in range(w.tab_widget.count())]
    check("tab names are Russian", "Команды" in tabs and "Настройки" in tabs and "Таймеры" in tabs, tabs)
    leftovers = {}
    for theme in ("classic", "sidebar"):
        w.apply_theme(theme); pump(300)
        for i in range(w.tab_widget.count()):
            w.tab_widget.setCurrentIndex(i); pump(150)
            k.shot("i18n_%s_%02d" % (theme, i))
            page = w.tab_widget.widget(i)
            for cls in (QLabel, QPushButton, QCheckBox, QGroupBox):
                for wid in page.findChildren(cls):
                    if not wid.isVisibleTo(page):
                        continue
                    text = wid.title() if cls is QGroupBox else wid.text()
                    if "<" in text:                   # rich text: strip tags
                        text = re.sub(r"<[^>]+>", " ", text)
                    words = _latin_words(text)
                    if words:
                        leftovers.setdefault(text.strip()[:80], "%s/%s" % (theme, w.tab_widget.tabText(i)))
            from PyQt5.QtWidgets import QAbstractItemView, QAbstractSpinBox
            from PyQt5.QtCore import Qt
            for view in page.findChildren(QAbstractItemView):
                model = view.model()
                if model is None or not view.isVisibleTo(page) or not hasattr(view, "horizontalHeader"):
                    continue
                for c in range(model.columnCount()):
                    text = model.headerData(c, Qt.Horizontal, Qt.DisplayRole) or ""
                    if _latin_words(str(text)):
                        leftovers.setdefault("[header] " + str(text), "%s/%s" % (theme, w.tab_widget.tabText(i)))
            for spin in page.findChildren(QAbstractSpinBox):
                if spin.isVisibleTo(page) and _latin_words(spin.text()):
                    leftovers.setdefault("[spin] " + spin.text(), "%s/%s" % (theme, w.tab_widget.tabText(i)))
        if w.sidebar_nav is not None:
            nav = [b.text().strip() for b in w.sidebar_nav.findChildren(QPushButton)]
            check("sidebar nav is Russian", "Команды" in nav and "Таймеры" in nav, nav)
    report = "\n".join("%s  <- %s" % (t, where) for t, where in sorted(leftovers.items()))
    if OUT:
        with open(os.path.join(OUT, "i18n_leftovers.txt"), "w", encoding="utf-8") as f:
            f.write(report)
    check("no English text left on the screens", not leftovers, report)
    w.apply_theme("classic"); pump(200)


kit.start(body, delay_ms=400)
