# shellcheck shell=bash
# Package and dependency management orchestration

install_homebrew() {
  if command_exists brew; then
    print_success "Homebrew already installed"
    return 0
  fi

  print_step "Installing Homebrew"
  print_warning "This will download and run the official Homebrew install script"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  # Add Homebrew to PATH for this session.
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

resolve_linux_operator_user() {
  local candidate
  for candidate in "${SUDO_USER:-}" "${USER:-}" "${LOGNAME:-}"; do
    if [[ -n "$candidate" && "$candidate" != "root" ]]; then
      echo "$candidate"
      return 0
    fi
  done

  candidate="$(id -un 2>/dev/null || true)"
  if [[ -n "$candidate" && "$candidate" != "root" ]]; then
    echo "$candidate"
    return 0
  fi

  echo ""
}

linux_tailscale_daemon_reachable() {
  if ! command_exists tailscale; then
    return 1
  fi
  # Use --json which succeeds even in NeedsLogin state, unlike plain 'tailscale status'
  tailscale status --json >/dev/null 2>&1
}

is_tailscale_authenticated() {
  if ! command_exists tailscale; then
    return 1
  fi
  local state
  state="$(tailscale status --json 2>/dev/null | grep -o '"BackendState":"[^"]*"' | head -1 || true)"
  [[ "$state" == *'"BackendState":"Running"'* ]]
}

ensure_linux_tailscaled_running() {
  local os_name="${1:?missing os name}"

  if [[ "$os_name" != "Linux" ]]; then
    return 0
  fi
  if ! command_exists tailscale; then
    return 0
  fi
  if linux_tailscale_daemon_reachable; then
    return 0
  fi

  print_step "Starting tailscaled service"
  if command_exists systemctl; then
    sudo systemctl enable --now tailscaled >/dev/null 2>&1 || true
  elif command_exists service; then
    sudo service tailscaled start >/dev/null 2>&1 || true
  elif command_exists rc-service; then
    sudo rc-service tailscaled start >/dev/null 2>&1 || true
  fi

  if linux_tailscale_daemon_reachable; then
    print_success "tailscaled service is running"
    return 0
  fi

  print_error "tailscaled is not running; cannot continue Linux setup."
  if command_exists systemctl; then
    print_warning "Check service status: sudo systemctl status tailscaled --no-pager"
    print_warning "Check logs: sudo journalctl -u tailscaled -n 80 --no-pager"
  fi
  return 1
}

ensure_linux_tailscale_operator() {
  local os_name="${1:?missing os name}"
  local operator_user

  if [[ "$os_name" != "Linux" ]]; then
    return 0
  fi
  if ! command_exists tailscale; then
    return 0
  fi

  if ! ensure_linux_tailscaled_running "$os_name"; then
    return 1
  fi

  # Check if tailscale is authenticated before trying to set operator
  if ! is_tailscale_authenticated; then
    print_warning "Tailscale needs authentication first."
    print_warning "Run: sudo tailscale up --ssh"
    print_warning "After login, set operator access: sudo tailscale set --operator=\$USER"
    return 0
  fi

  operator_user="$(resolve_linux_operator_user)"
  if [[ -z "$operator_user" ]]; then
    print_warning "Could not determine a non-root user for Tailscale operator setup."
    return 0
  fi

  print_step "Configuring Tailscale operator user: $operator_user"
  if sudo tailscale set --operator="$operator_user" >/dev/null 2>&1; then
    print_success "Configured Tailscale operator user '$operator_user'"
    return 0
  fi

  if sudo tailscale up --operator="$operator_user" >/dev/null 2>&1; then
    print_success "Configured Tailscale operator user '$operator_user'"
    return 0
  fi

  print_warning "Could not configure non-root Tailscale operator access automatically."
  print_warning "Run manually: sudo tailscale set --operator=$operator_user"
  print_warning "If 'set' is unsupported, run: sudo tailscale up --operator=$operator_user"
  return 0
}

ensure_linux_tailscale_ssh() {
  local os_name="${1:?missing os name}"

  if [[ "$os_name" != "Linux" ]]; then
    return 0
  fi
  if ! command_exists tailscale; then
    return 0
  fi
  if ! ensure_linux_tailscaled_running "$os_name"; then
    return 1
  fi

  print_step "Enabling Tailscale SSH on this device"
  if sudo tailscale set --ssh >/dev/null 2>&1; then
    print_success "Tailscale SSH enabled"
    return 0
  fi

  if ! is_tailscale_authenticated; then
    print_warning "Tailscale needs authentication first."
    print_warning "Run: sudo tailscale up --ssh"
    return 0
  fi

  print_warning "Could not enable Tailscale SSH automatically."
  print_warning "Run manually: sudo tailscale set --ssh"
  return 1
}

install_tailscale() {
  local os_name
  os_name="$(get_os_name)"

  print_step "Installing Tailscale"
  if [[ "$os_name" == "Darwin" ]]; then
    install_tailscale_macos
    return $?
  fi

  if command_exists tailscale; then
    print_success "Tailscale already installed"
    ensure_linux_tailscale_operator "$os_name"
    ensure_linux_tailscale_ssh "$os_name"
    return 0
  fi
  if ! command_exists curl; then
    print_warning "curl not found. Install Tailscale manually: https://tailscale.com/download"
    return 0
  fi

  print_warning "This will download and run the official Tailscale install script"
  curl -fsSL https://tailscale.com/install.sh | sh
  print_success "Tailscale installed"
  if ! ensure_linux_tailscaled_running "$os_name"; then
    return 1
  fi
  ensure_linux_tailscale_operator "$os_name"
  ensure_linux_tailscale_ssh "$os_name"
}

install_tmux() {
  if command_exists tmux; then
    print_success "tmux already installed"
    return 0
  fi

  print_step "Installing tmux"
  if ! package_manager_install tmux; then
    print_warning "Install tmux manually"
    return 1
  fi
  print_success "tmux installed"
}

davfs2_installed() {
  command -v mount.davfs >/dev/null 2>&1 || [[ -x /sbin/mount.davfs ]] || [[ -x /usr/sbin/mount.davfs ]]
}

print_davfs2_manual_install_hint() {
  linux_package_manager_install_hint davfs2
}

install_davfs2() {
  if davfs2_installed; then
    print_success "davfs2 already installed"
    return 0
  fi

  print_step "Installing davfs2 (Linux WebDAV mount support)"
  if command_exists apt-get; then
    sudo apt-get update -y && sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y davfs2
  elif ! linux_package_manager_install davfs2; then
    print_warning "Unsupported package manager for automatic davfs2 install"
    print_davfs2_manual_install_hint
    return 1
  fi

  if davfs2_installed; then
    print_success "davfs2 installed"
    return 0
  fi
  print_warning "davfs2 installation could not be verified"
  print_davfs2_manual_install_hint
  return 1
}

ensure_taildrive_mount_dependencies() {
  local os_name="${1:?missing os name}"
  if [[ "$os_name" != "Linux" ]]; then
    return 0
  fi

  if davfs2_installed; then
    print_success "davfs2 already installed (taildrive Linux mount support)"
    return 0
  fi

  print_warning "Linux taildrive mounting requires davfs2 (mount.davfs)."
  if confirm "Install davfs2 now for Linux mounting support? [Y/n]" "y"; then
    if ! install_davfs2; then
      print_warning "Continuing without verified davfs2 install; Linux mounting may fail until installed."
      print_davfs2_manual_install_hint
    fi
  else
    print_warning "Skipping davfs2 installation. Linux tailmount will fail until davfs2 is installed."
    print_davfs2_manual_install_hint
  fi
}

uninstall_davfs2() {
  if ! davfs2_installed; then
    print_warning "davfs2 not installed"
    return 0
  fi

  print_step "Uninstalling davfs2"
  if ! linux_package_manager_uninstall davfs2 true; then
    print_warning "Uninstall davfs2 manually"
    return 1
  fi
  print_success "davfs2 uninstalled"
}

uninstall_tmux() {
  if ! command_exists tmux; then
    print_warning "tmux not installed"
    return 0
  fi

  print_step "Uninstalling tmux"
  if ! package_manager_uninstall tmux; then
    print_warning "Uninstall tmux manually"
    return 1
  fi
  print_success "tmux uninstalled"
}

uninstall_tailscale() {
  local os_name
  os_name="$(get_os_name)"

  print_step "Uninstalling Tailscale"
  if [[ "$os_name" == "Darwin" ]]; then
    if ! uninstall_tailscale_macos; then
      return 1
    fi
    print_success "Tailscale uninstalled"
    return 0
  fi

  if ! command_exists tailscale; then
    print_warning "Tailscale not installed"
    return 0
  fi

  # Linux: proper uninstall with logout, service stop, and state cleanup.
  print_step "Logging out from Tailscale (removes device from tailnet)..."
  sudo tailscale logout 2>/dev/null || true

  print_step "Stopping Tailscale service..."
  sudo systemctl stop tailscaled 2>/dev/null || true
  sudo systemctl disable tailscaled 2>/dev/null || true

  print_step "Removing Tailscale package..."
  if ! linux_package_manager_uninstall tailscale true; then
    print_warning "Uninstall Tailscale manually"
    return 1
  fi

  print_step "Removing Tailscale state and configuration..."
  sudo rm -rf /var/lib/tailscale
  sudo rm -rf /etc/tailscale

  print_success "Tailscale uninstalled"
}
