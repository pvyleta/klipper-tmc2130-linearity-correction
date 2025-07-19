#!/bin/bash

# TMC2130 Linearity Correction Plugin Installation Script
# 
# This script installs the TMC2130 linearity correction plugin for Klipper
# 
# Usage: ./install.sh [klipper_path]
# 
# If klipper_path is not provided, it will try to auto-detect the Klipper installation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_msg() {
    echo -e "${2}${1}${NC}"
}

print_msg "TMC2130 Linearity Correction Plugin Installer" "$BLUE"
print_msg "=============================================" "$BLUE"

# Determine Klipper path
if [ -n "$1" ]; then
    KLIPPER_PATH="$1"
else
    # Try to auto-detect Klipper installation
    if [ -d "$HOME/klipper" ]; then
        KLIPPER_PATH="$HOME/klipper"
    elif [ -d "/opt/klipper" ]; then
        KLIPPER_PATH="/opt/klipper"
    else
        print_msg "Error: Could not find Klipper installation." "$RED"
        print_msg "Please specify the path to your Klipper installation:" "$YELLOW"
        print_msg "  ./install.sh /path/to/klipper" "$YELLOW"
        exit 1
    fi
fi

print_msg "Using Klipper path: $KLIPPER_PATH" "$GREEN"

# Verify Klipper installation
if [ ! -d "$KLIPPER_PATH/klippy/extras" ]; then
    print_msg "Error: Invalid Klipper path. Could not find klippy/extras directory." "$RED"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if the plugin file exists
PLUGIN_FILE="$SCRIPT_DIR/tmc2130_linearity.py"
if [ ! -f "$PLUGIN_FILE" ]; then
    print_msg "Error: Plugin file not found: $PLUGIN_FILE" "$RED"
    exit 1
fi

# Install the plugin
EXTRAS_DIR="$KLIPPER_PATH/klippy/extras"
TARGET_FILE="$EXTRAS_DIR/tmc2130_linearity.py"

print_msg "Installing plugin to: $TARGET_FILE" "$YELLOW"

# Create backup if file already exists
if [ -f "$TARGET_FILE" ]; then
    BACKUP_FILE="$TARGET_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    print_msg "Backing up existing file to: $BACKUP_FILE" "$YELLOW"
    cp "$TARGET_FILE" "$BACKUP_FILE"
fi

# Copy the plugin file
cp "$PLUGIN_FILE" "$TARGET_FILE"

# Set appropriate permissions
chmod 644 "$TARGET_FILE"

print_msg "Plugin installed successfully!" "$GREEN"

# Check if example config exists and offer to copy it
EXAMPLE_CONFIG="$SCRIPT_DIR/example_config.cfg"
if [ -f "$EXAMPLE_CONFIG" ]; then
    print_msg "" ""
    print_msg "Example configuration file available at:" "$BLUE"
    print_msg "  $EXAMPLE_CONFIG" "$BLUE"
    print_msg "" ""
    print_msg "You can copy relevant sections to your printer.cfg file." "$YELLOW"
fi

print_msg "" ""
print_msg "Installation complete!" "$GREEN"
print_msg "" ""
print_msg "Next steps:" "$BLUE"
print_msg "1. Add TMC2130 linearity correction sections to your printer.cfg" "$YELLOW"
print_msg "2. Restart Klipper to load the plugin" "$YELLOW"
print_msg "3. Use the provided G-code commands to configure and tune" "$YELLOW"
print_msg "" ""
print_msg "Available G-code commands:" "$BLUE"
print_msg "  TMC2130_SET_LINEARITY STEPPER=stepper_x FACTOR=1100" "$YELLOW"
print_msg "  TMC2130_GET_LINEARITY STEPPER=stepper_x" "$YELLOW"
print_msg "  TMC2130_SET_ALGORITHM STEPPER=stepper_x ALGORITHM=constant_torque" "$YELLOW"
print_msg "" ""
print_msg "For detailed configuration instructions, see README.md" "$BLUE"

# Check if we can restart Klipper automatically
if command -v systemctl &> /dev/null; then
    print_msg "" ""
    read -p "Would you like to restart Klipper now? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_msg "Restarting Klipper..." "$YELLOW"
        if sudo systemctl restart klipper; then
            print_msg "Klipper restarted successfully!" "$GREEN"
        else
            print_msg "Failed to restart Klipper. Please restart manually." "$RED"
        fi
    else
        print_msg "Please restart Klipper manually to load the plugin." "$YELLOW"
    fi
fi

print_msg "" ""
print_msg "Installation script completed!" "$GREEN"
