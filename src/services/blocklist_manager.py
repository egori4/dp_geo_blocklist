"""
Blocklist manager for creating DefensePro access control lists.

This module handles creation of blocklists that reference network classes,
enabling actual IP blocking functionality on DefensePro devices.
"""

import logging
from typing import List, Dict, Optional

from ..lib.exceptions import NetworkError
from ..lib.logging_config import get_logger
from ..models.network_class import NetworkClass
from .defensepro_client import DefenseProClient


class BlocklistManager:
    """
    Manages creation of DefensePro access list blocklists.
    
    Creates blocklists that reference network classes, enabling blocking
    of all IP ranges within those network classes.
    """
    
    BLOCKLIST_NAME_SUFFIX = "_blocklist"
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize blocklist manager.
        
        Args:
            logger: Optional logger instance (creates new if not provided)
        """
        self.log = logger if logger else get_logger("blocklist_manager")
    
    @staticmethod
    def generate_blocklist_name(network_class_name: str) -> str:
        """
        Generate blocklist name from network class name.
        
        Args:
            network_class_name: Network class name (e.g., "user_defined_feed_1")
            
        Returns:
            Blocklist name (e.g., "user_defined_feed_1_blocklist")
            
        Example:
            >>> generate_blocklist_name("user_defined_feed_1")
            "user_defined_feed_1_blocklist"
        """
        return f"{network_class_name}{BlocklistManager.BLOCKLIST_NAME_SUFFIX}"
    
    def create_blocklists(
        self,
        client: DefenseProClient,
        dp_ip: str,
        network_classes: List[NetworkClass]
    ) -> Dict[str, any]:
        """
        Create blocklists for all network classes on DefensePro.
        
        Creates one blocklist per network class, referencing that class
        as the source for blocking operations.
        
        Args:
            client: DefenseProClient instance for API operations
            dp_ip: DefensePro device IP address
            network_classes: List of NetworkClass objects to create blocklists for
            
        Returns:
            Dict containing creation statistics:
            - blocklists_attempted: Number of blocklists attempted
            - blocklists_successful: Number of blocklists successfully created
            - blocklists_failed: Number of blocklists that failed
            - errors: List of error messages
        """
        if not network_classes:
            self.log.warning("No network classes provided for blocklist creation")
            return {
                "blocklists_attempted": 0,
                "blocklists_successful": 0,
                "blocklists_failed": 0,
                "errors": []
            }
        
        self.log.info(
            f"Creating {len(network_classes)} blocklists on DefensePro {dp_ip}"
        )
        
        blocklists_attempted = 0
        blocklists_successful = 0
        blocklists_failed = 0
        errors = []
        
        for network_class in network_classes:
            blocklists_attempted += 1
            blocklist_name = self.generate_blocklist_name(network_class.name)
            
            self.log.info(
                f"Creating blocklist '{blocklist_name}' for network class '{network_class.name}' "
                f"({len(network_class)} networks)"
            )
            
            try:
                client.create_blocklist(
                    dp_ip=dp_ip,
                    blocklist_name=blocklist_name,
                    network_class_name=network_class.name
                )
                blocklists_successful += 1
                self.log.info(
                    f"Successfully created blocklist '{blocklist_name}'"
                )
                
            except Exception as e:
                blocklists_failed += 1
                error_msg = (
                    f"Failed to create blocklist '{blocklist_name}' "
                    f"for network class '{network_class.name}': {str(e)}"
                )
                errors.append(error_msg)
                self.log.error(error_msg)
        
        summary = {
            "blocklists_attempted": blocklists_attempted,
            "blocklists_successful": blocklists_successful,
            "blocklists_failed": blocklists_failed,
            "errors": errors
        }
        
        self.log.info(
            f"Blocklist creation complete: "
            f"{blocklists_successful}/{blocklists_attempted} blocklists created successfully"
        )
        
        if errors:
            self.log.warning(f"Encountered {len(errors)} errors during blocklist creation")
        
        return summary
