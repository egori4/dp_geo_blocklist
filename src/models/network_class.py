"""
Network class data model.

Represents a DefensePro network class configuration with its member networks.
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class NetworkClass:
    """Represents a DefensePro network class with its member networks."""
    
    name: str
    networks: List[Tuple[str, str]]  # List of (address, mask) tuples
    
    def __len__(self) -> int:
        """Return number of networks in this class."""
        return len(self.networks)
