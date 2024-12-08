import sys

from loguru import logger
from loguru._logger import Logger

from ansari.config import get_settings


# Using loguru for logging, check below resources for reasons/details:
# https://nikhilakki.in/loguru-logging-in-python-made-fun-and-easy#heading-why-use-loguru-over-the-std-logging-module
# https://loguru.readthedocs.io/en/stable/resources/migration.html
def get_logger(
    logging_level: str = None,
    debug_mode: bool = None,
) -> Logger:
    """Creates and returns a logger instance for the specified caller file.

    Args:
        caller_file_name (str): The name of the file requesting the logger.
        logging_level (Optional[str]): The logging level to be set for the logger.
                                    If None, it defaults to the LOGGING_LEVEL from settings.
        debug_mode (Optional[bool]): If True, adds a console handler to the logger.
                                    If None, it defaults to the DEBUG_MODE from settings.

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
    logger.add(
        sys.stdout,
        level=logging_level,
        format=log_format,
        enqueue=True,
    )

    return logger
