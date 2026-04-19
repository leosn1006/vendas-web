import logging
import os
from logging.handlers import TimedRotatingFileHandler


_VALID_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def _build_log_namer(service_name: str):
    def _namer(default_name: str) -> str:
        # default_name esperado: /path/log_app.log.2026-02-25
        path_parts = default_name.rsplit(".", 1)
        if len(path_parts) != 2:
            return default_name

        base_path, date_part = path_parts
        date_part = date_part.replace("-", "_")
        directory = os.path.dirname(base_path)
        return os.path.join(directory, f"log_{service_name}_{date_part}_001.log")

    return _namer


def setup_rotating_file_logging(service_name: str) -> None:
    root_logger = logging.getLogger()
    if any(getattr(handler, "_vendas_file_logger", False) for handler in root_logger.handlers):
        return

    log_level_name = os.getenv("LOG_LEVEL", "info").strip().lower()
    log_level = _VALID_LOG_LEVELS.get(log_level_name, logging.INFO)
    root_logger.setLevel(log_level)

    log_dir = os.getenv("LOG_DIR", "/app/storage/logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"log_{service_name}.log")
    handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=int(os.getenv("LOG_RETENTION_DAYS", "30")),
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    handler.namer = _build_log_namer(service_name)
    handler.setLevel(logging.DEBUG)
    handler._vendas_file_logger = True
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    root_logger.addHandler(handler)
