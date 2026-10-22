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

rc_paths() {
  printf '%s\n' "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.profile" "${ZDOTDIR:-$HOME}/.zshrc"
}
