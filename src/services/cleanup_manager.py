"""
Cleanup manager for removing existing DefensePro network classes and blocklists.

This module handles pre-cleanup operations using a query-first approach:
1. Query existing blocklists and network classes on DefensePro
2. Filter by user-defined prefix (user_defined_feed_*)
3. Delete blocklists first, then their associated network classes
4. Only attempts deletion of resources that actually exist (no 404 errors)
"""

import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass

from ..lib.exceptions import NetworkError
from ..lib.logging_config import get_logger
from .defensepro_client import DefenseProClient


@dataclass
class CleanupResult:
    """Results of cleanup operation."""
    
    blocklists_found: int
    blocklists_deleted: int
    blocklists_failed: int
    network_classes_found: int
    network_groups_deleted: int
    network_groups_failed: int
    errors: List[str]
    
    def __str__(self) -> str:
        return (
            f"Cleanup: {self.blocklists_deleted}/{self.blocklists_found} blocklists, "
            f"{self.network_groups_deleted} network groups deleted"
        )


class CleanupManager:
    """
    Manages cleanup of existing DefensePro configurations using query-first approach.
    
    Workflow:
    1. Query existing blocklists → filter by user_defined_feed_* prefix
    2. Query existing network classes → filter by user_defined_feed_* prefix
    3. Delete blocklists first (they reference network classes)
    4. Delete network classes (query each class for network groups, then delete)
    
    """
    
    CLASS_NAME_PREFIX = "user_defined_feed"
    BLOCKLIST_SUFFIX = "_blocklist"
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize cleanup manager.
        
        Args:
            logger: Optional logger instance (creates new if not provided)
        """
        self.log = logger if logger else get_logger("cleanup_manager")
    
    def _matches_prefix(self, name: str) -> bool:
        """
        Check if a name matches the user_defined_feed_* pattern.
        
        Args:
            name: Name to check
            
        Returns:
            True if name starts with CLASS_NAME_PREFIX
        """
        return name.lower().startswith(self.CLASS_NAME_PREFIX.lower())
    
    def cleanup_device(
        self,
        client: DefenseProClient,
        dp_ip: str
    ) -> CleanupResult:
        """
        Clean up existing configurations on a single DefensePro device.
        
        Uses query-first approach:
        1. Query all blocklists → filter by prefix → delete matches
        2. Query network classes from blocklist references → delete network groups
        
        Args:
            client: DefenseProClient instance for API operations
            dp_ip: DefensePro device IP address
            
        Returns:
            CleanupResult containing deletion statistics
        """
        self.log.info(f"Starting query-first cleanup on DefensePro {dp_ip}")
        
        blocklists_found = 0
        blocklists_deleted = 0
        blocklists_failed = 0
        network_classes_found = 0
        network_groups_deleted = 0
        network_groups_failed = 0
        errors = []
        
        # Step 1: Query and delete blocklists
        self.log.info(f"[{dp_ip}] Step 1: Querying existing blocklists...")
        
        try:
            all_blocklists = client.get_all_blocklists(dp_ip, count=1024)
            
            # Filter by user_defined_feed_* prefix
            target_blocklists = [
                bl for bl in all_blocklists
                if self._matches_prefix(bl.get("rsNewBlockListName", ""))
            ]
            
            blocklists_found = len(target_blocklists)
            
            if blocklists_found == 0:
                self.log.info(f"[{dp_ip}] No user_defined_feed_* blocklists found (first run or already clean)")
            else:
                self.log.info(
                    f"[{dp_ip}] Found {blocklists_found} user_defined_feed_* blocklists to delete"
                )
                
                # Build set of network classes referenced by blocklists
                referenced_network_classes: Set[str] = set()
                
                # Delete each blocklist
                for bl_info in target_blocklists:
                    blocklist_name = bl_info.get("rsNewBlockListName", "")
                    network_class = bl_info.get("rsNewBlockListSrcNetwork", "")
                    
                    if network_class and self._matches_prefix(network_class):
                        referenced_network_classes.add(network_class)
                    
                    try:
                        client.delete_blocklist(dp_ip, blocklist_name)
                        blocklists_deleted += 1
                    except NetworkError as e:
                        blocklists_failed += 1
                        error_msg = f"Failed to delete blocklist '{blocklist_name}': {str(e)}"
                        errors.append(error_msg)
                        self.log.error(error_msg)
                    except Exception as e:
                        blocklists_failed += 1
                        error_msg = f"Unexpected error deleting blocklist '{blocklist_name}': {str(e)}"
                        errors.append(error_msg)
                        self.log.error(error_msg)
                
                self.log.info(
                    f"[{dp_ip}] Blocklist deletion complete: "
                    f"{blocklists_deleted} deleted, {blocklists_failed} failed"
                )
                
                # Step 2: Delete network classes
                self.log.info(f"[{dp_ip}] Step 2: Deleting network classes...")
                
                network_classes_found = len(referenced_network_classes)
                
                if network_classes_found == 0:
                    self.log.info(f"[{dp_ip}] No network classes referenced by blocklists")
                else:
                    self.log.info(
                        f"[{dp_ip}] Found {network_classes_found} network classes to delete: "
                        f"{', '.join(sorted(referenced_network_classes))}"
                    )
                    
                    # Query and delete each network class
                    for network_class in sorted(referenced_network_classes):
                        self.log.info(f"[{dp_ip}] Querying network groups in class '{network_class}'...")
                        
                        try:
                            network_groups = client.get_network_groups(dp_ip, network_class)
                            
                            if not network_groups:
                                self.log.info(f"[{dp_ip}] Network class '{network_class}' has no groups or doesn't exist")
                                continue
                            
                            self.log.info(
                                f"[{dp_ip}] Found {len(network_groups)} network groups in '{network_class}'"
                            )
                            
                            # Delete each network group
                            for network_group in network_groups:
                                class_name = network_group.get("rsBWMNetworkName", "")
                                index_str = network_group.get("rsBWMNetworkSubIndex", "")
                                
                                try:
                                    index = int(index_str)
                                except (ValueError, TypeError):
                                    error_msg = (
                                        f"Invalid network index '{index_str}' for class '{class_name}'"
                                    )
                                    errors.append(error_msg)
                                    self.log.warning(error_msg)
                                    network_groups_failed += 1
                                    continue
                                
                                try:
                                    client.delete_network_group(dp_ip, class_name, index)
                                    network_groups_deleted += 1
                                except NetworkError as e:
                                    network_groups_failed += 1
                                    error_msg = (
                                        f"Failed to delete network group '{class_name}[{index}]': {str(e)}"
                                    )
                                    errors.append(error_msg)
                                    self.log.error(error_msg)
                                except Exception as e:
                                    network_groups_failed += 1
                                    error_msg = (
                                        f"Unexpected error deleting network group '{class_name}[{index}]': {str(e)}"
                                    )
                                    errors.append(error_msg)
                                    self.log.error(error_msg)
                            
                            self.log.info(
                                f"[{dp_ip}] Deleted {len(network_groups)} network groups from '{network_class}'"
                            )
                            
                        except NetworkError as e:
                            error_msg = f"Failed to query/delete network class '{network_class}': {str(e)}"
                            errors.append(error_msg)
                            self.log.error(error_msg)
                        except Exception as e:
                            error_msg = f"Unexpected error with network class '{network_class}': {str(e)}"
                            errors.append(error_msg)
                            self.log.error(error_msg)
                    
                    self.log.info(
                        f"[{dp_ip}] Network class deletion complete: "
                        f"{network_groups_deleted} network groups deleted, {network_groups_failed} failed"
                    )
                    
        except NetworkError as e:
            error_msg = f"Failed to query blocklists on {dp_ip}: {str(e)}"
            errors.append(error_msg)
            self.log.error(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error during cleanup on {dp_ip}: {str(e)}"
            errors.append(error_msg)
            self.log.error(error_msg)
        
        # Build result
        result = CleanupResult(
            blocklists_found=blocklists_found,
            blocklists_deleted=blocklists_deleted,
            blocklists_failed=blocklists_failed,
            network_classes_found=network_classes_found,
            network_groups_deleted=network_groups_deleted,
            network_groups_failed=network_groups_failed,
            errors=errors
        )
        
        self.log.info(f"[{dp_ip}] Cleanup complete: {result}")
        
        if errors:
            self.log.warning(f"[{dp_ip}] Encountered {len(errors)} errors during cleanup")
        
        return result
    
    def cleanup_multiple_devices(
        self,
        client: DefenseProClient,
        dp_ips: List[str]
    ) -> Dict[str, CleanupResult]:
        """
        Clean up existing configurations on multiple DefensePro devices.
        
        Args:
            client: DefenseProClient instance for API operations
            dp_ips: List of DefensePro device IP addresses
            
        Returns:
            Dict mapping dp_ip to CleanupResult for each device
        """
        self.log.info(f"Starting query-first cleanup on {len(dp_ips)} DefensePro devices")
        
        results = {}
        
        for device_num, dp_ip in enumerate(dp_ips, start=1):
            self.log.info("=" * 70)
            self.log.info(f"Cleaning DefensePro {device_num}/{len(dp_ips)}: {dp_ip}")
            self.log.info("=" * 70)
            
            try:
                result = self.cleanup_device(client, dp_ip)
                results[dp_ip] = result
            except Exception as e:
                self.log.error(f"[{dp_ip}] ✗ Failed to clean device: {e}")
                # Create error result
                results[dp_ip] = CleanupResult(
                    blocklists_found=0,
                    blocklists_deleted=0,
                    blocklists_failed=0,
                    network_classes_found=0,
                    network_groups_deleted=0,
                    network_groups_failed=0,
                    errors=[f"Device cleanup failed: {str(e)}"]
                )
        
        # Overall summary
        total_blocklists_found = sum(r.blocklists_found for r in results.values())
        total_blocklists_deleted = sum(r.blocklists_deleted for r in results.values())
        total_network_classes_found = sum(r.network_classes_found for r in results.values())
        total_network_groups_deleted = sum(r.network_groups_deleted for r in results.values())
        total_errors = sum(len(r.errors) for r in results.values())
        
        self.log.info("=" * 70)
        self.log.info("CLEANUP SUMMARY")
        self.log.info("=" * 70)
        self.log.info(f"Devices cleaned: {len(results)}")
        self.log.info(f"Total blocklists found: {total_blocklists_found}")
        self.log.info(f"Total blocklists deleted: {total_blocklists_deleted}")
        self.log.info(f"Total network classes found: {total_network_classes_found}")
        self.log.info(f"Total network groups deleted: {total_network_groups_deleted}")
        
        if total_errors > 0:
            self.log.warning(f"Total errors encountered: {total_errors}")
        else:
            self.log.info("✓ Cleanup completed without errors")
        
        if total_blocklists_found == 0:
            self.log.info("✓ No existing user_defined_feed_* configurations found (first run or clean state)")
        
        return results
