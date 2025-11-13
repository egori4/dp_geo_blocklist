"""
Tests for dry-run / step control configuration options.

These tests verify that ENABLE_GEODB_DOWNLOAD, ENABLE_NETWORK_SUMMARIZATION,
CONFIGURE_DEFENSEPRO, and FILTER_TARGET_REGIONS configuration flags work correctly.
"""

import os
import pytest
from unittest.mock import patch

from src.models.config import Config


class TestDryRunConfiguration:
    """Test dry-run configuration flags."""
    
    def test_default_all_enabled(self):
        """Test that all flags default to True when not specified."""
        env_vars = {
            'CC_IP': '10.105.193.3',
            'DP_IPS': '10.105.192.33,10.105.192.34',
            'CC_USERNAME': 'radware',
            'CC_PASSWORD': 'radware',
            'RADWARE_API_URL': 'https://services.radware.com/api/geodb/getfile',
            'TARGET_COUNTRY': 'UA',
            'TARGET_REGIONS': '43,09,14'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_environment()
            
            # All flags should default to True
            assert config.enable_geodb_download is True
            assert config.enable_network_summarization is True
            assert config.configure_defensepro is True
            assert config.filter_target_regions is True
    
    def test_enable_geodb_download_false(self):
        """Test ENABLE_GEODB_DOWNLOAD=false disables download."""
        env_vars = {
            'CC_IP': '10.105.193.3',
            'DP_IPS': '10.105.192.33',
            'CC_USERNAME': 'radware',
            'CC_PASSWORD': 'radware',
            'RADWARE_API_URL': 'https://services.radware.com/api/geodb/getfile',
            'TARGET_COUNTRY': 'UA',
            'TARGET_REGIONS': '43,09,14',
            'ENABLE_GEODB_DOWNLOAD': 'false'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_environment()
            
            assert config.enable_geodb_download is False
            assert config.enable_network_summarization is True  # Others still enabled
            assert config.configure_defensepro is True
    
    def test_enable_network_summarization_false(self):
        """Test ENABLE_NETWORK_SUMMARIZATION=false disables summarization."""
        env_vars = {
            'CC_IP': '10.105.193.3',
            'DP_IPS': '10.105.192.33',
            'CC_USERNAME': 'radware',
            'CC_PASSWORD': 'radware',
            'RADWARE_API_URL': 'https://services.radware.com/api/geodb/getfile',
            'TARGET_COUNTRY': 'UA',
            'TARGET_REGIONS': '43,09,14',
            'ENABLE_NETWORK_SUMMARIZATION': 'false'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_environment()
            
            assert config.enable_geodb_download is True
            assert config.enable_network_summarization is False
            assert config.configure_defensepro is True
    
    def test_configure_defensepro_false(self):
        """Test CONFIGURE_DEFENSEPRO=false disables DefensePro configuration."""
        env_vars = {
            'CC_IP': '10.105.193.3',
            'DP_IPS': '10.105.192.33',
            'CC_USERNAME': 'radware',
            'CC_PASSWORD': 'radware',
            'RADWARE_API_URL': 'https://services.radware.com/api/geodb/getfile',
            'TARGET_COUNTRY': 'UA',
            'TARGET_REGIONS': '43,09,14',
            'CONFIGURE_DEFENSEPRO': 'false'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_environment()
            
            assert config.enable_geodb_download is True
            assert config.enable_network_summarization is True
            assert config.configure_defensepro is False
    
    def test_all_flags_disabled(self):
        """Test all dry-run flags can be disabled simultaneously."""
        env_vars = {
            'CC_IP': '10.105.193.3',
            'DP_IPS': '10.105.192.33',
            'CC_USERNAME': 'radware',
            'CC_PASSWORD': 'radware',
            'RADWARE_API_URL': 'https://services.radware.com/api/geodb/getfile',
            'TARGET_COUNTRY': 'UA',
            'TARGET_REGIONS': '43,09,14',
            'ENABLE_GEODB_DOWNLOAD': 'false',
            'ENABLE_NETWORK_SUMMARIZATION': 'false',
            'CONFIGURE_DEFENSEPRO': 'false'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_environment()
            
            assert config.enable_geodb_download is False
            assert config.enable_network_summarization is False
            assert config.configure_defensepro is False
    
    def test_boolean_parsing_variations(self):
        """Test various boolean string representations work correctly."""
        # Test 'true' variations
        for true_val in ['true', 'True', 'TRUE', '1', 'yes', 'Yes', 'YES', 'on', 'On', 'ON']:
            env_vars = {
                'CC_IP': '10.105.193.3',
                'DP_IPS': '10.105.192.33',
                'CC_USERNAME': 'radware',
                'CC_PASSWORD': 'radware',
                'RADWARE_API_URL': 'https://services.radware.com/api/geodb/getfile',
                'TARGET_COUNTRY': 'UA',
                'TARGET_REGIONS': '43,09,14',
                'ENABLE_GEODB_DOWNLOAD': true_val
            }
            
            with patch.dict(os.environ, env_vars, clear=True):
                config = Config.from_environment()
                assert config.enable_geodb_download is True, f"Failed for value: {true_val}"
        
        # Test 'false' variations
        for false_val in ['false', 'False', 'FALSE', '0', 'no', 'No', 'NO', 'off', 'Off', 'OFF']:
            env_vars = {
                'CC_IP': '10.105.193.3',
                'DP_IPS': '10.105.192.33',
                'CC_USERNAME': 'radware',
                'CC_PASSWORD': 'radware',
                'RADWARE_API_URL': 'https://services.radware.com/api/geodb/getfile',
                'TARGET_COUNTRY': 'UA',
                'TARGET_REGIONS': '43,09,14',
                'ENABLE_GEODB_DOWNLOAD': false_val
            }
            
            with patch.dict(os.environ, env_vars, clear=True):
                config = Config.from_environment()
                assert config.enable_geodb_download is False, f"Failed for value: {false_val}"
    
    def test_config_repr_includes_flags(self):
        """Test that __repr__ includes dry-run flags."""
        env_vars = {
            'CC_IP': '10.105.193.3',
            'DP_IPS': '10.105.192.33',
            'CC_USERNAME': 'radware',
            'CC_PASSWORD': 'radware',
            'RADWARE_API_URL': 'https://services.radware.com/api/geodb/getfile',
            'TARGET_COUNTRY': 'UA',
            'TARGET_REGIONS': '43,09,14',
            'ENABLE_GEODB_DOWNLOAD': 'false',
            'ENABLE_NETWORK_SUMMARIZATION': 'true',
            'CONFIGURE_DEFENSEPRO': 'false'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_environment()
            repr_str = repr(config)
            
            # Check that flags appear in repr
            assert 'geodb_download=False' in repr_str
            assert 'summarization=True' in repr_str
            assert 'configure_defensepro=False' in repr_str
    
    def test_filter_target_regions_false(self):
        """Test FILTER_TARGET_REGIONS=false disables region filtering."""
        env_vars = {
            'CC_IP': '10.105.193.3',
            'DP_IPS': '10.105.192.33',
            'CC_USERNAME': 'radware',
            'CC_PASSWORD': 'radware',
            'RADWARE_API_URL': 'https://services.radware.com/api/geodb/getfile',
            'TARGET_COUNTRY': 'UA',
            'TARGET_REGIONS': '43,09,14',
            'FILTER_TARGET_REGIONS': 'false'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_environment()
            
            assert config.filter_target_regions is False
            assert config.enable_geodb_download is True  # Others still enabled
            assert config.enable_network_summarization is True
            assert config.configure_defensepro is True
    
    def test_all_flags_including_filter_disabled(self):
        """Test all flags including FILTER_TARGET_REGIONS can be disabled."""
        env_vars = {
            'CC_IP': '10.105.193.3',
            'DP_IPS': '10.105.192.33',
            'CC_USERNAME': 'radware',
            'CC_PASSWORD': 'radware',
            'RADWARE_API_URL': 'https://services.radware.com/api/geodb/getfile',
            'TARGET_COUNTRY': 'UA',
            'TARGET_REGIONS': '43,09,14',
            'ENABLE_GEODB_DOWNLOAD': 'false',
            'ENABLE_NETWORK_SUMMARIZATION': 'false',
            'CONFIGURE_DEFENSEPRO': 'false',
            'FILTER_TARGET_REGIONS': 'false'
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_environment()
            
            assert config.enable_geodb_download is False
            assert config.enable_network_summarization is False
            assert config.configure_defensepro is False
            assert config.filter_target_regions is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

