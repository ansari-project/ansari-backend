import logging

from ansari.config import get_settings


def get_logger(
    caller_file_name: str, logging_level=None, debug_mode=None
) -> logging.Logger:
    """
    Creates and returns a logger instance for the specified caller file.

    Args:
        caller_file_name (str): The name of the file requesting the logger.
        logging_level (Optional[str]): The logging level to be set for the logger.
                                    If None, it defaults to the LOGGING_LEVEL from settings.
        debug_mode (Optional[bool]): If True, adds a console handler to the logger.
                                    If None, it defaults to the DEBUG_MODE from settings.
    Returns:
        logging.Logger: Configured logger instance.
    """
    logger = logging.getLogger(caller_file_name)
    if logging_level is None:
        logging_level = get_settings().LOGGING_LEVEL.upper()
    logger.setLevel(logging_level)

    if debug_mode is not False and get_settings().DEBUG_MODE:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging_level)
        logger.addHandler(console_handler)

    return logger
