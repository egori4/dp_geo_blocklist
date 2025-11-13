"""
Radware GeoIP database client for downloading and processing GeoIP data.

This module handles the two-step Radware API workflow:
1. GET /api/geodb/getfile to get download URL and MD5
2. Download the actual ZIP file from the returned fileUrl
3. Extract nested GeoLite2-City-CSV.zip and process CSV files
"""

import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import requests
import re

from ..lib.exceptions import NetworkError, ValidationError, StateError
from ..lib.logging_config import get_logger
from ..lib.validators import validate_url, validate_md5_hash, calculate_file_md5


class RadwareGeoDBClient:
    """
    Client for downloading and managing Radware GeoIP database files.
    
    Implements the two-step Radware API workflow:
    1. GET /api/geodb/getfile to get download URL and MD5
    2. Download RadwareLocationBasedCities.zip from returned fileUrl
    3. Extract nested GeoLite2-City-CSV.zip and process CSV files
    """
    
    def __init__(
        self,
        api_url: str,
        cache_dir: str,
        api_timeout: int = 30,
        download_timeout: int = 300,
        max_retries: int = 3,
        retry_backoff: float = 2.0
    ) -> None:
        """
        Initialize the GeoIP database client.
        
        Args:
            api_url: Radware API URL (e.g., https://services.radware.com/api/geodb/getfile)
            cache_dir: Directory for caching downloaded files
            api_timeout: Timeout for API metadata requests in seconds
            download_timeout: Timeout for ZIP file downloads in seconds
            max_retries: Maximum number of retry attempts
            retry_backoff: Backoff multiplier for retries
        """
        self.api_url = validate_url(api_url)
        self.cache_dir = Path(cache_dir)
        self.api_timeout = api_timeout
        self.download_timeout = download_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.logger = get_logger("geodb_client")
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Session for connection reuse
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "GeoIP-Custom-Block/1.0.0",
            "Accept": "application/json"
        })
    
    def get_database_info(self) -> Dict[str, Any]:
        """
        Step 1: Get GeoIP database download information from Radware API.
        
        Makes GET request to /api/geodb/getfile to retrieve:
        - fileUrl: Direct download URL for RadwareLocationBasedCities.zip
        - md5: MD5 hash for verification
        - compressedSizeBytes: File size information
        
        Returns:
            Dictionary containing database metadata from API response
            
        Raises:
            NetworkError: When API request fails
            ValidationError: When API response format is invalid
        """
        try:
            self.logger.info("Fetching GeoIP database download information from Radware API")
            
            response = self.session.get(
                self.api_url,
                timeout=self.api_timeout
            )
            self.logger.debug(f"Sending GET request to {self.api_url}")
            self.logger.debug(f"API response status: {response.status_code}")
            
            if response.status_code != 200:
                raise NetworkError(
                    f"Failed to get database info from Radware API",
                    status_code=response.status_code,
                    url=self.api_url
                )
            
            api_response = response.json()
            
            # Validate API response structure
            if "status" not in api_response or api_response["status"] != "Success":
                raise ValidationError(
                    f"API returned non-success status",
                    "api_response", 
                    str(api_response)
                )
            
            if "data" not in api_response:
                raise ValidationError(
                    f"Missing 'data' field in API response",
                    "api_response", 
                    str(api_response)
                )
            
            data = api_response["data"]
            
            # Validate required fields in data section
            required_fields = ["fileUrl", "md5", "compressedSizeBytes"]
            for field in required_fields:
                if field not in data:
                    raise ValidationError(
                        f"Missing required field in API data: {field}", 
                        "api_response", 
                        str(api_response)
                    )
            
            # Validate MD5 format
            validate_md5_hash(data["md5"])
            
            self.logger.info(f"Database info retrieved - MD5: {data['md5']}, Size: {data['compressedSizeBytes']} bytes")
            self.logger.info(f"Download URL: {data['fileUrl']}")
            return data
            
        except requests.RequestException as e:
            raise NetworkError(f"Network error getting database info: {str(e)}", url=self.api_url)
        except ValidationError:
            raise
        except Exception as e:
            raise NetworkError(f"Unexpected error getting database info: {str(e)}", url=self.api_url)
    
    def download_database(self, file_url: str, expected_md5: str) -> Tuple[str, str]:
        """
        Step 2: Download the RadwareLocationBasedCities.zip file from the provided URL.
        
        Args:
            file_url: Direct download URL from Radware API response
            expected_md5: Expected MD5 hash from API response for verification
            
        Returns:
            Tuple of (file_path, actual_md5)
            
        Raises:
            NetworkError: When download fails
            ValidationError: When MD5 verification fails
        """
        self.logger.info(f"Starting RadwareLocationBasedCities.zip download from: {file_url}")
        
        # Create temporary file for download
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Download with retries
            for attempt in range(1, self.max_retries + 1):
                try:
                    self.logger.info(f"Download attempt {attempt}/{self.max_retries}")
                    
                    response = self.session.get(
                        file_url,
                        timeout=self.download_timeout,
                        stream=True
                    )
                    
                    if response.status_code != 200:
                        raise NetworkError(
                            f"Download failed with status {response.status_code}",
                            status_code=response.status_code,
                            url=file_url
                        )
                    
                    # Download with progress tracking
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    with open(temp_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                    
                    self.logger.info(f"Download completed - {downloaded} bytes received")
                    
                    # Calculate and verify MD5 of downloaded file
                    actual_md5 = calculate_file_md5(temp_path)
                    self.logger.info(f"Downloaded file MD5: {actual_md5}")
                    self.logger.info(f"Expected MD5 from API: {expected_md5}")
                    
                    if actual_md5.lower() != expected_md5.lower():
                        raise ValidationError(
                            f"MD5 verification failed - downloaded file corrupted or tampered",
                            field="file_md5",
                            expected_type=f"expected: {expected_md5}, got: {actual_md5}"
                        )
                    
                    self.logger.info("✓ MD5 verification passed - file integrity confirmed")
                    return temp_path, actual_md5
                    
                except (requests.RequestException, OSError) as e:
                    self.logger.warning(f"Download attempt {attempt} failed: {str(e)}")
                    
                    if attempt < self.max_retries:
                        import time
                        delay = self.retry_backoff ** attempt
                        self.logger.info(f"Retrying in {delay} seconds...")
                        time.sleep(delay)
                    else:
                        raise NetworkError(f"Download failed after {self.max_retries} attempts: {str(e)}", url=file_url)
            
        except Exception as e:
            # Clean up temporary file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
    
    def extract_zip_file(self, zip_path: str, extract_to: Optional[str] = None) -> Dict[str, str]:
        """
        Step 3: Extract CSV files from RadwareLocationBasedCities.zip.
        
        Handles the nested structure:
        1. Extract RadwareLocationBasedCities.zip
        2. Find and extract GeoLite2-City-CSV.zip inside it
        3. Extract CSV files from the nested archive
        
        Args:
            zip_path: Path to RadwareLocationBasedCities.zip file
            extract_to: Directory to extract to (default: cache_dir/extracted)
            
        Returns:
            Dictionary mapping file types to extracted CSV file paths
            
        Raises:
            StateError: When ZIP extraction fails
            ValidationError: When expected files are missing
        """
        if extract_to is None:
            extract_to = self.cache_dir / "extracted"
        
        extract_path = Path(extract_to)
        extract_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Extracting RadwareLocationBasedCities.zip: {zip_path}")
        
        try:
            # Step 1: Extract the outer RadwareLocationBasedCities.zip
            with zipfile.ZipFile(zip_path, 'r') as outer_zip:
                file_list = outer_zip.namelist()
                self.logger.info(f"RadwareLocationBasedCities.zip contains: {file_list}")
                
                # Look for GeoLite2-City-CSV.zip
                csv_zip_name = None
                for filename in file_list:
                    if filename == "GeoLite2-City-CSV.zip":
                        csv_zip_name = filename
                        break
                
                if not csv_zip_name:
                    raise ValidationError(
                        "GeoLite2-City-CSV.zip not found in RadwareLocationBasedCities.zip",
                        "archive_structure",
                        str(file_list)
                    )
                
                # Extract GeoLite2-City-CSV.zip to temporary location
                csv_zip_path = extract_path / csv_zip_name
                with open(csv_zip_path, 'wb') as f:
                    f.write(outer_zip.read(csv_zip_name))
                
                self.logger.info(f"Extracted nested archive: {csv_zip_path}")
            
            # Step 2: Extract the nested GeoLite2-City-CSV.zip
            extracted_files = {}
            
            with zipfile.ZipFile(csv_zip_path, 'r') as csv_zip:
                csv_file_list = csv_zip.namelist()
                self.logger.info(f"GeoLite2-City-CSV.zip contains {len(csv_file_list)} files")
                
                # Find the directory with dynamic date (e.g., GeoLite2-City-CSV_20251010)
                csv_dir = None
                for filename in csv_file_list:
                    if re.match(r'GeoLite2-City-CSV_\d{8}/', filename):
                        csv_dir = filename.split('/')[0]
                        break
                
                if not csv_dir:
                    raise ValidationError(
                        "Could not find GeoLite2-City-CSV_YYYYMMDD directory in nested archive",
                        "archive_structure",
                        str(csv_file_list)
                    )
                
                self.logger.info(f"Found CSV directory: {csv_dir}")
                
                # Extract required CSV files
                required_files = {
                    'locations': f'{csv_dir}/GeoLite2-City-Locations-en.csv',
                    'blocks_ipv4': f'{csv_dir}/GeoLite2-City-Blocks-IPv4.csv'
                }
                
                for file_type, csv_filename in required_files.items():
                    if csv_filename in csv_file_list:
                        # Extract to final location
                        output_path = extract_path / f"{file_type}.csv"
                        with open(output_path, 'wb') as f:
                            f.write(csv_zip.read(csv_filename))
                        
                        extracted_files[file_type] = str(output_path)
                        self.logger.info(f"Extracted {file_type}: {output_path}")
                    else:
                        raise ValidationError(
                            f"Required CSV file not found: {csv_filename}",
                            "missing_file",
                            csv_filename
                        )
            
            # Clean up temporary nested zip
            csv_zip_path.unlink()
            
            self.logger.info(f"Successfully extracted {len(extracted_files)} CSV files")
            return extracted_files
            
        except zipfile.BadZipFile:
            raise StateError(f"Invalid ZIP file format", zip_path, "extract")
        except (OSError, IOError) as e:
            raise StateError(f"File extraction error: {str(e)}", zip_path, "extract")
    
    def get_cached_database(self, md5_hash: str) -> Optional[dict]:
        """
        Check if a database with the given MD5 is already cached.
        
        Args:
            md5_hash: MD5 hash to look for
            
        Returns:
            Dictionary with extracted file paths if cached, None otherwise
        """
        cache_key = f"geodb_{md5_hash}"
        cached_dir = self.cache_dir / cache_key
        
        if not cached_dir.exists():
            return None
        
        # Check if all required files exist
        expected_files = {
            'locations': cached_dir / "locations.csv",
            'blocks_ipv4': cached_dir / "blocks_ipv4.csv"
        }
        
        for file_type, file_path in expected_files.items():
            if not file_path.exists():
                self.logger.warning(f"Cached file missing: {file_path}")
                return None
        
        self.logger.info(f"Found cached database for MD5: {md5_hash}")
        return {k: str(v) for k, v in expected_files.items()}
    
    def cache_database(self, md5_hash: str, extracted_files: dict) -> dict:
        """
        Cache the extracted database files for future use.
        
        Args:
            md5_hash: MD5 hash for cache key
            extracted_files: Dictionary of extracted file paths
            
        Returns:
            Dictionary with cached file paths
            
        Raises:
            StateError: When caching fails
        """
        cache_key = f"geodb_{md5_hash}"
        cached_dir = self.cache_dir / cache_key
        cached_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            cached_files = {}
            
            for file_type, source_path in extracted_files.items():
                target_path = cached_dir / f"{file_type}.csv"
                
                # Copy file to cache
                # shutil.copyfile is efficient (chunked reads) and doesn't preserve metadata (avoids permission issues)
                import shutil
                shutil.copyfile(source_path, target_path)
                cached_files[file_type] = str(target_path)
                
                self.logger.info(f"Cached {file_type} file: {target_path}")
            
            return cached_files
            
        except (OSError, IOError) as e:
            raise StateError(f"Failed to cache database files: {str(e)}", str(cached_dir), "cache")
    
    def get_or_download_database(self, force_download: bool = False) -> Tuple[Dict[str, str], str, bool]:
        """
        Get GeoIP database files using the complete Radware API workflow.
        
        Implementation of the two-step process:
        1. GET /api/geodb/getfile to get download URL and MD5
        2. Check if cached version matches MD5 (skip download if match)
        3. Download RadwareLocationBasedCities.zip from fileUrl (if needed)
        4. Extract nested GeoLite2-City-CSV.zip and CSV files
        
        Args:
            force_download: If True, bypass cache and force fresh download (default: False)
                           Can be set via FORCE_DOWNLOAD environment variable for testing
        
        Returns:
            Tuple of (file_paths_dict, md5_hash, is_cached)
            - file_paths_dict: Paths to extracted CSV files
            - md5_hash: MD5 of the database
            - is_cached: True if using cached version (no download), False if freshly downloaded
            
        Raises:
            NetworkError: When download/API requests fail
            ValidationError: When data validation fails
            StateError: When file operations fail
        """
        # Check for force download override from environment
        if not force_download:
            force_download_env = os.getenv("FORCE_DOWNLOAD", "false").lower()
            force_download = force_download_env in ("true", "1", "yes")
        
        if force_download:
            self.logger.warning("⚠ FORCE_DOWNLOAD enabled - bypassing cache, downloading fresh database")
        
        # Step 1: Get database info from Radware API
        self.logger.info("Starting Radware GeoIP database workflow")
        db_info = self.get_database_info()
        current_md5 = db_info["md5"]
        file_url = db_info["fileUrl"]
        
        # Check cache first (unless force download)
        if not force_download:
            cached_files = self.get_cached_database(current_md5)
            if cached_files:
                self.logger.info(
                    f"✓ Cached database matches API MD5 ({current_md5}) - skipping download"
                )
                self.logger.info("Using cached GeoIP database - no processing needed")
                return cached_files, current_md5, True  # is_cached = True
            else:
                self.logger.info(
                    f"Cached database not found or MD5 mismatch - downloading fresh database"
                )
        
        # Download and process new database
        self.logger.info("Downloading GeoIP database from Radware...")
        
        # Step 2: Download RadwareLocationBasedCities.zip
        zip_path, actual_md5 = self.download_database(file_url, current_md5)
        
        try:
            # Step 3: Extract nested archives and CSV files
            extracted_files = self.extract_zip_file(zip_path)
            
            # Cache for future use
            cached_files = self.cache_database(actual_md5, extracted_files)
            
            self.logger.info("Radware GeoIP database workflow completed successfully")
            return cached_files, actual_md5, False  # is_cached = False
            
        finally:
            # Clean up downloaded ZIP file
            try:
                os.unlink(zip_path)
                self.logger.debug(f"Cleaned up temporary file: {zip_path}")
            except OSError:
                pass
    
    def cleanup_old_cache(self, keep_count: int = 3) -> None:
        """
        Clean up old cached database versions, keeping only the most recent.
        
        Args:
            keep_count: Number of cache versions to keep
        """
        try:
            cache_dirs = []
            for item in self.cache_dir.iterdir():
                if item.is_dir() and item.name.startswith("geodb_"):
                    cache_dirs.append(item)
            
            # Sort by modification time (newest first)
            cache_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove old cache directories
            for old_dir in cache_dirs[keep_count:]:
                import shutil
                shutil.rmtree(old_dir)
                self.logger.info(f"Removed old cache directory: {old_dir}")
                
        except (OSError, IOError) as e:
            self.logger.warning(f"Failed to cleanup old cache: {str(e)}")
    
    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()