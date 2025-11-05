#!/usr/bin/env python3
"""
Independent test script for User Story 1 - GeoIP Data Processing

This script tests the complete GeoIP processing pipeline without requiring
actual API calls, using mock data to verify functionality.
"""

import json
import tempfile
import csv
import zipfile
from pathlib import Path
from typing import Dict, List

from src.models.geolocation import GeoLocation, NetworkRange
from src.services.csv_processor import CSVProcessor
from src.lib.logging_config import setup_logging


def create_mock_geodb_files() -> Dict[str, str]:
    """
    Create mock GeoIP database CSV files for testing.
    
    Returns:
        Dictionary with paths to mock CSV files
    """
    print("🔧 Creating mock GeoIP database files...")
    
    # Create temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="geodb_test_"))
    
    # Mock locations data (Ukraine with target subdivisions)
    locations_data = [
        # Header
        ["geoname_id", "locale_code", "continent_code", "continent_name", 
         "country_iso_code", "country_name", "subdivision_1_iso_code", 
         "subdivision_1_name", "city_name", "metro_code", "time_zone", "is_in_european_union"],
        
        # Ukraine - target subdivisions (43=Crimea, 09=Donetsk, 14=Luhansk)
        [123001, "en", "EU", "Europe", "UA", "Ukraine", "43", "Crimea", "Sevastopol", "", "Europe/Simferopol", 0],
        [123002, "en", "EU", "Europe", "UA", "Ukraine", "43", "Crimea", "Yalta", "", "Europe/Simferopol", 0],
        [123003, "en", "EU", "Europe", "UA", "Ukraine", "09", "Donetsk", "Donetsk", "", "Europe/Kiev", 0],
        [123004, "en", "EU", "Europe", "UA", "Ukraine", "09", "Donetsk", "Mariupol", "", "Europe/Kiev", 0],
        [123005, "en", "EU", "Europe", "UA", "Ukraine", "14", "Luhansk", "Luhansk", "", "Europe/Kiev", 0],
        
        # Other Ukraine subdivisions (should be filtered out)
        [123006, "en", "EU", "Europe", "UA", "Ukraine", "30", "Kiev", "Kiev", "", "Europe/Kiev", 0],
        [123007, "en", "EU", "Europe", "UA", "Ukraine", "65", "Kherson", "Kherson", "", "Europe/Kiev", 0],
        
        # Other countries (should be filtered out)
        [124001, "en", "EU", "Europe", "RU", "Russia", "91", "Krasnodar", "Sochi", "", "Europe/Moscow", 0],
        [125001, "en", "AS", "Asia", "CN", "China", "22", "Beijing", "Beijing", "", "Asia/Shanghai", 0],
    ]
    
    # Write locations file
    locations_file = temp_dir / "locations.csv"
    with open(locations_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(locations_data)
    
    # Mock network blocks data (IPv4 ranges for our target locations)
    blocks_data = [
        # Header
        ["network", "geoname_id", "registered_country_geoname_id", "represented_country_geoname_id",
         "is_anonymous_proxy", "is_satellite_provider", "postal_code", "latitude", "longitude", "accuracy_radius"],
        
        # Target regions - these should be extracted
        ["192.168.1.0/24", 123001, 123001, "", 0, 0, "99011", 44.6167, 33.5167, 100],  # Sevastopol
        ["192.168.2.0/24", 123002, 123001, "", 0, 0, "98600", 44.4953, 34.1664, 50],   # Yalta
        ["10.0.1.0/24", 123003, 123003, "", 0, 0, "83000", 48.0159, 37.8034, 200],     # Donetsk
        ["10.0.2.0/24", 123004, 123003, "", 0, 0, "87500", 47.0971, 37.5425, 150],     # Mariupol
        ["172.16.1.0/24", 123005, 123005, "", 0, 0, "91000", 48.5738, 39.3078, 100],   # Luhansk
        
        # Other Ukraine regions - should be filtered out
        ["203.0.113.0/24", 123006, 123006, "", 0, 0, "01001", 50.4501, 30.5234, 50],   # Kiev
        ["198.51.100.0/24", 123007, 123007, "", 0, 0, "73000", 46.6056, 32.6117, 75],  # Kherson
        
        # Other countries - should be filtered out
        ["209.85.128.0/24", 124001, 124001, "", 0, 0, "354000", 43.6028, 39.7342, 100], # Sochi
        ["220.181.0.0/24", 125001, 125001, "", 0, 0, "100000", 39.9042, 116.4074, 200], # Beijing
    ]
    
    # Write blocks file
    blocks_file = temp_dir / "blocks_ipv4.csv"
    with open(blocks_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(blocks_data)
    
    print(f"✅ Mock files created in: {temp_dir}")
    print(f"   - Locations: {len(locations_data)-1} entries")
    print(f"   - Blocks: {len(blocks_data)-1} entries")
    
    return {
        'locations': str(locations_file),
        'blocks_ipv4': str(blocks_file),
        'temp_dir': str(temp_dir)
    }


def test_geolocation_models():
    """Test GeoLocation and NetworkRange model functionality."""
    print("\n🧪 Testing GeoLocation and NetworkRange models...")
    
    # Test GeoLocation creation and validation
    location = GeoLocation(
        geoname_id=123001,
        country_iso_code="UA",
        subdivision_1_iso_code="43",
        city_name="Sevastopol"
    )
    
    assert location.country_iso_code == "UA"
    assert location.subdivision_1_iso_code == "43"
    assert location.matches_target_region("UA", ["43", "09", "14"]) == True
    assert location.matches_target_region("US", ["43", "09", "14"]) == False
    print("✅ GeoLocation model tests passed")
    
    # Test NetworkRange creation and validation
    network = NetworkRange(
        network_cidr="192.168.1.0/24",
        geoname_id=123001,
        latitude=44.6167,
        longitude=33.5167
    )
    
    assert network.network_cidr == "192.168.1.0/24"
    assert network.ip_count == 256
    assert network.contains_ip("192.168.1.100") == True
    assert network.contains_ip("192.168.2.100") == False
    print("✅ NetworkRange model tests passed")


def test_csv_parsing(file_paths: Dict[str, str]):
    """Test CSV parsing with mock data."""
    print("\n🧪 Testing CSV parsing...")
    
    # Test CSV processor with target criteria
    processor = CSVProcessor(
        target_country="UA",
        target_regions=["43", "09", "14"]
    )
    
    # Test locations parsing
    locations = list(processor.parse_locations_file(file_paths['locations']))
    print(f"   Parsed {len(locations)} target locations")
    
    # Should find 5 locations (Sevastopol, Yalta, Donetsk, Mariupol, Luhansk)
    assert len(locations) == 5, f"Expected 5 locations, got {len(locations)}"
    
    # Verify location details
    location_cities = {loc.city_name for loc in locations}
    expected_cities = {"Sevastopol", "Yalta", "Donetsk", "Mariupol", "Luhansk"}
    assert location_cities == expected_cities, f"Cities mismatch: {location_cities} vs {expected_cities}"
    
    print("✅ Location parsing tests passed")
    
    # Test network blocks parsing
    target_geoname_ids = {loc.geoname_id for loc in locations}
    networks = list(processor.parse_blocks_file(file_paths['blocks_ipv4'], target_geoname_ids))
    print(f"   Parsed {len(networks)} target network ranges")
    
    # Should find 5 network ranges
    assert len(networks) == 5, f"Expected 5 networks, got {len(networks)}"
    
    # Verify network details
    network_cidrs = {net.network_cidr for net in networks}
    expected_cidrs = {"192.168.1.0/24", "192.168.2.0/24", "10.0.1.0/24", "10.0.2.0/24", "172.16.1.0/24"}
    assert network_cidrs == expected_cidrs, f"Networks mismatch: {network_cidrs} vs {expected_cidrs}"
    
    print("✅ Network parsing tests passed")
    
    return locations, networks


def test_end_to_end_processing(file_paths: Dict[str, str]):
    """Test complete end-to-end processing pipeline."""
    print("\n🧪 Testing end-to-end processing pipeline...")
    
    processor = CSVProcessor(
        target_country="UA", 
        target_regions=["43", "09", "14"]
    )
    
    # Process files to get network ranges
    network_ranges = processor.process_geodb_files({
        'locations': file_paths['locations'],
        'blocks_ipv4': file_paths['blocks_ipv4']
    })
    
    print(f"   Extracted {len(network_ranges)} network ranges")
    
    # Verify results
    assert len(network_ranges) == 5, f"Expected 5 network ranges, got {len(network_ranges)}"
    
    # Check that networks are sorted
    for i in range(1, len(network_ranges)):
        assert network_ranges[i-1] <= network_ranges[i], "Network ranges not properly sorted"
    
    # Verify total IP count
    total_ips = sum(net.ip_count for net in network_ranges)
    expected_ips = 5 * 256  # 5 /24 networks = 1280 IPs
    assert total_ips == expected_ips, f"Expected {expected_ips} total IPs, got {total_ips}"
    
    # Get processing statistics
    stats = processor.get_processing_stats()
    print(f"   Processing stats: {stats}")
    
    assert stats['locations_processed'] == 8, f"Expected 8 locations processed, got {stats['locations_processed']}"
    assert stats['locations_matched'] == 5, f"Expected 5 locations matched, got {stats['locations_matched']}"
    assert stats['blocks_processed'] == 8, f"Expected 8 blocks processed, got {stats['blocks_processed']}"
    assert stats['blocks_matched'] == 5, f"Expected 5 blocks matched, got {stats['blocks_matched']}"
    assert stats['correlation_matches'] == 5, f"Expected 5 correlations, got {stats['correlation_matches']}"
    
    print("✅ End-to-end processing tests passed")
    
    return network_ranges, stats


def display_results(network_ranges: List[NetworkRange], stats: Dict):
    """Display test results in a user-friendly format."""
    print("\n📊 **TEST RESULTS SUMMARY**")
    print("=" * 50)
    
    print(f"🎯 **Target Criteria:**")
    print(f"   Country: UA (Ukraine)")
    print(f"   Subdivisions: 43 (Crimea), 09 (Donetsk), 14 (Luhansk)")
    
    print(f"\n📈 **Processing Statistics:**")
    print(f"   Locations processed: {stats['locations_processed']:,}")
    print(f"   Locations matched: {stats['locations_matched']:,}")
    print(f"   Network blocks processed: {stats['blocks_processed']:,}")
    print(f"   Network blocks matched: {stats['blocks_matched']:,}")
    print(f"   Successful correlations: {stats['correlation_matches']:,}")
    print(f"   Parse errors: {stats['parse_errors']:,}")
    
    print(f"\n🌐 **Extracted Network Ranges:**")
    print(f"   Total ranges found: {len(network_ranges)}")
    total_ips = sum(net.ip_count for net in network_ranges)
    print(f"   Total IP addresses: {total_ips:,}")
    
    print(f"\n📋 **Network Range Details:**")
    for i, net in enumerate(network_ranges, 1):
        print(f"   {i}. {net}")
    
    print(f"\n✅ **Test Status: ALL TESTS PASSED** 🎉")
    print(f"   User Story 1 GeoIP processing is working correctly!")


def cleanup_test_files(temp_dir: str):
    """Clean up temporary test files."""
    try:
        import shutil
        shutil.rmtree(temp_dir)
        print(f"\n🧹 Cleaned up test files from: {temp_dir}")
    except Exception as e:
        print(f"\n⚠️  Warning: Failed to clean up test files: {e}")


def main():
    """Run the complete User Story 1 independent test suite."""
    print("🚀 **User Story 1 Independent Test Suite**")
    print("Testing: Automated GeoIP Data Processing")
    print("=" * 60)
    
    # Set up logging for tests
    logger = setup_logging(log_level="INFO")
    
    try:
        # Create mock data files
        file_paths = create_mock_geodb_files()
        
        # Run individual component tests
        test_geolocation_models()
        test_csv_parsing(file_paths)
        
        # Run end-to-end integration test
        network_ranges, stats = test_end_to_end_processing(file_paths)
        
        # Display comprehensive results
        display_results(network_ranges, stats)
        
        return True
        
    except Exception as e:
        print(f"\n❌ **TEST FAILED**: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Clean up test files
        if 'file_paths' in locals():
            cleanup_test_files(file_paths['temp_dir'])


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)