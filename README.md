# GeoIP Custom IP Blocker

A containerized Python application that identifies defined IPv4 network ranges for specific geographic regions and synchronizes them with a custom feed REST API.

## 🎯 Overview

This security-focused application automatically:
- Downloads and processes Radware GeoIP database with MD5 validation
- Identifies IPv4 network ranges for user defined criteria Countries/Cities/Regions
- Aggregates networks intelligently (example 760 → 566 networks, 25.5% reduction)
- Configures BlockLists on DefensePro devices via CyberController API
- Provides comprehensive audit trails and monitoring
- Runs as a stateless container with external scheduling

## 📋 Features

- **Automated GeoIP Processing**: Downloads, validates, and extracts ~760 network ranges from Radware database
- **Network Summarization**: Intelligent CIDR aggregation reduces networks while maintaining exact coverage
- **Query-First Cleanup**: Discovers and removes existing configurations before creating new ones (overwrite)
- **Configurable Workflow**: Four control flags for flexible execution (download, filter, summarize, configure)
- **Parallel Execution**: Up to 10x faster network creation with configurable worker threads
- **Rollback Recovery**: Automatic detection and recovery from DefensePro transaction errors
- **Secure Deployment**: Environment-based configuration, non-root container execution
- **Comprehensive Logging**: Structured logging with DEBUG level support, syslog integration, and audit trails
- **Production Ready**: Complete Docker containerization, error handling, and monitoring

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
2. **Extract** → Unpack nested archives and extract CSV files (blocks_ipv4, locations)
3. **Filter** → Identify network ranges for target regions
4. **Summarize** → Intelligently aggregate networks using CIDR consolidation (optional, 25.5% reduction)
5. **Cleanup** → Query and remove existing DefensePro configurations (query-first approach)
6. **Synchronize** → Create network classes and blocklists on DefensePro devices
7. **Apply** → Update DefensePro policies to activate new configurations
8. **Monitor** → Log operations to file and syslog for observability

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
# DefensePro Configuration
CC_IP=127.0.0.1                     # CyberController IP address
DP_IPS=10.105.192.33,10.105.192.34  # Comma-separated DefensePro device IPs
CC_USERNAME=radware                  # CyberController username
CC_PASSWORD=radware                  # CyberController password
VERIFY_SSL=false                     # SSL verification (typically false for self-signed certs)

# Radware GeoIP Source
RADWARE_API_URL=https://services.radware.com/api/geodb/getfile

# Target Regions
TARGET_COUNTRY=UA
TARGET_REGIONS=43,09,14              # Optional: Specific subdivisions (comment for all subdivisions) !!! Warning, setting target regions to only country without regions may result in a number of networks that is too high to be configured on DefensePro.

# Logging
LOG_LEVEL=INFO
LOG_FILE=./tmp/geo-ip-blocker.log
SYSLOG_ENABLED=true
SYSLOG_HOST=localhost
SYSLOG_PORT=514

# Storage Paths
GEODB_CACHE_DIR=./tmp/geodb_cache

# Cache Management
CACHE_RETENTION_COUNT=3             # Number of cached database versions to keep (~230MB each)

# Optional: Step Control
ENABLE_GEODB_DOWNLOAD=true          # Download fresh database from Radware
FILTER_TARGET_REGIONS=true          # Filter by target regions or use cached CSV
ENABLE_NETWORK_SUMMARIZATION=true   # Aggregate networks (example 760 → 566 networks)
CONFIGURE_DEFENSEPRO=true           # Configure Blocklists on DefensePro

# Optional: DefensePro Update Mode (v1.4.0+)
CONFIGURE_DEFENSEPRO_MODE=OVERWRITE # OVERWRITE (default) or MERGE
                                    # OVERWRITE: Delete all, create fresh (backward compatible)
                                    # MERGE: Incremental updates only (no blocking gap)

# Optional: Force fresh download (testing)
FORCE_DOWNLOAD=false                # Bypass cache even if MD5 matches

# Optional: Timeout Configuration (seconds)
DP_API_TIMEOUT=30                   # DefensePro API operations
DP_DELETE_TIMEOUT=120               # DefensePro bulk delete operations
GEODB_API_TIMEOUT=30                # GeoIP API metadata requests
GEODB_DOWNLOAD_TIMEOUT=300          # GeoIP database download (~78MB)

# Optional: Retry Configuration
MAX_RETRIES=3
RETRY_BACKOFF_FACTOR=2

# Optional: Network Class Configuration
MAX_NETWORKS_PER_CLASS=256          # Maximum networks per class (1-256, default: 250)

# Optional: Parallel Execution Configuration
PARALLEL_EXECUTION=true             # Enable parallel network creation
PARALLEL_WORKERS=10                 # Number of concurrent workers (1-50)
```

### Dry-Run Mode

Control workflow execution for testing and validation using four configurable flags:

```bash
# Dry-run: Extract data only, no DefensePro push
CONFIGURE_DEFENSEPRO=false

# Test with cached GeoIP data (no download)
ENABLE_GEODB_DOWNLOAD=false

# Test with pre-exported CSV (skip region filtering)
FILTER_TARGET_REGIONS=false

# Use original networks without summarization
ENABLE_NETWORK_SUMMARIZATION=false

# Full dry-run: Extract and validate data only
ENABLE_GEODB_DOWNLOAD=true
FILTER_TARGET_REGIONS=true
ENABLE_NETWORK_SUMMARIZATION=false
CONFIGURE_DEFENSEPRO=false

# Force fresh download even if cache MD5 matches (testing)
FORCE_DOWNLOAD=true
```

**Use Cases:**
- **Data Validation**: Review extracted networks in CSV files before pushing
- **Summarization Testing**: Compare original vs. summarized networks  
- **Offline Development**: Work with cached data without API connectivity
- **Controlled Rollout**: Validate configuration on test devices first
- **Development Testing**: Force fresh downloads to test API integration

### Update Modes (v1.4.0+)

Choose between full overwrite or incremental updates for DefensePro configuration:

#### OVERWRITE Mode (Default)
```bash
CONFIGURE_DEFENSEPRO_MODE=OVERWRITE
```

**Behavior:**
- Deletes all existing `user_defined_feed_*` blocklists and network classes
- Creates fresh configuration from scratch
- Brief blocking gap during delete/recreate cycle

**Best For:**
- Initial setup and first-time deployment
- Major configuration changes (switching countries/regions)
- Troubleshooting configuration issues
- Ensuring clean state

#### MERGE Mode (Recommended for Scheduled Runs)
```bash
CONFIGURE_DEFENSEPRO_MODE=MERGE
```

**Behavior:**
- **No Blocking Gap**: Networks stay blocked during entire update process
- **Incremental Changes**: Only modifies networks that changed (additions/deletions)
- **Gap Filling**: Reuses freed subindexes before creating new classes
- **Smart Cleanup**: Automatically deletes empty classes and unused blocklists
- **Faster Updates**: Minutes vs. full recreation for small changes

**Best For:**
- Scheduled weekly/daily runs (cron jobs)
- Minimal network changes between updates
- Production environments requiring continuous protection
- Efficient resource utilization

**MERGE Mode Workflow:**
1. Query existing DefensePro configuration
2. Calculate diff (networks to add/delete)
3. Delete removed networks (selective, preserves others)
4. Add new networks (fills gaps in existing classes first)
5. Clean up empty classes and blocklists
6. Update policy once at end

**Comparison:**

| Aspect | OVERWRITE | MERGE |
|--------|-----------|-------|
| **Blocking Gap** | Yes (~seconds) | No |
| **Update Time** | Full recreation | Incremental (faster) |
| **Network Changes** | All replaced | Only changed |
| **Gap Management** | Creates new classes | Fills existing gaps |
| **Best Use Case** | Initial setup | Regular updates |

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
- **Application logs**: `./tmp/geo-ip-blocker.log` (or configured LOG_FILE path)
- **CSV Exports**:
  - `data/original_network_ranges.csv` - Networks after filtering, before summarization
  - `data/summarized_network_ranges.csv` - Networks after CIDR aggregation(if ENABLE_NETWORK_SUMMARIZATION is set to true)

### Success Indicators

- Exit code 0 (success) or 1 (failure)
- Network ranges identified for target regions
- Summarized networks shows reduction via aggregation
- Network classes created
- All blocklists created successfully
- Policy updates applied to all DefensePro devices
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
- [Implementation Summary](IMPLEMENTATION_SUMMARY.md) - Technical changes and architecture
- [Dry-Run Guide](docs/DRY_RUN_GUIDE.md) - Workflow control configuration
- [Task Breakdown](specs/001-geolocation-ip-blocker/tasks.md) - Development roadmap

## 🔄 Deployment

### Container Model

- **Stateless**: No internal state, all persistence via mounted volumes
- **Single Execution**: Runs once per trigger, then exits cleanly
- **External Scheduling**: Triggered by cron or orchestration system
- **Volume Mounts**: 
  - `./data:/app/data` - CSV exports and cached database
  - `./tmp:/app/tmp` - Logs, state files, extracted GeoIP files

### Uninstallation

```bash
# Complete removal (prompts for data retention)
sudo ./uninstall.sh
```

## 📈 Performance

- **Memory Usage**: <512MB during normal operations (Docker container)
- **Processing Time**: 
  - GeoIP download & extraction: ~10 seconds
  - Network filtering & summarization: <5 seconds
  - DefensePro configuration (1 device, 566 networks): ~34 seconds
  - Total execution: <2 minutes
- **Throughput**: 16.6 networks/sec (parallel mode with 10 workers)
- **Storage**: ~230MB for cached GeoIP CSV files


## 🚨 Troubleshooting



### Debug Mode

```bash
# Enable debug logging
LOG_LEVEL=DEBUG

# Test with single device
DP_IPS=10.105.192.33

# Force fresh download
FORCE_DOWNLOAD=true

# Run container
docker run --rm --env-file .env -v "$(pwd)/data:/app/data" -v "$(pwd)/tmp:/app/tmp" geo-ip-blocker
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

### Version 1.4.0 (2025-11-18) - New features, Enhancments

**Major Features:**
- **MERGE Mode**: Incremental DefensePro configuration updates without blocking gaps
  - Only modifies changed networks (additions/deletions) instead of full overwrite
  - Networks remain blocked during updates - no temporary permit window
  - Intelligent gap filling - reuses freed subindexes before creating new classes
  - Automatic empty class cleanup - deletes unused classes and blocklists
  - Configuration: `CONFIGURE_DEFENSEPRO_MODE=MERGE` or `OVERWRITE` (default)
  - Reduces update time for small changes (minutes vs. full recreation)

- **Audit networks change**: Added summary logging of additions/deletions to data/changes_log.csv

**New Components:**
- **State Management**: `DefenseProStateManager` - Query existing DefensePro configuration
  - Tracks all blocklists, network classes, occupied subindexes
  - Calculates optimal placement for new networks (fill gaps first)
  - Identifies freed subindexes for reuse
- **Diff Calculator**: `NetworkDiffCalculator` - Identify configuration changes
  - Compares incoming networks vs. existing configuration
  - Groups additions, deletions, and unchanged networks
  - Optimizes deletion operations by class grouping
- **MERGE Orchestrator**: `MergeStrategyManager` - Complete workflow automation
  - Query → Diff → Delete → Add → Policy Update
  - Parallel execution support (respects `PARALLEL_EXECUTION` setting)
  - Per-device error handling with detailed statistics
  - Comprehensive logging with operation summaries

**Enhancements:**
- **Packaging & Installation:** Added `install.sh` and `uninstall.sh` scripts for automated setup and removal
    - Simplifies Docker image build, environment configuration, and volume mounting
    - Prompts for data retention during uninstallation
- **Enhanced logic of adding networks:** 
    - Fill gaps in the first class (keeps networks contiguous)
      Then class 2, class 3, etc.
      Only use last class after previous classes are full
      If the last class is over MAX_NETWORKS_PER_CLASS, create a new class
  
- **Documentation:** Updated README with installation, uninstallation, and quick start instructions
    - Expanded configuration section with environment variable explanations
    - Clarified cache management and dry-run workflow
- **Containerization:** Improved Dockerfile for stateless execution and non-root user security
    - Ensures all persistence is via mounted volumes (`./data`, `./tmp`)
    - Supports external scheduling (cron, orchestrators)
- **Release Process:** Added versioning and changelog structure for future releases

**Configuration:**
- **MERGE Mode Control**: New environment variable for update strategy:
  - `CONFIGURE_DEFENSEPRO_MODE=OVERWRITE` - Delete all, create fresh (default, backward compatible)
  - `CONFIGURE_DEFENSEPRO_MODE=MERGE` - Incremental updates only (recommended for scheduled runs)
- **Mode Comparison**:
  - OVERWRITE: Brief blocking gap during delete/recreate, best for initial setup or major changes
  - MERGE: No blocking gap, faster updates, fills configuration gaps, best for regular maintenance



### Version 1.3.0 (2025-11-12) - Cache Management & Configuration Enhancements

**Enhancements:**
- **Automatic Cache Cleanup**: Intelligent cache retention management with configurable history
  - Keeps N most recent GeoIP database versions (default: 3)
  - Each cached version ~230MB (locations.csv + blocks_ipv4.csv)
  - Automatic cleanup in `finally` block ensures consistent execution across all code paths
  - Cleanup occurs after database processing but before region filtering
- **Optional TARGET_REGIONS**: Simplified configuration for country-wide operations
  - `TARGET_REGIONS` now optional - omit to include ALL subdivisions for `TARGET_COUNTRY`
  - When specified, filters to specific subdivision ISO codes (e.g., 43,09,14 for Ukraine occupied territories)
  - Reduces configuration complexity for non-subdivision-specific use cases

**Configuration:**
- **Cache Management**: New environment variable for retention control:
  - `CACHE_RETENTION_COUNT=3` - Number of cached database versions to keep (default: 3, minimum: 1)
  - Total cache size: ~690MB with default retention of 3 versions
  - Use `CACHE_RETENTION_COUNT=1` for minimal storage, 5+ for extended history
- **TARGET_REGIONS**: Changed from required to optional
  - When omitted: Includes all subdivisions for specified `TARGET_COUNTRY`
  - When specified: Filters to comma-separated subdivision codes only
  - Example: `TARGET_REGIONS=43,09,14` (Crimea, Donetsk, Luhansk in Ukraine)

**Bug Fixes:**
- **Cache Directory Discovery**: Fixed cached database lookup when `ENABLE_GEODB_DOWNLOAD=false`
  - Previously searched for CSV files in cache root directory
  - Now correctly searches for `geodb_*` subdirectories with MD5-hashed names
  - Uses most recent cache directory by modification time
  - Validates presence of both `locations.csv` and `blocks_ipv4.csv`
  
- **Duplicate Cache Cleanup**: Eliminated redundant cleanup calls
  - Removed 3 duplicate cleanup operations scattered across code paths
  - Consolidated to single cleanup in `finally` block for all execution scenarios
  - Ensures cleanup runs consistently regardless of success, failure, or early exit
  - Proper cleanup timing: after database processing, before region filtering

- **CSV Export Cleanup**: Removed unnecessary CSV export cleanup logic
  - CSV files (`original_network_ranges.csv`, `summarized_network_ranges.csv`) are overwritten each run
  - No accumulation occurs, so cleanup not needed
  - Simplified code and eliminated unnecessary file operations

**Documentation Updates:**
- Updated `.env` and `.env.example` with `CACHE_RETENTION_COUNT` configuration
- Updated README.md configuration section with cache management details
- Added `TARGET_REGIONS` optional behavior to all documentation
- Updated copilot-instructions.md with recent changes summary

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