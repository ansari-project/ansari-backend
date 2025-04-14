# This file provides a standard Python logging instance for the caller file (e.g., main_api.py, etc.).

import logging
import os
import sys
import re
import time
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install as install_rich_traceback

from ansari.config import get_settings


# Install rich traceback handler globally
install_rich_traceback(
    show_locals=True,
    max_frames=10,
    suppress=[],
    width=None,
    word_wrap=True,
)


def create_file_handler(name: str, logging_level: str) -> logging.FileHandler:
    """Creates and configures a file handler for logging.

    Args:
        name (str): The name of the module for the log file.
        logging_level (str): The logging level to set for the handler.

    Returns:
        logging.FileHandler: Configured file handler instance.
    """
    # Ensure logs directory exists
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{name}.log")
    file_handler = logging.FileHandler(
        filename=log_file,
        mode="a",  # Append mode
        encoding="utf-8",  # Use UTF-8 encoding to support Unicode characters
    )
    file_handler.setLevel(logging_level)

    # Custom formatter for files with forward slashes and function name in square brackets
    class VSCodePathFormatter(logging.Formatter):
        # ANSI color code regex pattern
        ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

        def format(self, record):
            # Format path with forward slashes and function name in square brackets
            path_format = f"{record.name.replace('.','/')}:{record.lineno} [{record.funcName}()]"

            # Format time without milliseconds
            # Override the default formatTime to remove milliseconds
            created = self.converter(record.created)
            time_format = time.strftime("%Y-%m-%d %H:%M:%S", created)

            # Get the message and strip any ANSI color codes
            message = record.getMessage()
            clean_message = self.ANSI_ESCAPE_PATTERN.sub("", message)

            # Combine everything
            return f"{time_format} | {record.levelname} | {path_format} | {clean_message}"

    # Use the custom formatter for files
    file_formatter = VSCodePathFormatter()  # No datefmt needed as we're formatting time manually
    file_handler.setFormatter(file_formatter)
    return file_handler


def get_logger(name: str) -> logging.Logger:
    """Creates and returns a logger instance for the specified module.

    Args:
        name (str): The name of the module requesting the logger (typically __name__).

    Returns:
        logging.Logger: Configured logger instance.
    """
    logging_level = get_settings().LOGGING_LEVEL.upper()

    # Create a Rich console for logging
    console = Console(
        highlight=True,  # Syntax highlighting
        markup=True,  # Enable Rich markup
        log_path=False,  # Don't write to a log file directly - we'll handle that separately
        log_time_format="%Y-%m-%d %H:%M:%S",
    )

    # Create a logger
    logger = logging.getLogger(name)

    # Clear any existing handlers to avoid duplicate logs
    if logger.handlers:
        logger.handlers.clear()

    # Set the logging level
    logger.setLevel(logging_level)

    # Create Rich handler with VS Code compatible formatting in DEV_MODE
    rich_handler = RichHandler(
        console=console,
        enable_link_path=get_settings().DEV_MODE,  # Enable VS Code clickable links in DEV_MODE
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        show_time=True,
        show_level=True,
        show_path=True,
    )
    rich_handler.setLevel(logging_level)

    # Add the Rich handler to the logger
    logger.addHandler(rich_handler)

    # Add file handler if DEV_MODE is enabled
    if get_settings().DEV_MODE:
        file_handler = create_file_handler(name, logging_level)
        logger.addHandler(file_handler)

    return logger
