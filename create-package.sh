#!/bin/bash

################################################################################
# GeoIP Custom IP Blocker - Package Creation Script
# Version: 1.3.0
# 
# This script creates a complete installation package including:
# - Docker image archive
# - Installation/uninstallation scripts
# - Documentation
################################################################################

set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
PACKAGE_NAME="geo-ip-custom-block-v1.3.0"
DOCKER_IMAGE_NAME="egori4/geo-ip-custom-block"
DOCKER_IMAGE_TAG="1.3.0"
DOCKER_IMAGE_FULL="${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}"

print_header() {
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${GREEN}GeoIP Custom IP Blocker - Package Creation${NC}                     ${BLUE}║${NC}"
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

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_section() {
    echo ""
    echo -e "${BLUE}═══${NC} $1"
    echo ""
}

# Check prerequisites
check_prerequisites() {
    print_section "Checking Prerequisites"
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    print_success "Docker is installed"
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running"
        exit 1
    fi
    print_success "Docker daemon is running"
}

# Build Docker image
build_docker_image() {
    print_section "Building Docker Image"
    
    if [ ! -f "Dockerfile" ]; then
        print_error "Dockerfile not found in current directory"
        exit 1
    fi
    
    print_info "Building image: ${DOCKER_IMAGE_FULL}"
    docker build -t "${DOCKER_IMAGE_FULL}" .
    
    print_success "Docker image built successfully"
    
    # Display image size
    IMAGE_SIZE=$(docker image inspect "${DOCKER_IMAGE_FULL}" --format '{{.Size}}' | awk '{printf "%.1f MB", $1/1024/1024}')
    print_info "Image size: ${IMAGE_SIZE}"
}

# Export Docker image
export_docker_image() {
    print_section "Exporting Docker Image"
    
    print_info "Exporting image to archive (this may take a few minutes)..."
    docker save "${DOCKER_IMAGE_FULL}" -o geo-ip-blocker-image.tar
    
    print_success "Image exported: geo-ip-blocker-image.tar"
    
    # Display archive size
    ARCHIVE_SIZE=$(du -h geo-ip-blocker-image.tar | cut -f1)
    print_info "Archive size: ${ARCHIVE_SIZE}"
}

# Create package directory
create_package() {
    print_section "Creating Installation Package"
    
    # Create temporary package directory
    PACKAGE_DIR="${PACKAGE_NAME}"
    rm -rf "${PACKAGE_DIR}"
    mkdir -p "${PACKAGE_DIR}"
    
    print_info "Copying files to package..."
    
    # Copy Docker image archive
    cp geo-ip-blocker-image.tar "${PACKAGE_DIR}/"
    print_success "Added: geo-ip-blocker-image.tar"
    
    # Copy installation scripts
    cp install.sh "${PACKAGE_DIR}/"
    chmod +x "${PACKAGE_DIR}/install.sh"
    print_success "Added: install.sh"
    
    cp uninstall.sh "${PACKAGE_DIR}/"
    chmod +x "${PACKAGE_DIR}/uninstall.sh"
    print_success "Added: uninstall.sh"
    
    # Copy configuration example
    cp .env.example "${PACKAGE_DIR}/"
    print_success "Added: .env.example"
    
    # Copy documentation
    cp INSTALLATION.md "${PACKAGE_DIR}/"
    print_success "Added: INSTALLATION.md"
    
    cp README.md "${PACKAGE_DIR}/"
    print_success "Added: README.md"
    
    # Create package archive
    print_info "Creating package archive..."
    tar -czf "${PACKAGE_NAME}.tar.gz" "${PACKAGE_DIR}"
    
    PACKAGE_SIZE=$(du -h "${PACKAGE_NAME}.tar.gz" | cut -f1)
    print_success "Package created: ${PACKAGE_NAME}.tar.gz (${PACKAGE_SIZE})"
    
    # Cleanup temporary directory
    rm -rf "${PACKAGE_DIR}"
}

# Push to Docker Hub (optional)
push_to_dockerhub() {
    print_section "Push to Docker Hub (Optional)"
    
    echo "Do you want to push the image to Docker Hub?"
    echo "Repository: ${DOCKER_IMAGE_FULL}"
    read -p "Push to Docker Hub? [y/N]: " PUSH_CONFIRM
    
    if [[ "$PUSH_CONFIRM" =~ ^[Yy]$ ]]; then
        print_info "Pushing image to Docker Hub..."
        
        # Check if logged in
        if ! docker info 2>/dev/null | grep -q "Username"; then
            print_info "You need to login to Docker Hub first"
            docker login
        fi
        
        docker push "${DOCKER_IMAGE_FULL}"
        print_success "Image pushed to Docker Hub: ${DOCKER_IMAGE_FULL}"
        
        echo ""
        print_info "Image is now available at:"
        print_info "  docker pull ${DOCKER_IMAGE_FULL}"
    else
        print_info "Skipping Docker Hub push"
        print_info "Users will use the local image archive from the package"
    fi
}

# Display summary
display_summary() {
    print_section "Package Creation Complete!"
    
    cat << EOF

${GREEN}✓ Installation package created successfully!${NC}

${BLUE}═══ Package Contents ═══${NC}
  • Docker image: ${DOCKER_IMAGE_FULL}
  • Package file: ${PACKAGE_NAME}.tar.gz
  • Package size: $(du -h "${PACKAGE_NAME}.tar.gz" | cut -f1)

${BLUE}═══ Package Includes ═══${NC}
  • geo-ip-blocker-image.tar  - Docker image archive
  • install.sh                 - Installation script
  • uninstall.sh               - Uninstallation script
  • .env.example               - Configuration template
  • INSTALLATION.md            - Installation guide
  • README.md                  - Full documentation

${BLUE}═══ Distribution ═══${NC}

${GREEN}Option 1: Docker Hub + Package${NC} (Recommended)
  1. Push image to Docker Hub (done if you selected 'y' above)
  2. Distribute: ${PACKAGE_NAME}.tar.gz
  3. Users will pull from Docker Hub (faster)
  4. Falls back to local archive if Docker Hub unavailable

${GREEN}Option 2: Package Only${NC}
  1. Distribute: ${PACKAGE_NAME}.tar.gz
  2. Users install from local image archive
  3. No internet required for Docker image

${BLUE}═══ User Installation ═══${NC}

Extract and install:
  tar -xzf ${PACKAGE_NAME}.tar.gz
  cd ${PACKAGE_NAME}
  chmod +x install.sh uninstall.sh
  sudo ./install.sh

${BLUE}═══ Next Steps ═══${NC}

1. ${YELLOW}Test the package:${NC}
   tar -xzf ${PACKAGE_NAME}.tar.gz
   cd ${PACKAGE_NAME}
   sudo ./install.sh
   
2. ${YELLOW}Verify installation:${NC}
   docker ps -a --filter name=geo-ip-blocker
   docker start geo-ip-blocker
   
3. ${YELLOW}Distribute package:${NC}
   - Upload ${PACKAGE_NAME}.tar.gz to file server
   - Or send directly to users
   - Include INSTALLATION.md instructions

EOF
}

# Main execution
main() {
    print_header
    
    check_prerequisites
    build_docker_image
    export_docker_image
    create_package
    push_to_dockerhub
    display_summary
}

main

exit 0
