"""
Network class manager for organizing network ranges into DefensePro network classes.

This module handles splitting large lists of network ranges into multiple network
classes (max 250 networks per class) and managing their creation on DefensePro devices.
"""

import logging
import ipaddress
import time
import os
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

from ..models.geolocation import NetworkRange
from ..lib.exceptions import ValidationError
from ..lib.logging_config import get_logger
from .defensepro_client import DefenseProClient


@dataclass
class NetworkClass:
    """Represents a DefensePro network class with its member networks."""
    
    name: str
    networks: List[Tuple[str, str]]  # List of (address, mask) tuples
    
    def __len__(self) -> int:
        """Return number of networks in this class."""
        return len(self.networks)


class NetworkClassManager:
    """
    Manages creation and organization of DefensePro network classes.
    
    Handles splitting network ranges into classes with max 250 networks each,
    using standardized naming convention (user_defined_feed_1, _2, _3, etc.).
    """
    
    MAX_NETWORKS_PER_CLASS = 250
    CLASS_NAME_PREFIX = "user_defined_feed"
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize network class manager.
        
        Args:
            logger: Optional logger instance (creates new if not provided)
        """
        self.log = logger if logger else get_logger("network_class_manager")
    
    @staticmethod
    def cidr_to_address_mask(cidr: str) -> Tuple[str, str]:
        """
        Convert CIDR notation to network address and mask.
        
        Args:
            cidr: Network in CIDR notation (e.g., "2.56.24.0/25")
            
        Returns:
            Tuple of (network_address, network_mask) in dotted decimal notation
            
        Raises:
            ValidationError: If CIDR is invalid
            
        Examples:
            >>> cidr_to_address_mask("2.56.24.0/25")
            ("2.56.24.0", "255.255.255.128")
            
            >>> cidr_to_address_mask("10.20.30.0/24")
            ("10.20.30.0", "255.255.255.0")
        """
        try:
            network = ipaddress.IPv4Network(cidr, strict=False)
            network_address = str(network.network_address)
            network_mask = str(network.netmask)
            return network_address, network_mask
        except (ValueError, ipaddress.AddressValueError) as e:
            raise ValidationError(
                f"Invalid CIDR notation '{cidr}': {str(e)}",
                field="network_cidr",
                expected_type="IPv4 CIDR"
            )
    
    def split_into_classes(
        self,
        network_ranges: List[NetworkRange]
    ) -> List[NetworkClass]:
        """
        Split network ranges into multiple network classes.
        
        Groups networks into classes with max 250 networks each, using
        naming convention user_defined_feed_1, user_defined_feed_2, etc.
        
        Args:
            network_ranges: List of NetworkRange objects to organize
            
        Returns:
            List of NetworkClass objects
            
        Example:
            For 773 networks:
            - user_defined_feed_1: networks 0-249 (250 networks)
            - user_defined_feed_2: networks 250-499 (250 networks)
            - user_defined_feed_3: networks 500-749 (250 networks)
            - user_defined_feed_4: networks 750-772 (23 networks)
        """
        if not network_ranges:
            self.log.warning("No network ranges provided to split into classes")
            return []
        
        total_networks = len(network_ranges)
        num_classes = (total_networks + self.MAX_NETWORKS_PER_CLASS - 1) // self.MAX_NETWORKS_PER_CLASS
        
        self.log.info(
            f"Splitting {total_networks} networks into {num_classes} network classes "
            f"(max {self.MAX_NETWORKS_PER_CLASS} networks per class)"
        )
        
        classes = []
        
        for class_num in range(1, num_classes + 1):
            start_idx = (class_num - 1) * self.MAX_NETWORKS_PER_CLASS
            end_idx = min(start_idx + self.MAX_NETWORKS_PER_CLASS, total_networks)
            
            class_name = f"{self.CLASS_NAME_PREFIX}_{class_num}"
            class_networks = []
            
            for network_range in network_ranges[start_idx:end_idx]:
                try:
                    address, mask = self.cidr_to_address_mask(network_range.network_cidr)
                    class_networks.append((address, mask))
                except ValidationError as e:
                    self.log.error(
                        f"Failed to convert CIDR '{network_range.network_cidr}' "
                        f"for class '{class_name}': {e}"
                    )
                    continue
            
            network_class = NetworkClass(name=class_name, networks=class_networks)
            classes.append(network_class)
            
            self.log.info(
                f"Created class '{class_name}' with {len(network_class)} networks "
                f"(range: {start_idx}-{end_idx-1})"
            )
        
        return classes
    
    def create_network_classes(
        self,
        client: DefenseProClient,
        dp_ip: str,
        network_classes: List[NetworkClass]
    ) -> Dict[str, any]:
        """
        Create all network classes and their network groups on DefensePro.
        
        Supports both sequential and parallel execution modes based on environment
        configuration (PARALLEL_EXECUTION and PARALLEL_WORKERS).
        
        Args:
            client: DefenseProClient instance for API operations
            dp_ip: DefensePro device IP address
            network_classes: List of NetworkClass objects to create
            
        Returns:
            Dict containing creation statistics:
            - classes_attempted: Number of classes attempted
            - classes_successful: Number of classes with all networks created
            - groups_attempted: Total network groups attempted
            - groups_successful: Total network groups successfully created
            - groups_failed: Total network groups that failed
            - errors: List of error messages
            
        Raises:
            ValidationError: If parameters are invalid
        """
        if not network_classes:
            self.log.warning("No network classes provided for creation")
            return {
                "classes_attempted": 0,
                "classes_successful": 0,
                "groups_attempted": 0,
                "groups_successful": 0,
                "groups_failed": 0,
                "errors": []
            }
        
        # Read configuration from environment
        parallel_execution = os.getenv("PARALLEL_EXECUTION", "true").lower() == "true"
        parallel_workers = int(os.getenv("PARALLEL_WORKERS", "10"))
        
        execution_mode = "parallel" if parallel_execution else "sequential"
        self.log.info(
            f"Creating {len(network_classes)} network classes on DefensePro {dp_ip} "
            f"(mode: {execution_mode}" + (f", workers: {parallel_workers}" if parallel_execution else "") + ")"
        )
        
        classes_attempted = 0
        classes_successful = 0
        groups_attempted = 0
        groups_successful = 0
        groups_failed = 0
        errors = []
        
        start_time = time.time()
        
        for network_class in network_classes:
            classes_attempted += 1
            class_start_time = time.time()
            
            self.log.info(
                f"Processing network class '{network_class.name}' "
                f"with {len(network_class)} networks ({execution_mode} mode)"
            )
            
            if parallel_execution:
                # Parallel execution using ThreadPoolExecutor
                networks_data = [
                    (index, address, mask)
                    for index, (address, mask) in enumerate(network_class.networks)
                ]
                
                result = client.create_network_groups_parallel(
                    dp_ip=dp_ip,
                    network_class_name=network_class.name,
                    networks=networks_data,
                    max_workers=parallel_workers
                )
                
                groups_attempted += len(network_class)
                groups_successful += result["created"]
                groups_failed += result["failed"]
                errors.extend(result["errors"])
                
                if result["failed"] == 0:
                    classes_successful += 1
                
                class_elapsed = time.time() - class_start_time
                rate = result["created"] / class_elapsed if class_elapsed > 0 else 0
                self.log.info(
                    f"Class '{network_class.name}' completed in {class_elapsed:.2f}s (parallel mode, {parallel_workers} workers): "
                    f"{result['created']} succeeded, {result['failed']} failed ({rate:.1f} networks/sec)"
                )
                
            else:
                # Sequential execution (original implementation)
                class_errors = 0
                class_successes = 0
                
                for index, (address, mask) in enumerate(network_class.networks):
                    groups_attempted += 1
                    
                    try:
                        client.create_network_group(
                            dp_ip=dp_ip,
                            network_class_name=network_class.name,
                            network_index=index,
                            network_address=address,
                            network_mask=mask
                        )
                        groups_successful += 1
                        class_successes += 1
                        
                        # Log progress for large classes
                        if (index + 1) % 50 == 0:
                            elapsed_so_far = time.time() - class_start_time
                            rate = (index + 1) / elapsed_so_far if elapsed_so_far > 0 else 0
                            self.log.info(
                                f"  Progress: {index + 1}/{len(network_class)} networks created "
                                f"in '{network_class.name}' ({elapsed_so_far:.1f}s, {rate:.1f} networks/sec)"
                            )
                        
                    except Exception as e:
                        groups_failed += 1
                        class_errors += 1
                        error_msg = (
                            f"Failed to create network group '{network_class.name}[{index}]' "
                            f"({address}/{mask}): {str(e)}"
                        )
                        errors.append(error_msg)
                        self.log.error(error_msg)
                
                # Mark class as successful if all networks were created
                if class_errors == 0:
                    classes_successful += 1
                
                class_elapsed = time.time() - class_start_time
                rate = class_successes / class_elapsed if class_elapsed > 0 else 0
                self.log.info(
                    f"Class '{network_class.name}' completed in {class_elapsed:.2f}s (sequential mode): "
                    f"{class_successes} succeeded, {class_errors} failed ({rate:.1f} networks/sec)"
                )
        
        total_elapsed = time.time() - start_time
        overall_rate = groups_successful / total_elapsed if total_elapsed > 0 else 0
        
        summary = {
            "classes_attempted": classes_attempted,
            "classes_successful": classes_successful,
            "groups_attempted": groups_attempted,
            "groups_successful": groups_successful,
            "groups_failed": groups_failed,
            "errors": errors
        }
        
        self.log.info(
            f"Network class creation complete in {total_elapsed:.2f}s ({execution_mode} mode): "
            f"{classes_successful}/{classes_attempted} classes successful, "
            f"{groups_successful}/{groups_attempted} network groups created ({overall_rate:.1f} networks/sec)"
        )
        
        if errors:
            self.log.warning(f"Encountered {len(errors)} errors during creation")
        
        return summary
