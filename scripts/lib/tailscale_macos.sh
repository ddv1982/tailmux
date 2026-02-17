# shellcheck shell=bash
# macOS-specific Tailscale install/uninstall helpers

detect_macos_tailscale_state() {
  local brew_bin
  local brew_prefix=""
  local formula_installed=false
  local formula_linked=false
  local cask_installed=false
  local tailscale_in_path=false
  local app_bundle_present=false

  if command_exists brew; then
    brew_bin="$(command -v brew)"
    brew_prefix="$("$brew_bin" --prefix 2>/dev/null || true)"
    if "$brew_bin" list --formula tailscale >/dev/null 2>&1; then
      formula_installed=true
      if [[ -n "$brew_prefix" && -x "$brew_prefix/bin/tailscale" ]]; then
        formula_linked=true
      fi
    fi
    if "$brew_bin" list --cask tailscale-app >/dev/null 2>&1 || "$brew_bin" list --cask tailscale >/dev/null 2>&1; then
      cask_installed=true
    fi
  fi

  if command_exists tailscale; then
    tailscale_in_path=true
  fi
  if [[ -d "/Applications/Tailscale.app" || -d "$HOME/Applications/Tailscale.app" ]]; then
    app_bundle_present=true
  fi

  if [[ "$formula_installed" == true ]]; then
    if [[ "$formula_linked" == true ]]; then
      echo "formula"
    else
      echo "formula_unlinked"
    fi
    return 0
  fi
  if [[ "$cask_installed" == true ]]; then
    echo "cask"
    return 0
  fi
  if [[ "$app_bundle_present" == true || "$tailscale_in_path" == true ]]; then
    echo "standalone"
    return 0
  fi

  echo "missing"
}

detect_macos_tailscale_binary() {
  if command_exists tailscale; then
    command -v tailscale
    return 0
  fi
  echo ""
}

tailscale_daemon_reachable() {
  local status_output=""
  if ! command_exists tailscale; then
    return 1
  fi

  status_output="$(tailscale status 2>&1 || true)"
  if [[ "$status_output" == *"failed to connect to local Tailscale service"* || "$status_output" == *"failed to connect to local Tailscaled process"* ]]; then
    return 1
  fi
  return 0
}

wait_for_tailscale_daemon() {
  local max_attempts="${1:-10}"
  local delay="${2:-1}"
  local attempt=1

  while [[ $attempt -le $max_attempts ]]; do
    if tailscale_daemon_reachable; then
      return 0
    fi
    sleep "$delay"
    ((attempt++))
  done
  return 1
}

start_macos_tailscale_daemon() {
  local brew_bin="${1:?missing brew path}"

  # tailscaled requires root privileges to create the TUN interface
  sudo "$brew_bin" services start tailscale >/dev/null 2>&1
}

install_tailscale_macos() {
  if ! command_exists brew; then
    print_warning "Install Tailscale manually: https://tailscale.com/download"
    return 0
  fi

  local brew_bin
  local brew_prefix
  local tailscale_state
  local tailscale_bin=""

  brew_bin="$(command -v brew)"
  brew_prefix="$("$brew_bin" --prefix 2>/dev/null || true)"
  tailscale_state="$(detect_macos_tailscale_state)"
  tailscale_bin="$(detect_macos_tailscale_binary)"

  if [[ "$tailscale_state" == "standalone" ]]; then
    print_error "Detected standalone/App Store Tailscale install on macOS."
    if [[ -n "$tailscale_bin" ]]; then
      print_warning "Detected tailscale binary at: $tailscale_bin"
    fi
    print_warning "To avoid conflicts, remove the standalone/App Store app first, then rerun setup."
    print_warning "Expected path to remove: /Applications/Tailscale.app (or ~/Applications/Tailscale.app)"
    return 1
  fi

  if [[ "$tailscale_state" == "cask" ]]; then
    print_warning "Detected macOS Tailscale install without 'tailscale drive' CLI support."
    print_warning "Taildrive shell functions need the Homebrew CLI formula."
    if ! confirm "Migrate to the Homebrew CLI version now? [Y/n]" "y"; then
      print_error "Cannot continue setup without migrating to the Homebrew CLI formula."
      return 1
    fi
  fi

  if [[ "$tailscale_state" == "formula_unlinked" ]]; then
    print_step "Linking Homebrew Tailscale formula"
    "$brew_bin" link tailscale
    tailscale_state="formula"
  fi

  if [[ "$tailscale_state" != "formula" ]]; then
    if [[ "$tailscale_state" == "cask" ]]; then
      print_step "Removing Homebrew Tailscale cask"
      HOMEBREW_NO_AUTOREMOVE=1 "$brew_bin" uninstall --cask --ignore-dependencies tailscale-app 2>/dev/null || HOMEBREW_NO_AUTOREMOVE=1 "$brew_bin" uninstall --cask --ignore-dependencies tailscale
    fi

    # Install open-source CLI version (not the GUI cask) for full 'tailscale drive' support
    "$brew_bin" install tailscale
  else
    local outdated_output=""
    local upgrade_output=""
    local upgrade_error_summary=""

    print_success "Tailscale already installed (Homebrew formula)"
    print_step "Checking whether Homebrew Tailscale formula is outdated"
    if outdated_output="$("$brew_bin" outdated --formula tailscale 2>/dev/null)"; then
      if printf '%s\n' "$outdated_output" | grep -qx 'tailscale'; then
        print_step "Upgrading Homebrew Tailscale formula"
        if upgrade_output="$("$brew_bin" upgrade tailscale 2>&1)"; then
          print_success "Homebrew Tailscale formula upgraded"
        else
          upgrade_error_summary="$(printf '%s\n' "$upgrade_output" | head -n1)"
          print_warning "Could not upgrade Homebrew Tailscale formula automatically."
          if [[ -n "$upgrade_error_summary" ]]; then
            print_warning "brew: $upgrade_error_summary"
          fi
          print_warning "Run manually: brew upgrade tailscale"
        fi
      else
        print_success "Homebrew Tailscale formula is already up to date"
      fi
    else
      print_warning "Could not determine whether Homebrew Tailscale is outdated."
      print_step "Attempting Homebrew upgrade for Tailscale"
      if upgrade_output="$("$brew_bin" upgrade tailscale 2>&1)"; then
        print_success "Homebrew Tailscale formula upgraded"
      else
        upgrade_error_summary="$(printf '%s\n' "$upgrade_output" | head -n1)"
        print_warning "Could not upgrade Homebrew Tailscale formula automatically."
        if [[ -n "$upgrade_error_summary" ]]; then
          print_warning "brew: $upgrade_error_summary"
        fi
        print_warning "Run manually: brew upgrade tailscale"
      fi
    fi
  fi

  if ! command_exists tailscale; then
    print_step "Linking Homebrew Tailscale formula"
    "$brew_bin" link tailscale
  fi
  if ! command_exists tailscale; then
    print_error "Tailscale formula is installed but 'tailscale' command is unavailable."
    if [[ -n "$brew_prefix" ]]; then
      print_warning "Check that $brew_prefix/bin is in PATH and rerun setup."
    fi
    return 1
  fi

  print_step "Starting Tailscale daemon"
  if start_macos_tailscale_daemon "$brew_bin"; then
    print_success "Tailscale service started"
  else
    print_error "Could not start Tailscale daemon automatically."
    print_warning "Run manually: sudo brew services start tailscale"
    print_warning "Then verify with: tailscale status"
    return 1
  fi

  print_step "Waiting for Tailscale daemon to become reachable..."
  if ! wait_for_tailscale_daemon 30 1; then
    print_error "Tailscale daemon is not reachable after waiting."
    print_warning "Run manually: sudo brew services restart tailscale"
    print_warning "Then verify with: tailscale status"
    return 1
  fi
  print_success "Tailscale ready (open-source CLI version)"
  print_warning "Authenticate with: sudo tailscale up --ssh"
  print_warning "Note: This version has no menu bar icon. Manage via CLI: tailscale status, tailscale up/down"
}

uninstall_tailscale_macos() {
  if ! command_exists brew; then
    print_warning "Uninstall Tailscale manually from Applications"
    return 0
  fi

  local brew_bin
  local brew_prefix
  local cellar
  local formula_installed=false

  brew_bin="$(command -v brew)"
  brew_prefix="$("$brew_bin" --prefix 2>/dev/null || true)"
  cellar="$("$brew_bin" --cellar 2>/dev/null || true)"

  if "$brew_bin" list --formula tailscale >/dev/null 2>&1; then
    formula_installed=true
  fi

  if command_exists tailscale; then
    print_step "Logging out from Tailscale (removes device from tailnet)..."
    sudo tailscale logout 2>/dev/null || true
  fi

  if [[ "$formula_installed" == true ]]; then
    print_step "Stopping Tailscale service..."
    sudo "$brew_bin" services stop tailscale 2>/dev/null || true

    sudo rm -f /Library/LaunchDaemons/homebrew.mxcl.tailscale.plist 2>/dev/null || true

    "$brew_bin" unlink tailscale 2>/dev/null || true

    print_step "Removing Tailscale formula..."
    if ! HOMEBREW_NO_AUTOREMOVE=1 "$brew_bin" uninstall --formula --ignore-dependencies tailscale 2>/dev/null; then
      if [[ -n "$cellar" && -d "$cellar/tailscale" ]]; then
        print_step "Force removing Tailscale keg..."
        sudo rm -rf "$cellar/tailscale"
      fi
    fi
  fi

  if "$brew_bin" list --cask tailscale-app >/dev/null 2>&1 || "$brew_bin" list --cask tailscale >/dev/null 2>&1; then
    print_step "Removing Tailscale cask..."
    HOMEBREW_NO_AUTOREMOVE=1 "$brew_bin" uninstall --cask --ignore-dependencies tailscale-app 2>/dev/null || \
    HOMEBREW_NO_AUTOREMOVE=1 "$brew_bin" uninstall --cask --ignore-dependencies tailscale 2>/dev/null || true
  fi

  if [[ -n "$brew_prefix" ]]; then
    rm -f "$brew_prefix/bin/tailscale" "$brew_prefix/bin/tailscaled" 2>/dev/null || true
  fi

  if command_exists tailscale; then
    print_warning "tailscale command is still present in PATH; uninstall may be incomplete"
    return 1
  fi

  return 0
}
