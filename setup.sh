#!/usr/bin/env bash
set -euo pipefail

# Trap for clean exit on interrupt
trap 'echo ""; echo "Setup interrupted."; exit 130' INT TERM

SCRIPT_DIR=""
LIB_DIR=""
REMOTE_LIB_DIR=""
RC_FILE=""

REQUIRED_MODULES=(
  "constants.sh"
  "dependency_policy.sh"
  "ui.sh"
  "platform.sh"
  "taildrive_templates.sh"
  "rc_blocks.sh"
  "managed_blocks.sh"
  "package_manager.sh"
  "tailscale_macos.sh"
  "packages.sh"
  "update.sh"
  "install.sh"
  "uninstall.sh"
  "cli.sh"
)

resolve_script_dir() {
  local source="${BASH_SOURCE[0]:-}"
  local source_dir
  local resolved_dir

  if [[ -z "$source" ]]; then
    echo ""
    return 0
  fi

  while [[ -h "$source" ]]; do
    source_dir="$(cd -P "$(dirname "$source")" >/dev/null 2>&1 && pwd)"
    source="$(readlink "$source")"
    [[ "$source" != /* ]] && source="$source_dir/$source"
  done

  if resolved_dir="$(cd -P "$(dirname "$source")" >/dev/null 2>&1 && pwd)"; then
    :
  else
    resolved_dir=""
  fi
  echo "$resolved_dir"
}

cleanup_remote_lib_dir() {
  if [[ -n "$REMOTE_LIB_DIR" && -d "$REMOTE_LIB_DIR" ]]; then
    rm -rf "$REMOTE_LIB_DIR"
  fi
}

load_module_from_local() {
  local module_name="${1:?missing module name}"
  local module_path="$LIB_DIR/$module_name"
  if [[ ! -f "$module_path" ]]; then
    echo "Error: Required module missing: $module_path" >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  source "$module_path"
}

fetch_remote_modules() {
  local raw_base="${TAILMUX_RAW_BASE:-https://raw.githubusercontent.com/ddv1982/tailmux/main}"
  local module_name
  local module_url
  local module_path

  if ! command -v curl >/dev/null 2>&1; then
    echo "Error: curl is required to fetch setup modules when running from a remote setup.sh." >&2
    exit 1
  fi

  REMOTE_LIB_DIR="$(mktemp -d)"
  trap 'cleanup_remote_lib_dir' EXIT

  for module_name in "${REQUIRED_MODULES[@]}"; do
    module_url="$raw_base/scripts/lib/$module_name"
    module_path="$REMOTE_LIB_DIR/$module_name"
    if ! curl -fsSL "$module_url" -o "$module_path"; then
      echo "Error: Failed to download required module: $module_url" >&2
      exit 1
    fi
  done

  LIB_DIR="$REMOTE_LIB_DIR"
}

load_modules() {
  local module_name

  if [[ "${TAILMUX_USE_LOCAL_MODULES:-0}" == "1" ]]; then
    if [[ ! -d "$LIB_DIR" ]]; then
      echo "Error: TAILMUX_USE_LOCAL_MODULES=1 but local module directory was not found: $LIB_DIR" >&2
      exit 1
    fi
    for module_name in "${REQUIRED_MODULES[@]}"; do
      load_module_from_local "$module_name"
    done
    return 0
  fi

  # Default behavior: fetch latest module set from raw GitHub main.
  fetch_remote_modules
  for module_name in "${REQUIRED_MODULES[@]}"; do
    # shellcheck disable=SC1090
    source "$LIB_DIR/$module_name"
  done
}

SCRIPT_DIR="$(resolve_script_dir)"
if [[ -n "$SCRIPT_DIR" ]]; then
  LIB_DIR="$SCRIPT_DIR/scripts/lib"
else
  LIB_DIR=""
fi

load_modules
# shellcheck disable=SC2034
RC_FILE="$(detect_shell_rc)"

main "${1:-}"
