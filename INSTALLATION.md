# GeoIP Custom IP Blocker - Installation Guide

## 📦 Package Contents

This installation package contains:

- `install.sh` - Installation script
- `uninstall.sh` - Uninstallation script
- `geo-ip-blocker-image.tar` - Docker image archive (~500MB)
- `.env.example` - Example configuration file
- `INSTALLATION.md` - This documentation file
- `README.md` - Full application documentation

## 🚀 Quick Start

### Prerequisites

- Docker installed and running
- Sudo/root access for installation
- 2GB free disk space for Docker image and data
- Network access to:
  - Docker Hub (egori4/geo-ip-custom-block) - optional, falls back to local archive
  - Radware GeoIP API (services.radware.com)
  - DefensePro CyberController

### Installation

```bash
# Extract the package
tar -xzf geo-ip-custom-block-v1.3.0.tar.gz
cd geo-ip-custom-block

# Make scripts executable
chmod +x install.sh uninstall.sh

# Run installation (prompts for configuration)
sudo ./install.sh
```

The installation script will:
1. ✓ Check Docker installation
2. ✓ Prompt for installation directory (default: /opt/radware/storage/scripts/geo-ip-custom-block/app)
3. ✓ Create directory structure with proper permissions
4. ✓ Try to pull Docker image from Docker Hub (egori4/geo-ip-custom-block:1.3.0)
5. ✓ Fall back to local archive if Docker Hub unavailable
6. ✓ Prompt for configuration values
7. ✓ Create and configure .env file
8. ✓ Create Docker container
9. ✓ Display usage instructions

### Configuration Prompts

During installation, you will be prompted for:

1. **Installation Directory**: Where to install the application
   - Default: `/opt/radware/storage/scripts/geo-ip-custom-block/app`
   - Can use custom path for testing (e.g., `~/geo-ip-blocker`)

2. **CyberController IP**: IP address of the CyberController
   - Example: `10.105.193.3`
   - Required

3. **DefensePro IPs**: Comma-separated list of DefensePro device IPs
   - Example: `10.105.192.33,10.105.192.34,10.105.192.35`
   - Required

4. **CyberController Username**: Username for CyberController API
   - Default: `radware`

5. **CyberController Password**: Password for CyberController API
   - Default: `radware`

6. **Target Country**: ISO country code for region filtering
   - Default: `UA` (Ukraine)

7. **Target Regions**: Subdivision ISO codes (optional)
   - Default: `43,09,14` (Crimea, Donetsk, Luhansk in Ukraine)
   - Leave empty to include ALL subdivisions
   - ⚠️ **WARNING**: Not setting regions may result in too many networks which could exceed DefensePro Blocklist rules limit.

## 🎯 Usage

### Manual Execution

```bash
# Start the container (one-time execution)
docker start geo-ip-blocker

# Watch logs in real-time
docker logs -f geo-ip-blocker

# View application log file
tail -f /opt/radware/storage/scripts/geo-ip-custom-block/app/tmp/geo-ip-blocker.log
```

### Scheduled Execution (Recommended)

```bash
# Add to crontab for weekly runs
crontab -e

# Run every Sunday at 2:00 AM
0 2 * * 0 docker start geo-ip-blocker
```

### Dry-Run Mode (Testing)

Before configuring DefensePro devices, test the data extraction:

```bash
# Edit configuration
nano /opt/radware/storage/scripts/geo-ip-custom-block/app/.env

# Set dry-run mode
CONFIGURE_DEFENSEPRO=false

# Recreate container with new config
docker rm geo-ip-blocker
cd /opt/radware/storage/scripts/geo-ip-custom-block/app
docker create --name geo-ip-blocker \
  --env-file .env \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/tmp:/app/tmp" \
  --restart unless-stopped \
  egori4/geo-ip-custom-block:1.3.0

# Run and check results
docker start geo-ip-blocker
docker logs geo-ip-blocker

# Review extracted networks
cat data/original_network_ranges.csv
cat data/summarized_network_ranges.csv
```

## 📊 Monitoring

### Check Container Status

```bash
# View container status
docker ps -a --filter name=geo-ip-blocker

# View container logs
docker logs geo-ip-blocker

# View last 50 lines
docker logs --tail 50 geo-ip-blocker
```

### Check Application Logs

```bash
# View application log
tail -f /opt/radware/storage/scripts/geo-ip-custom-block/app/tmp/geo-ip-blocker.log

# Search for errors
grep ERROR /opt/radware/storage/scripts/geo-ip-custom-block/app/tmp/geo-ip-blocker.log
```

### Check Exported Data

```bash
# List exported CSV files
ls -lh /opt/radware/storage/scripts/geo-ip-custom-block/app/data/

# View original networks (before summarization)
cat /opt/radware/storage/scripts/geo-ip-custom-block/app/data/original_network_ranges.csv

# View summarized networks (after CIDR aggregation)
cat /opt/radware/storage/scripts/geo-ip-custom-block/app/data/summarized_network_ranges.csv

# View summarization report
cat /opt/radware/storage/scripts/geo-ip-custom-block/app/data/network_summarization_report.csv
```

## 🔧 Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# DefensePro Configuration
CC_IP=10.105.193.3
DP_IPS=10.105.192.33,10.105.192.34
CC_USERNAME=radware
CC_PASSWORD=radware
VERIFY_SSL=false

# Target Regions
TARGET_COUNTRY=UA
TARGET_REGIONS=43,09,14  # Optional: leave empty for all subdivisions

# Workflow Control
ENABLE_GEODB_DOWNLOAD=true          # Download fresh database
FILTER_TARGET_REGIONS=true          # Filter by target regions
ENABLE_NETWORK_SUMMARIZATION=true   # Aggregate networks
CONFIGURE_DEFENSEPRO=true           # Push to DefensePro

# Cache Management
CACHE_RETENTION_COUNT=3             # Keep last 3 database versions

# Logging
LOG_LEVEL=INFO                      # DEBUG for troubleshooting
```

### Modify Configuration

After modifying `.env`, recreate the container:

```bash
# Remove old container
docker rm geo-ip-blocker

# Create new container with updated config
cd /opt/radware/storage/scripts/geo-ip-custom-block/app
docker create --name geo-ip-blocker \
  --env-file .env \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/tmp:/app/tmp" \
  --restart unless-stopped \
  egori4/geo-ip-custom-block:1.3.0

# Run with new configuration
docker start geo-ip-blocker
```

## 🗑️ Uninstallation

### Standard Uninstall (Prompts for Data)

```bash
sudo ./uninstall.sh
```

This will:
- Remove Docker container
- Remove Docker image
- Prompt whether to keep or remove data directory

### Keep Data, Remove Container/Image Only

```bash
sudo ./uninstall.sh --keep-data
```

Preserves:
- CSV exports in `data/` directory
- Logs in `tmp/` directory
- Cached GeoIP databases

### Complete Removal (No Prompts)

```bash
sudo ./uninstall.sh --remove-all --force
```

Removes everything:
- Docker container
- Docker image
- Installation directory and all data

⚠️ **WARNING**: This is destructive and cannot be undone!

### Uninstall Options

```
Usage: ./uninstall.sh [OPTIONS]

OPTIONS:
    --keep-data       Keep data directory (CSV exports, logs, cache)
    --remove-all      Complete removal including all data
    --force           Skip confirmation prompts
    -h, --help        Display help message

EXAMPLES:
    # Standard uninstall (prompts for data retention)
    sudo ./uninstall.sh
    
    # Keep data, remove container and image only
    sudo ./uninstall.sh --keep-data
    
    # Complete removal without prompts
    sudo ./uninstall.sh --remove-all --force
```

## 🚨 Troubleshooting

### Installation Issues

**Docker not found**:
```bash
# Install Docker
sudo apt-get update
sudo apt-get install docker.io

# Start Docker service
sudo systemctl start docker
sudo systemctl enable docker
```

**Permission denied**:
```bash
# Run with sudo
sudo ./install.sh

# Or add user to docker group
sudo usermod -aG docker $USER
# Log out and log back in
```

**Cannot create directory**:
```bash
# Check permissions
ls -ld /opt/radware/storage/scripts/

# Create parent directories
sudo mkdir -p /opt/radware/storage/scripts/

# Or use custom directory
./install.sh
# Enter custom path when prompted
```

### Runtime Issues

**Container won't start**:
```bash
# Check Docker logs
docker logs geo-ip-blocker

# Check container status
docker ps -a --filter name=geo-ip-blocker

# Inspect container configuration
docker inspect geo-ip-blocker
```

**Configuration errors**:
```bash
# Enable debug logging
nano /opt/radware/storage/scripts/geo-ip-custom-block/app/.env
# Set: LOG_LEVEL=DEBUG

# Recreate container
docker rm geo-ip-blocker
cd /opt/radware/storage/scripts/geo-ip-custom-block/app
docker create --name geo-ip-blocker \
  --env-file .env \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/tmp:/app/tmp" \
  egori4/geo-ip-custom-block:1.3.0

# Run and check logs
docker start geo-ip-blocker
docker logs -f geo-ip-blocker
```

**Network connectivity issues**:
```bash
# Test Radware API access
curl -I https://services.radware.com/api/geodb/getfile

# Test DefensePro connectivity
ping 10.105.193.3  # Replace with your CC_IP
```

**Too many networks extracted**:
```bash
# Edit .env to add specific regions
nano /opt/radware/storage/scripts/geo-ip-custom-block/app/.env

# Set TARGET_REGIONS (not just TARGET_COUNTRY)
TARGET_COUNTRY=UA
TARGET_REGIONS=43,09,14  # Specific subdivisions only

# Recreate container and run again
```

## 📁 Directory Structure

```
/opt/radware/storage/scripts/geo-ip-custom-block/app/
├── .env                           # Configuration file
├── data/                          # CSV exports (persistent)
│   ├── original_network_ranges.csv
│   ├── summarized_network_ranges.csv
│   └── network_summarization_report.csv
└── tmp/                           # Logs and cache (persistent)
    ├── geo-ip-blocker.log         # Application log
    └── geodb_cache/               # Cached GeoIP databases
        └── geodb_<md5>/           # Each database version
            ├── locations.csv      # ~150MB
            └── blocks_ipv4.csv    # ~80MB
```

## 🔄 Updates

To update to a new version:

```bash
# Uninstall current version (keep data)
sudo ./uninstall.sh --keep-data

# Extract new package
tar -xzf geo-ip-custom-block-v1.4.0.tar.gz
cd geo-ip-custom-block

# Run installation (will detect existing .env)
sudo ./install.sh

# Configuration will be preserved
# Answer 'N' when prompted to reconfigure
```

## 📚 Additional Documentation

For detailed information, see:
- `README.md` - Full application documentation
- `.env.example` - All configuration options
- [GitHub Repository](https://github.com/egori4/dp_geo_blocklist)

## 🆘 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review application logs (`docker logs geo-ip-blocker`)
3. Enable DEBUG logging in `.env`
4. Consult the full README.md documentation

## 📄 License

[Add appropriate license information]

---

**Version**: 1.3.0  
**Last Updated**: 2025-11-12
