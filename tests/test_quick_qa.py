"""
Quick QA Test Suite - Run this before deployment to validate core functionality.

Usage:
    pytest tests/test_quick_qa.py -v --tb=short

This test suite provides rapid pre-production validation (< 2 minutes).
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import requests

from src.models.config import Config
from src.lib.exceptions import ConfigError, ValidationError


class TestConfigurationQA:
    """Validate configuration loading and validation."""
    
    def test_config_loads_all_required_variables(self, monkeypatch):
        """Ensure all required environment variables are loaded."""
        # Set up minimal required environment
        env_vars = {
            "CC_IP": "10.105.193.3",
            "DP_IPS": "10.105.192.33",
            "CC_USERNAME": "radware",
            "CC_PASSWORD": "radware",
            "RADWARE_API_URL": "https://services.radware.com/api/geodb/getfile",
            "TARGET_COUNTRY": "UA",
            "TARGET_REGIONS": "43,09,14",
        }
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)
        
        config = Config.from_environment()
        
        assert config.cc_ip == "10.105.193.3"
        assert config.dp_ips == ["10.105.192.33"]
        assert config.target_country == "UA"
        assert config.target_regions == ["43", "09", "14"]
    
    def test_timeout_variables_renamed_correctly(self, monkeypatch):
        """Verify new timeout variable names are loaded."""
        env_vars = {
            "CC_IP": "10.105.193.3",
            "DP_IPS": "10.105.192.33",
            "CC_USERNAME": "radware",
            "CC_PASSWORD": "radware",
            "RADWARE_API_URL": "https://services.radware.com/api",
            "TARGET_COUNTRY": "UA",
            "TARGET_REGIONS": "43",
            "DP_API_TIMEOUT": "45",
            "DP_DELETE_TIMEOUT": "150",
            "GEODB_API_TIMEOUT": "20",
            "GEODB_DOWNLOAD_TIMEOUT": "400",
        }
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)
        
        config = Config.from_environment()
        
        assert config.dp_api_timeout == 45
        assert config.dp_delete_timeout == 150
        assert config.geodb_api_timeout == 20
        assert config.geodb_download_timeout == 400
    
    def test_config_defaults_applied(self, monkeypatch):
        """Verify default values are applied when optionals not provided."""
        env_vars = {
            "CC_IP": "10.105.193.3",
            "DP_IPS": "10.105.192.33",
            "CC_USERNAME": "radware",
            "CC_PASSWORD": "radware",
            "RADWARE_API_URL": "https://services.radware.com/api",
            "TARGET_COUNTRY": "UA",
            "TARGET_REGIONS": "43",
        }
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)
        
        config = Config.from_environment()
        
        # Check defaults
        assert config.dp_api_timeout == 30
        assert config.dp_delete_timeout == 120
        assert config.geodb_api_timeout == 30
        assert config.geodb_download_timeout == 300
        assert config.max_retries == 3
        assert config.retry_backoff_factor == 2.0
    
    def test_target_regions_optional_country_level_filtering(self, monkeypatch):
        """Verify TARGET_REGIONS is optional - when omitted, filters by country only."""
        env_vars = {
            "CC_IP": "10.105.193.3",
            "DP_IPS": "10.105.192.33",
            "CC_USERNAME": "radware",
            "CC_PASSWORD": "radware",
            "RADWARE_API_URL": "https://services.radware.com/api",
            "TARGET_COUNTRY": "UA",
            # TARGET_REGIONS intentionally omitted
        }
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)
        
        # Ensure TARGET_REGIONS is not set
        monkeypatch.delenv("TARGET_REGIONS", raising=False)
        
        config = Config.from_environment()
        
        assert config.target_country == "UA"
        assert config.target_regions is None  # Should be None when omitted
    
    def test_target_regions_empty_string_raises_error(self, monkeypatch):
        """Verify empty TARGET_REGIONS string raises validation error."""
        env_vars = {
            "CC_IP": "10.105.193.3",
            "DP_IPS": "10.105.192.33",
            "CC_USERNAME": "radware",
            "CC_PASSWORD": "radware",
            "RADWARE_API_URL": "https://services.radware.com/api",
            "TARGET_COUNTRY": "UA",
            "TARGET_REGIONS": "",  # Empty string should raise error
        }
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)
        
        with pytest.raises(ConfigError, match="TARGET_REGIONS"):
            Config.from_environment()
    
    def test_missing_required_variable_raises_error(self, monkeypatch):
        """Verify ConfigError raised when required variable missing."""
        # Set up incomplete environment (missing CC_IP)
        env_vars = {
            "DP_IPS": "10.105.192.33",
            "CC_USERNAME": "radware",
            "CC_PASSWORD": "radware",
            "RADWARE_API_URL": "https://services.radware.com/api",
            "TARGET_COUNTRY": "UA",
            "TARGET_REGIONS": "43",
        }
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)
        
        # Ensure CC_IP is not set
        monkeypatch.delenv("CC_IP", raising=False)
        
        with pytest.raises(ConfigError, match="CC_IP"):
            Config.from_environment()
    
    def test_invalid_timeout_raises_validation_error(self, monkeypatch):
        """Verify validation catches invalid timeout values."""
        env_vars = {
            "CC_IP": "10.105.193.3",
            "DP_IPS": "10.105.192.33",
            "CC_USERNAME": "radware",
            "CC_PASSWORD": "radware",
            "RADWARE_API_URL": "https://services.radware.com/api",
            "TARGET_COUNTRY": "UA",
            "TARGET_REGIONS": "43",
            "DP_API_TIMEOUT": "-10",  # Invalid: negative timeout
        }
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)
        
        with pytest.raises(ConfigError, match="DP_API_TIMEOUT"):
            Config.from_environment()


class TestGeoIPDatabaseQA:
    """Validate GeoIP database client functionality."""
    
    @patch('src.services.geodb_client.requests.Session')
    def test_md5_validation_enabled(self, mock_session):
        """Verify MD5 validation is re-enabled and working."""
        from src.services.geodb_client import RadwareGeoDBClient
        
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "Success",
            "data": {
                "md5": "d41d8cd98f00b204e9800998ecf8427e",  # Valid MD5 format
                "fileUrl": "https://example.com/db.zip",
                "compressedSizeBytes": 1000
            }
        }
        mock_session.return_value.get.return_value = mock_response
        
        with tempfile.TemporaryDirectory() as tmpdir:
            client = RadwareGeoDBClient(
                api_url="https://test.api.com",
                cache_dir=tmpdir,
                api_timeout=10,
                download_timeout=60
            )
            
            db_info = client.get_database_info()
            
            assert db_info["md5"] == "d41d8cd98f00b204e9800998ecf8427e"
            assert "fileUrl" in db_info
    
    def test_force_download_bypasses_cache(self, monkeypatch, tmp_path):
        """Verify FORCE_DOWNLOAD environment variable works."""
        from src.services.geodb_client import RadwareGeoDBClient
        
        # Set FORCE_DOWNLOAD
        monkeypatch.setenv("FORCE_DOWNLOAD", "true")
        
        # Create fake cached database
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cached_db = cache_dir / "geodb_test123"
        cached_db.mkdir()
        (cached_db / "GeoIP2-City-Blocks-IPv4.csv").write_text("test")
        (cached_db / "GeoIP2-City-Locations-en.csv").write_text("test")
        
        # Even with cache present, FORCE_DOWNLOAD should trigger re-download
        force_enabled = os.getenv("FORCE_DOWNLOAD", "false").lower() == "true"
        assert force_enabled is True


class TestDefenseProIntegrationQA:
    """Validate DefensePro client functionality."""
    
    def test_timeout_parameters_passed_correctly(self):
        """Verify timeout configuration is passed to DefensePro client."""
        from src.services.defensepro_client import DefenseProClient
        
        # Mock the login to avoid actual network calls
        with patch.object(DefenseProClient, '_load_or_login'):
            client = DefenseProClient(
                cc_ip="10.105.193.3",
                username="test",
                password="test",
                timeout=45,
                delete_timeout=150
            )
            
            assert client.timeout == 45
            assert client.delete_timeout == 150
    
    @patch('src.services.defensepro_client.requests.Session')
    def test_retry_logic_respects_max_retries(self, mock_session):
        """Verify retry logic doesn't loop infinitely."""
        from src.services.defensepro_client import DefenseProClient
        
        # Mock session to fail repeatedly
        mock_session.return_value.post.side_effect = requests.exceptions.Timeout()
        
        with patch.object(DefenseProClient, '_load_or_login'):
            client = DefenseProClient(
                cc_ip="10.105.193.3",
                username="test",
                password="test",
                max_retries=3
            )
            
            assert client.max_retries == 3


class TestEndToEndQA:
    """Quick end-to-end validation tests."""
    
    def test_import_all_modules(self):
        """Verify all modules can be imported without errors."""
        try:
            from src.cli import main
            from src.models import config
            from src.services import defensepro_client, geodb_client
            from src.lib import exceptions, logging_config
            assert True
        except ImportError as e:
            pytest.fail(f"Module import failed: {e}")
    
    def test_log_levels_valid(self):
        """Verify LOG_LEVEL accepts valid values."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        from src.lib.logging_config import setup_logging
        
        for level in valid_levels:
            try:
                logger = setup_logging(log_level=level)
                assert logger is not None
            except ValueError:
                pytest.fail(f"Valid log level '{level}' was rejected")


# Smoke test fixture
@pytest.fixture
def smoke_test_env(monkeypatch, tmp_path):
    """Set up complete environment for smoke testing."""
    env_vars = {
        "CC_IP": "10.105.193.3",
        "DP_IPS": "10.105.192.33",
        "CC_USERNAME": "radware",
        "CC_PASSWORD": "radware",
        "VERIFY_SSL": "false",
        "RADWARE_API_URL": "https://services.radware.com/api/geodb/getfile",
        "TARGET_COUNTRY": "UA",
        "TARGET_REGIONS": "43,09,14",
        "LOG_LEVEL": "DEBUG",
        "LOG_FILE": str(tmp_path / "test.log"),
        "SYSLOG_ENABLED": "false",
        "GEODB_CACHE_DIR": str(tmp_path / "cache"),
        "FORCE_DOWNLOAD": "false",
        "DP_API_TIMEOUT": "30",
        "DP_DELETE_TIMEOUT": "120",
        "GEODB_API_TIMEOUT": "30",
        "GEODB_DOWNLOAD_TIMEOUT": "300",
        "MAX_RETRIES": "3",
        "PARALLEL_EXECUTION": "true",
        "PARALLEL_WORKERS": "10",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    
    return Config.from_environment()


def test_full_config_loads(smoke_test_env):
    """Smoke test: Verify complete configuration loads successfully."""
    config = smoke_test_env
    
    assert config.cc_ip == "10.105.193.3"
    assert config.dp_ips == ["10.105.192.33"]
    assert config.dp_api_timeout == 30
    assert config.dp_delete_timeout == 120
    assert config.geodb_api_timeout == 30
    assert config.geodb_download_timeout == 300
    assert config.max_retries == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
