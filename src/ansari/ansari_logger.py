# This file provides a standard Python logging instance for the caller file (e.g., main_api.py, etc.).

import os
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

    # Add file handler if DEV_MODE is enabled
    if get_settings().DEV_MODE:
        # Ensure logs directory exists
        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)

        log_file = os.path.join(log_dir, f"{name}.log")
        # Using standard FileHandler instead of TimedRotatingFileHandler
        # Add encoding='utf-8' to handle Unicode characters like emojis
        file_handler = logging.FileHandler(
            filename=log_file,
            mode="a",  # Append mode
            encoding="utf-8",  # Use UTF-8 encoding to support Unicode characters
        )
        file_handler.setLevel(logging_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
