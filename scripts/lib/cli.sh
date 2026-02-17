# shellcheck shell=bash
show_menu() {
  while true; do
    echo ""
    echo "tailmux"
    echo "======="
    echo ""
    echo "1) Install"
    echo "2) Uninstall"
    echo "3) Update"
    echo "4) Exit"
    echo ""
    read -r -p "Choose [1-4]: " choice
    case "$choice" in
      1) do_install; break ;;
      2) do_uninstall; break ;;
      3) do_update; break ;;
      4) exit 0 ;;
      *) print_error "Invalid choice" ;;
    esac
  done
}

_setup_help() {
  echo "tailmux setup $TAILMUX_VERSION"
  echo ""
  echo "Usage: setup.sh <command>"
  echo ""
  echo "Commands:"
  echo "  install     Install and configure tailmux"
  echo "  uninstall   Remove shell functions and optionally Tailscale state"
  echo "  update      Check for and apply package updates"
  echo "  menu        Show interactive menu (default)"
  echo ""
  echo "Options:"
  echo "  --help, -h     Show this help message"
  echo "  --version, -V  Show version"
}

_setup_version() {
  echo "tailmux $TAILMUX_VERSION"
}

main() {
  case "${1:-}" in
    install)        do_install ;;
    uninstall)      do_uninstall ;;
    update)         do_update ;;
    menu|"")        show_menu ;;
    --help|-h)      _setup_help ;;
    --version|-V)   _setup_version ;;
    *)              echo "Unknown command: $1" >&2; _setup_help >&2; exit 1 ;;
  esac
}
