#!/bin/bash

################################################################################
# GeoIP Custom IP Blocker - Installation Script
# Version: 1.3.0
# 
# This script installs the geo-ip-custom-block Docker container and configures
# the application for production use.
################################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
DEFAULT_INSTALL_DIR="/opt/radware/storage/scripts/geo-ip-custom-block/app"
DOCKER_IMAGE_NAME="egori4/geo-ip-custom-block"
DOCKER_IMAGE_TAG="1.3.0"
DOCKER_IMAGE_FULL="${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}"
CONTAINER_NAME="geo-ip-blocker"

# Get the directory where the install script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_ARCHIVE="${SCRIPT_DIR}/geo-ip-blocker-image.tar"

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${GREEN}GeoIP Custom IP Blocker - Installation${NC}                         ${BLUE}║${NC}"
    echo -e "${BLUE}║${NC}  Version: 1.3.0                                                 ${BLUE}║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1" >&2
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_section() {
    echo ""
    echo -e "${BLUE}═══${NC} $1"
    echo ""
}

################################################################################
# Pre-flight Checks
################################################################################

check_docker() {
    print_section "Checking Prerequisites"
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        echo ""
        echo "Please install Docker before running this script:"
        echo "  • Ubuntu/Debian: sudo apt-get install docker.io"
        echo "  • CentOS/RHEL: sudo yum install docker"
        echo "  • Or visit: https://docs.docker.com/get-docker/"
        echo ""
        exit 1
    fi
    print_success "Docker is installed: $(docker --version)"
    
    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        echo ""
        echo "Please start Docker service:"
        echo "  • sudo systemctl start docker"
        echo "  • Or: sudo service docker start"
        echo ""
        exit 1
    fi
    print_success "Docker daemon is running"
}

check_permissions() {
    if [ "$EUID" -ne 0 ]; then
        print_warning "Script is not running as root"
        print_info "You may be prompted for sudo password for certain operations"
    fi
}

################################################################################
# Installation Directory Setup
################################################################################

setup_installation_directory() {
    print_section "Installation Directory Setup"
    
    echo "Enter installation directory path:"
    echo -e "  Default: ${BLUE}${DEFAULT_INSTALL_DIR}${NC}"
    read -p "  Path [press Enter for default]: " INSTALL_DIR
    
    # Use default if empty
    INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
    
    echo ""
    print_info "Installation directory: ${INSTALL_DIR}"
    
    # Create directory structure
    echo ""
    print_info "Creating directory structure..."
    
    if [ ! -d "$INSTALL_DIR" ]; then
        mkdir -p "$INSTALL_DIR" || {
            print_error "Failed to create directory: $INSTALL_DIR"
            print_info "Try running with sudo: sudo ./install.sh"
            exit 1
        }
    fi
    
    # Create subdirectories
    mkdir -p "${INSTALL_DIR}/data"
    mkdir -p "${INSTALL_DIR}/tmp"
    mkdir -p "${INSTALL_DIR}/tmp/geodb_cache"
    
    # Set permissions (if running as root, make accessible to non-root users)
    if [ "$EUID" -eq 0 ]; then
        chmod -R 755 "$INSTALL_DIR"
    fi
    
    print_success "Directory structure created"
    print_info "  • ${INSTALL_DIR}"
    print_info "  • ${INSTALL_DIR}/data (CSV exports)"
    print_info "  • ${INSTALL_DIR}/tmp (logs and cache)"
}

################################################################################
# Docker Image Setup
################################################################################

load_docker_image() {
    print_section "Docker Image Setup"
    
    # Check if image already exists
    if docker image inspect "${DOCKER_IMAGE_FULL}" &> /dev/null; then
        print_info "Image ${DOCKER_IMAGE_FULL} already exists locally"
        read -p "Do you want to re-pull/re-import the image? [y/N]: " RELOAD_IMAGE
        if [[ ! "$RELOAD_IMAGE" =~ ^[Yy]$ ]]; then
            print_info "Using existing image"
            return 0
        fi
    fi
    
    # Try to pull from Docker Hub first
    print_info "Attempting to pull image from Docker Hub..."
    if docker pull "${DOCKER_IMAGE_FULL}" 2>/dev/null; then
        print_success "Successfully pulled image from Docker Hub"
        return 0
    else
        print_warning "Failed to pull from Docker Hub (no internet or image not available)"
    fi
    
    # Fall back to local archive
    if [ -f "$IMAGE_ARCHIVE" ]; then
        print_info "Loading image from local archive: $(basename $IMAGE_ARCHIVE)"
        if docker load -i "$IMAGE_ARCHIVE"; then
            print_success "Successfully loaded image from archive"
            
            # Tag the image if needed (in case archive has different tag)
            LOADED_IMAGE=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep geo-ip-blocker | head -1)
            if [ "$LOADED_IMAGE" != "$DOCKER_IMAGE_FULL" ]; then
                docker tag "$LOADED_IMAGE" "$DOCKER_IMAGE_FULL" 2>/dev/null || true
            fi
            
            return 0
        else
            print_error "Failed to load image from archive"
            exit 1
        fi
    else
        print_error "Image archive not found: $IMAGE_ARCHIVE"
        print_error "Cannot proceed without Docker image"
        echo ""
        echo "Please ensure the installation package includes: geo-ip-blocker-image.tar"
        exit 1
    fi
}

################################################################################
# Configuration Setup
################################################################################

configure_environment() {
    print_section "Environment Configuration"
    
    ENV_FILE="${INSTALL_DIR}/.env"
    
    # Check if .env already exists
    if [ -f "$ENV_FILE" ]; then
        print_warning "Configuration file already exists: $ENV_FILE"
        read -p "Do you want to reconfigure? [y/N]: " RECONFIGURE
        if [[ ! "$RECONFIGURE" =~ ^[Yy]$ ]]; then
            print_info "Using existing configuration"
            return 0
        fi
        
        # Backup existing .env
        BACKUP_FILE="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$BACKUP_FILE"
        print_info "Backed up existing configuration to: $(basename $BACKUP_FILE)"
    fi
    
    # Copy .env.example as template
    if [ -f "${SCRIPT_DIR}/.env.example" ]; then
        cp "${SCRIPT_DIR}/.env.example" "$ENV_FILE"
    else
        print_error ".env.example not found in installation package"
        exit 1
    fi
    
    echo ""
    print_info "Please provide the following configuration values:"
    echo ""
    
    # CC_IP
    read -p "CyberController IP address: " CC_IP
    while [ -z "$CC_IP" ]; do
        print_warning "CC_IP is required"
        read -p "CyberController IP address: " CC_IP
    done
    
    # DP_IPS
    echo ""
    print_info "Enter DefensePro device IP addresses (comma-separated)"
    print_info "Example: 10.105.192.33,10.105.192.34,10.105.192.35"
    read -p "DefensePro IPs: " DP_IPS
    while [ -z "$DP_IPS" ]; do
        print_warning "DP_IPS is required"
        read -p "DefensePro IPs: " DP_IPS
    done
    
    # CC_USERNAME
    echo ""
    read -p "CyberController username [radware]: " CC_USERNAME
    CC_USERNAME="${CC_USERNAME:-radware}"
    
    # CC_PASSWORD
    read -sp "CyberController password [radware]: " CC_PASSWORD
    echo ""
    CC_PASSWORD="${CC_PASSWORD:-radware}"
    
    # TARGET_COUNTRY
    echo ""
    read -p "Target country code [UA]: " TARGET_COUNTRY
    TARGET_COUNTRY="${TARGET_COUNTRY:-UA}"
    
    # TARGET_REGIONS
    echo ""
    print_info "Target regions (subdivision ISO codes, comma-separated)"
    print_info "  • Leave empty to include ALL subdivisions for ${TARGET_COUNTRY}"
    print_info "  • For Ukraine occupied territories: 43,09,14 (Crimea, Donetsk, Luhansk)"
    print_warning "WARNING: Not setting regions may result in too many networks exceeding DefensePro Blocklist rule limits."
    read -p "Target regions [43,09,14]: " TARGET_REGIONS
    TARGET_REGIONS="${TARGET_REGIONS:-43,09,14}"
    
    # Update .env file
    sed -i "s|^CC_IP=.*|CC_IP=${CC_IP}|" "$ENV_FILE"
    sed -i "s|^DP_IPS=.*|DP_IPS=${DP_IPS}|" "$ENV_FILE"
    sed -i "s|^CC_USERNAME=.*|CC_USERNAME=${CC_USERNAME}|" "$ENV_FILE"
    sed -i "s|^CC_PASSWORD=.*|CC_PASSWORD=${CC_PASSWORD}|" "$ENV_FILE"
    sed -i "s|^TARGET_COUNTRY=.*|TARGET_COUNTRY=${TARGET_COUNTRY}|" "$ENV_FILE"
    
    if [ -n "$TARGET_REGIONS" ]; then
        sed -i "s|^TARGET_REGIONS=.*|TARGET_REGIONS=${TARGET_REGIONS}|" "$ENV_FILE"
    else
        sed -i "s|^TARGET_REGIONS=.*|#TARGET_REGIONS=|" "$ENV_FILE"
    fi
    
    # Update paths to use absolute paths
    sed -i "s|^LOG_FILE=.*|LOG_FILE=${INSTALL_DIR}/tmp/geo-ip-blocker.log|" "$ENV_FILE"
    sed -i "s|^GEODB_CACHE_DIR=.*|GEODB_CACHE_DIR=${INSTALL_DIR}/tmp/geodb_cache|" "$ENV_FILE"
    
    print_success "Configuration file created: $ENV_FILE"
}

################################################################################
# Container Setup
################################################################################

create_container() {
    print_section "Container Setup"
    
    # Check if container already exists
    if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        print_warning "Container '${CONTAINER_NAME}' already exists"
        read -p "Do you want to remove and recreate it? [y/N]: " RECREATE
        if [[ "$RECREATE" =~ ^[Yy]$ ]]; then
            print_info "Removing existing container..."
            docker rm -f "${CONTAINER_NAME}" &> /dev/null || true
        else
            print_info "Using existing container"
            return 0
        fi
    fi
    
    print_info "Creating container '${CONTAINER_NAME}'..."
    
    docker create \
        --name "${CONTAINER_NAME}" \
        --env-file "${INSTALL_DIR}/.env" \
        -v "${INSTALL_DIR}/data:/app/data" \
        -v "${INSTALL_DIR}/tmp:/app/tmp" \
        --restart unless-stopped \
        "${DOCKER_IMAGE_FULL}"
    
    print_success "Container created successfully"
}

################################################################################
# Post-Installation
################################################################################

display_usage_instructions() {
    print_section "Installation Complete!"
    
    cat << EOF

${GREEN}✓ Installation successful!${NC}

${BLUE}═══ Installation Summary ═══${NC}
  • Installation directory: ${INSTALL_DIR}
  • Container name: ${CONTAINER_NAME}
  • Docker image: ${DOCKER_IMAGE_FULL}
  • Configuration: ${INSTALL_DIR}/.env
  • Data directory: ${INSTALL_DIR}/data
  • Logs directory: ${INSTALL_DIR}/tmp

${BLUE}═══ Usage Instructions ═══${NC}

${GREEN}Manual Execution:${NC}
  docker start ${CONTAINER_NAME}
  docker logs -f ${CONTAINER_NAME}

${GREEN}Check Status:${NC}
  docker ps -a --filter name=${CONTAINER_NAME}
  docker logs ${CONTAINER_NAME}

${GREEN}View Logs:${NC}
  tail -f ${INSTALL_DIR}/tmp/geo-ip-blocker.log
  docker logs -f ${CONTAINER_NAME}

${GREEN}View Exported Data:${NC}
  ls -lh ${INSTALL_DIR}/data/
  cat ${INSTALL_DIR}/data/original_network_ranges.csv
  cat ${INSTALL_DIR}/data/summarized_network_ranges.csv

${GREEN}Scheduled Execution (Recommended):${NC}
  Add to crontab for weekly runs:
  
  crontab -e
  
  # Add this line (runs every Sunday at 2:00 AM):
  0 2 * * 0 docker start ${CONTAINER_NAME}

${GREEN}Testing (Dry-Run Mode):${NC}
  Edit ${INSTALL_DIR}/.env and set:
    CONFIGURE_DEFENSEPRO=false
  
  Then run:
    docker start ${CONTAINER_NAME}
  
  This will extract and validate data without pushing to DefensePro.

${GREEN}Configuration:${NC}
  Edit configuration: nano ${INSTALL_DIR}/.env
  After changes, recreate container:
    docker rm ${CONTAINER_NAME}
    docker create --name ${CONTAINER_NAME} \\
      --env-file ${INSTALL_DIR}/.env \\
      -v ${INSTALL_DIR}/data:/app/data \\
      -v ${INSTALL_DIR}/tmp:/app/tmp \\
      --restart unless-stopped \\
      ${DOCKER_IMAGE_FULL}

${BLUE}═══ Troubleshooting ═══${NC}

${GREEN}Enable Debug Logging:${NC}
  Edit ${INSTALL_DIR}/.env:
    LOG_LEVEL=DEBUG
  
  Recreate container and run again.

${GREEN}Force Fresh Download:${NC}
  Edit ${INSTALL_DIR}/.env:
    FORCE_DOWNLOAD=true
  
  Recreate container and run again.

${GREEN}Uninstallation:${NC}
  Run uninstall script:
    sudo ./uninstall.sh
  
  Options:
    --keep-data    # Keep data directory (CSV exports, logs, cache)
    --remove-all   # Complete removal including all data

${BLUE}═══ Next Steps ═══${NC}

1. ${YELLOW}Test the installation:${NC}
   docker start ${CONTAINER_NAME}
   docker logs -f ${CONTAINER_NAME}

2. ${YELLOW}Review the logs:${NC}
   tail -f ${INSTALL_DIR}/tmp/geo-ip-blocker.log

3. ${YELLOW}Check exported data:${NC}
   ls -lh ${INSTALL_DIR}/data/

4. ${YELLOW}Set up scheduled execution:${NC}
   crontab -e

${GREEN}For detailed documentation, see README.md${NC}

EOF
}

################################################################################
# Main Installation Flow
################################################################################

main() {
    print_header
    
    # Pre-flight checks
    check_docker
    check_permissions
    
    # Installation steps
    setup_installation_directory
    load_docker_image
    configure_environment
    create_container
    
    # Post-installation
    display_usage_instructions
}

# Run main installation
main

exit 0
