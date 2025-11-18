"""
DefensePro State Manager for querying and tracking existing configuration.

This module provides functionality to query existing DefensePro configuration
(blocklists and network classes) and maintain state for MERGE mode operations.
"""

import logging
import ipaddress
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field

from ..models.geolocation import NetworkRange


@dataclass
class NetworkClassState:
    """State of a single network class on DefensePro."""
    class_name: str
    occupied_subindexes: Set[int] = field(default_factory=set)  # Which subindexes are used
    network_map: Dict[int, str] = field(default_factory=dict)  # subindex -> network_cidr
    
    def get_available_subindexes(self, max_networks_per_class: int = 256) -> List[int]:
        """Get list of available (free) subindexes in this class."""
        all_indexes = set(range(max_networks_per_class))
        available = all_indexes - self.occupied_subindexes
        return sorted(list(available))
    
    def get_next_available_subindex(self, max_networks_per_class: int = 256) -> Optional[int]:
        """Get the next available subindex, or None if class is full."""
        available = self.get_available_subindexes(max_networks_per_class)
        return available[0] if available else None
    
    def is_full(self, max_networks_per_class: int = 256) -> bool:
        """Check if this class is at capacity."""
        return len(self.occupied_subindexes) >= max_networks_per_class
    
    def is_empty(self) -> bool:
        """Check if this class has no networks."""
        return len(self.occupied_subindexes) == 0


@dataclass
class DefenseProState:
    """Complete state of DefensePro configuration for user_defined_feed_* resources."""
    blocklists: Set[str] = field(default_factory=set)  # Set of blocklist names
    network_classes: Dict[str, NetworkClassState] = field(default_factory=dict)  # class_name -> state
    network_to_location: Dict[str, Tuple[str, int]] = field(default_factory=dict)  # network_cidr -> (class_name, subindex)
    
    def get_all_networks(self) -> Set[str]:
        """Get set of all configured network CIDRs."""
        return set(self.network_to_location.keys())
    
    def get_class_numbers(self) -> List[int]:
        """Extract class numbers from class names (e.g., user_defined_feed_3 -> 3)."""
        numbers = []
        for class_name in self.network_classes.keys():
            try:
                # Extract number from "user_defined_feed_N"
                number = int(class_name.split('_')[-1])
                numbers.append(number)
            except (ValueError, IndexError):
                pass
        return sorted(numbers)
    
    def get_next_class_number(self) -> int:
        """Get the next class number to use (fills gaps)."""
        existing_numbers = self.get_class_numbers()
        if not existing_numbers:
            return 1
        
        # Find gaps in the sequence
        for i in range(1, max(existing_numbers) + 2):
            if i not in existing_numbers:
                return i
        
        return max(existing_numbers) + 1
    
    def get_classes_with_capacity(self, max_networks_per_class: int = 256) -> List[Tuple[str, int]]:
        """
        Get classes that have available capacity, sorted by class number (fill earlier classes first).
        
        Returns:
            List of (class_name, available_count) tuples sorted by class number
        """
        classes_with_space = []
        for class_name, state in self.network_classes.items():
            if not state.is_full(max_networks_per_class):
                available = len(state.get_available_subindexes(max_networks_per_class))
                classes_with_space.append((class_name, available))
        
        # Sort by class name (which includes class number) to fill earlier classes first
        # e.g., user_defined_feed_1, then _2, then _3, etc.
        classes_with_space.sort(key=lambda x: x[0])
        return classes_with_space


class DefenseProStateManager:
    """
    Manager for querying and tracking DefensePro configuration state.
    
    Provides methods to:
    - Query existing blocklists and network classes
    - Build maps of network -> (class, subindex)
    - Track available subindexes (gaps) in each class
    - Calculate optimal placement for new networks
    """
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize state manager.
        
        Args:
            logger: Logger instance for operation logging
        """
        self.logger = logger
    
    @staticmethod
    def _address_mask_to_cidr(address: str, mask: str) -> str:
        """
        Convert network address and mask to CIDR notation.
        
        Args:
            address: Network address (e.g., "2.56.24.0")
            mask: Network mask - can be dotted decimal (e.g., "255.255.255.128") 
                  or prefix length (e.g., "25")
            
        Returns:
            CIDR notation string (e.g., "2.56.24.0/25")
            
        Examples:
            >>> _address_mask_to_cidr("2.56.24.0", "255.255.255.128")
            "2.56.24.0/25"
            >>> _address_mask_to_cidr("10.0.0.0", "24")
            "10.0.0.0/24"
        """
        try:
            # Check if mask is already a prefix length (e.g., "24")
            if mask.isdigit():
                return f"{address}/{mask}"
            
            # Convert dotted decimal mask to prefix length
            network = ipaddress.IPv4Network(f"{address}/{mask}", strict=False)
            return str(network)
        except Exception as e:
            # Fallback: return address/32 if conversion fails
            return f"{address}/32"
    
    def query_defensepro_state(
        self,
        client,  # DefenseProClient instance
        dp_ip: str
    ) -> DefenseProState:
        """
        Query DefensePro device for current user_defined_feed_* configuration.
        
        Args:
            client: DefenseProClient instance
            dp_ip: DefensePro device IP address
            
        Returns:
            DefenseProState: Complete state of current configuration
            
        Raises:
            NetworkError: When API queries fail
        """
        self.logger.info(f"[{dp_ip}] Querying existing DefensePro configuration...")
        
        state = DefenseProState()
        
        # Query blocklists
        self.logger.debug(f"[{dp_ip}] Querying blocklists...")
        blocklists = client.get_blocklists(dp_ip)
        
        # Filter for user_defined_feed_* blocklists
        user_blocklists = [bl for bl in blocklists if bl.startswith("user_defined_feed_")]
        state.blocklists = set(user_blocklists)
        self.logger.info(f"[{dp_ip}] Found {len(user_blocklists)} user_defined_feed_* blocklists")
        
        # Query network classes
        self.logger.debug(f"[{dp_ip}] Querying network classes...")
        all_classes = client.get_network_classes(dp_ip)
        
        # Filter for user_defined_feed_* classes
        user_classes = [nc for nc in all_classes if nc.startswith("user_defined_feed_")]
        self.logger.info(f"[{dp_ip}] Found {len(user_classes)} user_defined_feed_* network classes")
        
        # Query networks within each class
        total_networks = 0
        for class_name in user_classes:
            self.logger.debug(f"[{dp_ip}] Querying networks in class: {class_name}")
            
            # Get network groups (entries) in this class
            network_groups = client.get_network_groups(dp_ip, class_name)
            
            class_state = NetworkClassState(class_name=class_name)
            
            for group in network_groups:
                # Parse API response fields:
                # - rsBWMNetworkSubIndex: subindex (0-255)
                # - rsBWMNetworkAddress: network address
                # - rsBWMNetworkMask: network mask (dotted decimal or prefix length)
                try:
                    subindex_str = group.get('rsBWMNetworkSubIndex')
                    address = group.get('rsBWMNetworkAddress')
                    mask = group.get('rsBWMNetworkMask')
                    
                    if not all([subindex_str, address, mask]):
                        self.logger.warning(
                            f"[{dp_ip}] Incomplete network group data in {class_name}: {group}"
                        )
                        continue
                    
                    subindex = int(subindex_str)
                    network_cidr = self._address_mask_to_cidr(address, mask)
                    
                    class_state.occupied_subindexes.add(subindex)
                    class_state.network_map[subindex] = network_cidr
                    state.network_to_location[network_cidr] = (class_name, subindex)
                    total_networks += 1
                    
                except (ValueError, KeyError) as e:
                    self.logger.warning(
                        f"[{dp_ip}] Failed to parse network group in {class_name}: {group}. Error: {e}"
                    )
                    continue
            
            state.network_classes[class_name] = class_state
            self.logger.debug(
                f"[{dp_ip}] Class {class_name}: {len(class_state.occupied_subindexes)} networks, "
                f"{len(class_state.get_available_subindexes())} gaps"
            )
        
        self.logger.info(
            f"[{dp_ip}] Configuration state: {len(user_blocklists)} blocklists, "
            f"{len(user_classes)} classes, {total_networks} networks"
        )
        
        return state
    
    def calculate_placement_plan(
        self,
        state: DefenseProState,
        networks_to_add: List[NetworkRange],
        max_networks_per_class: int = 256
    ) -> Dict[str, List[Tuple[int, NetworkRange]]]:
        """
        Calculate optimal placement for new networks (fill gaps first).
        
        Strategy:
        1. Fill gaps in existing classes (use freed subindexes)
        2. Append to last class if it has capacity
        3. Create new classes as needed
        
        Args:
            state: Current DefensePro state
            networks_to_add: List of networks that need to be added
            max_networks_per_class: Maximum networks per class
            
        Returns:
            Dict mapping class_name -> List[(subindex, NetworkRange)]
        """
        self.logger.info(f"Calculating placement plan for {len(networks_to_add)} networks...")
        
        placement_plan: Dict[str, List[Tuple[int, NetworkRange]]] = {}
        networks_remaining = list(networks_to_add)
        
        # Phase 1: Fill gaps in existing classes
        classes_with_space = state.get_classes_with_capacity(max_networks_per_class)
        
        for class_name, available_count in classes_with_space:
            if not networks_remaining:
                break
            
            class_state = state.network_classes[class_name]
            available_subindexes = class_state.get_available_subindexes(max_networks_per_class)
            
            # Take up to available_count networks
            networks_to_place = networks_remaining[:available_count]
            networks_remaining = networks_remaining[available_count:]
            
            placements = []
            for network, subindex in zip(networks_to_place, available_subindexes):
                placements.append((subindex, network))
            
            if placements:
                placement_plan[class_name] = placements
                self.logger.debug(
                    f"Filling gaps in {class_name}: {len(placements)} networks "
                    f"using subindexes {[p[0] for p in placements]}"
                )
        
        # Phase 2: Create new classes for remaining networks
        class_number = state.get_next_class_number()
        
        while networks_remaining:
            # Create new class
            class_name = f"user_defined_feed_{class_number}"
            
            # Take up to max_networks_per_class networks
            networks_to_place = networks_remaining[:max_networks_per_class]
            networks_remaining = networks_remaining[max_networks_per_class:]
            
            # Assign sequential subindexes starting from 0
            placements = [(i, network) for i, network in enumerate(networks_to_place)]
            placement_plan[class_name] = placements
            
            self.logger.debug(
                f"Creating new class {class_name}: {len(placements)} networks "
                f"(subindexes 0-{len(placements)-1})"
            )
            
            class_number += 1
        
        # Summary
        total_placed = sum(len(placements) for placements in placement_plan.values())
        new_classes = sum(1 for class_name in placement_plan.keys() 
                         if class_name not in state.network_classes)
        
        self.logger.info(
            f"Placement plan: {total_placed} networks across {len(placement_plan)} classes "
            f"({new_classes} new classes)"
        )
        
        return placement_plan
