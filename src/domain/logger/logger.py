from typing import List

import logging
import logging.config
from logging import Logger
from pathlib import Path

from src.domain.logger.formatter import DefaultFormatter


_DEFAULT_LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            '()': DefaultFormatter,
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'formatter': 'default',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
        },
        # 'file': {
        #     'level': 'DEBUG',
        #     'formatter': 'default',
        #     'class': 'logging.FileHandler',
        #     'filename': 'logs/sinfonia.log',
        #     'mode': 'a',
        # }
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
_DEFAULT_LOGGER: Logger = logging.config.dictConfig(_DEFAULT_LOGGING_CONFIG)


# Named loggers
_LOGGERS: List[Logger] = list()


def get_default_logger() -> Logger:
    return logging.getLogger()


def configure_logger_from_yaml(name: str, path: Path) -> Logger:
    """Register logger based given yaml configuration."""    
    raise NotImplementedError()
