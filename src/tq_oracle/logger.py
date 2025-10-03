"""Simple logging configuration for tq-oracle."""

import logging
import os
import sys


class ColoredFormatter(logging.Formatter):
    """Colored log formatter using ANSI escape codes."""

    # ANSI color codes
    COLORS = {
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


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a module.

    Args:
        name: Usually __name__ of the calling module

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
