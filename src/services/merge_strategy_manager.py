"""
Merge Strategy Manager for incremental DefensePro configuration updates.

This module orchestrates MERGE mode operations, which incrementally update
DefensePro configuration by only adding/deleting changed networks rather than
full overwrite.
"""

import logging
import time
import ipaddress
from typing import List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..models.geolocation import NetworkRange
from ..lib.exceptions import NetworkError, ValidationError
from .defensepro_state_manager import DefenseProStateManager, DefenseProState
from .network_diff_calculator import NetworkDiffCalculator, NetworkDiff
from .blocklist_manager import BlocklistManager


@dataclass
class MergeResult:
    """Result of MERGE mode operation on a single device."""
    dp_ip: str
    success: bool
    networks_added: int = 0
    networks_deleted: int = 0
    classes_created: int = 0
    classes_deleted: int = 0
    blocklists_created: int = 0
    blocklists_deleted: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    @property
    def total_changes(self) -> int:
        """Total number of network changes."""
        return self.networks_added + self.networks_deleted


class MergeStrategyManager:
    """
    Manager for MERGE mode DefensePro configuration updates.
    
    Implements incremental updates:
    1. Query existing DefensePro state
    2. Calculate diff (networks to add/delete)
    3. Delete removed networks (selective deletion)
    4. Add new networks (fill gaps first)
    5. Update policy
    
    Key features:
    - No blocking gap (networks stay blocked during update)
    - Fill gaps in existing classes before creating new ones
    - Reuse freed class numbers
    - Delete empty classes and corresponding blocklists
    - Parallel execution support
    """
    
    def __init__(
        self,
        logger: logging.Logger,
        changes_logger=None,  # Optional ChangesLogger instance
        parallel_execution: bool = True,
        parallel_workers: int = 10
    ):
        """
        Initialize merge strategy manager.
        
        Args:
            logger: Logger instance
            changes_logger: Optional ChangesLogger for tracking changes
            parallel_execution: Enable parallel operations
            parallel_workers: Number of concurrent workers
        """
        self.logger = logger
        self.changes_logger = changes_logger
        self.parallel_execution = parallel_execution
        self.parallel_workers = parallel_workers
        
        # Initialize sub-managers
        self.state_manager = DefenseProStateManager(logger)
        self.diff_calculator = NetworkDiffCalculator(logger)
    
    @staticmethod
    def _cidr_to_address_mask(cidr: str) -> Tuple[str, str]:
        """
        Convert CIDR notation to network address and mask.
        
        Args:
            cidr: Network in CIDR notation (e.g., "104.28.131.176/32")
            
        Returns:
            Tuple of (network_address, network_mask) in dotted decimal notation
            
        Raises:
            ValidationError: If CIDR is invalid
        """
        try:
            network = ipaddress.IPv4Network(cidr, strict=False)
            return str(network.network_address), str(network.netmask)
        except (ValueError, ipaddress.AddressValueError) as e:
            raise ValidationError(
                f"Invalid CIDR notation '{cidr}': {str(e)}",
                field="network_cidr",
                value=cidr
            )
    
    def merge_configuration(
        self,
        client,  # DefenseProClient instance
        dp_ips: List[str],
        incoming_networks: List[NetworkRange],
        max_networks_per_class: int = 256
    ) -> Dict[str, MergeResult]:
        """
        Perform MERGE mode configuration update on multiple devices.
        
        Args:
            client: DefenseProClient instance
            dp_ips: List of DefensePro device IPs
            incoming_networks: Networks from GeoIP (after filter/summarization)
            max_networks_per_class: Maximum networks per class
            
        Returns:
            Dict mapping dp_ip -> MergeResult
        """
        self.logger.info("=" * 70)
        self.logger.info("MERGE MODE: INCREMENTAL CONFIGURATION UPDATE")
        self.logger.info("=" * 70)
        self.logger.info(f"Target devices: {len(dp_ips)}")
        self.logger.info(f"Incoming networks: {len(incoming_networks)}")
        self.logger.info(f"Parallel execution: {self.parallel_execution}")
        self.logger.info("=" * 70)
        
        results = {}
        
        # Process each device
        for i, dp_ip in enumerate(dp_ips, 1):
            self.logger.info("")
            self.logger.info("=" * 70)
            self.logger.info(f"Device {i}/{len(dp_ips)}: {dp_ip}")
            self.logger.info("=" * 70)
            
            start_time = time.time()
            
            try:
                result = self._merge_single_device(
                    client=client,
                    dp_ip=dp_ip,
                    incoming_networks=incoming_networks,
                    max_networks_per_class=max_networks_per_class
                )
                result.duration_seconds = time.time() - start_time
                result.success = len(result.errors) == 0
                
            except Exception as e:
                self.logger.error(f"[{dp_ip}] MERGE operation failed: {e}", exc_info=True)
                result = MergeResult(
                    dp_ip=dp_ip,
                    success=False,
                    duration_seconds=time.time() - start_time,
                    errors=[str(e)]
                )
            
            results[dp_ip] = result
            
            # Log device summary
            self._log_device_summary(result)
        
        # Log overall summary
        self._log_overall_summary(results)
        
        return results
    
    def _merge_single_device(
        self,
        client,
        dp_ip: str,
        incoming_networks: List[NetworkRange],
        max_networks_per_class: int
    ) -> MergeResult:
        """
        Perform MERGE operation on a single device.
        
        Returns:
            MergeResult with operation statistics
        """
        result = MergeResult(dp_ip=dp_ip, success=True)
        
        try:
            # Lock device
            self.logger.info(f"[{dp_ip}] Locking device...")
            client.lock_device(dp_ip)
            
            # STEP 1: Query existing state
            self.logger.info(f"[{dp_ip}] Step 1: Querying existing configuration...")
            state = self.state_manager.query_defensepro_state(client, dp_ip)
            
            # STEP 2: Calculate diff
            self.logger.info(f"[{dp_ip}] Step 2: Calculating configuration differences...")
            diff = self.diff_calculator.calculate_diff(
                incoming_networks=incoming_networks,
                existing_networks_map=state.network_to_location
            )
            
            # Check if any changes needed
            if not diff.has_changes:
                self.logger.info(f"[{dp_ip}] ✓ No changes needed - configuration is up-to-date")
                return result
            
            # STEP 3: Delete removed networks
            if diff.networks_to_delete:
                self.logger.info(
                    f"[{dp_ip}] Step 3: Deleting {len(diff.networks_to_delete)} removed networks..."
                )
                del_stats = self._delete_networks(client, dp_ip, diff.networks_to_delete, state)
                result.networks_deleted = del_stats['networks_deleted']
                result.classes_deleted = del_stats['classes_deleted']
                result.blocklists_deleted = del_stats['blocklists_deleted']
                result.errors.extend(del_stats['errors'])
                
                # Update state after deletions (track freed subindexes)
                self._update_state_after_deletions(state, diff.networks_to_delete)
            else:
                self.logger.info(f"[{dp_ip}] Step 3: No networks to delete - skipping")
            
            # STEP 4: Add new networks
            if diff.networks_to_add:
                self.logger.info(
                    f"[{dp_ip}] Step 4: Adding {len(diff.networks_to_add)} new networks..."
                )
                add_stats = self._add_networks(
                    client, dp_ip, diff.networks_to_add, state, max_networks_per_class
                )
                result.networks_added = add_stats['networks_added']
                result.classes_created = add_stats['classes_created']
                result.blocklists_created = add_stats['blocklists_created']
                result.errors.extend(add_stats['errors'])
            else:
                self.logger.info(f"[{dp_ip}] Step 4: No networks to add - skipping")
            
            # STEP 5: Update policy
            self.logger.info(f"[{dp_ip}] Step 5: Applying policy updates...")
            try:
                client.update_policies(dp_ip)
                self.logger.info(f"[{dp_ip}] ✓ Policy updates applied")
            except Exception as e:
                error_msg = f"Failed to apply policy updates: {str(e)}"
                self.logger.error(f"[{dp_ip}] {error_msg}")
                result.errors.append(error_msg)
            
        except Exception as e:
            error_msg = f"MERGE operation error: {str(e)}"
            self.logger.error(f"[{dp_ip}] {error_msg}", exc_info=True)
            result.errors.append(error_msg)
            result.success = False
            
        finally:
            # Always unlock device
            try:
                self.logger.info(f"[{dp_ip}] Unlocking device...")
                client.unlock_device(dp_ip)
            except Exception as e:
                self.logger.error(f"[{dp_ip}] Failed to unlock device: {e}")
        
        return result
    
    def _delete_networks(
        self,
        client,
        dp_ip: str,
        networks_to_delete: List[Tuple[str, str, int]],
        state: DefenseProState
    ) -> Dict[str, Any]:
        """
        Delete specific networks from DefensePro.
        
        Handles:
        - Selective subindex deletion
        - Empty class detection and deletion
        - Blocklist deletion (when last class deleted)
        
        Returns:
            Dict with statistics: networks_deleted, classes_deleted, blocklists_deleted, errors
        """
        stats = {
            'networks_deleted': 0,
            'classes_deleted': 0,
            'blocklists_deleted': 0,
            'errors': []
        }
        
        # Group deletions by class
        grouped = self.diff_calculator.group_deletions_by_class(networks_to_delete)
        
        # Track which classes will become empty after deletions
        classes_to_delete = []
        
        for class_name, deletions in grouped.items():
            self.logger.info(f"[{dp_ip}] Deleting {len(deletions)} networks from class '{class_name}'...")
            
            class_state = state.network_classes.get(class_name)
            if not class_state:
                self.logger.warning(f"[{dp_ip}] Class '{class_name}' not found in state - skipping")
                continue
            
            # Check if this class will become empty
            remaining_networks = len(class_state.occupied_subindexes) - len(deletions)
            
            if remaining_networks == 0:
                # Class will be empty - delete entire class and blocklist
                classes_to_delete.append(class_name)
                self.logger.info(
                    f"[{dp_ip}] Class '{class_name}' will be empty after deletions - "
                    "will delete class and blocklist"
                )
            else:
                # Selective deletion - delete each subindex
                for cidr, subindex in deletions:
                    try:
                        client.delete_network_subindex(dp_ip, class_name, subindex)
                        stats['networks_deleted'] += 1
                        
                        # Log deletion to changes log
                        if self.changes_logger:
                            blocklist_name = BlocklistManager.generate_blocklist_name(class_name)
                            self.changes_logger.record_deletion(
                                device_ip=dp_ip,
                                network_cidr=cidr,
                                blocklist_name=blocklist_name,
                                network_class=class_name,
                                subindex=subindex,
                                mode='MERGE'
                            )
                        
                        self.logger.debug(f"[{dp_ip}] Deleted {cidr} from {class_name}[{subindex}]")
                    except Exception as e:
                        error_msg = f"Failed to delete {cidr} from {class_name}[{subindex}]: {str(e)}"
                        self.logger.error(f"[{dp_ip}] {error_msg}")
                        stats['errors'].append(error_msg)
        
        # Delete empty classes and their blocklists
        for class_name in classes_to_delete:
            try:
                # Generate blocklist name using centralized method
                blocklist_name = BlocklistManager.generate_blocklist_name(class_name)
                
                # Delete blocklist first
                if blocklist_name in state.blocklists:
                    self.logger.info(f"[{dp_ip}] Deleting empty blocklist '{blocklist_name}'...")
                    client.delete_blocklist(dp_ip, blocklist_name)
                    stats['blocklists_deleted'] += 1
                
                # Delete all subindexes in the class (DefensePro requires deleting all entries)
                class_state = state.network_classes[class_name]
                subindexes_to_delete = sorted(class_state.occupied_subindexes)
                
                self.logger.info(
                    f"[{dp_ip}] Deleting {len(subindexes_to_delete)} subindexes from '{class_name}'..."
                )
                
                for subindex in subindexes_to_delete:
                    client.delete_network_subindex(dp_ip, class_name, subindex)
                    stats['networks_deleted'] += 1
                
                stats['classes_deleted'] += 1
                self.logger.info(f"[{dp_ip}] ✓ Deleted empty class '{class_name}' and blocklist")
                
            except Exception as e:
                error_msg = f"Failed to delete empty class '{class_name}': {str(e)}"
                self.logger.error(f"[{dp_ip}] {error_msg}")
                stats['errors'].append(error_msg)
        
        self.logger.info(
            f"[{dp_ip}] Deletion summary: {stats['networks_deleted']} networks, "
            f"{stats['classes_deleted']} classes, {stats['blocklists_deleted']} blocklists"
        )
        
        return stats
    
    def _add_networks(
        self,
        client,
        dp_ip: str,
        networks_to_add: List[NetworkRange],
        state: DefenseProState,
        max_networks_per_class: int
    ) -> Dict[str, Any]:
        """
        Add new networks to DefensePro (fill gaps first).
        
        Strategy:
        1. Calculate placement plan (fills gaps in existing classes)
        2. Create networks using parallel or sequential execution
        3. Create new blocklists for new classes
        
        Returns:
            Dict with statistics: networks_added, classes_created, blocklists_created, errors
        """
        stats = {
            'networks_added': 0,
            'classes_created': 0,
            'blocklists_created': 0,
            'errors': []
        }
        
        # Calculate placement plan
        placement_plan = self.state_manager.calculate_placement_plan(
            state=state,
            networks_to_add=networks_to_add,
            max_networks_per_class=max_networks_per_class
        )
        
        # Track which classes are new (need blocklist creation)
        new_classes = [
            class_name for class_name in placement_plan.keys()
            if class_name not in state.network_classes
        ]
        
        # Create networks (parallel or sequential)
        if self.parallel_execution and len(placement_plan) > 1:
            add_result = self._add_networks_parallel(client, dp_ip, placement_plan)
        else:
            add_result = self._add_networks_sequential(client, dp_ip, placement_plan)
        
        stats['networks_added'] = add_result['networks_added']
        stats['errors'].extend(add_result['errors'])
        
        # Create blocklists for new classes
        for class_name in new_classes:
            try:
                # Generate blocklist name using centralized method
                blocklist_name = BlocklistManager.generate_blocklist_name(class_name)
                
                self.logger.info(f"[{dp_ip}] Creating blocklist '{blocklist_name}' for new class...")
                client.create_blocklist(dp_ip, blocklist_name, class_name)
                stats['blocklists_created'] += 1
                stats['classes_created'] += 1
                
            except Exception as e:
                error_msg = f"Failed to create blocklist for '{class_name}': {str(e)}"
                self.logger.error(f"[{dp_ip}] {error_msg}")
                stats['errors'].append(error_msg)
        
        self.logger.info(
            f"[{dp_ip}] Addition summary: {stats['networks_added']} networks, "
            f"{stats['classes_created']} new classes, {stats['blocklists_created']} new blocklists"
        )
        
        return stats
    
    def _add_networks_sequential(
        self,
        client,
        dp_ip: str,
        placement_plan: Dict[str, List[Tuple[int, NetworkRange]]]
    ) -> Dict[str, Any]:
        """Add networks sequentially (one by one)."""
        result = {'networks_added': 0, 'errors': []}
        
        for class_name, placements in placement_plan.items():
            self.logger.info(
                f"[{dp_ip}] Adding {len(placements)} networks to class '{class_name}' (sequential)..."
            )
            
            for subindex, network in placements:
                try:
                    # Convert CIDR to address and mask
                    address, mask = self._cidr_to_address_mask(network.network_cidr)
                    client.create_network_group(
                        dp_ip=dp_ip,
                        network_class_name=class_name,
                        network_index=subindex,
                        network_address=address,
                        network_mask=mask
                    )
                    result['networks_added'] += 1
                    
                    # Log addition to changes log
                    if self.changes_logger:
                        blocklist_name = BlocklistManager.generate_blocklist_name(class_name)
                        self.changes_logger.record_addition(
                            device_ip=dp_ip,
                            network_cidr=network.network_cidr,
                            blocklist_name=blocklist_name,
                            network_class=class_name,
                            subindex=subindex,
                            mode='MERGE'
                        )
                    
                except Exception as e:
                    error_msg = f"Failed to add {network.network_cidr} to {class_name}[{subindex}]: {str(e)}"
                    self.logger.error(f"[{dp_ip}] {error_msg}")
                    result['errors'].append(error_msg)
        
        return result
    
    def _add_networks_parallel(
        self,
        client,
        dp_ip: str,
        placement_plan: Dict[str, List[Tuple[int, NetworkRange]]]
    ) -> Dict[str, Any]:
        """Add networks in parallel using ThreadPoolExecutor."""
        result = {'networks_added': 0, 'errors': []}
        
        # Flatten placement plan into tasks
        tasks = []
        for class_name, placements in placement_plan.items():
            for subindex, network in placements:
                try:
                    # Convert CIDR to address and mask
                    address, mask = self._cidr_to_address_mask(network.network_cidr)
                    tasks.append((class_name, subindex, network, address, mask))
                except Exception as e:
                    error_msg = f"Failed to convert CIDR {network.network_cidr}: {str(e)}"
                    self.logger.error(f"[{dp_ip}] {error_msg}")
                    result['errors'].append(error_msg)
        
        self.logger.info(
            f"[{dp_ip}] Adding {len(tasks)} networks across {len(placement_plan)} classes (parallel)..."
        )
        
        with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
            futures = {
                executor.submit(
                    client.create_network_group,
                    dp_ip,
                    class_name,
                    subindex,
                    address,
                    mask
                ): (class_name, subindex, network)
                for class_name, subindex, network, address, mask in tasks
            }
            
            for future in as_completed(futures):
                class_name, subindex, network = futures[future]
                try:
                    future.result()
                    result['networks_added'] += 1
                    
                    # Log addition to changes log
                    if self.changes_logger:
                        blocklist_name = BlocklistManager.generate_blocklist_name(class_name)
                        self.changes_logger.record_addition(
                            device_ip=dp_ip,
                            network_cidr=network.network_cidr,
                            blocklist_name=blocklist_name,
                            network_class=class_name,
                            subindex=subindex,
                            mode='MERGE'
                        )
                    
                except Exception as e:
                    error_msg = f"Failed to add {network.network_cidr} to {class_name}[{subindex}]: {str(e)}"
                    self.logger.error(f"[{dp_ip}] {error_msg}")
                    result['errors'].append(error_msg)
        
        return result
    
    def _update_state_after_deletions(
        self,
        state: DefenseProState,
        networks_deleted: List[Tuple[str, str, int]]
    ):
        """Update state to reflect deletions (track freed subindexes)."""
        for cidr, class_name, subindex in networks_deleted:
            if class_name in state.network_classes:
                class_state = state.network_classes[class_name]
                class_state.occupied_subindexes.discard(subindex)
                if subindex in class_state.network_map:
                    del class_state.network_map[subindex]
            
            if cidr in state.network_to_location:
                del state.network_to_location[cidr]
    
    def _log_device_summary(self, result: MergeResult):
        """Log summary for a single device."""
        self.logger.info("")
        self.logger.info("─" * 70)
        self.logger.info(f"[{result.dp_ip}] DEVICE SUMMARY")
        self.logger.info("─" * 70)
        
        if result.success:
            self.logger.info(f"[{result.dp_ip}] Status: ✓ SUCCESS")
        else:
            self.logger.error(f"[{result.dp_ip}] Status: ✗ FAILED ({len(result.errors)} errors)")
        
        self.logger.info(f"[{result.dp_ip}] Duration: {result.duration_seconds:.1f}s")
        self.logger.info(f"[{result.dp_ip}] Networks added: {result.networks_added}")
        self.logger.info(f"[{result.dp_ip}] Networks deleted: {result.networks_deleted}")
        self.logger.info(f"[{result.dp_ip}] Classes created: {result.classes_created}")
        self.logger.info(f"[{result.dp_ip}] Classes deleted: {result.classes_deleted}")
        self.logger.info(f"[{result.dp_ip}] Blocklists created: {result.blocklists_created}")
        self.logger.info(f"[{result.dp_ip}] Blocklists deleted: {result.blocklists_deleted}")
        
        if result.errors:
            self.logger.error(f"[{result.dp_ip}] Errors encountered:")
            for i, error in enumerate(result.errors[:5], 1):
                self.logger.error(f"[{result.dp_ip}]   {i}. {error}")
            if len(result.errors) > 5:
                self.logger.error(f"[{result.dp_ip}]   ... and {len(result.errors) - 5} more errors")
    
    def _log_overall_summary(self, results: Dict[str, MergeResult]):
        """Log summary across all devices."""
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("MERGE MODE: OVERALL SUMMARY")
        self.logger.info("=" * 70)
        
        total_devices = len(results)
        successful_devices = sum(1 for r in results.values() if r.success)
        failed_devices = total_devices - successful_devices
        
        total_networks_added = sum(r.networks_added for r in results.values())
        total_networks_deleted = sum(r.networks_deleted for r in results.values())
        total_classes_created = sum(r.classes_created for r in results.values())
        total_classes_deleted = sum(r.classes_deleted for r in results.values())
        total_blocklists_created = sum(r.blocklists_created for r in results.values())
        total_blocklists_deleted = sum(r.blocklists_deleted for r in results.values())
        
        total_duration = sum(r.duration_seconds for r in results.values())
        avg_duration = total_duration / total_devices if total_devices > 0 else 0
        
        self.logger.info(f"Devices processed: {total_devices}")
        self.logger.info(f"  Successful: {successful_devices}")
        self.logger.info(f"  Failed: {failed_devices}")
        self.logger.info("")
        self.logger.info("Configuration Changes:")
        self.logger.info(f"  Networks added: {total_networks_added}")
        self.logger.info(f"  Networks deleted: {total_networks_deleted}")
        self.logger.info(f"  Classes created: {total_classes_created}")
        self.logger.info(f"  Classes deleted: {total_classes_deleted}")
        self.logger.info(f"  Blocklists created: {total_blocklists_created}")
        self.logger.info(f"  Blocklists deleted: {total_blocklists_deleted}")
        self.logger.info("")
        self.logger.info(f"Total duration: {total_duration:.1f}s")
        self.logger.info(f"Average duration per device: {avg_duration:.1f}s")
        
        if failed_devices > 0:
            self.logger.warning("")
            self.logger.warning("Failed devices:")
            for dp_ip, result in results.items():
                if not result.success:
                    self.logger.warning(f"  • {dp_ip}: {len(result.errors)} errors")
        
        self.logger.info("=" * 70)
