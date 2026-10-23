# shellcheck shell=bash
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
  if [[ ${#listing} -ne 10 &&
    ! ( "$(uname -s)" == Darwin && "$listing" == ??????????@ ) &&
    ! ( "$(uname -s)" == Linux && "$listing" == ??????????. ) ]]; then
    rc_error 'RC has ACLs or extended metadata; use operator-managed removal' "$rc"; return 1
  fi
  original_bytes="$(wc -c < "$rc")" || return 1
  text_bytes="$(LC_ALL=C tr -d '\000' < "$rc" | wc -c)" || return 1
  if [[ "$original_bytes" != "$text_bytes" ]]; then
    rc_error 'RC contains NUL bytes or is unreadable' "$rc"; return 1
  fi
}

content_digest() {
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum
  else
    printf '%s\n' 'Error: shasum or sha256sum is required for file ownership checks.' >&2
    return 1
  fi
}

inspect_rc() {
  local rc="$1" line newline offset=0 start=-1 body=-1 kind='' digest
  local seen_core=false seen_drive=false scan_status=0
  local LC_ALL=C
  if [[ ! -e "$rc" ]]; then
    return 0
  fi
  [[ -f "$rc" ]] || { rc_error 'RC is not regular readable data' "$rc"; return 1; }
  LC_ALL=C grep -aFq 'tailmux managed block' "$rc" || scan_status=$?
  [[ "$scan_status" != 1 ]] || return 0
  [[ "$scan_status" == 0 ]] || { rc_error 'Cannot inspect RC bytes' "$rc"; return 1; }
  validate_rc_path "$rc" || return 1
  validate_rc_metadata "$rc" || return 1
  if [[ "$(uname -s)" != Darwin ]]; then
    rc_preserved_metadata "$rc" >/dev/null || return 1
  fi
  exec 3< "$rc" || return 1
  while true; do
    newline=1
    IFS= read -r line || newline=0
    [[ "$newline" == 1 || -n "$line" ]] || break
    case "$line" in
      '# >>> tailmux managed block (tailmux) >>>'|'# >>> tailmux managed block (taildrive) >>>')
        [[ "$start" == -1 && "$newline" == 1 ]] || { rc_error 'Malformed managed markers' "$rc"; return 1; }
        if [[ "$line" == *'(tailmux)'* ]]; then
          [[ "$seen_core" == false ]] || { rc_error 'Duplicate managed block' "$rc"; return 1; }
          seen_core=true; kind=core
        else
          [[ "$seen_drive" == false ]] || { rc_error 'Duplicate managed block' "$rc"; return 1; }
          seen_drive=true; kind=drive
        fi
        start=$offset; body=$((offset + ${#line} + 1))
        ;;
      '# <<< tailmux managed block (tailmux) <<<'|'# <<< tailmux managed block (taildrive) <<<')
        if [[ "$start" == -1 || ( "$kind" == core && "$line" != *'(tailmux)'* ) ||
          ( "$kind" == drive && "$line" != *'(taildrive)'* ) || "$offset" -le "$body" ]]; then
          rc_error 'Malformed managed markers' "$rc"; return 1
        fi
        digest="$(dd if="$rc" bs=1 skip="$body" count="$((offset - body - 1))" 2>/dev/null | content_digest)" || return 1
        digest="${digest%% *}"
        case "$kind:$digest" in
          core:81ffdbf42e083621213e52e7a6357837202df0fe5d27f5bf06fdc0123fedc042|core:0063e6bc80fb24698ccaa58e78db3813ee22b7bcd2dbbfa4df6644375cefa1a6|drive:e059586f6824dce31ddf49dc75ff70ba44ba25928a3a0516c2fcfda58f83c67e|drive:5882ed870c3811db9669644cc1ae177d9fbaa41d292b84db1d33defcca40e15f|drive:83277c6f973b7fdfd8540faea562af8d368eaf90c8840ec1a9f9403c513ad451) ;;
          *) rc_error 'Unknown or modified managed block; markers do not prove ownership' "$rc"; return 1 ;;
        esac
        printf '%s %s\n' "$start" "$((offset + ${#line} + newline))"
        start=-1; body=-1; kind=''
        ;;
      *'tailmux managed block'*) rc_error 'Unknown or malformed managed marker' "$rc"; return 1 ;;
    esac
    offset=$((offset + ${#line} + newline))
    [[ "$newline" == 1 ]] || break
  done <&3
  exec 3<&-
  [[ "$start" == -1 ]] || { rc_error 'Malformed managed markers' "$rc"; return 1; }
}

copy_rc_metadata() {
  if [[ "$(uname -s)" == Darwin ]]; then
    cp -p "$1" "$2"
  else
    cp --preserve=all -- "$1" "$2"
  fi
}

rc_preserved_metadata() {
  local flags
  rc_metadata "$1" | cut -d ' ' -f 1-4 || return 1
  if [[ "$(uname -s)" == Darwin ]]; then
    stat -f '%f' "$1" || return 1
    xattr -lx "$1" || return 1
  else
    if ! command -v lsattr >/dev/null || ! command -v python3 >/dev/null; then
      rc_error 'Linux legacy migration needs lsattr and Python 3 for metadata verification' "$1"; return 1
    fi
    flags="$(LC_ALL=C lsattr -d -- "$1")" || {
      rc_error 'Cannot verify Linux inode flags; remove the legacy block through your dotfiles owner' "$1"; return 1;
    }
    flags=${flags%% *}
    [[ "$flags" =~ ^[-e]+$ ]] || {
      rc_error 'Unsupported Linux inode flags; remove the legacy block through your dotfiles owner' "$1"; return 1;
    }
    printf '%s\n' "$flags"
    python3 -I -c '
import hashlib, json, os, sys
try:
    path = sys.argv[1]
    attributes = {name: hashlib.sha256(os.getxattr(path, name, follow_symlinks=False)).hexdigest()
                  for name in sorted(os.listxattr(path, follow_symlinks=False))}
    print(json.dumps(attributes, sort_keys=True, ensure_ascii=True))
except (AttributeError, OSError) as error:
    sys.exit("Cannot verify Linux extended attributes: " + str(error))
' "$1" || return 1
  fi
}
