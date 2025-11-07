"""
DefensePro CyberController API client for network class and blocklist management.

This module provides session-managed authentication and API operations for
creating network classes and blocklists on Radware DefensePro devices via
the CyberController management interface.

"""

import requests
import time
import random
import os
import tempfile
import pickle
import hashlib
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from ..lib.exceptions import NetworkError, ValidationError
from ..lib.logging_config import get_logger


class DefenseProClient:
    """
    Client for Radware DefensePro CyberController API operations.
    
    Provides session-managed authentication with automatic re-login on 403 errors,
    session caching, and retry logic for network operations.
    """
    
    def __init__(
        self,
        cc_ip: str,
        username: str,
        password: str,
        verify_ssl: bool = False,
        session_lifetime: int = 600,
        timeout: int = 30,
        max_retries: int = 3,
        retry_backoff: float = 2.0,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize DefensePro CyberController client.
        
        Args:
            cc_ip: CyberController IP address or hostname
            username: Authentication username
            password: Authentication password
            verify_ssl: Whether to verify SSL certificates (default: False for self-signed)
            session_lifetime: Session cache lifetime in seconds (default: 600)
            timeout: Request timeout in seconds (default: 30)
            max_retries: Maximum retry attempts for network operations (default: 3)
            retry_backoff: Exponential backoff factor for retries (default: 2.0)
            logger: Optional logger instance (creates new if not provided)
        """
        self.cc_ip = cc_ip
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.session = requests.Session()
        self._username = username
        self._password = password
        self.session_lifetime = session_lifetime
        
        # Disable SSL warnings if verification is disabled
        if not self.verify_ssl:
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass
        
        # Set up logging
        self.log = logger if logger else get_logger("defensepro_client")
        
        # Load or create session
        self._load_or_login()
    
    def _get_session_file(self) -> tuple[Path, Path]:
        """
        Get session cache file paths.
        
        Returns:
            Tuple of (session_file_path, session_time_file_path)
        """
        key = f"{self.cc_ip}_{self._username}"
        key_hash = hashlib.md5(key.encode()).hexdigest()
        
        # Try to use ./tmp/radware_cc_sessions under current working directory
        try:
            cwd = os.getcwd()
            session_dir = Path(cwd) / "tmp" / "radware_cc_sessions"
            session_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            # Fallback to system temp dir if creation fails
            session_dir = Path(tempfile.gettempdir()) / "radware_cc_sessions"
            session_dir.mkdir(parents=True, exist_ok=True)
        
        session_file = session_dir / f"session_{key_hash}.pkl"
        session_time_file = session_dir / f"session_{key_hash}.time"
        
        return session_file, session_time_file
    
    def _load_or_login(self) -> None:
        """
        Load cached session or perform fresh login.
        
        Checks for existing session cache and reuses if still valid,
        otherwise performs fresh authentication.
        """
        session_file, session_time_file = self._get_session_file()
        
        # Log separator for new run
        self.log.info("=" * 70)
        
        if session_file.exists() and session_time_file.exists():
            try:
                with open(session_time_file, "r") as tf:
                    created_time = float(tf.read().strip())
                
                age = time.time() - created_time
                self.log.debug(
                    f"Session file age: {age:.2f} seconds "
                    f"(lifetime: {self.session_lifetime}s)"
                )
                
                if age < self.session_lifetime:
                    with open(session_file, "rb") as f:
                        cookies = pickle.load(f)
                    self.session.cookies.update(cookies)
                    self.log.info(
                        f"Reusing session for {self.cc_ip} as {self._username} "
                        f"(age: {age:.2f}s < {self.session_lifetime}s)"
                    )
                    return
                else:
                    self.log.info(
                        f"Session expired for {self.cc_ip} as {self._username} "
                        f"(age: {age:.2f}s >= {self.session_lifetime}s), re-logging in"
                    )
            except Exception as e:
                self.log.error(f"Failed to load session: {e}")
        
        # Perform fresh login
        self.log.info(f"Logging in to CyberController at {self.cc_ip} as {self._username}")
        self._login()
        
        # Save session after login
        with open(session_file, "wb") as f:
            pickle.dump(self.session.cookies, f)
        with open(session_time_file, "w") as tf:
            tf.write(str(time.time()))
        
        self.log.info(f"Session stored at: {session_file}")
    
    def _login(self) -> None:
        """
        Perform authentication to CyberController.
        
        Raises:
            NetworkError: If authentication fails
        """
        url = f"https://{self.cc_ip}/mgmt/system/user/login"
        
        try:
            response = self.session.post(
                url,
                json={"username": self._username, "password": self._password},
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            data = response.json()
            if data.get("status") != "ok":
                raise NetworkError(
                    f"Login failed to {self.cc_ip}: {data}",
                    details={"response": data}
                )
            
            self.log.info(f"Successfully logged in to CyberController at {self.cc_ip}")
            
        except requests.exceptions.HTTPError as e:
            raise NetworkError(
                f"HTTP error during login to {self.cc_ip}: {str(e)}",
                details={"status_code": e.response.status_code if e.response else None}
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(
                f"Network error during login to {self.cc_ip}: {str(e)}"
            )
        except Exception as e:
            raise NetworkError(
                f"Unexpected error during login to {self.cc_ip}: {str(e)}"
            )
    
    def _request(
        self,
        method: str,
        url: str,
        data: Optional[Any] = None,
        json: Optional[Dict[str, Any]] = None
    ) -> requests.Response:
        """
        Perform HTTP request with retry logic and automatic re-authentication.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: Request URL
            data: Optional request body data
            json: Optional JSON request body
            
        Returns:
            Response object
            
        Raises:
            NetworkError: If request fails after retries
        """
        relogin_attempted = False
        
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    data=data,
                    json=json,
                    verify=self.verify_ssl,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response
                
            except requests.exceptions.HTTPError as err:
                # On 403, re-login once and retry
                if err.response is not None and err.response.status_code == 403 and not relogin_attempted:
                    self.log.info(
                        f"[{method.upper()}] 403 Forbidden. "
                        "Reauthenticating and retrying once..."
                    )
                    try:
                        self._load_or_login()
                        relogin_attempted = True
                        continue
                    except Exception as login_err:
                        raise NetworkError(
                            f"403 Forbidden. Re-login failed: {login_err}",
                            details={"original_error": str(err)}
                        )
                
                # Enhance error message with response body if available
                err_msg = str(err)
                if err.response is not None:
                    try:
                        content_type = err.response.headers.get('Content-Type', '')
                        if 'application/json' in content_type:
                            err_body = err.response.json()
                        else:
                            err_body = err.response.text
                        err_msg += f"\nResponse body: {err_body}"
                    except Exception:
                        pass
                
                raise NetworkError(
                    f"HTTP error: {err_msg}",
                    details={
                        "status_code": err.response.status_code if err.response else None,
                        "method": method,
                        "url": url
                    }
                )
                
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.SSLError,
                    requests.exceptions.Timeout) as err:
                if attempt < self.max_retries:
                    sleep_time = self.retry_backoff ** (attempt - 1) + random.uniform(0, 0.5)
                    self.log.warning(
                        f"Network error on attempt {attempt}/{self.max_retries}: {err}. "
                        f"Retrying in {sleep_time:.2f} seconds..."
                    )
                    time.sleep(sleep_time)
                else:
                    raise NetworkError(
                        f"Network operation failed after {self.max_retries} attempts: {err}",
                        details={"method": method, "url": url}
                    )
    
    def _post(self, url: str, data: Optional[Any] = None, json: Optional[Dict[str, Any]] = None) -> requests.Response:
        """Perform POST request."""
        return self._request("post", url, data=data, json=json)
    
    def _get(self, url: str) -> requests.Response:
        """Perform GET request."""
        return self._request("get", url)
    
    def _put(self, url: str, data: Optional[Any] = None, json: Optional[Dict[str, Any]] = None) -> requests.Response:
        """Perform PUT request."""
        return self._request("put", url, data=data, json=json)
    
    def _delete(self, url: str, data: Optional[Any] = None, json: Optional[Dict[str, Any]] = None) -> requests.Response:
        """Perform DELETE request."""
        return self._request("delete", url, data=data, json=json)
    
    def create_network_group(
        self,
        dp_ip: str,
        network_class_name: str,
        network_index: int,
        network_address: str,
        network_mask: str
    ) -> Dict[str, Any]:
        """
        Create a network group within a DefensePro network class.
        
        Args:
            dp_ip: DefensePro device IP address
            network_class_name: Name of the network class (e.g., "user_defined_feed_1")
            network_index: Index within the class (0-249)
            network_address: Network base address (e.g., "2.56.24.0")
            network_mask: Network mask (e.g., "255.255.255.128")
            
        Returns:
            Dict containing response status
            
        Raises:
            NetworkError: If creation fails
            ValidationError: If parameters are invalid
        """
        # Validate parameters
        if network_index < 0 or network_index > 249:
            raise ValidationError(
                f"Network index must be 0-249, got {network_index}",
                field="network_index",
                expected_type="0-249"
            )
        
        path = f"/mgmt/device/byip/{dp_ip}/config/rsBWMNetworkTable/{network_class_name}/{network_index}"
        url = f"https://{self.cc_ip}{path}"
        
        body = {
            "rsBWMNetworkName": network_class_name,
            "rsBWMNetworkSubIndex": network_index,
            "rsBWMNetworkAddress": network_address,
            "rsBWMNetworkMask": network_mask,
            "rsBWMNetworkMode": "1"
        }
        
        self.log.debug(f"Creating network group '{network_class_name}[{network_index}]': {network_address}/{network_mask}")
        
        try:
            response = self._post(url, json=body)
            data = response.json()
            
            if data.get("status") == "ok":
                self.log.debug(f"Successfully created network group '{network_class_name}[{network_index}]'")
            
            return data
            
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to create network group '{network_class_name}[{network_index}]': {str(e)}",
                details={"network_address": network_address, "network_mask": network_mask}
            )
    
    def create_blocklist(
        self,
        dp_ip: str,
        blocklist_name: str,
        network_class_name: str
    ) -> Dict[str, Any]:
        """
        Create an access list blocklist referencing a network class.
        
        Args:
            dp_ip: DefensePro device IP address
            blocklist_name: Name for the blocklist (e.g., "user_defined_feed_1_blocklist")
            network_class_name: Network class to reference (e.g., "user_defined_feed_1")
            
        Returns:
            Dict containing response status
            
        Raises:
            NetworkError: If creation fails
        """
        path = f"/mgmt/device/byip/{dp_ip}/config/rsNewBlockListTable/{blocklist_name}/"
        url = f"https://{self.cc_ip}{path}"
        
        body = {
            "rsNewBlockListState": "1",
            "rsNewBlockListAction": "1",
            "rsNewBlockListSrcNetwork": network_class_name,
            "rsNewBlockListReportAction": "1",
            "rsNewBlockListPacketReport": "2"
        }
        
        self.log.debug(f"Creating blocklist '{blocklist_name}' for network class '{network_class_name}'")
        
        try:
            response = self._post(url, json=body)
            data = response.json()
            
            if data.get("status") == "ok":
                self.log.info(f"Successfully created blocklist '{blocklist_name}'")
            
            return data
            
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to create blocklist '{blocklist_name}': {str(e)}",
                details={"network_class": network_class_name}
            )
    
    def get_all_blocklists(
        self,
        dp_ip: str,
        count: int = 1024
    ) -> List[Dict[str, str]]:
        """
        Query all configured blocklists on DefensePro device.
        
        Args:
            dp_ip: DefensePro device IP address
            count: Maximum number of blocklists to retrieve (default: 1024)
            
        Returns:
            List of dicts containing blocklist info:
            [
                {
                    "rsNewBlockListName": "test1",
                    "rsNewBlockListSrcNetwork": "TEST"
                },
                ...
            ]
            
        Raises:
            NetworkError: If query fails
        """
        path = f"/mgmt/device/byip/{dp_ip}/config/rsNewBlockListTable"
        url = f"https://{self.cc_ip}{path}?count={count}&props=rsNewBlockListName,rsNewBlockListSrcNetwork"
        
        self.log.debug(f"Querying blocklists on DefensePro {dp_ip}")
        
        try:
            response = self._get(url)
            data = response.json()
            
            blocklists = data.get("rsNewBlockListTable", [])
            self.log.info(f"Found {len(blocklists)} blocklists on DefensePro {dp_ip}")
            
            return blocklists
            
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to query blocklists on DefensePro {dp_ip}: {str(e)}",
                details={"dp_ip": dp_ip}
            )
    
    def get_network_groups(
        self,
        dp_ip: str,
        network_class_name: str
    ) -> List[Dict[str, str]]:
        """
        Query all network groups within a network class on DefensePro device.
        
        Args:
            dp_ip: DefensePro device IP address
            network_class_name: Name of the network class to query
            
        Returns:
            List of dicts containing network group info:
            [
                {
                    "rsBWMNetworkName": "test3",
                    "rsBWMNetworkSubIndex": "1",
                    "rsBWMNetworkAddress": "1.2.3.5",
                    "rsBWMNetworkMask": "32",
                    "rsBWMNetworkFromIP": "1.2.3.5",
                    "rsBWMNetworkToIP": "1.2.3.5",
                    "rsBWMNetworkMode": "1"
                },
                ...
            ]
            
        Raises:
            NetworkError: If query fails
        """
        path = f"/mgmt/device/byip/{dp_ip}/config/rsBWMNetworkTable/{network_class_name}"
        url = f"https://{self.cc_ip}{path}"
        
        self.log.debug(f"Querying network groups in class '{network_class_name}' on DefensePro {dp_ip}")
        
        try:
            response = self._get(url)
            data = response.json()
            
            networks = data.get("rsBWMNetworkTable", [])
            self.log.info(f"Found {len(networks)} network groups in class '{network_class_name}'")
            
            return networks
            
        except NetworkError as e:
            # If 404, the network class doesn't exist - return empty list
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                self.log.debug(f"Network class '{network_class_name}' does not exist (404)")
                return []
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to query network groups in class '{network_class_name}': {str(e)}",
                details={"dp_ip": dp_ip, "network_class": network_class_name}
            )
    
    def delete_blocklist(
        self,
        dp_ip: str,
        blocklist_name: str
    ) -> Dict[str, Any]:
        """
        Delete an access list blocklist from DefensePro.
        
        Args:
            dp_ip: DefensePro device IP address
            blocklist_name: Name of the blocklist to delete
            
        Returns:
            Dict containing response status
            
        Raises:
            NetworkError: If deletion fails
        """
        path = f"/mgmt/device/byip/{dp_ip}/config/rsNewBlockListTable/{blocklist_name}/"
        url = f"https://{self.cc_ip}{path}"
        
        self.log.debug(f"Deleting blocklist '{blocklist_name}' from DefensePro {dp_ip}")
        
        try:
            response = self._delete(url)
            data = response.json()
            
            if data.get("status") == "ok":
                self.log.info(f"Successfully deleted blocklist '{blocklist_name}'")
            
            return data
            
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to delete blocklist '{blocklist_name}': {str(e)}",
                details={"dp_ip": dp_ip}
            )
    
    def delete_network_group(
        self,
        dp_ip: str,
        network_class_name: str,
        network_index: int
    ) -> Dict[str, Any]:
        """
        Delete a network group from a DefensePro network class.
        
        Args:
            dp_ip: DefensePro device IP address
            network_class_name: Name of the network class
            network_index: Index within the class to delete
            
        Returns:
            Dict containing response status
            
        Raises:
            NetworkError: If deletion fails
        """
        path = f"/mgmt/device/byip/{dp_ip}/config/rsBWMNetworkTable/{network_class_name}/{network_index}"
        url = f"https://{self.cc_ip}{path}"
        
        self.log.debug(f"Deleting network group '{network_class_name}[{network_index}]' from DefensePro {dp_ip}")
        
        try:
            response = self._delete(url)
            data = response.json()
            
            if data.get("status") == "ok":
                self.log.debug(f"Successfully deleted network group '{network_class_name}[{network_index}]'")
            
            return data
            
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to delete network group '{network_class_name}[{network_index}]': {str(e)}",
                details={"dp_ip": dp_ip}
            )
    
    def close(self) -> None:
        """Close the HTTP session."""
        if self.session:
            self.session.close()
            self.log.debug("DefensePro client session closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
