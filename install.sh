#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# Bow — Pythonic Kubernetes DSL
# One-line installer for macOS and Linux
#
# Usage:
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/getbow/bow/main/install.sh)"
#
# Options (via env vars):
#   BOW_VERSION=0.3.1      Install a specific version
#   BOW_DIR=~/.bow         Installation directory (default: ~/.bow)
#   BOW_SOURCE=pypi        Install from PyPI instead of GitHub (default: github)
#   BOW_NO_MODIFY_PATH=1   Don't modify shell profile
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD='\033[1m'
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  RED='\033[0;31m'
  CYAN='\033[0;36m'
  RESET='\033[0m'
else
  BOLD='' GREEN='' YELLOW='' RED='' CYAN='' RESET=''
fi

info()  { echo -e "${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }
warn()  { echo -e "${YELLOW}warning:${RESET} $*"; }
error() { echo -e "${RED}error:${RESET} $*" >&2; }
success() { echo -e "${GREEN}✓${RESET} $*"; }

# ── Configuration ────────────────────────────────────────────
BOW_DIR="${BOW_DIR:-$HOME/.bow}"
BOW_BIN_DIR="${BOW_DIR}/bin"
BOW_VENV_DIR="${BOW_DIR}/venv"
BOW_VERSION="${BOW_VERSION:-}"    # empty = latest
BOW_SOURCE="${BOW_SOURCE:-github}" # "github" (default) or "pypi"
PACKAGE_NAME="bow-cli"
GITHUB_REPO="https://github.com/getbow/bow.git"

# Where we place the `bow` shim so it's on PATH
USER_BIN_DIR="${HOME}/.local/bin"

# ── Platform detection ───────────────────────────────────────
detect_platform() {
  local os
  os="$(uname -s)"
  case "$os" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)
      error "Unsupported operating system: $os"
      exit 1
      ;;
  esac
  info "Detected platform: ${PLATFORM}"
}

# ── Python detection ─────────────────────────────────────────
find_python() {
  local candidates=("python3.13" "python3.12" "python3.11" "python3")
  PYTHON_CMD=""

  for cmd in "${candidates[@]}"; do
    if command -v "$cmd" &>/dev/null; then
      local version
      version="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'  2>/dev/null || true)"
      if [[ -n "$version" ]]; then
        local major minor
        major="${version%%.*}"
        minor="${version#*.}"
        if (( major == 3 && minor >= 11 )); then
          PYTHON_CMD="$cmd"
          info "Found Python ${version} → $(command -v "$cmd")"
          return
        fi
      fi
    fi
  done

  error "Python 3.11+ is required but not found."
  echo ""
  if [[ "$PLATFORM" == "macos" ]]; then
    echo "  Install with Homebrew:"
    echo "    brew install python@3.12"
  else
    echo "  Install with your package manager, e.g.:"
    echo "    sudo apt install python3.12 python3.12-venv   # Debian/Ubuntu"
    echo "    sudo dnf install python3.12                    # Fedora"
  fi
  echo ""
  exit 1
}

# ── Ensure venv module is available ──────────────────────────
check_venv_module() {
  if ! "$PYTHON_CMD" -c "import venv" &>/dev/null; then
    error "Python venv module is not available."
    echo ""
    if [[ "$PLATFORM" == "linux" ]]; then
      local version
      version="$("$PYTHON_CMD" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
      echo "  Install it with:"
      echo "    sudo apt install python${version}-venv   # Debian/Ubuntu"
      echo "    sudo dnf install python3-libs             # Fedora"
    fi
    echo ""
    exit 1
  fi
}

# ── Ensure git is available (for github install) ─────────────
check_git() {
  if [[ "$BOW_SOURCE" == "github" ]] && ! command -v git &>/dev/null; then
    error "git is required for GitHub installation but not found."
    echo ""
    if [[ "$PLATFORM" == "macos" ]]; then
      echo "  Install with:  xcode-select --install"
    else
      echo "  Install with:  sudo apt install git"
    fi
    echo ""
    exit 1
  fi
}

# ── Install ──────────────────────────────────────────────────
install_bow() {
  # Clean previous installation
  if [[ -d "$BOW_VENV_DIR" ]]; then
    warn "Existing installation found. Reinstalling..."
    rm -rf "$BOW_VENV_DIR"
  fi

  # Create installation directory
  mkdir -p "$BOW_DIR" "$BOW_BIN_DIR"

  # Create isolated virtual environment
  info "Creating virtual environment..."
  "$PYTHON_CMD" -m venv "$BOW_VENV_DIR"

  # Upgrade pip silently
  "$BOW_VENV_DIR/bin/python" -m pip install --upgrade pip --quiet 2>/dev/null

  # Install bow-cli
  if [[ "$BOW_SOURCE" == "pypi" ]]; then
    local install_target="$PACKAGE_NAME"
    if [[ -n "$BOW_VERSION" ]]; then
      install_target="${PACKAGE_NAME}==${BOW_VERSION}"
    fi
    info "Installing ${install_target} from PyPI..."
    "$BOW_VENV_DIR/bin/python" -m pip install "$install_target" --quiet
  else
    # Install from GitHub
    local git_ref=""
    if [[ -n "$BOW_VERSION" ]]; then
      git_ref="@v${BOW_VERSION}"
    fi
    info "Installing from GitHub (${GITHUB_REPO})..."
    "$BOW_VENV_DIR/bin/python" -m pip install "git+${GITHUB_REPO}${git_ref}" --quiet
  fi

  # Verify installation
  if [[ ! -x "$BOW_VENV_DIR/bin/bow" ]]; then
    error "Installation failed — 'bow' executable not found in venv."
    exit 1
  fi

  local installed_version
  installed_version="$("$BOW_VENV_DIR/bin/bow" --version 2>/dev/null || echo "unknown")"
  success "Installed ${installed_version}"
}

# ── Create shim ──────────────────────────────────────────────
create_shim() {
  mkdir -p "$USER_BIN_DIR"

  # Create a thin wrapper script (more robust than symlinks across environments)
  cat > "$USER_BIN_DIR/bow" << 'SHIM'
#!/usr/bin/env bash
# Auto-generated by bow installer — do not edit
BOW_VENV="BOW_VENV_PLACEHOLDER"
exec "$BOW_VENV/bin/bow" "$@"
SHIM

  # Replace placeholder with actual path
  sed -i'' -e "s|BOW_VENV_PLACEHOLDER|${BOW_VENV_DIR}|g" "$USER_BIN_DIR/bow"
  chmod +x "$USER_BIN_DIR/bow"

  success "Created shim → ${USER_BIN_DIR}/bow"
}

# ── Update PATH in shell profile ─────────────────────────────
update_path() {
  if [[ "${BOW_NO_MODIFY_PATH:-}" == "1" ]]; then
    return
  fi

  # Check if already on PATH
  if echo "$PATH" | tr ':' '\n' | grep -qx "$USER_BIN_DIR"; then
    return
  fi

  local path_line="export PATH=\"${USER_BIN_DIR}:\$PATH\""
  local shell_name
  shell_name="$(basename "$SHELL")"

  local profiles=()
  case "$shell_name" in
    zsh)
      profiles=("$HOME/.zshrc")
      ;;
    bash)
      if [[ "$PLATFORM" == "macos" ]]; then
        profiles=("$HOME/.bash_profile" "$HOME/.bashrc")
      else
        profiles=("$HOME/.bashrc")
      fi
      ;;
    fish)
      # Fish uses a different syntax
      local fish_path_line="fish_add_path ${USER_BIN_DIR}"
      local fish_config="$HOME/.config/fish/config.fish"
      mkdir -p "$(dirname "$fish_config")"
      if [[ -f "$fish_config" ]] && grep -qF "$USER_BIN_DIR" "$fish_config"; then
        return
      fi
      echo "$fish_path_line" >> "$fish_config"
      info "Added PATH to ${fish_config}"
      NEED_RESTART=1
      return
      ;;
    *)
      profiles=("$HOME/.profile")
      ;;
  esac

  for profile in "${profiles[@]}"; do
    if [[ -f "$profile" ]]; then
      if grep -qF "${USER_BIN_DIR}" "$profile"; then
        return  # Already configured
      fi
    fi
  done

  # Write to the first profile
  local target_profile="${profiles[0]}"
  echo "" >> "$target_profile"
  echo "# Added by bow installer" >> "$target_profile"
  echo "$path_line" >> "$target_profile"
  info "Added PATH to ${target_profile}"
  NEED_RESTART=1
}

# ── Uninstall hint ───────────────────────────────────────────
print_uninstall_hint() {
  echo ""
  echo -e "  ${BOLD}To uninstall:${RESET}"
  echo "    rm -rf ${BOW_DIR} ${USER_BIN_DIR}/bow"
  echo ""
}

# ── Summary ──────────────────────────────────────────────────
print_summary() {
  echo ""
  echo -e "  ${GREEN}${BOLD}bow has been installed!${RESET}"
  echo ""
  echo -e "  ${BOLD}Location:${RESET}  ${BOW_DIR}"
  echo -e "  ${BOLD}Command:${RESET}   ${USER_BIN_DIR}/bow"
  echo ""

  if [[ "${NEED_RESTART:-}" == "1" ]]; then
    echo -e "  ${YELLOW}→ Restart your terminal or run:${RESET}"
    local shell_name
    shell_name="$(basename "$SHELL")"
    case "$shell_name" in
      zsh)  echo "    source ~/.zshrc" ;;
      bash) echo "    source ~/.bashrc" ;;
      fish) echo "    source ~/.config/fish/config.fish" ;;
      *)    echo "    source ~/.profile" ;;
    esac
    echo ""
  fi

  echo "  Get started:"
  echo "    bow --help"
  echo ""
}

# ── Main ─────────────────────────────────────────────────────
main() {
  echo ""
  echo -e "${BOLD}  ╔══════════════════════════════════════╗${RESET}"
  echo -e "${BOLD}  ║       ${CYAN}bow${RESET}${BOLD} installer                  ║${RESET}"
  echo -e "${BOLD}  ║       Pythonic Kubernetes DSL        ║${RESET}"
  echo -e "${BOLD}  ╚══════════════════════════════════════╝${RESET}"
  echo ""

  detect_platform
  find_python
  check_venv_module
  check_git
  install_bow
  create_shim
  update_path
  print_summary
}

main "$@"
