#!/bin/bash

################################################################################
# GeoIP Custom IP Blocker - Uninstallation Script
# Version: 1.3.0
# 
# This script removes the geo-ip-custom-block Docker container, image,
# and optionally the installation directory.
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

# Flags
KEEP_DATA=false
REMOVE_ALL=false
FORCE=false

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${RED}GeoIP Custom IP Blocker - Uninstallation${NC}                       ${BLUE}║${NC}"
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

usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Uninstall the GeoIP Custom IP Blocker application.

OPTIONS:
    --keep-data       Keep data directory (CSV exports, logs, cache)
                      Only removes container and Docker image
    
    --remove-all      Complete removal including all data
                      Removes container, image, and installation directory
    
    --force           Skip confirmation prompts (use with caution)
    
    -h, --help        Display this help message

EXAMPLES:
    # Standard uninstall (prompts for data retention):
    sudo ./uninstall.sh
    
    # Keep data, remove container and image only:
    sudo ./uninstall.sh --keep-data
    
    # Complete removal without prompts:
    sudo ./uninstall.sh --remove-all --force

EOF
    exit 0
}

################################################################################
# Parse Command Line Arguments
################################################################################

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --keep-data)
                KEEP_DATA=true
                shift
                ;;
            --remove-all)
                REMOVE_ALL=true
                shift
                ;;
            --force)
                FORCE=true
                shift
                ;;
            -h|--help)
                usage
                ;;
            *)
                print_error "Unknown option: $1"
                usage
                ;;
        esac
    done
    
    # Validate conflicting options
    if [ "$KEEP_DATA" = true ] && [ "$REMOVE_ALL" = true ]; then
        print_error "Cannot specify both --keep-data and --remove-all"
        exit 1
    fi
}

################################################################################
# Pre-flight Checks
################################################################################

check_docker() {
    if ! command -v docker &> /dev/null; then
        print_warning "Docker is not installed or not in PATH"
        print_info "Skipping Docker cleanup steps"
        return 1
    fi
    return 0
}

################################################################################
# Discover Installation
################################################################################

find_installation_directory() {
    print_section "Finding Installation"
    
    # Try to find installation directory by container mount points
    if docker ps -a --filter name="${CONTAINER_NAME}" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        MOUNT_INFO=$(docker inspect "${CONTAINER_NAME}" --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}' 2>/dev/null || echo "")
        
        if [ -n "$MOUNT_INFO" ]; then
            # Extract installation directory from mount path
            INSTALL_DIR=$(dirname "$MOUNT_INFO")
            print_info "Found installation via container mounts: ${INSTALL_DIR}"
        else
            INSTALL_DIR="$DEFAULT_INSTALL_DIR"
            print_warning "Could not detect installation directory from container"
            print_info "Using default: ${INSTALL_DIR}"
        fi
    else
        print_info "Container not found, using default directory: ${DEFAULT_INSTALL_DIR}"
        INSTALL_DIR="$DEFAULT_INSTALL_DIR"
    fi
    
    # Verify directory exists
    if [ -d "$INSTALL_DIR" ]; then
        print_success "Installation directory exists: ${INSTALL_DIR}"
    else
        print_warning "Installation directory not found: ${INSTALL_DIR}"
    fi
}

################################################################################
# Display Removal Plan
################################################################################

display_removal_plan() {
    print_section "Uninstallation Plan"
    
    echo -e "${YELLOW}The following items will be removed:${NC}"
    echo ""
    
    # Check what exists and will be removed
    CONTAINER_EXISTS=false
    IMAGE_EXISTS=false
    DATA_DIR_EXISTS=false
    
    if check_docker; then
        if docker ps -a --filter name="${CONTAINER_NAME}" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            CONTAINER_EXISTS=true
            CONTAINER_STATUS=$(docker ps -a --filter name="${CONTAINER_NAME}" --format '{{.Status}}')
            echo -e "  ${RED}✗${NC} Docker container: ${CONTAINER_NAME} (${CONTAINER_STATUS})"
        else
            echo -e "  ${GREEN}○${NC} Docker container: ${CONTAINER_NAME} (not found)"
        fi
        
        if docker image inspect "${DOCKER_IMAGE_FULL}" &> /dev/null; then
            IMAGE_EXISTS=true
            IMAGE_SIZE=$(docker image inspect "${DOCKER_IMAGE_FULL}" --format '{{.Size}}' | awk '{print $1/1024/1024 "MB"}')
            echo -e "  ${RED}✗${NC} Docker image: ${DOCKER_IMAGE_FULL} (~${IMAGE_SIZE})"
        else
            echo -e "  ${GREEN}○${NC} Docker image: ${DOCKER_IMAGE_FULL} (not found)"
        fi
    fi
    
    if [ -d "$INSTALL_DIR" ]; then
        DATA_DIR_EXISTS=true
        DIR_SIZE=$(du -sh "$INSTALL_DIR" 2>/dev/null | cut -f1 || echo "unknown")
        
        if [ "$KEEP_DATA" = true ]; then
            echo -e "  ${GREEN}✓${NC} Installation directory: ${INSTALL_DIR} (${DIR_SIZE}) - ${GREEN}KEEPING${NC}"
        elif [ "$REMOVE_ALL" = true ]; then
            echo -e "  ${RED}✗${NC} Installation directory: ${INSTALL_DIR} (${DIR_SIZE})"
            if [ -d "${INSTALL_DIR}/data" ]; then
                DATA_COUNT=$(find "${INSTALL_DIR}/data" -type f 2>/dev/null | wc -l || echo "0")
                echo -e "      - CSV exports: ${DATA_COUNT} files"
            fi
            if [ -d "${INSTALL_DIR}/tmp" ]; then
                LOG_SIZE=$(du -sh "${INSTALL_DIR}/tmp" 2>/dev/null | cut -f1 || echo "unknown")
                echo -e "      - Logs and cache: ${LOG_SIZE}"
            fi
        else
            echo -e "  ${YELLOW}?${NC} Installation directory: ${INSTALL_DIR} (${DIR_SIZE}) - ${YELLOW}WILL PROMPT${NC}"
        fi
    else
        echo -e "  ${GREEN}○${NC} Installation directory: ${INSTALL_DIR} (not found)"
    fi
    
    echo ""
    
    # Check if anything will be removed
    if [ "$CONTAINER_EXISTS" = false ] && [ "$IMAGE_EXISTS" = false ] && [ "$DATA_DIR_EXISTS" = false ]; then
        print_info "Nothing to uninstall - application not found"
        exit 0
    fi
}

################################################################################
# Confirmation
################################################################################

confirm_removal() {
    if [ "$FORCE" = true ]; then
        print_warning "Force mode enabled - skipping confirmation"
        return 0
    fi
    
    echo ""
    read -p "Do you want to proceed with uninstallation? [y/N]: " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        print_info "Uninstallation cancelled by user"
        exit 0
    fi
    echo ""
}

################################################################################
# Removal Operations
################################################################################

remove_container() {
    print_section "Removing Docker Container"
    
    if ! check_docker; then
        print_warning "Docker not available - skipping container removal"
        return 0
    fi
    
    if docker ps -a --filter name="${CONTAINER_NAME}" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        # Check if container is running
        if docker ps --filter name="${CONTAINER_NAME}" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            print_info "Stopping running container..."
            docker stop "${CONTAINER_NAME}" &> /dev/null
            print_success "Container stopped"
        fi
        
        print_info "Removing container..."
        docker rm "${CONTAINER_NAME}" &> /dev/null
        print_success "Container removed: ${CONTAINER_NAME}"
    else
        print_info "Container not found: ${CONTAINER_NAME}"
    fi
}

remove_docker_image() {
    print_section "Removing Docker Image"
    
    if ! check_docker; then
        print_warning "Docker not available - skipping image removal"
        return 0
    fi
    
    if docker image inspect "${DOCKER_IMAGE_FULL}" &> /dev/null; then
        print_info "Removing Docker image..."
        docker rmi "${DOCKER_IMAGE_FULL}" &> /dev/null || {
            print_warning "Failed to remove image (may be in use by other containers)"
            print_info "You can manually remove it later with: docker rmi ${DOCKER_IMAGE_FULL}"
            return 0
        }
        print_success "Docker image removed: ${DOCKER_IMAGE_FULL}"
    else
        print_info "Docker image not found: ${DOCKER_IMAGE_FULL}"
    fi
}

remove_installation_directory() {
    print_section "Removing Installation Directory"
    
    if [ ! -d "$INSTALL_DIR" ]; then
        print_info "Installation directory not found: ${INSTALL_DIR}"
        return 0
    fi
    
    # If --keep-data is specified, skip removal
    if [ "$KEEP_DATA" = true ]; then
        print_success "Keeping installation directory (--keep-data specified): ${INSTALL_DIR}"
        return 0
    fi
    
    # If --remove-all is specified, remove without prompting
    if [ "$REMOVE_ALL" = true ] || [ "$FORCE" = true ]; then
        print_info "Removing installation directory..."
        rm -rf "$INSTALL_DIR"
        print_success "Installation directory removed: ${INSTALL_DIR}"
        return 0
    fi
    
    # Otherwise, prompt user
    echo ""
    print_warning "Installation directory contains data:"
    if [ -d "${INSTALL_DIR}/data" ]; then
        DATA_COUNT=$(find "${INSTALL_DIR}/data" -type f 2>/dev/null | wc -l || echo "0")
        echo "  • CSV exports: ${DATA_COUNT} files in ${INSTALL_DIR}/data/"
    fi
    if [ -d "${INSTALL_DIR}/tmp" ]; then
        LOG_SIZE=$(du -sh "${INSTALL_DIR}/tmp" 2>/dev/null | cut -f1 || echo "unknown")
        echo "  • Logs and cache: ${LOG_SIZE} in ${INSTALL_DIR}/tmp/"
    fi
    echo ""
    
    read -p "Do you want to remove the installation directory and all data? [y/N]: " REMOVE_DATA
    if [[ "$REMOVE_DATA" =~ ^[Yy]$ ]]; then
        print_info "Removing installation directory..."
        rm -rf "$INSTALL_DIR"
        print_success "Installation directory removed: ${INSTALL_DIR}"
    else
        print_success "Installation directory preserved: ${INSTALL_DIR}"
        echo ""
        print_info "You can manually remove it later with:"
        print_info "  sudo rm -rf ${INSTALL_DIR}"
    fi
}

################################################################################
# Post-Uninstallation
################################################################################

display_completion_summary() {
    print_section "Uninstallation Complete"
    
    cat << EOF

${GREEN}✓ Uninstallation completed successfully!${NC}

${BLUE}═══ Summary ═══${NC}

EOF

    if check_docker; then
        if docker ps -a --filter name="${CONTAINER_NAME}" --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            echo -e "  ${YELLOW}⚠${NC} Container: ${CONTAINER_NAME} - ${YELLOW}STILL EXISTS${NC}"
        else
            echo -e "  ${GREEN}✓${NC} Container: ${CONTAINER_NAME} - removed"
        fi
        
        if docker image inspect "${DOCKER_IMAGE_FULL}" &> /dev/null; then
            echo -e "  ${YELLOW}⚠${NC} Image: ${DOCKER_IMAGE_FULL} - ${YELLOW}STILL EXISTS${NC}"
        else
            echo -e "  ${GREEN}✓${NC} Image: ${DOCKER_IMAGE_FULL} - removed"
        fi
    fi
    
    if [ -d "$INSTALL_DIR" ]; then
        echo -e "  ${GREEN}✓${NC} Data: ${INSTALL_DIR} - ${GREEN}PRESERVED${NC}"
        echo ""
        echo -e "${BLUE}Data preserved in:${NC} ${INSTALL_DIR}"
        echo -e "  • CSV exports: ${INSTALL_DIR}/data/"
        echo -e "  • Logs: ${INSTALL_DIR}/tmp/geo-ip-blocker.log"
        echo -e "  • Cache: ${INSTALL_DIR}/tmp/geodb_cache/"
        echo ""
        echo -e "To remove data manually:"
        echo -e "  ${YELLOW}sudo rm -rf ${INSTALL_DIR}${NC}"
    else
        echo -e "  ${GREEN}✓${NC} Data: ${INSTALL_DIR} - removed"
    fi
    
    echo ""
    echo -e "${GREEN}Thank you for using GeoIP Custom IP Blocker!${NC}"
    echo ""
}

################################################################################
# Main Uninstallation Flow
################################################################################

main() {
    print_header
    
    # Parse arguments
    parse_arguments "$@"
    
    # Find installation
    find_installation_directory
    
    # Display what will be removed
    display_removal_plan
    
    # Confirm removal
    confirm_removal
    
    # Perform removal operations
    remove_container
    remove_docker_image
    remove_installation_directory
    
    # Display completion summary
    display_completion_summary
}

# Run main uninstallation
main "$@"

exit 0
