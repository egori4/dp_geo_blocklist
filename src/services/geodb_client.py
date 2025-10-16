"""
Radware GeoIP database client for downloading and processing GeoIP data.

This module handles downloading, validating, and extracting GeoIP database files
from the Radware API with MD5 verification and caching support.
"""

import hashlib
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Tuple
import requests

from ..lib.exceptions import NetworkError, ValidationError, StateError
from ..lib.logging_config import get_logger
from ..lib.validators import validate_url, validate_md5_hash, calculate_file_md5


class RadwareGeoDBClient:
    """
    Client for downloading and managing Radware GeoIP database files.
    
    Handles download, MD5 validation, ZIP extraction, and caching with
    proper error handling and logging.
    """
    
    def __init__(
        self,
        api_url: str,
        cache_dir: str,
        download_timeout: int = 300,
        max_retries: int = 3,
        retry_backoff: float = 2.0
    ) -> None:
        """
        Initialize the GeoIP database client.
        
        Args:
            api_url: Base URL for the Radware GeoIP API
            cache_dir: Directory for caching downloaded files
            download_timeout: Timeout for downloads in seconds
            max_retries: Maximum number of retry attempts
            retry_backoff: Backoff multiplier for retries
        """
        self.api_url = validate_url(api_url)
        self.cache_dir = Path(cache_dir)
        self.download_timeout = download_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.logger = get_logger("geodb_client")
        
        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Session for connection reuse
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "GeoIP-Custom-Block/1.0.0"
        })
    
    def get_database_info(self) -> dict:
        """
        Get information about the current GeoIP database.
        
        Returns:
            Dictionary containing database metadata (MD5, size, etc.)
            
        Raises:
            NetworkError: When API request fails
        """
        try:
            self.logger.info("Fetching GeoIP database information")
            
            # Build info endpoint URL
            info_url = f"{self.api_url}/info"
            
            response = self.session.get(
                info_url,
                timeout=30  # Shorter timeout for metadata requests
            )
            
            if response.status_code != 200:
                raise NetworkError(
                    f"Failed to get database info",
                    status_code=response.status_code,
                    url=info_url
                )
            
            info = response.json()
            
            # Validate required fields
            required_fields = ["md5", "size", "last_modified"]
            for field in required_fields:
                if field not in info:
                    raise ValidationError(f"Missing required field in API response: {field}", "api_response", str(info))
            
            # Validate MD5 format
            validate_md5_hash(info["md5"])
            
            self.logger.info(f"Database info retrieved - MD5: {info['md5']}, Size: {info['size']} bytes")
            return info
            
        except requests.RequestException as e:
            raise NetworkError(f"Network error getting database info: {str(e)}", url=info_url)
        except ValidationError:
            raise
        except Exception as e:
            raise NetworkError(f"Unexpected error getting database info: {str(e)}", url=info_url)
    
    def download_database(self, expected_md5: Optional[str] = None) -> Tuple[str, str]:
        """
        Download the GeoIP database ZIP file.
        
        Args:
            expected_md5: Expected MD5 hash for validation (optional)
            
        Returns:
            Tuple of (file_path, actual_md5)
            
        Raises:
            NetworkError: When download fails
            ValidationError: When MD5 validation fails
        """
        download_url = f"{self.api_url}/download"
        
        self.logger.info(f"Starting GeoIP database download from {download_url}")
        
        # Create temporary file for download
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Download with retries
            for attempt in range(1, self.max_retries + 1):
                try:
                    self.logger.info(f"Download attempt {attempt}/{self.max_retries}")
                    
                    response = self.session.get(
                        download_url,
                        timeout=self.download_timeout,
                        stream=True
                    )
                    
                    if response.status_code != 200:
                        raise NetworkError(
                            f"Download failed with status {response.status_code}",
                            status_code=response.status_code,
                            url=download_url
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
                    
                    # Calculate MD5 of downloaded file
                    actual_md5 = calculate_file_md5(temp_path)
                    self.logger.info(f"Downloaded file MD5: {actual_md5}")
                    
                    # Validate MD5 if expected value provided
                    if expected_md5:
                        if actual_md5 != expected_md5.lower():
                            raise ValidationError(
                                f"MD5 mismatch - expected: {expected_md5}, actual: {actual_md5}",
                                "md5_hash",
                                actual_md5
                            )
                        self.logger.info("MD5 validation successful")
                    
                    return temp_path, actual_md5
                    
                except (requests.RequestException, OSError) as e:
                    self.logger.warning(f"Download attempt {attempt} failed: {str(e)}")
                    
                    if attempt < self.max_retries:
                        import time
                        delay = self.retry_backoff ** attempt
                        self.logger.info(f"Retrying in {delay} seconds...")
                        time.sleep(delay)
                    else:
                        raise NetworkError(f"Download failed after {self.max_retries} attempts: {str(e)}", url=download_url)
            
        except Exception as e:
            # Clean up temporary file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
    
    def extract_zip_file(self, zip_path: str, extract_to: Optional[str] = None) -> dict:
        """
        Extract CSV files from the downloaded ZIP archive.
        
        Args:
            zip_path: Path to ZIP file
            extract_to: Directory to extract to (default: cache_dir/extracted)
            
        Returns:
            Dictionary mapping file types to extracted file paths
            
        Raises:
            StateError: When ZIP extraction fails
            ValidationError: When expected files are missing
        """
        if extract_to is None:
            extract_to = self.cache_dir / "extracted"
        
        extract_path = Path(extract_to)
        extract_path.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Extracting ZIP file {zip_path} to {extract_path}")
        
        try:
            extracted_files = {}
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # List all files in archive
                file_list = zip_ref.namelist()
                self.logger.info(f"ZIP contains {len(file_list)} files")
                
                for file_info in zip_ref.infolist():
                    filename = file_info.filename
                    
                    # Look for the CSV files we need
                    if filename.endswith('City-Locations-en.csv'):
                        extracted_path = extract_path / "locations.csv"
                        with zip_ref.open(file_info) as source, open(extracted_path, 'wb') as target:
                            target.write(source.read())
                        extracted_files['locations'] = str(extracted_path)
                        self.logger.info(f"Extracted locations file: {extracted_path}")
                    
                    elif filename.endswith('City-Blocks-IPv4.csv'):
                        extracted_path = extract_path / "blocks_ipv4.csv"
                        with zip_ref.open(file_info) as source, open(extracted_path, 'wb') as target:
                            target.write(source.read())
                        extracted_files['blocks_ipv4'] = str(extracted_path)
                        self.logger.info(f"Extracted IPv4 blocks file: {extracted_path}")
            
            # Validate that we got the files we need
            required_files = ['locations', 'blocks_ipv4']
            missing_files = [f for f in required_files if f not in extracted_files]
            
            if missing_files:
                raise ValidationError(
                    f"Missing required CSV files in archive: {', '.join(missing_files)}",
                    "zip_contents",
                    str(file_list)
                )
            
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
                import shutil
                shutil.copy2(source_path, target_path)
                cached_files[file_type] = str(target_path)
                
                self.logger.info(f"Cached {file_type} file: {target_path}")
            
            return cached_files
            
        except (OSError, IOError) as e:
            raise StateError(f"Failed to cache database files: {str(e)}", str(cached_dir), "cache")
    
    def get_or_download_database(self) -> Tuple[dict, str]:
        """
        Get GeoIP database files, using cache if available or downloading if needed.
        
        Returns:
            Tuple of (file_paths_dict, md5_hash)
            
        Raises:
            NetworkError: When download/API requests fail
            ValidationError: When data validation fails
            StateError: When file operations fail
        """
        # Get current database info
        db_info = self.get_database_info()
        current_md5 = db_info["md5"]
        
        # Check cache first
        cached_files = self.get_cached_database(current_md5)
        if cached_files:
            self.logger.info("Using cached GeoIP database")
            return cached_files, current_md5
        
        # Download and process new database
        self.logger.info("Cached database not found, downloading...")
        
        # Download with MD5 validation
        zip_path, actual_md5 = self.download_database(current_md5)
        
        try:
            # Extract CSV files
            extracted_files = self.extract_zip_file(zip_path)
            
            # Cache for future use
            cached_files = self.cache_database(actual_md5, extracted_files)
            
            self.logger.info("GeoIP database download and caching completed")
            return cached_files, actual_md5
            
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