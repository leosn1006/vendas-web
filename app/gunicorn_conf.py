import logging

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
loglevel = 'info'
logger_class = 'gunicorn_conf.HealthAwareGunicornLogger'
