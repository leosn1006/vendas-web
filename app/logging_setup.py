import datetime
import glob
import logging
import os
import time


_VALID_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


class DailyFileHandler(logging.FileHandler):
    """
    Handler diário multiprocesso-safe: o arquivo ativo já tem a data no nome
    (log_app_2026_05_10_001.log), sem precisar renomear na rotação.
    """

    def __init__(self, service_name: str, log_dir: str, backup_count: int = 30):
        self.service_name = service_name
        self.log_dir = log_dir
        self.backup_count = backup_count
        super().__init__(filename=self._today_path(), mode="a", encoding="utf-8")
        self._schedule_next_rollover()

    def _today_path(self) -> str:
        date_str = datetime.date.today().strftime("%Y_%m_%d")
        return os.path.join(self.log_dir, f"log_{self.service_name}_{date_str}_001.log")

    def _schedule_next_rollover(self):
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        self._rollover_at = time.mktime(
            datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day).timetuple()
        )

    def emit(self, record: logging.LogRecord):
        if time.time() >= self._rollover_at:
            self._do_rollover()
        super().emit(record)

    def _do_rollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        self.baseFilename = self._today_path()
        self.stream = self._open()
        self._schedule_next_rollover()
        self._cleanup_old()

    def _cleanup_old(self):
        pattern = os.path.join(self.log_dir, f"log_{self.service_name}_[0-9][0-9][0-9][0-9]_*_001.log")
        files = sorted(glob.glob(pattern))
        while len(files) > self.backup_count:
            try:
                os.remove(files.pop(0))
            except OSError:
                pass


def setup_rotating_file_logging(service_name: str) -> None:
    root_logger = logging.getLogger()
    if any(getattr(handler, "_vendas_file_logger", False) for handler in root_logger.handlers):
        return

    log_level_name = os.getenv("LOG_LEVEL", "info").strip().lower()
    log_level = _VALID_LOG_LEVELS.get(log_level_name, logging.INFO)
    root_logger.setLevel(log_level)

    log_dir = os.getenv("LOG_DIR", "/app/storage/logs")
    os.makedirs(log_dir, exist_ok=True)

    handler = DailyFileHandler(
        service_name=service_name,
        log_dir=log_dir,
        backup_count=int(os.getenv("LOG_RETENTION_DAYS", "30")),
    )
    handler.setLevel(logging.DEBUG)
    handler._vendas_file_logger = True
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    root_logger.addHandler(handler)
