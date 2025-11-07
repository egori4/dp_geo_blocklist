"""
Network summarization module for aggregating network ranges into optimal supernets.

This module implements intelligent network aggregation to reduce the total number
of network ranges while ensuring complete coverage without including unwanted IPs.
"""

import logging
import ipaddress
from typing import List, Set, Tuple, Optional
from dataclasses import dataclass

from ..models.geolocation import NetworkRange
from ..lib.logging_config import get_logger


@dataclass
class SummarizationResult:
    """Results of network summarization operation."""
    
    original_count: int
    summarized_count: int
    reduction_percentage: float
    original_networks: List[str]
    summarized_networks: List[str]
    
    def __str__(self) -> str:
        return (
            f"Summarization: {self.original_count} → {self.summarized_count} networks "
            f"({self.reduction_percentage:.1f}% reduction)"
        )


class NetworkSummarizer:
    """
    Intelligent network aggregation for optimal supernet creation.
    
    Analyzes network ranges and aggregates them into larger supernets where possible,
    ensuring that:
    1. All original networks are covered
    2. No additional IP addresses are inadvertently included
    3. Maximum aggregation is achieved
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize network summarizer.
        
        Args:
            logger: Optional logger instance (creates new if not provided)
        """
        self.log = logger if logger else get_logger("network_summarizer")
    
    @staticmethod
    def _networks_to_ipnetworks(network_ranges: List[NetworkRange]) -> List[ipaddress.IPv4Network]:
        """
        Convert NetworkRange objects to IPv4Network objects.
        
        Args:
            network_ranges: List of NetworkRange objects
            
        Returns:
            List of IPv4Network objects, sorted
        """
        networks = []
        for nr in network_ranges:
            try:
                network = ipaddress.IPv4Network(nr.network_cidr, strict=False)
                networks.append(network)
            except (ValueError, ipaddress.AddressValueError) as e:
                # Skip invalid networks
                continue
        
        return sorted(networks)
    
    @staticmethod
    def _ipnetworks_to_network_ranges(networks: List[ipaddress.IPv4Network]) -> List[NetworkRange]:
        """
        Convert IPv4Network objects back to NetworkRange objects.
        
        Args:
            networks: List of IPv4Network objects
            
        Returns:
            List of NetworkRange objects
        """
        return [
            NetworkRange(
                network_cidr=str(network),
                geoname_id=None,
                registered_country_geoname_id=None,
                represented_country_geoname_id=None,
                is_anonymous_proxy=False,
                is_satellite_provider=False,
                postal_code=None,
                latitude=None,
                longitude=None,
                accuracy_radius=None,
                is_anycast=False
            )
            for network in networks
        ]
    
    def _try_aggregate_pair(
        self,
        net1: ipaddress.IPv4Network,
        net2: ipaddress.IPv4Network
    ) -> Optional[ipaddress.IPv4Network]:
        """
        Try to aggregate two adjacent networks into a single supernet.
        
        Args:
            net1: First network
            net2: Second network
            
        Returns:
            Aggregated supernet if possible, None otherwise
            
        Example:
            192.168.0.0/25 + 192.168.0.128/25 → 192.168.0.0/24
        """
        # Networks must have same prefix length to be candidates
        if net1.prefixlen != net2.prefixlen:
            return None
        
        # Try to aggregate
        try:
            supernets = list(ipaddress.collapse_addresses([net1, net2]))
            
            # If collapse produces exactly one network, aggregation succeeded
            if len(supernets) == 1:
                return supernets[0]
        except Exception:
            pass
        
        return None
    
    def _aggressive_collapse(self, networks: List[ipaddress.IPv4Network]) -> List[ipaddress.IPv4Network]:
        """
        Perform aggressive network aggregation through multiple passes.
        
        This function repeatedly tries to merge adjacent networks until no more
        merging is possible.
        
        Args:
            networks: List of networks to aggregate
            
        Returns:
            Aggregated list of networks
        """
        if not networks:
            return []
        
        # Start with sorted networks
        current = sorted(networks)
        
        self.log.info(f"Starting aggressive collapse with {len(current)} networks")
        
        pass_num = 0
        while True:
            pass_num += 1
            changed = False
            new_networks = []
            skip_next = False
            
            for i in range(len(current)):
                if skip_next:
                    skip_next = False
                    continue
                
                # Try to merge with next network if available
                if i < len(current) - 1:
                    merged = self._try_aggregate_pair(current[i], current[i + 1])
                    if merged:
                        new_networks.append(merged)
                        skip_next = True
                        changed = True
                        continue
                
                # No merge possible, keep original
                new_networks.append(current[i])
            
            self.log.debug(f"  Pass {pass_num}: {len(current)} → {len(new_networks)} networks")
            
            if not changed:
                # No more merging possible
                break
            
            current = sorted(new_networks)
        
        self.log.info(f"Aggressive collapse completed after {pass_num} passes: {len(networks)} → {len(current)} networks")
        
        return current
    
    def _validate_coverage(
        self,
        original: List[ipaddress.IPv4Network],
        summarized: List[ipaddress.IPv4Network]
    ) -> Tuple[bool, Set[ipaddress.IPv4Address]]:
        """
        Validate that summarized networks cover all original IPs without extras.
        
        Args:
            original: Original network list
            summarized: Summarized network list
            
        Returns:
            Tuple of (is_valid, extra_ips_set)
            - is_valid: True if coverage is exact, False if extra IPs included
            - extra_ips_set: Set of extra IP addresses (empty if valid)
        """
        # Build sets of all IP addresses
        original_ips = set()
        for network in original:
            for ip in network:
                original_ips.add(ip)
        
        summarized_ips = set()
        for network in summarized:
            for ip in network:
                summarized_ips.add(ip)
        
        # Check coverage
        extra_ips = summarized_ips - original_ips
        missing_ips = original_ips - summarized_ips
        
        if missing_ips:
            self.log.error(f"Coverage validation failed: {len(missing_ips)} IPs missing from summarization")
            return False, extra_ips
        
        if extra_ips:
            self.log.warning(f"Summarization includes {len(extra_ips)} extra IPs not in original networks")
            return False, extra_ips
        
        return True, set()
    
    def summarize(
        self,
        network_ranges: List[NetworkRange],
        validate: bool = True
    ) -> SummarizationResult:
        """
        Summarize network ranges into optimal supernets.
        
        Args:
            network_ranges: List of NetworkRange objects to summarize
            validate: Whether to validate coverage (default: True)
            
        Returns:
            SummarizationResult containing original and summarized networks
            
        Example:
            Input: ['1.1.1.1/32', '1.1.1.2/32', '1.1.1.3/32', '1.1.1.4/32']
            Output: ['1.1.1.0/30']  # Only if 1.1.1.0 is also in input
        """
        if not network_ranges:
            self.log.warning("No networks provided for summarization")
            return SummarizationResult(
                original_count=0,
                summarized_count=0,
                reduction_percentage=0.0,
                original_networks=[],
                summarized_networks=[]
            )
        
        self.log.info(f"Starting network summarization for {len(network_ranges)} networks")
        
        # Convert to IPv4Network objects
        original_networks = self._networks_to_ipnetworks(network_ranges)
        original_count = len(original_networks)
        
        self.log.info(f"Successfully parsed {original_count} valid networks")
        
        # Perform aggressive aggregation
        summarized_networks = self._aggressive_collapse(original_networks)
        summarized_count = len(summarized_networks)
        
        # Calculate reduction
        reduction_percentage = 0.0
        if original_count > 0:
            reduction_percentage = ((original_count - summarized_count) / original_count) * 100
        
        self.log.info(
            f"Summarization complete: {original_count} → {summarized_count} networks "
            f"({reduction_percentage:.1f}% reduction)"
        )
        
        # Validate coverage if requested
        if validate:
            self.log.info("Validating network coverage...")
            is_valid, extra_ips = self._validate_coverage(original_networks, summarized_networks)
            
            if not is_valid:
                if extra_ips:
                    self.log.error(
                        f"Coverage validation failed: {len(extra_ips)} extra IPs would be included. "
                        "Using original networks instead."
                    )
                    summarized_networks = original_networks
                    summarized_count = original_count
                    reduction_percentage = 0.0
            else:
                self.log.info("✓ Coverage validation passed: exact match, no extra IPs")
        
        # Build result
        result = SummarizationResult(
            original_count=original_count,
            summarized_count=summarized_count,
            reduction_percentage=reduction_percentage,
            original_networks=[str(n) for n in original_networks],
            summarized_networks=[str(n) for n in summarized_networks]
        )
        
        # Log sample of changes
        if summarized_count < original_count:
            self.log.info("Sample of summarization results (first 5 changes):")
            samples_shown = 0
            for i, orig_net in enumerate(original_networks[:20]):
                # Find if this network was merged into a larger one
                for summ_net in summarized_networks:
                    if orig_net.subnet_of(summ_net) and orig_net != summ_net:
                        self.log.info(f"  {orig_net} → merged into {summ_net}")
                        samples_shown += 1
                        break
                
                if samples_shown >= 5:
                    break
        
        return result
    
    def summarize_to_network_ranges(
        self,
        network_ranges: List[NetworkRange],
        validate: bool = True
    ) -> List[NetworkRange]:
        """
        Summarize network ranges and return as NetworkRange objects.
        
        Args:
            network_ranges: List of NetworkRange objects to summarize
            validate: Whether to validate coverage (default: True)
            
        Returns:
            List of summarized NetworkRange objects
        """
        result = self.summarize(network_ranges, validate=validate)
        
        # Convert back to NetworkRange objects
        summarized_ipnetworks = [
            ipaddress.IPv4Network(cidr, strict=False)
            for cidr in result.summarized_networks
        ]
        
        return self._ipnetworks_to_network_ranges(summarized_ipnetworks)
