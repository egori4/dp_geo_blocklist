# GeoIP Custom IP Blocker

A containerized Python application that identifies defined IPv4 network ranges for specific geographic regions and synchronizes them with a custom feed REST API.

## 🎯 Overview

This security-focused application automatically:
- Downloads and processes Radware GeoIP database
- Identifies IPv4 network ranges for Ukraine and Russia occupied territories 
- Synchronizes changes via delta-based API calls to minimize bandwidth
- Provides comprehensive audit trails and monitoring
- Runs as a stateless container with external scheduling

## 📋 Features

- **Automated GeoIP Processing**: Downloads, validates, and extracts ~100 network ranges from Radware database
- **Delta Synchronization**: Only sends changes (additions/removals) to API, not full lists
- **Secure Deployment**: Environment-based configuration, non-root container execution
- **Comprehensive Logging**: Structured logging with syslog integration and audit trails
- **Production Ready**: Complete installation automation, error handling, and monitoring

## 🏗️ Architecture

### Core Components

```
src/
├── models/          # Data structures (GeoLocation, NetworkRange, AppState)
├── services/        # Business logic (API clients, CSV processing, state management)
├── cli/             # Entry point and workflow orchestration
└── lib/             # Shared utilities (logging, validation, exceptions)

tests/
├── contract/        # API contract tests
├── integration/     # End-to-end workflow tests  
└── unit/            # Component unit tests
```

### Data Flow

1. **Fetch** → Download GeoIP database from Radware API with MD5 validation
2. **Process** → Extract and correlate CSV data to identify target network ranges
3. **Calculate** → Compare with previous state to determine delta changes
4. **Synchronize** → Send only additions/removals to custom feed API
5. **Persist** → Update state and append to audit log
6. **Monitor** → Log operations to file and syslog for observability

## 🚀 Quick Start

### Prerequisites

- Docker installed
- Sudo privileges for installation
- Network access to Radware and custom feed APIs

### Installation

```bash
# Clone repository
git clone <repository-url>
cd geo-ip-custom-block

# Run automated installation
sudo ./install.sh

# Configure environment variables
cp .env.example .env
nano .env  # Edit with your API credentials and settings
```

### Configuration

Required environment variables in `.env`:

```bash
# API Configuration
API_HOST=192.168.1.100
API_PORT=8443
API_USERNAME=admin 
API_PASSWORD=secret123

# Radware GeoIP Source
RADWARE_API_URL=https://services.radware.com/api/geodb/getfile

# Target Regions (Ukraine, occupied territories)
TARGET_COUNTRY=UA
TARGET_REGIONS=43,09,14

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/ip-blocker.log
SYSLOG_ENABLED=true
SYSLOG_HOST=localhost
SYSLOG_PORT=514

# Storage Paths
STATE_FILE=/app/data/ip_state.json
HISTORY_FILE=/app/data/ip_history.jsonl
GEODB_CACHE_DIR=/app/data/geodb_cache

# Optional: Dry-Run / Step Control (all default to 'true')
ENABLE_GEODB_DOWNLOAD=true          # Download fresh database from Radware
ENABLE_NETWORK_SUMMARIZATION=true   # Aggregate networks (760 → 87 networks)
CONFIGURE_DEFENSEPRO=true           # Push to DefensePro devices
```

### Dry-Run Mode

Control workflow execution for testing and validation:

```bash
# Dry-run: Extract data only, no DefensePro push
CONFIGURE_DEFENSEPRO=false

# Test with cached data (no download)
ENABLE_GEODB_DOWNLOAD=false

# Use original networks without summarization
ENABLE_NETWORK_SUMMARIZATION=false

# Full dry-run: Extract and validate data only
ENABLE_GEODB_DOWNLOAD=true
ENABLE_NETWORK_SUMMARIZATION=false
CONFIGURE_DEFENSEPRO=false
```

**Use Cases:**
- **Data Validation**: Review extracted networks in CSV files before pushing
- **Summarization Testing**: Compare original vs. summarized networks
- **Offline Testing**: Work with cached data without API calls
- **Controlled Rollout**: Validate configuration on test devices first

### Execution

```bash
# Manual execution (for testing)
docker start geo-ip-blocker

# Scheduled execution (recommended)
# Add to crontab for weekly runs:
0 2 * * 0 docker start geo-ip-blocker
```

## 📊 Monitoring

### Log Locations

- **Container logs**: `docker logs geo-ip-blocker`
- **Application logs**: `/var/log/ip-blocker.log`
- **Audit trail**: `/opt/radware/storage/scripts/geo-ip-custom-block/app/ip_history.jsonl`
- **State file**: `/opt/radware/storage/scripts/geo-ip-custom-block/app/ip_state.json`

### Success Indicators

- Exit code 0 (success) or 1 (failure)
- ~100 network ranges identified for target regions
- Delta operations logged (additions/removals)
- Syslog messages for operational events

## 🔧 Development

### Setup Development Environment

```bash
# Install dependencies
pip install -r requirements.txt

# Install development tools
pip install pytest flake8 black mypy

# Run tests
pytest tests/

# Run linting
flake8 src/
black src/
mypy src/
```

### Running Tests

```bash
# Unit tests
pytest tests/unit/

# Integration tests (requires Docker)
pytest tests/integration/

# Contract tests (requires API access)
pytest tests/contract/
```

## 🛡️ Security

- **Credentials**: Stored in environment variables only, never hardcoded
- **Input Validation**: All external data (API responses, CSV files) validated
- **Container Security**: Runs as non-root user with minimal privileges
- **Network Security**: SSL certificate validation, timeout configurations
- **Audit Trail**: Complete history of all IP operations with timestamps

## 📚 Documentation

- [Feature Specification](specs/001-geolocation-ip-blocker/spec.md) - Requirements and user stories
- [Implementation Plan](specs/001-geolocation-ip-blocker/plan.md) - Technical architecture
- [Task Breakdown](specs/001-geolocation-ip-blocker/tasks.md) - Development roadmap

## 🔄 Deployment

### Container Model

- **Stateless**: No internal state, all persistence via mounted volumes
- **Single Execution**: Runs once per trigger, then exits cleanly
- **External Scheduling**: Triggered by cron or orchestration system
- **Volume Mounts**: `/opt/radware/storage/scripts/geo-ip-custom-block/app` for data

### Uninstallation

```bash
# Complete removal (prompts for data retention)
sudo ./uninstall.sh
```

## 📈 Performance

- **Memory Usage**: <512MB during normal operations
- **Processing Time**: <5 minutes for full GeoIP database processing
- **Storage**: ~1GB for cached GeoIP data and logs
- **Network**: Delta sync reduces API calls by >90% on subsequent runs

## 🚨 Troubleshooting

### Common Issues

1. **Network Errors**: Check connectivity to Radware and custom feed APIs
2. **Permission Errors**: Ensure proper volume mount permissions
3. **Configuration Errors**: Validate all required environment variables
4. **CSV Processing**: Check for corrupted or unexpected data formats

### Debug Mode

```bash
# Enable debug logging
echo "LOG_LEVEL=DEBUG" >> .env
docker start geo-ip-blocker
```

## 🤝 Contributing

1. Follow the established [Constitution](\.specify\memory\constitution.md) principles
2. Maintain test coverage for all new functionality
3. Use structured commits following conventional commit format
4. Ensure all constitutional compliance checks pass

## 📄 License

[Add appropriate license information]

---

## 📝 Version History

### Version 1.2.0 (2025-11-11) - Enhancements & Configuration Reorganization

**Enhancements:**
- **MD5 Validation**: Added validation of MD5 between the downloaded db and declared MD5 from the endpoint
- **Caching**: Added condition - if MD5 of the new db matches last downloaded db, exit early
- **Policy Update Integration**: Added policy update after network class and blocklist creation
- **Workflow Optimization**: Reorganized processing order - summarization now occurs after GeoIP filtering

**Configuration:**
- **Timeout Variables**: Reorganized with clear prefixes:
  - `DP_API_TIMEOUT=30` - DefensePro CyberController API operations
  - `DP_DELETE_TIMEOUT=120` - DefensePro bulk delete operations (250 networks)
  - `GEODB_API_TIMEOUT=30` - Radware GeoIP API metadata requests
  - `GEODB_DOWNLOAD_TIMEOUT=300` - GeoIP database ZIP download (~78MB)

- **Network Class Limits**: Added configurable network class capacity:
  - `MAX_NETWORKS_PER_CLASS=256` - Maximum networks per DefensePro class (range: 1-256)

**New Features:**
- **Workflow Control Flags**: Four configurable flags for controlled execution:
  - `ENABLE_GEODB_DOWNLOAD` (true/false): Control GeoIP database download vs. using cache
  - `FILTER_TARGET_REGIONS` (true/false): Filter target regions or use cached CSV from previous run
  - `ENABLE_NETWORK_SUMMARIZATION` (true/false): Toggle network aggregation (760 → 560 networks)
  - `CONFIGURE_DEFENSEPRO` (true/false): Enable/disable DefensePro device configuration


**Bug Fixes:**
- **Rollback Recovery**: Fixed transaction rollback handling to properly detect and recover from M_00386 errors
  - Extended retry loop by 2 attempts for rollback verification
  - Added `had_transaction_rollback` flag persistence across retry attempts
  - Improved logging to distinguish rollback recovery from genuine failures
  
- **Network Index Validation**: Fixed ValidationError calls throughout codebase
  - Corrected parameter from `expected_type` to `value` per exception signature
  - Updated validation to use dynamic `MAX_NETWORKS_PER_CLASS` instead of hardcoded limits

- **Double Summarization**: Eliminated duplicate summarization execution
  - Network summarization now runs once instead of twice
  - Improved performance and log clarity




### Version 1.1.0 (2025-11-10) - Performance & Reliability Update

**Major Enhancements:**
- **Parallel Network Creation**: upto 10x times performance improvement with configurable ThreadPoolExecutor (default: 10 workers)
- **Bulk Deletion API**: Reduced cleanup time from N API calls to 1 per network class
- **Transaction Rollback Recovery**: Automatic detection and recovery from DefensePro transaction errors
- **Original Network Export**: Added `original_network_ranges.csv` for pre-summarization audit trail

**Bug Fixes:**
- Fixed infinite retry loop respecting MAX_RETRIES=3
- Fixed M_00386 error handling to differentiate rollback recovery vs. genuine duplicates
- Fixed per-device cleanup error handling to skip only failed devices
- Fixed DELETE operation timeout (30s → 120s for 250-network bulk deletions)

**Configuration:**
- Added `DELETE_TIMEOUT=120` for bulk operations(deleting networks on DefensePro)
- Added `PARALLEL_EXECUTION=true/false` to toggle execution modes
- Added `PARALLEL_WORKERS=10` (range: 1-50) for concurrency control

**Technical Details:**
- Retry logic enhanced with transaction state tracking (`had_transaction_rollback` flag)
- Per-class and overall timing measurements with networks/sec metrics
- Comprehensive DEBUG logging for troubleshooting bulk operations

---

**Version**: 1.0.0 | **Created**: 2025-10-15 |