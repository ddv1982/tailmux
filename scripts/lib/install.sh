# shellcheck shell=bash
# Install flow and install-time shell function management
install_shell_function() {
  local prepare_status=0
  managed_block_prepare_install \
    "tailmux function" \
    "$TAILMUX_BLOCK_BEGIN" \
    "$TAILMUX_BLOCK_END" \
    "tailmux_function_installed" || prepare_status=$?
  if [[ "$prepare_status" == "10" ]]; then
    return 0
  fi
  if [[ "$prepare_status" == "20" ]]; then
    return 1
  fi

  print_step "Adding tailmux function to $RC_FILE"
  append_managed_block "$TAILMUX_BLOCK_BEGIN" "$TAILMUX_BLOCK_END" "$TAILMUX_FUNC"
  print_success "tailmux function added to $RC_FILE"
}

install_taildrive_functions() {
  local prepare_status=0
  managed_block_prepare_install \
    "taildrive functions" \
    "$TAILDRIVE_BLOCK_BEGIN" \
    "$TAILDRIVE_BLOCK_END" \
    "taildrive_functions_up_to_date" || prepare_status=$?
  if [[ "$prepare_status" == "10" ]]; then
    return 0
  fi
  if [[ "$prepare_status" == "20" ]]; then
    return 1
  fi

  local os_name
  local taildrive_content="$TAILDRIVE_SHARE_FUNCS"
  os_name="$(get_os_name)"
  if [[ "$os_name" == "Darwin" || "$os_name" == "Linux" ]]; then
    taildrive_content+=$'\n'"$TAILDRIVE_MOUNT_FUNCS"
  fi

  print_step "Adding taildrive functions to $RC_FILE"
  append_managed_block "$TAILDRIVE_BLOCK_BEGIN" "$TAILDRIVE_BLOCK_END" "$taildrive_content"
  print_success "taildrive functions added to $RC_FILE"
}

enable_macos_taildrive_filesharing_ui() {
  local os_name="${1:?missing os name}"

  if [[ "$os_name" != "Darwin" ]]; then
    return 0
  fi
  # With the open-source Homebrew tailscale formula, taildrive is managed via CLI
  # (tailscale drive share), not the GUI File Sharing settings. Skip this step.
  # The GUI settings only apply to the App Store / Standalone GUI app variants.
  return 0
}

print_reload_shell_hint() {
  local os_name="${1:?missing os name}"
  if [[ "$os_name" == "Darwin" ]]; then
    echo "Reload your shell: source $RC_FILE (or open a new Terminal window)"
  else
    echo "Reload your shell: source $RC_FILE (or open a new terminal)"
  fi
}

print_taildrive_help() {
  echo "Taildrive commands:"
  echo "  tailshare <name> [path]"
  echo "  tailunshare <name>"
  echo "  tailshare-ls"
  echo "  tailmount <host> <share> [mount_point]"
  echo "  tailumount <host> <share> [mount_point]"
  echo "  tailmount-ls"
  echo "One-time ACL setup required: add nodeAttrs 'drive:share' and 'drive:access'"
  echo "  README steps: https://github.com/ddv1982/tailmux#one-time-taildrive-acl-setup"
  echo "  See: https://tailscale.com/kb/1369/taildrive"
}

do_install() {
  echo ""
  echo "tailmux setup"
  echo "============="
  echo ""
  local os_name
  os_name="$(get_os_name)"

  local needs_install=false
  local install_list=""
  local macos_tailscale_state=""
  local macos_tailscale_ready=false

  if [[ "$os_name" == "Darwin" ]]; then
    if ! command_exists brew; then
      install_list+="  - Homebrew (package manager for macOS)\n"
      needs_install=true
    else
      macos_tailscale_state="$(detect_macos_tailscale_state)"
      if [[ "$macos_tailscale_state" == "formula" ]] && tailscale_daemon_reachable; then
        macos_tailscale_ready=true
      fi
      if [[ "$macos_tailscale_ready" != true ]]; then
        install_list+="  - Tailscale (Homebrew CLI formula for macOS)\n"
        needs_install=true
      fi
    fi
  elif ! command_exists tailscale; then
    install_list+="  - Tailscale (VPN/mesh network)\n"
    needs_install=true
  fi
  if ! command_exists tmux; then
    install_list+="  - tmux (terminal multiplexer)\n"
    needs_install=true
  fi
  if ! tailmux_function_installed; then
    install_list+="  - tailmux shell function (added to $RC_FILE)\n"
    needs_install=true
  fi
  local taildrive_missing=false
  local taildrive_refresh_needed=false
  if ! taildrive_functions_installed; then
    taildrive_missing=true
  elif ! taildrive_functions_up_to_date; then
    taildrive_refresh_needed=true
  fi
  if [[ "$needs_install" == false ]]; then
    local taildrive_installed_now=false
    print_success "Core setup is already installed!"
    if [[ "$os_name" == "Linux" ]]; then
      if command_exists tailscale; then
        ensure_linux_tailscale_operator "$os_name"
        if ! ensure_linux_tailscale_ssh "$os_name"; then
          print_warning "Could not enable Tailscale SSH automatically."
        fi
      fi
    fi
    if [[ "$taildrive_refresh_needed" == true ]]; then
      install_taildrive_functions
      taildrive_installed_now=true
    elif [[ "$taildrive_missing" == true ]]; then
      echo ""
      if confirm "Install optional taildrive file sharing functions? [y/N]" "n"; then
        ensure_taildrive_mount_dependencies "$os_name"
        install_taildrive_functions
        enable_macos_taildrive_filesharing_ui "$os_name"
        taildrive_installed_now=true
      fi
    else
      enable_macos_taildrive_filesharing_ui "$os_name"
    fi
    echo ""
    print_reload_shell_hint "$os_name"
    if command_exists tailscale; then
      if [[ "$os_name" == "Linux" ]]; then
        echo "If not authenticated yet, run: sudo tailscale up --ssh"
      else
        echo "If not authenticated yet, run: tailscale up"
      fi
    fi
    echo "Usage: tailmux <hostname>"
    if [[ "$taildrive_installed_now" == true || "$taildrive_missing" == false ]]; then
      echo ""
      print_taildrive_help
    fi
    return 0
  fi

  echo "This will install:"
  printf "%b" "$install_list"
  echo ""

  if ! confirm "Continue? [Y/n]" "y"; then
    echo "Setup cancelled."
    exit 0
  fi

  if [[ "$os_name" == "Darwin" ]] && ! command_exists brew; then
    install_homebrew
  fi

  install_tailscale
  install_tmux
  install_shell_function

  local taildrive_installed=false
  if [[ "$taildrive_refresh_needed" == true ]]; then
    install_taildrive_functions
    taildrive_installed=true
  elif [[ "$taildrive_missing" == true ]]; then
    echo ""
    if confirm "Install taildrive file sharing functions? [y/N]" "n"; then
      ensure_taildrive_mount_dependencies "$os_name"
      install_taildrive_functions
      enable_macos_taildrive_filesharing_ui "$os_name"
      taildrive_installed=true
    fi
  else
    enable_macos_taildrive_filesharing_ui "$os_name"
  fi

  echo ""
  print_success "Setup complete!"
  echo ""
  echo "Next steps:"
  if [[ "$os_name" == "Linux" ]]; then
    local step=1
    echo "  $step. Authenticate with Tailscale and enable Tailscale SSH: sudo tailscale up --ssh"
    echo "     (Opens browser for login - required first time)"
    ((step++))
    echo "  $step. After login, enable passwordless access: sudo tailscale set --operator=\$USER"
    ((step++))
    echo "  $step. Open a new terminal, or run: source $RC_FILE"
    ((step++))
    echo "  $step. Connect: tailmux <hostname>"
  else
    echo "  1. Authenticate with Tailscale (if not already): tailscale up"
    echo "  2. Ensure SSH is enabled on the destination (macOS: Remote Login)"
    echo "  3. Open a new Terminal window, or run: source $RC_FILE"
    echo "  4. Connect: tailmux <hostname>"
  fi
  if [[ "$taildrive_installed" == true ]]; then
    echo ""
    print_taildrive_help
  fi
  echo ""
}
