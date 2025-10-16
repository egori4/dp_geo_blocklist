"""
Structured logging configuration for the GeoIP Custom IP Blocker application.

This module sets up logging with multiple handlers including file, console,
and syslog integration with structured formatting.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from ..lib.exceptions import ConfigError


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    syslog_enabled: bool = False,
    syslog_host: str = "localhost",
    syslog_port: int = 514,
) -> logging.Logger:
    """
    Set up structured logging with multiple handlers.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (None for no file logging)
        syslog_enabled: Whether to enable syslog integration
        syslog_host: Syslog server hostname
        syslog_port: Syslog server port
        
    Returns:
        Configured logger instance
        
    Raises:
        ConfigError: When logging configuration is invalid
    """
    # Validate log level
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ConfigError(f"Invalid log level: {log_level}", "LOG_LEVEL", "valid log level")

    # Create root logger
    logger = logging.getLogger("geo_ip_blocker")
    logger.setLevel(numeric_level)
    
    # Clear any existing handlers
    logger.handlers.clear()

    # Create formatter for structured logging
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler - always enabled
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler - optional
    if log_file:
        try:
            # Create log directory if it doesn't exist
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Rotating file handler to prevent excessive disk usage
            file_handler = logging.handlers.RotatingFileHandler(
                filename=log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setLevel(numeric_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
        except (OSError, PermissionError) as e:
            raise ConfigError(f"Failed to set up file logging: {str(e)}", "LOG_FILE", "writable file path")

    # Syslog handler - optional
    if syslog_enabled:
        try:
            syslog_handler = logging.handlers.SysLogHandler(
                address=(syslog_host, syslog_port),
                facility=logging.handlers.SysLogHandler.LOG_DAEMON
            )
            
            # Syslog formatter with program name
            syslog_formatter = logging.Formatter(
                fmt="geo-ip-blocker[%(process)d]: %(levelname)s - %(message)s"
            )
            syslog_handler.setFormatter(syslog_formatter)
            syslog_handler.setLevel(logging.WARNING)  # Only warnings and errors to syslog
            logger.addHandler(syslog_handler)
            
        except (OSError, ConnectionError) as e:
            # Don't fail if syslog is unavailable, just warn
            logger.warning(f"Failed to set up syslog logging: {str(e)}")

    # Prevent propagation to root logger
    logger.propagate = False

    # Log initial setup message
    logger.info(f"Logging initialized - Level: {log_level}, File: {log_file or 'None'}, Syslog: {syslog_enabled}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger with the specified name.
    
    Args:
        name: Logger name (will be prefixed with 'geo_ip_blocker.')
        
    Returns:
        Child logger instance
    """
    return logging.getLogger(f"geo_ip_blocker.{name}")


def log_operation_start(logger: logging.Logger, operation: str, **kwargs) -> None:
    """
    Log the start of an operation with structured data.
    
    Args:
        logger: Logger instance
        operation: Operation name
        **kwargs: Additional operation details
    """
    details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"Starting {operation}" + (f" - {details}" if details else ""))


def log_operation_success(logger: logging.Logger, operation: str, **kwargs) -> None:
    """
    Log successful completion of an operation.
    
    Args:
        logger: Logger instance
        operation: Operation name
        **kwargs: Additional operation results
    """
    details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"Completed {operation}" + (f" - {details}" if details else ""))


def log_operation_error(logger: logging.Logger, operation: str, error: Exception, **kwargs) -> None:
    """
    Log operation failure with error details.
    
    Args:
        logger: Logger instance
        operation: Operation name
        error: Exception that occurred
        **kwargs: Additional error context
    """
    details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.error(
        f"Failed {operation}: {str(error)}" + (f" - {details}" if details else ""),
        exc_info=isinstance(error, Exception)
    )