# shellcheck shell=bash
migrate_rc() (
  local expected_digest published_digest expected_metadata published_metadata before_metadata snapshot_metadata stage_metadata current_metadata backup_metadata
  local rc="$1" parent work='' lock backup='' before='' exists=false
  local bounds block_start block_end cursor=0
  parent="${rc%/*}"
  bounds="$(inspect_rc "$rc")" || return 1
  if [[ -z "$bounds" ]]; then
    return 0
  fi
  lock="$rc.tailmux-lock"
  if ! (umask 077; mkdir "$lock"); then
    rc_error 'RC lifecycle is locked; inspect the existing lock before retrying' "$rc"; return 1
  fi
  trap '[[ -z "$work" ]] || { rm -f "$work/original" "$work/result"; rmdir "$work"; }; rmdir "$lock"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  bounds="$(inspect_rc "$rc")" || return 1
  work="$(mktemp -d "$parent/.tailmux-stage.XXXXXX")" || return 1
  if [[ -e "$rc" ]]; then
    exists=true
    [[ -w "$rc" && -w "$parent" ]] || { rc_error 'RC or parent is not writable' "$rc"; return 1; }
    before="$(rc_metadata "$rc")" || return 1
    before_metadata="$(rc_preserved_metadata "$rc")" || return 1
    copy_rc_metadata "$rc" "$work/original" || return 1
    copy_rc_metadata "$rc" "$work/result" || return 1
    cmp -s "$rc" "$work/original" || return 1
    snapshot_metadata="$(rc_preserved_metadata "$work/original")" || return 1
    stage_metadata="$(rc_preserved_metadata "$work/result")" || return 1
    [[ "$before_metadata" == "$stage_metadata" && "$before_metadata" == "$snapshot_metadata" ]] || {
      rc_error 'RC metadata could not be preserved' "$rc"; return 1;
    }
  else
    (umask 077; : > "$work/original"; : > "$work/result") || return 1
  fi
  bounds="$(inspect_rc "$work/original")" || return 1
  {
    while read -r block_start block_end; do
      dd if="$work/original" bs=1 skip="$cursor" count="$((block_start - cursor))" 2>/dev/null || exit 1
      cursor=$block_end
    done <<< "$bounds"
    dd if="$work/original" bs=1 skip="$cursor" 2>/dev/null
  } > "$work/result" || return 1

  if cmp -s "$work/original" "$work/result"; then
    printf 'Managed blocks already absent in %s\n' "$rc"
    return 0
  fi
  expected_digest="$(content_digest < "$work/result")" || return 1
  expected_metadata="$(rc_preserved_metadata "$work/result")" || return 1
  if [[ "$exists" == true && "$expected_metadata" != "$before_metadata" ]]; then
    rc_error 'Staged RC metadata changed during the write' "$rc"; return 1
  fi
  validate_rc_path "$rc" || return 1
  if [[ "$exists" == true ]]; then
    current_metadata="$(rc_preserved_metadata "$rc")" || return 1
    if [[ "$(rc_metadata "$rc")" != "$before" || "$current_metadata" != "$before_metadata" ]] || ! cmp -s "$rc" "$work/original"; then
      rc_error 'RC changed during setup' "$rc"; return 1
    fi
    backup="$(mktemp -d "$parent/.tailmux-backup.XXXXXX")" || return 1
    if ! copy_rc_metadata "$work/original" "$backup/original" || ! cmp -s "$rc" "$backup/original"; then
      rc_error 'Backup failed' "$rc"; return 1
    fi
    backup_metadata="$(rc_preserved_metadata "$backup/original")" || return 1
    [[ "$backup_metadata" == "$before_metadata" ]] || { rc_error 'Backup metadata verification failed' "$rc"; return 1; }
    printf 'Backup saved in %s/original\n' "$backup"
  elif [[ -e "$rc" ]]; then
    rc_error 'RC appeared during setup' "$rc"; return 1
  fi
  if ! mv -f "$work/result" "$rc"; then
    rc_error 'RC replacement failed' "$rc"; return 1
  fi
  validate_rc_path "$rc" || return 1
  published_digest="$(content_digest < "$rc")" || return 1
  published_metadata="$(rc_preserved_metadata "$rc")" || return 1
  if [[ "$expected_digest" != "$published_digest" || "$expected_metadata" != "$published_metadata" ]]; then
    rc_error 'Published RC content or metadata verification failed; inspect the backup' "$rc"; return 1
  fi
  printf 'Recognized managed blocks removed from %s\n' "$rc"
)
