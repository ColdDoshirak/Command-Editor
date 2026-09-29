"""Логирование работы программы.

- Пишет в command_editor.log рядом с config.json (RotatingFileHandler:
  1 МБ x 3 бэкапа — файл не разрастается бесконечно).
- Маскирует чувствительные данные (токены, секреты, пароли) — в лог
  попадает только работа программы, не секретные строки.
- Py3.8-совместимо, без внешних зависимостей.
"""
import logging
import logging.handlers
import os
import re
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
            # Убираем вчерашний лог: файл создаётся пустым,
            # ротация внутри сессии работает поверх него.
            if os.path.exists(log_path):
                os.remove(log_path)
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


# Глобальный логгер по умолчанию (до setup_logging — NullHandler, чтобы
# print->logger не падал, если setup ещё не вызван).
logger = logging.getLogger("command_editor")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.INFO)