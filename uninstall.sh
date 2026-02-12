#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Bow — Uninstaller
#
# Usage:
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/getbow/bow/main/uninstall.sh)"
# ──────────────────────────────────────────────────────────────
set -euo pipefail

BOLD='\033[1m' GREEN='\033[0;32m' YELLOW='\033[0;33m' RED='\033[0;31m' CYAN='\033[0;36m' RESET='\033[0m'

BOW_DIR="${BOW_DIR:-$HOME/.bow}"
USER_BIN_DIR="${HOME}/.local/bin"

echo ""
echo -e "${BOLD}Uninstalling bow...${RESET}"
echo ""

# Remove installation directory
if [[ -d "$BOW_DIR" ]]; then
  rm -rf "$BOW_DIR"
  echo -e "${GREEN}✓${RESET} Removed ${BOW_DIR}"
else
  echo -e "${YELLOW}  ${BOW_DIR} not found (skipped)${RESET}"
fi

# Remove shim
if [[ -f "$USER_BIN_DIR/bow" ]]; then
  rm -f "$USER_BIN_DIR/bow"
  echo -e "${GREEN}✓${RESET} Removed ${USER_BIN_DIR}/bow"
else
  echo -e "${YELLOW}  ${USER_BIN_DIR}/bow not found (skipped)${RESET}"
fi

echo ""
echo -e "${BOLD}bow has been uninstalled.${RESET}"
echo ""
echo -e "${YELLOW}Note:${RESET} The PATH entry in your shell profile was not removed."
echo "  You can manually remove the 'Added by bow installer' line from your shell config."
echo ""
