#!/bin/bash

################################################################################
# GeoIP Custom IP Blocker - Installation Script
# Version: 1.4.0
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
DOCKER_IMAGE_TAG="1.4.0"
DOCKER_IMAGE_FULL="${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}"
CONTAINER_NAME="geo-ip-blocker"

# Get the directory where the install script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_ARCHIVE="${SCRIPT_DIR}/geo-ip-blocker-image.tar"

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${NC}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${NC}║${NC}  ${GREEN}GeoIP Custom IP Blocker - Installation${NC}                           ${NC}║${NC}"
    echo -e "${NC}║${NC}  Version: 1.4.0                                                   ${NC}║${NC}"
    echo -e "${NC}╚═══════════════════════════════════════════════════════════════════╝${NC}"
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
    echo -e "${NC}ℹ${NC} $1"
}

print_section() {
    echo ""
    echo -e "${NC}═══${NC} $1"
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
    echo -e "  Default: ${NC}${DEFAULT_INSTALL_DIR}${NC}"
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
    
    # Set permissions and ownership
    if [ "$EUID" -eq 0 ]; then
        # Running as root - set ownership to UID 1000 (standard non-root user)
        chmod -R 755 "$INSTALL_DIR"
        chown -R 1000:1000 "$INSTALL_DIR"
        print_info "Set ownership to UID:GID 1000:1000 for container compatibility"
    else
        # Running as regular user - ensure current user can write
        chmod -R 755 "$INSTALL_DIR"
        print_info "Set permissions for current user ($(id -un))"
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
    sed -i "s|^LOG_FILE=.*|LOG_FILE=./tmp/geo-ip-blocker.log|" "$ENV_FILE"
    sed -i "s|^GEODB_CACHE_DIR=.*|GEODB_CACHE_DIR=./tmp/geodb_cache|" "$ENV_FILE"
    
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
    print_info "Container will run as UID:GID 1000:1000 (defined in Docker image)"
    
    docker create \
        --name "${CONTAINER_NAME}" \
        --env-file "${INSTALL_DIR}/.env" \
        -v "${INSTALL_DIR}/data:/app/data" \
        -v "${INSTALL_DIR}/tmp:/app/tmp" \
        "${DOCKER_IMAGE_FULL}"
    
    print_success "Container created successfully"
}

################################################################################
# Post-Installation
################################################################################

display_usage_instructions() {
    print_section "Installation Complete!"
    
    echo ""
    echo -e "${GREEN}✓ Installation successful!${NC}"
    echo ""
    echo -e "${NC}═══ Installation Summary ═══${NC}"
    echo "  • Installation directory: ${INSTALL_DIR}"
    echo "  • Container name: ${CONTAINER_NAME}"
    echo "  • Docker image: ${DOCKER_IMAGE_FULL}"
    echo "  • Configuration: ${INSTALL_DIR}/.env"
    echo "  • Data directory: ${INSTALL_DIR}/data"
    echo "  • Logs directory: ${INSTALL_DIR}/tmp"
    echo ""
    echo -e "${NC}═══ Usage Instructions ═══${NC}"
    echo ""
    echo -e "${GREEN}Manual Execution:${NC}"
    echo "  docker start ${CONTAINER_NAME}"
    echo "  docker logs -f ${CONTAINER_NAME}"
    echo ""
    echo -e "${GREEN}Check Status:${NC}"
    echo "  docker ps -a --filter name=${CONTAINER_NAME}"
    echo "  docker logs ${CONTAINER_NAME}"
    echo ""
    echo -e "${GREEN}View Logs:${NC}"
    echo "  tail -f ${INSTALL_DIR}/tmp/geo-ip-blocker.log"
    echo "  docker logs -f ${CONTAINER_NAME}"
    echo ""
    echo -e "${GREEN}View Exported Data:${NC}"
    echo "  ls -lh ${INSTALL_DIR}/data/"
    echo "  cat ${INSTALL_DIR}/data/original_network_ranges.csv"
    echo "  cat ${INSTALL_DIR}/data/summarized_network_ranges.csv"
    echo ""
    echo -e "${GREEN}Scheduled Execution (Recommended):${NC}"
    echo "  Add to crontab for weekly runs:"
    echo ""
    echo "  crontab -e"
    echo ""
    echo "  # Add this line (runs every Sunday at 2:00 AM):"
    echo "  0 2 * * 0 docker start ${CONTAINER_NAME}"
    echo ""
    echo -e "${GREEN}Testing (Dry-Run Mode):${NC}"
    echo "  Edit ${INSTALL_DIR}/.env and set:"
    echo "    CONFIGURE_DEFENSEPRO=false"
    echo ""
    echo "  Then run:"
    echo "    docker start ${CONTAINER_NAME}"
    echo ""
    echo "  This will extract and validate data without pushing to DefensePro."
    echo ""
    echo -e "${GREEN}Configuration:${NC}"
    echo "  Edit configuration: nano ${INSTALL_DIR}/.env"
    echo "  After changes, recreate container:"
    echo "    docker rm ${CONTAINER_NAME}"
    echo "    docker create --name ${CONTAINER_NAME} \\"
    echo "      --env-file ${INSTALL_DIR}/.env \\"
    echo "      -v ${INSTALL_DIR}/data:/app/data \\"
    echo "      -v ${INSTALL_DIR}/tmp:/app/tmp \\"
    echo "      ${DOCKER_IMAGE_FULL}"
    echo ""
    echo -e "${NC}═══ Troubleshooting ═══${NC}"
    echo ""
    echo -e "${GREEN}Enable Debug Logging:${NC}"
    echo "  Edit ${INSTALL_DIR}/.env:"
    echo "    LOG_LEVEL=DEBUG"
    echo ""
    echo "  Recreate container and run again."
    echo ""
    echo -e "${GREEN}Force Fresh Download:${NC}"
    echo "  Edit ${INSTALL_DIR}/.env:"
    echo "    FORCE_DOWNLOAD=true"
    echo ""
    echo "  Recreate container and run again."
    echo ""
    echo -e "${GREEN}Uninstallation:${NC}"
    echo "  Run uninstall script:"
    echo "    sudo ./uninstall.sh"
    echo ""
    echo "  Options:"
    echo "    --keep-data    # Keep data directory (CSV exports, logs, cache)"
    echo "    --remove-all   # Complete removal including all data"
    echo ""
    echo -e "${NC}═══ Next Steps ═══${NC}"
    echo ""
    echo -e "1. ${YELLOW}Test the installation:${NC}"
    echo "   docker start ${CONTAINER_NAME}"
    echo "   docker logs -f ${CONTAINER_NAME}"
    echo ""
    echo -e "2. ${YELLOW}Review the logs:${NC}"
    echo "   tail -f ${INSTALL_DIR}/tmp/geo-ip-blocker.log"
    echo ""
    echo -e "3. ${YELLOW}Check exported data:${NC}"
    echo "   ls -lh ${INSTALL_DIR}/data/"
    echo ""
    echo -e "4. ${YELLOW}Set up scheduled execution:${NC}"
    echo "   crontab -e"
    echo ""
    echo -e "${GREEN}For detailed documentation, see README.md${NC}"
    echo ""
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
