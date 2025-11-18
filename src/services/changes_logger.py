"""
Changes Logger for tracking network configuration changes.

This module provides functionality to log detailed change history including
networks added/removed, blocklists, and network class assignments for audit
and troubleshooting purposes.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class NetworkChange:
    """Represents a single network configuration change."""
    timestamp: str
    device_ip: str
    operation: str  # 'ADD' or 'DELETE'
    network_cidr: str
    blocklist_name: str
    network_class: str
    subindex: int
    mode: str  # 'OVERWRITE' or 'MERGE'
    
    def to_csv_row(self) -> Dict[str, Any]:
        """Convert to CSV row dict."""
        return {
            'timestamp': self.timestamp,
            'device_ip': self.device_ip,
            'operation': self.operation,
            'network_cidr': self.network_cidr,
            'blocklist_name': self.blocklist_name,
            'network_class': self.network_class,
            'subindex': self.subindex,
            'mode': self.mode
        }


class ChangesLogger:
    """
    Logger for tracking network configuration changes to CSV file.
    
    Records each network added/removed with full context including
    blocklist, network class, and subindex for detailed audit trail.
    """
    
    CSV_HEADERS = [
        'timestamp',
        'device_ip',
        'operation',
        'network_cidr',
        'blocklist_name',
        'network_class',
        'subindex',
        'mode'
    ]
    
    def __init__(self, changes_log_file: str, logger: Optional[logging.Logger] = None):
        """
        Initialize changes logger.
        
        Args:
            changes_log_file: Path to changes log CSV file
            logger: Optional logger instance for operation logging
        """
        self.logger = logger
        self.changes: List[NetworkChange] = []
        self.enabled = True
        
        # Handle path resolution for container vs. local execution
        changes_log_path = Path(changes_log_file)
        
        # If path starts with /app (container path) but /app doesn't exist,
        # we're running outside container - use local data directory instead
        if str(changes_log_path).startswith('/app') and not Path('/app').exists():
            # Running outside container - convert /app/data to ./data
            relative_path = str(changes_log_path).replace('/app/', '')
            changes_log_path = Path(relative_path)
            if self.logger:
                self.logger.debug(
                    f"Running outside container - using local path: {changes_log_path} "
                    f"(instead of {changes_log_file})"
                )
        
        self.changes_log_file = changes_log_path
        
        # Try to ensure directory exists
        try:
            self.changes_log_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Initialize CSV file with headers if it doesn't exist
            if not self.changes_log_file.exists():
                self._initialize_csv()
        except PermissionError as e:
            # Permission denied even after path adjustment
            if self.logger:
                self.logger.warning(
                    f"Cannot create changes log directory (permission denied): {self.changes_log_file.parent}. "
                    f"Changes logging will be disabled for this run."
                )
            self.enabled = False
        except Exception as e:
            if self.logger:
                self.logger.warning(
                    f"Failed to initialize changes log at {self.changes_log_file}: {e}. "
                    f"Changes logging will be disabled for this run."
                )
            self.enabled = False
    
    def _initialize_csv(self):
        """Create CSV file with headers."""
        try:
            with open(self.changes_log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
                writer.writeheader()
            
            if self.logger:
                self.logger.debug(f"Initialized changes log file: {self.changes_log_file}")
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to initialize changes log file: {e}")
    
    def record_addition(
        self,
        device_ip: str,
        network_cidr: str,
        blocklist_name: str,
        network_class: str,
        subindex: int,
        mode: str
    ):
        """
        Record a network addition.
        
        Args:
            device_ip: DefensePro device IP
            network_cidr: Network in CIDR notation
            blocklist_name: Name of the blocklist
            network_class: Name of the network class
            subindex: Subindex within the class
            mode: Configuration mode (OVERWRITE/MERGE)
        """
        if not self.enabled:
            return
        
        change = NetworkChange(
            timestamp=datetime.now().isoformat(),
            device_ip=device_ip,
            operation='ADD',
            network_cidr=network_cidr,
            blocklist_name=blocklist_name,
            network_class=network_class,
            subindex=subindex,
            mode=mode
        )
        self.changes.append(change)
    
    def record_deletion(
        self,
        device_ip: str,
        network_cidr: str,
        blocklist_name: str,
        network_class: str,
        subindex: int,
        mode: str
    ):
        """
        Record a network deletion.
        
        Args:
            device_ip: DefensePro device IP
            network_cidr: Network in CIDR notation
            blocklist_name: Name of the blocklist
            network_class: Name of the network class
            subindex: Subindex within the class
            mode: Configuration mode (OVERWRITE/MERGE)
        """
        if not self.enabled:
            return
        
        change = NetworkChange(
            timestamp=datetime.now().isoformat(),
            device_ip=device_ip,
            operation='DELETE',
            network_cidr=network_cidr,
            blocklist_name=blocklist_name,
            network_class=network_class,
            subindex=subindex,
            mode=mode
        )
        self.changes.append(change)
    
    def flush(self) -> int:
        """
        Write all buffered changes to CSV file.
        
        Returns:
            Number of changes written
        """
        if not self.enabled or not self.changes:
            return 0
        
        try:
            with open(self.changes_log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.CSV_HEADERS)
                for change in self.changes:
                    writer.writerow(change.to_csv_row())
            
            count = len(self.changes)
            if self.logger:
                self.logger.info(f"Recorded {count} network changes to {self.changes_log_file}")
            
            self.changes.clear()
            return count
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to write changes to log file: {e}")
            return 0
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of buffered changes.
        
        Returns:
            Dict with additions/deletions counts per device
        """
        summary: Dict[str, Dict[str, int]] = {}
        
        for change in self.changes:
            if change.device_ip not in summary:
                summary[change.device_ip] = {'additions': 0, 'deletions': 0}
            
            if change.operation == 'ADD':
                summary[change.device_ip]['additions'] += 1
            elif change.operation == 'DELETE':
                summary[change.device_ip]['deletions'] += 1
        
        return summary
    
    def log_summary(self):
        """Log summary of buffered changes."""
        if not self.enabled or not self.logger or not self.changes:
            return
        
        summary = self.get_summary()
        
        self.logger.info("=" * 70)
        self.logger.info("CHANGES SUMMARY")
        self.logger.info("=" * 70)
        
        for device_ip, counts in summary.items():
            self.logger.info(
                f"[{device_ip}] Added: {counts['additions']}, "
                f"Deleted: {counts['deletions']}"
            )
        
        total_additions = sum(c['additions'] for c in summary.values())
        total_deletions = sum(c['deletions'] for c in summary.values())
        
        self.logger.info("")
        self.logger.info(f"Total additions: {total_additions}")
        self.logger.info(f"Total deletions: {total_deletions}")
        self.logger.info(f"Changes log file: {self.changes_log_file}")
        self.logger.info("=" * 70)
