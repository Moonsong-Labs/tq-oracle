"""Simple logging configuration for tq-oracle."""

import logging
import os
import sys

# Define TRACE level (lower than DEBUG)
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


class ColoredFormatter(logging.Formatter):
    """Colored log formatter using ANSI escape codes."""

    # ANSI color codes
    COLORS = {
        "TRACE": "\033[90m",  # Dark gray
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = (
                f"{self.COLORS[levelname]}{self.BOLD}{levelname}{self.RESET}"
            )

        result = super().format(record)

        record.levelname = levelname

        return result


def setup_logging() -> None:
    """Configure logging for the application.

    Reads LOG_LEVEL environment variable (defaults to INFO).
    Sets up a simple console handler with formatted output and colors.

    When LOG_LEVEL is DEBUG, web3 and urllib3 loggers are set to WARNING
    to reduce noise. Use LOG_LEVEL=TRACE to see all web3/urllib3 logs.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = ColoredFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    logging.basicConfig(
        level=level,
        handlers=[handler],
        force=True,
    )

    # Configure noisy third-party loggers
    # When LOG_LEVEL is DEBUG, suppress web3/urllib3 noise
    # Use TRACE to see everything
    if log_level == "DEBUG":
        logging.getLogger("web3").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
    elif log_level == "TRACE":
        # TRACE level (5) - show everything including web3/urllib3
        logging.getLogger("web3").setLevel(TRACE)
        logging.getLogger("urllib3").setLevel(TRACE)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module.

    Args:
        name: Usually __name__ of the calling module

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
