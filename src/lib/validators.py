"""
Input validation utilities for the GeoIP Custom IP Blocker application.

This module provides validation functions for URLs, CIDR blocks, file formats,
and other external data inputs.
"""

import hashlib
import ipaddress
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from ..lib.exceptions import ValidationError


def validate_url(url: str, allowed_schemes: Optional[list] = None) -> str:
    """
    Validate and normalize a URL.
    
    Args:
        url: URL string to validate
        allowed_schemes: List of allowed schemes (default: ['http', 'https'])
        
    Returns:
        Normalized URL string
        
    Raises:
        ValidationError: When URL is invalid or uses disallowed scheme
    """
    if not url or not url.strip():
        raise ValidationError("URL cannot be empty", "url", url)
    
    url = url.strip()
    
    if allowed_schemes is None:
        allowed_schemes = ['http', 'https']
    
    try:
        parsed = urlparse(url)
        
        if not parsed.scheme:
            raise ValidationError("URL must include a scheme (http/https)", "url", url)
        
        if parsed.scheme.lower() not in allowed_schemes:
            raise ValidationError(
                f"URL scheme '{parsed.scheme}' not allowed. Must be one of: {', '.join(allowed_schemes)}",
                "url", url
            )
        
        if not parsed.netloc:
            raise ValidationError("URL must include a hostname", "url", url)
        
        # Basic hostname validation
        if not re.match(r'^[a-zA-Z0-9.-]+$', parsed.netloc.split(':')[0]):
            raise ValidationError("URL contains invalid hostname characters", "url", url)
        
        return url
        
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        raise ValidationError(f"Invalid URL format: {str(e)}", "url", url)


def validate_cidr(cidr: str) -> str:
    """
    Validate a CIDR network notation.
    
    Args:
        cidr: CIDR string to validate (e.g., "192.168.1.0/24")
        
    Returns:
        Normalized CIDR string
        
    Raises:
        ValidationError: When CIDR is invalid
    """
    if not cidr or not cidr.strip():
        raise ValidationError("CIDR cannot be empty", "cidr", cidr)
    
    cidr = cidr.strip()
    
    try:
        # Parse as IPv4 or IPv6 network
        network = ipaddress.ip_network(cidr, strict=False)
        
        # Return normalized format
        return str(network)
        
    except ValueError as e:
        raise ValidationError(f"Invalid CIDR format: {str(e)}", "cidr", cidr)


def validate_ipv4_cidr(cidr: str) -> str:
    """
    Validate a CIDR network notation specifically for IPv4.
    
    Args:
        cidr: CIDR string to validate
        
    Returns:
        Normalized IPv4 CIDR string
        
    Raises:
        ValidationError: When CIDR is invalid or not IPv4
    """
    normalized = validate_cidr(cidr)
    
    try:
        network = ipaddress.ip_network(normalized)
        if network.version != 4:
            raise ValidationError("CIDR must be IPv4", "cidr", cidr)
        
        return normalized
        
    except ipaddress.AddressValueError:
        raise ValidationError("Invalid IPv4 CIDR format", "cidr", cidr)


def validate_file_extension(file_path: str, allowed_extensions: list) -> str:
    """
    Validate file extension against allowed list.
    
    Args:
        file_path: Path to file
        allowed_extensions: List of allowed extensions (with dots, e.g., ['.csv', '.zip'])
        
    Returns:
        Normalized file path
        
    Raises:
        ValidationError: When file extension is not allowed
    """
    if not file_path or not file_path.strip():
        raise ValidationError("File path cannot be empty", "file_path", file_path)
    
    file_path = file_path.strip()
    path = Path(file_path)
    
    if not path.suffix:
        raise ValidationError("File must have an extension", "file_path", file_path)
    
    if path.suffix.lower() not in [ext.lower() for ext in allowed_extensions]:
        raise ValidationError(
            f"File extension '{path.suffix}' not allowed. Must be one of: {', '.join(allowed_extensions)}",
            "file_path", file_path
        )
    
    return file_path


def validate_md5_hash(hash_string: str) -> str:
    """
    Validate MD5 hash format.
    
    Args:
        hash_string: MD5 hash string to validate
        
    Returns:
        Normalized MD5 hash (lowercase)
        
    Raises:
        ValidationError: When hash format is invalid
    """
    if not hash_string or not hash_string.strip():
        raise ValidationError("MD5 hash cannot be empty", "md5_hash", hash_string)
    
    hash_string = hash_string.strip().lower()
    
    # MD5 hash should be exactly 32 hexadecimal characters
    if len(hash_string) != 32:
        raise ValidationError("MD5 hash must be 32 characters long", "md5_hash", hash_string)
    
    if not re.match(r'^[a-f0-9]{32}$', hash_string):
        raise ValidationError("MD5 hash must contain only hexadecimal characters", "md5_hash", hash_string)
    
    return hash_string


def calculate_file_md5(file_path: str) -> str:
    """
    Calculate MD5 hash of a file.
    
    Args:
        file_path: Path to file
        
    Returns:
        MD5 hash as hexadecimal string
        
    Raises:
        ValidationError: When file cannot be read
    """
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
        
    except (OSError, IOError) as e:
        raise ValidationError(f"Cannot read file for MD5 calculation: {str(e)}", "file_path", file_path)


def validate_country_code(country_code: str) -> str:
    """
    Validate ISO 3166-1 alpha-2 country code.
    
    Args:
        country_code: 2-character country code
        
    Returns:
        Normalized country code (uppercase)
        
    Raises:
        ValidationError: When country code format is invalid
    """
    if not country_code or not country_code.strip():
        raise ValidationError("Country code cannot be empty", "country_code", country_code)
    
    country_code = country_code.strip().upper()
    
    if len(country_code) != 2:
        raise ValidationError("Country code must be exactly 2 characters", "country_code", country_code)
    
    if not re.match(r'^[A-Z]{2}$', country_code):
        raise ValidationError("Country code must contain only letters", "country_code", country_code)
    
    return country_code


def validate_subdivision_code(subdivision_code: str) -> str:
    """
    Validate ISO 3166-2 subdivision code.
    
    Args:
        subdivision_code: Subdivision code (typically 2-3 characters)
        
    Returns:
        Normalized subdivision code
        
    Raises:
        ValidationError: When subdivision code format is invalid
    """
    if not subdivision_code or not subdivision_code.strip():
        raise ValidationError("Subdivision code cannot be empty", "subdivision_code", subdivision_code)
    
    subdivision_code = subdivision_code.strip()
    
    # Subdivision codes are typically 1-3 alphanumeric characters
    if not re.match(r'^[A-Za-z0-9]{1,3}$', subdivision_code):
        raise ValidationError(
            "Subdivision code must be 1-3 alphanumeric characters",
            "subdivision_code", subdivision_code
        )
    
    return subdivision_code


def validate_positive_integer(value: str, field_name: str) -> int:
    """
    Validate that a string represents a positive integer.
    
    Args:
        value: String value to validate
        field_name: Name of the field for error reporting
        
    Returns:
        Integer value
        
    Raises:
        ValidationError: When value is not a positive integer
    """
    if not value or not value.strip():
        raise ValidationError(f"{field_name} cannot be empty", field_name, value)
    
    try:
        int_value = int(value.strip())
        if int_value <= 0:
            raise ValidationError(f"{field_name} must be positive", field_name, value)
        return int_value
        
    except ValueError:
        raise ValidationError(f"{field_name} must be a valid integer", field_name, value)


def validate_port_number(port: str) -> int:
    """
    Validate port number (1-65535).
    
    Args:
        port: Port number as string
        
    Returns:
        Port number as integer
        
    Raises:
        ValidationError: When port is invalid
    """
    port_int = validate_positive_integer(port, "port")
    
    if port_int > 65535:
        raise ValidationError("Port number must be between 1 and 65535", "port", port)
    
    return port_int