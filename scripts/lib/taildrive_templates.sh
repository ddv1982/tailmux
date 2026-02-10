# shellcheck shell=bash
# shellcheck disable=SC2034
# Taildrive shell function templates
# Taildrive shell functions (sharing)
read -r -d '' TAILDRIVE_SHARE_FUNCS <<'SHARE_EOF' || true
# taildrive - file sharing over Tailscale
_taildrive_get_os_name() {
  uname -s
}
_taildrive_require_cmd() {
  local cmd="${1:?missing command name}"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: Required command '$cmd' not found in PATH" >&2
    return 1
  fi
}
_taildrive_require_drive_subcommand() {
  _taildrive_require_cmd tailscale || return 1
  if tailscale drive --help >/dev/null 2>&1; then
    return 0
  fi
  if [[ "$(_taildrive_get_os_name)" == "Darwin" ]]; then
    echo "Error: Your current macOS 'tailscale' CLI does not expose the 'drive' subcommand." >&2
    echo "On macOS, configure shares in the Tailscale app: Settings -> File Sharing." >&2
    echo "Taildrive docs: https://tailscale.com/kb/1369/taildrive" >&2
  else
    echo "Error: Your current 'tailscale' CLI does not expose the 'drive' subcommand." >&2
    echo "Update Tailscale, then retry." >&2
  fi
  return 1
}
_taildrive_status_json() {
  _taildrive_require_cmd tailscale || return 1
  tailscale status --json 2>/dev/null
}
_taildrive_self_hostname() {
  local json
  if ! json="$(_taildrive_status_json)"; then
    return 1
  fi
  if command -v jq >/dev/null 2>&1; then
    printf '%s\n' "$json" | jq -r '.Self.HostName // empty' 2>/dev/null
    return $?
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "$json" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(((data.get("Self") or {}).get("HostName","")))' 2>/dev/null
    return $?
  fi
  printf '%s\n' "$json" | sed -n 's/.*"HostName"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1
}
_taildrive_magicdns_suffix() {
  local json
  if ! json="$(_taildrive_status_json)"; then
    return 1
  fi
  if command -v jq >/dev/null 2>&1; then
    printf '%s\n' "$json" | jq -r '.MagicDNSSuffix // empty' 2>/dev/null
    return $?
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "$json" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(data.get("MagicDNSSuffix",""))' 2>/dev/null
    return $?
  fi
  printf '%s\n' "$json" | sed -n 's/.*"MagicDNSSuffix"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1
}
tailshare() {
  local name="${1:?Usage: tailshare <name> [path]}"
  local path="${2:-.}"
  _taildrive_require_drive_subcommand || return 1
  if ! path="$(cd "$path" && pwd)"; then
    echo "Error: Path '$path' does not exist" >&2
    return 1
  fi
  if ! tailscale drive share "$name" "$path"; then
    return 1
  fi
  echo "Shared '$name' -> $path"
  local hostname
  hostname="$(_taildrive_self_hostname || true)"
  if [[ -n "$hostname" ]]; then
    echo "Others can mount with: tailmount $hostname $name"
  else
    echo "Tip: mount from another machine with: tailmount <host> $name"
  fi
}
tailunshare() {
  local name="${1:?Usage: tailunshare <name>}"
  _taildrive_require_drive_subcommand || return 1
  if ! tailscale drive unshare "$name"; then
    return 1
  fi
  echo "Unshared '$name'"
}
tailshare-ls() {
  _taildrive_require_drive_subcommand || return 1
  tailscale drive list
}
SHARE_EOF

# Taildrive shell functions (mounting - macOS and Linux)
read -r -d '' TAILDRIVE_MOUNT_FUNCS <<'MOUNT_EOF' || true
_taildrive_get_os_name() {
  uname -s
}
_taildrive_mount_darwin() {
  local url="${1:?missing mount url}"
  local mount_point="${2:?missing mount point}"
  _taildrive_require_cmd mount_webdav || return 1
  mount_webdav "$url" "$mount_point"
}
_taildrive_mount_linux() {
  local url="${1:?missing mount url}"
  local mount_point="${2:?missing mount point}"
  local mount_err_file
  if ! command -v mount.davfs >/dev/null 2>&1 && [[ ! -x /sbin/mount.davfs ]] && [[ ! -x /usr/sbin/mount.davfs ]]; then
    echo "Error: davfs2 is not installed (missing mount.davfs)." >&2
    echo "Install it with: sudo apt-get install -y davfs2 (or your distro equivalent)." >&2
    return 1
  fi
  mount_err_file="$(mktemp)"
  if mount -t davfs "$url" "$mount_point" 2>"$mount_err_file"; then
    rm -f "$mount_err_file"
    return 0
  fi
  if command -v sudo >/dev/null 2>&1; then
    echo "Mount needs elevated privileges on this system; retrying with sudo..."
    if sudo mount -t davfs "$url" "$mount_point"; then
      rm -f "$mount_err_file"
      return 0
    fi
  fi
  if [[ -s "$mount_err_file" ]]; then
    cat "$mount_err_file" >&2
  fi
  rm -f "$mount_err_file"
  if command -v sudo >/dev/null 2>&1; then
    echo "Error: mount failed." >&2
  else
    echo "Error: mount failed and sudo is not available." >&2
  fi
  return 1
}
_taildrive_umount_linux() {
  local mount_point="${1:?missing mount point}"
  if umount "$mount_point" 2>/dev/null; then
    return 0
  fi
  if command -v fusermount >/dev/null 2>&1 && fusermount -u "$mount_point" 2>/dev/null; then
    return 0
  fi
  if command -v sudo >/dev/null 2>&1; then
    echo "Unmount needs elevated privileges on this system; retrying with sudo..."
    if sudo umount "$mount_point"; then
      return 0
    fi
    if command -v fusermount >/dev/null 2>&1 && sudo fusermount -u "$mount_point"; then
      return 0
    fi
  fi
  return 1
}
tailmount() {
  local host="${1:?Usage: tailmount <host> <share> [mount_point]}"
  local share="${2:?Usage: tailmount <host> <share> [mount_point]}"
  local mount_point="${3:-$HOME/taildrive/$host/$share}"
  local tailnet
  local os_name
  local mount_url
  if ! tailnet="$(_taildrive_magicdns_suffix)"; then
    echo "Error: Could not determine tailnet name. Is Tailscale running?" >&2
    return 1
  fi
  tailnet="${tailnet%.}"
  if [[ -z "$tailnet" ]]; then
    echo "Error: Could not determine tailnet name. Is Tailscale running?" >&2
    return 1
  fi
  if ! mkdir -p "$mount_point"; then
    echo "Error: Could not create mount point '$mount_point'" >&2
    return 1
  fi
  mount_url="http://100.100.100.100:8080/$tailnet/$host/$share"
  os_name="$(_taildrive_get_os_name)"
  case "$os_name" in
    Darwin)
      if ! _taildrive_mount_darwin "$mount_url" "$mount_point"; then
        return 1
      fi
      ;;
    Linux)
      if ! _taildrive_mount_linux "$mount_url" "$mount_point"; then
        return 1
      fi
      ;;
    *)
      echo "Error: tailmount is only supported on macOS and Linux (current: $os_name)." >&2
      return 1
      ;;
  esac
  echo "Mounted at $mount_point"
}
tailumount() {
  local host="${1:?Usage: tailumount <host> <share> [mount_point]}"
  local share="${2:?Usage: tailumount <host> <share> [mount_point]}"
  local mount_point="${3:-$HOME/taildrive/$host/$share}"
  local os_name
  os_name="$(_taildrive_get_os_name)"
  case "$os_name" in
    Darwin)
      if ! umount "$mount_point" 2>/dev/null && ! diskutil unmount "$mount_point" 2>/dev/null; then
        echo "Error: Failed to unmount '$mount_point'" >&2
        return 1
      fi
      ;;
    Linux)
      if ! _taildrive_umount_linux "$mount_point"; then
        echo "Error: Failed to unmount '$mount_point'" >&2
        return 1
      fi
      ;;
    *)
      echo "Error: tailumount is only supported on macOS and Linux (current: $os_name)." >&2
      return 1
      ;;
  esac
  echo "Unmounted $mount_point"
}
tailmount-ls() {
  local mounts
  mounts="$(mount | grep -E '100\.100\.100\.100:8080|/taildrive/' || true)"
  if [[ -z "$mounts" ]]; then
    echo "No taildrive mounts found"
    return 0
  fi
  printf '%s\n' "$mounts"
  return 0
}
MOUNT_EOF
