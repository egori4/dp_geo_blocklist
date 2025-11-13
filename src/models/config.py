"""
Configuration management for the GeoIP Custom IP Blocker application.

This module handles loading and validating configuration from environment variables
with type safety and clear error reporting.
"""

import os
from dataclasses import dataclass
from typing import List, Optional

from ..lib.exceptions import ConfigError


@dataclass
class Config:
    """Configuration dataclass with environment variable loading and validation."""

    # DefensePro Configuration
    cc_ip: str  # CyberController IP address
    dp_ips: List[str]  # List of DefensePro device IP addresses (supports multiple devices)
    cc_username: str
    cc_password: str
    verify_ssl: bool

    # Radware GeoIP Source
    radware_api_url: str

    # Target Regions for IP Range Identification
    target_country: str
    target_regions: Optional[List[str]]  # Optional: If None, filter by country only

    # Logging Configuration
    log_level: str
    log_file: str
    syslog_enabled: bool
    syslog_host: str
    syslog_port: int

    # Storage Paths
    state_file: str
    history_file: str
    geodb_cache_dir: str
    cache_retention_count: int  # Number of cache versions to keep

    # DefensePro Timeout Configuration
    dp_api_timeout: int
    dp_delete_timeout: int

    # GeoIP Database Timeout Configuration
    geodb_api_timeout: int
    geodb_download_timeout: int

    # Retry Configuration
    max_retries: int
    retry_backoff_factor: float

    # Dry-Run / Step Control Configuration
    enable_geodb_download: bool
    enable_network_summarization: bool
    configure_defensepro: bool
    filter_target_regions: bool

    @classmethod
    def from_environment(cls) -> "Config":
        """
        Load configuration from environment variables with validation.
        
        Returns:
            Config: Validated configuration instance
            
        Raises:
            ConfigError: When required environment variables are missing or invalid
        """
        try:
            # Required DefensePro/CyberController configuration
            cc_ip = cls._get_required_env("CC_IP")
            dp_ips_str = cls._get_required_env("DP_IPS")
            dp_ips = [ip.strip() for ip in dp_ips_str.split(",")]
            cc_username = cls._get_required_env("CC_USERNAME")
            cc_password = cls._get_required_env("CC_PASSWORD")
            verify_ssl = cls._get_bool_env("VERIFY_SSL", False)

            # Required Radware GeoIP source
            radware_api_url = cls._get_required_env("RADWARE_API_URL")

            # Required target country, optional target regions
            target_country = cls._get_required_env("TARGET_COUNTRY")
            target_regions_str = os.getenv("TARGET_REGIONS", "").strip()
            target_regions = [region.strip() for region in target_regions_str.split(",") if region.strip()] if target_regions_str else None

            # Logging configuration with defaults
            log_level = os.getenv("LOG_LEVEL", "INFO").upper()
            log_file = os.getenv("LOG_FILE", "/app/data/ip-blocker.log")
            syslog_enabled = cls._get_bool_env("SYSLOG_ENABLED", False)
            syslog_host = os.getenv("SYSLOG_HOST", "localhost")
            syslog_port = cls._get_int_env("SYSLOG_PORT", 514)

            # Storage paths with defaults
            state_file = os.getenv("STATE_FILE", "/app/data/ip_state.json")
            history_file = os.getenv("HISTORY_FILE", "/app/data/ip_history.jsonl")
            geodb_cache_dir = os.getenv("GEODB_CACHE_DIR", "/app/data/geodb_cache")
            cache_retention_count = cls._get_int_env("CACHE_RETENTION_COUNT", 3)

            # DefensePro timeout configuration with defaults
            dp_api_timeout = cls._get_int_env("DP_API_TIMEOUT", 30)
            dp_delete_timeout = cls._get_int_env("DP_DELETE_TIMEOUT", 120)

            # GeoIP database timeout configuration with defaults
            geodb_api_timeout = cls._get_int_env("GEODB_API_TIMEOUT", 30)
            geodb_download_timeout = cls._get_int_env("GEODB_DOWNLOAD_TIMEOUT", 300)

            # Retry configuration with defaults
            max_retries = cls._get_int_env("MAX_RETRIES", 3)
            retry_backoff_factor = cls._get_float_env("RETRY_BACKOFF_FACTOR", 2.0)

            # Dry-run / step control configuration with defaults (all enabled by default)
            enable_geodb_download = cls._get_bool_env("ENABLE_GEODB_DOWNLOAD", True)
            enable_network_summarization = cls._get_bool_env("ENABLE_NETWORK_SUMMARIZATION", True)
            configure_defensepro = cls._get_bool_env("CONFIGURE_DEFENSEPRO", True)
            filter_target_regions = cls._get_bool_env("FILTER_TARGET_REGIONS", True)

            # Validate configuration values
            cls._validate_config(
                log_level=log_level,
                target_country=target_country,
                target_regions=target_regions,
                dp_ips=dp_ips,
                dp_api_timeout=dp_api_timeout,
                dp_delete_timeout=dp_delete_timeout,
                geodb_api_timeout=geodb_api_timeout,
                geodb_download_timeout=geodb_download_timeout,
                max_retries=max_retries,
                retry_backoff_factor=retry_backoff_factor,
                cache_retention_count=cache_retention_count,
            )

            return cls(
                cc_ip=cc_ip,
                dp_ips=dp_ips,
                cc_username=cc_username,
                cc_password=cc_password,
                verify_ssl=verify_ssl,
                radware_api_url=radware_api_url,
                target_country=target_country,
                target_regions=target_regions,
                log_level=log_level,
                log_file=log_file,
                syslog_enabled=syslog_enabled,
                syslog_host=syslog_host,
                syslog_port=syslog_port,
                state_file=state_file,
                history_file=history_file,
                geodb_cache_dir=geodb_cache_dir,
                cache_retention_count=cache_retention_count,
                dp_api_timeout=dp_api_timeout,
                dp_delete_timeout=dp_delete_timeout,
                geodb_api_timeout=geodb_api_timeout,
                geodb_download_timeout=geodb_download_timeout,
                max_retries=max_retries,
                retry_backoff_factor=retry_backoff_factor,
                enable_geodb_download=enable_geodb_download,
                enable_network_summarization=enable_network_summarization,
                configure_defensepro=configure_defensepro,
                filter_target_regions=filter_target_regions,
            )

        except ConfigError:
            raise
        except Exception as e:
            raise ConfigError(f"Failed to load configuration: {str(e)}")

    @staticmethod
    def _get_required_env(key: str) -> str:
        """Get required environment variable or raise ConfigError."""
        value = os.getenv(key)
        if value is None:
            raise ConfigError(f"Required environment variable '{key}' is not set", key, "string")
        if not value.strip():
            raise ConfigError(f"Environment variable '{key}' cannot be empty", key, "non-empty string")
        return value.strip()

    @staticmethod
    def _get_int_env(key: str, default: Optional[int] = None) -> int:
        """Get integer environment variable with optional default."""
        value = os.getenv(key)
        if value is None:
            if default is not None:
                return default
            raise ConfigError(f"Required environment variable '{key}' is not set", key, "integer")
        
        try:
            return int(value)
        except ValueError:
            raise ConfigError(f"Environment variable '{key}' must be a valid integer", key, "integer")

    @staticmethod
    def _get_float_env(key: str, default: Optional[float] = None) -> float:
        """Get float environment variable with optional default."""
        value = os.getenv(key)
        if value is None:
            if default is not None:
                return default
            raise ConfigError(f"Required environment variable '{key}' is not set", key, "float")
        
        try:
            return float(value)
        except ValueError:
            raise ConfigError(f"Environment variable '{key}' must be a valid float", key, "float")

    @staticmethod
    def _get_bool_env(key: str, default: bool = False) -> bool:
        """Get boolean environment variable with default."""
        value = os.getenv(key)
        if value is None:
            return default
        
        return value.lower() in ("true", "1", "yes", "on")

    @staticmethod
    def _validate_config(
        log_level: str,
        target_country: str,
        target_regions: Optional[List[str]],
        dp_ips: List[str],
        dp_api_timeout: int,
        dp_delete_timeout: int,
        geodb_api_timeout: int,
        geodb_download_timeout: int,
        max_retries: int,
        retry_backoff_factor: float,
        cache_retention_count: int,
    ) -> None:
        """Validate configuration values for correctness."""
        # Validate log level
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if log_level not in valid_log_levels:
            raise ConfigError(
                f"Invalid log level '{log_level}'. Must be one of: {', '.join(valid_log_levels)}",
                "LOG_LEVEL",
                "valid log level"
            )

        # Validate country code
        if len(target_country) != 2:
            raise ConfigError(
                f"Invalid country code '{target_country}'. Must be 2-character ISO code",
                "TARGET_COUNTRY",
                "2-character ISO code"
            )

        # Validate target regions (optional - if provided, cannot be empty)
        if target_regions is not None and len(target_regions) == 0:
            raise ConfigError(
                "TARGET_REGIONS cannot be empty string - either provide subdivision codes or omit the variable entirely",
                "TARGET_REGIONS", 
                "comma-separated region codes or omit variable"
            )
        
        # Validate DefensePro IPs
        if not dp_ips:
            raise ConfigError(
                "DP_IPS cannot be empty",
                "DP_IPS",
                "comma-separated IP addresses"
            )
        
        for dp_ip in dp_ips:
            if not dp_ip:
                raise ConfigError(
                    "DP_IPS contains empty IP address",
                    "DP_IPS",
                    "valid IP addresses"
                )

        # Validate DefensePro timeout values
        if dp_api_timeout <= 0:
            raise ConfigError(
                f"DefensePro API timeout must be positive, got {dp_api_timeout}",
                "DP_API_TIMEOUT",
                "positive integer"
            )
        
        if dp_delete_timeout <= 0:
            raise ConfigError(
                f"DefensePro delete timeout must be positive, got {dp_delete_timeout}",
                "DP_DELETE_TIMEOUT",
                "positive integer"
            )

        # Validate GeoIP database timeout values
        if geodb_api_timeout <= 0:
            raise ConfigError(
                f"GeoIP API timeout must be positive, got {geodb_api_timeout}",
                "GEODB_API_TIMEOUT",
                "positive integer"
            )
        
        if geodb_download_timeout <= 0:
            raise ConfigError(
                f"GeoIP download timeout must be positive, got {geodb_download_timeout}",
                "GEODB_DOWNLOAD_TIMEOUT",
                "positive integer"
            )

        # Validate retry configuration
        if max_retries < 0:
            raise ConfigError(
                f"Max retries must be non-negative, got {max_retries}",
                "MAX_RETRIES",
                "non-negative integer"
            )

        if retry_backoff_factor <= 0:
            raise ConfigError(
                f"Retry backoff factor must be positive, got {retry_backoff_factor}",
                "RETRY_BACKOFF_FACTOR",
                "positive float"
            )
        
        # Validate cache retention count
        if cache_retention_count < 1:
            raise ConfigError(
                f"Cache retention count must be at least 1, got {cache_retention_count}",
                "CACHE_RETENTION_COUNT",
                "positive integer (minimum 1)"
            )

    def __repr__(self) -> str:
        """Safe representation that doesn't expose sensitive information."""
        regions_str = ','.join(self.target_regions) if self.target_regions else 'ALL (country-level only)'
        return (
            f"Config(cc_ip='{self.cc_ip}', "
            f"dp_ips={self.dp_ips} ({len(self.dp_ips)} devices), "
            f"target_country='{self.target_country}', "
            f"target_regions=[{regions_str}], "
            f"log_level='{self.log_level}', "
            f"api_timeout={self.dp_api_timeout}, "
            f"geodb_download={self.enable_geodb_download}, "
            f"summarization={self.enable_network_summarization}, "
            f"configure_defensepro={self.configure_defensepro}, "
            f"filter_regions={self.filter_target_regions})"
        )