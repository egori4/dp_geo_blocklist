# Quick Reference - Deployment Scripts

## 📦 For Package Creators (Developers)

### Create Installation Package
```bash
# Make scripts executable
chmod +x install.sh uninstall.sh create-package.sh

# Create package (includes Docker image export)
./create-package.sh

# Result: geo-ip-custom-block-v1.3.0.tar.gz (~500MB)
```

### Push to Docker Hub (Optional)
```bash
# Login
docker login

# Build and tag
docker build -t egori4/geo-ip-custom-block:1.3.0 .
docker tag egori4/geo-ip-custom-block:1.3.0 egori4/geo-ip-custom-block:latest

# Push
docker push egori4/geo-ip-custom-block:1.3.0
docker push egori4/geo-ip-custom-block:latest
```

## 🚀 For End Users (Installation)

### Install Application
```bash
# Extract package
tar -xzf geo-ip-custom-block-v1.3.0.tar.gz
cd geo-ip-custom-block-v1.3.0

# Make executable (if needed)
chmod +x install.sh uninstall.sh

# Run installation
sudo ./install.sh
```

**Prompts**:
- Installation directory (default: /opt/radware/storage/scripts/geo-ip-custom-block/app)
- CyberController IP (required)
- DefensePro IPs (comma-separated, required)
- Username (default: radware)
- Password (default: radware)
- Target country (default: UA)
- Target regions (default: 43,09,14)

### Run Application
```bash
# Manual execution
docker start geo-ip-blocker

# Watch logs
docker logs -f geo-ip-blocker

# Check status
docker ps -a --filter name=geo-ip-blocker
```

### Schedule Execution (Cron)
```bash
# Edit crontab
crontab -e

# Add line (runs every Sunday at 2 AM)
0 2 * * 0 docker start geo-ip-blocker
```

## 🗑️ Uninstallation

### Keep Data (CSV, Logs, Cache)
```bash
sudo ./uninstall.sh --keep-data
```

### Remove Everything (Interactive)
```bash
sudo ./uninstall.sh
# Prompts for data removal confirmation
```

### Complete Removal (No Prompts)
```bash
sudo ./uninstall.sh --remove-all --force
```

## 🔧 Configuration

### Edit Configuration
```bash
# Location (after installation)
nano /opt/radware/storage/scripts/geo-ip-custom-block/app/.env

# Key settings
CC_IP=10.105.193.3
DP_IPS=10.105.192.33,10.105.192.34
TARGET_COUNTRY=UA
TARGET_REGIONS=43,09,14
LOG_LEVEL=INFO  # DEBUG for troubleshooting
CONFIGURE_DEFENSEPRO=true  # false for dry-run
```

### Apply Configuration Changes
```bash
# Remove old container
docker rm geo-ip-blocker

# Recreate with new config
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

## 📊 Monitoring

### View Logs
```bash
# Docker container logs
docker logs geo-ip-blocker
docker logs -f geo-ip-blocker  # Follow

# Application log file
tail -f /opt/radware/storage/scripts/geo-ip-custom-block/app/tmp/geo-ip-blocker.log

# Search for errors
grep ERROR /opt/radware/storage/scripts/geo-ip-custom-block/app/tmp/geo-ip-blocker.log
```

### View Data
```bash
# List CSV exports
ls -lh /opt/radware/storage/scripts/geo-ip-custom-block/app/data/

# View original networks
cat /opt/radware/storage/scripts/geo-ip-custom-block/app/data/original_network_ranges.csv

# View summarized networks
cat /opt/radware/storage/scripts/geo-ip-custom-block/app/data/summarized_network_ranges.csv
```

## 🚨 Troubleshooting

### Docker Issues
```bash
# Check Docker status
docker info

# Start Docker
sudo systemctl start docker

# Check if image exists
docker images | grep geo-ip-blocker
```

### Container Issues
```bash
# Check container status
docker ps -a --filter name=geo-ip-blocker

# Inspect container
docker inspect geo-ip-blocker

# Remove and recreate
docker rm geo-ip-blocker
# Run install.sh again or create manually
```

### Enable Debug Logging
```bash
# Edit .env
nano /opt/radware/storage/scripts/geo-ip-custom-block/app/.env

# Change LOG_LEVEL
LOG_LEVEL=DEBUG

# Recreate container (see "Apply Configuration Changes" above)
# Run and check detailed logs
```

### Force Fresh Download
```bash
# Edit .env
nano /opt/radware/storage/scripts/geo-ip-custom-block/app/.env

# Enable force download
FORCE_DOWNLOAD=true

# Recreate container and run
```

## 📁 Important Paths

### After Installation

```
/opt/radware/storage/scripts/geo-ip-custom-block/app/
├── .env                          # Configuration
├── data/                         # CSV exports
│   ├── original_network_ranges.csv
│   ├── summarized_network_ranges.csv
│   └── network_summarization_report.csv
└── tmp/                          # Logs and cache
    ├── geo-ip-blocker.log
    └── geodb_cache/
        └── geodb_<md5>/
            ├── locations.csv
            └── blocks_ipv4.csv
```

## 🎯 Common Use Cases

### Dry-Run (Test Without DefensePro)
```bash
# Edit .env
CONFIGURE_DEFENSEPRO=false

# Recreate container and run
# Check CSV exports in data/ directory
```

### Use Cached Database (No Download)
```bash
# Edit .env
ENABLE_GEODB_DOWNLOAD=false

# Recreate container and run
# Uses existing cache in tmp/geodb_cache/
```

### Disable Network Summarization
```bash
# Edit .env
ENABLE_NETWORK_SUMMARIZATION=false

# Recreate container and run
# Uses original networks without aggregation
```

## 📖 Documentation

- **INSTALLATION.md** - Detailed installation guide
- **README.md** - Full application documentation
- **PACKAGING.md** - Package creation guide (developers)
- **DEPLOYMENT_SCRIPTS_SUMMARY.md** - Script features and testing

## 🆘 Support

For issues:
1. Check logs: `docker logs geo-ip-blocker`
2. Enable debug: `LOG_LEVEL=DEBUG` in .env
3. Review INSTALLATION.md troubleshooting section
4. Check README.md for detailed documentation

---

**Version**: 1.3.0  
**Last Updated**: 2025-11-12
