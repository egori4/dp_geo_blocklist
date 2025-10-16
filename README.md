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
```

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

**Version**: 1.0.0 | **Created**: 2025-10-15 | **Status**: Implementation Ready