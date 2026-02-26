import logging
import os

from gunicorn.glogging import Logger


class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        return '"GET /health ' not in message


class HealthAwareGunicornLogger(Logger):
    def setup(self, cfg):
        super().setup(cfg)
        health_filter = HealthCheckFilter()
        for handler in self.access_log.handlers:
            handler.addFilter(health_filter)


accesslog = '-'
errorlog = '-'
_VALID_LOG_LEVELS = {'debug', 'info', 'warning', 'error', 'critical'}
_env_log_level = os.getenv('LOG_LEVEL', 'info').strip().lower()
loglevel = _env_log_level if _env_log_level in _VALID_LOG_LEVELS else 'info'
logger_class = 'gunicorn_conf.HealthAwareGunicornLogger'
