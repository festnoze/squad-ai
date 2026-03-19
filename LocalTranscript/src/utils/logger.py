"""Logging configuration for LocalTranscript."""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logger(
    name: str = "LocalTranscript",
    level: int = logging.INFO,
    log_to_file: bool = True,
    log_file: str = "localtranscript.log"
) -> logging.Logger:
    """
    Setup application logger.

    Args:
        name: Logger name
        level: Logging level
        log_to_file: Whether to log to file
        log_file: Log file path

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    if log_to_file:
        try:
            # Create logs directory if needed
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=5 * 1024 * 1024,  # 5MB
                backupCount=3,
                encoding='utf-8'
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            logger.warning(f"Could not setup file logging: {e}")

    return logger
