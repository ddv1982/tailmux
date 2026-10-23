# shellcheck shell=bash
do_uninstall() (
  local id=".tailmux-tx.$$.$RANDOM" backup
  require_installation && preflight_lifecycle || return 1
  if [[ -f "$TAILMUX_PREFIX/.tailmux-receipt" ]]; then
    lifecycle_lock "$TAILMUX_PREFIX" "$id" || return 1
    trap 'lifecycle_unlock "$TAILMUX_PREFIX" "$id"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    preflight_lifecycle || return 1
    migrate_all_rc || return 1
    backup="$(mktemp -d "$TAILMUX_PREFIX/.tailmux-backup.XXXXXX")" || return 1
    cp "$TAILMUX_PREFIX/.tailmux-receipt" "$backup/receipt" && cmp -s "$TAILMUX_PREFIX/.tailmux-receipt" "$backup/receipt" || return 1
    if [[ -e "$TAILMUX_PREFIX/tailmux" ]]; then
      cp "$TAILMUX_PREFIX/tailmux" "$backup/tailmux" && cmp -s "$TAILMUX_PREFIX/tailmux" "$backup/tailmux" || return 1
      rm "$TAILMUX_PREFIX/tailmux" || return 1
    fi
    rm "$TAILMUX_PREFIX/.tailmux-receipt" || return 1
    [[ ! -e "$TAILMUX_PREFIX/tailmux" && ! -L "$TAILMUX_PREFIX/tailmux" && ! -e "$TAILMUX_PREFIX/.tailmux-receipt" && ! -L "$TAILMUX_PREFIX/.tailmux-receipt" ]] || {
      rc_error 'Executable removal verification failed' "$TAILMUX_PREFIX"; return 1;
    }
    printf 'Removed client. Protected backup saved in %s\n' "$backup"
  else
    migrate_all_rc || return 1
  fi
  printf '%s\n' 'Client uninstall complete. Only receipt-owned files and exact recognized legacy blocks were removed.' \
    'Unmanaged shell code, aliases, backups, and networking remain. Existing shells may retain loaded functions.'
)
