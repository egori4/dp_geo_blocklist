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
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        delete_timeout: int = 120,
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
            delete_timeout: Timeout for DELETE operations in seconds (default: 120)
            max_retries: Maximum retry attempts for network operations (default: 3)
            retry_backoff: Exponential backoff factor for retries (default: 2.0)
            logger: Optional logger instance (creates new if not provided)
        """
        self.cc_ip = cc_ip
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.delete_timeout = delete_timeout
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
        
        # Read MAX_NETWORKS_PER_CLASS from environment
        try:
            self.max_networks_per_class = int(os.getenv("MAX_NETWORKS_PER_CLASS", "250"))
            if not (1 <= self.max_networks_per_class <= 256):
                self.log.warning(
                    f"MAX_NETWORKS_PER_CLASS={self.max_networks_per_class} out of range (1-256), "
                    "using default 250"
                )
                self.max_networks_per_class = 250
        except (ValueError, TypeError):
            self.max_networks_per_class = 250
            self.log.warning("Invalid MAX_NETWORKS_PER_CLASS in environment, using default 250")
        
        self.log.debug(f"MAX_NETWORKS_PER_CLASS configured: {self.max_networks_per_class}")
        
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
        json: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> requests.Response:
        """
        Perform HTTP request with retry logic and automatic re-authentication.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            url: Request URL
            data: Optional request body data
            json: Optional JSON request body
            timeout: Optional custom timeout (uses self.timeout if not provided)
            
        Returns:
            Response object
            
        Raises:
            NetworkError: If request fails after retries
        """
        relogin_attempted = False
        request_timeout = timeout if timeout is not None else self.timeout
        had_transaction_rollback = False  # Track if previous attempt had rollback error
        rollback_verification_attempts = 0  # Track extra attempts for rollback verification
        max_attempts = self.max_retries + 2  # Allow 2 extra attempts for rollback verification
        
        for attempt in range(1, max_attempts + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    data=data,
                    json=json,
                    verify=self.verify_ssl,
                    timeout=request_timeout
                )
                response.raise_for_status()
                
                # Log successful retry if this wasn't the first attempt
                if attempt > 1:
                    if had_transaction_rollback:
                        self.log.info(
                            f"✓ Rollback recovery successful - network verified on attempt {attempt} "
                            f"[{method.upper()}] {url}"
                        )
                    else:
                        self.log.info(
                            f"✓ Retry successful on attempt {attempt}/{self.max_retries} "
                            f"[{method.upper()}] {url}"
                        )
                
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
                
                # On 500 Internal Server Error, check if it's a non-retryable error
                if err.response is not None and err.response.status_code == 500:
                    # Check for non-retryable errors (e.g., "already exists")
                    try:
                        err_body = err.response.json()
                        err_message = err_body.get("message", "")
                        
                        # Log error details for troubleshooting
                        self.log.debug(
                            f"500 Error Details - Request: [{method.upper()}] {url}, "
                            f"Body: {json if json else data}, "
                            f"Response: {err_body}"
                        )
                        
                        # M_00386 with "already exists" - check if this is after rollback
                        # Note: M_00386 can have different messages, only "already exists" is non-retryable
                        if "m_00386" in err_message.lower() and "already exists" in err_message.lower():
                            # If we had a transaction rollback on previous attempt, this "already exists"
                            # means the network WAS successfully created despite the rollback error
                            if had_transaction_rollback:
                                self.log.info(
                                    f"✓ Network exists after transaction rollback - treating as SUCCESS. "
                                    f"[{method.upper()}] {url}"
                                )
                                # Return a success response indicating the entry exists
                                # This will be caught and handled as success by create_network_group
                                raise NetworkError(
                                    f"HTTP error (success - already exists after rollback): {str(err)}",
                                    details={
                                        "status_code": 500,
                                        "method": method,
                                        "url": url,
                                        "retryable": False,
                                        "rollback_recovery": True  # Flag indicating this is a recovered rollback
                                    }
                                )
                            else:
                                # This is a genuine "already exists" error (user tried to create duplicate)
                                self.log.warning(
                                    f"✗ Non-retryable error: Entry already exists. "
                                    f"Skipping retry. [{method.upper()}] {url}"
                                )
                                # Enhance error message and raise immediately
                                err_msg = str(err)
                                err_msg += f"\nResponse body: {err_body}"
                                raise NetworkError(
                                    f"HTTP error (non-retryable): {err_msg}",
                                    details={
                                        "status_code": 500,
                                        "method": method,
                                        "url": url,
                                        "retryable": False,
                                        "rollback_recovery": False
                                    }
                                )
                        
                        # M_00386 with transaction rollback - this is a FALSE FAILURE
                        # The transaction error is reported, but the network may have been created
                        # This commonly happens during parallel operations when the API is under load
                        if "m_00386" in err_message.lower() and "rollbackexception" in err_message.lower():
                            had_transaction_rollback = True  # Set flag for next iteration
                            rollback_verification_attempts += 1
                            
                            if rollback_verification_attempts <= 2:
                                self.log.info(
                                    f"⚠ Transaction rollback detected - network may have been created despite error. "
                                    f"Retrying immediately to verify (rollback verification attempt {rollback_verification_attempts}/2). "
                                    f"[{method.upper()}] {url}"
                                )
                                time.sleep(0.5)  # Brief pause before verification retry
                                continue
                            else:
                                self.log.error(
                                    f"✗ Transaction rollback persists after {rollback_verification_attempts} verification attempts. "
                                    f"[{method.upper()}] {url}"
                                )
                                # Fall through to normal error handling
                    except (ValueError, KeyError):
                        pass  # Failed to parse JSON, treat as normal 500
                    
                    # Normal 500 error - retry if attempts remain
                    if attempt < self.max_retries:
                        sleep_time = self.retry_backoff ** (attempt - 1) + random.uniform(0, 0.5)
                        
                        # Try to get error message for retry log
                        error_detail = ""
                        try:
                            err_body = err.response.json()
                            error_detail = f" | Error: {err_body.get('message', 'Unknown')}"
                        except:
                            pass
                        
                        self.log.warning(
                            f"✗ 500 Internal Server Error on attempt {attempt}/{self.max_retries}{error_detail}. "
                            f"Retrying in {sleep_time:.2f} seconds... [{method.upper()}] {url}"
                        )
                        time.sleep(sleep_time)
                        continue
                
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
                        f"✗ Network error on attempt {attempt}/{self.max_retries}: {err}. "
                        f"Retrying in {sleep_time:.2f} seconds..."
                    )
                    time.sleep(sleep_time)
                    continue
                else:
                    # Max retries exhausted
                    raise NetworkError(
                        f"Network operation failed after {self.max_retries} attempts: {err}",
                        details={"method": method, "url": url}
                    )
        
        # Should never reach here, but just in case
        raise NetworkError(
            f"Request failed after {self.max_retries} attempts",
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
        """Perform DELETE request with extended timeout for bulk operations."""
        return self._request("delete", url, data=data, json=json, timeout=self.delete_timeout)
    
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
            network_index: Index within the class (0-255, depending on MAX_NETWORKS_PER_CLASS)
            network_address: Network base address (e.g., "2.56.24.0")
            network_mask: Network mask (e.g., "255.255.255.128")
            
        Returns:
            Dict containing response status
            
        Raises:
            NetworkError: If creation fails
            ValidationError: If parameters are invalid
        """
        # Validate parameters using configured max_networks_per_class
        max_index = self.max_networks_per_class - 1
        if network_index < 0 or network_index > max_index:
            raise ValidationError(
                f"Network index must be 0-{max_index}, got {network_index}",
                field="network_index",
                value=network_index
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
            
        except NetworkError as e:
            # Check if this is a rollback recovery (network exists after transaction error)
            if e.details and e.details.get("rollback_recovery"):
                self.log.info(
                    f"✓ Network group '{network_class_name}[{network_index}]' successfully recovered from transaction rollback"
                )
                return {"status": "ok", "message": "Recovered from transaction rollback - entry exists"}
            
            # Check if this is a genuine "already exists" error (non-rollback)
            if e.details and not e.details.get("retryable", True) and not e.details.get("rollback_recovery", False):
                error_str = str(e).lower()
                if "already exists" in error_str and "m_00386" in error_str:
                    # This is a real duplicate - user tried to create something that already exists
                    # Re-raise as genuine failure
                    raise
            
            # Re-raise all other errors
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to create network group '{network_class_name}[{network_index}]': {str(e)}",
                details={"network_address": network_address, "network_mask": network_mask}
            )
    
    def create_network_groups_parallel(
        self,
        dp_ip: str,
        network_class_name: str,
        networks: List[Tuple[int, str, str]],
        max_workers: int = 10
    ) -> Dict[str, Any]:
        """
        Create multiple network groups in parallel using ThreadPoolExecutor.
        
        Significantly improves performance for large network sets by making
        concurrent API calls instead of sequential operations.
        
        Args:
            dp_ip: DefensePro device IP address
            network_class_name: Name of the network class
            networks: List of (index, address, mask) tuples
            max_workers: Number of concurrent workers (default: 10)
            
        Returns:
            Dict containing success/failure counts and errors
            
        Example:
            networks = [
                (0, "2.56.24.0", "255.255.255.128"),
                (1, "2.56.24.128", "255.255.255.128"),
                (2, "2.56.25.0", "255.255.255.0")
            ]
            result = client.create_network_groups_parallel(
                dp_ip="10.105.192.33",
                network_class_name="user_defined_feed_1",
                networks=networks,
                max_workers=10
            )
        """
        if not networks:
            return {"status": "ok", "created": 0, "failed": 0, "errors": []}
        
        self.log.info(
            f"Creating {len(networks)} network groups in '{network_class_name}' "
            f"using {max_workers} parallel workers"
        )
        
        created = 0
        failed = 0
        errors = []
        
        def create_single_network(network_data: Tuple[int, str, str]) -> Tuple[bool, Optional[str]]:
            """Worker function to create a single network group."""
            index, address, mask = network_data
            try:
                self.create_network_group(
                    dp_ip=dp_ip,
                    network_class_name=network_class_name,
                    network_index=index,
                    network_address=address,
                    network_mask=mask
                )
                return (True, None)
            except Exception as e:
                error_msg = f"[{network_class_name}[{index}] {address}/{mask}]: {str(e)}"
                return (False, error_msg)
        
        # Execute parallel creation
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_network = {
                executor.submit(create_single_network, network): network
                for network in networks
            }
            
            # Process completed tasks
            for future in as_completed(future_to_network):
                success, error_msg = future.result()
                if success:
                    created += 1
                else:
                    failed += 1
                    if error_msg:
                        errors.append(error_msg)
                        self.log.warning(f"Failed to create network: {error_msg}")
        
        self.log.info(
            f"Parallel creation complete: {created} succeeded, {failed} failed"
        )
        
        return {
            "status": "ok" if failed == 0 else "partial",
            "created": created,
            "failed": failed,
            "errors": errors
        }
    
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
    
    def get_all_network_classes(
        self,
        dp_ip: str,
        count: int = 1024
    ) -> List[Dict[str, str]]:
        """
        Query all configured network classes (BWM network tables) on DefensePro device.
        
        Args:
            dp_ip: DefensePro device IP address
            count: Maximum number of network classes to retrieve (default: 1024)
            
        Returns:
            List of dicts containing network class info:
            [
                {
                    "rsBWMNetworkName": "user_defined_feed_1",
                    ...
                },
                ...
            ]
            
        Raises:
            NetworkError: If query fails
        """
        path = f"/mgmt/device/byip/{dp_ip}/config/rsBWMNetworkTable"
        url = f"https://{self.cc_ip}{path}?count={count}"
        
        self.log.debug(f"Querying network classes on DefensePro {dp_ip}")
        
        try:
            response = self._get(url)
            data = response.json()
            
            # Response contains network classes grouped by name
            # We need to extract unique network class names
            network_table = data.get("rsBWMNetworkTable", [])
            
            # Extract unique network class names
            class_names_set = set()
            for entry in network_table:
                class_name = entry.get("rsBWMNetworkName")
                if class_name:
                    class_names_set.add(class_name)
            
            # Convert to list of dicts for consistency
            network_classes = [{"rsBWMNetworkName": name} for name in sorted(class_names_set)]
            
            self.log.info(f"Found {len(network_classes)} network classes on DefensePro {dp_ip}")
            
            return network_classes
            
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to query network classes on DefensePro {dp_ip}: {str(e)}",
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
            Returns empty list if network class doesn't exist or has no groups.
            
        Raises:
            NetworkError: If query fails
        """
        path = f"/mgmt/device/byip/{dp_ip}/config/rsBWMNetworkTable/{network_class_name}"
        url = f"https://{self.cc_ip}{path}"
        
        self.log.debug(f"Querying network groups in class '{network_class_name}' on DefensePro {dp_ip}")
        
        try:
            response = self._get(url)
            data = response.json()
            
            # DefensePro returns 200 OK with empty array if network class doesn't exist or has no groups
            # Response: {"rsBWMNetworkTable": []} or {"rsBWMNetworkTable": [...]}
            networks = data.get("rsBWMNetworkTable", [])
            
            if networks:
                self.log.info(f"Found {len(networks)} network groups in class '{network_class_name}'")
            else:
                self.log.debug(f"Network class '{network_class_name}' has no groups or doesn't exist (empty result)")
            
            return networks
            
        except NetworkError:
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
        
        DEPRECATED: Use delete_network_groups_bulk() for better performance.
        This method is kept for backward compatibility but makes individual API calls.
        
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
    
    def delete_network_groups_bulk(
        self,
        dp_ip: str,
        network_class_name: str,
        network_indices: List[int]
    ) -> Dict[str, Any]:
        """
        Delete multiple network groups from a DefensePro network class in a single API call.
        
        This is the preferred method for deleting network groups as it reduces API calls
        from N (one per network) to 1 (bulk deletion).
        
        Args:
            dp_ip: DefensePro device IP address
            network_class_name: Name of the network class
            network_indices: List of indices to delete (e.g., [0, 1, 2, 3, ...])
            
        Returns:
            Dict containing response status
            
        Raises:
            NetworkError: If deletion fails
        """
        if not network_indices:
            self.log.debug(f"No network groups to delete from '{network_class_name}'")
            return {"status": "ok", "message": "No networks to delete"}
        
        # Build the indicesToDelete array
        # Format: "network_class_nameU+002findex" (U+002f is URL-encoded forward slash)
        indices_to_delete = [
            f"{network_class_name}U+002f{index}"
            for index in network_indices
        ]
        
        path = f"/mgmt/device/byip/{dp_ip}/config/deletetablerows"
        url = f"https://{self.cc_ip}{path}"
        
        body = {
            "table": "rsBWMNetworkTable",
            "indicesToDelete": indices_to_delete
        }
        
        self.log.info(
            f"Bulk deleting {len(network_indices)} network groups from '{network_class_name}' "
            f"on DefensePro {dp_ip}"
        )
        self.log.debug(
            f"DELETE Request Details:\n"
            f"  URL: {url}\n"
            f"  Table: rsBWMNetworkTable\n"
            f"  Network Class: {network_class_name}\n"
            f"  Indices Count: {len(network_indices)}\n"
            f"  Index Range: {min(network_indices)}-{max(network_indices)}\n"
            f"  Sample Indices: {network_indices[:5]}{'...' if len(network_indices) > 5 else ''}\n"
            f"  Sample indicesToDelete: {indices_to_delete[:3]}{'...' if len(indices_to_delete) > 3 else ''}"
        )
        
        try:
            response = self._delete(url, json=body)
            data = response.json()
            
            if data.get("status") == "ok":
                self.log.info(
                    f"Successfully deleted {len(network_indices)} network groups from '{network_class_name}'"
                )
            else:
                self.log.warning(f"Unexpected bulk delete response: {data}")
            
            return data
            
        except NetworkError as e:
            # Enhanced error logging with automatic retry for partial deletions
            error_msg = str(e)
            
            # Check if this is a partial deletion scenario (M_00386: Field cannot be empty)
            if "m_00386" in error_msg.lower() and "field cannot be empty" in error_msg.lower():
                self.log.warning(
                    f"⚠ Bulk deletion failed with 'Field cannot be empty' error. "
                    f"Attempting recovery by re-querying actual remaining networks..."
                )
                
                try:
                    # Re-query to get actual remaining networks
                    remaining_networks = self.get_network_groups(dp_ip, network_class_name)
                    
                    if not remaining_networks:
                        self.log.info(
                            f"✓ Re-query shows 0 remaining networks. "
                            f"All {len(network_indices)} networks were actually deleted despite error."
                        )
                        return {"status": "ok", "message": "All networks deleted (verified by re-query)"}
                    
                    # Extract actual remaining indices
                    remaining_indices = []
                    for network in remaining_networks:
                        try:
                            index = int(network.get("rsBWMNetworkSubIndex", ""))
                            remaining_indices.append(index)
                        except (ValueError, TypeError):
                            pass
                    
                    if not remaining_indices:
                        self.log.info(
                            f"✓ No valid indices found in remaining {len(remaining_networks)} networks. "
                            f"Considering deletion complete."
                        )
                        return {"status": "ok", "message": "No valid indices remaining"}
                    
                    deleted_count = len(network_indices) - len(remaining_indices)
                    self.log.info(
                        f"Found {len(remaining_indices)} remaining network groups in '{network_class_name}' "
                        f"(attempted: {len(network_indices)}, partial success: {deleted_count} deleted)"
                    )
                    
                    # Retry deletion with actual remaining indices
                    self.log.info(
                        f"Retrying bulk deletion with {len(remaining_indices)} verified remaining indices..."
                    )
                    
                    retry_result = self.delete_network_groups_bulk(
                        dp_ip=dp_ip,
                        network_class_name=network_class_name,
                        network_indices=remaining_indices
                    )
                    
                    self.log.info(
                        f"✓ Retry completed. Total deletion result: "
                        f"{deleted_count} deleted in first attempt + "
                        f"{len(remaining_indices)} in retry = {len(network_indices)} total"
                    )
                    
                    return retry_result
                    
                except Exception as retry_err:
                    self.log.error(
                        f"Failed to recover from partial deletion: {retry_err}. "
                        f"Manual intervention may be required."
                    )
                    # Re-raise original error
                    raise
            
            # For other errors, just raise
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to bulk delete {len(network_indices)} network groups from '{network_class_name}': {str(e)}",
                details={"dp_ip": dp_ip, "network_class": network_class_name, "count": len(network_indices)}
            )
    
    def lock_device(self, dp_ip: str) -> Dict[str, Any]:
        """
        Lock a DefensePro device for configuration changes.
        
        Must be called before making any configuration changes to the device.
        Device should be unlocked after all changes are complete.
        
        Args:
            dp_ip: DefensePro device IP address
            
        Returns:
            Dict containing response status
            
        Raises:
            NetworkError: If lock operation fails
        """
        path = f"/mgmt/system/config/tree/device/byip/{dp_ip}/lock"
        url = f"https://{self.cc_ip}{path}"
        
        self.log.info(f"Locking DefensePro device {dp_ip}")
        
        try:
            response = self._post(url)
            data = response.json()
            
            if data.get("status") == "ok":
                self.log.info(f"Successfully locked DefensePro device {dp_ip}")
            else:
                self.log.warning(f"Unexpected lock response for {dp_ip}: {data}")
            
            return data
            
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to lock DefensePro device {dp_ip}: {str(e)}",
                details={"dp_ip": dp_ip}
            )
    
    def update_policies(self, dp_ip: str) -> Dict[str, Any]:
        """
        Apply pending configuration changes (policy updates) to DefensePro device.
        
        This operation commits all configuration changes made since the device was locked,
        making them active on the DefensePro device. Must be called after making
        configuration changes (network classes, blocklists) and before unlocking the device.
        
        Args:
            dp_ip: DefensePro device IP address
            
        Returns:
            Dict containing response status and any warnings
            
        Raises:
            NetworkError: If policy update operation fails
        """
        path = f"/mgmt/device/byip/{dp_ip}/config/updatepolicies"
        url = f"https://{self.cc_ip}{path}"
        
        self.log.info(f"Applying policy updates to DefensePro device {dp_ip}")
        self.log.debug(f"Policy update URL: {url}")
        
        try:
            # POST request with no payload to apply policy updates
            response = self._post(url)
            
            # Try to parse JSON response
            try:
                data = response.json()
            except Exception:
                # Some APIs return text instead of JSON
                data = {"response_text": response.text if hasattr(response, 'text') else "Success"}
            
            # Analyze response for success/failure indicators
            response_str = str(data).lower()
            warnings = []
            
            # Check for known error patterns
            error_patterns = ['error', 'failed', 'exception', 'timeout', 'denied']
            success_patterns = ['success', 'completed', 'applied', 'updated', 'ok']
            
            has_error = any(pattern in response_str for pattern in error_patterns)
            has_success = any(pattern in response_str for pattern in success_patterns)
            
            if has_error:
                error_msg = f"Policy update failed for {dp_ip}: API response indicates failure"
                self.log.error(f"{error_msg}: {data}")
                raise NetworkError(
                    error_msg,
                    details={"dp_ip": dp_ip, "response": data}
                )
            
            if not has_success:
                # No clear success indicator - add warning
                warnings.append(
                    "API response does not provide clear success confirmation - "
                    "verify policy status manually if issues occur"
                )
                self.log.warning(f"Policy update response unclear for {dp_ip}: {data}")
            else:
                self.log.info(f"Successfully applied policy updates to DefensePro device {dp_ip}")
            
            return {
                "status": "success",
                "message": f"Policy updates applied to {dp_ip}",
                "api_response": data,
                "warnings": warnings if warnings else None
            }
            
        except NetworkError:
            raise
        except Exception as e:
            error_msg = f"Failed to apply policy updates to DefensePro device {dp_ip}: {str(e)}"
            self.log.error(error_msg)
            raise NetworkError(
                error_msg,
                details={"dp_ip": dp_ip, "exception": str(e)}
            )
    
    def unlock_device(self, dp_ip: str) -> Dict[str, Any]:
        """
        Unlock a DefensePro device after configuration changes.
        
        Should always be called after configuration changes are complete,
        even if errors occurred during configuration.
        
        Args:
            dp_ip: DefensePro device IP address
            
        Returns:
            Dict containing response status
            
        Raises:
            NetworkError: If unlock operation fails
        """
        path = f"/mgmt/system/config/tree/device/byip/{dp_ip}/unlock"
        url = f"https://{self.cc_ip}{path}"
        
        self.log.info(f"Unlocking DefensePro device {dp_ip}")
        
        try:
            response = self._post(url)
            data = response.json()
            
            if data.get("status") == "ok":
                self.log.info(f"Successfully unlocked DefensePro device {dp_ip}")
            else:
                self.log.warning(f"Unexpected unlock response for {dp_ip}: {data}")
            
            return data
            
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(
                f"Failed to unlock DefensePro device {dp_ip}: {str(e)}",
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
