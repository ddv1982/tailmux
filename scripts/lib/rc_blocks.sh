# shellcheck shell=bash
readonly TAILMUX_REVIEWED_CORE_DIGEST=81ffdbf42e083621213e52e7a6357837202df0fe5d27f5bf06fdc0123fedc042
readonly TAILMUX_LEGACY_CORE_DIGEST=0063e6bc80fb24698ccaa58e78db3813ee22b7bcd2dbbfa4df6644375cefa1a6
rc_error() {
  printf 'Error: %s (%s). No further RC changes made.\n' "$1" "$2" >&2
  return 1
}

validate_rc_path() {
  local rc="$1" component parent_uid parent_mode ancestor_uid ancestor_mode ancestor_listing
  [[ "$rc" == /* && "$rc" != *$'\n'* && "$rc" != *'/../'* && "$rc" != *'/./'* ]] || {
    rc_error 'RC path must be absolute and contain no dot components or newlines' "$rc"; return 1;
  }
  component="$rc"
  while [[ "$component" != / ]]; do
    if [[ -L "$component" ]]; then
      rc_error 'Symlinked RC paths and ancestors are refused; remove the block manually through your dotfiles owner' "$rc"
      return 1
    fi
    component="${component%/*}"
    [[ -n "$component" ]] || component=/
    if [[ "$(uname -s)" == Darwin ]]; then
      ancestor_listing="$(LC_ALL=C ls -lde "$component")" || return 1
    else
      ancestor_listing="$(LC_ALL=C ls -ld "$component")" || return 1
    fi
    if [[ "$ancestor_listing" == *$'\n'* ]]; then
      if [[ "$(uname -s)" != Darwin || "${ancestor_listing#*$'\n'}" != ' 0: group:everyone deny delete' ]]; then
        rc_error 'Unknown or mutating RC ancestor ACLs are refused' "$rc"; return 1
      fi
    elif [[ "${ancestor_listing%% *}" == *+ ]]; then
      rc_error 'Unknown or mutating RC ancestor ACLs are refused' "$rc"; return 1
    fi
    read -r ancestor_uid _ ancestor_mode _ < <(rc_metadata "$component")
    if [[ "$ancestor_uid" != "$UID" && "$ancestor_uid" != 0 ]] || [[ ! "$ancestor_mode" =~ ^[0-7]+$ ]]; then
      rc_error 'RC ancestor must be owned by the current user or root' "$rc"; return 1
    fi
    if (( (8#$ancestor_mode & 0022) != 0 && (8#$ancestor_mode & 01000) == 0 )); then
      rc_error 'Group or other writable non-sticky RC ancestor is refused' "$rc"; return 1
    fi
  done
  [[ -d "${rc%/*}" ]] || { rc_error 'RC parent directory is missing' "$rc"; return 1; }
  read -r parent_uid _ parent_mode _ < <(rc_metadata "${rc%/*}")
  if [[ "$parent_uid" != "$UID" || ! "$parent_mode" =~ ^[0-7]+$ ]] || (( (8#$parent_mode & 0022) != 0 )); then
    rc_error 'RC parent must be current-user owned and not group or other writable' "$rc"; return 1
  fi
  if [[ -e "$rc" && ! -f "$rc" ]]; then
    rc_error 'RC path is not a regular file' "$rc"; return 1
  fi
}

rc_metadata() {
  if [[ "$(uname -s)" == Darwin ]]; then
    stat -f '%u %g %p %l %i %m %c %z' "$1"
  else
    stat -c '%u %g %a %h %i %Y %Z %s' "$1"
  fi
}

validate_rc_metadata() {
  local rc="$1" uid mode links listing original_bytes text_bytes
  read -r uid _ mode links _ < <(rc_metadata "$rc")
  if [[ "$uid" != "$UID" || "$links" != 1 || ! "$mode" =~ ^[0-7]+$ ]]; then
    rc_error 'RC must be current-user owned with one hard link' "$rc"; return 1
  fi
  if (( (8#$mode & 0022) != 0 )); then
    rc_error 'Group or other writable RC files are refused' "$rc"; return 1
  fi
  if [[ "$(uname -s)" == Darwin ]]; then
    listing="$(LC_ALL=C ls -lde "$rc")" || return 1
  else
    listing="$(LC_ALL=C ls -ld "$rc")" || return 1
  fi
  if [[ "$listing" == *$'\n'* ]]; then
    rc_error 'RC ACLs are refused; use operator-managed removal' "$rc"; return 1
  fi
  listing="${listing%% *}"
  if [[ ${#listing} -ne 10 && ! ( "$(uname -s)" == Darwin && "$listing" == ??????????@ ) ]]; then
    rc_error 'RC has ACLs or extended metadata; use operator-managed removal' "$rc"; return 1
  fi
  original_bytes="$(wc -c < "$rc")" || return 1
  text_bytes="$(LC_ALL=C tr -d '\000' < "$rc" | wc -c)" || return 1
  if [[ "$original_bytes" != "$text_bytes" ]]; then
    rc_error 'RC contains NUL bytes or is unreadable' "$rc"; return 1
  fi
}

core_body_digest() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum
  else
    printf '%s\n' 'Error: shasum or sha256sum is required for managed block ownership checks.' >&2
    return 1
  fi
}

inspect_rc() {
  local rc="$1" line newline offset=0 start=-1 body=-1 end=-1 digest
  local LC_ALL=C
  validate_rc_path "$rc" || return 1
  [[ -e "$rc" ]] || { printf '%s\n' '-1 -1'; return 0; }
  validate_rc_metadata "$rc" || return 1
  exec 3< "$rc" || return 1
  while true; do
    newline=1
    IFS= read -r line || newline=0
    [[ "$newline" == 1 || -n "$line" ]] || break
    case "$line" in
      "$TAILMUX_BLOCK_BEGIN")
        [[ "$start" == -1 && "$newline" == 1 ]] || { rc_error 'Malformed core markers' "$rc"; return 1; }
        start=$offset
        body=$((offset + ${#line} + 1))
        ;;
      "$TAILMUX_BLOCK_END")
        [[ "$body" != -1 && "$end" == -1 ]] || { rc_error 'Malformed core markers' "$rc"; return 1; }
        [[ "$offset" -gt "$body" ]] || { rc_error 'Empty core block' "$rc"; return 1; }
        digest="$(dd if="$rc" bs=1 skip="$body" count="$((offset - body - 1))" 2>/dev/null | core_body_digest)" || return 1
        digest="${digest%% *}"
        case "$digest" in
          "$TAILMUX_REVIEWED_CORE_DIGEST"|"$TAILMUX_LEGACY_CORE_DIGEST") ;;
          *) rc_error 'Unknown or modified core block; markers do not prove ownership' "$rc"; return 1 ;;
        esac
        end=$((offset + ${#line} + newline))
        ;;
      *'tailmux managed block'*)
        case "$line" in
          '# >>> tailmux managed block (taildrive) >>>'|'# <<< tailmux managed block (taildrive) <<<') ;;
          *) rc_error 'Unknown or malformed managed marker' "$rc"; return 1 ;;
        esac
        ;;
    esac
    if [[ "$start" == -1 || "$end" != -1 ]]; then
      if [[ "$line" =~ (^|[[:space:];])(function[[:space:]]+tailmux([[:space:]\(]|$)|tailmux[[:space:]]*\([[:space:]]*\)) ]]; then
        rc_error 'Unmanaged tailmux function; resolve it manually' "$rc"; return 1
      fi
      if [[ "$line" =~ (^|[[:space:];])alias[[:space:]] && "$line" =~ (^|[[:space:]\'\"])tailmux= ]]; then
        rc_error 'Unmanaged tailmux alias; resolve it manually' "$rc"; return 1
      fi
    fi
    offset=$((offset + ${#line} + newline))
    [[ "$newline" == 1 ]] || break
  done <&3
  exec 3<&-
  if [[ "$start" != -1 && "$end" == -1 ]]; then
    rc_error 'Malformed core markers' "$rc"; return 1
  fi
  printf '%s %s\n' "$start" "$end"
}

copy_rc_metadata() {
  if [[ "$(uname -s)" == Darwin ]]; then
    cp -p "$1" "$2"
  else
    cp --preserve=mode,ownership,timestamps,xattr "$1" "$2"
  fi
}

rc_preserved_metadata() {
  rc_metadata "$1" | cut -d ' ' -f 1-4 || return 1
  if [[ "$(uname -s)" == Darwin ]]; then
    stat -f '%f' "$1" || return 1
    xattr -lx "$1" || return 1
  fi
}
