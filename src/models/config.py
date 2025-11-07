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
    target_regions: List[str]

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

    # Timeout Configuration
    api_timeout: int
    download_timeout: int

    # Retry Configuration
    max_retries: int
    retry_backoff_factor: float

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

            # Required target regions
            target_country = cls._get_required_env("TARGET_COUNTRY")
            target_regions_str = cls._get_required_env("TARGET_REGIONS")
            target_regions = [region.strip() for region in target_regions_str.split(",")]

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

            # Timeout configuration with defaults
            api_timeout = cls._get_int_env("API_TIMEOUT", 30)
            download_timeout = cls._get_int_env("DOWNLOAD_TIMEOUT", 300)

            # Retry configuration with defaults
            max_retries = cls._get_int_env("MAX_RETRIES", 3)
            retry_backoff_factor = cls._get_float_env("RETRY_BACKOFF_FACTOR", 2.0)

            # Validate configuration values
            cls._validate_config(
                log_level=log_level,
                target_country=target_country,
                target_regions=target_regions,
                dp_ips=dp_ips,
                api_timeout=api_timeout,
                download_timeout=download_timeout,
                max_retries=max_retries,
                retry_backoff_factor=retry_backoff_factor,
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
                api_timeout=api_timeout,
                download_timeout=download_timeout,
                max_retries=max_retries,
                retry_backoff_factor=retry_backoff_factor,
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
        target_regions: List[str],
        dp_ips: List[str],
        api_timeout: int,
        download_timeout: int,
        max_retries: int,
        retry_backoff_factor: float,
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

        # Validate target regions
        if not target_regions:
            raise ConfigError(
                "TARGET_REGIONS cannot be empty",
                "TARGET_REGIONS", 
                "comma-separated region codes"
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

        # Validate timeout values
        if api_timeout <= 0:
            raise ConfigError(
                f"API timeout must be positive, got {api_timeout}",
                "API_TIMEOUT",
                "positive integer"
            )

        if download_timeout <= 0:
            raise ConfigError(
                f"Download timeout must be positive, got {download_timeout}",
                "DOWNLOAD_TIMEOUT", 
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

    def __repr__(self) -> str:
        """Safe representation that doesn't expose sensitive information."""
        return (
            f"Config(cc_ip='{self.cc_ip}', "
            f"dp_ips={self.dp_ips} ({len(self.dp_ips)} devices), "
            f"target_country='{self.target_country}', "
            f"target_regions={self.target_regions}, "
            f"log_level='{self.log_level}', "
            f"api_timeout={self.api_timeout})"
        )