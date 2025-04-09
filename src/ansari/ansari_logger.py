# This file provides a standard Python logging instance for the caller file (e.g., main_api.py, etc.).

import logging
import os
import sys

from ansari.config import get_settings


# ANSI color codes
class Colors:
    RESET = "\033[0m"
    GREEN = "\033[32m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    YELLOW = "\033[33m"
    WHITE = "\033[37m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    LEVEL_COLORS = {
        "DEBUG": "\033[34m",  # Blue
        "INFO": "\033[0m",  # RESET # (alternative: \033[37m - White),
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[1;31m",  # Bold Red
    }


class EnhancedFormatter(logging.Formatter):
    """Advanced formatter that provides rich, colorful logging with enhanced exception handling.

    Features:
    - Colorful log output similar to loguru
    - Rich exception formatting with source code context
    - Local variable display in exception tracebacks
    - Smart color detection based on terminal capabilities
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Determine if colors should be used
        self.use_colors = sys.stdout.isatty() or os.environ.get("GITHUB_ACTIONS") is not None

    def colorize(self, text, color):
        """Wrap text with color codes if colors are enabled."""
        if self.use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text

    def format(self, record):
        # Get the level color or default to reset if not found
        level_color = Colors.LEVEL_COLORS.get(record.levelname, Colors.RESET)

        # Format components with appropriate colors (if enabled)
        timestamp = self.colorize(self.formatTime(record), Colors.GREEN)
        level = self.colorize(record.levelname, level_color)
        if get_settings().DEV_MODE:
            # Create a clickable VS Code link in the format that VS Code recognizes
            code_loc = f"{record.name.replace(".", "/")}:{record.lineno} [{record.funcName}()]"
        else:
            # Else, use the standard format
            code_loc = f"{record.name}:{record.funcName}:{record.lineno}"
        code_location = self.colorize(code_loc, Colors.MAGENTA)

        # Use level color for message except for INFO level (keep those plain)
        if record.levelname == "INFO":
            message = record.getMessage()  # No coloring for INFO messages
        else:
            message = self.colorize(record.getMessage(), level_color)

        # Combine everything with the pipe separator
        formatted_log = f"{timestamp} | {level} | {code_location} | {message}"

        # Add exception info if available
        if record.exc_info:
            formatted_exception = self.format_exception(record.exc_info)
            formatted_log = f"{formatted_log}\n{formatted_exception}"

        return formatted_log

    def format_exception(self, exc_info) -> str:
        """
        Format exception info with colorful traceback and variable values.

        Example output:
        ```
        list indices must be integers or slices, not str
        TypeError: list indices must be integers or slices, not str
        Traceback (most recent call last):
        File "path/to/file1.py", line 328, in <func_name_which_is_called_first>
            <line which calls <func_called_second>>
            Local variables:
                var_1 = val_1
                var_2 = val_2
                /// /// ///
                /// /// ///
                ... and x more
        File "path/to/file2.py", line 669, in <func_called_second>
            <line which caused the error>
            Local variables:
                var_1 = val_1
                /// /// ///
                ... and x more
        File ///////////////////////////////////////
            /////////////////////
            Local variables:
                /// /// ///

        and so on...
        ```
        """
        exc_type, exc_value, tb = exc_info

        # Format the exception header
        exc_name = exc_type.__name__
        exc_message = str(exc_value)
        header = self.colorize(f"{exc_name}: {exc_message}", Colors.LEVEL_COLORS["ERROR"])

        # Process the traceback
        tb_frames = []
        current_tb = tb
        while current_tb:
            frame = current_tb.tb_frame
            filename = frame.f_code.co_filename
            lineno = current_tb.tb_lineno
            function = frame.f_code.co_name
            locals_dict = frame.f_locals.copy()
            tb_frames.append((filename, lineno, function, locals_dict))
            current_tb = current_tb.tb_next

        # Generate enhanced traceback with variable information
        lines = [header]
        lines.append(self.colorize("Traceback (most recent call last):", Colors.BOLD))

        for filename, lineno, function, locals_dict in tb_frames:
            frame_header = self.colorize(f'File "{filename}", line {lineno}, in {function}', Colors.YELLOW)
            lines.append(f"  {frame_header}")

            # Try to get the source line
            try:
                source_line = linecache_getline(filename, lineno).strip()
                if source_line:
                    lines.append(self.colorize(f"    {source_line}", Colors.WHITE))
            except Exception:
                pass  # Skip if we can't get the source line

            # Add local variables (similar to loguru's style)
            var_lines = []
            for name, value in locals_dict.items():
                # Skip magic and module variables to reduce noise
                if name.startswith("__") or name.startswith("_["):
                    continue
                try:
                    # Safer way to get string representation
                    if isinstance(value, (str, int, float, bool, type(None))):
                        val_str = repr(value)
                    else:
                        val_str = str(value)

                    if len(val_str) > 50:
                        val_str = val_str[:47] + "..."
                    var_lines.append(f"{name} = {val_str}")
                except Exception:
                    var_lines.append(f"{name} = <unprintable>")

            if var_lines:
                vars_header = self.colorize("    Local variables:", Colors.CYAN)
                lines.append(vars_header)
                for var_line in var_lines[:10]:  # Limit to 10 variables to avoid overwhelming output
                    lines.append(self.colorize(f"      {var_line}", Colors.CYAN + Colors.DIM))

                if len(var_lines) > 10:
                    lines.append(self.colorize(f"      ... and {len(var_lines) - 10} more", Colors.DIM))

        return "\n".join(lines)


# For accessing source lines safely
def linecache_getline(filename, lineno):
    """Get line from file, with better error handling than linecache."""
    try:
        with open(filename, "r") as f:
            lines = f.readlines()
            if 1 <= lineno <= len(lines):
                return lines[lineno - 1]
    except (IOError, IndexError):
        pass
    return ""


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

    # Create formatter that handles colors based on environment
    formatter = EnhancedFormatter(datefmt="%Y-%m-%d %H:%M:%S")

    # Add formatter to handler
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    return logger
