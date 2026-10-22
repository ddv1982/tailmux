# shellcheck shell=bash
validate_rc_environment() {
  local path
  for path in "${HOME:-}" "${ZDOTDIR:-${HOME:-}}"; do
    if [[ "$path" != /* || "$path" == *$'\n'* ]]; then
      printf '%s\n' 'Error: HOME and ZDOTDIR must be absolute paths without newlines.' >&2
      return 1
    fi
  done
}

detect_shell_rc() {
  if [[ "${SHELL:-}" == *zsh* ]]; then
    printf '%s\n' "${ZDOTDIR:-$HOME}/.zshrc"
  elif [[ -e "$HOME/.bashrc" || -L "$HOME/.bashrc" ]]; then
    printf '%s\n' "$HOME/.bashrc"
  elif [[ -e "$HOME/.bash_profile" || -L "$HOME/.bash_profile" ]]; then
    printf '%s\n' "$HOME/.bash_profile"
  else
    printf '%s\n' "$HOME/.profile"
  fi
}

rc_paths() {
  printf '%s\n' "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" "${ZDOTDIR:-$HOME}/.zshrc"
}
