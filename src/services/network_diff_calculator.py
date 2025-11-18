"""
Network Diff Calculator for comparing network configurations.

This module provides functionality to calculate differences between incoming
and existing network configurations for MERGE mode operations.
"""

import logging
from typing import List, Set, Tuple
from dataclasses import dataclass

from ..models.geolocation import NetworkRange


@dataclass
class NetworkDiff:
    """
    Difference between incoming and existing network configurations.
    """
    networks_to_add: List[NetworkRange]  # In incoming, not in existing
    networks_to_delete: List[Tuple[str, str, int]]  # (network_cidr, class_name, subindex) to delete
    networks_unchanged: Set[str]  # Networks present in both
    
    @property
    def has_changes(self) -> bool:
        """Check if there are any changes (additions or deletions)."""
        return len(self.networks_to_add) > 0 or len(self.networks_to_delete) > 0
    
    @property
    def total_changes(self) -> int:
        """Get total number of changes."""
        return len(self.networks_to_add) + len(self.networks_to_delete)


class NetworkDiffCalculator:
    """
    Calculator for determining differences between network configurations.
    
    Compares incoming networks (from GeoIP database) with existing networks
    (configured on DefensePro) to identify what needs to be added or deleted.
    """
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize diff calculator.
        
        Args:
            logger: Logger instance for operation logging
        """
        self.logger = logger
    
    def calculate_diff(
        self,
        incoming_networks: List[NetworkRange],
        existing_networks_map: dict  # Dict[str, Tuple[str, int]] - network_cidr -> (class_name, subindex)
    ) -> NetworkDiff:
        """
        Calculate difference between incoming and existing networks.
        
        Args:
            incoming_networks: List of networks from GeoIP database (after filtering/summarization)
            existing_networks_map: Map of existing networks on DefensePro
                                  {network_cidr: (class_name, subindex)}
        
        Returns:
            NetworkDiff: Object containing networks to add, delete, and unchanged
        """
        self.logger.info("Calculating network configuration differences...")
        
        # Convert incoming networks to set of CIDRs
        incoming_cidrs = {network.network_cidr for network in incoming_networks}
        existing_cidrs = set(existing_networks_map.keys())
        
        # Calculate set differences
        cidrs_to_add = incoming_cidrs - existing_cidrs
        cidrs_to_delete = existing_cidrs - incoming_cidrs
        cidrs_unchanged = incoming_cidrs & existing_cidrs
        
        # Build networks_to_add list (preserve NetworkRange objects)
        networks_to_add = [
            network for network in incoming_networks 
            if network.network_cidr in cidrs_to_add
        ]
        
        # Build networks_to_delete list with location information
        networks_to_delete = [
            (cidr, class_name, subindex)
            for cidr in cidrs_to_delete
            for class_name, subindex in [existing_networks_map[cidr]]
        ]
        
        # Log summary
        self.logger.info("=" * 70)
        self.logger.info("NETWORK DIFF SUMMARY")
        self.logger.info("=" * 70)
        self.logger.info(f"Existing networks:  {len(existing_cidrs)}")
        self.logger.info(f"Incoming networks:  {len(incoming_cidrs)}")
        self.logger.info(f"Networks unchanged: {len(cidrs_unchanged)}")
        self.logger.info(f"Networks to ADD:    {len(cidrs_to_add)}")
        self.logger.info(f"Networks to DELETE: {len(cidrs_to_delete)}")
        self.logger.info("=" * 70)
        
        # Log sample of changes if any
        if networks_to_add:
            sample_add = min(5, len(networks_to_add))
            self.logger.info(f"Sample networks to ADD (showing {sample_add}/{len(networks_to_add)}):")
            for i, network in enumerate(networks_to_add[:sample_add], 1):
                self.logger.info(f"  {i}. {network.network_cidr}")
        
        if networks_to_delete:
            sample_del = min(5, len(networks_to_delete))
            self.logger.info(f"Sample networks to DELETE (showing {sample_del}/{len(networks_to_delete)}):")
            for i, (cidr, class_name, subindex) in enumerate(networks_to_delete[:sample_del], 1):
                self.logger.info(f"  {i}. {cidr} (from {class_name}[{subindex}])")
        
        if not networks_to_add and not networks_to_delete:
            self.logger.info("✓ No changes detected - configuration is up-to-date")
        
        return NetworkDiff(
            networks_to_add=networks_to_add,
            networks_to_delete=networks_to_delete,
            networks_unchanged=cidrs_unchanged
        )
    
    def group_deletions_by_class(
        self,
        networks_to_delete: List[Tuple[str, str, int]]
    ) -> dict:
        """
        Group deletions by network class for efficient processing.
        
        Args:
            networks_to_delete: List of (network_cidr, class_name, subindex) tuples
            
        Returns:
            Dict mapping class_name -> List[(network_cidr, subindex)]
        """
        grouped = {}
        for cidr, class_name, subindex in networks_to_delete:
            if class_name not in grouped:
                grouped[class_name] = []
            grouped[class_name].append((cidr, subindex))
        
        # Sort subindexes within each class (ascending order for consistent processing)
        for class_name in grouped:
            grouped[class_name].sort(key=lambda x: x[1])
        
        self.logger.debug(
            f"Grouped {len(networks_to_delete)} deletions into {len(grouped)} classes"
        )
        
        return grouped
