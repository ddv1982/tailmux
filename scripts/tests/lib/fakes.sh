#!/usr/bin/env bash

make_fake_bin() {
  local bin_dir="${1:?missing bin dir}"

  cat > "$bin_dir/tailscale" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${TAILSCALE_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$TAILSCALE_CALLS_FILE"
fi
if [[ "${1:-}" == "status" && "${2:-}" == "--json" ]]; then
  if [[ -n "${TAILSCALE_STATUS_FAIL_FILE:-}" && -f "$TAILSCALE_STATUS_FAIL_FILE" ]]; then
    exit 1
  fi
  printf '{"BackendState":"Running","Self":{"HostName":"test-host"},"MagicDNSSuffix":"example.ts.net."}\n'
  exit 0
fi
if [[ "${1:-}" == "status" ]]; then
  if [[ -n "${TAILSCALE_STATUS_FAIL_FILE:-}" && -f "$TAILSCALE_STATUS_FAIL_FILE" ]]; then
    exit 1
  fi
  operator=""
  for arg in "$@"; do
    case "$arg" in
      --operator=*)
        operator="${arg#--operator=}"
        ;;
    esac
  done
  if [[ -n "$operator" ]]; then
    if [[ -n "${TAILSCALE_FAKE_OPERATOR_FILE:-}" && -f "$TAILSCALE_FAKE_OPERATOR_FILE" ]]; then
      configured="$(cat "$TAILSCALE_FAKE_OPERATOR_FILE" 2>/dev/null || true)"
      [[ "$configured" == "$operator" ]] && exit 0
    fi
    exit 1
  fi
  exit 0
fi
if [[ "${1:-}" == "set" || "${1:-}" == "up" ]]; then
  for arg in "$@"; do
    case "$arg" in
      --operator=*)
        if [[ -n "${TAILSCALE_FAKE_OPERATOR_FILE:-}" ]]; then
          printf '%s\n' "${arg#--operator=}" > "$TAILSCALE_FAKE_OPERATOR_FILE"
        fi
        ;;
    esac
  done
  exit 0
fi
if [[ "${1:-}" == "drive" ]]; then
  exit 0
fi
if [[ "${1:-}" == "dns" && "${2:-}" == "query" ]]; then
  exit 1
fi
if [[ "${1:-}" == "debug" && "${2:-}" == "prefs" ]]; then
  printf '{"CorpDNS":true}\n'
  exit 0
fi
exit 0
BIN

  cat > "$bin_dir/tmux" <<'BIN'
#!/usr/bin/env bash
exit 0
BIN

  cat > "$bin_dir/sudo" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${SUDO_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$SUDO_CALLS_FILE"
fi
if [[ $# -eq 0 ]]; then
  exit 0
fi
cmd="${1:-}"
shift || true
case "$cmd" in
  rm|/bin/rm|/usr/bin/rm)
    if [[ -n "${SUDO_RM_CALLS_FILE:-}" ]]; then
      printf '%s\n' "$cmd $*" >> "$SUDO_RM_CALLS_FILE"
    fi
    exit 0
    ;;
  env)
    env "$@"
    ;;
  *)
    "$cmd" "$@"
    ;;
esac
BIN

  cat > "$bin_dir/ssh" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${SSH_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$SSH_CALLS_FILE"
fi
exit "${SSH_EXIT_CODE:-0}"
BIN

  cat > "$bin_dir/systemctl" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${SYSTEMCTL_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$SYSTEMCTL_CALLS_FILE"
fi
if [[ "${1:-}" == "is-active" ]]; then
  if [[ -n "${SSH_ACTIVE_FILE:-}" ]]; then
    if [[ -f "$SSH_ACTIVE_FILE" ]]; then
      exit 0
    fi
    exit 3
  fi
  exit 0
fi
if [[ "${1:-}" == "enable" && "${2:-}" == "--now" && ( "${3:-}" == "ssh" || "${3:-}" == "sshd" ) ]]; then
  if [[ -n "${SSH_ENABLE_FAIL_FILE:-}" && -f "$SSH_ENABLE_FAIL_FILE" ]]; then
    exit 1
  fi
  if [[ -n "${SSH_ACTIVE_FILE:-}" ]]; then
    : > "$SSH_ACTIVE_FILE"
  fi
  exit 0
fi
if [[ "${1:-}" == "enable" && "${2:-}" == "--now" && "${3:-}" == "tailscaled" ]]; then
  if [[ -n "${SYSTEMCTL_FIX_STATUS_FILE:-}" ]]; then
    rm -f "$SYSTEMCTL_FIX_STATUS_FILE"
  fi
  exit 0
fi
if [[ "${1:-}" == "stop" || "${1:-}" == "disable" ]]; then
  exit 0
fi
exit 0
BIN

  cat > "$bin_dir/apt-get" <<'BIN'
#!/usr/bin/env bash
exit 0
BIN

  cat > "$bin_dir/curl" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${CURL_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$CURL_CALLS_FILE"
fi
if [[ "$*" == *"https://tailscale.com/install.sh"* ]]; then
  printf '%s\n' '#!/usr/bin/env bash'
  printf '%s\n' 'exit 0'
  exit 0
fi
exit 0
BIN

  cat > "$bin_dir/mount" <<'BIN'
#!/usr/bin/env bash
exit 1
BIN

  cat > "$bin_dir/umount" <<'BIN'
#!/usr/bin/env bash
exit 1
BIN

  cat > "$bin_dir/fusermount" <<'BIN'
#!/usr/bin/env bash
exit 1
BIN

  chmod +x "$bin_dir/tailscale" "$bin_dir/tmux" "$bin_dir/sudo" "$bin_dir/ssh" "$bin_dir/systemctl" "$bin_dir/apt-get" "$bin_dir/curl" "$bin_dir/mount" "$bin_dir/umount" "$bin_dir/fusermount"
}

make_fake_macos_bin() {
  local bin_dir="${1:?missing bin dir}"
  local brew_prefix="${2:?missing brew prefix}"
  make_fake_bin "$bin_dir"
  mkdir -p "$brew_prefix/bin" "$brew_prefix/Cellar"
  cp "$bin_dir/tailscale" "$brew_prefix/bin/tailscale"

  cat > "$bin_dir/brew" <<'BIN'
#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"
shift || true
if [[ -n "${BREW_CALLS_FILE:-}" ]]; then
  printf '%s %s\n' "$cmd" "$*" >> "$BREW_CALLS_FILE"
fi
case "$cmd" in
  --prefix)
    printf '%s\n' "${BREW_PREFIX:?missing BREW_PREFIX}"
    ;;
  --cellar)
    printf '%s\n' "${BREW_PREFIX:?missing BREW_PREFIX}/Cellar"
    ;;
  list)
    if [[ "${1:-}" == "--formula" && "${2:-}" == "tailscale" ]]; then
      exit 0
    fi
    if [[ "${1:-}" == "--cask" ]]; then
      exit 1
    fi
    exit 1
    ;;
  outdated)
    if [[ "${1:-}" == "--formula" && "${2:-}" == "tailscale" ]]; then
      if [[ "${BREW_TAILSCALE_OUTDATED:-0}" == "1" ]]; then
        printf '%s\n' "tailscale"
      fi
      exit 0
    fi
    exit 0
    ;;
  info)
    printf '%s\n' '{"formulae":[{"versions":{"stable":"1.99.0"}}]}'
    exit 0
    ;;
  install|link|unlink|uninstall|upgrade)
    exit 0
    ;;
  services)
    exit 0
    ;;
  update)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
BIN

  cat > "$bin_dir/sudo" <<'BIN'
#!/usr/bin/env bash
"$@"
BIN

  chmod +x "$bin_dir/brew" "$bin_dir/sudo"
}

make_fake_tailscale_installer_capture_bin() {
  local bin_dir="${1:?missing bin dir}"

  cat > "$bin_dir/curl" <<'BIN'
#!/usr/bin/env bash
if [[ -n "${CURL_CALLS_FILE:-}" ]]; then
  printf '%s\n' "$*" >> "$CURL_CALLS_FILE"
fi
printf '%s\n' '#!/usr/bin/env bash'
printf '%s\n' 'exit 0'
BIN

  cat > "$bin_dir/sh" <<'BIN'
#!/usr/bin/env bash
cat >/dev/null
if [[ -n "${TAILSCALE_INSTALL_ENV_FILE:-}" ]]; then
  {
    printf 'TRACK=%s\n' "${TRACK:-}"
  } > "$TAILSCALE_INSTALL_ENV_FILE"
fi
exit 0
BIN

  chmod +x "$bin_dir/curl" "$bin_dir/sh"
}

make_update_brew_fake() {
  local bin_dir="${1:?missing bin dir}"
  cat > "$bin_dir/brew" <<'BIN'
#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"
shift || true
if [[ -n "${BREW_CALLS_FILE:-}" ]]; then
  printf '%s %s\n' "$cmd" "$*" >> "$BREW_CALLS_FILE"
fi
case "$cmd" in
  --prefix)
    printf '%s\n' "${BREW_PREFIX:?missing BREW_PREFIX}"
    ;;
  --cellar)
    printf '%s\n' "${BREW_PREFIX:?missing BREW_PREFIX}/Cellar"
    ;;
  list)
    if [[ "${1:-}" == "--formula" && "${2:-}" == "tailscale" ]]; then
      exit 0
    fi
    if [[ "${1:-}" == "--cask" ]]; then
      exit 1
    fi
    exit 1
    ;;
  outdated)
    has_formula=false
    for arg in "$@"; do
      [[ "$arg" == "--formula" ]] && has_formula=true
    done
    if [[ "$has_formula" == true && "${BREW_TAILSCALE_OUTDATED:-0}" == "1" ]]; then
      printf '%s\n' "tailscale"
    fi
    exit 0
    ;;
  info)
    printf '%s\n' '{"formulae":[{"versions":{"stable":"1.99.0"}}]}'
    exit 0
    ;;
  update)
    exit 0
    ;;
  install|link|unlink|uninstall)
    exit 0
    ;;
  upgrade)
    if [[ "${BREW_FAIL_UPGRADE:-0}" == "1" ]]; then
      echo "Error: simulated upgrade failure" >&2
      exit 1
    fi
    exit 0
    ;;
  services)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
BIN
  chmod +x "$bin_dir/brew"
}
