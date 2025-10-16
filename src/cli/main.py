"""
Main CLI entry point for the GeoIP Custom IP Blocker application.

This module provides the main application workflow including configuration loading,
logging setup, and error handling framework.
"""

import sys
import logging
from typing import Optional, List

from ..lib.exceptions import ConfigError, GeoIPError, NetworkError, ValidationError, StateError
from ..lib.logging_config import setup_logging, get_logger, log_operation_start, log_operation_success, log_operation_error
from ..models.config import Config
from ..models.geolocation import NetworkRange
from ..services.geodb_client import RadwareGeoDBClient
from ..services.csv_processor import CSVProcessor


def process_geodb_data(config: Config, logger: logging.Logger) -> List[NetworkRange]:
    """
    Process GeoIP database to extract network ranges for target regions.
    
    Args:
        config: Application configuration
        logger: Logger instance
        
    Returns:
        List of NetworkRange objects for target regions
        
    Raises:
        GeoIPError: When processing fails
    """
    log_operation_start(
        logger, 
        "GeoIP database processing",
        target_country=config.target_country,
        target_regions=config.target_regions,
        cache_dir=config.geodb_cache_dir
    )
    
    geodb_client = None
    
    try:
        # Initialize GeoIP database client
        geodb_client = RadwareGeoDBClient(
            api_url=config.radware_api_url,
            cache_dir=config.geodb_cache_dir,
            download_timeout=config.download_timeout,
            max_retries=config.max_retries,
            retry_backoff=config.retry_backoff_factor
        )
        
        # Get or download database files
        logger.info("Acquiring GeoIP database files...")
        file_paths, db_md5 = geodb_client.get_or_download_database()
        
        # Initialize CSV processor
        csv_processor = CSVProcessor(
            target_country=config.target_country,
            target_regions=config.target_regions
        )
        
        # Process CSV files to extract network ranges
        logger.info("Processing GeoIP data for target regions...")
        network_ranges = csv_processor.process_geodb_files(file_paths)
        
        # Get processing statistics
        stats = csv_processor.get_processing_stats()
        
        log_operation_success(
            logger,
            "GeoIP database processing",
            database_md5=db_md5,
            network_ranges_found=len(network_ranges),
            locations_processed=stats['locations_processed'],
            locations_matched=stats['locations_matched'],
            blocks_processed=stats['blocks_processed'],
            blocks_matched=stats['blocks_matched'],
            parse_errors=stats['parse_errors']
        )
        
        # Cleanup old cache files
        geodb_client.cleanup_old_cache()
        
        return network_ranges
        
    except (NetworkError, ValidationError, StateError) as e:
        log_operation_error(logger, "GeoIP database processing", e)
        raise GeoIPError(f"Failed to process GeoIP database: {str(e)}") from e
        
    finally:
        if geodb_client:
            geodb_client.close()


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
        
        # User Story 1: Process GeoIP data to extract network ranges
        network_ranges = process_geodb_data(config, logger)
        
        if not network_ranges:
            logger.warning("No network ranges found for target criteria")
            logger.info("=== GeoIP Custom IP Blocker Finished (No Results) ===")
            return 0
        
        logger.info(f"Successfully extracted {len(network_ranges)} network ranges")
        
        # Log sample of extracted ranges for verification
        sample_size = min(5, len(network_ranges))
        logger.info(f"Sample network ranges (first {sample_size}):")
        for i, network_range in enumerate(network_ranges[:sample_size]):
            logger.info(f"  {i+1}. {network_range}")
        
        # TODO: User Story 2 - Delta-based API synchronization
        # This will be implemented in the next phase:
        # - Load previous state
        # - Calculate deltas (additions/removals)
        # - Synchronize changes with custom feed API
        # - Update state and audit trail
        
        logger.info("Delta synchronization not yet implemented - User Story 1 complete")
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