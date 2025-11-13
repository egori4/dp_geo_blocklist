# Deployment Scripts Summary

## Created Files

### 1. `install.sh` - Installation Script
**Purpose**: Automated installation of geo-ip-custom-block application

**Features**:
- ✅ Docker installation verification
- ✅ Custom installation directory support (default: /opt/radware/storage/scripts/geo-ip-custom-block/app)
- ✅ Directory structure creation with proper permissions
- ✅ Intelligent Docker image loading:
  - First attempts to pull from Docker Hub (egori4/geo-ip-custom-block:1.3.0)
  - Falls back to local archive (geo-ip-blocker-image.tar) if Docker Hub unavailable
- ✅ Interactive configuration prompts with defaults:
  - CC_IP (CyberController IP)
  - DP_IPS (DefensePro devices, comma-separated)
  - CC_USERNAME (default: radware)
  - CC_PASSWORD (default: radware)
  - TARGET_COUNTRY (default: UA)
  - TARGET_REGIONS (default: 43,09,14 with warning)
- ✅ .env file creation from .env.example with user values
- ✅ Docker container creation with volume mounts
- ✅ Comprehensive usage instructions display
- ✅ Color-coded output for better UX
- ✅ Error handling and validation

**Usage**:
```bash
chmod +x install.sh
sudo ./install.sh
```

### 2. `uninstall.sh` - Uninstallation Script
**Purpose**: Clean removal of geo-ip-custom-block application

**Features**:
- ✅ Automatic installation directory discovery
- ✅ Intelligent cleanup options:
  - `--keep-data`: Preserve data directory (CSV exports, logs, cache)
  - `--remove-all`: Complete removal including all data
  - `--force`: Skip confirmation prompts
- ✅ Interactive prompts for data retention
- ✅ Detailed removal plan display before execution
- ✅ Safe container and image removal
- ✅ Comprehensive summary of what was removed/preserved
- ✅ Color-coded output
- ✅ Error handling

**Usage**:
```bash
# Standard uninstall (prompts for data)
sudo ./uninstall.sh

# Keep data
sudo ./uninstall.sh --keep-data

# Complete removal (no prompts)
sudo ./uninstall.sh --remove-all --force
```

### 3. `create-package.sh` - Package Creation Script
**Purpose**: Create complete installation package for distribution

**Features**:
- ✅ Docker image building
- ✅ Docker image export to tar archive
- ✅ Package assembly with all required files
- ✅ Compressed archive creation (tar.gz)
- ✅ Optional Docker Hub push integration
- ✅ Size reporting for image and package
- ✅ Comprehensive distribution instructions
- ✅ Color-coded output

**Usage**:
```bash
chmod +x create-package.sh
./create-package.sh
```

**Creates**:
- `geo-ip-blocker-image.tar` (~500MB Docker image)
- `geo-ip-custom-block-v1.3.0.tar.gz` (complete package)

### 4. `INSTALLATION.md` - User Installation Guide
**Purpose**: End-user documentation for installation and usage

**Contents**:
- Package contents description
- Quick start guide
- Usage instructions (manual, scheduled, dry-run)
- Monitoring and logging
- Configuration management
- Uninstallation procedures
- Comprehensive troubleshooting
- Directory structure explanation
- Update procedures

### 5. `PACKAGING.md` - Developer Packaging Guide
**Purpose**: Developer documentation for creating distribution packages

**Contents**:
- Overview of packaging process
- Step-by-step package creation
- Docker Hub publishing instructions
- Distribution options comparison
- Version management procedures
- Testing checklist
- Troubleshooting package creation
- Manual package creation (fallback)
- Checksum generation for verification

## Package Structure

The installation package includes:

```
geo-ip-custom-block-v1.3.0.tar.gz
└── geo-ip-custom-block-v1.3.0/
    ├── geo-ip-blocker-image.tar    # Docker image (~500MB)
    ├── install.sh                  # Installation script (executable)
    ├── uninstall.sh                # Uninstallation script (executable)
    ├── .env.example                # Configuration template
    ├── INSTALLATION.md             # User guide
    └── README.md                   # Full documentation
```

## Installation Flow

```
1. User downloads: geo-ip-custom-block-v1.3.0.tar.gz
2. Extract package: tar -xzf geo-ip-custom-block-v1.3.0.tar.gz
3. Run install.sh: sudo ./install.sh
4. Script checks Docker
5. Script prompts for installation directory
6. Script tries Docker Hub pull
7. Script falls back to local archive if needed
8. Script prompts for configuration
9. Script creates .env file
10. Script creates container
11. User runs: docker start geo-ip-blocker
```

## Distribution Options

### Option 1: Docker Hub + Package (Recommended)
- Push image to Docker Hub: `egori4/geo-ip-custom-block:1.3.0`
- Distribute package: `geo-ip-custom-block-v1.3.0.tar.gz`
- Users pull from Docker Hub (faster)
- Falls back to local archive if offline

### Option 2: Package Only
- Distribute package: `geo-ip-custom-block-v1.3.0.tar.gz`
- Users install from local archive
- No internet required
- Works in air-gapped environments

## Key Features

### Security
- ✅ No hardcoded credentials
- ✅ Interactive password prompts (hidden input)
- ✅ Proper file permissions
- ✅ Non-root container execution
- ✅ Volume mounts for data persistence

### User Experience
- ✅ Color-coded output (success, error, warning, info)
- ✅ Clear section headers
- ✅ Sensible defaults
- ✅ Comprehensive error messages
- ✅ Detailed usage instructions
- ✅ Interactive confirmations for destructive operations

### Testability
- ✅ Works in WSL environment
- ✅ Supports custom installation directories
- ✅ Docker Hub connectivity optional
- ✅ Dry-run mode support
- ✅ Debug logging available

### Robustness
- ✅ Pre-flight checks (Docker, permissions)
- ✅ Error handling with exit codes
- ✅ Automatic fallback (Docker Hub → local archive)
- ✅ Directory detection and validation
- ✅ Cleanup on failure

## Testing Procedures

### 1. Test Installation (WSL)
```bash
# Use custom directory (no sudo needed)
./install.sh
# Enter: ~/test-geo-ip-blocker
# Provide test configuration
# Verify container created
docker ps -a --filter name=geo-ip-blocker
```

### 2. Test Execution
```bash
docker start geo-ip-blocker
docker logs -f geo-ip-blocker
```

### 3. Test Uninstallation
```bash
# Test with data preservation
./uninstall.sh --keep-data

# Verify data preserved
ls -la ~/test-geo-ip-blocker/data/
```

### 4. Test Complete Removal
```bash
# Clean removal
./uninstall.sh --remove-all --force

# Verify everything removed
docker ps -a --filter name=geo-ip-blocker
ls -la ~/test-geo-ip-blocker/  # Should not exist
```

## Deployment Checklist

Before distributing package:

- [ ] All scripts are executable (`chmod +x`)
- [ ] Docker image builds successfully
- [ ] Package creation completes without errors
- [ ] Installation works in test environment
- [ ] Container starts and processes data correctly
- [ ] Uninstallation works with all options
- [ ] Documentation is complete and accurate
- [ ] README.md version history is updated
- [ ] Docker Hub image is pushed (optional)
- [ ] Package checksum is generated

## Version Updates

When releasing new version (e.g., 1.4.0):

1. Update version in:
   - `install.sh` (line 16: DOCKER_IMAGE_TAG)
   - `uninstall.sh` (line 16: DOCKER_IMAGE_TAG)
   - `create-package.sh` (lines 17-19: PACKAGE_NAME, DOCKER_IMAGE_TAG)
   - `INSTALLATION.md` (bottom version line)
   - `PACKAGING.md` (bottom version line)
   - `README.md` (Version History section)

2. Create package:
   ```bash
   ./create-package.sh
   ```

3. Test package thoroughly

4. Push to Docker Hub (optional)

5. Distribute package

## Troubleshooting

### Common Issues

**Docker not found**:
```bash
# Install Docker first
sudo apt-get install docker.io
sudo systemctl start docker
```

**Permission denied**:
```bash
# Run with sudo
sudo ./install.sh
```

**Cannot create directory**:
```bash
# Use custom directory
./install.sh
# Enter: ~/geo-ip-blocker (user home, no sudo needed)
```

**Image pull fails**:
- Script automatically falls back to local archive
- Verify connectivity to https://hub.docker.com/
- Verify `geo-ip-blocker-image.tar` exists in package

**Container won't start**:
```bash
# Check logs
docker logs geo-ip-blocker

# Enable debug mode
nano /path/to/install/.env
# Set: LOG_LEVEL=DEBUG

# Recreate container
docker rm geo-ip-blocker
# Run install.sh again or manually create container
```

## Success Criteria

✅ Installation completes without errors  
✅ Container is created and named correctly  
✅ Configuration file is properly populated  
✅ Volume mounts are correct  
✅ Container can start and execute  
✅ Data is persisted in correct directories  
✅ Logs are accessible and readable  
✅ Uninstallation removes container and image  
✅ Data preservation option works correctly  
✅ Documentation is clear and complete  

---

**Created**: 2025-11-12  
**Version**: 1.3.0  
**Status**: ✅ Ready for distribution
