"""
Main CLI entry point for the GeoIP Custom IP Blocker application.

This module provides the main application workflow including configuration loading,
logging setup, and error handling framework.
"""

import sys
import csv
import logging
from pathlib import Path
from typing import Optional, List

from ..lib.exceptions import ConfigError, GeoIPError, NetworkError, ValidationError, StateError
from ..lib.logging_config import setup_logging, get_logger, log_operation_start, log_operation_success, log_operation_error
from ..models.config import Config
from ..models.geolocation import NetworkRange
from ..services.geodb_client import RadwareGeoDBClient
from ..services.csv_processor import CSVProcessor
from ..services.defensepro_client import DefenseProClient
from ..services.network_class_manager import NetworkClassManager
from ..services.blocklist_manager import BlocklistManager
from ..services.network_summarizer import NetworkSummarizer
from ..services.cleanup_manager import CleanupManager


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


def push_to_defensepro(config: Config, logger: logging.Logger, network_ranges: List[NetworkRange]) -> None:
    """
    Push network ranges to multiple DefensePro devices via CyberController.
    
    Workflow:
    1. Cleanup: Delete existing user_defined_feed_* blocklists and network classes
    2. Summarization: Aggregate networks into optimal supernets
    3. Create: Push summarized networks to all DefensePro devices
    
    Args:
        config: Application configuration
        logger: Logger instance
        network_ranges: List of NetworkRange objects to push
        
    Raises:
        GeoIPError: When DefensePro operations fail critically
    """
    log_operation_start(
        logger,
        "DefensePro network class and blocklist creation",
        cc_ip=config.cc_ip,
        dp_count=len(config.dp_ips),
        dp_ips=config.dp_ips,
        total_networks=len(network_ranges)
    )
    
    defensepro_client = None
    
    try:
        # Initialize DefensePro client (connects to CyberController)
        logger.info(f"Connecting to CyberController at {config.cc_ip}...")
        defensepro_client = DefenseProClient(
            cc_ip=config.cc_ip,
            username=config.cc_username,
            password=config.cc_password,
            verify_ssl=config.verify_ssl,
            timeout=config.api_timeout,
            max_retries=config.max_retries,
            retry_backoff=config.retry_backoff_factor,
            logger=logger
        )
        
        # STEP 0: Cleanup existing configurations
        logger.info("=" * 70)
        logger.info("STEP 0: CLEANUP EXISTING CONFIGURATIONS")
        logger.info("=" * 70)
        logger.info("Cleaning up existing user_defined_feed_* blocklists and network classes...")
        
        cleanup_manager = CleanupManager(logger=logger)
        cleanup_results = cleanup_manager.cleanup_multiple_devices(
            client=defensepro_client,
            dp_ips=config.dp_ips
        )
        
        # Identify devices with cleanup errors - skip configuration for these devices only
        devices_with_cleanup_errors = set()
        devices_cleaned_successfully = []
        
        for dp_ip, result in cleanup_results.items():
            if result.errors:
                devices_with_cleanup_errors.add(dp_ip)
                logger.warning(
                    f"✗ [{dp_ip}] Cleanup encountered {len(result.errors)} errors. "
                    f"Will skip configuration for this device."
                )
                for error in result.errors[:3]:  # Show first 3 errors
                    logger.warning(f"    - {error}")
                if len(result.errors) > 3:
                    logger.warning(f"    ... and {len(result.errors) - 3} more errors")
            else:
                devices_cleaned_successfully.append(dp_ip)
                logger.info(f"✓ [{dp_ip}] Cleanup completed successfully")
        
        if devices_with_cleanup_errors:
            logger.warning(
                f"⚠ Cleanup failed on {len(devices_with_cleanup_errors)} device(s). "
                f"These devices will be skipped during configuration: {', '.join(sorted(devices_with_cleanup_errors))}"
            )
        
        if not devices_cleaned_successfully:
            logger.error("✗ Cleanup failed on ALL devices. Cannot proceed with configuration.")
            raise SystemExit(1)
        
        logger.info(
            f"✓ Cleanup successful on {len(devices_cleaned_successfully)} device(s). "
            f"Will proceed with configuration: {', '.join(sorted(devices_cleaned_successfully))}"
        )
        
        # Export original network ranges before summarization for comparison
        try:
            original_output_file = Path("data") / "original_network_ranges.csv"
            original_output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(original_output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['network_cidr', 'note'])
                
                for network in network_ranges:
                    writer.writerow([network.network_cidr, 'original'])
            
            logger.info(f"✓ Exported {len(network_ranges)} original networks to {original_output_file}")
        except Exception as e:
            logger.warning(f"Failed to export original networks CSV: {e}")
        
        # STEP 1: Network Summarization
        logger.info("=" * 70)
        logger.info("STEP 1: NETWORK SUMMARIZATION")
        logger.info("=" * 70)
        logger.info(f"Analyzing {len(network_ranges)} networks for aggregation opportunities...")
        
        network_summarizer = NetworkSummarizer(logger=logger)
        summarization_result = network_summarizer.summarize(network_ranges, validate=True)
        
        logger.info(f"✓ {summarization_result}")
        logger.info(f"  Original networks: {summarization_result.original_count}")
        logger.info(f"  Summarized networks: {summarization_result.summarized_count}")
        logger.info(f"  Reduction: {summarization_result.reduction_percentage:.1f}%")
        
        # Convert summarized networks back to NetworkRange objects
        summarized_network_ranges = network_summarizer.summarize_to_network_ranges(
            network_ranges,
            validate=True
        )
        
        # Use summarized networks for DefensePro push
        networks_to_push = summarized_network_ranges
        logger.info(f"Will push {len(networks_to_push)} summarized networks to DefensePro devices")
        
        # Export summarized networks to CSV for audit
        try:
            output_file = Path("data") / "summarized_network_ranges.csv"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['network_cidr', 'note'])
                
                for network in networks_to_push:
                    writer.writerow([network.network_cidr, 'summarized'])
            
            logger.info(f"✓ Exported {len(networks_to_push)} summarized networks to {output_file}")
            
            # Also export comparison file showing original vs summarized
            comparison_file = Path("data") / "network_summarization_report.csv"
            with open(comparison_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['original_count', 'summarized_count', 'reduction_count', 'reduction_percentage'])
                writer.writerow([
                    summarization_result.original_count,
                    summarization_result.summarized_count,
                    summarization_result.original_count - summarization_result.summarized_count,
                    f"{summarization_result.reduction_percentage:.2f}%"
                ])
            
            logger.info(f"✓ Exported summarization report to {comparison_file}")
            
        except Exception as e:
            logger.warning(f"Failed to export CSV files: {e}")
        
        # STEP 2: Prepare network classes
        logger.info("=" * 70)
        logger.info("STEP 2: PREPARING NETWORK CLASSES")
        logger.info("=" * 70)
        network_class_manager = NetworkClassManager(logger=logger)
        
        # Split networks into classes (max 250 per class)
        network_classes = network_class_manager.split_into_classes(networks_to_push)
        logger.info(
            f"Split {len(networks_to_push)} networks into {len(network_classes)} network classes "
            f"to be pushed to {len(devices_cleaned_successfully)} DefensePro device(s)"
        )
        
        # Track overall statistics across all devices
        total_devices_successful = 0
        total_devices_failed = 0
        all_device_results = []
        
        # STEP 3: Push to DefensePro devices
        logger.info("=" * 70)
        logger.info("STEP 3: PUSHING TO DEFENSEPRO DEVICES")
        logger.info("=" * 70)
        
        # Iterate over each DefensePro device that cleaned successfully
        for device_num, dp_ip in enumerate(devices_cleaned_successfully, start=1):
            logger.info("=" * 70)
            logger.info(f"Device {device_num}/{len(devices_cleaned_successfully)}: {dp_ip}")
            logger.info("=" * 70)
            
            device_result = {
                "dp_ip": dp_ip,
                "device_num": device_num,
                "success": False,
                "class_results": {},
                "blocklist_results": {},
                "locked": False
            }
            
            try:
                # Lock device before making any configuration changes
                logger.info(f"[{dp_ip}] Locking device for configuration changes...")
                try:
                    defensepro_client.lock_device(dp_ip)
                    device_result["locked"] = True
                except Exception as e:
                    logger.error(f"[{dp_ip}] ✗ Failed to lock device: {e}")
                    total_devices_failed += 1
                    device_result["error"] = f"Failed to lock device: {str(e)}"
                    all_device_results.append(device_result)
                    continue  # Skip this device if we can't lock it
                
                # Create network classes on this DefensePro device
                logger.info(f"Creating network classes on DefensePro {dp_ip}...")
                class_results = network_class_manager.create_network_classes(
                    client=defensepro_client,
                    dp_ip=dp_ip,
                    network_classes=network_classes
                )
                device_result["class_results"] = class_results
                
                logger.info(
                    f"[{dp_ip}] Network class creation: "
                    f"{class_results['classes_successful']}/{class_results['classes_attempted']} classes successful, "
                    f"{class_results['groups_successful']}/{class_results['groups_attempted']} network groups created"
                )
                
                if class_results['errors']:
                    logger.warning(
                        f"[{dp_ip}] Encountered {len(class_results['errors'])} errors during network class creation"
                    )
                
                # Create blocklists on this DefensePro device
                logger.info(f"Creating blocklists on DefensePro {dp_ip}...")
                blocklist_manager = BlocklistManager(logger=logger)
                
                blocklist_results = blocklist_manager.create_blocklists(
                    client=defensepro_client,
                    dp_ip=dp_ip,
                    network_classes=network_classes
                )
                device_result["blocklist_results"] = blocklist_results
                
                logger.info(
                    f"[{dp_ip}] Blocklist creation: "
                    f"{blocklist_results['blocklists_successful']}/{blocklist_results['blocklists_attempted']} blocklists created"
                )
                
                if blocklist_results['errors']:
                    logger.warning(
                        f"[{dp_ip}] Encountered {len(blocklist_results['errors'])} errors during blocklist creation"
                    )
                
                # Mark device as successful if no critical errors
                device_errors = len(class_results['errors']) + len(blocklist_results['errors'])
                if device_errors == 0:
                    device_result["success"] = True
                    total_devices_successful += 1
                    logger.info(f"[{dp_ip}] ✓ Successfully configured DefensePro device")
                else:
                    total_devices_failed += 1
                    logger.warning(f"[{dp_ip}] ✗ Completed with {device_errors} errors")
                
            except Exception as e:
                total_devices_failed += 1
                device_result["error"] = str(e)
                logger.error(f"[{dp_ip}] ✗ Failed to configure DefensePro device: {e}")
            finally:
                # Always unlock device, even if errors occurred
                if device_result["locked"]:
                    logger.info(f"[{dp_ip}] Unlocking device...")
                    try:
                        defensepro_client.unlock_device(dp_ip)
                    except Exception as e:
                        logger.error(f"[{dp_ip}] ✗ Failed to unlock device: {e}")
            
            all_device_results.append(device_result)
        
        # Overall summary
        logger.info("=" * 70)
        logger.info("OVERALL SUMMARY")
        logger.info("=" * 70)
        
        # Summarization statistics
        logger.info("Network Summarization:")
        logger.info(f"  Original networks: {summarization_result.original_count}")
        logger.info(f"  Summarized networks: {summarization_result.summarized_count}")
        logger.info(f"  Reduction: {summarization_result.reduction_percentage:.1f}%")
        
        # Cleanup statistics
        total_cleanup_blocklists = sum(r.blocklists_deleted for r in cleanup_results.values())
        total_cleanup_groups = sum(r.network_groups_deleted for r in cleanup_results.values())
        logger.info("Pre-cleanup:")
        logger.info(f"  Blocklists deleted: {total_cleanup_blocklists}")
        logger.info(f"  Network groups deleted: {total_cleanup_groups}")
        
        # Device configuration statistics
        logger.info("DefensePro Configuration:")
        logger.info(
            f"  Devices: {total_devices_successful}/{len(config.dp_ips)} successful, "
            f"{total_devices_failed} failed"
        )
        
        # Calculate total statistics across all devices
        total_classes = sum(r['class_results'].get('classes_successful', 0) for r in all_device_results)
        total_groups = sum(r['class_results'].get('groups_successful', 0) for r in all_device_results)
        total_blocklists = sum(r['blocklist_results'].get('blocklists_successful', 0) for r in all_device_results)
        
        logger.info(f"  Network classes created: {total_classes}")
        logger.info(f"  Network groups created: {total_groups}")
        logger.info(f"  Blocklists created: {total_blocklists}")
        
        # Calculate total devices attempted (cleaned successfully + skipped due to cleanup errors)
        total_devices_attempted = len(devices_cleaned_successfully) + len(devices_with_cleanup_errors)
        
        if devices_with_cleanup_errors:
            logger.warning(
                f"  Devices skipped due to cleanup errors: {len(devices_with_cleanup_errors)} "
                f"({', '.join(sorted(devices_with_cleanup_errors))})"
            )
        
        if total_devices_successful == len(devices_cleaned_successfully):
            log_operation_success(
                logger,
                "DefensePro integration",
                original_networks=summarization_result.original_count,
                summarized_networks=summarization_result.summarized_count,
                reduction_percentage=summarization_result.reduction_percentage,
                devices_configured=total_devices_successful,
                network_classes_created=total_classes,
                network_groups_created=total_groups,
                blocklists_created=total_blocklists,
                cleanup_blocklists_deleted=total_cleanup_blocklists,
                cleanup_groups_deleted=total_cleanup_groups
            )
        elif total_devices_successful > 0:
            logger.warning(
                f"DefensePro integration partially successful: "
                f"{total_devices_successful}/{total_devices_attempted} devices configured "
                f"({len(devices_with_cleanup_errors)} skipped due to cleanup errors)"
            )
        else:
            raise GeoIPError(
                f"Failed to configure any DefensePro devices "
                f"({total_devices_attempted} attempted, {len(devices_with_cleanup_errors)} skipped due to cleanup errors)"
            )
        
    except (NetworkError, ValidationError) as e:
        log_operation_error(logger, "DefensePro integration", e)
        raise GeoIPError(f"Failed to push network ranges to DefensePro: {str(e)}") from e
        
    finally:
        if defensepro_client:
            defensepro_client.close()


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
        
        # User Story 2 & 3: Push network ranges to DefensePro
        push_to_defensepro(config, logger, network_ranges)
        
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