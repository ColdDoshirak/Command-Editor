"""Every file and folder the app reads or writes, in one place.

Data lives next to the program: next to command_editor.exe when frozen
(PyInstaller), next to the project when run from source. It used to be
mixed - some files next to the program, others relative to the current
working directory - so starting the app from a shortcut with another
"Start in" folder split the data between two places.

Tests (or a portable setup) can move the data folder with set_app_dir()
or the COMMAND_EDITOR_HOME environment variable.

Python 3.8 compatible, no Qt.
"""
import os
import shutil
import sys
from pathlib import Path

ENV_HOME = "COMMAND_EDITOR_HOME"

_override = None


def _program_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # core/paths.py -> project root
    return Path(__file__).resolve().parent.parent


def app_dir():
    """Folder with the user's data (config, commands, currency, backups)."""
    if _override is not None:
        return _override
    env = os.environ.get(ENV_HOME)
    if env:
        return Path(env)
    return _program_dir()


def set_app_dir(path):
    """Point the data folder somewhere else (None restores the default)."""
    global _override
    _override = Path(path) if path else None


def resource_dir():
    """Read-only files bundled with the program (e.g. the memes folder)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", _program_dir()))
    return _program_dir()


def path(*parts):
    return app_dir().joinpath(*parts)


# -- files ----------------------------------------------------------------
def config_file():
    return path("config.json")


def twitch_file():
    return path("twitch_config.json")


def commands_file():
    return path("commands.json")


def moderators_file():
    return path("moderators.json")


def system_commands_file():
    return path("system_commands.json")


def users_currency_file():
    return path("users_currency.json")


def currency_settings_file():
    return path("data", "currency_settings.json")


def ranks_file():
    return path("data", "ranks.json")


def legacy_ini_file():
    return path("config.ini")


# -- folders --------------------------------------------------------------
def backups_dir():
    return path("backups")


def comprehensive_backups_dir():
    return path("backups", "comprehensive")


def currency_backups_dir():
    return path("backups", "currency")


def history_dir():
    return path("command_history")


# -- one-time migration ------------------------------------------------------
# Files that older versions wrote relative to the working directory.
_CWD_FILES = (
    ("data", "currency_settings.json"),
    ("data", "ranks.json"),
    ("commands.json",),
    ("config.ini",),
)
_CWD_DIRS = (
    ("command_history",),
    ("backups", "comprehensive"),
)
# Only folders that clearly belong to Command Editor are migrated from,
# so starting the app from an unrelated folder copies nothing.
_MARKERS = (
    ("command_history",),
    ("data", "currency_settings.json"),
    ("data", "ranks.json"),
)


def migrate_from_cwd(cwd=None):
    """Copy data that older versions left in the working directory.

    Copies only what is missing next to the program; never overwrites and
    never deletes. Returns [(source, destination)] of copied files.
    """
    src_root = Path(cwd or os.getcwd()).resolve()
    dst_root = app_dir().resolve()
    if src_root == dst_root:
        return []
    if not any(src_root.joinpath(*m).exists() for m in _MARKERS):
        return []
    copied = []

    def _copy(src, dst):
        if src.is_file() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            copied.append((src, dst))

    for rel in _CWD_FILES:
        _copy(src_root.joinpath(*rel), dst_root.joinpath(*rel))
    for rel in _CWD_DIRS:
        folder = src_root.joinpath(*rel)
        if folder.is_dir():
            for f in folder.iterdir():
                _copy(f, dst_root.joinpath(*rel) / f.name)
    return copied
