#!/usr/bin/env bash
# ==============================================================================
#  Abel — One-Click macOS Installer
#  Property of Student Led Business Solutions
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

chmod +x "$DIR/installer/setup_mac.sh" 2>/dev/null || true
bash "$DIR/installer/setup_mac.sh"
