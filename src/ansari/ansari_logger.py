# This file provides a standard Python logging instance for the caller file (e.g., main_api.py, etc.).

import logging
import sys

from ansari.config import get_settings


def get_logger(name: str) -> logging.Logger:
    """Creates and returns a logger instance for the specified module.

    Args:
        name (str): The name of the module requesting the logger (typically __name__).

    Returns:
        logging.Logger: Configured logger instance.
    """
    logging_level = get_settings().LOGGING_LEVEL.upper()

    # Create a logger
    logger = logging.getLogger(name)

    # Clear any existing handlers to avoid duplicate logs
    if logger.handlers:
        logger.handlers.clear()

    # Set the logging level
    logger.setLevel(logging_level)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging_level)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Add formatter to handler
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    return logger
