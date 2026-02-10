# shellcheck shell=bash
command_exists() { command -v "$1" &>/dev/null; }

get_os_name() {
  if [[ -n "${TAILMUX_OS_OVERRIDE:-}" ]]; then
    echo "$TAILMUX_OS_OVERRIDE"
    return 0
  fi
  uname -s
}

# Detect shell config
detect_shell_rc() {
  if [[ -n "${ZSH_VERSION:-}" ]] || [[ "${SHELL:-}" == *zsh* ]]; then
    echo "$HOME/.zshrc"
    return 0
  fi
  if [[ -f "$HOME/.bashrc" ]]; then
    echo "$HOME/.bashrc"
    return 0
  fi
  if [[ -f "$HOME/.bash_profile" ]]; then
    echo "$HOME/.bash_profile"
    return 0
  fi
  echo "$HOME/.profile"
}
