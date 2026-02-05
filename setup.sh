#!/usr/bin/env bash
set -euo pipefail

# Trap for clean exit on interrupt
trap 'echo ""; echo "Setup interrupted."; exit 130' INT TERM

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

print_step() { printf "\n%b→%b %s\n" "$GREEN" "$NC" "$1"; }
print_success() { printf "%b✓%b %s\n" "$GREEN" "$NC" "$1"; }
print_warning() { printf "%b⚠%b %s\n" "$YELLOW" "$NC" "$1"; }
print_error() { printf "%b✗%b %s\n" "$RED" "$NC" "$1" >&2; }

confirm() {
  local prompt=$1 default=${2:-n}
  local reply
  read -r -p "$prompt " reply
  reply=${reply:-$default}
  [[ "$reply" =~ ^[Yy]$ ]]
}

command_exists() { command -v "$1" &>/dev/null; }

# Detect shell config
detect_shell_rc() {
  if [[ -n "${ZSH_VERSION:-}" ]] || [[ "${SHELL:-}" == *zsh* ]]; then
    echo "$HOME/.zshrc"
    return 0
  fi
  if [[ -f "$HOME/.bashrc" ]]; then
    echo "$HOME/.bashrc"
    return 0
  fi
  if [[ -f "$HOME/.bash_profile" ]]; then
    echo "$HOME/.bash_profile"
    return 0
  fi
  echo "$HOME/.profile"
}

RC_FILE=$(detect_shell_rc)

TAILMUX_FUNC='tailmux() { local host="${1:?Usage: tailmux <host>}"; ssh -t "$host" "PATH=\"/opt/homebrew/bin:/usr/local/bin:/home/linuxbrew/.linuxbrew/bin:$PATH\"; if command -v tmux >/dev/null 2>&1; then tmux attach || tmux new; else echo \"tmux not found on remote\" >&2; exit 127; fi"; }'

# --- Install Functions ---

install_homebrew() {
  if command_exists brew; then
    print_success "Homebrew already installed"
    return 0
  fi

  print_step "Installing Homebrew"
  print_warning "This will download and run the official Homebrew install script"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  
  # Add Homebrew to PATH for this session
  if [[ -f "/opt/homebrew/bin/brew" ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -f "/usr/local/bin/brew" ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
  
  if ! command_exists brew; then
    print_error "Homebrew installation failed"
    return 1
  fi
  print_success "Homebrew installed"
}

install_tailscale() {
  if command_exists tailscale; then
    print_success "Tailscale already installed"
    return 0
  fi

  print_step "Installing Tailscale"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    if command_exists brew; then
      brew install --cask tailscale
      print_success "Tailscale installed"
      print_warning "Open Tailscale from Applications to log in and connect to your tailnet"
    else
      print_warning "Install Tailscale manually: https://tailscale.com/download"
      return 0
    fi
  else
    if ! command_exists curl; then
      print_warning "curl not found. Install Tailscale manually: https://tailscale.com/download"
      return 0
    fi
    print_warning "This will download and run the official Tailscale install script"
    curl -fsSL https://tailscale.com/install.sh | sh
    print_success "Tailscale installed"
  fi
}

install_tmux() {
  if command_exists tmux; then
    print_success "tmux already installed"
    return 0
  fi

  print_step "Installing tmux"
  if command_exists brew; then
    brew install tmux
  elif command_exists apt-get; then
    sudo apt-get update -y && sudo apt-get install -y tmux
  elif command_exists dnf; then
    sudo dnf install -y tmux
  elif command_exists yum; then
    sudo yum install -y tmux
  elif command_exists pacman; then
    sudo pacman -S --noconfirm tmux
  else
    print_warning "Install tmux manually"
    return 1
  fi
  print_success "tmux installed"
}

install_shell_function() {
  touch "$RC_FILE"
  if grep -q "^tailmux()" "$RC_FILE" 2>/dev/null; then
    print_success "tailmux function already in $RC_FILE"
    return 0
  fi

  print_step "Adding tailmux function to $RC_FILE"
  {
    echo ""
    echo "# tailmux - tmux over Tailscale"
    echo "$TAILMUX_FUNC"
  } >> "$RC_FILE"
  print_success "tailmux function added to $RC_FILE"
}

# --- Uninstall Functions ---

uninstall_shell_function() {
  if ! grep -q "^tailmux()" "$RC_FILE" 2>/dev/null; then
    print_warning "tailmux function not found in $RC_FILE"
    return 0
  fi

  print_step "Removing tailmux function from $RC_FILE"
  # Remove the comment, function, and preceding blank line (works on both macOS and Linux)
  if [[ "$(uname -s)" == "Darwin" ]]; then
    sed -i '' '/^$/N;/\n# tailmux - tmux over Tailscale$/d' "$RC_FILE"
    sed -i '' '/^# tailmux - tmux over Tailscale$/d' "$RC_FILE"
    sed -i '' '/^tailmux() {/d' "$RC_FILE"
  else
    sed -i '/^$/N;/\n# tailmux - tmux over Tailscale$/d' "$RC_FILE"
    sed -i '/^# tailmux - tmux over Tailscale$/d' "$RC_FILE"
    sed -i '/^tailmux() {/d' "$RC_FILE"
  fi
  print_success "tailmux function removed from $RC_FILE"
}

uninstall_tmux() {
  if ! command_exists tmux; then
    print_warning "tmux not installed"
    return 0
  fi

  print_step "Uninstalling tmux"
  if command_exists brew; then
    brew uninstall tmux
  elif command_exists apt-get; then
    sudo apt-get remove -y tmux
  elif command_exists dnf; then
    sudo dnf remove -y tmux
  elif command_exists yum; then
    sudo yum remove -y tmux
  elif command_exists pacman; then
    sudo pacman -R --noconfirm tmux
  else
    print_warning "Uninstall tmux manually"
    return 1
  fi
  print_success "tmux uninstalled"
}

uninstall_tailscale() {
  if ! command_exists tailscale; then
    print_warning "Tailscale not installed"
    return 0
  fi

  print_step "Uninstalling Tailscale"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    if command_exists brew; then
      brew uninstall --cask tailscale
    else
      print_warning "Uninstall Tailscale manually from Applications"
      return 0
    fi
  elif command_exists apt-get; then
    sudo apt-get remove -y tailscale
  elif command_exists dnf; then
    sudo dnf remove -y tailscale
  elif command_exists yum; then
    sudo yum remove -y tailscale
  elif command_exists pacman; then
    sudo pacman -R --noconfirm tailscale
  else
    print_warning "Uninstall Tailscale manually"
    return 1
  fi
  print_success "Tailscale uninstalled"
}

# --- Main ---

do_install() {
  echo ""
  echo "tailmux setup"
  echo "============="
  echo ""
  local os_name
  os_name="$(uname -s)"

  if [[ "$os_name" == "Darwin" ]] && ! command_exists brew; then
    if confirm "Install Homebrew (required for Tailscale/tmux on macOS)? [Y/n]" "y"; then
      install_homebrew
    fi
  fi

  if confirm "Install Tailscale? [Y/n]" "y"; then
    install_tailscale
  fi

  if confirm "Install tmux? [Y/n]" "y"; then
    install_tmux
  fi

  install_shell_function

  echo ""
  print_success "Setup complete!"
  echo ""
  echo "Next steps:"
  echo "  1. Ensure SSH is enabled on the destination (macOS: Remote Login)"
  if [[ "$os_name" == "Darwin" ]]; then
    echo "  2. Open a new Terminal window, or run: source $RC_FILE"
  else
    echo "  2. Open a new terminal, or run: source $RC_FILE"
  fi
  echo "  3. Connect: tailmux <hostname>"
  echo ""
}

do_uninstall() {
  echo ""
  echo "tailmux uninstall"
  echo "================="
  echo ""

  if confirm "Remove tailmux shell function? [Y/n]" "y"; then
    uninstall_shell_function
  fi

  if confirm "Uninstall tmux? [y/N]" "n"; then
    uninstall_tmux
  fi

  if confirm "Uninstall Tailscale? [y/N]" "n"; then
    uninstall_tailscale
  fi

  echo ""
  print_success "Uninstall complete!"
  echo "Run: source $RC_FILE"
  echo ""
}

show_menu() {
  while true; do
    echo ""
    echo "tailmux"
    echo "======="
    echo ""
    echo "1) Install"
    echo "2) Uninstall"
    echo "3) Exit"
    echo ""
    read -r -p "Choose [1-3]: " choice
    case "$choice" in
      1) do_install; break ;;
      2) do_uninstall; break ;;
      3) exit 0 ;;
      *) print_error "Invalid choice" ;;
    esac
  done
}

# Handle arguments or show menu
case "${1:-}" in
  install) do_install ;;
  uninstall) do_uninstall ;;
  *) show_menu ;;
esac
