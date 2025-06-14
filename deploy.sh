#!/bin/bash
set -e

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}====== html2md Deployment Script ======${NC}"

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Error: This script must be run from the html2md project root directory${NC}"
    exit 1
fi

# Step 1: Run tests
echo -e "\n${YELLOW}Running tests...${NC}"
if python -m pytest; then
    echo -e "${GREEN}✅ Tests passed${NC}"
else
    echo -e "${RED}❌ Tests failed. Fix before deploying.${NC}"
    exit 1
fi

# Step 2: Build with Poetry
echo -e "\n${YELLOW}Building package...${NC}"
if poetry build; then
    echo -e "${GREEN}✅ Package built successfully${NC}"
else
    echo -e "${RED}❌ Build failed${NC}"
    exit 1
fi

# Step 3: Install with pipx
echo -e "\n${YELLOW}Installing globally with pipx...${NC}"
if pipx install . --force; then
    echo -e "${GREEN}✅ Package installed globally${NC}"
else
    echo -e "${RED}❌ Global installation failed${NC}"
    exit 1
fi

# Step 4: Verify installation
echo -e "\n${YELLOW}Verifying installation...${NC}"
if which html2md > /dev/null; then
    echo -e "${GREEN}✅ Verification successful! html2md is available.${NC}"

    # Get version info
    VERSION=$(html2md --version 2>/dev/null || echo "Unknown")

    echo -e "\n${GREEN}Deployment complete!${NC}"
    echo -e "Version: ${VERSION}"
    echo -e "You can now use ${YELLOW}html2md${NC} from anywhere."
    echo -e "Example: ${YELLOW}html2md batch urls.txt --output-dir output${NC}"
else
    echo -e "${RED}❌ Verification failed. The commands are not available on PATH.${NC}"
    exit 1
fi

echo -e "\n${YELLOW}====== Deployment Complete ======${NC}"
