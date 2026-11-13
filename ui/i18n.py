"""Interface language (2.0): Russian or English.

The texts in the code are English; ui/i18n_ru.py holds their Russian
versions. tr("Save") returns the text in the current language (the
English one when there is no translation).

Which language: config.json "language" - "system" (the default: Russian
when Windows is in Russian, otherwise English), "ru" or "en". It is set
once at start-up; a change in Settings applies after a restart.
COMMAND_EDITOR_LANG=en|ru overrides it (the UI checks run in English).

Values that are saved to files (Everyone / Moderator, Points / Hours,
SC / Chat ...) and the bot's chat answers are not translated.

Python 3.8 / PyQt5.
"""
import os

LANGUAGES = (("system", "System"), ("ru", "Русский"), ("en", "English"))
ENV = "COMMAND_EDITOR_LANG"

_current = "en"
_table = {}


def system_language():
    """"ru" when the system's UI language is Russian, otherwise "en"."""
    try:
        from PyQt5.QtCore import QLocale
        langs = list(QLocale.system().uiLanguages()) or [QLocale.system().name()]
        first = str(langs[0]).lower()
    except Exception:
        first = ""
    return "ru" if first.startswith("ru") else "en"


def resolve(setting):
    """The language to use for a stored setting ("system" / "ru" / "en")."""
    env = os.environ.get(ENV, "").strip().lower()
    if env in ("ru", "en"):
        return env
    setting = str(setting or "system").strip().lower()
    if setting in ("ru", "en"):
        return setting
    return system_language()


def set_language(lang):
    global _current, _table
    _current = "ru" if lang == "ru" else "en"
    if _current == "ru":
        from ui.i18n_ru import RU
        _table = RU
    else:
        _table = {}


def language():
    return _current


def tr(text):
    """`text` (English) in the current language."""
    return _table.get(text, text) if _table else text


def N_(text):
    """Marks a text for translation where it is defined (a table of labels);
    it is translated with tr() where it is shown."""
    return text
