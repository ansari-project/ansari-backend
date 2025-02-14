# This file aims to provide a loguru logger instance for the caller file (e.g., main_api.py, etc.).
# NOTE: Using loguru for logging (for simpler syntax); check below resources for reasons/details:
#   https://nikhilakki.in/loguru-logging-in-python-made-fun-and-easy#heading-why-use-loguru-over-the-std-logging-module
#   https://loguru.readthedocs.io/en/stable/resources/migration.html

import copy
import os
import sys

from loguru import logger
from loguru._logger import Logger

from ansari.config import get_settings


def get_logger(
    logging_level: str = None,
) -> Logger:
    """Creates and returns a logger instance for the specified caller file.

    Args:
        caller_file_name (str): The name of the file requesting the logger.
        logging_level (Optional[str]): The logging level to be set for the logger.
                                    If None, it defaults to the LOGGING_LEVEL from settings.

    Returns:
        logger: Configured logger instance.

    """
    if logging_level is None:
        logging_level = get_settings().LOGGING_LEVEL.upper()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSSS}</green> | "
        + "<level>{level}</level> | "
        + "<magenta>{name}:{function}:{line}</magenta> | "
        + "<level>{message}</level>"
    )

    logger.remove()
    cur_logger = copy.deepcopy(logger)

    # In colorize, If None, the choice is automatically made based on the sink being a tty or not.
    cur_logger.add(
        sys.stdout, level=logging_level, format=log_format, enqueue=True, colorize=os.getenv("GITHUB_ACTIONS", None)
    )

    return cur_logger
