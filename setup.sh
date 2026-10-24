#!/usr/bin/env bash
set -euo pipefail

TAILMUX_VERSION=0.3.0

setup_help() {
  printf '%s\n' "tailmux setup $TAILMUX_VERSION" '' \
    'Usage: bash setup.sh <command> [--prefix /absolute/bin/directory] [--replace-owned]' '' 'Commands:' \
    '  install     Install the local standalone client' \
    '  uninstall   Remove the owned client and recognized legacy blocks' \
    '  recover     Preview or explicitly recover a modified receipt-owned client' \
    '  configure   Save an explicit socket through this local candidate' \
    '  update      Deprecated; dependencies belong to their package owners' '' \
    'Recovery:' \
    '  recover [--prefix ABS] --dry-run' \
    '  recover [--prefix ABS] --expect-current-sha256 LOWER64HEX' \
    '  recover [--prefix ABS] --resume|--rollback|--unlock-abandoned --transaction ID --expect-current-sha256 LOWER64HEX' \
    '  --unlock-abandoned asserts that no writer remains active' \
    'Configuration:' '  configure --socket ABS_SOCKET' '' \
    'Options:' '  --replace-owned  Replace an unchanged owned client without RC migration' \
    '  --help, -h     Show help without loading modules' \
    '  --version, -V  Show version without loading modules'
}

if [[ $# == 1 ]]; then
  case "$1" in
    --help|-h) setup_help; exit 0 ;;
    --version|-V) printf 'tailmux %s\n' "$TAILMUX_VERSION"; exit 0 ;;
    update) printf '%s\n' 'tailmux update is deprecated. Use existing package owners for dependency updates.' >&2; exit 1 ;;
  esac
fi
[[ $# -ge 1 ]] || { setup_help >&2; exit 2; }
case "$1" in
  install|uninstall|recover|configure) ;;
  *) printf 'Unknown command: %s\n' "$1" >&2; setup_help >&2; exit 2 ;;
esac
command=$1
shift
TAILMUX_REPLACE_OWNED=false
TAILMUX_PREFIX="${HOME:-}/.local/bin"
prefix_seen=false
RECOVERY_REQUEST=(apply '' '')
recovery_action_seen=false
TAILMUX_SOCKET=''
socket_seen=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      [[ $# -ge 2 && "$prefix_seen" == false ]] || { setup_help >&2; exit 2; }
      TAILMUX_PREFIX=$2
      prefix_seen=true
      shift 2 ;;
    --replace-owned)
      [[ "$command" == install && "$TAILMUX_REPLACE_OWNED" == false ]] || { setup_help >&2; exit 2; }
      TAILMUX_REPLACE_OWNED=true
      shift ;;
    --dry-run|--resume|--rollback|--unlock-abandoned)
      [[ "$command" == recover && "$recovery_action_seen" == false ]] || { setup_help >&2; exit 2; }
      RECOVERY_REQUEST[0]=${1#--}
      recovery_action_seen=true
      shift ;;
    --expect-current-sha256|--transaction)
      [[ "$command" == recover && $# -ge 2 ]] || { setup_help >&2; exit 2; }
      if [[ "$1" == --transaction ]]; then request_field=2; else request_field=1; fi
      [[ -z "${RECOVERY_REQUEST[$request_field]}" && -n "$2" ]] || { setup_help >&2; exit 2; }
      RECOVERY_REQUEST[request_field]=$2
      shift 2 ;;
    --socket)
      [[ "$command" == configure && $# -ge 2 && "$socket_seen" == false ]] || { setup_help >&2; exit 2; }
      TAILMUX_SOCKET=$2
      socket_seen=true
      shift 2 ;;
    *) setup_help >&2; exit 2 ;;
  esac
done
validate_setup_request() {
  local LC_ALL=C recovery_id
  if [[ "$command" == configure ]]; then
    [[ "$prefix_seen" == false && "$socket_seen" == true && "$TAILMUX_SOCKET" == /* &&
      ! "$TAILMUX_SOCKET" =~ [[:cntrl:]] ]] || { setup_help >&2; exit 2; }
  elif [[ "$command" == recover ]]; then
    case "${RECOVERY_REQUEST[0]}" in
      dry-run) [[ -z "${RECOVERY_REQUEST[1]}${RECOVERY_REQUEST[2]}" ]] || { setup_help >&2; exit 2; } ;;
      apply) [[ -z "${RECOVERY_REQUEST[2]}" ]] || { setup_help >&2; exit 2; } ;;
      *)
        recovery_id=${RECOVERY_REQUEST[2]}
        [[ ${#recovery_id} -ge 1 && ${#recovery_id} -le 96 && "$recovery_id" != . && "$recovery_id" != .. &&
          "$recovery_id" != *[!a-zA-Z0-9._-]* ]] || { setup_help >&2; exit 2; } ;;
    esac
    if [[ "${RECOVERY_REQUEST[0]}" != dry-run ]]; then
      [[ "${RECOVERY_REQUEST[1]}" =~ ^[a-f0-9]{64}$ ]] || { setup_help >&2; exit 2; }
    fi
  fi
}
validate_setup_request
export TAILMUX_PREFIX

if [[ ! -f "${BASH_SOURCE[0]}" || "${BASH_SOURCE[0]}" == /dev/fd/* || "${BASH_SOURCE[0]}" == /proc/*/fd/* ]]; then
  printf '%s\n' 'Error: remote/process-substitution setup is disabled. Run bash setup.sh from a reviewed local checkout.' >&2
  exit 1
fi
SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/scripts/lib"
REQUIRED_MODULES=(platform.sh rc_blocks.sh managed_blocks.sh install.sh uninstall.sh cli.sh)
for module in "${REQUIRED_MODULES[@]}"; do
  if [[ ! -f "$LIB_DIR/$module" ]]; then
    printf 'Error: Required module missing: %s\n' "$LIB_DIR/$module" >&2
    exit 1
  fi
done
for module in "${REQUIRED_MODULES[@]}"; do
  # shellcheck source=/dev/null
  source "$LIB_DIR/$module"
done
main "$command"
