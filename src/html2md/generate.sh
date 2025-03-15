#!/usr/bin/env bash

# Ensure script execution stops on errors
set -euo pipefail

# Define the base directory as the script's location
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Define the directory structure
DIRECTORIES=(
    "$BASE_DIR/config"
    "$BASE_DIR/utils"
    "$BASE_DIR/cookies"
    "$BASE_DIR/markdown"
    "$BASE_DIR/network"
    "$BASE_DIR/cli"
    "$BASE_DIR/tests"
)

# Define the files to be created
FILES=(
    "$BASE_DIR/config/loader.py"
    "$BASE_DIR/config/config.json"
    "$BASE_DIR/utils/logger.py"
    "$BASE_DIR/utils/formatter.py"
    "$BASE_DIR/utils/parser.py"
    "$BASE_DIR/cookies/chrome_loader.py"
    "$BASE_DIR/cookies/session_manager.py"
    "$BASE_DIR/markdown/converter.py"
    "$BASE_DIR/markdown/trimmer.py"
    "$BASE_DIR/network/request_handler.py"
    "$BASE_DIR/cli/main.py"
    "$BASE_DIR/tests/test_converter.py"
    "$BASE_DIR/tests/test_trimmer.py"
    "$BASE_DIR/tests/test_cookie_loader.py"
    "$BASE_DIR/tests/test_request_handler.py"
)

# Create directories if they do not exist
for dir in "${DIRECTORIES[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir" || { echo "Failed to create $dir"; exit 1; }
        echo "Created directory: $dir"
    fi
    touch "$dir/__init__.py" || { echo "Failed to create $dir/__init__.py"; exit 1; }
done

# Create files if they do not exist
for file in "${FILES[@]}"; do
    if [ ! -f "$file" ]; then
        touch "$file" || { echo "Failed to create $file"; exit 1; }
        echo "Created file: $file"
    fi
done

echo "Directory and file structure setup complete."
