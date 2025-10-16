"""
Main CLI entry point for the GeoIP Custom IP Blocker application.

This module provides the main application workflow including configuration loading,
logging setup, and error handling framework.
"""

import sys
import logging
from typing import Optional

from ..lib.exceptions import ConfigError, GeoIPError
from ..lib.logging_config import setup_logging, get_logger
from ..models.config import Config


def main() -> int:
    """
    Main application entry point.
    
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    logger: Optional[logging.Logger] = None
    
    try:
        # Load configuration from environment
        config = Config.from_environment()
        
        # Set up logging based on configuration
        logger = setup_logging(
            log_level=config.log_level,
            log_file=config.log_file,
            syslog_enabled=config.syslog_enabled,
            syslog_host=config.syslog_host,
            syslog_port=config.syslog_port,
        )
        
        logger.info("=== GeoIP Custom IP Blocker Starting ===")
        logger.info(f"Configuration: {config}")
        
        # TODO: Implement main application workflow
        # This will be implemented in user story phases:
        # - Phase 3 (US1): GeoIP data processing
        # - Phase 4 (US2): Delta-based API synchronization
        
        logger.info("Application workflow not yet implemented - foundational setup complete")
        logger.info("=== GeoIP Custom IP Blocker Finished Successfully ===")
        
        return 0
        
    except ConfigError as e:
        error_msg = f"Configuration error: {str(e)}"
        if logger:
            logger.error(error_msg)
        else:
            print(f"ERROR: {error_msg}", file=sys.stderr)
        return 1
        
    except GeoIPError as e:
        error_msg = f"Application error: {str(e)}"
        if logger:
            logger.error(error_msg)
        else:
            print(f"ERROR: {error_msg}", file=sys.stderr)
        return 2
        
    except KeyboardInterrupt:
        error_msg = "Application interrupted by user"
        if logger:
            logger.warning(error_msg)
        else:
            print(f"WARNING: {error_msg}", file=sys.stderr)
        return 130  # Standard exit code for Ctrl+C
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        if logger:
            logger.critical(error_msg, exc_info=True)
        else:
            print(f"CRITICAL: {error_msg}", file=sys.stderr)
        return 3


def cli_entry_point() -> None:
    """
    Entry point for command-line execution.
    
    This function calls main() and exits with the returned code.
    Separated from main() to allow for easier testing.
    """
    exit_code = main()
    sys.exit(exit_code)


if __name__ == "__main__":
    cli_entry_point()