"""
Geolocation data models for the GeoIP Custom IP Blocker application.

This module contains data models for representing geographic locations
and network ranges from the GeoIP database.
"""

from dataclasses import dataclass
from typing import Optional, List
import ipaddress

from ..lib.exceptions import ValidationError
from ..lib.validators import validate_ipv4_cidr, validate_country_code, validate_subdivision_code


@dataclass(frozen=True)
class GeoLocation:
    """
    Represents a geographic location from the GeoIP database.
    
    This corresponds to entries in the GeoLite2-City-Locations CSV file.
    """
    geoname_id: int
    country_iso_code: str
    subdivision_1_iso_code: Optional[str] = None
    city_name: Optional[str] = None
    locale_code: str = "en"
    continent_code: Optional[str] = None
    time_zone: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Validate data after object creation."""
        if self.geoname_id <= 0:
            raise ValidationError("geoname_id must be positive", "geoname_id", str(self.geoname_id))
        
        # Validate country code
        try:
            object.__setattr__(self, 'country_iso_code', validate_country_code(self.country_iso_code))
        except ValidationError as e:
            raise ValidationError(f"Invalid country code: {e.message}", "country_iso_code", self.country_iso_code)
        
        # Validate subdivision code if present
        if self.subdivision_1_iso_code:
            try:
                object.__setattr__(self, 'subdivision_1_iso_code', validate_subdivision_code(self.subdivision_1_iso_code))
            except ValidationError as e:
                raise ValidationError(f"Invalid subdivision code: {e.message}", "subdivision_1_iso_code", self.subdivision_1_iso_code)
    
    @classmethod
    def from_csv_row(cls, row: dict) -> "GeoLocation":
        """
        Create a GeoLocation from a CSV row dictionary.
        
        Args:
            row: Dictionary with keys matching GeoLite2-City-Locations CSV headers
            
        Returns:
            GeoLocation instance
            
        Raises:
            ValidationError: When required fields are missing or invalid
        """
        try:
            geoname_id = int(row.get("geoname_id", 0))
            if geoname_id <= 0:
                raise ValidationError("Missing or invalid geoname_id", "geoname_id", row.get("geoname_id"))
            
            country_iso_code = row.get("country_iso_code", "").strip()
            if not country_iso_code:
                raise ValidationError("Missing country_iso_code", "country_iso_code", country_iso_code)
            
            # Optional fields
            subdivision_1_iso_code = row.get("subdivision_1_iso_code", "").strip() or None
            city_name = row.get("city_name", "").strip() or None
            locale_code = row.get("locale_code", "en").strip()
            continent_code = row.get("continent_code", "").strip() or None
            time_zone = row.get("time_zone", "").strip() or None
            
            return cls(
                geoname_id=geoname_id,
                country_iso_code=country_iso_code,
                subdivision_1_iso_code=subdivision_1_iso_code,
                city_name=city_name,
                locale_code=locale_code,
                continent_code=continent_code,
                time_zone=time_zone
            )
            
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Failed to parse CSV row: {str(e)}", "csv_row", str(row))
    
    def matches_target_region(self, target_country: str, target_subdivisions: Optional[List[str]] = None) -> bool:
        """
        Check if this location matches the target geographic criteria.
        
        Args:
            target_country: Target country code (e.g., "UA")
            target_subdivisions: Optional list of target subdivision codes (e.g., ["43", "09", "14"]).
                               If None or empty, matches all subdivisions in the target country.
            
        Returns:
            True if this location matches the criteria
        """
        # Must match country
        if self.country_iso_code != target_country.upper():
            return False
        
        # If no subdivision specified, any subdivision in the country matches
        if not target_subdivisions:
            return True
        
        # If location has no subdivision, it doesn't match specific subdivision criteria
        if not self.subdivision_1_iso_code:
            return False
        
        # Check if subdivision matches any target
        return self.subdivision_1_iso_code in target_subdivisions
    
    def __str__(self) -> str:
        """Human-readable string representation."""
        parts = [f"{self.country_iso_code}"]
        if self.subdivision_1_iso_code:
            parts.append(f"-{self.subdivision_1_iso_code}")
        if self.city_name:
            parts.append(f" ({self.city_name})")
        return "".join(parts) + f" [ID: {self.geoname_id}]"


@dataclass(frozen=True)
class NetworkRange:
    """
    Represents an IPv4 network range with geographic location association.
    
    This corresponds to entries in the GeoLite2-City-Blocks-IPv4 CSV file
    correlated with location data.
    """
    network_cidr: str
    geoname_id: Optional[int] = None
    registered_country_geoname_id: Optional[int] = None
    represented_country_geoname_id: Optional[int] = None
    is_anonymous_proxy: bool = False
    is_satellite_provider: bool = False
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_radius: Optional[int] = None
    
    def __post_init__(self) -> None:
        """Validate data after object creation."""
        # Validate CIDR format
        try:
            object.__setattr__(self, 'network_cidr', validate_ipv4_cidr(self.network_cidr))
        except ValidationError as e:
            raise ValidationError(f"Invalid network CIDR: {e.message}", "network_cidr", self.network_cidr)
        
        # Validate geoname_id if provided
        if self.geoname_id is not None and self.geoname_id <= 0:
            raise ValidationError("geoname_id must be positive", "geoname_id", str(self.geoname_id))
        
        # Validate optional coordinates
        if self.latitude is not None:
            if not (-90 <= self.latitude <= 90):
                raise ValidationError("Latitude must be between -90 and 90", "latitude", str(self.latitude))
        
        if self.longitude is not None:
            if not (-180 <= self.longitude <= 180):
                raise ValidationError("Longitude must be between -180 and 180", "longitude", str(self.longitude))
        
        if self.accuracy_radius is not None and self.accuracy_radius < 0:
            raise ValidationError("Accuracy radius must be non-negative", "accuracy_radius", str(self.accuracy_radius))
    
    @classmethod
    def from_csv_row(cls, row: dict) -> "NetworkRange":
        """
        Create a NetworkRange from a CSV row dictionary.
        
        Args:
            row: Dictionary with keys matching GeoLite2-City-Blocks-IPv4 CSV headers
            
        Returns:
            NetworkRange instance
            
        Raises:
            ValidationError: When required fields are missing or invalid
        """
        try:
            network_cidr = row.get("network", "").strip()
            if not network_cidr:
                raise ValidationError("Missing network CIDR", "network", network_cidr)
            
            geoname_id = int(row.get("geoname_id", 0))
            if geoname_id <= 0:
                raise ValidationError("Missing or invalid geoname_id", "geoname_id", row.get("geoname_id"))
            
            # Optional integer fields
            registered_country_geoname_id = None
            if row.get("registered_country_geoname_id"):
                registered_country_geoname_id = int(row["registered_country_geoname_id"])
            
            represented_country_geoname_id = None
            if row.get("represented_country_geoname_id"):
                represented_country_geoname_id = int(row["represented_country_geoname_id"])
            
            # Boolean fields
            is_anonymous_proxy = row.get("is_anonymous_proxy", "0") == "1"
            is_satellite_provider = row.get("is_satellite_provider", "0") == "1"
            
            # Optional string/numeric fields
            postal_code = row.get("postal_code", "").strip() or None
            
            latitude = None
            if row.get("latitude"):
                latitude = float(row["latitude"])
            
            longitude = None
            if row.get("longitude"):
                longitude = float(row["longitude"])
            
            accuracy_radius = None
            if row.get("accuracy_radius"):
                accuracy_radius = int(row["accuracy_radius"])
            
            return cls(
                network_cidr=network_cidr,
                geoname_id=geoname_id,
                registered_country_geoname_id=registered_country_geoname_id,
                represented_country_geoname_id=represented_country_geoname_id,
                is_anonymous_proxy=is_anonymous_proxy,
                is_satellite_provider=is_satellite_provider,
                postal_code=postal_code,
                latitude=latitude,
                longitude=longitude,
                accuracy_radius=accuracy_radius
            )
            
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Failed to parse CSV row: {str(e)}", "csv_row", str(row))
    
    @property
    def network(self) -> ipaddress.IPv4Network:
        """Get the network as an ipaddress.IPv4Network object."""
        return ipaddress.IPv4Network(self.network_cidr)
    
    @property
    def ip_count(self) -> int:
        """Get the number of IP addresses in this network range."""
        return self.network.num_addresses
    
    def contains_ip(self, ip_address: str) -> bool:
        """
        Check if an IP address is contained in this network range.
        
        Args:
            ip_address: IP address string to check
            
        Returns:
            True if the IP is in this network range
            
        Raises:
            ValidationError: When IP address format is invalid
        """
        try:
            ip = ipaddress.IPv4Address(ip_address)
            return ip in self.network
        except ipaddress.AddressValueError:
            raise ValidationError("Invalid IP address format", "ip_address", ip_address)
    
    def overlaps_with(self, other_cidr: str) -> bool:
        """
        Check if this network range overlaps with another CIDR.
        
        Args:
            other_cidr: CIDR string to check overlap with
            
        Returns:
            True if the networks overlap
            
        Raises:
            ValidationError: When other_cidr format is invalid
        """
        try:
            other_network = ipaddress.IPv4Network(other_cidr)
            return self.network.overlaps(other_network)
        except ipaddress.AddressValueError:
            raise ValidationError("Invalid CIDR format", "other_cidr", other_cidr)
    
    def __str__(self) -> str:
        """Human-readable string representation."""
        coord_str = ""
        if self.latitude is not None and self.longitude is not None:
            coord_str = f" @ {self.latitude:.4f},{self.longitude:.4f}"
        
        return f"{self.network_cidr} -> Location[{self.geoname_id}]{coord_str} ({self.ip_count} IPs)"
    
    def __lt__(self, other: "NetworkRange") -> bool:
        """Support sorting by network address."""
        return self.network.network_address < other.network.network_address