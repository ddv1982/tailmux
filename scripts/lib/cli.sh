# shellcheck shell=bash
main() {
  if [[ "$1" == install && "$TAILMUX_REPLACE_OWNED" == true ]]; then
    do_replace_owned
    return $?
  fi
  validate_rc_environment || return 1
  case "$1" in
    install) do_install ;;
    uninstall) do_uninstall ;;
  esac
}
