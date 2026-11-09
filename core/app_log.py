"""Логирование работы программы.

- Пишет в command_editor.log рядом с config.json (RotatingFileHandler:
  1 МБ x 3 бэкапа — файл не разрастается бесконечно).
- Маскирует чувствительные данные (токены, секреты, пароли) — в лог
  попадает только работа программы, не секретные строки.
- Лог прошлого запуска сдвигается в .1/.2/.3, а не удаляется.
- Журнал падений command_editor_crash.log: необработанные исключения
  (UI, потоки, цикл asyncio бота), ошибки Qt, faulthandler.
- Py3.8-совместимо, без внешних зависимостей.
"""
import faulthandler
import logging
import logging.handlers
import os
import re
import sys
import threading
import time
import traceback
import builtins

LOG_FILE_NAME = "command_editor.log"
LOG_MAX_BYTES = 1024 * 1024  # 1 МБ
LOG_BACKUP_COUNT = 3

# Чувствительные ключи: если в сообщении есть "token ... = <value>",
# значение маскируется.
_SENSITIVE_RE = re.compile(
    r'(?i)((?:access|refresh|client|api|auth|session)?_?(?:token|secret|password|passwd|pwd|key)\s*[=:]\s*)\S+'
)


class _SensitiveDataFilter(logging.Filter):
    """Маскирует значения токенов/секретов/паролей в лог-записях."""

    def filter(self, record):
        try:
            msg = record.getMessage()
            if _SENSITIVE_RE.search(msg):
                record.msg = _SENSITIVE_RE.sub(r'\1***MASKED***', msg)
                record.args = None
        except Exception:
            # Никогда не роняем логирование из-за фильтра
            pass
        return True


def setup_logging(program_dir, overwrite=True):
    """Настроить логгер приложения. Идемпотентно (повторный вызов не
    добавляет дублирующих хендлеров). Возвращает логгер.

    overwrite=True — лог перезаписывается при каждом запуске (не копится
    куча файлов); RotatingFileHandler при этом страхует от разрастания
    файла в течение одной сессии (1 МБ x 3)."""
    logger = logging.getLogger("command_editor")
    if getattr(logger, "_ce_configured", False):
        return logger
    logger.setLevel(logging.INFO)

    log_path = os.path.join(str(program_dir), LOG_FILE_NAME)
    try:
        if overwrite:
            # Лог прошлого запуска не удаляем, а сдвигаем в .1 (.1 -> .2 ...):
            # после падения он нужен, а пользователь обычно сразу
            # перезапускает программу.
            rotate_previous_log(log_path)
        handler = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8")
    except Exception:
        # Если файл создать не удалось (права, диск) — деградируем до null,
        # чтобы приложение работало без логов, а не упало.
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"))
    handler.addFilter(_SensitiveDataFilter())
    logger.addHandler(handler)
    logger._ce_configured = True
    return logger


def install_print_bridge():
    """Направить print() в лог приложения (плюс в stdout, как раньше).

    Бот и UI пишут print() повсюду — это и есть «работа программы».
    Через логгер проходит _SensitiveDataFilter, поэтому токены/секреты
    в файл не попадают. Идемпотентно."""
    if getattr(install_print_bridge, "_done", False):
        return
    real_print = builtins.print

    def _print(*args, **kwargs):
        try:
            text = " ".join(str(a) for a in args)
            logger.info(text)
        except Exception:
            pass
        real_print(*args, **kwargs)

    builtins.print = _print
    install_print_bridge._done = True


def rotate_previous_log(log_path, keep=LOG_BACKUP_COUNT):
    """log -> log.1 -> log.2 ... (самый старый, log.<keep>, выбрасывается)."""
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return
    for i in range(keep, 0, -1):
        src = log_path if i == 1 else "%s.%d" % (log_path, i - 1)
        dst = "%s.%d" % (log_path, i)
        if os.path.exists(src):
            try:
                os.replace(src, dst)
            except OSError:
                pass


# -- журнал падений ------------------------------------------------------------
CRASH_LOG_NAME = "command_editor_crash.log"
_crash = {"path": None, "fault_file": None, "prev": None}


def _write_crash(title, text):
    """Дописать запись в журнал падений и в обычный лог. Никогда не бросает."""
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = "==== %s  %s ====\n%s\n" % (stamp, title, text.rstrip())
        try:
            entry = _SENSITIVE_RE.sub(r'\1***MASKED***', entry)
        except Exception:
            pass
        if _crash["path"]:
            with open(_crash["path"], "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        logger.critical(entry)
    except Exception:
        pass


def _format(exc_type, exc, tb):
    return "".join(traceback.format_exception(exc_type, exc, tb))


def install_crash_handlers(program_dir, fault_handler=True):
    """Ловить необработанные исключения: главный поток (в т.ч. слоты Qt),
    другие потоки, жёсткие падения интерпретатора (faulthandler).
    Возвращает путь к журналу падений. Повторный вызов безопасен."""
    path = os.path.join(str(program_dir), CRASH_LOG_NAME)
    _crash["path"] = path
    if _crash["prev"] is None:
        _crash["prev"] = (sys.excepthook, threading.excepthook)
    prev_sys, prev_thread = _crash["prev"]

    def _sys_hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return prev_sys(exc_type, exc, tb)
        _write_crash("Unhandled exception", _format(exc_type, exc, tb))
        # Не вызываем стандартный хук PyQt: с ним необработанное
        # исключение в слоте завершает программу (qFatal).

    def _thread_hook(args):
        if args.exc_type is SystemExit:
            return
        name = getattr(args.thread, "name", "?")
        _write_crash("Unhandled exception in thread %s" % name,
                     _format(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook

    if fault_handler and _crash["fault_file"] is None:
        try:
            # Держим файл открытым всю жизнь процесса: faulthandler пишет
            # в него при access violation / зависании C-кода.
            _crash["fault_file"] = open(path, "a", encoding="utf-8")
            faulthandler.enable(file=_crash["fault_file"], all_threads=True)
        except Exception:
            _crash["fault_file"] = None
    return path


def uninstall_crash_handlers():
    """Вернуть исходные хуки (для тестов)."""
    if _crash["prev"] is not None:
        sys.excepthook, threading.excepthook = _crash["prev"]
        _crash["prev"] = None
    if _crash["fault_file"] is not None:
        try:
            faulthandler.disable()
            _crash["fault_file"].close()
        except Exception:
            pass
        _crash["fault_file"] = None
    _crash["path"] = None


def install_asyncio_handler(loop):
    """Ошибки в задачах/колбэках цикла asyncio (поток бота) - в журнал падений."""
    def _handler(lp, context):
        exc = context.get("exception")
        msg = context.get("message", "asyncio error")
        if exc is not None:
            text = _format(type(exc), exc, exc.__traceback__)
        else:
            text = msg
        _write_crash("asyncio: %s" % msg, text)
    loop.set_exception_handler(_handler)


# Глобальный логгер по умолчанию (до setup_logging — NullHandler, чтобы
# print->logger не падал, если setup ещё не вызван).
logger = logging.getLogger("command_editor")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.INFO)