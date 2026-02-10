# shellcheck shell=bash
# Uninstall flow and uninstall-time shell function management
uninstall_taildrive_functions() {
  managed_block_remove \
    "Taildrive" \
    "taildrive functions" \
    "taildrive managed block" \
    "$TAILDRIVE_BLOCK_BEGIN" \
    "$TAILDRIVE_BLOCK_END"
}

uninstall_shell_function() {
  managed_block_remove \
    "Tailmux" \
    "tailmux function" \
    "tailmux managed block" \
    "$TAILMUX_BLOCK_BEGIN" \
    "$TAILMUX_BLOCK_END"
}

do_uninstall() {
  echo ""
  echo "tailmux uninstall"
  echo "================="
  echo ""

  if confirm "Remove tailmux shell function? [Y/n]" "y"; then
    uninstall_shell_function
  fi

  if confirm "Remove taildrive functions? [Y/n]" "y"; then
    uninstall_taildrive_functions

    # Offer to uninstall davfs2 on Linux if installed
    local os_name
    os_name="$(get_os_name)"
    if [[ "$os_name" == "Linux" ]] && davfs2_installed; then
      if confirm "Uninstall davfs2 (taildrive mount support)? [y/N]" "n"; then
        uninstall_davfs2
      fi
    fi
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
