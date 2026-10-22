# shellcheck shell=bash
do_install() {
  local rc template_digest
  template_digest="$(printf '%s' "$TAILMUX_FUNC" | core_body_digest)" || return 1
  if [[ "${template_digest%% *}" != "$TAILMUX_REVIEWED_CORE_DIGEST" ]]; then
    rc_error 'Local core template is not the reviewed PR-01 template' "$LIB_DIR/constants.sh"; return 1
  fi
  while IFS= read -r rc; do
    inspect_rc "$rc" > /dev/null || return 1
  done < <(rc_paths)
  rc="$(detect_shell_rc)"
  core_rc_operation install "$rc" || return 1
  printf 'Core setup complete in %s. Open a fresh shell.\n' "$rc"
  if ! command -v tailscale >/dev/null 2>&1; then
    printf '%s\n' 'Tailscale is missing. Install and configure it through its existing package owner before connecting.'
  fi
  printf '%s\n' 'The destination account needs tmux and an operator-managed SSH service.' \
    'Taildrive is legacy and is not installed. See docs/taildrive.md.'
}
