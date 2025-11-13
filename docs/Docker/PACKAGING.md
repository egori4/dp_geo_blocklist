# Packaging Instructions

## Overview

This document describes how to create the installation package for distribution.

## Prerequisites

- Docker installed and running
- Docker Hub account (optional, for publishing image)
- Build environment with all source files

## Create Installation Package

### Step 1: Make Scripts Executable

```bash
chmod +x install.sh uninstall.sh create-package.sh
```

### Step 2: Run Package Creation Script

```bash
./create-package.sh
```

This script will:
1. Build Docker image from Dockerfile
2. Export Docker image to `geo-ip-blocker-image.tar`
3. Create package directory with all necessary files
4. Create compressed archive: `geo-ip-custom-block-v1.3.0.tar.gz`
5. Optionally push image to Docker Hub

### Step 3: Test Installation Package

```bash
# Extract package
tar -xzf geo-ip-custom-block-v1.3.0.tar.gz
cd geo-ip-custom-block-v1.3.0

# Test installation
sudo ./install.sh

# Verify container works
docker start geo-ip-blocker
docker logs geo-ip-blocker

# Test uninstallation
sudo ./uninstall.sh --keep-data
```

## Package Contents

The installation package includes:

```
geo-ip-custom-block-v1.3.0/
├── geo-ip-blocker-image.tar    # Docker image (~500MB)
├── install.sh                  # Installation script
├── uninstall.sh                # Uninstallation script
├── .env.example                # Configuration template
├── INSTALLATION.md             # User installation guide
└── README.md                   # Full documentation
```

## Docker Hub Publishing

### Login to Docker Hub

```bash
docker login
# Enter username: egori4
# Enter password: [your-token]
```

### Tag and Push Image

```bash
# Tag image
docker tag egori4/geo-ip-custom-block:1.3.0 egori4/geo-ip-custom-block:latest

# Push version tag
docker push egori4/geo-ip-custom-block:1.3.0

# Push latest tag
docker push egori4/geo-ip-custom-block:latest
```

### Verify on Docker Hub

Visit: https://hub.docker.com/r/egori4/geo-ip-custom-block

## Distribution Options

### Option 1: Docker Hub + Package (Recommended)

**Advantages**:
- Smaller package size
- Faster downloads from Docker Hub
- Automatic fallback to local archive
- Easier updates

**Process**:
1. Push image to Docker Hub
2. Distribute `geo-ip-custom-block-v1.3.0.tar.gz`
3. Users install with `install.sh` (pulls from Docker Hub first)
4. Falls back to local archive if Docker Hub unavailable

### Option 2: Package Only

**Advantages**:
- No Docker Hub dependency
- Works in air-gapped environments
- Single file distribution

**Process**:
1. Create package with `create-package.sh`
2. Distribute `geo-ip-custom-block-v1.3.0.tar.gz`
3. Users install with `install.sh` (uses local archive)

## Version Management

When creating a new version:

1. Update version in all files:
   - `install.sh` (DOCKER_IMAGE_TAG)
   - `uninstall.sh` (DOCKER_IMAGE_TAG)
   - `create-package.sh` (PACKAGE_NAME, DOCKER_IMAGE_TAG)
   - `Dockerfile` (LABEL version)

2. Update documentation:
   - `README.md` (Version History section)
   - `INSTALLATION.md` (version references)

3. Create new package:
   ```bash
   ./create-package.sh
   ```

4. Tag in git:
   ```bash
   git tag -a v1.3.0 -m "Version 1.3.0"
   git push origin v1.3.0
   ```

5. Publish to Docker Hub:
   ```bash
   docker push egori4/geo-ip-custom-block:1.3.0
   docker push egori4/geo-ip-custom-block:latest
   ```

## Testing Checklist

Before distributing a package:

- [ ] Build succeeds without errors
- [ ] Docker image runs successfully
- [ ] Installation script completes without errors
- [ ] Container starts and processes data
- [ ] Logs show no errors
- [ ] Uninstallation works with all options
- [ ] Package can be extracted on target system
- [ ] Documentation is complete and accurate

## Troubleshooting Package Creation

### Docker build fails

```bash
# Clean Docker cache
docker system prune -a

# Rebuild image
docker build --no-cache -t egori4/geo-ip-custom-block:1.3.0 .
```

### Image export fails

```bash
# Check available disk space
df -h

# Clean up old images
docker image prune -a
```

### Package creation fails

```bash
# Ensure all files exist
ls -la install.sh uninstall.sh .env.example INSTALLATION.md README.md

# Check permissions
chmod +x install.sh uninstall.sh create-package.sh
```

## Manual Package Creation

If the automated script fails, create the package manually:

```bash
# Build and export image
docker build -t egori4/geo-ip-custom-block:1.3.0 .
docker save egori4/geo-ip-custom-block:1.3.0 -o geo-ip-blocker-image.tar

# Create package directory
mkdir -p geo-ip-custom-block-v1.3.0

# Copy files
cp geo-ip-blocker-image.tar geo-ip-custom-block-v1.3.0/
cp install.sh uninstall.sh .env.example geo-ip-custom-block-v1.3.0/
cp INSTALLATION.md README.md geo-ip-custom-block-v1.3.0/

# Make scripts executable
chmod +x geo-ip-custom-block-v1.3.0/install.sh
chmod +x geo-ip-custom-block-v1.3.0/uninstall.sh

# Create archive
tar -czf geo-ip-custom-block-v1.3.0.tar.gz geo-ip-custom-block-v1.3.0/

# Verify package
tar -tzf geo-ip-custom-block-v1.3.0.tar.gz | head -20
```

## File Checksums

Generate checksums for package verification:

```bash
# SHA256
sha256sum geo-ip-custom-block-v1.3.0.tar.gz > geo-ip-custom-block-v1.3.0.tar.gz.sha256

# MD5
md5sum geo-ip-custom-block-v1.3.0.tar.gz > geo-ip-custom-block-v1.3.0.tar.gz.md5
```

Users can verify:

```bash
# Verify SHA256
sha256sum -c geo-ip-custom-block-v1.3.0.tar.gz.sha256

# Verify MD5
md5sum -c geo-ip-custom-block-v1.3.0.tar.gz.md5
```

---

**Version**: 1.3.0  
**Last Updated**: 2025-11-12
