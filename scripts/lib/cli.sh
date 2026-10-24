# shellcheck shell=bash
main() {
  if [[ "$1" == install && "$TAILMUX_REPLACE_OWNED" == true ]]; then
    do_replace_owned
    return $?
  fi
  case "$1" in
    recover) do_recover; return $? ;;
    configure)
      lifecycle_file "$SCRIPT_DIR/bin/tailmux" || { rc_error 'Unsafe local candidate' "$SCRIPT_DIR/bin/tailmux"; return 1; }
      /bin/bash "$SCRIPT_DIR/bin/tailmux" --config set socket "$TAILMUX_SOCKET"
      return $? ;;
  esac
  validate_rc_environment || return 1
  case "$1" in
    install) do_install ;;
    uninstall) do_uninstall ;;
  esac
}
