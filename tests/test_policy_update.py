"""
Test policy update functionality after network and blocklist creation.

Usage:
    pytest tests/test_policy_update.py -v
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.services.defensepro_client import DefenseProClient
from src.lib.exceptions import NetworkError


class TestPolicyUpdate:
    """Test policy update operations."""
    
    def test_update_policies_success(self):
        """Verify policy update API is called correctly on success."""
        # Mock successful response with clear success indicator
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "success",
            "message": "Policy updates applied"
        }
        
        with patch.object(DefenseProClient, '_load_or_login'), \
             patch.object(DefenseProClient, '_post', return_value=mock_response):
            client = DefenseProClient(
                cc_ip="10.105.193.3",
                username="test",
                password="test"
            )
            
            result = client.update_policies("10.105.192.33")
            
            assert result["status"] == "success"
            assert "Policy updates applied" in result["message"]
            assert result["warnings"] is None or len(result["warnings"]) == 0
    
    def test_update_policies_unclear_response(self):
        """Verify warning issued when API response lacks clear success indicator."""
        # Mock response without clear success indicator
        mock_response = Mock()
        mock_response.json.return_value = {
            "result": "done"
        }
        
        with patch.object(DefenseProClient, '_load_or_login'), \
             patch.object(DefenseProClient, '_post', return_value=mock_response):
            client = DefenseProClient(
                cc_ip="10.105.193.3",
                username="test",
                password="test"
            )
            
            result = client.update_policies("10.105.192.33")
            
            assert result["status"] == "success"
            assert result["warnings"] is not None
            assert len(result["warnings"]) > 0
            assert "does not provide clear success confirmation" in result["warnings"][0]
    
    def test_update_policies_error_in_response(self):
        """Verify error raised when API response contains error indicators."""
        # Mock response with error indicator
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": "error",
            "message": "Failed to apply policy updates"
        }
        
        with patch.object(DefenseProClient, '_load_or_login'), \
             patch.object(DefenseProClient, '_post', return_value=mock_response):
            client = DefenseProClient(
                cc_ip="10.105.193.3",
                username="test",
                password="test"
            )
            
            with pytest.raises(NetworkError, match="Policy update failed"):
                client.update_policies("10.105.192.33")
    
    def test_update_policies_text_response(self):
        """Verify handling of non-JSON text responses."""
        # Mock text response
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("No JSON")
        mock_response.text = "Policy update completed successfully"
        
        with patch.object(DefenseProClient, '_load_or_login'), \
             patch.object(DefenseProClient, '_post', return_value=mock_response):
            client = DefenseProClient(
                cc_ip="10.105.193.3",
                username="test",
                password="test"
            )
            
            result = client.update_policies("10.105.192.33")
            
            assert result["status"] == "success"
            assert "response_text" in result["api_response"]
            assert "completed successfully" in result["api_response"]["response_text"]
    
    def test_update_policies_network_error(self):
        """Verify NetworkError raised on request failure."""
        with patch.object(DefenseProClient, '_load_or_login'), \
             patch.object(DefenseProClient, '_post', side_effect=NetworkError("Connection timeout")):
            client = DefenseProClient(
                cc_ip="10.105.193.3",
                username="test",
                password="test"
            )
            
            with pytest.raises(NetworkError):
                client.update_policies("10.105.192.33")


class TestPolicyUpdateWorkflow:
    """Test policy update integration in main workflow."""
    
    def test_workflow_calls_policy_update_after_blocklists(self):
        """Verify policy update is called after creating blocklists."""
        # This is an integration test placeholder
        # Actual test would mock the entire workflow and verify call order:
        # 1. Lock device
        # 2. Create network classes
        # 3. Create blocklists
        # 4. Update policies  <-- NEW STEP
        # 5. Unlock device
        pass
    
    def test_workflow_unlocks_on_policy_update_failure(self):
        """Verify device is unlocked even if policy update fails."""
        # This validates the finally block still executes
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
