"""
CSV processor for parsing GeoIP database files with streaming and filtering.

This module handles memory-efficient processing of large CSV files from the
GeoIP database with geographic filtering and data correlation.
"""

import csv
from typing import Iterator, List, Dict, Set, Optional, Tuple
from pathlib import Path

from ..lib.exceptions import ValidationError, StateError
from ..lib.logging_config import get_logger
from ..models.geolocation import GeoLocation, NetworkRange


class CSVProcessor:
    """
    Memory-efficient CSV processor for GeoIP database files.
    
    Handles streaming parsing of large CSV files with geographic filtering
    and correlation between locations and network blocks.
    """
    
    def __init__(self, target_country: str, target_regions: List[str]) -> None:
        """
        Initialize the CSV processor with target geographic criteria.
        
        Args:
            target_country: Target country code (e.g., "UA")
            target_regions: List of target subdivision codes (e.g., ["43", "09", "14"])
        """
        self.target_country = target_country.upper()
        self.target_regions = target_regions
        self.logger = get_logger("csv_processor")
        
        # Statistics tracking
        self.stats = {
            'locations_processed': 0,
            'locations_matched': 0,
            'blocks_processed': 0,
            'blocks_matched': 0,
            'correlation_matches': 0,
            'parse_errors': 0
        }
    
    def parse_locations_file(self, file_path: str) -> Iterator[GeoLocation]:
        """
        Parse the locations CSV file and yield matching GeoLocation objects.
        
        Args:
            file_path: Path to the locations CSV file
            
        Yields:
            GeoLocation objects that match the target criteria
            
        Raises:
            StateError: When file cannot be read
            ValidationError: When CSV format is invalid
        """
        self.logger.info(f"Starting to parse locations file: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                # Detect CSV dialect
                sample = csvfile.read(1024)
                csvfile.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=',;|')
                
                reader = csv.DictReader(csvfile, dialect=dialect)
                
                # Validate required columns exist
                required_columns = ['geoname_id', 'country_iso_code']
                missing_columns = [col for col in required_columns if col not in reader.fieldnames]
                if missing_columns:
                    raise ValidationError(
                        f"Missing required columns in locations CSV: {', '.join(missing_columns)}",
                        "csv_columns",
                        str(reader.fieldnames)
                    )
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 since row 1 is header
                    self.stats['locations_processed'] += 1
                    
                    try:
                        # Parse location from CSV row
                        location = GeoLocation.from_csv_row(row)
                        
                        # Check if location matches target criteria
                        if location.matches_target_region(self.target_country, self.target_regions):
                            self.stats['locations_matched'] += 1
                            self.logger.debug(f"Matched location: {location}")
                            yield location
                        
                    except ValidationError as e:
                        self.stats['parse_errors'] += 1
                        self.logger.warning(f"Failed to parse location row {row_num}: {e}")
                        continue
                    
                    # Log progress periodically
                    if self.stats['locations_processed'] % 10000 == 0:
                        self.logger.info(f"Processed {self.stats['locations_processed']:,} locations")
                
                self.logger.info(
                    f"Locations processing complete - "
                    f"Processed: {self.stats['locations_processed']:,}, "
                    f"Matched: {self.stats['locations_matched']:,}, "
                    f"Errors: {self.stats['parse_errors']:,}"
                )
                
        except (OSError, IOError) as e:
            raise StateError(f"Cannot read locations file: {str(e)}", file_path, "read")
        except csv.Error as e:
            raise ValidationError(f"Invalid CSV format in locations file: {str(e)}", "csv_format", file_path)
    
    def parse_blocks_file(self, file_path: str, target_geoname_ids: Set[int]) -> Iterator[NetworkRange]:
        """
        Parse the network blocks CSV file and yield matching NetworkRange objects.
        
        Args:
            file_path: Path to the blocks CSV file
            target_geoname_ids: Set of geoname_ids to filter by
            
        Yields:
            NetworkRange objects that match the target geoname_ids
            
        Raises:
            StateError: When file cannot be read
            ValidationError: When CSV format is invalid
        """
        self.logger.info(f"Starting to parse blocks file: {file_path}")
        self.logger.info(f"Filtering by {len(target_geoname_ids)} target geoname_ids")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                # Detect CSV dialect
                sample = csvfile.read(1024)
                csvfile.seek(0)
                dialect = csv.Sniffer().sniff(sample, delimiters=',;|')
                
                reader = csv.DictReader(csvfile, dialect=dialect)
                
                # Validate required columns exist
                required_columns = ['network', 'geoname_id']
                missing_columns = [col for col in required_columns if col not in reader.fieldnames]
                if missing_columns:
                    raise ValidationError(
                        f"Missing required columns in blocks CSV: {', '.join(missing_columns)}",
                        "csv_columns",
                        str(reader.fieldnames)
                    )
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 since row 1 is header
                    self.stats['blocks_processed'] += 1
                    
                    try:
                        # Quick geoname_id check before expensive parsing
                        geoname_id_str = row.get('geoname_id', '').strip()
                        if not geoname_id_str:
                            continue
                        
                        geoname_id = int(geoname_id_str)
                        if geoname_id not in target_geoname_ids:
                            continue
                        
                        # Parse network range from CSV row
                        network_range = NetworkRange.from_csv_row(row)
                        self.stats['blocks_matched'] += 1
                        self.stats['correlation_matches'] += 1
                        
                        self.logger.debug(f"Matched network: {network_range}")
                        yield network_range
                        
                    except (ValueError, ValidationError) as e:
                        self.stats['parse_errors'] += 1
                        self.logger.warning(f"Failed to parse block row {row_num}: {e}")
                        continue
                    
                    # Log progress periodically
                    if self.stats['blocks_processed'] % 50000 == 0:
                        self.logger.info(f"Processed {self.stats['blocks_processed']:,} network blocks")
                
                self.logger.info(
                    f"Blocks processing complete - "
                    f"Processed: {self.stats['blocks_processed']:,}, "
                    f"Matched: {self.stats['blocks_matched']:,}, "
                    f"Correlated: {self.stats['correlation_matches']:,}, "
                    f"Errors: {self.stats['parse_errors']:,}"
                )
                
        except (OSError, IOError) as e:
            raise StateError(f"Cannot read blocks file: {str(e)}", file_path, "read")
        except csv.Error as e:
            raise ValidationError(f"Invalid CSV format in blocks file: {str(e)}", "csv_format", file_path)
    
    def process_geodb_files(self, file_paths: Dict[str, str]) -> List[NetworkRange]:
        """
        Process both locations and blocks files to extract correlated network ranges.
        
        Args:
            file_paths: Dictionary with 'locations' and 'blocks_ipv4' file paths
            
        Returns:
            List of NetworkRange objects for target regions
            
        Raises:
            ValidationError: When required files are missing
            StateError: When file processing fails
        """
        # Validate required files
        required_files = ['locations', 'blocks_ipv4']
        missing_files = [f for f in required_files if f not in file_paths]
        if missing_files:
            raise ValidationError(
                f"Missing required file paths: {', '.join(missing_files)}",
                "file_paths",
                str(file_paths)
            )
        
        self.logger.info("Starting GeoIP database processing")
        self.logger.info(f"Target: {self.target_country} regions {self.target_regions}")
        
        # Reset statistics
        self.stats = {k: 0 for k in self.stats}
        
        # Phase 1: Process locations file to get target geoname_ids
        self.logger.info("Phase 1: Processing locations file...")
        target_locations = {}  # geoname_id -> GeoLocation
        
        for location in self.parse_locations_file(file_paths['locations']):
            target_locations[location.geoname_id] = location
        
        if not target_locations:
            self.logger.warning("No matching locations found for target criteria")
            return []
        
        target_geoname_ids = set(target_locations.keys())
        self.logger.info(f"Found {len(target_geoname_ids)} target locations")
        
        # Phase 2: Process blocks file to get correlated network ranges
        self.logger.info("Phase 2: Processing network blocks file...")
        network_ranges = []
        
        for network_range in self.parse_blocks_file(file_paths['blocks_ipv4'], target_geoname_ids):
            network_ranges.append(network_range)
        
        # Sort network ranges for consistent output
        network_ranges.sort()
        
        self.logger.info(f"Processing complete - extracted {len(network_ranges)} network ranges")
        
        return network_ranges
    
    def get_processing_stats(self) -> Dict[str, int]:
        """
        Get processing statistics.
        
        Returns:
            Dictionary with processing statistics
        """
        return self.stats.copy()
    
    def validate_csv_file(self, file_path: str, expected_columns: List[str]) -> bool:
        """
        Validate that a CSV file exists and has expected columns.
        
        Args:
            file_path: Path to CSV file
            expected_columns: List of required column names
            
        Returns:
            True if file is valid
            
        Raises:
            StateError: When file cannot be read
            ValidationError: When CSV format is invalid
        """
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                raise StateError(f"CSV file does not exist", file_path, "validate")
            
            if file_path_obj.stat().st_size == 0:
                raise ValidationError("CSV file is empty", "file_size", "0")
            
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                # Read header
                reader = csv.reader(csvfile)
                header = next(reader, None)
                
                if not header:
                    raise ValidationError("CSV file has no header row", "csv_header", "empty")
                
                # Check for required columns
                missing_columns = [col for col in expected_columns if col not in header]
                if missing_columns:
                    raise ValidationError(
                        f"Missing required columns: {', '.join(missing_columns)}",
                        "csv_columns",
                        str(header)
                    )
                
                # Check if we can read at least one data row
                data_row = next(reader, None)
                if data_row is None:
                    self.logger.warning(f"CSV file has header but no data rows: {file_path}")
                
                return True
                
        except (OSError, IOError) as e:
            raise StateError(f"Cannot read CSV file: {str(e)}", file_path, "validate")
        except csv.Error as e:
            raise ValidationError(f"Invalid CSV format: {str(e)}", "csv_format", file_path)
    
    def estimate_processing_time(self, file_paths: Dict[str, str]) -> Dict[str, float]:
        """
        Estimate processing time based on file sizes.
        
        Args:
            file_paths: Dictionary with file paths
            
        Returns:
            Dictionary with time estimates in seconds
        """
        estimates = {}
        
        try:
            # Rough estimates based on typical file sizes and processing rates
            # These are approximations for planning purposes
            
            for file_type, file_path in file_paths.items():
                file_size = Path(file_path).stat().st_size
                
                if file_type == 'locations':
                    # ~100KB/sec for locations processing
                    estimates[f'{file_type}_seconds'] = file_size / (100 * 1024)
                elif file_type == 'blocks_ipv4':
                    # ~500KB/sec for blocks processing (more complex)
                    estimates[f'{file_type}_seconds'] = file_size / (500 * 1024)
                else:
                    # Default estimate
                    estimates[f'{file_type}_seconds'] = file_size / (200 * 1024)
            
            # Total estimate
            estimates['total_seconds'] = sum(v for k, v in estimates.items() if k != 'total_seconds')
            
        except (OSError, IOError):
            # If we can't get file sizes, provide default estimates
            estimates = {
                'locations_seconds': 30.0,
                'blocks_ipv4_seconds': 120.0,
                'total_seconds': 150.0
            }
        
        return estimates