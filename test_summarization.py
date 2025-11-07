#!/usr/bin/env python3
"""
Test script for network summarization functionality.

This script tests the network summarization module with actual GeoIP data
extracted from the Radware MaxMind feed.
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.lib.logging_config import setup_logging
from src.models.config import Config
from src.models.geolocation import NetworkRange
from src.services.geodb_client import RadwareGeoDBClient
from src.services.csv_processor import CSVProcessor
from src.services.network_summarizer import NetworkSummarizer


def main():
    """Test network summarization with real GeoIP data."""
    
    # Load environment variables from .env file
    from pathlib import Path
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        import os
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    
    # Setup basic logging
    logger = setup_logging(log_level="INFO", syslog_enabled=False)
    logger.info("=" * 70)
    logger.info("NETWORK SUMMARIZATION TEST")
    logger.info("=" * 70)
    
    try:
        config = Config.from_environment()
        
        # Step 1: Extract networks from GeoIP
        logger.info("Step 1: Extracting networks from GeoIP database...")
        
        geodb_client = RadwareGeoDBClient(
            api_url=config.radware_api_url,
            cache_dir=config.geodb_cache_dir,
            download_timeout=config.download_timeout,
            max_retries=config.max_retries,
            retry_backoff=config.retry_backoff_factor
        )
        
        file_paths, db_md5 = geodb_client.get_or_download_database()
        
        csv_processor = CSVProcessor(
            target_country=config.target_country,
            target_regions=config.target_regions
        )
        
        network_ranges = csv_processor.process_geodb_files(file_paths)
        
        logger.info(f"✓ Extracted {len(network_ranges)} networks from GeoIP database")
        logger.info(f"  Database MD5: {db_md5}")
        
        # Sample of networks
        logger.info("\nSample of extracted networks (first 10):")
        for i, nr in enumerate(network_ranges[:10], 1):
            logger.info(f"  {i}. {nr.network_cidr}")
        
        # Step 2: Test summarization
        logger.info("\n" + "=" * 70)
        logger.info("Step 2: Testing network summarization...")
        logger.info("=" * 70)
        
        summarizer = NetworkSummarizer(logger=logger)
        result = summarizer.summarize(network_ranges, validate=True)
        
        logger.info("\nSUMMARIZATION RESULTS:")
        logger.info(f"  Original networks: {result.original_count}")
        logger.info(f"  Summarized networks: {result.summarized_count}")
        logger.info(f"  Networks reduced: {result.original_count - result.summarized_count}")
        logger.info(f"  Reduction percentage: {result.reduction_percentage:.2f}%")
        
        if result.summarized_count < result.original_count:
            logger.info("\n✓ Summarization achieved reduction!")
            logger.info("\nSample of summarized networks (first 10):")
            for i, network in enumerate(result.summarized_networks[:10], 1):
                logger.info(f"  {i}. {network}")
        else:
            logger.info("\n⚠ No reduction possible - networks already optimal")
        
        # Step 3: Export results with clear mapping
        logger.info("\n" + "=" * 70)
        logger.info("Step 3: Exporting results to CSV with mapping...")
        logger.info("=" * 70)
        
        import csv
        import ipaddress
        
        # Export original networks
        output_dir = Path("data")
        output_dir.mkdir(exist_ok=True)
        
        original_file = output_dir / "test_original_networks.csv"
        with open(original_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['network_cidr', 'type'])
            for network in result.original_networks:
                writer.writerow([network, 'original'])
        
        logger.info(f"✓ Exported {len(result.original_networks)} original networks to {original_file}")
        
        # Export summarized networks
        summarized_file = output_dir / "test_summarized_networks.csv"
        with open(summarized_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['network_cidr', 'type'])
            for network in result.summarized_networks:
                writer.writerow([network, 'summarized'])
        
        logger.info(f"✓ Exported {len(result.summarized_networks)} summarized networks to {summarized_file}")
        
        # NEW: Export detailed mapping showing which original networks were merged
        mapping_file = output_dir / "test_network_mapping.csv"
        with open(mapping_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'original_network', 
                'summarized_to', 
                'action', 
                'original_ip_count',
                'summarized_ip_count',
                'notes'
            ])
            
            # Convert to ipaddress objects for comparison
            original_nets = [ipaddress.IPv4Network(n) for n in result.original_networks]
            summarized_nets = [ipaddress.IPv4Network(n) for n in result.summarized_networks]
            
            # Track which original networks were processed
            for orig_net in original_nets:
                # Check if this network still exists as-is in summarized
                if orig_net in summarized_nets:
                    writer.writerow([
                        str(orig_net),
                        str(orig_net),
                        'KEPT',
                        orig_net.num_addresses,
                        orig_net.num_addresses,
                        'No aggregation possible or network is optimal'
                    ])
                else:
                    # Find which summarized network contains this original network
                    found_parent = False
                    for summ_net in summarized_nets:
                        if orig_net.subnet_of(summ_net) and orig_net != summ_net:
                            writer.writerow([
                                str(orig_net),
                                str(summ_net),
                                'MERGED',
                                orig_net.num_addresses,
                                summ_net.num_addresses,
                                f'Aggregated into larger supernet'
                            ])
                            found_parent = True
                            break
                    
                    if not found_parent:
                        # This shouldn't happen if validation passed
                        writer.writerow([
                            str(orig_net),
                            'NOT FOUND',
                            'ERROR',
                            orig_net.num_addresses,
                            0,
                            'Network not found in summarized list (validation error?)'
                        ])
        
        logger.info(f"✓ Exported detailed network mapping to {mapping_file}")
        
        # NEW: Export aggregation groups showing which networks were merged together
        groups_file = output_dir / "test_aggregation_groups.csv"
        with open(groups_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'summarized_network',
                'action',
                'original_networks_included',
                'original_count',
                'total_ip_count'
            ])
            
            original_nets = [ipaddress.IPv4Network(n) for n in result.original_networks]
            summarized_nets = [ipaddress.IPv4Network(n) for n in result.summarized_networks]
            
            for summ_net in summarized_nets:
                # Find all original networks that are subnets of this summarized network
                included_originals = []
                for orig_net in original_nets:
                    if orig_net.subnet_of(summ_net):
                        included_originals.append(str(orig_net))
                
                if len(included_originals) == 1 and included_originals[0] == str(summ_net):
                    # This summarized network is the same as original (no merge)
                    writer.writerow([
                        str(summ_net),
                        'KEPT',
                        included_originals[0],
                        1,
                        summ_net.num_addresses
                    ])
                else:
                    # This summarized network contains multiple originals (merged)
                    writer.writerow([
                        str(summ_net),
                        'AGGREGATED',
                        '; '.join(included_originals),
                        len(included_originals),
                        summ_net.num_addresses
                    ])
        
        logger.info(f"✓ Exported aggregation groups to {groups_file}")
        
        # Export summary report
        report_file = output_dir / "test_summarization_report.txt"
        with open(report_file, 'w') as f:
            f.write("Network Summarization Test Report\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"Original networks: {result.original_count}\n")
            f.write(f"Summarized networks: {result.summarized_count}\n")
            f.write(f"Networks reduced: {result.original_count - result.summarized_count}\n")
            f.write(f"Reduction percentage: {result.reduction_percentage:.2f}%\n\n")
            f.write("Status: ")
            if result.summarized_count < result.original_count:
                f.write("SUCCESS - Summarization achieved reduction\n")
            else:
                f.write("NO REDUCTION - Networks already optimal\n")
        
        logger.info(f"✓ Exported summary report to {report_file}")
        
        # Cleanup
        geodb_client.cleanup_old_cache()
        geodb_client.close()
        
        logger.info("\n" + "=" * 70)
        logger.info("TEST COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        
        return 0
        
    except Exception as e:
        logger.error(f"\n✗ Test failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
