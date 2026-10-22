# shellcheck shell=bash
main() {
  validate_rc_environment || return 1
  case "$1" in
    install) do_install ;;
    uninstall) do_uninstall ;;
  esac
}
