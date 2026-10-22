# shellcheck shell=bash
validate_prefix() {
  local prefix="$1" component="$1" uid mode
  [[ "$prefix" == /* && "$prefix" != / && "$prefix" != *$'\n'* && "$prefix" != *$'\r'* &&
    "$prefix" != *'/../'* && "$prefix" != */.. && "$prefix" != *'/./'* && "$prefix" != */. && "$prefix" != */ ]] || {
    rc_error 'Prefix must be an absolute directory path without dot components or line breaks' "$prefix"; return 1;
  }
  while [[ ! -e "$component" && ! -L "$component" ]]; do component=${component%/*}; [[ -n "$component" ]] || component=/; done
  [[ -d "$component" ]] || { rc_error 'Prefix ancestor is not a directory' "$component"; return 1; }
  validate_rc_path "$component/.tailmux-path-check" || return 1
  read -r uid _ mode _ < <(rc_metadata "$component")
  if [[ "$uid" != "$UID" || ! "$mode" =~ ^[0-7]+$ ]] || (( (8#$mode & 0022) != 0 )); then
    rc_error 'Prefix ancestor must be privately writable and current-user owned' "$component"; return 1;
  fi
}

inspect_installation() {
  local prefix="$1" binary="$1/tailmux" receipt="$1/.tailmux-receipt" line digest
  if [[ ! -e "$binary" && ! -L "$binary" && ! -e "$receipt" && ! -L "$receipt" ]]; then
    return 0
  fi
  [[ -f "$receipt" && ! -L "$receipt" ]] || { rc_error 'Foreign or partial installation; receipt is missing' "$prefix"; return 1; }
  validate_rc_path "$receipt" && validate_rc_metadata "$receipt" || return 1
  { IFS= read -r line; IFS= read -r line; IFS= read -r digest; } < "$receipt" || return 1
  if [[ ! "$digest" =~ ^[a-f0-9]{64}$ ]] || ! cmp -s "$receipt" <(printf 'tailmux-receipt-v1\n%s\n%s\n' "$binary" "$digest"); then
    rc_error 'Foreign or modified installation receipt/content' "$prefix"; return 1;
  fi
  if [[ -e "$binary" || -L "$binary" ]]; then
    [[ -f "$binary" && ! -L "$binary" && -x "$binary" ]] || { rc_error 'Foreign or modified executable' "$binary"; return 1; }
    validate_rc_path "$binary" && validate_rc_metadata "$binary" || return 1
    line="$(content_digest < "$binary")" || return 1
    [[ "${line%% *}" == "$digest" ]] || { rc_error 'Foreign or modified installation receipt/content' "$prefix"; return 1; }
  fi
}

preflight_lifecycle() {
  local rc
  validate_prefix "$TAILMUX_PREFIX" || return 1
  inspect_installation "$TAILMUX_PREFIX" || return 1
  while IFS= read -r rc; do inspect_rc "$rc" >/dev/null || return 1; done < <(rc_paths)
}

migrate_all_rc() {
  local rc
  while IFS= read -r rc; do migrate_rc "$rc" || return 1; done < <(rc_paths)
}

do_install() (
  local stage='' lock="$TAILMUX_PREFIX/.tailmux-install-lock" digest published
  preflight_lifecycle || return 1
  [[ -f "$SCRIPT_DIR/bin/tailmux" && ! -L "$SCRIPT_DIR/bin/tailmux" ]] || { rc_error 'Local executable is missing or symlinked' "$SCRIPT_DIR/bin/tailmux"; return 1; }
  (umask 077; mkdir -p "$TAILMUX_PREFIX") || return 1
  validate_prefix "$TAILMUX_PREFIX" || return 1
  (umask 077; mkdir "$lock") || { rc_error 'Installation lifecycle is locked; inspect before retrying' "$TAILMUX_PREFIX"; return 1; }
  trap '[[ -z "$stage" ]] || { rm -f "$stage/tailmux" "$stage/receipt"; rmdir "$stage"; }; rmdir "$lock"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  preflight_lifecycle || return 1
  stage="$(mktemp -d "$TAILMUX_PREFIX/.tailmux-stage.XXXXXX")" || return 1
  cp "$SCRIPT_DIR/bin/tailmux" "$stage/tailmux" && chmod 755 "$stage/tailmux" || return 1
  cmp -s "$SCRIPT_DIR/bin/tailmux" "$stage/tailmux" || return 1
  digest="$(content_digest < "$stage/tailmux")" || return 1
  digest=${digest%% *}
  printf 'tailmux-receipt-v1\n%s\n%s\n' "$TAILMUX_PREFIX/tailmux" "$digest" > "$stage/receipt" || return 1
  chmod 600 "$stage/receipt" || return 1
  if [[ -f "$TAILMUX_PREFIX/tailmux" ]]; then
    if ! cmp -s "$TAILMUX_PREFIX/tailmux" "$stage/tailmux"; then
      rc_error 'A different owned version is installed; uninstall it with a reviewed checkout before replacing' "$TAILMUX_PREFIX"; return 1
    fi
  else
    if [[ -f "$TAILMUX_PREFIX/.tailmux-receipt" ]]; then
      cmp -s "$stage/receipt" "$TAILMUX_PREFIX/.tailmux-receipt" || { rc_error 'Interrupted installation belongs to a different source digest' "$TAILMUX_PREFIX"; return 1; }
    else
      mv "$stage/receipt" "$TAILMUX_PREFIX/.tailmux-receipt" || return 1
      cmp -s "$TAILMUX_PREFIX/.tailmux-receipt" <(printf 'tailmux-receipt-v1\n%s\n%s\n' "$TAILMUX_PREFIX/tailmux" "$digest") || { rc_error 'Published receipt verification failed' "$TAILMUX_PREFIX"; return 1; }
    fi
    mv "$stage/tailmux" "$TAILMUX_PREFIX/tailmux" || return 1
    published="$(content_digest < "$TAILMUX_PREFIX/tailmux")" || return 1
    [[ "${published%% *}" == "$digest" && -x "$TAILMUX_PREFIX/tailmux" && ! -L "$TAILMUX_PREFIX/tailmux" ]] || { rc_error 'Published executable verification failed' "$TAILMUX_PREFIX"; return 1; }
  fi
  inspect_installation "$TAILMUX_PREFIX" || return 1
  migrate_all_rc || return 1
  printf 'Client installed at %s/tailmux\n' "$TAILMUX_PREFIX"
  printf '%s\n' 'Warning: your current shell may shadow bare tailmux with an alias or loaded function. Use the absolute executable path.' \
    'No PATH or shell code was added. Dependencies and destination SSH/tmux configuration remain operator-owned.'
)
