"""Qt's own warnings and errors -> the program log (critical ones also to
the crash journal). The rest of the logging is core/app_log.py.

Python 3.8 compatible.
"""
from PyQt5.QtCore import qInstallMessageHandler, QtWarningMsg, QtCriticalMsg, QtFatalMsg

from core.app_log import _write_crash, logger


def install_qt_message_handler():
    """Предупреждения и ошибки самого Qt - в лог (критичные - и в журнал падений)."""
    def _qt_handler(mode, context, message):
        try:
            if mode in (QtCriticalMsg, QtFatalMsg):
                _write_crash("Qt", "%s (%s:%s)" % (message, context.file, context.line))
            elif mode == QtWarningMsg:
                logger.warning("Qt: %s", message)
        except Exception:
            pass
    qInstallMessageHandler(_qt_handler)
