#!/usr/bin/env bash
set -euo pipefail

TAILMUX_VERSION=0.2.2

setup_help() {
  printf '%s\n' "tailmux setup $TAILMUX_VERSION" '' \
    'Usage: bash setup.sh <command> [--prefix /absolute/bin/directory]' '' 'Commands:' \
    '  install     Install the local standalone client' \
    '  uninstall   Remove the owned client and recognized legacy blocks' \
    '  update      Deprecated; dependencies belong to their package owners' '' \
    'Options:' '  --help, -h     Show help without loading modules' \
    '  --version, -V  Show version without loading modules'
}

if [[ $# == 1 ]]; then
  case "$1" in
    --help|-h) setup_help; exit 0 ;;
    --version|-V) printf 'tailmux %s\n' "$TAILMUX_VERSION"; exit 0 ;;
    update) printf '%s\n' 'tailmux update is deprecated. Use existing package owners for dependency updates.' >&2; exit 1 ;;
  esac
fi
[[ $# == 1 || ( $# == 3 && "$2" == --prefix ) ]] || { setup_help >&2; exit 2; }
case "$1" in
  install|uninstall) ;;
  *) printf 'Unknown command: %s\n' "$1" >&2; setup_help >&2; exit 2 ;;
esac
export TAILMUX_PREFIX=${3-"${HOME:-}/.local/bin"}

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
main "$1"
