"""
Custom exception classes for the GeoIP Custom IP Blocker application.

This module defines all custom exceptions used throughout the application
to provide clear error handling and debugging information.
"""

from typing import Optional


class GeoIPError(Exception):
    """Base exception for all GeoIP-related errors."""

    def __init__(self, message: str, details: Optional[str] = None) -> None:
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class NetworkError(GeoIPError):
    """Raised when network operations fail (downloads, API calls)."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        url: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(message, details)

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.status_code:
            base_msg += f" (HTTP {self.status_code})"
        if self.url:
            base_msg += f" [URL: {self.url}]"
        return base_msg


class ValidationError(GeoIPError):
    """Raised when input validation fails (URLs, CIDR, file formats)."""

    def __init__(
        self, message: str, field: Optional[str] = None, value: Optional[str] = None
    ) -> None:
        self.field = field
        self.value = value
        super().__init__(message)

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.field:
            base_msg += f" [Field: {self.field}"
            if self.value:
                base_msg += f", Value: {self.value}"
            base_msg += "]"
        return base_msg


class ConfigError(GeoIPError):
    """Raised when configuration is invalid or missing."""

    def __init__(
        self, message: str, config_key: Optional[str] = None, expected_type: Optional[str] = None
    ) -> None:
        self.config_key = config_key
        self.expected_type = expected_type
        super().__init__(message)

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.config_key:
            base_msg += f" [Config: {self.config_key}"
            if self.expected_type:
                base_msg += f", Expected: {self.expected_type}"
            base_msg += "]"
        return base_msg


class StateError(GeoIPError):
    """Raised when state management operations fail (file I/O, corruption)."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        self.file_path = file_path
        self.operation = operation
        super().__init__(message, details)

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.file_path:
            base_msg += f" [File: {self.file_path}"
            if self.operation:
                base_msg += f", Operation: {self.operation}"
            base_msg += "]"
        return base_msg
