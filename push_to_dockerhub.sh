#!/bin/bash

################################################################################
# GeoIP Custom IP Blocker - Push to Docker Hub Script
# This script optionally pushes the Docker image to Docker Hub.
################################################################################

# Color codes
set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'



# Configuration

DOCKER_IMAGE_NAME="egori4/geo-ip-custom-block"
DOCKER_IMAGE_TAG="1.4.0"
DOCKER_IMAGE_FULL="${DOCKER_IMAGE_NAME}:${DOCKER_IMAGE_TAG}"

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

push_to_dockerhub() {
    print_section "Push to Docker Hub"
    
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


        print_info "Tagging image ${DOCKER_IMAGE_FULL} as latest..."
        docker tag "${DOCKER_IMAGE_FULL}" egori4/geo-ip-custom-block:latest

        # Push latest tag
        print_info "Pushing latest tag to Docker Hub..."
        docker push egori4/geo-ip-custom-block:latest


    else
        print_info "Skipping Docker Hub push"
        print_info "Users will use the local image archive from the package"
    fi
}

push_to_dockerhub